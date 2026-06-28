# SI-v2 Phase 5B — Rollback Executor Boundary

## Status
GREEN

## Context
- Candidate: `max_open_trades_3_to_2`
- Target: `freqtrade-freqforge-canary`
- Current runtime: `max_open_trades=2`, `dry_run=true`, RuntimeEffectProof GREEN
- Measurement state: T0 GREEN, T1 YELLOW, T2 YELLOW, T3 pending at 2026-06-28T18:27Z
- Why rollback executor boundary matters: Falls T3 RED wird, darf kein hektischer Ad-hoc-Rollback gebaut werden. Der Executor Boundary stellt sicher, dass ein Rollback nur mit canary-only, dry-run-only, candidate-spezifischem L3-Token und safety_red/luke_override durchgeführt werden kann.

## Implementation

### RollbackExecutionPlan
- `candidate_id`, `target_bot`, `canary_only`, `dry_run_only`
- `rollback_source`, `restore_mode` (4 Literal-Werte)
- `expected_parameter`, `current_value`, `rollback_value`
- `pre_rollback_snapshot_path`, `post_rollback_proof_path`, `audit_path`
- `command_preview` (tuple of strings, never executed)
- `blocked_reasons`
- `to_dict()` serialization

### RollbackExecutionGate
- `allowed`, `candidate_id`, `target_bot`
- `requires_l3_approval`, `l3_approval_present`
- `safety_red_required_or_luke_override`
- `dry_run_confirmed`, `canary_confirmed`, `rollback_plan_valid`
- `blocked_reasons`
- `to_dict()` serialization

### RollbackExecutionResult
- `status`: `READY_FOR_L3_ROLLBACK` / `BLOCKED` / `NOT_EXECUTED` / `EXECUTION_NOT_ALLOWED_IN_PHASE_5B`
- `plan`, `gate`, `audit_record`, `next_step`
- `to_dict()` serialization

### Functions
- `build_rollback_execution_plan()` — baut Plan aus RollbackRehearsal-kompatiblem Objekt
- `check_rollback_execution_gate()` — prüft alle 5 Gates (canary, dry_run, plan_valid, safety_red/luke, L3-token)
- `execute_canary_rollback_boundary()` — Boundary-Entry-Point, `execute=True` hard-blocked
- `render_rollback_execution_audit()` — Markdown-Audit ohne Secrets

## Safety Boundaries
- **canary-only**: Nur `freqtrade-freqforge-canary` akzeptiert
- **dry-run-only**: `dry_run_required` muss im RollbackPlan bestätigt sein
- **L3 candidate-specific token**: `APPROVE_ROLLBACK_<candidate_id>_CANARY` — generisches `APPROVE` blockiert
- **safety_red or luke_override required**: Ohne beides → BLOCKED
- **execute=True disabled in Phase 5B**: Gibt `EXECUTION_NOT_ALLOWED_IN_PHASE_5B` zurück
- **No runtime mutation**: Kein subprocess, kein Docker, kein os.system

## Test Evidence
- pytest command: `PYTHONPATH=src python -m pytest tests/test_rollback_executor.py -q`
- test count: 33 tests (24 required + 9 additional coverage)
- result: **ALL GREEN**
- Full suite (4 test files): **ALL GREEN** (rollback_rehearsal, rollback_executor, final_decision_pack, snapshot_runner)

## Current Rollback Readiness
- ready_for_l3_rollback: ✅ YES (gate passed, plan valid, token correct)
- execution_performed: false
- blocked_reasons: (none — gate passes with safety_red + valid token)

## Next Step
Wait for `2026-06-28T18:27Z` T3 measurement. If T3 RED → use this executor boundary to prepare Phase 5C rollback approval prompt. If T3 GREEN/YELLOW → proceed with KEEP/EXTEND decision.
