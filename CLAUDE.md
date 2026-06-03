# CLAUDE.md

Diese Datei bietet Orientierung fuer Claude Code (claude.ai/code) bei der Arbeit in diesem Repository.

## Sprache

**Kommunikation immer auf Deutsch.** Antworten, Erklaerungen, Kommentare und alle Interaktionen mit dem Nutzer erfolgen auf Deutsch. Code-Kennungen (Variablen, Funktionsnamen, Pfade) bleiben natuerlich auf Englisch.

## Projektueberblick

Trading Hub ist ein privates, autonomes Krypto-Trading-Forschungssystem. Es laeuft **ausschliesslich im Dry-Run-Modus** — Live-Trading ist ohne explizite menschliche Freigabe nach Absolvierung aller Validierungsgates strikt untersagt.

Repository: `github.com/GoLukeEnviro/trading-hub` (privat). Arbeitsverzeichnis: `/home/hermes/projects/trading`.

## Unverletzliche Sicherheitsregeln

- **Niemals** `dry_run=false` setzen, Live-Trading aktivieren, Exchange-Zugangsdaten hinterlegen oder echte Orders platzieren.
- **Niemals** Freqtrade-Konfigs, Strategielogik, Signal-Schwellenwerte oder Pair-Allowlists ohne explizite Freigabe aendern.
- **Niemals** Docker-Container ohne explizite Freigabe neustarten oder recreieren.
- **Niemals** `git add .` verwenden — Dateien immer explizit nach Pfad stagen.
- **Niemals** force-push, `git reset --hard`, `git clean -fdx` oder History umschreiben.
- **Niemals** Secrets, Runtime-State, Datenbanken, Logs, Backups oder `.env`-Dateien committen.
- `docs/context/` nach jeder wesentlichen Aenderung, jedem Vorfall oder jeder Architekturentscheidung aktualisieren.

## Architektur

```
ai-hedge-fund-crypto (Port 8410)     Signal-Generator — TA-Ensemble + LLM via DeepSeek
        │ hermes_signal.json
        ▼
Trading-Pipeline                     orchestrator/scripts/trading_pipeline.py
  ├── signal_bridge.py               Liest Signal, schreibt per-Bot-State-Dateien
  ├── riskguard.py                   Validiert Signal-Schema, Frische, Konfidenz
  └── tools/freqforge/               Shadow-Evaluator — passiver Beobachter, handelt nie
        │ primo_signal_state.json
        ▼
Freqtrade-Fleet (alles Dry-Run)      freqtrade/docker-compose.fleet.yml
  ├── FreqForge         :8086        FreqForge_Override-Strategie
  ├── Canary             :8081        FreqForge_Override (abgeleitet)
  ├── Regime-Hybrid      :8085        RegimeSwitchingHybrid_v7_v04_Integration
  └── FreqAI-Rebel       :8087        RebelLiquidation + RebelXGBoostClassifier
```

Zusaetzliche Infrastruktur in der root-`docker-compose.yml`: Docker-Socket-Proxy, Hermes-Agent-Container (hermes-green), Qdrant/Ollama/Mem0-Memory-Stack, Caddy-Reverse-Proxy und einfacher Watchdog-Container.

## Wichtige Verzeichnisse

| Pfad | Zweck |
|------|-------|
| `orchestrator/scripts/` | Alle Automatisierungen: Healthchecks, Watchdogs, Audits, Bridge, Heartbeat, Fleet-Reparatur |
| `orchestrator/guardian/` | Externer Guardian-Docker-Container (traegt `external_cron_guardian.sh`) |
| `orchestrator/state/` | Runtime-State (gitignored) — Equity, Drawdown, Quarantaene, Alerts |
| `freqtrade/bots/` | Per-Bot-Verzeichnisse (config/, user_data/, docker-compose-Dateien) |
| `freqtrade/shared/` | Gemeinsame Fleet-Bibliotheken: fleet_watcher, fleet_risk_manager, fleetguard, Strategien |
| `freqforge/` | FreqForge-Baseline-Bot: Config und user_data |
| `tools/freqforge/` | FreqForge-Shadow-Evaluator (freqforge_shadow.py, freqforge_rules.py) |
| `tools/riskguard/` | RiskGuard-Implementierung (riskguard.py, decisions.jsonl) |
| `bridge/` | Hermes/Primo-Bridge (hermes_primo_bridge.py, Dockerfile) |
| `docs/state/` | `current-operational-state.md` — der kanonische System-Snapshot |
| `docs/context/` | Append-only historische Berichte und Migrationsnotizen |

