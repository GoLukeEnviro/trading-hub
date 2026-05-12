# Multi-Cycle Validation Report

## Summary

- **Status:** GREEN
- **Validated At:** 2026-05-08T09:20:58.318424+00:00
- **Wrapper Runs Found:** 11
- **Latest Run ID:** 20260508T091944Z

## Component Status

| Component | Status | Details |
|-----------|--------|---------|
| RiskGuard | ✅ | 7 signals, 0 ACCEPTED |
| ShadowLogger | ✅ | 70 lines logged |
| State Files | ✅ | Schema: 0.2 |
| Fleet Health | ✅ | GREEN |

## Wrapper Runs

| Run ID | Timestamp | Status | Log |
|--------|-----------|--------|-----|
| 20260508T091944Z | 2026-05-08T09:19:44Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260508T091944Z.log) |
| 20260508T061944Z | 2026-05-08T06:19:44Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260508T061944Z.log) |
| 20260508T031944Z | 2026-05-08T03:19:44Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260508T031944Z.log) |
| 20260508T001944Z | 2026-05-08T00:19:44Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260508T001944Z.log) |
| 20260507T211944Z | 2026-05-07T21:19:44Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T211944Z.log) |
| 20260507T210235Z | 2026-05-07T21:02:35Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T210235Z.log) |
| 20260507T201616Z | 2026-05-07T20:16:16Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T201616Z.log) |
| 20260507T201301Z | 2026-05-07T20:13:01Z | ❌ unknown | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T201301Z.log) |
| 20260507T195314Z | 2026-05-07T19:53:14Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T195314Z.log) |
| 20260507T185137Z | 2026-05-07T18:51:37Z | ✅ success | [log](/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T185137Z.log) |


## State Files

| Bot | Exists | Valid JSON | Schema | Pairs | Issues |
|-----|--------|------------|--------|-------|--------|
| rsi | ✅ | ✅ | 0.2 | 7 | ✅ |
| momentum | ✅ | ✅ | 0.2 | 7 | ✅ |
| regime-hybrid | ✅ | ✅ | 0.2 | 7 | ✅ |


## RiskGuard Verdict Distribution

- **ACCEPTED:** 0
- **WATCH_ONLY:** 7
- **BLOCK_ENTRY:** 0

## Fleet Health

| Bot | Verdict |
|-----|---------|
| rsi | GREEN |
| momentum | GREEN |
| regime-hybrid | GREEN |


## Known Limitations

- **BLOCK_ENTRY semantics:** Currently behaves neutral (same as WATCH_ONLY). Documented as deferred tech debt for explicit block-policy design.
- **Multi-cycle history:** Only current state validated. Repeated runs needed for drift detection.

---

**Generated:** 2026-05-08T09:20:58.318424+00:00  
**Multi-Cycle Validator Version:** v0.1.0
