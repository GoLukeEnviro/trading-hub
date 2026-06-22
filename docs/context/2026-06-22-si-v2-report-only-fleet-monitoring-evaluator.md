# SI v2 Report-only Fleet Monitoring Evaluator

Date: 2026-06-22
Branch: `feat/si-v2-report-only-fleet-monitoring-evaluator`
Related work: #292 Phase 4A

## Summary
Implemented the report-only SI v2 fleet monitoring evaluator as a pure, advisory-only module.

### New files
- `self_improvement_v2/src/si_v2/monitoring/__init__.py`
- `self_improvement_v2/src/si_v2/monitoring/fleet_monitoring.py`
- `self_improvement_v2/tests/test_fleet_monitoring.py`

## Behavior
- Reads existing evidence-like dicts or dataclass-like objects.
- Produces per-bot monitoring status and fleet-level verdicts.
- Uses controlled verdicts: `green`, `yellow`, `red`.
- Uses advisory recommendation labels only:
  - `restart_collector_recommended`
  - `pause_promotion_recommended`
  - `mark_bot_blocked_recommended`
  - `manual_review_recommended`
  - `no_action_recommended`
- Fail-closed behavior for missing heartbeat, stale telemetry, missing gate evidence, and hard gate blocks.
- No side effects, no runtime mutation, no config writes, no strategy writes, no live-trading actions.

## Validation
- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_fleet_monitoring.py -q`
- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_dynamic_exit_evidence.py -q`
- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_forbidden_patterns.py -q`
- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_any_types.py -q`
- `python3 -m ruff check self_improvement_v2/src/si_v2/monitoring self_improvement_v2/tests/test_fleet_monitoring.py`
- `uv run --active --with mypy mypy --follow-imports=skip self_improvement_v2/src/si_v2/monitoring/fleet_monitoring.py`

## Notes
- A broader `uv run --with mypy mypy self_improvement_v2/src/si_v2/monitoring` invocation surfaces pre-existing mypy errors in unrelated `proposal_scoring` files; the new monitoring module itself is clean under `--follow-imports=skip`.
- No restarts, Docker changes, Compose changes, Cron changes, runtime mutation, config writes, strategy writes, or live-trading activation were introduced.
