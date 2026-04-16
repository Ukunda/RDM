═══════════════════════════════════════════════
  TODO 2 — Ergänzungen & Verbesserungen
  Stand: 2026-04-16
═══════════════════════════════════════════════

Legende:
  🟢 Einfach   — Hauptsächlich UI-Arbeit, wenig Risiko, kein Protokoll-Umbau
  🟡 Mittel    — Erfordert Client+Server-Änderungen, moderate Komplexität
  🔴 Komplex   — Tiefgreifende Architektur-Änderung, hohes Regressionsrisiko

═══════════════════════════════════════════════
  BUGS
═══════════════════════════════════════════════

🐛🟡 Multiskip-Bug: Gleichzeitiges "Random Clip" drücken bricht Session
   Symptom: Zwei User drücken zeitnah "Random Clip" → zwei Videos werden
   geladen, eines startet kurz und wird sofort vom zweiten überschrieben.
   Ursache: Kein serverseitiger Lock auf Clip-Transitionen. Der Ready-Sync
   kann keine überlappenden prepare_video-Flows serialisieren.
   Lösung: Server-seitige Transition-Sperre (nur ein prepare_video gleichzeitig).
   Nachfolgende Requests werden in eine Queue gestellt oder mit "busy"-Fehler
   abgelehnt. Client zeigt Toast: "Clip wird bereits geladen…"
   ⚠ Überschneidung mit TODO.md — dort bereits als High-Priority Bug gelistet.
   Abhängigkeit: Profitiert stark von Phase 3 State Machine (TODO.md).

🐛🟡 Autoplay/Random startet Video nicht — manuelles Play nötig
   Symptom: Nach "Random Clip" oder bei Autoplay lädt das Video, aber es
   bleibt pausiert. User muss jedes Mal Play drücken.
   Ursache (vermutl.): MPV wird mit keep_open=True initialisiert. Nach dem
   Laden eines neuen Videos bleibt player.pause ggf. auf True, weil der
   EOF-State vom vorherigen Clip den Pause-Flag nicht zurücksetzt. Im
   Session-Modus zusätzlich möglich: _ignore_remote blockiert den
   automatischen Play-Befehl nach all_ready.
   Lösung: Nach player.play(filepath) explizit player.pause = False setzen,
   sobald das Video geladen ist (auf 'file-loaded' MPV-Event warten).
   Im Session-Modus: Nach all_ready sicherstellen, dass Pause aufgehoben wird.

═══════════════════════════════════════════════
  FEATURES — SESSION
═══════════════════════════════════════════════

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
  FEATURES — LOKAL
═══════════════════════════════════════════════

🔲🟡 Dislike-Button: Reaktivierung im Session-Modus + Dual-Funktion
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
  PERFORMANCE & UX
═══════════════════════════════════════════════

🔲🔴 Upload/Download-Geschwindigkeit & Transparenz verbessern
   Symptom: Große Videos (+500 MB) blockieren die Session. User denken das
   Programm ist abgestürzt, weil keine sichtbare Aktivität stattfindet.
   Dann spielt plötzlich ein Video.
   ⚠ Überschneidung mit TODO.md — dort als "System gets very slow with larger
   clips" gelistet.
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
  ABGLEICH MIT TODO.md
═══════════════════════════════════════════════

Folgende Punkte aus todo2 überschneiden sich mit bestehenden TODO.md-Einträgen:

  • Multiskip-Bug ↔ TODO.md "Two people pressing Random Clip"
  • Upload/Download-Speed ↔ TODO.md "System gets very slow with larger clips"
  • Video-Queue + Prefetch → Löst teilweise TODO.md "ready-sync fragility"
  • Pool Opt-In/Out → Erweitert TODO.md "Shared clip pool rework"

Folgende Punkte sind NEU und nicht in TODO.md enthalten:

  • Autoplay-Bug (Video startet nicht automatisch)
  • Startup-Dialog (Zuschauen vs. Clips teilen)
  • Dislike Dual-Funktion (Blacklist vs. Papierkorb)
  • Advanced Info Toggle & Status-Overhaul
  • Individueller Pool Opt-In pro User

═══════════════════════════════════════════════
  EMPFOHLENE REIHENFOLGE
═══════════════════════════════════════════════

  1. 🐛 Autoplay-Bug fixen           (🟡 schneller Win, nervt am meisten)
  2. 🐛 Multiskip-Bug (Server-Lock)  (🟡 kritisch für Session-Stabilität)
  3. 🔲 Startup-Dialog               (🟢 schnell umsetzbar, guter UX-Gewinn)
  4. 🔲 Advanced Info & Status        (🟢 schnell umsetzbar, reduziert Verwirrung)
  5. 🔲 UX-Sofortmaßnahmen Downloads (🟢 Fortschrittsbalken-Overlay)
  6. 🔲 Pool Opt-In/Out pro User     (🟡 mittlerer Aufwand)
  7. 🔲 Dislike Dual-Funktion        (🟡 mittlerer Aufwand)
  8. 🔲 Video-Queue + Prefetch       (🔴 großes Feature, nach State Machine)
  9. 🔲 Transfer-Optimierung         (🔴 großes Feature, nach Queue)
