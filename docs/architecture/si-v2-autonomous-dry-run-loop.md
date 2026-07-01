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
  → Canary Dry-run Apply
  → Runtime Proof
  → Measurement
  → Final Decision (KEEP / EXTEND / ROLLBACK)
  → Auto next iteration
```

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
