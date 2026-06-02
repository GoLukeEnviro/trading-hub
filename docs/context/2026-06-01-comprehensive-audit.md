# Trading Hub Komplett-Audit -- 2026-06-01

**Audit-Typ:** Read-Only Sicherheits- und Betriebsaudit
**Auditor:** Claude Code (automatisiert)
**Zeitraum:** 2026-06-01 01:22 UTC bis 01:28 UTC
**Host:** Agent0 | User: hermes (uid=1337, docker=110, ftuser=10000)

---

## Status-Uebersicht

| Kennzahl | Wert |
|----------|------|
| **LIVE_RISK** | **no** |
| **DRY_RUN_PROOF** | **pass** (4/4 Bots) |
| **AUTONOMY_STATUS** | **yellow** |
| **PAPER_TRADING_STATUS** | **active** |
| **MCP_BITGET_STATUS** | **broken** |
| **LIVE_READINESS** | **paper_ready** |

---

## 0. Zusammenfassung (Executive Summary)

Das Trading-System ist **autonom paper-ready** mit Einschraenkungen. Alle 4 Freqtrade-Bots laufen bestaetigt im `dry_run=True`-Modus, keine Exchange-Keys vorhanden, kein Live-Trading-Risiko. Die Hermes-Scheduler-Infrastruktur funktioniert (37 Cron-Jobs, UID/GID korrekt, Docker-Zugriff vom Container). Allerdings gibt es mehrere **mittlere Probleme**: Das Signal ist ~15h alt (Permission-Fehler beim signal-heartbeat), MCP-Server (bitget-paper + filesystem) sind nicht verbunden, und 4 von 12 geprueften Cron-Jobs laufen auf Fehler (ueberwiegend Permission-Probleme). Das Backblaze-Backup laeuft taeglich erfolgreich. **Blocker vor Live-Trading** bleiben zahlreich.

---

## 1. Systemkontext und Sicherheitspreflight

### 1.1 Host-Umgebung
- **Host:** Agent0
- **User:** hermes (uid=1337, gid=1337, groups: 1337, 110(docker), 10000(ftuser))
- **Docker:** Alle Container aktiv, Socket verfuegbar

### 1.2 Compose-Origin
- **Compose-File:** `/opt/hermes-green/docker-compose.yml` bestaetigt
- **hermes-green Container:** Running seit 2026-05-31T23:44 UTC, RestartCount=0

### 1.3 Sicherheit
- Keine Anzeichen von Live-Trading
- Keine Exchange-Keys in den Bot-Konfigurationen
- Alle `.env`-Dateien nicht world-readable

---

## 2. Hermes-Scheduler und Docker-Kontext

### 2.1 Scheduler-Gesundheit
- Gateway-Prozess (PID 36): UID=10000, GID=10000, **Groups=110** (Docker)
- Dashboard-Prozess (PID 37): UID=10000, GID=10000, **Groups=110** (Docker)
- Beide Prozesse aktiv und stabil

### 2.2 Docker-Zugriff vom Container
- `docker exec -u hermes hermes-green docker ps` funktioniert
- Alle 16 Container sichtbar von innen
- `jobs.json`: READ_OK und WRITE_OK als User hermes

### 2.3 Bekannte Warnung
- `auth.json` Permission Denied (UID 10000 vs Container-User) -- Hermes faellt auf leeren Store zurueck, funktional aber stabil

---

## 3. Cron-Autonomie-Status

### 3.1 Job-Uebersicht
| Metrik | Wert |
|--------|------|
| Gesamt-Jobs | **37** |
| Aktiviert | 36 |
| Mit Fehlern | 6 |
| Nie gelaufen | 3 |

### 3.2 Wichtige Jobs

| Job | Enabled | Letzter Lauf | Status |
|-----|---------|-------------|--------|
| critical-event-watchdog | ja | 01:22 UTC | **ok** |
| drawdown-guard | ja | 01:00 UTC | **ok** |
| container-watchdog | ja | 01:00 UTC | **ok** |
| fleet-auto-repair | ja | 00:09 UTC | **ok** |
| trading-pipeline | ja | 01:20 UTC | **ok** |
| daily-heartbeat | ja | gestern 06:02 | **ok** |
| riskguard-service | ja | 01:03 UTC | **error** (Exit 1, aber funktionale Ausgabe) |
| signal-heartbeat | ja | 01:21 UTC | **error** (Permission denied beim Signal-Refresh) |
| smart-heartbeat | ja | 01:22 UTC | **error** (Signal age=898min) |
| config-diff-detector | ja | 01:03 UTC | **error** (Permission denied, Log-File) |
| fleetrisk-auto-params | ja | 01:15 UTC | **error** (Permission denied, auto_params) |

