"""
Random Clip Player — Watch Together Server
A lightweight FastAPI server for synced video sessions.

Features:
  - Room creation with hashed passwords
  - WebSocket signaling for playback sync
  - Chunked video upload + HTTP range streaming
  - Auto-cleanup of expired rooms and temp files
  - Rate limiting on join attempts
"""

import os
import sys
import json
import time
import uuid
import string
import random
import asyncio
import hashlib
import logging
import secrets
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

import bcrypt
import aiofiles
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    HTTPException, UploadFile, File, Form, Request,
)
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ============================================================================
# Configuration
# ============================================================================

SERVER_HOST = os.getenv("RDM_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("RDM_PORT", "8765"))
UPLOAD_DIR = Path(os.getenv("RDM_UPLOAD_DIR", "./uploads"))
MAX_FILE_SIZE = int(os.getenv("RDM_MAX_FILE_SIZE_MB", "500")) * 1024 * 1024  # bytes
ROOM_EXPIRY_SECONDS = int(os.getenv("RDM_ROOM_EXPIRY_SECONDS", "14400"))  # 4 hours
CLEANUP_INTERVAL = 300  # 5 minutes
UPLOAD_STALE_SECONDS = 1800  # 30 minutes — incomplete chunked uploads older than this get cleaned up
MAX_JOIN_ATTEMPTS = 5
JOIN_LOCKOUT_SECONDS = 60

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rdm-server")

ALLOWED_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
    '.webm', '.m4v', '.mpeg', '.mpg', '.3gp', '.ts', '.mts',
}

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class User:
    """A connected user in a room."""
    user_id: str
    username: str
    websocket: WebSocket
    joined_at: float = field(default_factory=time.time)


@dataclass
class Room:
    """A watch-together session room."""
    room_code: str
    password_hash: bytes
    host_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    users: dict = field(default_factory=dict)          # user_id -> User
    current_video: Optional[str] = None                # video_id of active clip
    videos: dict = field(default_factory=dict)          # video_id -> file metadata
    shared_pool: bool = False                           # Shared random pool mode
    pool_opted_in: dict = field(default_factory=dict)   # user_id -> {"opted_in": bool, "count": int}
    pending_video: Optional[str] = None                  # video_id waiting for all users to be ready
    ready_users: set = field(default_factory=set)         # user_ids that reported ready for pending_video
    pending_random_request: Optional[dict] = None        # {target_uid, requester_uid, tried: []}
    pending_uploads: dict = field(default_factory=dict)  # upload_id -> chunked upload metadata
    playback_state: dict = field(default_factory=lambda: {
        "playing": False,
        "position": 0.0,       # 0.0 - 1.0
        "speed": 1.0,
        "timestamp": 0.0,      # server time of last state update
    })

    def touch(self):
        self.last_activity = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_activity) > ROOM_EXPIRY_SECONDS

    def user_list(self) -> list:
        return [
            {"user_id": u.user_id, "username": u.username}
            for u in self.users.values()
        ]


# ============================================================================
# State Management
# ============================================================================

