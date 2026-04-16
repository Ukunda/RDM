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

═══════════════════════════════════════════════
  1 — DESYNC-HEARTBEAT  (🟢 ~60 LOC)
═══════════════════════════════════════════════

Problem: Nach all_ready gibt es keine Drift-Erkennung. Ein einziger
Netzwerk-Hickup oder Seek-Rundungsfehler → Host und Gäste dauerhaft out-of-sync.

Lösung:
  Client (Host):
  - QTimer alle 5s → _send_position_heartbeat()
  - Sendet nur wenn: player existiert, nicht paused, in Session, _ignore_remote False
  - WS: {"type": "position_heartbeat", "position": float, "speed": float}
  - Timer starten bei all_ready, stoppen bei pause/disconnect/stop

  Server:
  - "position_heartbeat" → broadcast an alle AUSSER Sender (wie play/pause/seek)
  - Kein serverseitiger State — reines Relay

  Client (Gast):
  - Signal position_heartbeat(float, float) auf SessionSignals
  - Handler _on_position_heartbeat(position, speed):
    - Eigene Position per self.player.time_pos lesen
    - drift = abs(eigene_pos - host_pos)
    - drift > 2.0s → _ignore_remote=True, player.seek(host_pos), _ignore_remote=False
    - drift > 5.0s → zusätzlich kurze Statusmeldung "🔄 Sync korrigiert"
    - drift < 0.5s → nichts tun (normaler Jitter)
    - Speed-Abgleich: wenn host_speed != player.speed → korrigieren

  Bekannte Einschränkung: Heartbeat kompensiert Drift, VERHINDERT ihn nicht.
  Ursache (decode-speed, netzwerk) bleibt. Akzeptabler Trade-off.

═══════════════════════════════════════════════
  2 — SHARED POOL: ROBUSTHEIT  (🟡)
═══════════════════════════════════════════════

Probleme (einzeln adressiert):

  (a) User mit 0 Clips wird gewählt → keine Antwort, Session hängt
  Fix:
  - pool_opt_in Message erweitern: {"opted_in": bool, "clip_count": int}
  - Server speichert clip_count in Room.pool_opted_in: {uid: {"opted_in": bool, "count": int}}
  - request_random filtert: opted_in=True AND count > 0
  - Client sendet clip_count = len(play_queue) beim Opt-In und bei jedem Rejoin

  (b) Gewählter User disconnected oder antwortet nicht
  Fix — Server-seitig:
  - request_random speichert pending_random_request = {target_uid, requested_at, requester_uid}
  - asyncio.create_task: 10s Timeout. Wenn kein play_video kommt:
    → Nächsten eligible User wählen (ausschließlich des gescheiterten)
    → Max 3 Versuche, dann Error-Message an Requester:
      {"type": "random_failed", "message": "Kein User konnte einen Clip liefern"}
  - play_video Handler: wenn pending_random_request vorhanden und sender==target → clear pending
  Fix — Client-seitig:
  - Nach send_request_random: Status "🎲 Warte auf Clip…" mit Spinner
  - Neues Signal random_failed(str) → Statusmeldung + erneuter Random-Button Enabled
  - Bestehender all_ready Handler räumt Status ohnehin auf

  (c) Clip-Wiederholung bei ungleichen Pool-Größen (100 vs 50 Clips)
  Fix — Client-seitig (gewichtete Auswahl):
  - _on_random_clip_requested: Wenn play_queue erschöpft → Status
    "🎲 Meine Clips aufgebraucht" senden (neues WS-Event: pool_exhausted)
  - Server: User mit pool_exhausted werden bei random-Auswahl übersprungen
  - Server: Wenn ALLE User exhausted → broadcast pool_reset → Clients resetten play_queue
  - Client: Bei pool_reset → play_queue reshufflen, queue_index = -1
  Vorteil: Tracking bleibt client-seitig (Server kennt keine Clip-Listen),
  nur ein Boolean "exhausted" wird synchronisiert.

  (d) _playing_remote_clip Bug
  Problem: _on_all_ready setzt _playing_remote_clip=True auch für den User
  der den Clip SELBST geteilt hat. Folge: Like/Dislike für eigenen Clip disabled.
  Fix: _on_all_ready prüft ob video_id in client._videos mit local_path existiert
  (= wir haben den Clip hochgeladen). Wenn ja → _playing_remote_clip=False.

