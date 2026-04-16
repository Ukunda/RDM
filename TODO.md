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
  - Timer starten bei all_ready UND bei unpause, stoppen bei pause/disconnect/stop
  - Nach einem Seek: Timer resetten (restart mit vollem 5s Intervall).
    Ohne Reset könnte ein Heartbeat mit der alten Position feuern bevor der
    Seek-Event den Gast erreicht → Gast korrigiert zur alten Position,
    dann kommt der Seek → sichtbarer Glitch.

  Server:
  - "position_heartbeat" → broadcast an alle AUSSER Sender (wie play/pause/seek)
  - Kein serverseitiger State — reines Relay

  Client (Gast):
  - Signal position_heartbeat(float, float) auf SessionSignals
  - Handler _on_position_heartbeat(host_pos, host_speed):
    - RTT-Kompensation: host_pos += (last_ping_ms / 2000.0) * host_speed
      (Heartbeat reiste ~halbe RTT durchs Netz, Host ist inzwischen weiter.
      Ohne Kompensation würde der Gast bei 200ms Ping dauerhaft ~0.1s
      "korrigieren" obwohl er eigentlich synchron ist.)
    - Voraussetzung: _on_ping_result muss latency_ms in self._last_ping_ms
      speichern (aktuell wird es nur ins Label geschrieben, nicht gespeichert).
    - Eigene Position per self.player.time_pos lesen
    - drift = abs(eigene_pos - compensated_host_pos)
    - drift > 2.0s → _ignore_remote=True, player.seek(compensated_host_pos),
      _ignore_remote=False
    - drift > 5.0s → zusätzlich kurze Statusmeldung "🔄 Sync korrigiert"
    - drift < 0.5s → nichts tun (normaler Jitter + Messungenauigkeit)
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
  Fix: Server fügt "uploaded_by" in die all_ready Message ein (Room.videos[video_id]
  ["uploaded_by"] existiert bereits). Client prüft uploaded_by == own user_id.
  Wenn ja → _playing_remote_clip=False. Kein Raten über Client-Cache-State nötig.

═══════════════════════════════════════════════
  3 — SESSION STATE CONSOLIDATION  (🟡)
═══════════════════════════════════════════════

Problem: _session_uploading, _pending_sync_video_id, _pending_prepare_video_id
sind drei separate Felder die eine einzige Sache beschreiben: "In welcher Phase
ist der aktuelle Clip-Wechsel?" Dazu kommt _session_uploading das bei Disconnect
hängen bleiben kann (→ User locked out).

