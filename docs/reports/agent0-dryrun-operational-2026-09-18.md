# Agent0 — Dry-Run-Flotte im Betrieb (Inbetriebnahme-Nachweis)

**Datum:** 2026-09-18 · **Host:** Agent0 (`agent0-1`, Hetzner instance-id `125365346`, tailnet `100.103.203.107`)
**Issue:** #730 (Abschluss Inbetriebnahme) · **Klasse:** A2 (Dry-Run-Runtime, autorisiert ohne Live-Trading)
**Deployter Commit:** `ea194e6` (`origin/main`, lokaler Checkout == origin/main)

> Dieser Report belegt den **tatsächlichen laufenden Betrieb** auf Agent0. Er ersetzt keine
> Vorbereitungs- oder Staging-Dokumente: `docs/reports/agent0-staging-verification-2026-09-17.md`
> bleibt gültig (Transfer + Images), `docs/reports/agent0-takeover-plan-2026-09-16.md` bleibt die
> Planungsreferenz. Alle Zahlen unten stammen aus frischen Messungen nach dem Deployment.

---

## 1. Ergebnis

`TRADING_HUB_DRYRUN_OPERATIONAL` — die Default-Flotte läuft auf Agent0:

| # | Dienst | Image-ID (== Lock) | Status | RestartCount | Funktion |
|---|---|---|---|---|---|
| 1 | `freqtrade-freqforge` | `aa4ab785…d380` | **Up (healthy)** | 0 | Trading-Bot, dry_run, `127.0.0.1:8086→8080` |
| 2 | `freqtrade-freqforge-canary` | `aa4ab785…d380` | **Up (healthy)** | 0 | Trading-Bot, dry_run, `127.0.0.1:8081→8080` |
| 3 | `freqtrade-regime-hybrid` | `aa4ab785…d380` | **Up (healthy)** | 0 | Trading-Bot, dry_run, `127.0.0.1:8085→8080` |
| 4 | `freqtrade-webserver` | `aa4ab785…d380` | **Up (healthy)** | 0 | Webserver (UI/API, kein Bot-Loop), `127.0.0.1:8180→8080` |
| 5 | `rainbow` | `7e2fab4a…5db0` | **Up (healthy)** | 0 | TA-Collector, internal-only, keine Ports |

- `OOMKilled=false` für alle fünf; `user=10000:10000`, `cap_drop=[ALL]`,
  `no-new-privileges`, `restart=unless-stopped`, Logrotation `json-file 10m×3`.
- Kein `freqai-rebel` (profile-gated, `NOT_REPRODUCIBLE`); Registry-Eintrag bleibt
  `enabled:false` mit `disabled_reason` und wird nicht als aktiver Bot gezählt.
- `freqtrade-freqforge`-Referenzbot zuerst gestartet und vollständig verifiziert
  (authentifizierte API, `dry_run=True`, Balance 1000 USDT, DB `integrity ok`,
  `last_process` fortschreitend), danach die übrigen vier.

## 2. Effektiver Dry-Run-Nachweis (drei Trading-Bots)

| Bot | `dry_run` (API) | Runmode | State | Offene Trades | Auth | API-Bindung |
|---|---|---|---|---|---|---|
| `freqtrade-freqforge` | **True** | dry_run | running | 0 | `AUTHENTICATED` (200) | nur `127.0.0.1:8086` |
| `freqtrade-freqforge-canary` | **True** | dry_run | running | 0 | `AUTHENTICATED` (200) | nur `127.0.0.1:8081` |
| `freqtrade-regime-hybrid` | **True** | dry_run | running | 0 | `AUTHENTICATED` (200) | nur `127.0.0.1:8085` |

- Marktdaten und Strategieauswertung belegt: frische 15m/1h-Candles (BTC/USDT:USDT,
  Zeitstempel aktuell), berechnete Strategie-Spalten inkl. `v04_action=BUY`,
  `v04_regime=trending`; `last_process` aller drei Bots fortschreitend.
- Null offene Trades ist zulässig (keine Trades erzwungen); die Entscheidungs-Pipeline
  läuft nachweislich (siehe §3 `per_bot_decisions`).
- Alle vier Runtime-Configs (`user_data/config.json`, gitignoriert, Mode `600`) wurden
  mit **neuen, host-lokalen** API-Passwörtern/JWT-Secrets erzeugt; Exchange-`key`/`secret`
  bleiben leer (keine Live-Credentials). Die SI-v2-Secrets liegen außerhalb des Repos in
  `/opt/data/secrets/si-v2-freqtrade.env` (`0600`).
- Keine `0.0.0.0`-Bindung: `ss -lnt` zeigt ausschließlich `127.0.0.1` für 8081/8085/8086/8180.

## 3. SI-v2-Zyklus gegen echte Bot-Telemetrie

Mehrere vollständige read-only Zyklen über den kanonischen Wrapper
(`/opt/data/scripts/si-v2-active-cycle-runner.sh`), Ergebnis exemplarisch:

```text
cycle_id=20260918T130535Z          (automatisch ausgelöst, §4)
fleet_verdict=GREEN
fleet_verdict_reason: all 3 bots authenticated and decisions generated
ping_ok=3/3   status_authenticated=3   strategy_mutations=0
runtime_mutations=0  config_mutations=0  live_trading_mutations=0
docker_mutations=0   controller=PAUSED / L3_REPOSITORY_ONLY
rainbow_status=SUCCESS  source=read_only  count=30  errors=0
rainbow_freshness_seconds=24  rainbow_fresh=True
```

- **Keine Fixtures**: `rainbow_source=read_only`, gespeist aus der realen
  `signals.db` des laufenden Rainbow-Containers (konsistenter
  SQLite-Backup-Snapshot, siehe §6).
- Evidence-Bundle je Zyklus unter
  `self_improvement_v2/reports/phase2/evidence/active_cycle_<cycle_id>.json`,
  Cycle-State `…/cycle_state/active_cycle_latest.state.json`, Measurement-Ledger
  aktualisiert (`mutations_all_zero=True`, `secrets_found=False`).
- **Kein Proposal** in den beobachteten Zyklen → korrekt `NO_PROPOSAL` mit
  `no_proposal_reason=insufficient_signal_depth` je Bot (3×), kein
  Schwellen-Absenken, kein erzeugter Vorschlag. `AUTONOMOUS_DRY_RUN` wurde
  **nicht** aktiviert (Policy-Gates siehe §7).
- **Historische Evidenz aktiv** (AGENTS.md-Priorität 2): Nach dem Import der
  transferierten Trade-Historie in den SI-v2-Store liefert der Zyklus
  `historical_trade_window.status=OK`, `primary_verdict=GREEN` —
  292 geschlossene Trades über alle drei Bots, Coverage
  `2026-07-13 18:30 → 2026-09-17 01:28`, per-Bot-Summaries in
  `per_bot_decisions[*].historical_trade_summary`. Die Telemetrie-Evidenz
  desselben Zyklus bleibt davon unberührt (additiv, kein Ersatz).
- **Fehlerverhalten geprüft:** Canary-Endpunkt gestoppt → Zyklus meldete
  kontrolliert `fleet_verdict=YELLOW`, `ping_ok=2/3` (kein falscher PASS);
  nach Neustart wieder `GREEN 3/3`.

## 4. Scheduler — genau einer, mit echtem automatischem Lauf

- **Genau ein** SI-v2-Scheduler: Hermes-Cron-Job `5f26075be2cb`
  (`si-v2-active-cycle-agent0`, `17 */6 * * *`, `no-agent`, `deliver=telegram:610209401`).
- Kein zweiter Cron-/Systemd-Timer für denselben Zyklus; `crontab` leer, keine
  weiteren systemd-Timer; Überlappungsschutz per `flock` nachgewiesen
  (`overlap_skip=1 reason=lock_held` bei parallelem Start).
- **Echter automatischer Lauf** (kein manueller Trigger): 2026-09-18 15:05:34
  über den Gateway-Scheduler (restart-safe Worker `pid=673135`), Ergebnis
  `cycle_id=20260918T130535Z`, `rc=0`, `GREEN`, silent (kein Alert nötig).
- Reboot-Verhalten: alle fünf Container `restart=unless-stopped`, Docker-Dienst
  `enabled`; nach Reboot startet die Flotte automatisch.
- Alerting: Telegram-Zustellung verifiziert (`delivered to telegram:610209401`);
  der Job meldet bei Fleet-RED, nicht-frischem Rainbow, Mutationen ≠ 0,
  blockiertem Controller oder Ressourcen-Druck (MemAvailable < 512 MB, Disk ≥ 90%).

## 5. Backup, Restore, Wiederanlauf

- **Frischer Snapshot** (SQLite-Backup-API, kein rohes `cp`):
  `/opt/data/backups/agent0-dryrun-snapshot-20260918T125653Z` — 5 Datenbanken
  (freqforge/canary/regime-hybrid mit je 0 Trades — frischer Dry-Run-Start;
  rainbow-signals/-canonical), alle `PRAGMA integrity_check=ok`,
  `manifest.json` + `SHA256SUMS` (`0600`).
  Webserver hat keine Trade-DB (Runmode `webserver`) — dokumentiert, kein Fehler.
- **Historische Trade-Evidenz (AGENTS.md-Priorität 2) getrennt erhalten:** Die
  transferierte Historie (freqforge 74, canary 141, regime-hybrid 81 Trades;
  Stand HermesTrader) wurde aus dem Staging-Paket in den SI-v2-Store
  `self_improvement_v2/state/historical_trades/` importiert (296 Trades,
  read-only SQLite-Backfill); fehlender Rebel-DB-Eintrag ist erwartbar
  (`bots_skipped: 1`). Die frische Runtime-DB ersetzt diese Historie nicht.