═══════════════════════════════════════════════
  3 — SESSION STATE CONSOLIDATION  (🟡)
═══════════════════════════════════════════════

Problem: 6 Booleans in VideoPlayer + 3 State-Felder in SessionPanel. Kein
zentraler Überblick was die Session gerade tut. Bugs entstehen durch
widersprüchliche Flag-Kombinationen.

Ansatz: KEIN flaches Enum (die Dimensionen sind orthogonal). Stattdessen
drei getrennte, typisierte State-Felder in einem SessionState-Objekt:

  @dataclass
  class SessionState:
      connection: ConnectionState = DISCONNECTED  # DISCONNECTED | CONNECTING | CONNECTED
      transfer: TransferState = IDLE              # IDLE | UPLOADING | DOWNLOADING | PREFETCHING
      sync: SyncState = NONE                      # NONE | WAITING_READY | SYNCING | PLAYING

  Regeln (validated per Property-Setter):
  - transfer=UPLOADING nur wenn connection=CONNECTED
  - sync=WAITING_READY nur wenn connection=CONNECTED und transfer != UPLOADING
  - PREFETCHING kann parallel zu PLAYING laufen (das ist der Punkt)

  Ersetzt:
  - _session_uploading → state.transfer == UPLOADING
  - _playing_remote_clip → bleibt separat (ist kein State, sondern Clip-Metadata)
  - _session_shared_pool → bleibt separat (ist ein Setting, kein State)
  - _session_active → state.connection != DISCONNECTED
  - _pending_sync_video_id → state.sync == SYNCING + video_id Property
  - _pending_prepare_video_id → state.sync == WAITING_READY + video_id Property

  _ignore_remote bleibt unverändert — es ist ein synchroner Echo-Guard,
  kein State. Das zu erfassen wäre over-engineering.

  Implementierung:
  - SessionState Klasse mit Validierung (~40 LOC)
  - Property self.session_state auf VideoPlayer
  - Schrittweise Migration: Alte Flags als Properties die auf session_state delegieren
    (Backward-compatible, kein Big-Bang-Refactoring)
  - Debug-Logging bei State-Transitions (nur wenn --debug)

═══════════════════════════════════════════════
  4 — RESUMABLE CHUNKED UPLOADS  (🟡)
═══════════════════════════════════════════════

Problem: Einzelner multipart POST, bis zu 500MB. Abbruch = Neustart von 0.
Server liest bereits in 256KB Chunks auf Disk (kein RAM-Problem), aber der
Client hat keine Resume-Möglichkeit.

  Server-Änderungen:
  - Neuer Endpoint: POST /rooms/{code}/upload/init
    Body: {user_id, filename, file_size, chunk_size}
    Response: {upload_id} (= video_id, generiert hier statt bei Completion)
    Erstellt temp-Ordner: uploads/{room_code}/chunks/{upload_id}/
  - Neuer Endpoint: PUT /rooms/{code}/upload/{upload_id}/chunk/{index}
    Body: Raw Bytes (kein Multipart-Overhead pro Chunk)
    Server schreibt: chunks/{upload_id}/{index:06d}.part
    Response: {index, received_bytes}
  - Neuer Endpoint: GET /rooms/{code}/upload/{upload_id}/status
    Response: {last_chunk_index, received_bytes, expected_bytes}
    (Client ruft das bei Resume auf um zu wissen wo er weitermachen soll)
  - Neuer Endpoint: POST /rooms/{code}/upload/{upload_id}/complete
    Server merged alle .part Files → finale Datei, räumt temp auf
    Response: {video_id, filename, size} (identisch zum alten Upload-Response)
    Broadcasts video_uploaded wie bisher
  - Alter POST /rooms/{code}/upload bleibt bestehen (Backward-Kompatibilität)
  - Cleanup: Unvollständige Uploads (>30min alt) bei Room-Cleanup entfernen

  Client-Änderungen (session_client.py):
  - _upload_thread Rework:
    1. POST /init → upload_id
    2. File in CHUNK_SIZE (2MB) Blöcke splitten
    3. For each chunk: PUT /chunk/{i}, bei Fehler → retry 3x mit 2s Delay
    4. Progress: Bestehende upload_progress Signal (bytes_sent, total)
    5. POST /complete → video_id
    6. send_play_video(video_id) wie bisher
  - Resume: Bei ConnectionError → GET /status → letzter successful Index →
    Loop ab Index+1 fortsetzen (kein erneuter /init Call)
  - Config: chunk_size (default 2MB, nicht user-facing)

  Kein Chunked Download nötig: Server liefert StreamingResponse, Client liest
  iter_content(256KB). Bei Abbruch reicht ein neuer GET (Server hat die Datei
  vollständig). Optional: Range-Header Support für partial resume, aber
  Low-Priority da Downloads schneller sind als Uploads.