## Betriebbefehle

```bash
# Fleet-Healthcheck
python3 freqtrade/shared/fleet_watcher.py --once --tail-lines 20

# Docker-Status (vom Repo-Root aus)
docker compose ps
docker compose -f freqtrade/docker-compose.fleet.yml ps

# Signal-Layer-Health
curl -s http://localhost:8410/health

# Bot-API-Ping
curl -s http://localhost:8086/api/v1/ping   # FreqForge
curl -s http://localhost:8085/api/v1/ping   # Regime-Hybrid

# Git-Hygiene
git branch --show-current
git status -sb
git diff --cached
git check-ignore -v <pfad>
```

## Python-Umgebung

Das venv liegt unter `.venv/` im Repo-Root. Freqtrade-Bots laufen als UID/GID 10000 (ftuser) in Docker mit dem Image `freqtrade-hermes10000:stable` (gebaut aus `freqtrade/Dockerfile.hermes10000`).

## Git-Workflow

- `main` immer mit `origin/main` synchron halten.
- Feature-Branches fuer nicht-triviale Aenderungen anlegen.
- Dateien explizit nach Pfad stagen; `git diff --cached` vor jedem Commit pruefen.
- Nested Repos (`ai-hedge-fund-crypto/`, `Agenten_Auto_Trade/`, `btc5m-bot/`, `Polymarket-BTC-15-Minute-Trading-Bot/`, `weatherbot/`) sind gitignored — deren Inhalte nicht tracken.
- `tools/riskguard/decisions.jsonl` ist lokales Runtime-Log und bleibt untracked.

## Cronjobs

Die Cronjobs werden vom Hermes-Agent verwaltet (Profil: `orchestrator`). Die Job-Definitionen liegen in `/opt/data/profiles/orchestrator/cron/jobs.json`, ein Backup in `orchestrator/config/cron_jobs_backup.json`. Alle Jobs sind `no_agent: true` (kein LLM-Aufruf, reine Skriptausfuehrung).

| Job | Skript | Intervall | Zustellung | Beschreibung |
|-----|--------|-----------|------------|-------------|
| `signal-heartbeat` | `ai_hedge_signal_heartbeat.sh` | alle 20 Min | local | Loest einen neuen Signalzyklus beim ai-hedge-fund-crypto-Container aus (`/trigger`) |
| `trading-pipeline` | `trading_pipeline.py` | alle 10 Min | local | Liest Signal, validiert via RiskGuard, schreibt Shadow-Log, verteilt per-Bot-State-Dateien |
| `drawdown-guard` | `drawdown_guard.py` | alle 30 Min | telegram | Prueft Portfolio-Drawdown, Signal-Frische, Fleet-Health. Sendet Alerts ab 5% DD (WARN), 8% (PAUSE), 12% (CLOSE), 15% (HALT) |
| `container-watchdog` | `container_watchdog.sh` | alle 5 Min | telegram | Prueft ob alle kritischen Container laufen. Fallback auf file-based Heuristik wenn kein Docker-Socket verfuegbar. Nur Ausgabe bei Problemen |
| `mcp-watchdog` | `mcp_watchdog.sh` | alle 5 Min | telegram | Startet `bitget_mcp_server.py` automatisch neu wenn der Prozess fehlt |
| `daily-backup` | `backup_rotation.py` | taeglich 02:00 UTC | local | Rolling Backup der Bot-Configs, State-Dateien und Logs. Behaelt 7 Tage |
| `portfolio-rebalancer` | `portfolio_rebalancer.py` | woechentlich Mo 06:00 UTC | origin | Portfolio-Rebalancing-Empfehlungen |
| `cron-guardian` | `restore_cron_jobs.sh` | alle 6 Std | local | Stellt Cron-Jobs aus Backup wieder her falls jobs.json korrupt oder fehlend |
| `smart-heartbeat` | `smart_heartbeat.py` | alle 10 Min | local | Intelligenter Heartbeat mit Zustandsbewertung |

