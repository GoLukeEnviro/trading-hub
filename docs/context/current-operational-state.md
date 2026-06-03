# Current Operational State — Pointer

**Status:** archived snapshot
**Superseded by:** `docs/context/cron-orchestrator-stable-setup-20260602.md`

Kurzfassung der aktuellen Lage:
- Hermes Cron ist die operative Quelle der Wahrheit.
- 36 Jobs gesamt, 35 aktiviert, 1 pausiert, alle `last_status=ok`.
- Der aktive Signalpfad ist `unified-signal-heartbeat`; `signal-heartbeat` und `smart-heartbeat` sind pausiert.
- Ein klassisches System-Crontab-Setup mit `claudio` ist in diesem Runtime nicht verfügbar.
- Die aktive Orchestrator-State-/Log-Struktur bleibt repo-lokal unter `orchestrator/{logs,state}`.

Für Details und Verifikation: neue Kontext-Datei oben öffnen.