Ansatz: Ein Enum für die Workflow-Phase + ein separater Prefetch-State.
Kein Compound-State aus 3 Enums (over-engineering für die tatsächliche Komplexität).

  class SessionPhase(Enum):
      IDLE = "idle"                # Nichts passiert / normale Wiedergabe
      UPLOADING = "uploading"      # Wir laden einen Clip hoch
      DOWNLOADING = "downloading"  # Wir laden einen Clip herunter (prepare_video)
      READY_WAIT = "ready_wait"    # Video geladen, warten auf all_ready
      SYNCING = "syncing"          # Join-in-progress: warten auf Sync-Video

  class PrefetchState(Enum):
      NONE = "none"
      FETCHING = "fetching"        # Prefetch-Download läuft
      CACHED = "cached"            # Prefetch-Video bereit

  Auf VideoPlayer/SessionPanel:
  - self._session_phase = SessionPhase.IDLE
  - self._phase_video_id: Optional[str] = None  (welches Video zur Phase gehört)
  - self._prefetch = PrefetchState.NONE
  - self._prefetch_video_id: Optional[str] = None

  Ersetzt direkt:
  - _session_uploading      → _session_phase == UPLOADING
  - _pending_prepare_video_id → _session_phase == DOWNLOADING, _phase_video_id
  - _pending_sync_video_id    → _session_phase == SYNCING, _phase_video_id
  - _pending_sync_state       → bleibt (ist Daten, kein State)

  Bleibt unverändert (mit Begründung):
  - _ignore_remote: Synchroner Echo-Guard, wird im selben Callstack gesetzt
    und gelöscht. Kein State, kein Lifecycle.
  - _session_shared_pool: Setting, kein Workflow-State.
  - _session_active: UI-Visibility-Flag, orthogonal zum Workflow.
  - _playing_remote_clip: Clip-Eigenschaft, nicht Workflow-Phase.

  Validierung (in Phase-Setter):
  - UPLOADING/DOWNLOADING/SYNCING → nur aus IDLE heraus möglich
  - IDLE → von überall (reset)
  - _phase_video_id wird bei IDLE automatisch auf None gesetzt
  - Debug-Log bei jeder Transition (nur wenn --debug)

  Fehler-Recovery:
  - _show_disconnected: _session_phase = IDLE (räumt alles auf)
  - _on_error: _session_phase = IDLE
  - Timeout: falls Phase != IDLE für >60s ohne Fortschritt → force IDLE + Warnung
    (fängt den Fall ab dass _session_uploading bei Disconnect hängen bleibt)

  Migration: Alte Properties als Wrapper:
  @property
  def _session_uploading(self): return self._session_phase == SessionPhase.UPLOADING
  Schrittweise umstellen, alter Code bricht nicht.

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
    2. File in CHUNK_SIZE (5MB) Blöcke splitten
       (5MB = 100 Requests für 500MB. Bei 2MB wären es 250 — unnötiger
       HTTP-Overhead pro Chunk. Bei 10MB wäre die Resume-Granularität zu grob.
       5MB ist der Sweet Spot.)
    3. For each chunk: PUT /chunk/{i}, bei Fehler → retry 3x mit 2s Delay
    4. Progress: Bestehende upload_progress Signal (bytes_sent, total)
    5. POST /complete → video_id
    6. send_play_video(video_id) wie bisher
  - Resume: Bei ConnectionError → GET /status → letzter successful Index →
    Loop ab Index+1 fortsetzen (kein erneuter /init Call)
  - CHUNK_SIZE als Konstante in session_client.py (nicht user-facing)

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

  Update-Mechanismus (Windows):
  - Windows erlaubt os.rename() auf eine laufende .exe (nur delete/overwrite
    ist gesperrt). Kein Batch-Script nötig.
  - Download: .exe aus release assets[0].browser_download_url → %TEMP%\rdm_update.exe
  - Progress-Dialog (QProgressDialog) mit Download-Fortschritt
  - Nach Download:
    1. os.rename(current_exe, current_exe + ".old")  — laufende .exe umbenennen
    2. shutil.move(%TEMP%\rdm_update.exe, current_exe)  — neue .exe an alten Platz
    3. subprocess.Popen([current_exe], creationflags=DETACHED_PROCESS)  — neue starten
    4. sys.exit(0)  — alte beenden
  - Beim nächsten Start: if exists(exe_path + ".old"): os.remove(exe_path + ".old")
  - Rollback: Falls Schritt 3 fehlschlägt → os.rename(current_exe + ".old", current_exe)
    und Fehlermeldung anzeigen. User hat weiterhin die alte Version.

  Sonderfall: Wenn App via python random_clip_player.py läuft (kein .exe):
  - Update-Check zeigt "Neue Version v1.x verfügbar" + Link zum GitHub Release
  - Kein Auto-Download (macht keinen Sinn für .py-Ausführung)

═══════════════════════════════════════════════
  6 — PREFETCH NÄCHSTES VIDEO  (🟡)
═══════════════════════════════════════════════

Problem: Jeder Clip-Wechsel in Sessions hat 5-30s Wartezeit
(Upload + Download + Ready-Sync). Bei großen Dateien unerträglich.

