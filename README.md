# Random Clip Player

A polished desktop application for playing random video clips from a selected folder. Perfect for rediscovering your old gaming moments, drone footage, or home videos.

## Features

- **🎲 Shuffle Queue:** True shuffle - see every clip once before reshuffling
- **▶️ Autoplay:** Automatically play the next random clip when current ends
- **📂 Open in Explorer:** Quickly locate current clip in Windows Explorer (Ctrl+E)
- **👍 Like/Dislike:** Mark favorites and block clips you don't want to see
- **📁 Folder Management:** Select any folder containing video files
- **⏯ Playback Controls:** Play/Pause, Skip 10s, Previous Clip
- **🐢 Slow Motion:** Toggle 0.5x speed for analyzing plays
- **🔊 Volume Memory:** Remembers your volume settings between sessions
- **⌨ Keyboard Shortcuts:** Full keyboard control
- **🎨 Modern Dark UI:** Clean, GitHub-inspired dark theme

## Supported Formats
Supports most common video formats including:
`.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.mpeg`, `.mpg`

## Installation

1. Download the latest `RandomClipPlayer.exe` from the [Releases](https://github.com/Ukunda/RDM/releases) page.
2. Run the executable.
3. Select your clips folder when prompted.
4. Enjoy!

## Requirements

- **VLC Media Player:** Must be installed on your system (the player uses the VLC engine).
  - Download: [videolan.org](https://www.videolan.org/vlc/)

## Keyboard Shortcuts

| Key | Action |
|:-:|---|
| **Space** | Play Random Clip |
| **P** | Play / Pause |
| **A** | Toggle Autoplay |
| **S** | Toggle Slow Motion |
| **L** | Like Current Clip |
| **Del** | Dislike & Block Clip |
| **Ctrl+E** | Open in Explorer |
| **← / →** | Skip Back / Forward 10s |
| **Backspace** | Previous Clip |
| **M** | Mute |
| **↑ / ↓** | Volume Up / Down |
| **Esc** | Stop |

## Building from Source

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the valid build command (or use the build script):
   ```bash
   pyinstaller --clean --onefile --windowed --name "RandomClipPlayer" --icon=NONE random_clip_player.py
   ```

## License
MIT