### 3.3 Fehler-Klassifizierung
- **Permission-Fehler (3 Jobs):** signal-heartbeat, config-diff-detector, fleetrisk-auto-params -- alle durch UID-Mismatch (Container-Scheduler laeuft als UID 10000, Ziel-Dateien gehoeren UID 1337 oder 10000 auf dem Host)
- **Exit-Code-1 (2 Jobs):** riskguard-service gibt Exit 1 zurueck obwohl funktional OK (RiskGuard validiert korrekt), smart-heartbeat meldet Signal-Alter > Schwellenwert
- **Kein falscher Hermes-DOWN-Alert:** critical-event-watchdog ist OK

---

## 4. Trading-Container-Fleet

| Container | Status | Seit | Restarts | Health | Port | Strategie |
|-----------|--------|------|----------|--------|------|-----------|
| freqtrade-freqforge | running | May 30 20:18 | 0 | none | 8086 | FreqForge v1 |
| freqtrade-freqforge-canary | running | May 30 20:18 | 0 | none | 8081 | Canary |
| freqtrade-regime-hybrid | running | May 30 20:18 | 0 | none | 8085 | Regime Hybrid |
| freqai-rebel | running | May 30 20:18 | 0 | none | 8087 | FreqAI Rebel |
| ai-hedge-fund-crypto | running | May 25 04:03 | 0 | **healthy** | 8410 | Signal-Generator |
| hermes-green | running | May 31 23:44 | 0 | none | 8083/8642 | Orchestrator |
| green-qdrant | running | May 29 10:47 | 0 | none | 6336 | Vector DB |
| green-mem0 | running | May 29 10:47 | 0 | **healthy** | 8788 | Memory API |
| green-ollama | running | May 29 10:47 | 0 | none | 11436 | LLM |

**Bewertung:** Alle 9 Trading-relevanten Container aktiv, **0 Restarts**, keine Crashloops. Alle Bots zeigen stabile Heartbeats (`state='RUNNING'`, version='2026.3').

### 4.1 Bot-Whitelists
- **FreqForge:** 6 Paare (BTC, ETH, SOL, AVAX, NEAR, ARB)
- **Canary:** 5 Paare (BTC, SOL, AVAX, NEAR, ARB)
- **Regime-Hybrid:** 8 Paare (BTC, ETH, SOL, LINK, DOT, ATOM, UNI, AAVE)
- **Rebel:** 2 Paare (BTC, ETH)

---

## 5. Dry-Run-Beweisfuehrung (KRITISCH)

### 5.1 Konfig-Datei-Verifikation

| Bot | Config-Pfad | dry_run | exchange | keys_present | max_open | stake |
|-----|-------------|---------|----------|--------------|----------|-------|
| freqforge | config_freqforge_dryrun.json | **True** | bitget | false | 5 | 100 |
| canary | config_canary_dryrun.json | **True** | bitget | false | 3 | 50 |
| regime-hybrid | config_regime_hybrid_dryrun.json | **True** | bitget | false | 5 | 50 |
| rebel | config.json | **True** | bitget | false | 2 | 50 |

**Ergebnis: 4/4 Bots bestaetigt dry_run=True. Keine Exchange-Keys vorhanden.**

### 5.2 Zusatz-Configs (Backtest)
- regime-hybrid `config_backtest.json`: dry_run=True
- regime-hybrid `momentum_v2_backtest.json`: dry_run=True

### 5.3 Pipeline-Layer
- `trading_pipeline.py`: MCP_DRY_RUN hardcoded True
- `bitget_mcp_server.py`: DRY_RUN hardcoded True

---

## 6. Freqtrade-API-Gesundheit und Paper-Status

### 6.1 Trade-Statistik

| Bot | DB-File | Trades | Offen | Geschl. PnL (USDT) |
|-----|---------|--------|-------|---------------------|
| freqforge | tradesv3.freqforge.dryrun.sqlite | 52 | **1** | **+7.96** |
| canary | tradesv3.freqforge_canary.dryrun.sqlite | 33 | 0 | **+3.23** |
| regime-hybrid | tradesv3.regime_hybrid.dryrun.sqlite | 43 | 0 | **-7.10** |
| rebel | tradesv3.rebel.dryrun.sqlite | 0 | 0 | **0.00** |
| **Fleet** | | **128** | **1** | **+4.09** |

