# SI-v2 Phase 5A — Rollback Rehearsal Gate

**Date:** 2026-06-27
**Branch:** `feat/si-v2-rollback-rehearsal-gate`
**Candidate:** `max_open_trades 3→2`
**Status:** Implemented — read-only rollback planning layer, no runtime mutation

## Context

Der erste runtime-bewiesene Canary Apply (`max_open_trades 3→2`) läuft im Measurement Window (T1 YELLOW/CONTINUE, T2/T3 pending). Was fehlte, war der **kontrollierte Rückweg**: ein Rollback-Rehearsal, der vor einem echten Rollback alle Gates prüft und ein Preview erzeugt.

## Rollback Rehearsal

Modul: `self_improvement_v2/src/si_v2/apply_actuator/rollback_rehearsal.py`

| Komponente | Aufgabe |
|------------|---------|
| `RollbackPlan` | Plan-Datenmodell: aktueller Command, Rollback-Command, Overlay-Pfad, Baseline-Erwartung |
| `RollbackGateResult` | 10 Gates G1–G10 |
| `RollbackPreview` | Read-only Preview des Rollback-Zustands |
| `plan_canary_rollback_from_overlay()` | Baut RollbackPlan aus aktuellem Overlay-Command |
| `check_rollback_gate()` | 10 Gates: Canary-only, dry_run, Overlay-Vorhandensein, Baseline-Match, Reason |
| `build_rollback_preview()` | Baut Preview aus Plan + Gate |
| `render_rollback_compose_preview()` | YAML-String für Compose Override (read-only) |
| `execute_canary_rollback()` | Hard-blocked (NOT_IMPLEMENTED) |

## Rollback Gates (10)

| Gate | Check | Blocked when |
|------|-------|------------|
| G1 | `plan_exists` | Plan is None |
| G2 | `bot_is_canary` | bot_id != canary |
| G3 | `current_command_contains_overlay` | Current command has no overlay --config |
| G4 | `rollback_command_removes_overlay` | Rollback command still has overlay |
| G5 | `rollback_command_keeps_base_config` | No --config in rollback command |
| G6 | `dry_run_true` | dry_run is not True |
| G7 | `current_runtime_matches_expected_before` | Runtime value != expected before (e.g. 2) |
| G8 | `expected_after_matches_baseline` | Expected after != baseline (e.g. 3) |
| G9 | `rollback_reason_present` | Reason is empty |
| G10 | `runtime_execution_still_blocked` | execution_enabled=True |

## Safety Boundaries

- **Rein read-only** — kein subprocess, kein Docker, kein Apply, kein Restart
- **Rollback bedeutet Command-Änderung, nicht Datei-Löschung**
- **Overlay-Datei wird nicht gelöscht** — nur aus dem Command entfernt
- **Measurement State (T2/T3) wird nicht berührt**
- **Kein Import** von runtime_executor-mutierenden Funktionen

## Test Evidence

```bash
cd self_improvement_v2 && PYTHONPATH=src python -m pytest \
  tests/test_rollback_rehearsal.py -q
→ 24 passed
```

Gesamt: 24/24 Tests, Ruff clean.

## Next Step

**Rollback Rehearsal PR erstellen und mergen.** Nach Merge: T2 auswerten (00:27Z).
