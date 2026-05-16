# Signal Staleness Audit — Runbook

**Typ:** Read-Only Audit
**Zweck:** Signal freshness prüfen ohne Eingriff in Runtime oder Cron

---

## Constraints (non-negotiable)

- Keine Cron-Änderungen
- Kein Service-Restart
- Keine Signal-Regenerierung
- Keine Docker-Änderungen
- Read-Only Inspection nur

---

## Audit Steps

### 1. Signal File Timestamps

```bash
# ai-hedge-fund-crypto output
stat /home/hermes/projects/trading/ai-hedge-fund-crypto/output/hermes_signal.json

# Shared signal bridge state
stat /home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json

# Latest signal symlink
stat /home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json
```

### 2. Cron Job Inspection

```bash
# List signal-related cron jobs
hermes cron list

# Read job config for signal generation
jq '.[] | select(((.prompt // "") + " " + (.title // "")) | test("signal|hedge|ai-hedge"; "i"))' ~/.hermes/cron/jobs.json
```

### 3. Container Health

```bash
# Check ai-hedge-fund-crypto container status
docker ps -a --filter "name=ai-hedge-fund-crypto"

# Check Freqtrade containers
docker ps -a --filter "name=freqtrade"
```

---

## Decision Matrix

| Signal Age | Classification | Action |
|------------|---------------|--------|
| < 45 min | FRESH | Kein Handlungsbedarf |
| 45 min – 2h | STALE | Monitoring erhöhen, Ursache prüfen |
| > 2h | CRITICAL | Eskalation — operative Entscheidung erforderlich |
| File Missing | MISSING | Sofortige Eskalation |
| Cannot Verify | UNVERIFIED | Annahme: STALE, behandeln als kritisch |

---

## Escalation Criteria

Vor jeder operativen Maßnahme (Cron-Änderung, Service-Restart, Signal-Neugenerierung):

1. Beweise dokumentieren (Timestamps, Exit-Codes, Error-Logs)
2. Luke über Telegram informieren
3. Geplante Aktion + Zeitrahmen nennen
4. Explizite Freigabe abwarten

**Kein Eingriff ohne Freigabe.**

---

## Referenz

- Signal Core: `ai-hedge-fund-crypto`
- Bridge: `primo_signal.py`
- Operational State: `docs/state/current-operational-state.md`