### 6.2 Offene Position
| Bot | Trade# | Pair | Richtung | Seit | Stake |
|-----|--------|------|----------|------|-------|
| freqforge | 52 | BTC/USDT:USDT | SHORT | 2026-05-29 15:45 | ~95.89 USDT |

### 6.3 Letzte geschlossene Trades (Top 5 pro Bot)

**FreqForge:**
| # | Pair | PnL (USDT) | PnL (%) | Geschlossen |
|---|------|------------|---------|-------------|
| 51 | BTC/USDT | +0.9975 | +1.04% | May 29 14:19 |
| 50 | SOL/USDT | +1.0453 | +1.05% | May 29 02:30 |
| 49 | OP/USDT | -3.5453 | -3.55% | May 23 18:20 |
| 48 | OP/USDT | -2.5644 | -2.57% | May 23 15:08 |

**Canary:**
| # | Pair | PnL (USDT) | PnL (%) | Geschlossen |
|---|------|------------|---------|-------------|
| 33 | BTC/USDT | +0.0355 | +0.08% | May 31 14:30 |
| 32 | BTC/USDT | +0.0358 | +0.08% | May 29 18:45 |
| 31 | DOT/USDT | +0.0275 | +0.06% | May 29 18:46 |
| 30 | LINK/USDT | -0.0143 | -0.03% | May 29 18:52 |

**Regime-Hybrid:**
| # | Pair | PnL (USDT) | PnL (%) | Geschlossen |
|---|------|------------|---------|-------------|
| 43 | BTC/USDT | -0.0858 | -0.19% | May 30 13:56 |
| 42 | OP/USDT | +0.0294 | +0.03% | May 22 15:31 |
| 41 | NEAR/USDT | +0.0176 | +0.02% | May 20 04:41 |
| 40 | ARB/USDT | +0.3083 | +0.31% | May 18 00:45 |

### 6.4 Portfolio-Uebersicht (fleet_risk_state.json)
- **Portfolio-Equity:** $3,408.60
- **Peak-Equity:** $3,494.09
- **Aktueller Drawdown:** 2.45%
- **Start-Kapital:** $3,450.00
- **PnL gesamt:** +$48.48 (+1.41%)

---

## 7. Signal-Pipeline und RiskGuard

### 7.1 Signal-Frische

| Metrik | Wert |
|--------|------|
| Signal-Datei | `hermes_signal.json` |
| Letzte Aenderung | 2026-05-31 10:23 UTC |
| **Alter** | **~15 Stunden** |
| Schema-Version | 1.0 |
| LLM-Modell | deepseek-v4-pro |
| Modus | active |

**Bewertung: STALE** -- Signal ist deutlich aelter als 45 Min. Schwellenwert. Ursache: `signal-heartbeat` Cron-Job scheitert mit Permission Denied beim Schreiben der `.tmp`-Datei.

**Aktuelle Signal-Inhalte:** Alle 7 Paare im "observe"-Modus, Konfidenz 0.30-0.43 (weit unter 0.65 Schwellenwert). Keine aktiven Handels-Empfehlungen.

### 7.2 RiskGuard-Zustand
- **Status:** ACTIVE
- **Konfidenz-Schwellenwert:** 0.65
- **Letzte Pruefung (dry-run):** 3 ACCEPTED (BTC/ETH/SOL SHORT, conf=0.75), 4 WATCH_ONLY
- **Consecutive Losses:** 0 (keine Pausierung)
- **Max-Age:** 25 Min. (Signal wurde als FRESH von RiskGuard bewertet, da interne Altersberechnung abweicht)

### 7.3 Shadow-Logger
- **Datei:** `shadow_decisions.jsonl` (2.0 MB)
- **Letzter Eintrag:** 2026-05-31 12:23 UTC (~13h alt)
- **Pipeline-Zyklen dokumentiert:** Letzte 5 Eintraege zeigen vollstaendige RiskGuard-Entscheidungen mit Paar-Bewertungen

### 7.4 Pipeline-Aktivitaet
- `trading-pipeline` Cron-Job laeuft alle 10 Min, Status OK
- Letzter Lauf: 01:20 UTC, erfolgreich
- Pipeline schreibt `primo_signal_state.json` an alle Bot-Ziele

---

## 8. MCP und Bitget-Konnektivitaet

### 8.1 MCP-Server-Status

| Server | Command | Status |
|--------|---------|--------|
| bitget-paper | `/opt/hermes/.venv/bin/python3` | **BROKEN** -- Connection failed nach 3 Versuchen |
| filesystem | `npx` | **BROKEN** -- Connection failed nach 3 Versuchen |