class ServerState:
    """Global server state — rooms, rate limits, etc."""

    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.join_attempts: dict[str, list[float]] = {}  # ip -> [timestamps]

    def generate_room_code(self) -> str:
        """Generate a unique room code like 'ABCDE-12345-FGHIJ'."""
        while True:
            p1 = ''.join(random.choices(string.ascii_uppercase, k=5))
            p2 = ''.join(random.choices(string.digits, k=5))
            p3 = ''.join(random.choices(string.ascii_uppercase, k=5))
            code = f"{p1}-{p2}-{p3}"
            if code not in self.rooms:
                return code

    def create_room(self, password: str, host_id: str) -> Room:
        code = self.generate_room_code()
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        room = Room(room_code=code, password_hash=pw_hash, host_id=host_id)
        self.rooms[code] = room
        # Create upload directory for this room
        room_dir = UPLOAD_DIR / code
        room_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Room created: {code}")
        return room

    def verify_password(self, room_code: str, password: str) -> bool:
        room = self.rooms.get(room_code)
        if not room:
            return False
        return bcrypt.checkpw(password.encode(), room.password_hash)

    def check_rate_limit(self, ip: str) -> bool:
        """Returns True if the IP is allowed to attempt joining."""
        now = time.time()
        attempts = self.join_attempts.get(ip, [])
        # Remove old attempts outside the lockout window
        attempts = [t for t in attempts if now - t < JOIN_LOCKOUT_SECONDS]
        self.join_attempts[ip] = attempts
        return len(attempts) < MAX_JOIN_ATTEMPTS

    def record_join_attempt(self, ip: str):
        attempts = self.join_attempts.setdefault(ip, [])
        attempts.append(time.time())

    async def delete_room(self, room_code: str):
        """Delete a room and clean up its files."""
        if room_code in self.rooms:
            del self.rooms[room_code]
        room_dir = UPLOAD_DIR / room_code
        if room_dir.exists():
            await asyncio.to_thread(shutil.rmtree, room_dir, ignore_errors=True)
        log.info(f"Room deleted: {room_code}")

    async def cleanup_expired(self):
        """Remove expired rooms and their files."""
        expired = [code for code, room in self.rooms.items() if room.is_expired]
        for code in expired:
            # Disconnect remaining users
            room = self.rooms[code]
            for user in list(room.users.values()):
                try:
                    await user.websocket.close(1000, "Room expired")
                except Exception:
                    pass
            await self.delete_room(code)
        if expired:
            log.info(f"Cleaned up {len(expired)} expired room(s)")
            
        # Clean up old join attempts
        now = time.time()
        stale_ips = []
        for ip, attempts in self.join_attempts.items():
            valid_attempts = [t for t in attempts if now - t < JOIN_LOCKOUT_SECONDS]
            if valid_attempts:
                self.join_attempts[ip] = valid_attempts
            else:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self.join_attempts[ip]

        # Clean up stale chunked uploads (>30min) in active rooms
        now = time.time()
        for code, room in list(self.rooms.items()):
            stale = [
                uid for uid, info in room.pending_uploads.items()
                if now - info["started_at"] > UPLOAD_STALE_SECONDS
            ]
            for uid in stale:
                info = room.pending_uploads.pop(uid)
                chunks_dir = Path(info["chunks_dir"])
                if chunks_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, str(chunks_dir), True)
                log.info(f"Cleaned up stale chunked upload {uid} in room {code}")


state = ServerState()

# ============================================================================
# Background Tasks
# ============================================================================

