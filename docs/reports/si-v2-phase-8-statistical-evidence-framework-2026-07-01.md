# SI-v2 Phase 8 — Statistical Evidence Framework

## Summary

Adds a read-only statistical evidence layer for autonomous dry-run measurement decisions.

## Scope

- Trade sample model (TradeSample, ArmTradeEvidence)
- Sample adequacy by evidence class A/B/C
- Bootstrap confidence intervals (stdlib-only, deterministic via random seed)
- Effect size (Cohen's d style with pooled std)
- Winrate
- Profit factor
- Recommendation: STAT_KEEP / STAT_EXTEND / STAT_ROLLBACK / STAT_INSUFFICIENT / STAT_BLOCKED
- Snapshot-to-input builder for Phase-7 watcher integration
- No runtime mutation
- No scheduler enablement
- No rollback execution
- No live trading

## Evidence Classes

| Class | Use case | Default min samples per arm |
|---|---|---:|
| A | Small config / hyperparam tweak | 5 |
| B | Strategy logic / risk / pair-adjacent change | 15 |
| C | Fleet rollout candidate | 30 |

## Decision Logic

- **STAT_KEEP**: CI entirely positive, or positive mean with non-worse PF
- **STAT_ROLLBACK**: CI entirely negative, or negative mean with worse PF
- **STAT_EXTEND**: CI crosses zero, ambiguous evidence
- **STAT_INSUFFICIENT**: Sample count below class minimum
- **STAT_BLOCKED**: Invalid inputs (empty ID, NaN, bad config)

## Evidence Grades

- **STRONG**: CI entirely positive/negative with effect_size > 0.5
- **MODERATE**: CI entirely positive/negative with smaller effect, or CI crosses zero but effect > 0.3
- **WEAK**: CI crosses zero with small effect
- **INSUFFICIENT**: Below minimum sample threshold

## Safety

- Read-only only
- No live trading
- No dry_run=false
- No runtime action
- No rollback execution
- No scheduler enablement
- Missing or insufficient samples block or return INSUFFICIENT

## Files

- `self_improvement_v2/src/si_v2/measurement/statistical_evidence.py` — statistical evidence module
- `self_improvement_v2/tests/test_statistical_evidence.py` — 33 tests