═══════════════════════════════════════════════
  5 — AUTO-UPDATER  (🟡)
═══════════════════════════════════════════════

  Startup-Check (Background-Thread, blockiert UI nicht):
  - GET https://api.github.com/repos/Ukunda/RDM/releases/latest
    Headers: Accept: application/vnd.github+json
  - Vergleich: remote tag_name vs. eingebaute VERSION Konstante
    Parsing: semver-artig (v1.2.3 → Tuple-Vergleich)
  - Timeout: 5s (Netzwerkfehler → still ignorieren, kein Popup)
  - Rate: Einmal pro Programmstart, kein wiederholter Timer

  Update-Dialog (nur wenn neue Version vorhanden):
  - "Update verfügbar: v1.2 → v1.3"
  - Release-Notes (body aus GitHub API) anzeigen (QTextBrowser, Markdown)
  - Drei Buttons:
    "Jetzt updaten" → startet Download + Update-Prozess
    "Später" → schließt Dialog, fragt beim nächsten Start erneut
    "Überspringen" → skipped_version=tag in config, nie wieder für diese Version
  - Prüfung: if tag == config.skipped_version → kein Dialog

  Update-Mechanismus (Windows-spezifisch):
  - Download: .exe aus release assets[0].browser_download_url → %TEMP%\rdm_update.exe
  - Progress-Dialog (QProgressDialog) mit Download-Fortschritt
  - Nach Download: Schreibe updater.bat nach %TEMP%:
      @echo off
      timeout /t 2 /nobreak > nul
      move /y "%TEMP%\rdm_update.exe" "{aktueller_exe_pfad}"
      start "" "{aktueller_exe_pfad}"
      del "%~f0"
  - Starte updater.bat (detached, CREATE_NO_WINDOW)
  - App beendet sich (sys.exit)
  - Batch-Script: wartet 2s (Prozess-Exit), überschreibt, startet neu, löscht sich

  Sicherheit:
  - HTTPS-only für Download
  - Optionale Checksum-Verifikation (SHA256 in Release-Notes oder als .sha256 Asset)

═══════════════════════════════════════════════
  6 — PREFETCH NÄCHSTES VIDEO  (🟡→🔴)
═══════════════════════════════════════════════

Problem: Jeder Clip-Wechsel in Sessions hat 5-30s Wartezeit
(Upload + Download + Ready-Sync). Bei großen Dateien unerträglich.

