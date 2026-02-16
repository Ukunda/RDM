"""
Random Clip Player — Session Client
Handles all networking for Watch Together: WebSocket signaling + HTTP upload/download.

Runs in a background thread to keep the UI responsive.
All communication with the UI is via Qt signals.
"""

import os
import json
import time
import threading
import tempfile
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

# Use requests for HTTP (simpler, synchronous, runs in thread)
import requests
import websocket  # websocket-client library

log = logging.getLogger("rdm-session")

# ============================================================================
# Session Client Signals (thread-safe communication with UI)
# ============================================================================

class SessionSignals(QObject):
    """Qt signals emitted by the session client for the UI to react to."""

    # Connection
    connected = pyqtSignal()                      # Successfully connected to server
    disconnected = pyqtSignal(str)                 # Disconnected (reason)
    connection_error = pyqtSignal(str)             # Failed to connect

    # Room
    room_created = pyqtSignal(str, str)            # (room_code, user_id)
    room_joined = pyqtSignal(dict)                 # Full room state dict
    room_error = pyqtSignal(str)                   # Room create/join error

    # Users
    user_joined = pyqtSignal(str, list)            # (username, users_list)
    user_left = pyqtSignal(str, list)              # (username, users_list)
    user_kicked = pyqtSignal(str, str, list)        # (username, kicked_by, users_list)
    kicked = pyqtSignal(str)                        # (message) — you were kicked

    # Playback sync
    remote_play = pyqtSignal(float, str)           # (position, username)
    remote_pause = pyqtSignal(float, str)          # (position, username)
    remote_seek = pyqtSignal(float, str)           # (position, username)
    remote_speed = pyqtSignal(float, str)          # (speed, username)
    remote_play_video = pyqtSignal(str, str, str)  # (video_id, filename, username)

    # Video sharing
    video_uploaded = pyqtSignal(str, str, int, str)  # (video_id, filename, size, uploader)
    upload_progress = pyqtSignal(int, int)           # (bytes_sent, total_bytes)
    download_progress = pyqtSignal(int, int)         # (bytes_recv, total_bytes)
    video_ready = pyqtSignal(str, str)               # (video_id, local_filepath)

    # Ready-sync: server tells us to prepare a video, then signals all_ready
    prepare_video = pyqtSignal(str, str, str)         # (video_id, filename, username) — download & wait
    all_ready = pyqtSignal(str)                       # (video_id) — everyone is ready, start playback
    ready_progress = pyqtSignal(int, int)             # (ready_count, total_count)

    # Sync on join
    sync_to_video = pyqtSignal(str, str, dict)       # (video_id, filename, playback_state)

    # Shared pool — server asks you to provide a random clip
    random_clip_requested = pyqtSignal()              # Server wants us to share a random clip
    shared_pool_changed = pyqtSignal(bool, str)       # (enabled, changed_by)

    # Ping
    ping_result = pyqtSignal(int)                   # (latency_ms)


# ============================================================================
# Session Client
# ============================================================================

