# Upgrading Random Clip Player: Tech Stack & State Machine

This plan focuses on high-value technology upgrades (PySide6, MPV) and resolving fragile state management in the Watch Together client. We will execute these changes incrementally in separate branches to isolate risk.

## User Review Required

> [!NOTE]
> Thank you for the detailed review! I've updated the plan to match your recommended execution order, dropped the low-value high-complexity items (Nuitka, metadata caching), and added concrete strategies for the MPV DLL and Qt embedding gotchas. Let me know if you approve this final version to start the PySide6 migration!

## Execution Strategy

Each phase will be executed, verified, and committed independently on its own branch. 

### Phase 1: PySide6 Migration
*Status: Mechanical, low risk, high value (fixes type stubs, better licensing).*
- **[MODIFY] [random_clip_player.py](file:///c:/Hobby/RDM/random_clip_player.py), [session_client.py](file:///c:/Hobby/RDM/session_client.py):**
  - Update imports: `PyQt5` -> `PySide6`.
  - Update Enums: Fix namespace changes (e.g., `Qt.LeftButton` -> `Qt.MouseButton.LeftButton`, `Qt.Key_Space` -> `Qt.Key.Key_Space`).
  - Update Signals/Slots: `pyqtSignal` -> [Signal](file:///c:/Hobby/RDM/session_client.py#31-77) (must remain at class level), `pyqtSlot` -> `Slot`.
  - Application Execution: Change `app.exec_()` to `app.exec()`.
- **[MODIFY] [requirements.txt](file:///c:/Hobby/RDM/requirements.txt) / Build:** Replace `PyQt5` with `PySide6`. Verify PyInstaller builds correctly.

### Phase 2: MPV Integration
*Status: High risk, high reward. Requires replacing the entire playback layer.*
- **Step 1: MPV DLL Strategy**
  - Download a prebuilt `mpv-1.dll` (e.g., from shinchiro builds) and place it in a `lib/` directory in the repository.
  - Update [build.bat](file:///c:/Hobby/RDM/build.bat) and [RandomClipPlayer.spec](file:///c:/Hobby/RDM/RandomClipPlayer.spec) to explicitly bundle `lib/mpv-1.dll` via `--add-data`.
- **Step 2: Engine Replacement ([random_clip_player.py](file:///c:/Hobby/RDM/random_clip_player.py))**
  - Remove [setup_vlc()](file:///c:/Hobby/RDM/random_clip_player.py#36-89) and `python-vlc` dependency.
  - Add `python-mpv` to [requirements.txt](file:///c:/Hobby/RDM/requirements.txt).
  - Initialize the engine: `mpv.MPV(wid=int(self.video_frame.winId()), vo='gpu', hwdec='auto')`.
- **Step 3: Playback API Mapping & Threading**
  - Rewrite core logic ([_play_video](file:///c:/Hobby/RDM/random_clip_player.py#2586-2617), [_toggle_play_pause](file:///c:/Hobby/RDM/random_clip_player.py#2618-2640), [_stop](file:///c:/Hobby/RDM/random_clip_player.py#2667-2676), frame stepping).
  - Update speed control: Set `--af=scaletempo2` for seamless pitch correction when adjusting speed.
  - **Threading Constraint:** MPV runs its event loop on a separate thread. `mpv.observe_property` callbacks (e.g., for time updates or window resizes) *must not* directly call Qt GUI methods. Callbacks must emit custom Qt [Signal](file:///c:/Hobby/RDM/session_client.py#31-77)s to route data safely back to the main GUI thread.
- **Fallback Strategy (QMediaPlayer):**
  - If `python-mpv` integration proves unviable on Windows due to OpenGL/compositor conflicts or packaging issues, we will pivot to Qt6's native `QMediaPlayer` (`PySide6.QtMultimedia`) as the official fallback engine. It provides the same core benefits (FFmpeg-backed, no external VLC installation required) with zero embedding friction.

### Phase 3: Formal State Machine
*Status: Medium effort, significantly improves robustness of Watch Together.*
- **[NEW/MODIFY] [session_client.py](file:///c:/Hobby/RDM/session_client.py) / `SessionPanel`:**
  - Define an explicit `enum.Enum` (e.g., `SessionState`: `DISCONNECTED`, `CONNECTING`, `LOBBY`, `DOWNLOADING_SYNC`, `WAITING_FOR_HOST`, `PLAYING`).
  - Replace the scattered boolean flags (`_ignore_remote`, `_session_uploading`, `_playing_remote_clip`, `_pending_sync_video_id`).
  - Route all websocket events and UI actions through a central state handler to prevent impossible state combinations (e.g., trying to play while downloading).

### Phase 4: QThread Migration (Optional Polish)
*Status: Low priority.*
- **[MODIFY] [session_client.py](file:///c:/Hobby/RDM/session_client.py):**
  - If time permits, migrate the native `threading.Thread` usage ([_upload_thread](file:///c:/Hobby/RDM/session_client.py#648-715), [_download_thread](file:///c:/Hobby/RDM/session_client.py#716-755)) to PySide6 `QThread` or `QRunnable` for idiom consistency.

---
*(Items dropped from previous plans: Nuitka, Metadata Caching, HLS Transcoding, Server Persistence)*