- **Isolierter Restore**: `/opt/data/backups/restore-proof-20260918T125719Z` —
  `sha256sum -c` grün, alle fünf DBs lesbar und integer, Zeilenzahlen == Manifest:
  `RESTORE_PROOF=PASS`.
- **Gezielter Wiederanlauf** (`freqtrade-freqforge-canary`, `stop` → `start`):
  Trade-Zahl 0 → 0 (nicht gesunken), `integrity ok` vorher/nachher, danach
  `Up (healthy)`, API + Marktdatenverarbeitung erneut bestätigt, übrige Flotte
  unbeeinflusst (`RestartCount=0`). Kein `down -v` verwendet.
- **Offsite-Backup**: `restic-agent0-backup.timer` läuft auf Agent0
  (täglich 03:30, letzter Lauf exit 0) und erfasst u. a. `/home/hermes`,
  `/etc/*`, `/var/lib/docker/volumes` — Dry-Run-Volumes sind damit abgedeckt.

## 6. Host-seitige Ergänzungen (Runtime-only, außerhalb des Repos)

| Ergänzung | Pfad | Zweck |
|---|---|---|
| SI-v2-Wrapper (Agent0-Install) | `/opt/data/scripts/si-v2-active-cycle-runner.sh` | read-only Zyklus, identisch zum Repo-Pendant |
| Cron-Script (Agent0) | `~/.hermes/scripts/si_v2_active_cycle_agent0.sh` | flock-Schutz, Rainbow-DB-Refresh, Alert-only-Ausgabe |
| Rainbow-Hostkopie | `/opt/data/ai4trade-bot/rainbow/storage/signals.db` | konsistenter Backup-API-Snapshot aus dem Container, vor jedem Zyklus erneuert |
| SI-v2-Runtime-Env | `/opt/data/secrets/si-v2-runtime.env` | `SI_V2_REPO_ROOT=/workspace/projects/trading-hub` |

## 7. Bewusst NICHT getan (Policy-Gates)

- **`AUTONOMOUS_DRY_RUN` nicht aktiviert.** Die vorhandenen Gates sind teils
  nicht erfüllt: Host-Kill-Switch `HALT_NEW` (Testartefakt, §8) und kein
  RiskGuard-State auf Agent0 (Apply-Guard fail-closed `BLOCKED` — korrektes
  Fail-Closed-Verhalten, aber eben kein PASS). Der Controller bleibt
  `PAUSED / L3_REPOSITORY_ONLY`; es gibt keine geeignete Proposal.
- Kein `dry_run=false`, keine Live-Orders, keine Exchange-Live-Credentials,
  keine Risikolimit-Änderung, kein Kill-Switch-Eingriff, kein `down -v`.

## 8. Befunde für Folgearbeiten

1. **Kill-Switch-Testartefakt (Fix empfohlen, Folge-PR):** Der Host-Kill-Switch
   `var/kill_switch.json` steht auf `HALT_NEW` mit
   `reason="Daily drawdown 5.00% >= 5.0% (day_start=100000, equity=94999)"` und
   `triggered_by=drawdown_guard`. Ursache belegt: die SI-v2-Testsuite
   (`FleetDrawdownGuard`) schreibt über die Default-Pfadauflösung in die echte
   Datei; der Reason-String entstammt 1:1 dem Testfall
   `test_daily_loss_triggers_at_threshold`. Reproduziert mit umgeleitetem
   `KILL_SWITCH_FILE` (identischer Output); die echte Datei blieb byte-identisch
   (`sha256 c2568b19…`), sie wurde **nicht** zurückgesetzt. Die Bot-/Strategiepfade
   nutzen die Container-Sicht `/freqtrade/shared/kill_switch.json` (= `NORMAL`)
   und blockieren bei `HALT_NEW` fail-closed (im Bot-Image verifiziert).
   Empfehlung: Test-Isolation (KILL_SWITCH_FILE in Tests erzwingen), danach
   Betriebsentscheidung über den Host-Zustand.
2. **RiskGuard-State fehlt auf Agent0** (`orchestrator/state/riskguard/`): Der
   Apply-Pfad failt damit fail-closed; für spätere `AUTONOMOUS_DRY_RUN`-Schritte
   braucht es einen gültigen RiskGuard-PASS.
3. Die gestagte Compose aus dem Transferpaket ist die Revision **vor** #734;
   verwendet wurde ausschließlich die `origin/main`-Compose (`ea194e6`).

## 9. Verifikationsbefehle (Auszug)

```bash
docker compose -f /workspace/projects/trading-hub/docker-compose.hermestrader-dryrun.yml \
  -p hermestrader-dryrun ps                     # 5× Up (healthy)
python3 /workspace/projects/trading-hub/hermes_root/r5a_recovery.py verify-only
#   -> R5A_PROVENANCE_GATE=PASS
/opt/data/scripts/si-v2-active-cycle-runner.sh  # read-only Zyklus, GREEN 3/3
```

---

**Belege gesammelt:** 2026-09-18, Agent0. Keine Secrets in diesem Report.
