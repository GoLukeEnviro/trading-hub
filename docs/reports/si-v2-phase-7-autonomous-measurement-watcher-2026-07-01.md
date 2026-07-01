# SI-v2 Phase 7 — Autonomous Measurement Watcher

## Summary

Adds the read-only autonomous measurement watcher that consumes Phase-6C T0 activation records, reads fleet evidence, emits KEEP / EXTEND / ROLLBACK decisions, and writes decision packs.

## Scope

- T0 activation record reader (validation, age check)
- Fleet evidence reader protocol (pluggable, read-only)
- Evidence snapshot validation and schema checks
- Measurement readiness rules (minimum closed trades per arm)
- Final decision emission (KEEP / EXTEND / ROLLBACK)
- Decision pack writer (JSON, fail-closed)
- No scheduler enablement
- No runtime mutation
- No rollback execution
- No live trading

## Flow

```
T0 activation record
  → validate T0 (GREEN, canary, correct component)
  → check T0 age
  → read fleet evidence (reader or file fallback)
  → validate evidence snapshot schema
  → extract canary/control data
  → check measurement readiness
  → determine final decision
  → write decision pack
```

## Decision Logic

| Decision | Condition |
|----------|-----------|
| KEEP_CANARY_OVERLAY | Canary profit >= control profit, PF not worse |
| ROLLBACK_CANARY_OVERLAY | Canary profit clearly worse + PF worse, or allow_extend=False + ambiguous |
| EXTEND_MEASUREMENT | Ambiguous evidence with allow_extend=True |

## Safety

- T0 must be CEREMONY_EXECUTED_GREEN with GREEN proof
- Canary-only (must match T0 target_bot)
- Evidence required (schema-validated)
- Missing data blocks or emits NOT_READY
- Decision pack required (fail-closed if write fails)
- Runtime mutation is NONE in all fields
- No rollback execution — only decision emission
- No scheduler or watcher enablement

## Files

- `self_improvement_v2/src/si_v2/measurement/autonomous_measurement_watcher.py` — watcher module
- `self_improvement_v2/tests/test_autonomous_measurement_watcher.py` — 29 tests
- `docs/reports/si-v2-phase-7-autonomous-measurement-watcher-2026-07-01.md` — this report
- `docs/architecture/si-v2-autonomous-dry-run-loop.md` — architecture doc update