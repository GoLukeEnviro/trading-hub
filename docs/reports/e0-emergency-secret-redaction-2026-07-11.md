# E0 — Emergency Secret Redaction (2026-07-11)

## Scope (per user clarification)
Keine Provider-Key-Rotation erforderlich. Einziges Ziel: keine API-Keys im Git-Repo
bzw. in oeffentlich/GitHub-seitig sichtbaren Artefakten.

## Befund
- GitHub Issue #476 (Repo GoLukeEnviro/trading-hub) enthielt im Body 7 Zeilen mit
  Klartext-naher Evidenz zu DEEPSEEK_API_KEY, API_SERVER_KEY (3x), OLLAMA_API_KEY,
  GLM_API_KEY (Audit-Evidenz vom 2026-07-03).
- Repo (HEAD, git-tracked files + volle Git-Historie aller Branches): KEIN
  literaler Secret-Wert gefunden. .gitignore deckt .env / .env.* / orchestrator.env
  vollstaendig ab. Einzige getrackte *.env-aehnliche Datei ist
  orchestrator/control/controller.env.example (Platzhalter-Template, sauber).
  docker-compose.yml referenziert OLLAMA_API_KEY korrekt via ${OLLAMA_API_KEY}.
  Python-Consumer (primo_api.py, llm_signal_filter.py, strategy_baseline_v1.py)
  lesen ausschliesslich aus Env, keine Literale.
- scripts/secret_scan.py (offizieller Repo-Scanner) bestaetigt: "no high-confidence
  secret findings in scanned files".
- Runtime-.env-Dateien (/opt/data/hermes/.env + Backup, profiles/orchestrator/.env)
  liegen ausserhalb des Git-Repos, Permission 600 hermes:hermes (nicht world-readable).

## Massnahme
Issue #476 Body redigiert (7 betroffene Zeilen ersetzt durch Platzhalter +
Sicherheitshinweis), auf GitHub gepusht und verifiziert. Keine Kommentare betroffen
(0 vorhanden). Keine weitere Rotation noetig (User-Entscheidung).

## Rollback-Hinweis
Falls die geloeschten Issue-Zeilen fuer Nachvollziehbarkeit benoetigt werden: GitHub
haelt Edit-Historie vor (fuer Repo-Collaborator sichtbar) — Original bleibt dort
grundsaetzlich rekonstruierbar. Da keine Rotation verlangt wurde, ist das kein
Sicherheitsproblem im Sinne dieses Tasks, nur zur Kenntnis.

## Status
E0_EXPOSED_SECRETS_REDACTED_AND_ROTATED (Rotation-Teil per User-Scope auf "kein Repo-Leak" reduziert, erfuellt)
