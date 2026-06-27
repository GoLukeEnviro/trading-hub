# SI-v2 Phase 4D — Measurement Smoke Runner

**Status:** ✅ **GREEN** — On-Demand Runner implementiert, Smoke T3 Precheck bestanden.

## Context

T0/T1/T2 wurden erfasst. T3 ist für 2026-06-28T18:27Z geplant. Die Measurement-Automation brauchte einen sofort triggerbaren, read-only On-Demand Snapshot Runner, der die T3-Erfassungslogik validiert ohne den offiziellen T3 zu kontaminieren.

## Implementation

| Komponente | Datei |
|------------|-------|
| `MeasurementSnapshotRequest` | `snapshot_runner.py` |
| `MeasurementSnapshotResult` | `snapshot_runner.py` |
| `run_measurement_snapshot()` | `snapshot_runner.py` |
| CLI `python -m si_v2.measurement.snapshot_runner` | `snapshot_runner.py` |
| Tests (18) | `test_measurement_snapshot_runner.py` |

## Safety Boundaries

- **read-only** — keine subprocess, kein Docker, kein Apply/Restart/Rollback
- **smoke=True** → Label darf kein offizielles T0..T3 sein
- **official=False** → Report-Pfad enthält `smoke-` Prefix
- **Existierende Reports werden nicht überschrieben** — `_check_report_overwrite()` blockiert
- **T3 nicht vorzeitig final entscheidbar**

## Smoke Run Evidence

```bash
python -m si_v2.measurement.snapshot_runner \
  --label SMOKE_T3_PRECHECK \
  --candidate-id max_open_trades_3_to_2 \
  --smoke --write-report
```

| Field | Value |
|-------|-------|
| Status | 🟡 YELLOW |
| RuntimeProof | GREEN |
| Decision | YELLOW/EXTEND_MEASUREMENT |
| Report | `docs/reports/si-v2-phase-4-measurement-smoke-smoke_t3_precheck-2026-06-27.md` |
| max_open_trades | 2 |
| dry_run | true |
| Blocked | None — no safety issues |

## Scheduler Readiness

| Job | Time | Status |
|-----|------|--------|
| T2 (Cron `138e8a2b637e`) | 2026-06-28T00:27Z | ✅ Scheduled |
| T3 | 2026-06-28T18:27Z | 🔴 **Cron nicht gesetzt** — muss manuell oder via separatem Job ausgelöst werden |
| On-Demand Runner | Jederzeit | ✅ Verfügbar |

**Recommendation:** T3 kann via On-Demand Runner um 18:27Z ausgelöst werden, oder via separatem Cron-Job.

## Tests

```bash
cd self_improvement_v2 && PYTHONPATH=src python -m pytest \
  tests/test_measurement_snapshot_runner.py \
  tests/test_measurement_decision_engine.py \
  tests/test_rollback_rehearsal.py \
  tests/test_candidate_to_apply_pipeline.py \
  -q
→ 115 passed (4 modules)
```

## Next Step

**T3 um 2026-06-28T18:27Z auswerten**, entweder via On-Demand Runner oder Cron. Danach Final Measurement Decision erstellen.