async def cleanup_loop():
    """Periodically clean up expired rooms."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        await state.cleanup_expired()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup / shutdown lifecycle."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(cleanup_loop())
    log.info(f"Server started on {SERVER_HOST}:{SERVER_PORT}")
    yield
    task.cancel()
    log.info("Server shutting down")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title="RDM Watch Together Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "rooms": len(state.rooms)}


@app.post("/rooms")
async def create_room(request: Request):
    """Create a new room. Body: { password: str, username: str }"""
    body = await request.json()
    password = body.get("password", "").strip()
    username = body.get("username", "").strip()

    if not password or len(password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    if not username or len(username) > 32:
        raise HTTPException(400, "Username required (max 32 chars)")

    user_id = secrets.token_hex(8)
    room = state.create_room(password, host_id=user_id)

    return {
        "room_code": room.room_code,
        "user_id": user_id,
        "host_id": room.host_id,
    }


@app.post("/rooms/{room_code}/join")
async def join_room(room_code: str, request: Request):
    """Join a room. Body: { password: str, username: str }"""
    client_ip = request.client.host if request.client else "unknown"

    if not state.check_rate_limit(client_ip):
        raise HTTPException(429, "Too many join attempts. Try again later.")

    state.record_join_attempt(client_ip)

    body = await request.json()
    password = body.get("password", "")
    username = body.get("username", "").strip()

    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")
    if not username or len(username) > 32:
        raise HTTPException(400, "Username required (max 32 chars)")
    if not state.verify_password(room_code, password):
        raise HTTPException(403, "Incorrect password")

    user_id = secrets.token_hex(8)
    room = state.rooms[room_code]
    room.touch()

    return {
        "room_code": room.room_code,
        "user_id": user_id,
        "host_id": room.host_id,
        "users": room.user_list(),
        "playback_state": room.playback_state,
        "current_video": room.current_video,
        "videos": {
            vid: {"filename": meta["filename"], "size": meta["size"]}
            for vid, meta in room.videos.items()
        },
    }


@app.post("/rooms/{room_code}/upload")
async def upload_video(
    room_code: str,
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a video clip to a room for streaming to other users."""
    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")

    room = state.rooms[room_code]
    if user_id not in room.users:
        raise HTTPException(403, "Not a member of this room")

    room.touch()

    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Generate a unique video ID
    video_id = secrets.token_hex(8)
    safe_filename = f"{video_id}_{file.filename}"
    room_dir = UPLOAD_DIR / room_code
    room_dir.mkdir(parents=True, exist_ok=True)
    filepath = room_dir / safe_filename

    # Stream upload to disk with size check
    total_size = 0
    chunk_size = 1024 * 256  # 256KB chunks

    try:
        async with aiofiles.open(filepath, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    await f.close()
                    filepath.unlink(missing_ok=True)
                    raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
                await f.write(chunk)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, "Upload failed")

    # Store metadata
    room.videos[video_id] = {
        "filename": file.filename,
        "safe_filename": safe_filename,
        "size": total_size,
        "uploaded_by": user_id,
        "uploaded_at": time.time(),
    }

    # Notify all room members about the new video
    uploader = room.users.get(user_id)
    uploader_name = uploader.username if uploader else "Unknown"

    await broadcast(room, {
        "type": "video_uploaded",
        "video_id": video_id,
        "filename": file.filename,
        "size": total_size,
        "uploaded_by": uploader_name,
    })

    log.info(f"Video uploaded: {file.filename} ({total_size // 1024}KB) to room {room_code}")

    return {"video_id": video_id, "filename": file.filename, "size": total_size}


# ----------------------------------------------------------------------------
# Chunked Upload Endpoints (resumable)
# ----------------------------------------------------------------------------

@app.post("/rooms/{room_code}/upload/init")
async def init_chunked_upload(room_code: str, request: Request):
    """Initialize a resumable chunked upload. Returns an upload_id."""
    body = await request.json()
    user_id = body.get("user_id")
    filename = body.get("filename", "")
    file_size = body.get("file_size", 0)
    chunk_size = body.get("chunk_size", 5 * 1024 * 1024)

    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")
    room = state.rooms[room_code]
    if user_id not in room.users:
        raise HTTPException(403, "Not a member of this room")
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
    if file_size <= 0:
        raise HTTPException(400, "Invalid file size")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    upload_id = secrets.token_hex(8)
    chunks_dir = UPLOAD_DIR / room_code / "chunks" / upload_id
    chunks_dir.mkdir(parents=True, exist_ok=True)

    total_chunks = (file_size + chunk_size - 1) // chunk_size

    room.pending_uploads[upload_id] = {
        "user_id": user_id,
        "filename": filename,
        "file_size": file_size,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "chunks_dir": str(chunks_dir),
        "started_at": time.time(),
        "received_chunks": set(),
        "received_bytes": 0,
    }
    room.touch()

    log.info(f"Chunked upload init: {filename} ({file_size // 1024}KB, {total_chunks} chunks) in room {room_code}")
    return {"upload_id": upload_id, "chunk_size": chunk_size, "total_chunks": total_chunks}


