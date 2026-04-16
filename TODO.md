Legende:
  🟢 Einfach   — Hauptsächlich UI-Arbeit, wenig Risiko, kein Protokoll-Umbau
  🟡 Mittel    — Erfordert Client+Server-Änderungen, moderate Komplexität
  🔴 Komplex   — Tiefgreifende Architektur-Änderung, hohes Regressionsrisiko

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
✅ Fullscreen toggle (F11 or double-click video area)
✅ scaletempo2 audio filter for pitch-correct speed changes

═══════════════════════════════════════════════
  BUGS — FIXED
═══════════════════════════════════════════════

✅ Slider seeking fixed — time-pos observer now suppressed while slider is held,
   seek only fires on release. ClickableSlider properly emits pressed/released.

✅ Multiskip-Bug fixed — server-side transition lock rejects play_video when a
   pending_video transition is already in progress. Client shows "busy" feedback.

✅ Autoplay/Random bug fixed — explicit player.pause = False after play() to
   prevent stale pause state from keep_open=True. Session load/ready-sync fixed.

═══════════════════════════════════════════════
  BUGS — HIGH PRIORITY
═══════════════════════════════════════════════

🐛🟡 Shared clip pool is buggy and needs a full rework. Current issues:
   - Random user selection doesn't account for users with 0 clips
   - No feedback when the selected user fails to provide a clip
   - Race conditions when pool toggle and random request happen simultaneously
   - No timeout/fallback if the chosen user disconnects mid-share
   - Clips wiederholen sich wenn ein User weniger hat als andere: Bei z.B.
     100 Clips (User A) und 50 Clips (User B) fängt User B nach 50 wieder
     von vorne an, statt dass das System alle 150 einmalig abspielt.
     Lösung: Server/Client trackt bereits gespielte Clips pro User. User
     dessen Pool erschöpft ist wird bei der Random-Auswahl übersprungen bis
     alle User durch sind. Erst dann Reset aller Pools.

🐛🟡 Permanent uncertainty whether guests see the same thing as host during a session.
   No periodic sync verification exists — once a desync happens (network hiccup, 
   different decode speed, seek rounding) there is no way to detect or correct it.
   Need: periodic position heartbeat from host, drift detection + correction on guests.

🐛 Upload/Download-Geschwindigkeit & Transparenz bei großen Clips
   Symptom: Große Videos (+500 MB) blockieren die Session. Upload/download
   blocks the session and there's no progress gating — large files choke the
   server and stall the ready-sync. User denken das Programm ist abgestürzt,
   weil keine sichtbare Aktivität stattfindet.
   Umsetzung (gestuft):
   Stufe 1 — UX-Sofortmaßnahmen (🟢 einfach):
   - Prominenter Fortschrittsbalken im Video-Bereich (Overlay) statt nur im
     Session-Panel. Zeigt: "Lade Video… 234 MB / 512 MB (45%) — 2.1 MB/s"
   - Geschätzte Restzeit (ETA) anzeigen
   - Pulsierender Rahmen oder Spinner im Video-Frame während Download
   Stufe 2 — Transfer-Optimierung (🔴 komplex):
   - Chunked Upload mit konfigurierbarer Chunk-Größe (aktuell: einzelner POST)
   - Parallele Chunk-Downloads (2-3 gleichzeitige Connections)
   - Server: Streaming-Response statt komplettes File im RAM halten
   - Kompression für Signaling-Daten (nicht für Video-Daten)
   - Konfigurierbare Dateigrößen-Warnung (z.B. >500 MB → Bestätigungsdialog)
   Stufe 3 — Architektur (🔴 komplex, langfristig):
   - Peer-to-Peer Transfer-Option (WebRTC DataChannel) für LAN-Sessions
   - Server als Relay nur für WAN-Sessions

═══════════════════════════════════════════════
  FEATURES — SESSION
═══════════════════════════════════════════════

🔲🔴 Phase 3: Formal State Machine for Watch Together
   - Define SessionState enum: DISCONNECTED, CONNECTING, LOBBY, UPLOADING, 
     DOWNLOADING, WAITING_READY, PLAYING, ERROR
   - Replace scattered boolean flags (_ignore_remote, _session_uploading, 
     _playing_remote_clip, _pending_sync_video_id, _pending_prepare_video_id)
   - Central state handler that rejects impossible transitions
   - This will fix most of the session race condition bugs above