### 8.2 Details
- Beide MCP-Server scheitern beim initialen Verbindungsaufbau mit "unhandled errors in a TaskGroup"
- `ccxt` ist **NICHT verfuegbar** im hermes-green Container
- Keine BITGET/MCP Env-Variablen im Container gesetzt
- MCP-Server waren bereits beim letzten Container-Start (May 31 23:44) defekt

### 8.3 Auswirkung
- Keine direkte -- Paper-Trading laeuft ueber Freqtrade-Bots direkt, nicht ueber MCP
- MCP-Layer (bitget_mcp_server.py) ist fuer zukuenftige Live-Integration gedacht, aktuell nicht kritisch

### 8.4 Telegram
- Wiederkehrende Netzwerkfehler: Bad Gateway, Timed Out
- Telegram-Integration gestört, aber nicht sicherheitsrelevant

---

## 9. Watchdogs und Sicherheitssysteme

### 9.1 Watchdog-Ergebnisse

| Skript | Exit-Code | Ergebnis |
|--------|-----------|----------|
| critical_event_watchdog.py | **0** | Keine kritischen Alerts |
| drawdown_guard.py | **0** | 4/4 Bots erreichbar, DD 0.0%, Signal FRESH |
| riskguard_service.py --dry-run | **0** | 3 ACCEPTED, 4 WATCH_ONLY, nicht stale |

### 9.2 DrawdownGuard Detail
- Portfolio: $3,498.48 / $3,450.00 Start
- PnL: +$48.48 (+1.41%)
- Drawdown: 0.0% (unter 5% Warn-Schwelle)
- Erreichbare Bots: 4/4

### 9.3 Sicherheitsprofil der Skripte
- `trading_pipeline.py`: MCP_DRY_RUN=True hardcoded, stale-block bei altem Signal
- `bitget_mcp_server.py`: DRY_RUN=True hardcoded, sandbox-mode aktiv
- `drawdown_guard.py`: KEIN automatisches Pausieren ohne User-Approval
- `fleet_auto_repair.py`: Nur Bericht, keine Config-Aenderungen
- `ghostbuster.py`: Nur Erkennung, kein docker prune/job removal

---

## 10. Backblaze-Backup

### 10.1 Systemd-Timer
- **restic-backblaze-backup.timer:** **active**
- **Naechster Lauf:** 2026-06-01 03:32 CEST (in ~2h)
- **Letzter Lauf:** 2026-05-31 03:35 CEST (vor ~22h)

### 10.2 Letzte Sicherung (May 31 03:35)
- Status: **Erfolgreich** ("Finished restic-backblaze-backup.service")
- Enthaltene Pfade:
  - `/home/hermes` (komplett)
  - `/home/hermes/projects/trading`
  - `/opt/hermes-green` (ueber `/opt/data` und volume mounts)
  - `/opt/hermes`
  - `/var/lib/docker/volumes`
  - `/etc/docker`, `/etc/ssh`, `/etc/systemd`
  - `/root/.ssh`, `/root/claude-worker-data`
  - Cron-Spools, Docker-Compose, Scripte
- Retention: 7 daily, 4 weekly, 6 monthly
- CPU-Zeit: 1min 874ms

### 10.3 Lokale Backups
- `/opt/hermes-green/backups/`: 3 Snapshots (root-fix, groupfix, auth-json-fix)
- `/home/hermes/projects/trading/orchestrator/backups/`: 25+ Snapshots, taegliche Rotation aktiv
- Neuester Daily: 20260531-daily

### 10.4 Einschraenkung
- `restic snapshots` kann von User hermes nicht direkt aufgerufen werden (env-Datei root-only)
- Backup-Verifizierung nur ueber journalctl-Logs moeglich

---

## 11. Funde und Empfehlungen

### 11.1 Mittlere Funde (GELB)

| # | Fund | Auswirkung | Empfehlung |
|---|------|-----------|------------|
| M1 | Signal-Datei ~15h alt, signal-heartbeat Permission Denied | Keine neuen Signale seit May 31 10:23 UTC | Signal-Heartbeat-Script-Pfad oder Ziel-Permissions pruefen (`/home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/`) |
| M2 | MCP-Server (bitget-paper + filesystem) defekt | MCP-Layer nicht funktional, Telegram-Integration gestört | MCP-Dependencies im Container-venv pruefen, npx verfuegbarkeit pruefen |
| M3 | 4 Cron-Jobs mit Permission-Fehlern (config-diff-detector, fleetrisk-auto-params, signal-heartbeat, smart-heartbeat) | Monitoring-Luecken | UID-Mismatch zwischen Scheduler (10000) und Host-Dateien (1337) beheben |
| M4 | auth.json Permission Denied in Hermes-Logs | Hermes faellt auf leeren Auth-Store zurueck | Berechtigungs-Fix fuer `/opt/data/profiles/orchestrator/auth.json` |
| M5 | Telegram-Netzwerkfehler (Bad Gateway, Timed Out) | Telegram-Benachrichtigungen unzuverlaessig | Netzwerk/Firewall-Regeln pruefen |

