# SI-v2 Phase 8B — Watcher Statistical Integration

## Summary

Wires Phase-8 Statistical Evidence into Phase-7 Measurement Watcher decision packs.

## Scope

- Optional statistical evidence evaluation
- Decision pack enrichment
- Statistical conflict marker (SOFT / HARD)
- Simple watcher rules remain default and authoritative
- No runtime mutation
- No rollback execution
- No scheduler enablement
- No live trading

## Behavior

- `use_statistical_evidence=False` (default): existing behavior preserved exactly
- `use_statistical_evidence=True` + trade samples present: pack includes statistical_evidence
- `missing trade samples`: no block, simple decision continues, stat evidence is null
- `conflicting statistics`: conflict marker only (SOFT or HARD), no auto-override
- `runtime_mutation` remains `NONE` regardless of stat result

## Decision Pack Shape

Legacy fields:
- event, change_id, candidate_id, target_bot, decision, status
- measurement_points, evidence_ref, created_at_utc
- next_required_component, runtime_mutation

New fields:
- `statistical_evidence`: StatisticalEvidenceResult.to_dict() or null
- `statistical_conflict`: {has_conflict, severity, simple_decision, stat_recommendation, reason}

## Next

Phase 9 can consume enriched decision packs for fleet promotion policy.

## Files

- `self_improvement_v2/src/si_v2/measurement/autonomous_measurement_watcher.py` — stat helpers + integration
- `self_improvement_v2/tests/test_autonomous_measurement_watcher.py` — 8 new tests (37 total)