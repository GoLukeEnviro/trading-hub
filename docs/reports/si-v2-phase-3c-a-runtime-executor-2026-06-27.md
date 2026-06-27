# SI-v2 Phase 3C-A — Runtime Executor

**Date:** 2026-06-27
**Branch:** `feat/si-v2-runtime-executor`
**PR:** #381 (merged)
**Status:** Implemented — execute=False default, hard L3 gate, no real restart in this sprint

## Summary

Phase 3C-A implements the **Runtime Executor** for the SI-v2 controlled restart chain. It completes the architecture:

```
execute_apply() → RestartPlan → RestartGate → CanaryRecreatePlan → ComposePreview
                                                                        ↓
                                                              run_canary_restart_with_overlay()
                                                                        ↓
                                                                EXECUTED_GREEN / RED
```

## Architecture

```
run_canary_restart_with_overlay()
  │
  ├─ 1. execute=False? → BLOCKED (default, safe)
  ├─ 2. Wrong L3 token? → BLOCKED
  ├─ 3. Execution gates fail? → BLOCKED (wrong bot, not ready, invalid command)
  ├─ 4. Write compose override file to orchestrator state dir
  ├─ 5. Run: docker compose -f docker-compose.yml -f override.yml up -d <service>
  ├─ 6. Run RuntimeEffectProof (verify_runtime_effect)
  └─ 7. Return EXECUTED_GREEN / EXECUTED_RED / EXECUTED_YELLOW
```

## Module: `runtime_executor.py`

| Function | Responsibility |
|----------|---------------|
| `run_canary_restart_with_overlay()` | Main entry point — all 6 execution gates + compose + proof |
| `write_compose_override_file()` | Renders and writes compose override YAML to disk |
| `_run_compose_recreate()` | Runs `docker compose up -d` (mockable via `_subprocess_run`) |
| `_run_runtime_effect_proof()` | Calls `verify_runtime_effect()` after restart |
| `_check_execute_flag()` | G1: execute must be True |
| `_check_token()` | G2: L3 token must match |
| `_check_execution_bot()` | G3: must be canary |
| `_check_restart_gate_ready()` | G4: gates must be green |
| `_check_proposed_command()` | G5: must contain overlay |
| `_check_rollback_ready()` | G6: rollback command present |

## Execution Gates (6 gates)

| Gate | Check | BLOCKED when |
|------|-------|------------|
| G1 | `execute_flag_enabled` | execute=False (default) |
| G2 | `token_matches` | token != APPROVE |
| G3 | `bot_is_canary` | bot_id != canary |
| G4 | `restart_gate_ready` | restart_gate_ready=False |
| G5 | `proposed_command_valid` | no --config with overlay_ |
| G6 | `rollback_command_ready` | rollback command empty |

## Status Values

| Status | Meaning |
|--------|---------|
| `BLOCKED` | Pre-condition failed (execute=False, wrong token, etc.) |
| `EXECUTED_GREEN` | Compose recreate + runtime proof GREEN |
| `EXECUTED_RED` | Compose ran but proof failed (rollback needed) |
| `EXECUTED_YELLOW` | Compose ran but proof inconclusive |

## Tests (23)

| # | Test | Status |
|---|------|--------|
| 1 | execute=True passes flag check | ✅ |
| 2 | execute=False blocks | ✅ |
| 3 | Correct token passes | ✅ |
| 4 | None token blocks | ✅ |
| 5 | Wrong token blocks | ✅ |
| 6 | Canary bot passes | ✅ |
| 7 | Wrong bot blocks | ✅ |
| 8 | Gate ready passes | ✅ |
| 9 | Gate not ready blocks | ✅ |
| 10 | Valid proposed command passes | ✅ |
| 11 | No overlay in command blocks | ✅ |
| 12 | Rollback ready passes | ✅ |
| 13 | Empty rollback blocks | ✅ |
| 14 | Compose override file is written | ✅ |
| 15 | Override file contains proposed command | ✅ |
| 16 | Override file contains no secrets | ✅ |
| 17 | Compose mock success | ✅ |
| 18 | Compose mock failure | ✅ |
| 19 | Docker unavailable handled | ✅ |
| 20 | execute=False → BLOCKED integration | ✅ |
| 21 | Wrong token → BLOCKED integration | ✅ |
| 22 | No subprocess when execute=False | ✅ |
| 23 | Execution result to_dict serializable | ✅ |

## Overall Test Status

| Module | Tests | Status |
|--------|-------|--------|
| `restart_with_overlay.py` (Phase 3B-A) | 45 | ✅ |
| `restart_gate.py` (Phase 3B-B) | 23 | ✅ |
| `runtime_executor.py` (Phase 3C-A) | 23 | ✅ |
| **Total** | **91** | **All GREEN** |

## Next Step

**Phase 3C-B: Erster echter L3 Canary Restart.** Voraussetzungen:
1. Luke gibt `APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY` Token frei
2. Overlay-Datei existiert (via `execute_apply()`)
3. `RestartPlan` und `RestartGate` sind GREEN
4. `run_canary_restart_with_overlay(execute=True, token=APPROVE)` wird aufgerufen
5. Container wird kontrolliert recreatet
6. RuntimeEffectProof bestätigt GREEN
7. Measurement kann starten
