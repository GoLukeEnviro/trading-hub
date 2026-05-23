# Fleet Healthcheck Report

## Summary

- **Verdict:** RED
- **Checked At:** 2026-05-23T17:17:48.380772+00:00
- **Shared Helper:** ✅ Exists
- **Total Bots:** 3

## Bot Status

| Bot | Container | Running | Dry-Run | Credentials | Strategy | State File | Verdict |
|-----|-----------|---------|---------|-------------|----------|------------|---------|
| rsi | freqtrade-rsi | ❌ | ✅ | absent/absent | ❌ | ✅ | RED |
| momentum | freqtrade-momentum | ❌ | ✅ | absent/absent | ❌ | ✅ | RED |
| regime-hybrid | freqtrade-regime-hybrid | ✅ | ✅ | absent/absent | ❌ | ✅ | RED |


## Verdict Legend

| Verdict | Meaning |
|---------|---------|
| GREEN | All bots safe, dry_run, no credentials |
| YELLOW | Minor issues (state file missing, but bot safe) |
| ORANGE | Concerns (stale RiskGuard, API unreachable) |
| RED | Critical (dry_run=false, credentials present, container down) |

---

**Generated:** 2026-05-23T17:17:48.380772+00:00  
**Fleet Healthcheck Version:** v0.1.0
