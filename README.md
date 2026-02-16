# Random Clip Player

A polished desktop application for playing random video clips from a selected folder. Perfect for rediscovering your old gaming moments, drone footage, or home videos — now with **Watch Together** to enjoy clips with friends.

## Features

### Core Playback
- **🎲 Shuffle Queue:** True shuffle — see every clip once before reshuffling
- **▶️ Autoplay:** Automatically play the next random clip when current ends
- **📁 Folder Management:** Select any folder containing video files
- **⏯ Playback Controls:** Play/Pause, Skip 10s, Previous Clip
- **🔊 Volume Memory:** Remembers your volume settings between sessions

### Clip Management
- **👍 Like/Dislike:** Mark favorites and block clips you don't want to see
- **⭐ Favorites Mode:** Filter to only play your liked clips
- **📂 Open in Explorer:** Quickly locate current clip in Windows Explorer

### Speed Control
- **🐢 Variable Speed:** Scroll on speed button to cycle 0.25x → 0.5x → 0.75x → 1.0x → 1.25x → 1.5x → 2.0x
- **🎞 Frame-by-Frame:** Step forward/backward one frame at a time (adapts to video FPS)

### Watch Together (v4.0)
- **👥 Session Rooms:** Create or join password-protected rooms with unique room codes
- **🎬 Synchronized Playback:** Play, pause, seek, and speed changes sync across all users in real-time
- **📤 Clip Sharing:** Upload and stream clips to everyone in the room (chunked HTTP transfer with progress)
- **🎲 Shared Random Pool:** Optionally let the server pick random clips from any connected user's library
- **🔄 Ready-Sync:** Everyone downloads the clip before playback starts — no desync
- **👑 Host-Only Autoplay:** Only the host triggers the next clip; guests wait in sync
- **📡 Auto-Reconnect:** Automatic reconnection with exponential backoff (up to 5 attempts)
- **🔄 Sync on Join:** Late joiners sync to the current clip position immediately
- **🏓 Ping Display:** Live latency indicator in the session panel
- **👢 Host Kick:** Room host can remove users from the session
- **📋 Activity Feed:** Live event log showing who joined, shared clips, synced, etc.
- **🟢 Connection Status:** Green/grey dot on the Session menu shows connection state
- **🐛 Debug Mode:** Launch with `--debug` for verbose logging and diagnostics

### Customization (v3.0)
- **⚙️ Settings Menu:** Preferences dialog for all settings (Ctrl+,)
- **⌨️ Custom Keybinds:** Reassign any keyboard shortcut with automatic conflict swapping
- **🎛 Auto-Hide Controls:** Optionally hide control bar when mouse is over video
- **🔀 Drag-to-Rearrange:** Alt+drag buttons to customize control bar layout

### Visual
- **🎨 Modern Dark UI:** Clean, GitHub-inspired dark theme
- **📺 High-DPI Support:** Crisp UI on 4K displays

## Supported Formats
Supports most common video formats including:
`.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.mpeg`, `.mpg`, `.ts`, `.mts`, `.3gp`

## Installation

1. Download the latest `RandomClipPlayer.exe` from the [Releases](https://github.com/Ukunda/RDM/releases) page.
2. Run the executable.
3. Select your clips folder when prompted.
4. Enjoy!

## Requirements

- **VLC Media Player:** Must be installed on your system (the player uses the VLC engine).
  - Download: [videolan.org](https://www.videolan.org/vlc/)

## Watch Together — Self-Hosted Server

The Watch Together feature requires a server. See [server/README.md](server/README.md) for full setup instructions.

**Quick start with Docker:**
```bash
cd server
cp .env.example .env   # edit password/settings
docker compose up -d
```

The server runs on port **8765** by default and handles room management, WebSocket signaling, and chunked video relay.

## Keyboard Shortcuts

All shortcuts can be customized in Settings → Preferences (Ctrl+,)

| Key | Action |
|:-:|---|
| **Space** | Play Random Clip |
| **P** | Play / Pause |
| **A** | Toggle Autoplay |
| **S** | Toggle Slow Motion (0.5x) |
| **L** | Like Current Clip |
| **Del** | Dislike & Block Clip |
| **← / →** | Skip Back / Forward 10s |
| **. / ,** | Frame Forward / Backward |
| **Backspace** | Previous Clip |
| **R** | Reshuffle Queue |
| **M** | Mute |
| **↑ / ↓** | Volume Up / Down |
| **E** | Open in Explorer |
| **Esc** | Stop |
| **Ctrl+,** | Open Preferences |
| **Ctrl+O** | Open Folder |
| **Ctrl+Q** | Quit |

## Building from Source

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the build:
   ```bash
   pyinstaller --clean --onefile --windowed --name "RandomClipPlayer" random_clip_player.py
   ```
4. Debug mode (optional):
   ```bash
   RandomClipPlayer.exe --debug
   ```

## Changelog

### v4.0 - Watch Together
- 👥 Watch Together sessions — create/join rooms with password protection
- 🎬 Full playback sync (play, pause, seek, speed) over WebSocket
- 📤 Clip upload & streaming with progress (chunked HTTP)
- 🎲 Shared random pool — server picks clips from any user's library
- 🔄 Ready-sync protocol — everyone downloads before playback starts
- 👑 Host-only autoplay — no ping-pong desync between users
- 📡 Auto-reconnect with exponential backoff (5 attempts)
- 🔄 Sync-on-join for late joiners
- 🏓 Live ping/latency display
- 👢 Host kick functionality
- 📋 Activity feed with live session events
- 🟢 Connection status indicator (green/grey dot)
- 🐛 `--debug` CLI flag for verbose logging and diagnostics
- 🛡 Server: bcrypt password hashing, rate limiting, room auto-expiry
- 🐳 Docker deployment support for the server

### v3.0 - Settings & Customization
- ⚙️ New Settings menu with Preferences dialog
- ⌨️ Fully customizable keyboard shortcuts with swap-on-conflict
- 🎞️ Frame-by-frame navigation (. / ,) — adapts to video FPS (30/60/120fps)
- 🚀 Variable playback speed (scroll on speed button: 0.25x – 2.0x)
- ⭐ Show Only Favorites mode in File menu
- 🎛️ Auto-hide controls option
- 🔀 Drag-to-rearrange button bar (Alt+drag)
- 🔧 Performance optimizations (FPS caching, proper cleanup)

### v2.0 - Enhanced Playback
- True shuffle queue with previous clip navigation
- Like/Dislike system with persistence
- Autoplay mode
- Improved UI and stability

### v1.0 - Initial Release
- Basic random clip playback
- Volume control
- Folder selection

## License
MIT
