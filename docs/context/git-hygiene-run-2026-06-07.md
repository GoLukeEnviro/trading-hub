# Git-Hygiene Run — 2026-06-07

## 1) Klassifikation

### A — Commit-worthy
- `Caddyfile`
- `docker-compose.yml`
- `docs/state/canonical-trading-status.md`
- `docs/state/current-operational-state.md`
- `orchestrator/reports/canonical_trading_status_latest.json`
- `freqforge/user_data/config.json`
- `freqforge-canary/user_data/config.json`
- `freqtrade/shared/fleet_risk_manager.py`
- `freqtrade/shared/entrypoint_env.py`
- kompletter `self_improvement/`-Baum (Code, Bot-Configs, Shared-Helper)

### B — Ignore-worthy / lokal behalten
- Symlinks / lokale Clones:
  - `freqtrade/freqai-rebel`
  - `freqtrade/freqforge-canary`
  - `freqtrade/regime-hybrid`
- Laufzeit-/Runtime-Artefakte bleiben über bestehende Regeln ignoriert, z. B. `var/trading-self-improvement/`, Backtests, Logs, `.venv/`, `__pycache__/`

### C — Delete / Scratch-worthy
- `freqforge/user_data/strategies/FreqForge_Override_*Probe.py`
- `freqtrade/shared/entrypoint_envsubst.sh`

## 2) Pfad-Rollen nach der Bereinigung
- `self_improvement/` = dauerhafte Orchestrator-/Analyse-Quelle
- `var/trading-self-improvement/` = Laufzeitstate, Outputs, Backtest-Artefakte
- `docs/state/` = aktuelle, entscheidungsrelevante Status-Snapshots
- `orchestrator/reports/` = aktuelle strukturierte Diagnose-/Statusberichte
- `freqtrade/shared/` = geteilte Freqtrade-Hilfslogik
- `freqforge*/user_data/strategies/` = produktive Strategien; Probe-Dateien werden nicht versioniert

## 3) Bewusst lokal geblieben
- Die drei Symlink-Clones unter `freqtrade/` sind absichtlich nicht Teil des Haupt-Repos.
- Runtime- und Backtest-Artefakte bleiben lokal und werden durch `.gitignore` abgedeckt.
- Die Probe-Strategien wurden gelöscht statt verschoben, weil sie nur Debug-/Experiment-Charakter hatten.

## 4) Offene Fragen / manuelle Entscheidungspunkte
- Die `self_improvement`-Configs und Shell-Wrapper enthalten weiterhin hostbezogene Absolute Paths als operative Konvention.
- Falls das Repo künftig auf einen anderen Host umzieht, sollte diese Pfadschicht auf relative Root-Auflösung umgestellt werden.
- Die lokale `.env.freqtrade` bleibt bewusst untracked; die Compose-Datei referenziert sie nur.

## 5) Nächster sinnvoller Agent
- Ein Self-Improvement-Executor kann jetzt die `self_improvement/`-Struktur als Quelle nutzen und Runtime-Artefakte sauber in `var/trading-self-improvement/` schreiben.
- Ein Deployment-/Audit-Agent kann die drei Freqtrade-Configs und den Caddy/Compose-Stack gegen die aktuellen State-Dateien prüfen, ohne lokale Noise-Pfade anfassen zu müssen.
- Ein Follow-up-Hygiene-Agent kann später entscheiden, ob die hostgebundenen Pfade in `self_improvement/` noch weiter generalisiert werden sollen.