🔲🟡 Individueller Pool-Opt-In/Out pro User
   Beschreibung: Jeder User in der Session soll per Toggle entscheiden können,
   ob die eigenen Clips im Shared Random Pool verfügbar sind oder nicht.
   Der Toggle muss jederzeit während der Session umschaltbar sein.
   Aktueller Stand: Nur der Host kann den gesamten Shared Pool global
   an-/ausschalten. Es gibt keine Per-User-Granularität.
   Umsetzung:
   - Server: Pro User ein Flag pool_opted_in (default: True) im Room-State
   - Server: Bei random-User-Auswahl nur User mit pool_opted_in=True berücksichtigen
   - Client: Checkbox im Session-Panel: "🎲 Meine Clips im Pool"
   - WebSocket-Event: "pool_opt_in" {user_id, opted_in} → Server broadcastet Update
   - UI: Userliste zeigt Icon (🎲/—) neben Usernamen für Pool-Status

🔲🔴 Video-Queue mit Prefetch-Buffering
   Beschreibung: Im Session-Panel soll eine sichtbare Video-Queue angezeigt
   werden. Das System soll bereits die nächsten 1-2 Videos im Hintergrund
   herunterladen, damit der Übergang zwischen Clips nahtlos ist.
   Disconnect-Button wird unter die Queue verschoben.
   Aktueller Stand: Kein Queue-System. Jedes Video wird erst bei Bedarf
   geladen. Zwischen Clips gibt es eine spürbare Wartezeit.
   Umsetzung:
   - Server: Neues Konzept "queue" pro Room — geordnete Liste von video_ids
   - Server: Endpoint zum Queue-Management (add, remove, reorder, peek_next)
   - Client: Queue-Widget im Session-Panel (scrollbare Liste, drag-to-reorder)
   - Client: Background-Download-Thread für nächstes Video in der Queue
   - Client: Prefetch-Cache (max 2 Videos vorgeladen, älteste verwerfen)
   - Ready-Sync anpassen: Prefetch-Videos überspringen Ready-Download-Phase
   Abhängigkeit: Profitiert von Phase 3 State Machine für saubere Transitions.

🔲🟢 Startup-Dialog: "Zuschauen" vs. "Clips teilen"
   Beschreibung: Beim Programmstart erscheint ein moderner Dialog mit zwei
   Optionen: (A) "Ich möchte nur zuschauen" → Überspringt Ordnerauswahl,
   öffnet direkt den Session-Beitritts-Dialog. (B) "Ich habe eigene Clips" →
   Normaler Flow mit Ordnerauswahl.
   Umsetzung:
   - Neuer QDialog mit zwei großen Karten-Buttons (Icons + Beschreibung)
   - Option A: Setzt internen Flag viewer_only=True, überspringt scan_folder(),
     öffnet Session-Panel mit Join-Dialog
   - Option B: Normaler Programmstart mit QFileDialog
   - "Nicht erneut fragen"-Checkbox → Speichert Auswahl in config.json
   - Einstellung zum Zurücksetzen unter Settings

═══════════════════════════════════════════════
  FEATURES — LOKAL / PLAYER
═══════════════════════════════════════════════

🔲🟡 Auto-updater connected to GitHub Releases
   - On startup (or on a timer), check GitHub API for latest release tag
   - If newer than current version, show a popup with three buttons:
     "Update now"  /  "Later"  /  "Nah I'm good"
   - "Update now" → download the new .exe, replace self, restart
   - "Later" → remind again next launch
   - "Nah I'm good" → don't ask again for this version
   - Store skipped version + "later" state in config.json