Ansatz: Spekulativer Prefetch des NÄCHSTEN Clips während der aktuelle läuft.
Kein Queue-UI, kein Server-Queue-State, kein Drag-to-Reorder.

  Neues Konzept: "Prefetch-Slot"
  - Client hat einen Prefetch-Slot: {video_id, local_path} oder None
  - Server hat pro Room: prefetch_video = {video_id, ready_users: set} oder None

  Flow — Prefetch einleiten (nach all_ready des aktuellen Clips):
  1. Host wartet 3s (lässt User erst den Clip sehen)
  2. Host sendet: {"type": "request_prefetch"} (wie request_random, aber non-blocking)
  3. Server wählt Provider (gleiche Logik wie request_random, mit Timeout/Retry aus Fix #2)
  4. Provider erhält: {"type": "provide_prefetch_clip"} → wählt nächsten Clip,
     uploaded via bestehenden Upload-Endpoint
  5. Provider sendet: {"type": "prefetch_ready", "video_id": id}
  6. Server setzt room.prefetch_video = {video_id, ready_users: {provider_uid}}
  7. Server broadcasts: {"type": "prefetch_available", "video_id": id, "filename": name}
  8. Andere Clients downloaden im Hintergrund (state.transfer = PREFETCHING)
  9. Nach Download: Client sendet {"type": "prefetch_downloaded", "video_id": id}
  10. Server trackt ready_users. Wenn alle ready → room.prefetch_video.all_ready = True

  Flow — Prefetch nutzen (wenn User nächsten Clip will):
  1. Host ruft play_random_clip → prüft prefetch_slot
  2. Wenn prefetch_slot vorhanden UND video_id == room.prefetch_video:
     - Host sendet {"type": "play_prefetched", "video_id": id}
     - Server: Wenn alle prefetch_downloaded → sofort all_ready (skip Download-Phase)
     - Server: Wenn nicht alle ready → normaler ready-sync (die die noch downloaden
       müssen warten, aber die meisten haben es schon)
  3. Wenn kein Prefetch oder Prefetch nicht ready → normaler Flow (upload + ready-sync)

  Client State:
  - _prefetch_slot: Optional[dict] = None  # {"video_id": str, "local_path": str}
  - transfer State: PREFETCHING (parallel zu PLAYING erlaubt, siehe State Consolidation)
  - SessionPanel: Kleiner Indikator "⏳ Nächster Clip wird vorbereitet…" (kein Overlay)

  Edge Cases:
  - User skipped bevor Prefetch fertig → Prefetch verwerfen, normaler Flow
  - Provider disconnected während Prefetch → Prefetch abbrechen, kein Fehler (war optional)
  - Prefetch-Clip == aktueller Clip (Provider hat nur wenige) → ignorieren

  Abhängigkeit: Pool Robustheit (#2) muss fertig sein (Timeout/Retry-Logik)
  Profitiert von: State Consolidation (#3, PREFETCHING Dimension)

═══════════════════════════════════════════════
  7 — MODUL-SPLIT  (🟡 Housekeeping)
═══════════════════════════════════════════════

random_clip_player.py ist bei 3500+ Zeilen. Wartbarkeit leidet.

  Vorgeschlagene Aufteilung:
  - config.py: ConfigManager Klasse + COLORS dict + Defaults (~200 LOC)
  - widgets.py: StyledButton, ClickableSlider, ButtonBar, BlockedListDialog,
    SettingsDialog, StartupDialog, TransferOverlay (~800 LOC)
  - session_panel.py: SessionPanel Klasse (~500 LOC)
  - player.py: VideoPlayer Klasse (Rest, ~2000 LOC)
  - main.py: Entry-Point (__main__), Argument-Parsing, Logging-Setup (~50 LOC)

  Migration-Strategie (kein Big-Bang):
  1. config.py extrahieren (keine Abhängigkeit auf andere Module)
  2. widgets.py extrahieren (hängt nur von config.py ab)
  3. session_panel.py extrahieren (hängt von config, widgets, session_client ab)
  4. player.py ist der Rest
  5. Circular Imports vermeiden: SessionPanel bekommt VideoPlayer-Referenz per
     __init__(player=...) statt Import

  Timing: NACH Abschluss aller Feature-Arbeit. Merge-Konflikte während
  paralleler Feature-Entwicklung sind es nicht wert.

═══════════════════════════════════════════════
  HOUSEKEEPING — KLEIN
═══════════════════════════════════════════════

🔲 Server: Room-Count-Limit (max 50 Rooms)
   Einzeiler in create_room. if len(rooms) >= MAX_ROOMS: return 503.

🔲 Server: Auth-Token statt user_id
   Bei Join: Server generiert JWT/HMAC-Token, Client sendet Token bei WS-Auth.
   Verhindert user_id-Spoofing. Niedrige Priorität (Server läuft lokal/Docker).

🔲 Folder-Scan: rglob("*") → gezielte Extension-Globs (*.mp4, *.mkv, etc.)
   Nur messbar bei Verzeichnissen mit vielen Nicht-Video-Dateien.

🔲 _playing_remote_clip Fix (Teil von #2d, aber auch standalone machbar)
   _on_all_ready: check ob video_id eigener Upload war → False statt True.

═══════════════════════════════════════════════
  REIHENFOLGE
═══════════════════════════════════════════════

  1. 🐛 Desync-Heartbeat              (🟢 ~60 LOC, höchster UX-Impact/LOC)
  2. 🐛 Shared Pool Robustheit        (🟡 Timeout, Clip-Count, Exhaustion-Tracking)
  3. 🔲 Session State Consolidation    (🟡 Basis für Prefetch, reduziert Flag-Chaos)
  4. 🔲 Auto-Updater                   (🟡 eigenständig, kein Risiko)
  5. 🔲 Resumable Uploads              (🟡 Chunked + Resume)
  6. 🔲 Prefetch nächstes Video        (🔴 nach #2 + #3, größtes UX-Feature)
  7. 🔲 Modul-Split                    (🟡 nach Feature-Freeze)
