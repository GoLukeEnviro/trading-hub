# Emergency Evidence Directory Convention

> **Directory:** `var/si_v2/emergency/`
> **Purpose:** Timestamped audit records for emergency stop events
> **Created:** 2026-07-03 (C3 Rollback Readiness — #443)

---

## File Naming Convention

```
emergency_<YYYYMMDD>_<HHMMSS>.json
```

Example: `emergency_20260703_041500.json`

## File Format

```json
{
  "event": "emergency_stop",
  "timestamp_utc": "2026-07-03T04:15:00Z",
  "target": "freqtrade-freqforge-canary",
  "reason": "max_drawdown breach — rollback",
  "kill_switch_mode": "EMERGENCY",
  "triggered_by": "emergency_stop.sh",
  "dry_run": false
}
```

## Lifecycle

| Event | Action |
|-------|--------|
| Emergency stop executed | Write record to `var/si_v2/emergency/` |
| Post-mortem filed | Reference record in incident report |
| Incident resolved | Records are preserved — never deleted |

## Safety Rules

- Records are **append-only** — never modify or delete existing records
- Records are **not tracked in git** (`var/` is in `.gitignore`)
- Each emergency event produces exactly one record
- The `emergency_stop.sh` script writes to this directory automatically
