# Rainbow R6 — Candidate Quality with Signal Context Report

**Issue:** #495
**Parent Tracker:** #489
**Canonical Roadmap:** #423
**Branch:** `feat/rainbow-r6-candidate-quality`
**Base SHA:** `a70a058c535aa80ed813be7cebfc4fe621cb8b25`
**Head SHA:** *(set on commit)*
**Date:** 2026-07-10

## Observation

The fleet analyzer (`loop/fleet_analyzer.py`) generates ShadowProposal decisions from bot evidence, and the candidate pipeline (`pipeline/candidate_to_apply.py`) evaluates them through autonomy, RiskGuard, and measurement gates. However, Rainbow signal evidence was not integrated into candidate ranking or quality assessment.

## Cause

R3 created the attribution producer. R6 adds the advisory quality layer that evaluates Rainbow evidence for candidate ranking without relaxing any safety gates.

## Actual Candidate Architecture

The issue's proposed path `proposals/candidate_builder.py` does not exist on current main. The actual architecture:

| Component | Path | Role |
|-----------|------|------|
| Fleet analyzer | `loop/fleet_analyzer.py` | Generates ShadowProposal decisions |
| Evidence pipeline | `evidence/input_pipeline.py` | Produces quality-gated ProposalEvidenceRecords |
| Candidate pipeline | `pipeline/candidate_to_apply.py` | Orchestrates gates with evidence_refs |
| Signal models | `signals/models.py` | Typed evidence summaries |

## Implementation

### New file: `si_v2/rainbow/candidate_quality.py`

| Component | Description |
|-----------|-------------|
| `AlignmentState` | ALIGNED, CONFLICTING, NEUTRAL, UNUSABLE, ABSENT |
| `RainbowCandidateQuality` | Typed advisory result: source_ids, evidence_ids, direction, confidence, freshness, reason_codes, quality_status, alignment, advisory_score, downgrade_reasons, usable |
| `RainbowCandidateQualityEvaluator` | Pure, deterministic evaluator with evaluate() method |

### Advisory Quality Contract

- `advisory_score` is for ranking only — NOT Autonomy confidence, NOT RiskGuard confidence, NOT Judge approval
- Alignment: direction match → ALIGNED, long↔short → CONFLICTING, otherwise → NEUTRAL
- Freshness: within max_signal_age → fresh, within stale_age → stale, beyond → unavailable
- Score: aligned fresh = 0.5 + confidence*0.5, neutral = 0.3, conflicting/stale/degraded/absent = 0.0

### Monotonic Safety Invariant

For identical baseline candidate and gate inputs: `decision_with_rainbow` must be equal to or stricter than `decision_without_rainbow`. Rainbow evidence can only rank, annotate, or downgrade — never increase permissiveness.

### Evidence References

`CandidateApplyInput.evidence_refs` remains informational. Rainbow evidence IDs and source IDs are propagated as bounded identifiers, not raw payloads.

### Guard Tests Extended

`test_no_forbidden_patterns.py` now also forbids:
- `primo_signal_state.json`
- `execute_apply`
- `run_canary_restart`
- `execute_canary_rollback`

## Tests

| Test Suite | Result |
|------------|--------|
| `test_rainbow_candidate_quality.py` (new, 10 tests) | PASS |
| All 11 Rainbow test suites | PASS |
| `test_no_forbidden_patterns.py` | PASS |
| Ruff (all changed Python files) | PASS |

## Safety Invariants

- ✅ Rainbow remains advisory only
- ✅ No execution confidence was increased
- ✅ No autonomy gate was weakened
- ✅ No RiskGuard/Judge threshold changed
- ✅ No runtime mutation occurred
- ✅ No C4/D1/D2 authorization was produced
- ✅ No parameter overlay generated from Rainbow
- ✅ No target bot modification
- ✅ No human-approval relaxation
- ✅ No NO_PROPOSAL-to-executable promotion
- ✅ No Rainbow-to-order path

## Known Limitations

- The evaluator is a pure helper module; integration with the fleet analyzer's ranking is a separate step
- Evidence IDs from the input pipeline are accepted but not yet cross-referenced with R3 attribution fingerprints

## Rollback

`git revert` of the merge commit on `main` restores the previous state. No data migration required.

## Next Gate

`R6_CANDIDATE_QUALITY_MERGED_R5_READ_ONLY_AUDIT_SELECTED`
