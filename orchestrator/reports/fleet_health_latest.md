# Fleet Healthcheck Report

## Summary

- **Verdict:** GREEN
- **Checked At:** 2026-05-08T21:32:05.164237+00:00
- **Shared Helper:** ✅ Exists
- **Total Bots:** 3

## Bot Status

| Bot | Container | Running | Dry-Run | Credentials | Strategy | State File | Verdict |
|-----|-----------|---------|---------|-------------|----------|------------|---------|
| rsi | freqtrade-rsi | ✅ | ✅ | absent/absent | ✅ | ✅ | GREEN |
| momentum | freqtrade-momentum | ✅ | ✅ | absent/absent | ✅ | ✅ | GREEN |
| regime-hybrid | freqtrade-regime-hybrid | ✅ | ✅ | absent/absent | ✅ | ✅ | GREEN |


## Verdict Legend

| Verdict | Meaning |
|---------|---------|
| GREEN | All bots safe, dry_run, no credentials |
| YELLOW | Minor issues (state file missing, but bot safe) |
| ORANGE | Concerns (stale RiskGuard, API unreachable) |
| RED | Critical (dry_run=false, credentials present, container down) |

---

**Generated:** 2026-05-08T21:32:05.164237+00:00  
**Fleet Healthcheck Version:** v0.1.0