**Wichtige Hinweise zu Cronjobs:**
- Cron-Jobs duerfen **nicht** ohne explizite Freigabe geaendert, migriert oder geloescht werden.
- Der `cron-guardian` kann `jobs.json` aus dem Backup restaurieren, wenn die Datei fehlt oder ungueltig ist.
- `trading_pipeline.py` hat einen harten Konfidenz-Schwellenwert von 0.65 und blockiert Signale aelter als 25 Minuten.
- Drawdown-Levels sind in `drawdown_guard.py` definiert und duerfen nicht ohne Freigabe geaendert werden.
- Logs der Cronjobs landen in `orchestrator/logs/`.

## Guardian-Setup

Der **trading-guardian** ist ein unabhaengiger Docker-Container, der alle 5 Minuten System-Checks durchfuehrt und bei Bedarf selbstreparierend eingreift. Er laeuft vollstaendig getrennt vom Hermes-Agent.

**Architektur:**
```
trading-guardian (Docker-Container)
  ├── guardian_loop.sh              Hauploop: ruft alle 5 Min external_cron_guardian.sh auf
  └── external_cron_guardian.sh     Fuenfstufiger Check- und Reparaturprozess
```

**Mount-Layout:**
```
/guardian/entrypoint  →  einkompilierte Guardian-Skripte (Dockerfile COPY)
/guardian/data        →  /home/hermes/projects/trading
/guardian/cron        →  /opt/data/profiles/orchestrator/cron
/guardian/scripts     →  /opt/data/profiles/orchestrator/scripts
/var/run/docker.sock  →  Docker-API-Zugriff (nur Lesezugriff via Socket-Proxy)
```

**Fuenf Guardian-Checks:**

1. **jobs.json-Integritaet** — Prueft ob `jobs.json` existiert und gueltiges JSON ist. Stellt aus Backup wieder her bei Fehlern.
2. **Steckengebliebene Jobs** — Zaehlt aktive Jobs mit `next_run_at=null`. Ab 3 steckengebliebenen Jobs: Warnung und Empfehlung fuer manuelle Recovery.
3. **Signal-Frische** — Prueft Alter von `hermes_signal.json`. Ab 30 Minuten: triggert `/trigger` am ai-hedge-fund-crypto-Container und startet die Trading-Pipeline via `docker exec`.
4. **Kritische Skripte** — Prueft ob alle wichtigen Skripte im Profil-Verzeichnis existieren. Kopiert bei Fehlen aus dem Projektverzeichnis nach.
5. **Permission-Drift-Guard** — Prueft und repariert Berechtigungen auf kritischen Shared-State-Dateien und Verzeichnissen. Modus: `PERMISSION_GUARD_MODE=repair` (Standard) oder `check` (nur Melden).

**Permission-Guard-Scope:**
- Verzeichnisse: `freqtrade/shared/`, `freqtrade/logs/`, `orchestrator/logs/` (erwartet: `2775` GID `10000`)
- Dateien: `primo_signal_state.json`, `fleet_risk_state.json`, `.fleet_risk_state.json.lock`, diverse Log-Dateien
- Cron-Verzeichnis: korrigiert `root:root`-Dateien auf `root:10000 0640`

**Guardian-Logs:** `orchestrator/logs/external_cron_guardian.log`

## Runbooks

Die Runbooks liegen in `docs/runbooks/`. Jedes Runbook folgt dem gleichen Muster: Constraints, Audit-Steps, Decision-Matrix und Eskalationskriterien.

### Honcho-Health-Audit (`docs/runbooks/honcho-health-audit.md`)

Read-Only-Audit fuer Honcho-API und Datenbank. Prueft Container-Status, Port-Mapping, Dokumentenanzahl in PostgreSQL und API-Endpunkt-Erreichbarkeit.

