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

## Phase 9A — Controlled Fleet Rollout Policy

The policy evaluator (`self_improvement_v2/src/si_v2/rollout/fleet_rollout_policy.py`)
consumes enriched Measurement Watcher decision packs, validates KEEP +
statistical evidence, blocks HARD conflicts, selects eligible fleet target
bots, and writes a rollout policy artifact.

## Phase 9B — Fleet Rollout Artifact Planner

The planner (`self_improvement_v2/src/si_v2/rollout/fleet_rollout_artifact_planner.py`)
consumes Phase-9A rollout policy artifacts and generates concrete per-target
rollout plan artifacts: planned overlay, pre-apply snapshot plan, rollback
plan, and fleet rollout plan.

## Phase 9C — Controlled Fleet Runtime Ceremony

The ceremony module (`self_improvement_v2/src/si_v2/rollout/fleet_runtime_ceremony.py`)
consumes Phase-9B fleet rollout plans and runs controlled dry-run-only target
ceremonies. It writes pre-apply snapshots, audit events, RuntimeEffectProof,
and measurement-start records per target through a mockable runtime executor.

## Phase 10 — Fleet Rollout Chain Active-Cycle Integration

The chain runner (`self_improvement_v2/src/si_v2/rollout/fleet_rollout_chain_runner.py`)
integrates Phase 9A/9B/9C into a controlled fleet rollout chain runner and
optional Active Cycle hook. Scheduler activation remains out of scope.

The chain runner:
1. Reads the Measurement Watcher decision pack
2. Runs Phase 9A rollout policy evaluation
3. Runs Phase 9B artifact planning
4. Runs Phase 9C runtime ceremony (READY-only by default)
5. Writes a chain audit artifact

The Active Cycle hook (`maybe_run_fleet_rollout_chain_from_active_cycle`)
is disabled by default (`_FLEET_ROLLOUT_CHAIN_ENABLED = False`).

## T0 Activation Record

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

## Phase 8 Statistical Evidence Framework

The framework (`self_improvement_v2/src/si_v2/measurement/statistical_evidence.py`)
provides a read-only statistical evidence layer for autonomous dry-run
measurement decisions. It enriches Phase-7 decisions with bootstrap
confidence intervals, effect sizes, winrate, profit factor, and evidence
grades.

Key features:
- Evidence classes A/B/C with graduated sample requirements
- Bootstrap confidence intervals (stdlib-only, deterministic)
- Effect size via pooled two-sample formula
- Profit factor and winrate computation
- Snapshot-to-input builder for optional Phase-7 integration
- Graded evidence output: STRONG / MODERATE / WEAK / INSUFFICIENT / BLOCKED

The framework is read-only and does not execute KEEP/ROLLBACK or
enable schedulers.

## Phase 8B Watcher Statistical Integration

Phase 8B enriches Measurement Watcher decision packs with
``StatisticalEvidenceResult``. When ``use_statistical_evidence=True``
and trade samples are present in the evidence snapshot, the watcher
evaluates statistical evidence and includes it in the decision pack.

Key behavior:
- Existing simple watcher rules remain default and authoritative
- Statistical conflicts are recorded (SOFT or HARD) but not auto-applied
- Missing trade samples do not block the simple decision path
- ``runtime_mutation`` remains ``NONE`` regardless of stat result

## Phase 9A Controlled Fleet Rollout Policy

Phase 9A evaluates fleet promotion eligibility from enriched Measurement
Watcher decision packs. It validates KEEP + statistical evidence, blocks
HARD statistical conflicts, selects eligible fleet target bots, and writes
a rollout policy artifact.

The evaluator is read-only — it does not apply overlays to fleet bots,
execute rollback, or enable schedulers.

## Phase 9B Fleet Rollout Artifact Planner

Phase 9B converts rollout policy eligibility into concrete per-target
rollout artifacts. It reads the Phase-9A rollout policy, validates the
source overlay hash, validates target runtime specs (dry-run, config
path, command), and generates per-target plan artifacts: planned
overlay copy, pre-apply snapshot plan, and rollback plan. It does not
apply overlays or mutate runtime.

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
