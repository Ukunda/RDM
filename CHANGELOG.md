# Changelog

## [4.5.0] - 2026-02-20

### Fixed
- **Server:** Fixed a critical bug where deleting expired rooms blocked the FastAPI event loop, causing the server to freeze for all users. Room deletion is now handled asynchronously.
- **Server:** Fixed a memory leak in the rate limiting system where old IP addresses were never pruned from the `join_attempts` dictionary.
- **Server:** Fixed an issue where partial video uploads from dropped connections were left on disk until room expiration. Incomplete files are now immediately deleted.
- **Client:** Fixed a resource leak where temporary downloaded video files were never deleted, eventually exhausting the user's `%TEMP%` drive. The client now cleans up its temporary directory on disconnect and application exit.
- **Client:** Optimized configuration saving to prevent excessive disk I/O when rapidly changing settings (e.g., dragging the volume slider). Settings are now debounced.
