═══════════════════════════════════════════════
  COMPLETED
═══════════════════════════════════════════════

✅ Add options to change keybinds via menu 
✅ Frame by frame skip via . and , button (changeable via keybind)
✅ Toggle option for the "button bar" to auto-hide when cursor leaves 
✅ Toggle in the dropdown menu to "show only favorites" 
✅ Settings menu next to the file menu 
✅ When scrolling over the slomo button change slow amount. If pressed it defaults to 0.5 
✅ Drag buttons around to rearrange them (Alt+drag). Size stays the same 
✅ PySide6 migration (was PyQt5) 
✅ MPV integration (replaced VLC) 
✅ Big update: "Watch Together" — session rooms, room codes, password protection,
   playback sync (play/pause/seek/speed), clip upload & streaming, shared random pool,
   ready-sync protocol, host-only autoplay, auto-reconnect, sync-on-join, ping display,
   host kick, activity feed, connection status dot, debug mode (--debug). Server via Docker.

═══════════════════════════════════════════════
  BUGS — HIGH PRIORITY
═══════════════════════════════════════════════

🐛 Slider seeking is broken — video glitches and jumps aggressively back and forth 
   when dragging the time slider. Hard to pinpoint exact moments. Likely caused by 
   MPV property observers fighting with slider updates during seek. Need to suppress 
   time-pos observer while slider is held and debounce seek commands.

🐛 Two people pressing "Random Clip" at the same time breaks the whole session.
   Behaviour varies depending on whether shared clip pool is on or off. The ready-sync 
   state machine can't handle overlapping prepare_video flows — second request either 
   gets lost or corrupts the first. Needs a queuing/locking mechanism on the server 
   and client to serialize clip transitions.

🐛 Shared clip pool is buggy and needs a full rework. Current issues:
   - Random user selection doesn't account for users with 0 clips
   - No feedback when the selected user fails to provide a clip
   - Race conditions when pool toggle and random request happen simultaneously
   - No timeout/fallback if the chosen user disconnects mid-share

🐛 Permanent uncertainty whether guests see the same thing as host during a session.
   No periodic sync verification exists — once a desync happens (network hiccup, 
   different decode speed, seek rounding) there is no way to detect or correct it.
   Need: periodic position heartbeat from host, drift detection + correction on guests.

🐛 System gets very slow with larger clips in session mode. Upload/download blocks 
   the session and there's no progress gating — large files choke the server and 
   stall the ready-sync. Need chunked streaming, server-side size warnings, and 
   possibly a file size limit UI.

═══════════════════════════════════════════════
  FEATURES — NEXT SESSION
═══════════════════════════════════════════════

🔲 Auto-updater connected to GitHub Releases
   - On startup (or on a timer), check GitHub API for latest release tag
   - If newer than current version, show a popup with three buttons:
     "Update now"  /  "Later"  /  "Nah I'm good"
   - "Update now" → download the new .exe, replace self, restart
   - "Later" → remind again next launch
   - "Nah I'm good" → don't ask again for this version
   - Store skipped version + "later" state in config.json

🔲 Phase 3 from implementation plan: Formal State Machine for Watch Together
   - Define SessionState enum: DISCONNECTED, CONNECTING, LOBBY, UPLOADING, 
     DOWNLOADING, WAITING_READY, PLAYING, ERROR
   - Replace scattered boolean flags (_ignore_remote, _session_uploading, 
     _playing_remote_clip, _pending_sync_video_id, _pending_prepare_video_id)
   - Central state handler that rejects impossible transitions
   - This will fix most of the session race condition bugs above

🔲 Add scaletempo2 audio filter to MPV init for pitch-correct speed changes
   (last missing piece from Phase 2)

🔲 Fullscreen toggle (F11 or double-click video area)

═══════════════════════════════════════════════
  IMPROVEMENTS — LOWER PRIORITY
═══════════════════════════════════════════════

🔲 Phase 4 (optional): Migrate threading.Thread to QThread/QRunnable in session_client
🔲 Split random_clip_player.py (~3200 lines) into modules: config, widgets, session_panel, player
🔲 Server: session token/JWT so WebSocket auth can't be spoofed with a guessed user_id
🔲 Server: room count limit to prevent memory exhaustion
🔲 Optimise folder scan — use targeted globs (*.mp4, *.mkv …) instead of rglob("*")
🔲 Replace blocking QMessageBox.question in block_current_clip with non-blocking dialog