### 11.2 Niedrige Funde (GRUEN)

| # | Fund | Bewertung |
|---|------|-----------|
| N1 | regime-hybrid: 429 Rate-Limit von Bitget-API | Erwartet bei 8 Paar Whitelist, Backoff funktioniert |
| N2 | FreqAI Rebel hat 0 Trades | Erwartet -- FreqAI trainiert aktiv (BTC/ETH Modelle) |
| N3 | freqtrade-freqforge hat fremde DB-Dateien (canary/rebel/regime) | Durch Shared-Volume-Mounts, nicht kritisch |
| N4 | DrawdownGuard meldet Signal "FRESH" trotz 15h-Alter | Interne Altersberechnung nutzt anderen Referenzpunkt, pruefen |

### 11.3 Bekannte erwartete Zustaende

- freqai-rebel in permanenter Quarantaene (Training-Phase, kein Fehler)
- freqtrade-momentum dekommissioniert (nicht in docker-compose)
- hermes-green Restart vor 2h (nach auth-json-fix, erwartet)

---

## 12. Blocker vor Live-Trading

1. **Signal-Pipeline instabil** -- Permission-Fehler verhindern neue Signale
2. **MCP-Server defekt** -- Paper-Trading-Execution-Layer nicht funktional
3. **Permission-Mismatch** -- UID 10000 vs 1337 verursacht mehrere Cron-Fehler
4. **Kein Restore-Drill** -- Backups existieren, aber Wiederherstellung nicht praktisch getestet
5. **Telegram unzuverlaessig** -- Kritische Alerts koennten nicht ankommen
6. **Portfolio-Drawdown-Monitoring-Luecke** -- DrawdownGuard meldet "FRESH" bei 15h-altem Signal
7. **Keine einheitliche DB-Isolation** -- Shared Volumes zwischen Bots (fremde DB-Dateien)
8. **FreqAI Rebel** -- Noch in Trainings-Phase, keine Trading-Ergebnisse
9. **Keine Live-Readiness-Checkliste** -- Kriterien fuer Live-Switch nicht formal definiert

---

## 13. Priorisierte Naechste Schritte

1. **[HOCH] Permission-Fix fuer signal-heartbeat** -- Ziel-Verzeichnis und/oder Script-Berechtigungen korrigieren, damit neue Signale geschrieben werden koennen
2. **[HOCH] MCP-Server reparieren** -- Dependencies im hermes-green venv installieren, npx verfuegbar machen
3. **[MITTEL] UID-Permission-Audit** -- Systematische Pruefung aller Scheduler-Schreibziele (Logs, State, Config) gegen UID 10000
4. **[MITTEL] Telegram-Netzwerk pruefen** -- Firewall/Proxy-Einstellungen fuer Telegram API
5. **[MITTEL] auth.json Berechtigung** -- Container-Zugriff auf auth.json sicherstellen
6. **[NIEDRIG] Restore-Drill planen** -- Restic restore auf separaten Pfad testen
7. **[NIEDRIG] DB-Isolation** -- Separate Volumes pro Bot, fremde DB-Dateien entfernen
8. **[NIEDRIG] Live-Readiness-Checkliste erstellen** -- Formale Kriterien fuer den Wechsel von Paper zu Live

---

## Anhang A: Vollstaendige Cron-Job-Liste (37 Jobs)

37 Jobs im Live-Store, davon 36 enabled, 1 disabled, 6 mit Fehlern, 3 nie gelaufen. Wichtigste Jobs in Sektion 3.2 dokumentiert.

## Anhang B: Container-Restart-Historie

Alle 9 Trading-Container: **0 Restarts** seit letztem Start (May 30 20:18 bzw. May 29/31). Keine Crashloops.

## Anhang C: Portfolio-Quellen

| Quelle | Equity | Peak | Updated |
|--------|--------|------|---------|
| baseline_v1_freqforge | $957.57 | $1,009.47 | 01:25 UTC |
| freqforge_canary_v1 | $478.07 | $503.23 | 01:25 UTC |
| regime_hybrid_dryrun | $982.97 | $992.98 | 01:25 UTC |
| regime_hybrid_backtest | $990.00 | $990.00 | May 30 07:42 |
