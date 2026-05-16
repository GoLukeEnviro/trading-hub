# Trading Hub Autopilot Report

**Generated:** 2026-05-16T19:02:15Z
**Overall Status:** **GREEN**

## Signal Layer

| Check | Result |
|-------|--------|
| Signal File | Present |
| Signal Age | 3.5 min |
| Signal Status | GREEN |
| Heartbeat | ok |
| BTC/USDT:USDT | hold conf=0.03 |
| ETH/USDT:USDT | hold conf=0.08 |
| SOL/USDT:USDT | hold conf=0.09 |

## Fleet Status

| Bot | Color | Container | Strategy | Trades | Profit | Open | Detail |
|-----|-------|-----------|----------|--------|---------|------|--------|
| freqtrade-freqforge | GREEN | Up 5 days | FreqForge_Override | 18 | 2.9493 | 2 | |
| freqtrade-freqforge-canary | GREEN | Up 27 minutes | FreqForge_Override | 0 | 0.0000 | 0 | |
| freqtrade-regime-hybrid | GREEN | Up 4 days | RegimeSwitchingHybrid_v7_v04_Integration | 39 | -7.3707 | 0 | |
| freqtrade-momentum | GREEN | Up 21 minutes | MomentumBG15_v1 | 13 | -10.1428 | 0 | |
| freqai-rebel | GREEN | Up 18 minutes | RebelLiquidation | 0 | 0.0000 | 0 | |
| ai-hedge-fund-crypto | GREEN | Up 4 days (healthy) | N/A | ? | ? | ? | |

## Special Checks

| Check | Status |
|-------|--------|
| Momentum Entries Halted | YES |
| Rebel Total Trades | 0 |

## Approval Required

- [MEDIUM] **freqai-rebel**: increase_DI_threshold_to_2_0 — 0 trades — consider further DI threshold increase

---
*Autopilot v0 — read-only monitor*
## Daily Summary

**Date:** 2026-05-16

### Fleet Health at a Glance

- 6/6 containers GREEN
- Signal: GREEN
- Momentum entries blocked: Yes
- Rebel trades: 0

### Pending Approvals
- [MEDIUM] freqai-rebel: increase_DI_threshold_to_2_0

---
*Daily report — 2026-05-16T19:02:18Z*