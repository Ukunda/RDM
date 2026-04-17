═══════════════════════════════════════════════
  COMPLETED
═══════════════════════════════════════════════

✅ Keybinds, Frame-skip, Button-bar auto-hide, Favorites filter, Settings menu
✅ Slomo scroll, Drag-to-rearrange buttons, PySide6 migration, MPV integration
✅ Watch Together (rooms, sync, upload/stream, ready-sync, auto-reconnect, kick, etc.)
✅ Fullscreen toggle, scaletempo2 audio filter
✅ Slider seeking fix, Multiskip-Bug fix, Autoplay/Random bug fix
✅ Startup-Dialog, Advanced Info & Status-Overhaul, Transfer Overlay (Stufe 1)
✅ Pool Opt-In/Out pro User, Dislike Dual-Funktion (Blacklist + Trash)
✅ Desync-Heartbeat (RTT-kompensierte 5s Position-Sync)
✅ Shared Pool Robustheit (Clip-Count, Timeout/Retry, Exhaustion, Remote-Clip-Fix)
✅ Session State Consolidation (SessionPhase Enum, PrefetchState)
✅ Resumable Chunked Uploads (5MB Chunks, Resume via GET /status)
✅ Auto-Updater (GitHub Release Check, Download + In-Place Swap)
✅ Prefetch nächstes Video (Background Pre-Upload + Cache-Hit bei Play)

═══════════════════════════════════════════════
  OPEN — FEATURES
═══════════════════════════════════════════════

🔲🔴 Video-Queue mit sichtbarem Queue-Widget
   Im Session-Panel eine sichtbare Video-Queue anzeigen. Drag-to-reorder.
   Server: Queue pro Room (add, remove, reorder, peek_next).
   Client: Queue-Widget, Background-Download, Prefetch-Cache (max 2 Videos).
   Abhängigkeit: Profitiert von State Machine für saubere Transitions.

🔲🔴 Transfer-Optimierung (Stufe 2+3)
   Parallele Chunk-Downloads, Kompression für Signaling, konfigurierbare
   Dateigrößen-Warnung (>500 MB → Bestätigungsdialog).
   Langfristig: Peer-to-Peer Transfer-Option (WebRTC DataChannel) für LAN.

═══════════════════════════════════════════════
  OPEN — HOUSEKEEPING
═══════════════════════════════════════════════

🔲🟡 Modul-Split (random_clip_player.py → config, widgets, session_panel, player, main)
   Vorgeschlagene Aufteilung:
   - config.py: ConfigManager + COLORS + Defaults (~200 LOC)
   - widgets.py: StyledButton, ClickableSlider, ButtonBar, Dialoge, Overlay (~800 LOC)
   - session_panel.py: SessionPanel (~500 LOC)
   - player.py: VideoPlayer (~2000 LOC)
   - main.py: Entry-Point, Argument-Parsing, Logging (~50 LOC)
   Timing: Nach Feature-Freeze.

🔲🟢 Server: Room-Count-Limit (max 50 Rooms)
   Einzeiler in create_room. if len(rooms) >= MAX_ROOMS: return 503.

🔲🟡 Server: Auth-Token statt user_id
   Bei Join: Server generiert JWT/HMAC-Token, Client sendet Token bei WS-Auth.
   Verhindert user_id-Spoofing. Niedrige Priorität (Server läuft lokal/Docker).

🔲🟢 Folder-Scan: rglob("*") → gezielte Extension-Globs (*.mp4, *.mkv, etc.)
   Nur messbar bei Verzeichnissen mit vielen Nicht-Video-Dateien.