@app.put("/rooms/{room_code}/upload/{upload_id}/chunk/{index}")
async def upload_chunk(room_code: str, upload_id: str, index: int, request: Request):
    """Upload a single chunk of a resumable upload."""
    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")
    room = state.rooms[room_code]
    upload = room.pending_uploads.get(upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found")
    if index < 0 or index >= upload["total_chunks"]:
        raise HTTPException(400, f"Invalid chunk index: {index}")

    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty chunk")

    if upload["received_bytes"] + len(body) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")

    chunk_path = Path(upload["chunks_dir"]) / f"{index:06d}.part"
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(body)

    if index not in upload["received_chunks"]:
        upload["received_chunks"].add(index)
        upload["received_bytes"] += len(body)

    room.touch()
    return {"index": index, "received_bytes": len(body)}


@app.get("/rooms/{room_code}/upload/{upload_id}/status")
async def upload_status(room_code: str, upload_id: str):
    """Get the status of a chunked upload for resume support."""
    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")
    room = state.rooms[room_code]
    upload = room.pending_uploads.get(upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found")

    received = sorted(upload["received_chunks"])
    last_index = received[-1] if received else -1

    return {
        "upload_id": upload_id,
        "last_chunk_index": last_index,
        "received_chunks": len(received),
        "total_chunks": upload["total_chunks"],
        "received_bytes": upload["received_bytes"],
        "expected_bytes": upload["file_size"],
    }


@app.post("/rooms/{room_code}/upload/{upload_id}/complete")
async def complete_chunked_upload(room_code: str, upload_id: str):
    """Merge all chunks into the final file and broadcast video_uploaded."""
    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")
    room = state.rooms[room_code]
    upload = room.pending_uploads.get(upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found")

    expected = set(range(upload["total_chunks"]))
    if upload["received_chunks"] != expected:
        missing = sorted(expected - upload["received_chunks"])
        raise HTTPException(400, f"Missing {len(missing)} chunk(s)")

    video_id = upload_id
    safe_filename = f"{video_id}_{upload['filename']}"
    room_dir = UPLOAD_DIR / room_code
    filepath = room_dir / safe_filename
    chunks_dir = Path(upload["chunks_dir"])

    try:
        async with aiofiles.open(filepath, "wb") as out:
            for i in range(upload["total_chunks"]):
                chunk_path = chunks_dir / f"{i:06d}.part"
                async with aiofiles.open(chunk_path, "rb") as cf:
                    while True:
                        data = await cf.read(262144)  # 256KB
                        if not data:
                            break
                        await out.write(data)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        raise HTTPException(500, f"Failed to merge chunks: {e}")
    finally:
        await asyncio.to_thread(shutil.rmtree, str(chunks_dir), True)

    del room.pending_uploads[upload_id]

    room.videos[video_id] = {
        "filename": upload["filename"],
        "safe_filename": safe_filename,
        "size": upload["received_bytes"],
        "uploaded_by": upload["user_id"],
        "uploaded_at": time.time(),
    }

    uploader = room.users.get(upload["user_id"])
    uploader_name = uploader.username if uploader else "Unknown"
    await broadcast(room, {
        "type": "video_uploaded",
        "video_id": video_id,
        "filename": upload["filename"],
        "size": upload["received_bytes"],
        "uploaded_by": uploader_name,
    })

    log.info(f"Chunked upload complete: {upload['filename']} ({upload['received_bytes'] // 1024}KB) to room {room_code}")
    room.touch()

    return {"video_id": video_id, "filename": upload["filename"], "size": upload["received_bytes"]}


@app.get("/rooms/{room_code}/videos/{video_id}")
async def stream_video(room_code: str, video_id: str, request: Request):
    """Stream a video file with HTTP range request support for chunked playback."""
    if room_code not in state.rooms:
        raise HTTPException(404, "Room not found")

    room = state.rooms[room_code]
    video_meta = room.videos.get(video_id)
    if not video_meta:
        raise HTTPException(404, "Video not found")

    filepath = UPLOAD_DIR / room_code / video_meta["safe_filename"]
    if not filepath.exists():
        raise HTTPException(404, "Video file missing")

    file_size = filepath.stat().st_size
    range_header = request.headers.get("range")

    # Determine content type
    ext = Path(video_meta["filename"]).suffix.lower()
    content_types = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime", ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv", ".m4v": "video/x-m4v",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    if range_header:
        # Parse range request
        range_val = range_header.strip().replace("bytes=", "")
        range_parts = range_val.split("-")
        start = int(range_parts[0]) if range_parts[0] else 0
        end = int(range_parts[1]) if range_parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        async def ranged_file():
            async with aiofiles.open(filepath, "rb") as f:
                await f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_sz = min(65536, remaining)
                    data = await f.read(chunk_sz)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            ranged_file(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
            },
        )
    else:
        # Full file response
        async def full_file():
            async with aiofiles.open(filepath, "rb") as f:
                while True:
                    data = await f.read(65536)
                    if not data:
                        break
                    yield data

        return StreamingResponse(
            full_file(),
            headers={
                "Content-Length": str(file_size),
                "Content-Type": content_type,
                "Accept-Ranges": "bytes",
            },
        )


# ============================================================================
# WebSocket — Real-time Signaling
# ============================================================================

async def broadcast(room: Room, message: dict, exclude_id: str = None):
    """Send a message to all users in a room, optionally excluding one."""
    data = json.dumps(message)
    disconnected = []
    for uid, user in room.users.items():
        if uid == exclude_id:
            continue
        try:
            await user.websocket.send_text(data)
        except Exception:
            disconnected.append(uid)
    # Clean up disconnected users
    for uid in disconnected:
        room.users.pop(uid, None)


async def _ready_timeout(room: Room, video_id: str, timeout: float):
    """Force-start playback if not everyone is ready within the timeout."""
    await asyncio.sleep(timeout)
    if room.pending_video == video_id:
        log.info(f"Ready-sync timeout for {video_id} — forcing start")
        room.pending_video = None
        room.playback_state["playing"] = True
        room.playback_state["position"] = 0.0
        room.playback_state["timestamp"] = time.time()
        uploaded_by = room.videos.get(video_id, {}).get("uploaded_by", "")
        await broadcast(room, {
            "type": "all_ready",
            "video_id": video_id,
            "uploaded_by": uploaded_by,
        })


async def _random_request_timeout(room: Room, target_uid: str, requester_uid: str, tried: list):
    """Timeout for random clip request — retry with another user or fail."""
    await asyncio.sleep(10.0)
    req = room.pending_random_request
    if not req or req.get("target_uid") != target_uid:
        return  # Request was fulfilled or cancelled
    tried.append(target_uid)
    if len(tried) >= 3:
        # Max retries exceeded — notify requester
        room.pending_random_request = None
        requester = room.users.get(requester_uid)
        if requester:
            try:
                await requester.websocket.send_json({
                    "type": "random_failed",
                    "message": "Kein User konnte einen Clip liefern",
                })
            except Exception:
                pass
        return
    # Try next eligible user
    eligible = [
        uid for uid, info in room.pool_opted_in.items()
        if isinstance(info, dict) and info.get("opted_in") and info.get("count", 0) > 0
        and uid in room.users and uid not in tried and not info.get("exhausted")
    ]
    if not eligible:
        room.pending_random_request = None
        requester = room.users.get(requester_uid)
        if requester:
            try:
                await requester.websocket.send_json({
                    "type": "random_failed",
                    "message": "Kein User konnte einen Clip liefern",
                })
            except Exception:
                pass
        return
    next_uid = random.choice(eligible)
    room.pending_random_request = {
        "target_uid": next_uid,
        "requester_uid": requester_uid,
        "tried": tried,
    }
    target = room.users.get(next_uid)
    if target:
        try:
            requester_name = room.users.get(requester_uid)
            await target.websocket.send_json({
                "type": "provide_random_clip",
                "requested_by": requester_name.username if requester_name else "Unknown",
            })
        except Exception:
            pass
    asyncio.create_task(_random_request_timeout(room, next_uid, requester_uid, tried))


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    """WebSocket connection for room signaling."""
    await websocket.accept()

    if room_code not in state.rooms:
        await websocket.send_json({"type": "error", "message": "Room not found"})
        await websocket.close()
        return

    room = state.rooms[room_code]
    user_id = None

    try:
        # First message must be authentication
        auth_data = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if auth_data.get("type") != "auth":
            await websocket.send_json({"type": "error", "message": "Auth required"})
            await websocket.close()
            return

        user_id = auth_data.get("user_id")
        username = auth_data.get("username", "Anonymous")

        if not user_id:
            await websocket.send_json({"type": "error", "message": "Invalid user_id"})
            await websocket.close()
            return

        # Register user in room
        user = User(user_id=user_id, username=username, websocket=websocket)
        room.users[user_id] = user
        room.pool_opted_in.setdefault(user_id, True)  # Default to opted-in
        room.touch()

        # Send current room state
        await websocket.send_json({
            "type": "room_state",
            "users": room.user_list(),
            "playback_state": room.playback_state,
            "current_video": room.current_video,
            "host_id": room.host_id,
            "videos": {
                vid: {"filename": meta["filename"], "size": meta["size"]}
                for vid, meta in room.videos.items()
            },
        })

        # Notify others that user joined
        await broadcast(room, {
            "type": "user_joined",
            "user_id": user_id,
            "username": username,
            "users": room.user_list(),
        }, exclude_id=user_id)

        log.info(f"User '{username}' ({user_id[:8]}) joined room {room_code}")

        # Main message loop
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            room.touch()

            if msg_type == "play":
                room.playback_state["playing"] = True
                room.playback_state["position"] = data.get("position", 0.0)
                room.playback_state["timestamp"] = time.time()
                await broadcast(room, {
                    "type": "play",
                    "position": room.playback_state["position"],
                    "user": username,
                    "timestamp": room.playback_state["timestamp"],
                }, exclude_id=user_id)

            elif msg_type == "pause":
                room.playback_state["playing"] = False
                room.playback_state["position"] = data.get("position", 0.0)
                room.playback_state["timestamp"] = time.time()
                await broadcast(room, {
                    "type": "pause",
                    "position": room.playback_state["position"],
                    "user": username,
                    "timestamp": room.playback_state["timestamp"],
                }, exclude_id=user_id)

            elif msg_type == "seek":
                room.playback_state["position"] = data.get("position", 0.0)
                room.playback_state["timestamp"] = time.time()
                await broadcast(room, {
                    "type": "seek",
                    "position": room.playback_state["position"],
                    "user": username,
                    "timestamp": room.playback_state["timestamp"],
                }, exclude_id=user_id)

            elif msg_type == "speed":
                speed = data.get("speed", 1.0)
                room.playback_state["speed"] = speed
                await broadcast(room, {
                    "type": "speed",
                    "speed": speed,
                    "user": username,
                }, exclude_id=user_id)

            elif msg_type == "play_video":
                video_id = data.get("video_id")
                if video_id and video_id in room.videos:
                    # Clear pending random request if this is the response
                    req = room.pending_random_request
                    if req and req.get("target_uid") == user_id:
                        room.pending_random_request = None
                    # Reject if a transition is already in progress
                    if room.pending_video is not None:
                        await websocket.send_json({
                            "type": "transition_busy",
                            "message": "A clip is already being loaded. Please wait.",
                            "pending_video_id": room.pending_video,
                        })
                        log.info(f"Rejected play_video {video_id} — transition in progress for {room.pending_video} in room {room_code}")
                        continue
                    room.current_video = video_id
                    # Start ready-sync: pause playback, tell everyone to download
                    room.playback_state["playing"] = False
                    room.playback_state["position"] = 0.0
                    room.playback_state["timestamp"] = time.time()
                    room.pending_video = video_id
                    room.ready_users = {user_id}  # Sharer is already ready
                    # Tell all OTHER users to prepare this video
                    await broadcast(room, {
                        "type": "prepare_video",
                        "video_id": video_id,
                        "filename": room.videos[video_id]["filename"],
                        "user": username,
                        "timestamp": room.playback_state["timestamp"],
                    }, exclude_id=user_id)
                    # Check if sharer is the only user — start immediately
                    uploaded_by = room.videos[video_id].get("uploaded_by", "")
                    if len(room.users) <= 1:
                        room.pending_video = None
                        room.playback_state["playing"] = True
                        room.playback_state["timestamp"] = time.time()
                        await websocket.send_json({
                            "type": "all_ready",
                            "video_id": video_id,
                            "uploaded_by": uploaded_by,
                        })
                    else:
                        log.info(f"Ready-sync started for {video_id} in room {room_code} (1/{len(room.users)} ready)")
                        # Timeout: force start after 30 seconds if not everyone is ready
                        asyncio.create_task(_ready_timeout(room, video_id, 30.0))

            elif msg_type == "ready":
                # User finished downloading and is ready to play
                ready_video_id = data.get("video_id")
                if room.pending_video and ready_video_id == room.pending_video:
                    room.ready_users.add(user_id)
                    total = len(room.users)
                    ready_count = len(room.ready_users & set(room.users.keys()))
                    log.info(f"Ready-sync: {ready_count}/{total} for {ready_video_id} in room {room_code}")
                    # Broadcast progress to everyone
                    await broadcast(room, {
                        "type": "ready_progress",
                        "video_id": ready_video_id,
                        "ready": ready_count,
                        "total": total,
                    })
                    # All users ready? Start playback!
                    if ready_count >= total:
                        room.pending_video = None
                        room.playback_state["playing"] = True
                        room.playback_state["position"] = 0.0
                        room.playback_state["timestamp"] = time.time()
                        uploaded_by = room.videos.get(ready_video_id, {}).get("uploaded_by", "")
                        await broadcast(room, {
                            "type": "all_ready",
                            "video_id": ready_video_id,
                            "uploaded_by": uploaded_by,
                        })
                        log.info(f"All ready! Playback started for {ready_video_id} in room {room_code}")

            elif msg_type == "kick":
                # Only the host can kick users
                if user_id != room.host_id:
                    await websocket.send_json({"type": "error", "message": "Only the host can kick users"})
                    continue
                target_id = data.get("target_user_id")
                if not target_id or target_id == user_id:
                    continue
                target_user = room.users.get(target_id)
                if target_user:
                    target_name = target_user.username
                    # Close the target's WebSocket
                    try:
                        await target_user.websocket.send_json({
                            "type": "kicked",
                            "message": f"You were kicked by {username}",
                        })
                        await target_user.websocket.close(1000, "Kicked by host")
                    except Exception:
                        pass
                    room.users.pop(target_id, None)
                    log.info(f"Host '{username}' kicked '{target_name}' from room {room_code}")
                    # Notify remaining users
                    await broadcast(room, {
                        "type": "user_kicked",
                        "username": target_name,
                        "kicked_by": username,
                        "users": room.user_list(),
                    })

            elif msg_type == "set_shared_pool":
                # Only the host can toggle shared pool
                if user_id != room.host_id:
                    await websocket.send_json({"type": "error", "message": "Only the host can change pool mode"})
                    continue
                room.shared_pool = data.get("enabled", False)
                await broadcast(room, {
                    "type": "shared_pool_changed",
                    "enabled": room.shared_pool,
                    "changed_by": username,
                })
                log.info(f"Shared pool {'enabled' if room.shared_pool else 'disabled'} in room {room_code}")

            elif msg_type == "pool_opt_in":
                opted_in = data.get("opted_in", True)
                clip_count = data.get("clip_count", 0)
                room.pool_opted_in[user_id] = {"opted_in": opted_in, "count": clip_count}
                await broadcast(room, {
                    "type": "pool_opt_in_changed",
                    "user_id": user_id,
                    "username": username,
                    "opted_in": opted_in,
                })
                log.info(f"Pool opt-in for '{username}' in room {room_code}: {opted_in} (clips: {clip_count})")

            elif msg_type == "request_random":
                # In shared pool mode, pick a random user to provide a clip
                if room.shared_pool and len(room.users) > 0:
                    # Filter: opted_in=True AND count > 0 AND not exhausted
                    eligible = [
                        uid for uid, info in room.pool_opted_in.items()
                        if isinstance(info, dict) and info.get("opted_in") and info.get("count", 0) > 0
                        and uid in room.users and not info.get("exhausted")
                    ]
                    if not eligible:
                        # Check if all exhausted → pool_reset
                        all_exhausted = all(
                            isinstance(info, dict) and info.get("exhausted")
                            for uid, info in room.pool_opted_in.items()
                            if isinstance(info, dict) and info.get("opted_in") and uid in room.users
                        )
                        if all_exhausted and any(
                            isinstance(info, dict) and info.get("opted_in") and uid in room.users
                            for uid, info in room.pool_opted_in.items()
                        ):
                            # Reset all exhausted flags
                            for uid, info in room.pool_opted_in.items():
                                if isinstance(info, dict):
                                    info["exhausted"] = False
                            await broadcast(room, {"type": "pool_reset"})
                            log.info(f"Pool reset in room {room_code} — all users exhausted")
                            # Re-filter after reset
                            eligible = [
                                uid for uid, info in room.pool_opted_in.items()
                                if isinstance(info, dict) and info.get("opted_in") and info.get("count", 0) > 0
                                and uid in room.users
                            ]
                    if eligible:
                        target_uid = random.choice(eligible)
                        room.pending_random_request = {
                            "target_uid": target_uid,
                            "requester_uid": user_id,
                            "tried": [],
                        }
                        target = room.users.get(target_uid)
                        if target:
                            try:
                                await target.websocket.send_json({
                                    "type": "provide_random_clip",
                                    "requested_by": username,
                                })
                            except Exception:
                                pass
                        asyncio.create_task(_random_request_timeout(room, target_uid, user_id, []))
                    else:
                        await websocket.send_json({
                            "type": "random_failed",
                            "message": "Keine eligible User im Pool",
                        })
                else:
                    # Not in shared pool mode — just tell the requester to play their own
                    await websocket.send_json({
                        "type": "provide_random_clip",
                        "requested_by": username,
                    })

            elif msg_type == "pool_exhausted":
                # User's play queue is exhausted
                info = room.pool_opted_in.get(user_id)
                if isinstance(info, dict):
                    info["exhausted"] = True
                log.info(f"Pool exhausted for '{username}' in room {room_code}")

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "position_heartbeat":
                await broadcast(room, {
                    "type": "position_heartbeat",
                    "position": data.get("position", 0.0),
                    "speed": data.get("speed", 1.0),
                }, exclude_id=user_id)

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        log.warning(f"WebSocket auth timeout for room {room_code}")
    except Exception as e:
        log.error(f"WebSocket error in room {room_code}: {e}")
    finally:
        # Clean up user
        if user_id and room_code in state.rooms:
            room = state.rooms[room_code]
            leaving_user = room.users.pop(user_id, None)
            username = leaving_user.username if leaving_user else "Unknown"

            log.info(f"User '{username}' left room {room_code}")

            # Clean up pending random request if this user was the target
            req = room.pending_random_request
            if req and req.get("target_uid") == user_id:
                room.pending_random_request = None  # Timeout task will handle retry

            # Notify remaining users
            await broadcast(room, {
                "type": "user_left",
                "user_id": user_id,
                "username": username,
                "users": room.user_list(),
            })

            # If room is empty, schedule cleanup
            if not room.users:
                log.info(f"Room {room_code} is empty, will expire after inactivity")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )
