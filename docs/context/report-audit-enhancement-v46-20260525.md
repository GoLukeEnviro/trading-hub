# Report Audit & Enhancement v4.6 — 2026-05-25

## Scope
Vollständige Bestandsaufnahme der aktiven Report-Jobs, Qualitätsbewertung der aktuellen Outputs und Umbau auf ein dichteres, einheitliches Operator-Format.

## Aktive Reports (live aus jobs.json / cron list)

| Name | Schedule | Erzeugende Datei/Quelle | Ziel |
|---|---|---|---|
| Fleet Report (alle 4h) | `every 240m` | LLM cron prompt | Telegram |
| System Health Check (alle 8h) | `0 */8 * * *` | LLM cron prompt | Telegram |
| trading-hub-deep-dive-validation | `0 9 * * *` | LLM cron prompt | Origin/Chat |
| quality-hub-monitor | `0 8 * * *` | `quality_hub_monitor.py` | Origin/Chat |
| drawdown-guard | `*/30 * * * *` | `drawdown_guard.py` | Telegram |
| ghostbuster | `0 */2 * * *` | `ghostbuster.py` | Telegram |
| mem0-watchdog | `0 */2 * * *` | `mem0_watchdog.py` | Telegram |
| daily-heartbeat | `0 6 * * *` | `daily_heartbeat.py` | Telegram |
| monthly-strategy-report | `0 8 1 * *` | `monthly_strategy_report.py` | Telegram |
| system-optimizer | `every 5m` | `system_optimizer.py` | Log/Local |
| Heartbeat Intelligence Report (every 6h) | `0 */6 * * *` | `heartbeat_intelligence_wrapper.py` | Log/Local |
| signal-heartbeat | `*/20 * * * *` | `ai_hedge_signal_heartbeat.sh` | Log/Local |
| smart-heartbeat | `*/10 * * * *` | `smart_heartbeat.py` | Log/Local |
| container-watchdog | `*/30 * * * *` | `container_watchdog.sh` | Telegram |
| mcp-watchdog | `*/15 * * * *` | `mcp_watchdog.sh` | Telegram |

Hinweis: `72h Research Fleet Monitor` ist pausiert und nicht Teil der aktiven Report-Oberfläche.

## Qualitätsanalyse der letzten Outputs

Zu minimal bzw. strukturell schwach vor dem Umbau:
- `quality-hub-monitor`: LLM-Job fiel mit `HTTP 429` aus; damit zugleich inhaltlich unzuverlässig.
- `monthly-strategy-report`: tabellarisch, aber nicht Telegram-optimiert und ohne Standardsektionen.
- `drawdown-guard`: Alarm-orientiert, aber Safety-Block ohne `dry_run`/`max_open_trades` Snapshot.
- ältere LLM-Reports: Risiko für zu knappe "all green" / "0 issues" Formulierungen und Halluzinationen wie `HONCHO WATCHDOG`.

Bereits brauchbar, aber harmonisiert/verstärkt:
- `daily-heartbeat`
- `mem0-watchdog`
- `ghostbuster`
- `system-optimizer` Fleet Report
- `Fleet Report`, `System Health Check`, `Deep-Dive` Prompts

## Einheitliches Report-Format
Alle relevanten Reports verwenden jetzt dieselbe Reihenfolge:
1. `PROFITABILITÄT`
2. `FLEET STATUS`
3. `SIGNAL`
4. `SAFETY`
5. `VORSCHLÄGE`

Pflichtinhalte je nach Report-Typ:
- Fleet-PnL / Drawdown / Best/Worst
- Bot-Zeilen mit `PnL`, `WR`, `PF`, `open`, Status
- Signal-Alter, Risk-Mode, ACCEPTED/WATCH_ONLY/REJECTED oder klare N/A-Begründung
- `dry_run` Snapshot
- `max_open_trades` Snapshot
- Permission/Cron/Pipeline/Quarantäne-Risiken
- maximal 2 konkrete nächste Schritte

Inline-Buttons bleiben dort aktiv, wo echte Telegram-Interaktion bereits im Skript verdrahtet ist:
- `drawdown_guard.py`
- `system_optimizer.py`

## Umgesetzte Änderungen

### 1) quality-hub-monitor 429 strukturell beseitigt
Alt:
- Agent-Job auf `zai/glm-5.1`
- letzter Live-Fehler: `RuntimeError: HTTP 429: The service may be temporarily overloaded`

Neu:
- Agent-Job entfernt
- ersetzt durch script-backed Cron: `quality_hub_monitor.py`
- neuer Job: `quality-hub-monitor` (`job_id=1c55cd5d4c6f`, `no_agent=true`, `0 8 * * *`, deliver `origin`)
- schreibt Vollreport nach `/home/hermes/projects/trading/orchestrator/logs/quality-hub-report.md`
- druckt kompakten Telegram/Origin-Report in Standardsektionen

### 2) HONCHO WATCHDOG Fail abgeriegelt
Aktualisiert in den aktiven LLM-Reportjobs:
- Fleet Report
- System Health Check
- trading-hub-deep-dive-validation
- autonomous-health-loop

Neue Guardrail in Prompts:
- Honcho ist decommissioned
- lokale Mem0/Qdrant ist einzige Memory-Referenz
- `HONCHO WATCHDOG` oder Honcho-Fehler dürfen nicht mehr erwähnt werden
- Toolsets auf `terminal,file` reduziert, `workdir=/home/hermes/projects/trading`

### 3) Skript-Reports harmonisiert
Geändert:
- `/home/hermes/projects/trading/orchestrator/scripts/quality_hub_monitor.py` (neu)
- `/home/hermes/projects/trading/orchestrator/scripts/monthly_strategy_report.py`
- `/home/hermes/projects/trading/orchestrator/scripts/drawdown_guard.py`
- `/home/hermes/projects/trading/orchestrator/scripts/system_optimizer.py`

Bereits im v4.6-Stil vorhanden/verifiziert:
- `daily_heartbeat.py`
- `mem0_watchdog.py`
- `ghostbuster.py`

Alle geänderten Skripte wurden nach `/opt/data/profiles/orchestrator/scripts/` synchronisiert und per `python3 -m py_compile` verifiziert.

## Verifikation

### quality_hub_monitor.py
Direktlauf erfolgreich. Beispielausgabe:
- Fleet `-2.08U`, Open `2`, DD `0%`
- 4 Bot-Zeilen mit `PnL / WR / PF / open / Status`
- Safety mit `dry_run`, `max_open`, `Cron`, `Permissions`, `Disk`

### monthly_strategy_report.py
Direktlauf erfolgreich. Ergebnis jetzt Telegram-tauglich statt Tabellenwüste.

### drawdown_guard.py
Formatter geprüft. Safety enthält jetzt zusätzlich:
- `dry_run ...`
- `max_open ...`
- Alert-Level in derselben kompakten Sektion

### system_optimizer.py
Cron-Fehlerlogik repariert:
- nutzt jetzt `id` oder `job_id`
- skippt `no_agent` Jobs korrekt
- erkennt `HTTP 429` als Overload/Fallback-Situation statt blindem Model-Umschreiben

### Permission-Status
`/opt/data/profiles/orchestrator/cron/jobs.json` am Ende wieder auf `root:10000 0640` normalisiert.

## Nettoeffekt
- Reports sind nicht mehr minimal, sondern operator-tauglich.
- Der unzuverlässigste Report (`quality-hub-monitor`) hängt nicht mehr am LLM-429-Pfad.
- Die Honcho/HONCHO-WATCHDOG-Altlast ist aus den aktiven Report-Prompts entfernt.
- Telegram/Origin-Outputs sind jetzt konsistenter, dichter und vergleichbarer.
