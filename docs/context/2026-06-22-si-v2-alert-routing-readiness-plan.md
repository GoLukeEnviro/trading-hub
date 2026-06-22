# SI v2 Alert Routing Readiness Proof — Phase 1 Plan

**Date**: 2026-06-22
**Issue**: [#310](https://github.com/GoLukeEnviro/trading-hub/issues/310)
**Branch**: `feat/si-v2-alert-routing-readiness-310`

## Goal

Verify that alert-routing decisions can be represented as deterministic advisory
artifacts. Every decision is pure, typed, and does not mutate the runtime.

## Scope

- Add `self_improvement_v2/src/si_v2/monitoring/alert_routing.py`
- Add `self_improvement_v2/tests/test_alert_routing.py`
- Update `self_improvement_v2/src/si_v2/monitoring/__init__.py` exports
- Create proof artifacts under `reports/phase2/alert_routing/`

### Explicitly out of scope

- No notification is sent (Telegram, email, Slack, webhook)
- No external endpoint is called
- No runtime mutation / config writes / strategy writes
- No Docker, Compose, or Cron changes
- No exchange I/O or orders
- No capital execution

## Input evidence contract

`AlertRoutingInput` accepts the following fields (all optional, all `None`-safe):

| Field | Type | Description |
|---|---|---|
| `fleet_monitoring_verdict` | `str \| None` | Verdict from FleetMonitoring evaluator (green/yellow/red) |
| `dynamic_exit_gate_verdict` | `str \| None` | Verdict from Dynamic Exit Evidence gate (candidate/inconclusive/blocked) |
| `profitability_gate_verdict` | `str \| None` | Verdict from Profitability Gate (candidate/inconclusive/blocked) |
| `telemetry_fresh` | `bool \| None` | Whether telemetry is within freshness threshold |
| `telemetry_age_seconds` | `int \| None` | Age of telemetry in seconds |
| `heartbeat_ok` | `bool \| None` | Whether heartbeat is present and healthy |
| `runtime_drift_detected` | `bool \| None` | Whether runtime drift was detected |
| `credential_path_clear` | `bool \| None` | Whether credential path is unambiguous |
| `shadow_paper_status` | `str \| None` | Shadow/paper readiness status |
| `go_no_go_blocker_present` | `bool \| None` | Whether a Go/No-Go hard blocker exists |
| `reason_codes` | `tuple[str, ...]` | Additional reason codes |

## Routing decision rules

### info — No Alert (`no_alert_recommended`)

All of:
- fleet monitoring is green
- dynamic exit gate is candidate
- profitability gate is candidate or inconclusive (without hard blocker)
- telemetry is fresh
- heartbeat is ok
- no runtime drift
- credential path is clear
- no Go/No-Go blocker

### warning — Operator Review (`operator_review_recommended`)

Any of:
- fleet monitoring is yellow
- telemetry is stale (warning threshold, not hard)
- profitability is inconclusive
- evidence is incomplete but not hard-blocked
- heartbeat is missing or failed
- dynamic exit gate is inconclusive

### critical — Promotion Pause + Risk Review

Any of:
- dynamic exit gate is blocked → adds `risk_review_recommended`
- profitability gate is blocked → adds `promotion_pause_recommended`
- runtime drift detected → adds `runtime_drift_review_recommended`
- unclear credential path → adds `credential_review_recommended`

### blocked — Promotion Pause + Operator Review

Any of:
- fleet monitoring is red
- Go/No-Go hard blocker present
- stale telemetry crosses hard threshold

## Output artifact shape

### AlertRoutingDecision

```json
{
  "severity": "info|warning|critical|blocked",
  "routes": ["no_alert_recommended", "operator_review_recommended", ...],
  "reason_codes": ["go_no_go_blocker_present", ...],
  "notification_sent": false,
  "action_count": 0,
  "mutation_count": 0,
  "runtime_mutation": false,
  "capital_execution": false
}
```

### AlertRoutingReport

```json
{
  "schema_version": 1,
  "overall_severity": "info|warning|critical|blocked",
  "decisions": [...],
  "summary": {
    "decision_count": N,
    "notification_sent_count": 0,
    "action_count": 0,
    "mutation_count": 0,
    "capital_execution": false
  },
  "safety": {
    "exchange_io": false,
    "orders": false,
    "runtime_mutation": false,
    "config_writes": false,
    "strategy_writes": false,
    "docker_changes": false,
    "compose_changes": false,
    "cron_changes": false,
    "auto_healing": false,
    "capital_execution": false
  }
}
```

## Safety constraints

| Invariant | Guarantee |
|---|---|
| `notification_sent` | Always `false` — no notification pathway exists |
| `action_count` | Always `0` — no runtime action is performed |
| `mutation_count` | Always `0` — no state mutation |
| `capital_execution` | Always `false` — no capital path |
| `routes` | Recommendation labels only; never parsed as commands |

## Validation commands

```bash
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_alert_routing.py -q
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_fleet_monitoring.py -q
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_forbidden_patterns.py -q
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_any_types.py -q
python3 -m ruff check self_improvement_v2/src/si_v2/monitoring self_improvement_v2/tests/test_alert_routing.py
uv run --active --with mypy mypy --follow-imports=skip self_improvement_v2/src/si_v2/monitoring/alert_routing.py
git diff --check
```

## Definition of Done

- [x] `AlertRoutingInput`, `AlertRoutingDecision`, `AlertRoutingReport` dataclasses defined
- [x] `AlertSeverity` and `AlertRoute` enums defined
- [x] `evaluate_alert_routing()` pure function implemented
- [x] `evaluate_alert_routing_report()` aggregation function implemented
- [x] 24 tests cover healthy, warning, critical/blocked, and edge-case paths
- [x] Safety invariants proven: notification_sent=0, action_count=0, mutation_count=0
- [x] Ruff clean
- [x] Mypy clean
- [x] No forbidden patterns
- [x] No `Any` types
- [x] Monitoring `__init__.py` exports updated
