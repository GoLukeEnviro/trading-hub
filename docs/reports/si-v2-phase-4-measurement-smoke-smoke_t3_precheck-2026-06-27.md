# SI-v2 Phase 4 — Measurement Snapshot: SMOKE_T3_PRECHECK

**Date:** 2026-06-27T21:16:38.382464+00:00
**Label:** SMOKE_T3_PRECHECK
**Official:** False
**Smoke:** True
**Candidate:** max_open_trades_3_to_2
**Target Bot:** freqtrade-freqforge-canary

## RuntimeEffectProof

| Check | Result |
|-------|--------|
| Runtime proof status | GREEN |
| max_open_trades | 2 |
| dry_run | True |
| Container healthy | True |
| Open trades | 0 |
| Closed trades | 59 |
| Profit (abs) | 3.98 USD |
| Errors since last | 0 |
| Warnings since last | 12 |

## Decision Engine

| Field | Value |
|-------|-------|
| Safety verdict | YELLOW |
| Full decision | YELLOW/EXTEND_MEASUREMENT |
| Reason | YELLOW: 12 warning(s) since last snapshot |
| Next step | Continue measurement. Monitor warnings. Do not rollback or apply. |

## Safety

- rollback_required: False
- No apply, restart, or rollback executed
