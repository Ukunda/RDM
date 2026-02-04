# Random Clip Player

Desktop app for playing random video clips from a folder. Good for rewatching old gameplay recordings, drone footage, whatever you've got sitting around.

## Features

**Playback**
- True shuffle - plays every clip once before reshuffling
- Autoplay next clip when current one ends
- Variable speed (0.25x to 2.0x) - scroll on the speed button
- Frame-by-frame stepping (. and , keys) - adapts to video FPS
- Skip forward/back 10s, go to previous clip

**Clip Management**
- Like clips to mark favorites, dislike to block them from showing up
- Favorites-only mode to just play the good stuff
- Open current clip in Explorer

**Customization**
- Rebind any keyboard shortcut (Ctrl+, to open settings)
- Auto-hide the control bar
- Rearrange buttons by Alt+dragging them
- Volume and preferences persist between sessions

**Other**
- Dark theme
- Works on 4K displays

## Supported Formats

`.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.mpeg`, `.mpg`, `.ts`, `.mts`, `.3gp`

## Installation

1. Grab `RandomClipPlayer.exe` from [Releases](https://github.com/Ukunda/RDM/releases)
2. Run it
3. Pick your clips folder
4. Done

**Requires VLC** - download from [videolan.org](https://www.videolan.org/vlc/) if you don't have it

## Keyboard Shortcuts

Customizable in Settings (Ctrl+,)

| Key | Action |
|:-:|---|
| Space | Random clip |
| P | Play/Pause |
| A | Toggle autoplay |
| S | Toggle slow-mo |
| L | Like clip |
| Del | Block clip |
| ← / → | Skip 10s |
| . / , | Frame step |
| Backspace | Previous clip |
| R | Reshuffle |
| M | Mute |
| ↑ / ↓ | Volume |
| E | Open in Explorer |
| Esc | Stop |

## Building

```bash
pip install -r requirements.txt
pyinstaller --clean --onefile --windowed --name "RandomClipPlayer" random_clip_player.py
```

## Changelog

**v3.0**
- Settings dialog with customizable keybinds
- Frame-by-frame navigation that actually works with 60/120fps video
- Variable playback speed via scroll wheel
- Favorites-only mode
- Auto-hide controls
- Drag to rearrange buttons
- Fixed some memory leaks

**v2.0**
- Shuffle queue with history
- Like/dislike system
- Autoplay

**v1.0**
- Initial release

## License
MIT
