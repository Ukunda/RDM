# RDM Watch Together — Server

A lightweight signaling + video relay server for the Random Clip Player "Watch Together" feature.

## Quick Start (Docker)

```bash
# 1. Copy and edit the environment config
cp .env.example .env

# 2. Build and run
docker compose up -d

# 3. Check it's running
curl http://localhost:8765/health
```

## Quick Start (Without Docker)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Set environment variables or use defaults
export RDM_PORT=8765
export RDM_MAX_FILE_SIZE_MB=500

# 3. Run
python server.py
```

## Configuration

All settings are via environment variables (or `.env` file for Docker):

| Variable | Default | Description |
|---|---|---|
| `RDM_HOST` | `0.0.0.0` | Bind address |
| `RDM_PORT` | `8765` | Server port |
| `RDM_UPLOAD_DIR` | `./uploads` | Temp video storage directory |
| `RDM_MAX_FILE_SIZE_MB` | `500` | Max upload size per file (MB) |
| `RDM_ROOM_EXPIRY_SECONDS` | `14400` | Room auto-delete after inactivity (seconds, default 4h) |

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/rooms` | POST | Create a room |
| `/rooms/{code}/join` | POST | Join a room |
| `/rooms/{code}/upload` | POST | Upload a video clip |
| `/rooms/{code}/videos/{id}` | GET | Stream/download a video (supports range requests) |
| `/ws/{code}` | WS | WebSocket for real-time sync |

## Security

- Room passwords are **bcrypt-hashed** server-side
- **Rate limiting**: 5 join attempts per IP per 60 seconds
- Rooms **auto-expire** after the configured inactivity period
- Uploaded files are **cleaned up** when rooms expire

## Architecture

```
Client A                    Server                    Client B
   │                          │                          │
   ├── POST /rooms ──────────►│                          │
   │◄── room_code ────────────┤                          │
   │                          │◄── POST /rooms/join ─────┤
   │                          ├── user_id ──────────────►│
   │── WS /ws/{code} ───────►│◄── WS /ws/{code} ────────┤
   │        (auth)            │        (auth)            │
   │                          │                          │
   │── POST /upload ─────────►│                          │
   │                          ├── video_uploaded ───────►│
   │── play_video ───────────►│                          │
   │                          ├── prepare_video ────────►│
   │                          │◄── GET /videos/{id} ─────┤
   │                          ├── (chunked stream) ─────►│
   │                          │◄── ready ────────────────┤
   │◄── ready_progress ───────┤── ready_progress ───────►│
   │◄── all_ready ────────────┤── all_ready ────────────►│
   │       ▶ play             │         ▶ play           │
   │                          │                          │
   │── play/pause/seek ──────►│                          │
   │                          ├── play/pause/seek ──────►│
```