class SessionClient:
    """
    Manages the connection to an RDM Watch Together server.
    
    Usage:
        client = SessionClient()
        client.signals.connected.connect(on_connected)
        client.create_room("http://server:8765", "MyName", "password123")
        
        # Or join:
        client.join_room("http://server:8765", "MyName", "ABCD-1234", "password123")
        
        # Send playback events:
        client.send_play(0.5)
        client.send_pause(0.5)
        
        # Share a clip:
        client.upload_and_play("/path/to/clip.mp4")
        
        # Disconnect:
        client.disconnect()
    """

    def __init__(self):
        self.signals = SessionSignals()

        self._server_url: Optional[str] = None
        self._room_code: Optional[str] = None
        self._user_id: Optional[str] = None
        self._username: Optional[str] = None
        self._host_id: Optional[str] = None

        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._connected = False
        self._shutting_down = False

        # Temp directory for downloaded videos
        self._download_dir = Path(tempfile.mkdtemp(prefix="rdm_session_"))

        # Track available videos
        self._videos: dict = {}  # video_id -> metadata

        # Ping measurement
        self._ping_sent_at: float = 0.0
        self._ping_timer: Optional[threading.Timer] = None

        # Auto-reconnect state
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_timer: Optional[threading.Timer] = None
        self._last_password: Optional[str] = None  # Saved for reconnect

    # ====================================================================
    # Properties
    # ====================================================================

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def room_code(self) -> Optional[str]:
        return self._room_code

    @property
    def user_id(self) -> Optional[str]:
        return self._user_id

    @property
    def username(self) -> Optional[str]:
        return self._username

    @property
    def is_host(self) -> bool:
        return self._user_id == self._host_id

    # ====================================================================
    # Connection
    # ====================================================================

    def test_connection(self, server_url: str) -> tuple[bool, str]:
        """Test if a server is reachable. Returns (success, message)."""
        try:
            url = self._normalize_url(server_url)
            resp = requests.get(f"{url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return True, f"Server OK — {data.get('rooms', 0)} active rooms"
            return False, f"Server returned {resp.status_code}"
        except requests.ConnectionError:
            return False, "Cannot reach server"
        except requests.Timeout:
            return False, "Connection timed out"
        except Exception as e:
            return False, str(e)

    def create_room(self, server_url: str, username: str, password: str):
        """Create a new room on the server, then connect via WebSocket."""
        self._shutting_down = False
        self._reconnect_attempts = 0
        self._last_password = password
        threading.Thread(
            target=self._create_room_thread,
            args=(server_url, username, password),
            daemon=True,
        ).start()

    def join_room(self, server_url: str, username: str, room_code: str, password: str):
        """Join an existing room, then connect via WebSocket."""
        self._shutting_down = False
        self._reconnect_attempts = 0
        self._last_password = password
        threading.Thread(
            target=self._join_room_thread,
            args=(server_url, username, room_code, password),
            daemon=True,
        ).start()

    def disconnect(self):
        """Disconnect from the current session."""
        self._shutting_down = True
        self._reconnect_attempts = self._max_reconnect_attempts  # Prevent reconnect
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        self.stop_ping_loop()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._connected = False
        self._room_code = None
        self._user_id = None
        self._videos.clear()

    # ====================================================================
    # Send Playback Events
    # ====================================================================

    def send_play(self, position: float):
        self._send({"type": "play", "position": position})

    def send_pause(self, position: float):
        self._send({"type": "pause", "position": position})

    def send_seek(self, position: float):
        self._send({"type": "seek", "position": position})

    def send_speed(self, speed: float):
        self._send({"type": "speed", "speed": speed})

    def send_play_video(self, video_id: str):
        self._send({"type": "play_video", "video_id": video_id})

    def send_kick(self, target_user_id: str):
        self._send({"type": "kick", "target_user_id": target_user_id})

    def send_request_random(self):
        """Request the server to pick a random user to play their next clip."""
        self._send({"type": "request_random"})

    def send_ready(self, video_id: str):
        """Tell the server we've downloaded this video and are ready to play."""
        self._send({"type": "ready", "video_id": video_id})

    def send_set_shared_pool(self, enabled: bool):
        """Host toggles shared random pool mode."""
        self._send({"type": "set_shared_pool", "enabled": enabled})

    def send_ping(self):
        """Send a ping to measure round-trip latency."""
        self._ping_sent_at = time.monotonic()
        self._send({"type": "ping"})

    def start_ping_loop(self, interval: float = 5.0):
        """Start a repeating ping every `interval` seconds."""
        self.stop_ping_loop()
        def _loop():
            if self._connected and not self._shutting_down:
                self.send_ping()
                self._ping_timer = threading.Timer(interval, _loop)
                self._ping_timer.daemon = True
                self._ping_timer.start()
        _loop()

    def stop_ping_loop(self):
        """Stop the repeating ping timer."""
        if self._ping_timer:
            self._ping_timer.cancel()
            self._ping_timer = None

    # ====================================================================
    # Auto-Reconnect
    # ====================================================================

    def _attempt_reconnect(self):
        """Try to reconnect to the room with exponential backoff."""
        self._reconnect_attempts += 1
        delay = min(2 ** self._reconnect_attempts, 30)  # 2s, 4s, 8s, 16s, 30s
        log.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})")
        self.signals.connection_error.emit(
            f"Connection lost — reconnecting in {delay}s ({self._reconnect_attempts}/{self._max_reconnect_attempts})"
        )
        self._reconnect_timer = threading.Timer(delay, self._reconnect_thread)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _reconnect_thread(self):
        """Re-join the room and reconnect WebSocket."""
        if self._shutting_down:
            return
        try:
            resp = requests.post(
                f"{self._server_url}/rooms/{self._room_code}/join",
                json={"password": self._last_password or "", "username": self._username},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._user_id = data["user_id"]
                self._host_id = data["host_id"]
                self._reconnect_attempts = 0
                log.info("Reconnected successfully")
                self.signals.room_joined.emit(data)
                self._connect_ws()
            elif resp.status_code == 404:
                # Room no longer exists
                log.info("Room no longer exists, giving up reconnect")
                self.signals.disconnected.emit("Room no longer exists")
            else:
                # Retry
                if self._reconnect_attempts < self._max_reconnect_attempts:
                    self._attempt_reconnect()
                else:
                    self.signals.disconnected.emit("Failed to reconnect")
        except Exception as e:
            log.error(f"Reconnect failed: {e}")
            if self._reconnect_attempts < self._max_reconnect_attempts:
                self._attempt_reconnect()
            else:
                self.signals.disconnected.emit("Failed to reconnect")

    # ====================================================================
    # Video Upload / Download
    # ====================================================================

    def upload_and_play(self, filepath: str):
        """Upload a local video to the server and tell the room to play it."""
        threading.Thread(
            target=self._upload_thread,
            args=(filepath,),
            daemon=True,
        ).start()

    def download_video(self, video_id: str):
        """Download a video from the server to a local temp file."""
        threading.Thread(
            target=self._download_thread,
            args=(video_id,),
            daemon=True,
        ).start()

    def get_local_video_path(self, video_id: str) -> Optional[str]:
        """Get the local path of a previously downloaded video, or None."""
        meta = self._videos.get(video_id)
        if meta and meta.get("local_path"):
            path = meta["local_path"]
            if os.path.exists(path):
                return path
        return None

    # ====================================================================
    # Internal: Room Creation/Joining
    # ====================================================================

    def _normalize_url(self, url: str) -> str:
        url = url.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        return url

    def _ws_url(self, http_url: str) -> str:
        return http_url.replace("http://", "ws://").replace("https://", "wss://")

    def _create_room_thread(self, server_url: str, username: str, password: str):
        try:
            url = self._normalize_url(server_url)
            self._server_url = url
            self._username = username

            resp = requests.post(
                f"{url}/rooms",
                json={"password": password, "username": username},
                timeout=10,
            )

            if resp.status_code != 200:
                error = resp.json().get("detail", resp.text)
                self.signals.room_error.emit(f"Failed to create room: {error}")
                return

            data = resp.json()
            self._room_code = data["room_code"]
            self._user_id = data["user_id"]
            self._host_id = data["host_id"]

            self.signals.room_created.emit(self._room_code, self._user_id)

            # Connect WebSocket
            self._connect_ws()

        except requests.ConnectionError:
            self.signals.connection_error.emit("Cannot reach server")
        except Exception as e:
            self.signals.connection_error.emit(str(e))

    def _join_room_thread(self, server_url: str, username: str, room_code: str, password: str):
        try:
            url = self._normalize_url(server_url)
            self._server_url = url
            self._username = username

            resp = requests.post(
                f"{url}/rooms/{room_code}/join",
                json={"password": password, "username": username},
                timeout=10,
            )

            if resp.status_code == 429:
                self.signals.room_error.emit("Too many attempts. Try again later.")
                return
            elif resp.status_code == 404:
                self.signals.room_error.emit("Room not found")
                return
            elif resp.status_code == 403:
                self.signals.room_error.emit("Incorrect password")
                return
            elif resp.status_code != 200:
                error = resp.json().get("detail", resp.text)
                self.signals.room_error.emit(f"Failed to join: {error}")
                return

            data = resp.json()
            self._room_code = data["room_code"]
            self._user_id = data["user_id"]
            self._host_id = data["host_id"]
            self._videos = {
                vid: meta for vid, meta in data.get("videos", {}).items()
            }

            self.signals.room_joined.emit(data)

            # Connect WebSocket
            self._connect_ws()

        except requests.ConnectionError:
            self.signals.connection_error.emit("Cannot reach server")
        except Exception as e:
            self.signals.connection_error.emit(str(e))

    # ====================================================================
    # Internal: WebSocket
    # ====================================================================

    def _connect_ws(self):
        """Connect the WebSocket to the room."""
        ws_url = f"{self._ws_url(self._server_url)}/ws/{self._room_code}"

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )

        # Run in its own thread
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            daemon=True,
        )
        self._ws_thread.start()

    def _on_ws_open(self, ws):
        """Send auth message on connect."""
        ws.send(json.dumps({
            "type": "auth",
            "user_id": self._user_id,
            "username": self._username,
        }))
        self._connected = True
        self.signals.connected.emit()
        self.start_ping_loop()

    def _on_ws_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "room_state":
                self.signals.room_joined.emit(data)
                # Sync-on-join: if there's an active video, trigger download + sync
                current_vid = data.get("current_video")
                if current_vid:
                    videos = data.get("videos", {})
                    vid_meta = videos.get(current_vid, {})
                    filename = vid_meta.get("filename", f"{current_vid}.mp4")
                    self._videos.update({
                        vid: meta for vid, meta in videos.items()
                    })
                    playback = data.get("playback_state", {})
                    self.signals.sync_to_video.emit(current_vid, filename, playback)
                    self.download_video(current_vid)

            elif msg_type == "user_joined":
                self.signals.user_joined.emit(
                    data.get("username", ""),
                    data.get("users", []),
                )

            elif msg_type == "user_left":
                self.signals.user_left.emit(
                    data.get("username", ""),
                    data.get("users", []),
                )

            elif msg_type == "kicked":
                # We were kicked from the room
                self._connected = False
                self.signals.kicked.emit(data.get("message", "Kicked from room"))

            elif msg_type == "user_kicked":
                self.signals.user_kicked.emit(
                    data.get("username", ""),
                    data.get("kicked_by", ""),
                    data.get("users", []),
                )

            elif msg_type == "play":
                self.signals.remote_play.emit(
                    data.get("position", 0.0),
                    data.get("user", ""),
                )

            elif msg_type == "pause":
                self.signals.remote_pause.emit(
                    data.get("position", 0.0),
                    data.get("user", ""),
                )

            elif msg_type == "seek":
                self.signals.remote_seek.emit(
                    data.get("position", 0.0),
                    data.get("user", ""),
                )

            elif msg_type == "speed":
                self.signals.remote_speed.emit(
                    data.get("speed", 1.0),
                    data.get("user", ""),
                )

            elif msg_type == "play_video":
                video_id = data.get("video_id", "")
                filename = data.get("filename", "")
                user = data.get("user", "")
                self.signals.remote_play_video.emit(video_id, filename, user)
                # Auto-download the video
                self.download_video(video_id)

            elif msg_type == "prepare_video":
                # New ready-sync: download the video, then report ready
                video_id = data.get("video_id", "")
                filename = data.get("filename", "")
                user = data.get("user", "")
                self.signals.prepare_video.emit(video_id, filename, user)
                # Auto-download — when done, video_ready signal fires → UI sends ready
                self.download_video(video_id)

            elif msg_type == "all_ready":
                # Everyone has downloaded — start playback
                video_id = data.get("video_id", "")
                self.signals.all_ready.emit(video_id)

            elif msg_type == "ready_progress":
                ready_count = data.get("ready", 0)
                total = data.get("total", 0)
                self.signals.ready_progress.emit(ready_count, total)

            elif msg_type == "video_uploaded":
                video_id = data.get("video_id", "")
                filename = data.get("filename", "")
                size = data.get("size", 0)
                uploader = data.get("uploaded_by", "")
                self._videos[video_id] = {"filename": filename, "size": size}
                self.signals.video_uploaded.emit(video_id, filename, size, uploader)

            elif msg_type == "pong":
                if self._ping_sent_at > 0:
                    latency_ms = int((time.monotonic() - self._ping_sent_at) * 1000)
                    self._ping_sent_at = 0.0
                    self.signals.ping_result.emit(latency_ms)

            elif msg_type == "provide_random_clip":
                # Server picked us to share a random clip
                self.signals.random_clip_requested.emit()

            elif msg_type == "shared_pool_changed":
                self.signals.shared_pool_changed.emit(
                    data.get("enabled", False),
                    data.get("changed_by", ""),
                )

            elif msg_type == "error":
                self.signals.room_error.emit(data.get("message", "Unknown error"))

        except json.JSONDecodeError:
            log.warning(f"Invalid JSON from server: {message[:100]}")
        except Exception as e:
            log.error(f"Error handling WS message: {e}")

    def _on_ws_error(self, ws, error):
        if not self._shutting_down:
            log.error(f"WebSocket error: {error}")
            self.signals.connection_error.emit(str(error))

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self._connected = False
        self.stop_ping_loop()
        if not self._shutting_down:
            # Try auto-reconnect before fully disconnecting
            if self._reconnect_attempts < self._max_reconnect_attempts and self._room_code and self._server_url:
                self._attempt_reconnect()
            else:
                reason = close_msg or "Connection closed"
                self.signals.disconnected.emit(reason)

    def _send(self, data: dict):
        """Send a JSON message over WebSocket."""
        if self._ws and self._connected:
            try:
                self._ws.send(json.dumps(data))
            except Exception as e:
                log.error(f"Failed to send WS message: {e}")

    # ====================================================================
    # Internal: Upload / Download
    # ====================================================================

    def _upload_thread(self, filepath: str):
        """Upload a video file, then tell the room to play it."""
        try:
            if not os.path.exists(filepath):
                self.signals.room_error.emit(f"File not found: {filepath}")
                return

            file_size = os.path.getsize(filepath)
            filename = os.path.basename(filepath)

            # Upload with progress tracking
            url = f"{self._server_url}/rooms/{self._room_code}/upload"

            # Use a generator to track upload progress (throttled to ~20 updates/sec)
            class ProgressFile:
                def __init__(self, path, signals, total_size):
                    self._file = open(path, "rb")
                    self._signals = signals
                    self._total = total_size
                    self._sent = 0
                    self._last_emit = 0.0

                def read(self, size=-1):
                    data = self._file.read(size)
                    self._sent += len(data)
                    now = time.monotonic()
                    if now - self._last_emit >= 0.05 or self._sent >= self._total:
                        self._signals.upload_progress.emit(self._sent, self._total)
                        self._last_emit = now
                    return data

                def __getattr__(self, name):
                    return getattr(self._file, name)

            progress_file = ProgressFile(filepath, self.signals, file_size)

            resp = requests.post(
                url,
                data={"user_id": self._user_id},
                files={"file": (filename, progress_file, "application/octet-stream")},
                timeout=600,  # 10 minute timeout for large files
            )

            progress_file._file.close()

            if resp.status_code != 200:
                error = resp.json().get("detail", resp.text)
                self.signals.room_error.emit(f"Upload failed: {error}")
                return

            data = resp.json()
            video_id = data["video_id"]

            # Store locally too (we already have the file)
            self._videos[video_id] = {
                "filename": filename,
                "size": file_size,
                "local_path": filepath,
            }

            # Tell room to play this video (server starts ready-sync)
            self.send_play_video(video_id)
            self.signals.video_ready.emit(video_id, filepath)

        except Exception as e:
            log.error(f"Upload error: {e}")
            self.signals.room_error.emit(f"Upload error: {e}")

    def _download_thread(self, video_id: str):
        """Download a video from the server to a local temp file."""
        try:
            # Check if already downloaded
            existing = self.get_local_video_path(video_id)
            if existing:
                self.signals.video_ready.emit(video_id, existing)
                return

            meta = self._videos.get(video_id, {})
            filename = meta.get("filename", f"{video_id}.mp4")
            total_size = meta.get("size", 0)

            url = f"{self._server_url}/rooms/{self._room_code}/videos/{video_id}"
            local_path = str(self._download_dir / f"{video_id}_{filename}")

            resp = requests.get(url, stream=True, timeout=600)
            if resp.status_code not in (200, 206):
                self.signals.room_error.emit(f"Download failed: {resp.status_code}")
                return

            received = 0
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=262144):  # 256KB
                    f.write(chunk)
                    received += len(chunk)
                    self.signals.download_progress.emit(received, total_size)

            # Store local path
            if video_id in self._videos:
                self._videos[video_id]["local_path"] = local_path
            else:
                self._videos[video_id] = {"filename": filename, "local_path": local_path}

            self.signals.video_ready.emit(video_id, local_path)

        except Exception as e:
            log.error(f"Download error: {e}")
            self.signals.room_error.emit(f"Download error: {e}")

    # ====================================================================
    # Cleanup
    # ====================================================================

    def cleanup(self):
        """Clean up temp files and disconnect."""
        self.stop_ping_loop()
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        self.disconnect()
        try:
            import shutil
            if self._download_dir.exists():
                shutil.rmtree(self._download_dir, ignore_errors=True)
        except Exception:
            pass
