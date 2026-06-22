# SI v2 Alert Routing Readiness Proof — 2026-06-22

**Schema version**: 1
**Overall severity**: blocked
**Decision count**: 3

## Safety Verification

- `notification_sent_count`: **0**
- `action_count`: **0**
- `mutation_count`: **0**
- `capital_execution`: **false**

## Case 1 — Healthy

All evidence green, dynamic exit and profitability gates are candidate, no drift, clear credentials, no Go/No-Go blocker.

- Severity: `info`
- Routes: `no_alert_recommended`
- Reason codes: `all_checks_clean`

## Case 2 — Warning

Fleet monitoring yellow, telemetry stale at warning threshold (3660s > 3600s). All gates still candidate.

- Severity: `warning`
- Routes: `operator_review_recommended`
- Reason codes: `fleet_monitoring_yellow`, `stale_telemetry_warning`

## Case 3 — Blocked

Maximum severity: monitoring red, dynamic exit blocked, profitability blocked, telemetry hard stale (7400s > 7200s), heartbeat failed, runtime drift detected, credential path unclear, Go/No-Go blocker present.

- Severity: `blocked`
- Routes: `operator_review_recommended`, `promotion_pause_recommended`, `risk_review_recommended`, `runtime_drift_review_recommended`, `credential_review_recommended`
- Reason codes: `go_no_go_blocker_present`, `runtime_drift_detected`, `unclear_credential_path`, `fleet_monitoring_red`, `dynamic_exit_gate_blocked`, `profitability_gate_blocked`, `stale_telemetry_hard`, `heartbeat_failed`

## Safety Block

```json
{
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
```
