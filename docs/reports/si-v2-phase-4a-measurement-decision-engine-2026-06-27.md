# SI-v2 Phase 4A — Measurement Decision Engine

**Date:** 2026-06-27
**Branch:** `feat/si-v2-measurement-decision-engine`
**Candidate:** `max_open_trades 3→2`
**Status:** Implemented — read-only decision layer

## Context

Der erste runtime-bewiesene Canary Apply (`max_open_trades 3→2`) ist in der Measurement Phase (T0 erfasst, T1/T2/T3 laufen). Was fehlte, war ein harter Entscheidungsapparat, der T0/T1/T2/T3 in KEEP / ROLLBACK / EXTEND / INVESTIGATE übersetzt.

## Decision Engine

Modul: `self_improvement_v2/src/si_v2/measurement/decision_engine.py`

| Funktion | Aufgabe |
|----------|---------|
| `evaluate_measurement_safety()` | Prüft Runtime/Safety-Gates: dry_run, max_open_trades, container health, proof status |
| `compare_canary_to_control()` | Berechnet Deltas + Gaps zwischen Canary und Control-Bot |
| `decide_measurement_point()` | Bewertet T1/T2/T3 einzeln (Stabilität → Wirkung → Final) |
| `decide_final_measurement()` | Bewertet gesamte T0..T3 Sequenz |

## Verdict-Regeln

| Status | Bedingung | Decision |
|--------|-----------|----------|
| GREEN | Safety OK + Runtime Proof GREEN | CONTINUE_MEASUREMENT / KEEP_CANARY_OVERLAY |
| YELLOW | Keine Trades, Warnings, unvollständige Daten | CONTINUE_MEASUREMENT / EXTEND_MEASUREMENT |
| RED | dry_run=false, falscher max, Container down | ROLLBACK_CANARY_OVERLAY |

## Safety Boundaries

- **Rein read-only** — keine subprocess, kein Docker, kein Apply, kein Restart
- **Kein Import** von `run_canary_restart_with_overlay()` oder `execute_apply()`
- **Kein Runtime-Mutationspfad** im Modul

## Test Evidence

```bash
cd self_improvement_v2 && PYTHONPATH=src python -m pytest \
  tests/test_measurement_decision_engine.py \
  tests/test_restart_with_overlay_plan.py \
  tests/test_restart_gate_compose_plan.py \
  tests/test_runtime_executor.py \
  -q
```

| Test Suite | Tests | Status |
|-----------|-------|--------|
| `test_measurement_decision_engine.py` | 37 | ✅ |
| `test_restart_with_overlay_plan.py` | 45 | ✅ |
| `test_restart_gate_compose_plan.py` | 23 | ✅ |
| `test_runtime_executor.py` | 23 | ✅ |
| **Total** | **128** | **All GREEN** |

## Next Step

**T1 um 19:27Z abwarten, dann via Decision Engine auswerten.** Kein Apply, kein Restart, kein Rollback bis T3.