**Entscheidungsmatrix:**
| Pruefung | Ergebnis | Klassifikation |
|----------|----------|----------------|
| Container laeuft | false | DOWN → Eskalation |
| API 200 | true | HEALTHY |
| API non-200 | true | DEGRADED → Logs pruefen |
| API Timeout | — | UNREACHABLE → Netzwerk pruefen |

Eskalation: Luke via Telegram informieren, geplante Diagnose nennen, Freigabe abwarten. Kein Service-Restart ohne Freigabe.

### Signal-Staleness-Audit (`docs/runbooks/signal-staleness-audit.md`)

Read-Only-Audit fuer Signal-Frische. Prueft Timestamps von `hermes_signal.json`, Bridge-State und Cron-Job-Status.

**Entscheidungsmatrix:**
| Signal-Alter | Klassifikation | Aktion |
|--------------|----------------|--------|
| < 45 Min | FRESH | Kein Handlungsbedarf |
| 45 Min – 2h | STALE | Monitoring erhoehen |
| > 2h | CRITICAL | Eskalation |
| Datei fehlt | MISSING | Sofortige Eskalation |

Eskalation: Beweise dokumentieren, Luke via Telegram informieren, geplante Aktion + Zeitrahmen nennen, Freigabe abwarten.

### Zusaetzliche operative Skripte (Runbook-artig)

Diese Skripte in `orchestrator/scripts/` fungieren als automatisierte Runbooks:

| Skript | Rolle | Eingriff? |
|--------|-------|-----------|
| `fleet_auto_repair.py` | Fleet-Gesundheit pruefen (Profit-Factor < 1.4, Drawdown > 5%, leere DBs, offene Positionen > 48h) | Advisory only — generiert Bericht, keine Config-Aenderungen |
| `fleet_healthcheck.py` | Read-only Fleet-Audit: Container-Status, `dry_run`-Verifikation, Credential-Check, Strategie-Match | Read-only, erzeugt JSON- und Markdown-Report unter `orchestrator/reports/` |
| `ghostbuster.py` | Detektiert und meldet Ghost-Patterns (veraltete Referenzen, stale Container, Permission-Drift) | Nur melden. Kein `docker prune`, kein Job-Removal, kein Container-Loeschen |
| `container_watchdog.sh` | Prueft ob alle kritischen Container laufen | Nur Ausgabe bei Problemen (silent = OK). Kein automatischer Restart |
| `drawdown_guard.py` | Portfolio-Drawdown-Level ueberwacht | Advisory + Telegram-Alert. KEIN automatisches Pausieren ohne User-Approval |
| `mcp_watchdog.sh` | Ueberwacht `bitget_mcp_server.py`-Prozess | Startet Prozess automatisch neu wenn er fehlt |

## Monitoring und Zustandsautomat

Das System verwendet eine Gate-basierte Pipeline: `INIT → PREFLIGHT → DATA_READY → SIGNAL_READY → RISK_FILTERED → SHADOW_LOGGED → FLEET_SYNCED → MONITORING`

Signal-Frische-Schwelle: 45 Minuten. Konfidenz muss >= 0.60 sein. Fehlerzustaende: `DATA_STALE`, `SIGNAL_INVALID`, `RISK_BLOCKED`, `FLEET_UNHEALTHY`, `CRON_DRIFT`.

## Dokumentationskonventionen

- `docs/state/current-operational-state.md` — Single Source of Truth fuer den aktuellen Systemzustand.
- `docs/context/` — Append-only historische Berichte, Benennungsschema `YYYY-MM-DD-thema.md`.
- Root-Dokumentation (`README.md`, `AGENTS.md`, `SOUL.md`, `ORCHESTRATOR_CHARTER.md`) immer mit dem Repo-Zustand konsistent halten.

## Eskalation an Menschen

**Eskalation erforderlich bei:** Live-Geld-Risiko, gefundene Zugangsdaten, `dry_run=false`, Aenderungen an Freqtrade-Config/Strategie, Container-Recreation, Signal-Schwellenwert-Aenderungen, Datenloeschung, Cronjob-Migration/-Loeschung.

**Keine Eskalation noetig bei:** Read-only-Audits, Berichtgenerierung, JSON-Validierung, Healthchecks, nicht-destruktive Git-Commits.
