# SI-v2 Autonomous Dry-Run Loop Architecture

## Overview

The SI-v2 loop operates in **AUTONOMOUS_DRY_RUN** mode by default. This means
qualified ShadowProposals may be applied automatically in dry-run when all
policy gates pass — no per-iteration human approval required.

## Loop Flow

```
Active Cycle
  → Candidate Selection
  → Autonomy Policy (policy-gated)
  → Phase 6B Executor (prepares overlay, rollback, audit, measurement plan)
  → Runtime Ceremony (separate task — Docker restart, compose)
  → Runtime Proof
  → Measurement
  → Final Decision (KEEP / EXTEND / ROLLBACK)
  → Auto next iteration
```

## Phase 6B Executor

The executor (`self_improvement_v2/src/si_v2/pipeline/autonomous_dry_run_executor.py`)
converts `AUTO_DRY_RUN_APPROVED` policy decisions into prepared canary dry-run
apply artifacts:

- **Overlay** — parameter change JSON file
- **Rollback plan** — snapshot of pre-apply config with restore instructions
- **Audit event** — append-only JSONL audit trail
- **Measurement start plan** — T0 timestamp, baseline snapshot, expected policy

The executor does NOT execute external runtime actions or scheduler changes.
Runtime activation is handled by Phase 6C Runtime Ceremony Runner.

## Phase 6C Runtime Ceremony Runner

The runner (`self_improvement_v2/src/si_v2/pipeline/runtime_ceremony_runner.py`)
closes the loop between Phase-6B artifacts and controlled canary dry-run
runtime action:

1. **Artifact verification** — overlay exists, hash matches, rollback/audit/
   measurement plan exist, dry_run=true, kill switch NORMAL, RiskGuard PASS
2. **Restart plan** — builds and validates a canary restart plan via
   `plan_canary_restart_with_overlay()`
3. **Restart gate** — evaluates G1-G10 gates (G10 bypassed in AUTONOMOUS_DRY_RUN)
4. **Runtime execution** — delegates to `run_canary_restart_with_overlay()`
   with `apply_mode=AUTONOMOUS_DRY_RUN` (bypasses L3 token)
5. **RuntimeEffectProof** — standard proof pipeline
6. **T0 activation record** — only written after GREEN proof

The runner does NOT enable scheduler or watcher jobs. No live trading.

## Phase 7 Autonomous Measurement Watcher

The watcher (`self_improvement_v2/src/si_v2/measurement/autonomous_measurement_watcher.py`)
consumes Phase-6C T0 activation records and emits autonomous measurement
decisions:

1. **T0 validation** — record must be CEREMONY_EXECUTED_GREEN, GREEN proof,
   canary-only, correct next component
2. **T0 age check** — measurement must be within max age window
3. **Fleet evidence** — read-only evidence reader protocol for Freqtrade
   dry-run DB or REST API data
4. **Snapshot validation** — schema check for required fields (closed trades,
   profit, profit factor on both arms)
5. **Readiness rules** — minimum closed trades per arm before KEEP/ROLLBACK
6. **Final decision** — KEEP_CANARY_OVERLAY, EXTEND_MEASUREMENT, or
   ROLLBACK_CANARY_OVERLAY based on canary vs control comparison
7. **Decision pack** — JSON output written to `var/si_v2/measurement_decisions/`

The watcher does NOT execute rollback or scheduler changes. No live trading.

## Data Sources (Real Data Only)

All decisions must be based on real runtime evidence:

- **Freqtrade dry-run DBs** — SQLite databases per bot (`tradesv3.<bot>.dryrun.sqlite`)
- **Freqtrade APIs** — REST API evidence for bot state and trade activity
- **Rainbow / fleet scoring modules** — external signal scoring
- **RiskGuard state** — canonical risk assessment
- **ShadowLogger** — append-only audit trail
- **Measurement ledger** — T0-T3 measurement points and final decisions

## Explicitly Rejected

The following are **not** valid decision sources:

- Simulation as decision source
- Mocked candidate approval
- Hardcoded trade counts
- Stale report values as live facts
- Synthetic or fabricated evidence

## Policy Gates

All of the following must pass for an autonomous dry-run apply:

| Gate | Condition |
|------|-----------|
| `dry_run_all_true` | All fleet bots have `dry_run=true` |
| `kill_switch_mode` | Must be `NORMAL` |
| `riskguard_status` | Must be `PASS` |
| `canary_first` | Target must be a canary bot |
| `allowlist_compatible` | Candidate must be allowlist-compatible |
| `rollback_available` | Rollback plan must exist |
| `parameter_overlay` | Must be non-empty, all keys in SAFE_PARAMETERS, none in FORBIDDEN_KEYS |
| `target_bot` | Must be a recognized canary bot |
| `active_measurement` | No conflicting measurement window active |

## Operating Modes

| Mode | Description | Human Gate | Token Gate |
|------|-------------|------------|------------|
| `AUTONOMOUS_DRY_RUN` | Policy-gated autonomous dry-run | Bypassed | Bypassed |
| `MANUAL_L3` | Legacy human-gated mode | Required | Required |
| `LIVE_CAPITAL_MODE` | Future live-capital mode (not implemented) | N/A | N/A |

## Safety

- No live trading enabled
- No `dry_run=false`
- No exchange secrets touched
- No Docker/Compose mutation
- No runtime apply in this PR
- No restart
- No rollback
- No jobs.json change
- No watcher enablement
