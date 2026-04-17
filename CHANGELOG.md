# Changelog

## [4.6.0] - 2026-04-16

### Added
- **Desync-Heartbeat:** RTT-compensated position sync every 5s corrects drift between host and guests.
- **Shared Pool Robustness:** Clip-count tracking, 10s timeout with 3-retry fallback, pool exhaustion detection, and `uploaded_by` fix for remote clip flag.
- **Session State Consolidation:** Replaced scattered boolean flags with `SessionPhase` enum and `PrefetchState` enum for clearer workflow tracking.
- **Resumable Chunked Uploads:** 5 MB chunked upload with resume support via `GET /status`. Old single-POST upload preserved for backward compatibility.
- **Auto-Updater:** GitHub release check on startup with download + in-place EXE swap (Windows). Supports "Skip this version" and "Later" options.
- **Prefetch Next Video:** Background pre-upload + pre-download of the next clip so transitions are near-instant via cache hits.

### Fixed
- **Server:** Path traversal in upload filenames, WS auth bypass, broadcast dict-view crash, range suffix-byte-range parsing, chunk retransmit false-413, ready-sync re-evaluation on disconnect, zero-byte upload rejection, error message sanitization.
- **Client:** Kicked user auto-reconnect loop, download directory not recreated after cleanup, path traversal in downloads, concurrent download deduplication, reconnect race condition, JSON parse safety.
- **Player:** `_on_video_ready` fallback pausing forever, `closeEvent` not disconnecting session, `_skip` not syncing in session mode, stale `_operation_status`, prefetch phase gating, `_host_wait_for_ready` transition, `_on_all_ready` video_id validation.
- **Types:** Resolved all Pyright type-checker errors (Optional narrowing, parentWidget null, MPV property isinstance guards).

### Removed
- One-time migration scripts (`migrate_pyside6.py`, `migrate_vlc.py`).
- Stale documentation (`implementation_plan.md`, `mpv_dll_usage.md`).
- Duplicate TODO file (`todo2.md`, merged into `TODO.md`).

## [4.5.0] - 2026-02-20

### Fixed
- **Server:** Fixed a critical bug where deleting expired rooms blocked the FastAPI event loop, causing the server to freeze for all users. Room deletion is now handled asynchronously.
- **Server:** Fixed a memory leak in the rate limiting system where old IP addresses were never pruned from the `join_attempts` dictionary.
- **Server:** Fixed an issue where partial video uploads from dropped connections were left on disk until room expiration. Incomplete files are now immediately deleted.
- **Client:** Fixed a resource leak where temporary downloaded video files were never deleted, eventually exhausting the user's `%TEMP%` drive. The client now cleans up its temporary directory on disconnect and application exit.
- **Client:** Optimized configuration saving to prevent excessive disk I/O when rapidly changing settings (e.g., dragging the volume slider). Settings are now debounced with a 300ms timer.

### Improved
- **Code Quality:** Resolved all Pylance/type-checker errors across the codebase.
  - Added null-safety guards for Optional returns (`menuBar()`, `centralWidget()`, `clipboard()`, VLC instance).
  - Migrated core playback engine from `python-vlc` to `python-mpv` (`libmpv`) for better performance and stability without a system-wide installation requirement.
  - Fixed `SessionClient` possibly-unbound errors from conditional import.
  - Fixed argument type mismatches (`config.get()` returning Optional passed to typed parameters).
  - Fixed `DraggableButtonBar.layout` shadowing `QWidget.layout()` (renamed to `_layout`).
  - Added `pyrightconfig.json` for PyQt5 stub false-positive suppression.