Kernidee: Das bestehende Ready-Sync + Download-Cache löst Prefetch bereits —
wenn Clients ein Video schon heruntergeladen haben, schlägt _download_thread
sofort im Cache an (get_local_video_path) und emittiert video_ready instant.
Prefetch muss also nur dafür sorgen, dass das Video VOR dem play_video-Aufruf
auf allen Clients liegt. Kein neuer Server-State, kein neues Protokoll.

  Neues WS-Event (2 Stück):
  - "request_prefetch" (Client → Server): Identisch zu request_random, aber
    der Provider uploaded das Video ohne play_video zu senden.
  - "prefetch_available" (Server → alle): {video_id, filename}
    Clients starten Background-Download. Kein Ready-Sync, kein Status-Update.

  Flow:
  1. all_ready für aktuellen Clip → Host startet 3s QTimer
  2. Timer feuert → Host sendet {"type": "request_prefetch"}
  3. Server: Gleiche Provider-Auswahl wie request_random (mit Timeout/Retry aus #2)
  4. Provider: Wählt nächsten Clip aus play_queue, uploaded via existierendem
     POST /upload. SENDET KEIN play_video. Stattdessen sendet Provider:
     {"type": "prefetch_uploaded", "video_id": id}
  5. Server: Broadcasts {"type": "prefetch_available", "video_id": id, "filename": name}
  6. Alle Clients (inkl. Host): download_video(video_id) im Hintergrund.
     Kein Overlay, kein Status-Update (es ist spekulativ, User soll nichts merken).
     Download landet in _videos Cache wie bei normalem Download.
  7. Host speichert: _prefetch_video_id = video_id

  Flow — Prefetch nutzen:
  1. Host ruft play_random_clip:
     - Wenn _prefetch_video_id vorhanden:
       Host's _session_auto_share() erkennt: Video ist bereits uploaded.
       Stattdessen: client.send_play_video(_prefetch_video_id) direkt
       (skip Upload, Video liegt schon auf dem Server).
     - Server startet normalen Ready-Sync (prepare_video → download → ready)
     - ABER: _download_thread bei jedem Client → get_local_video_path → Cache hit
       → sofort video_ready → sofort ready → all_ready in <1s.
     - _prefetch_video_id = None
  2. Wenn kein Prefetch vorhanden → normaler Flow (Upload + Download + Ready-Sync)

  Client State (minimal):
  - _prefetch_video_id: Optional[str] = None
  - _prefetch_state = PrefetchState.NONE / FETCHING / CACHED (aus #3)
  - Cleared bei: disconnect, stop, manueller Clip-Wechsel

  Edge Cases:
  - Prefetch-Download nicht fertig wenn User skippt → normaler Flow, unvollständiger
    Download wird von neuem _download_thread für selbe video_id abgeschlossen
    (oder gestartet falls noch nicht gestartet)
  - Provider disconnect während Upload → Prefetch silently abgebrochen.
    Kein Fehler nötig (Prefetch ist optional, Fallback ist der normale Flow).
  - Room mit nur 1 User → kein Prefetch (User ist selbst Provider + Consumer,
    Upload wäre Verschwendung. Lokale Clips sind eh instant.)
  - Prefetch-Video passt nicht mehr (Provider wechselt) → egal, Video liegt
    trotzdem im Cache. Worst case: unnötig heruntergeladen.

  Warum kein extra Server-State:
  - Server muss nicht wissen wer den Prefetch hat. Wenn play_video kommt,
    ist es ein normaler Ready-Sync. Der Speed-Gewinn kommt ausschließlich
    vom Client-Cache-Hit. Server-Logik bleibt identisch.

  Abhängigkeit: Pool Robustheit (#2) für Timeout/Retry.
  Profitiert von: State Consolidation (#3) für PrefetchState Enum.

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

🔲 Server: Doppelte Zeile entfernen
   server.py L732-733: `target = room.users.get(target_uid)` steht zweimal.
   Harmlos, aber sollte bereinigt werden.

═══════════════════════════════════════════════
  REIHENFOLGE
═══════════════════════════════════════════════

  1. 🐛 Desync-Heartbeat              (🟢 ~60 LOC, höchster UX-Impact/LOC)
  2. 🐛 Shared Pool Robustheit        (🟡 Timeout, Clip-Count, Exhaustion, Remote-Clip-Fix)
  3. 🔲 Session State Consolidation    (🟡 SessionPhase Enum, Basis für Prefetch)
  4. 🔲 Auto-Updater                   (🟡 eigenständig, kein Risiko)
  5. 🔲 Resumable Uploads              (🟡 Chunked + Resume, 5MB Chunks)
  6. 🔲 Prefetch nächstes Video        (🟡 nutzt bestehenden Cache + Ready-Sync)
  7. 🔲 Modul-Split                    (🟡 nach Feature-Freeze)