🔲 Dislike-Button: Reaktivierung im Session-Modus + Dual-Funktion
   Beschreibung: Der Dislike-Button (👎) soll im Session-Modus wieder aktiv
   sein, aber ausgegraut wenn gerade ein externer Clip läuft (da man fremde
   Clips nicht löschen/blocken kann). Zusätzlich bekommt der Button zwei Modi:
   (1) Blacklisting (wie bisher) — Clip wird aus Rotation entfernt
   (2) Direkte Löschung — Clip wird in den Papierkorb verschoben
   Bei Entfernung des Dislikes wird der Clip wiederhergestellt.
   Umsetzung:
   - Settings: Neue Option "Dislike-Aktion" → Dropdown: "Blacklist" / "In Papierkorb"
   - Blacklist-Modus: Wie bisher (config blocked_clips)
   - Papierkorb-Modus: send2trash-Bibliothek nutzen, Original-Pfad in config
     speichern (restore_map: {clip_name: original_path})
   - Undo: Bei Dislike-Entfernung → Datei aus Papierkorb zurück an original_path
     ⚠ Achtung: Papierkorb-Restore ist OS-abhängig und nicht immer zuverlässig.
     Alternative: Eigener "Trash"-Ordner innerhalb des Clip-Verzeichnisses.
   - Session-Modus: Button enabled wenn _playing_remote_clip == False,
     disabled (grayed out) wenn externer Clip läuft
   - Neue Dependency: send2trash (pip install send2trash)

🔲🟢 Advanced Info Toggle für Activity-Feed & Status-Overhaul
   Beschreibung: In den Einstellungen eine Option "Erweiterte Infos anzeigen",
   die in der Activity-Leiste zusätzliche technische Details einblendet
   (z.B. Dateigröße, Upload/Download-Speed, Codec, Auflösung).
   Genereller Status-Overhaul: Klarere Rückmeldung was das Programm gerade tut.
   Umsetzung:
   - Settings: Checkbox "Erweiterte Infos in Activity-Feed"
   - Erweiterte Einträge: Dateigröße bei Share, Transfer-Speed, Video-Metadaten
   - Status-Label Overhaul: Animierter "Lade…"-Indikator statt stiller Phasen
   - Persistenter Status-Text während Operationen (nicht nur 2-3 Sek.)
   - Optional: Mini-Fortschrittsbalken in der Statusleiste

═══════════════════════════════════════════════
  IMPROVEMENTS — LOWER PRIORITY
═══════════════════════════════════════════════

🔲 Phase 4 (optional): Migrate threading.Thread to QThread/QRunnable in session_client
🔲 Split random_clip_player.py (~3200 lines) into modules: config, widgets, session_panel, player
🔲 Server: session token/JWT so WebSocket auth can't be spoofed with a guessed user_id
🔲 Server: room count limit to prevent memory exhaustion
🔲 Optimise folder scan — use targeted globs (*.mp4, *.mkv …) instead of rglob("*")
🔲 Replace blocking QMessageBox.question in block_current_clip with non-blocking dialog

═══════════════════════════════════════════════
  EMPFOHLENE REIHENFOLGE
═══════════════════════════════════════════════

  ✅ Autoplay-Bug fixen
  ✅ Slider-Seeking fixen
  ✅ Multiskip-Bug / Server-Lock
  ✅ scaletempo2 Audio-Filter
  ✅ Fullscreen Toggle

  1. 🔲 Startup-Dialog                  (🟢 schnell umsetzbar, guter UX-Gewinn)
  2. 🔲 Advanced Info & Status-Overhaul  (🟢 reduziert User-Verwirrung)
  3. 🔲 UX-Sofortmaßnahmen Downloads    (🟢 Fortschrittsbalken-Overlay)
  4. 🔲 Pool Opt-In/Out pro User        (🟡 mittlerer Aufwand)
  5. 🔲 Dislike Dual-Funktion           (🟡 mittlerer Aufwand)
  6. 🔲 Auto-Updater                    (🟡 eigenständiges Feature)
  7. 🐛 Shared Pool Rework              (🟡 nach Pool Opt-In, baut darauf auf)
  8. 🐛 Desync-Erkennung / Heartbeat    (🟡 nach State Machine)
  9. 🔲 Phase 3: State Machine          (🔴 Kernrefactoring, enabler für vieles)
  10. 🔲 Video-Queue + Prefetch          (🔴 großes Feature, nach State Machine)
  11. 🔲 Transfer-Optimierung Stufe 2+3  (🔴 nach Queue-System)
