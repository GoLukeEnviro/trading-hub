# Rainbow Shadowlock Audit Event Preview

> **Status:** Preview/offline only — not written to Shadowlock storage.
> **Events:** 7 total

## Event Summary

| Metric | Value |
|--------|-------|
| Total events | 7 |
| Actionable | 3 |
| Non-actionable | 4 |

### By Category

| Category | Count |
|----------|-------|
| `rainbow_heartbeat_observed` | 1 |
| `rainbow_no_signal_observed` | 1 |
| `rainbow_signal_rejected` | 1 |
| `rainbow_signal_stale` | 1 |
| `rainbow_signal_validated` | 3 |

## Event Details

### Event 1: `rainbow_heartbeat_observed`

| Field | Value |
|-------|-------|
| event_id | `3d7ba682-4883-4f69-9543-a1c9635b6207` |
| provider_id | `rainbow` |
| source_id | `system:health` |
| validator_verdict | warn |
| is_actionable | False |
| direction | no_signal |
| confidence | 0.0 |
| symbol | * |
| redaction_status | clean |
| warnings | Heartbeat event — not a trading signal |

### Event 2: `rainbow_signal_rejected`

| Field | Value |
|-------|-------|
| event_id | `0ebbc4ee-50db-412f-a66a-c78f8bcef720` |
| provider_id | `rainbow` |
| source_id | `rainbow:ta` |
| validator_verdict | fail |
| is_actionable | False |
| direction | unknown |
| confidence | 0.0 |
| symbol |  |
| redaction_status | unchecked |
| errors | Missing required field: event_type; Missing required field: strategy_id; Missing required field: symbol; Missing required field: timestamp_utc; Missing required field: direction; Missing required field: confidence; Missing required field: metadata; Missing required field: redaction_status |

### Event 3: `rainbow_no_signal_observed`

| Field | Value |
|-------|-------|
| event_id | `8c0b2ea6-32a4-4b19-a14f-8877a435a317` |
| provider_id | `rainbow` |
| source_id | `rainbow:ta` |
| validator_verdict | warn |
| is_actionable | False |
| direction | no_signal |
| confidence | 0.0 |
| symbol | SOL/USDT:USDT |
| redaction_status | clean |
| warnings | No-signal event — not an actionable signal |

### Event 4: `rainbow_signal_validated`

| Field | Value |
|-------|-------|
| event_id | `c96c9d8f-7406-426a-bbd0-1610d1c50575` |
| provider_id | `rainbow` |
| source_id | `rainbow:news` |
| validator_verdict | pass |
| is_actionable | True |
| direction | long |
| confidence | 0.55 |
| symbol | AVAX/USDT:USDT |
| redaction_status | unchecked |

### Event 5: `rainbow_signal_stale`

| Field | Value |
|-------|-------|
| event_id | `bd61d09a-1392-49fd-a8ee-4eefcf552f24` |
| provider_id | `rainbow` |
| source_id | `rainbow:ta` |
| validator_verdict | warn |
| is_actionable | False |
| direction | long |
| confidence | 0.8 |
| symbol | BTC/USDT:USDT |
| redaction_status | clean |
| warnings | Signal marked as 'stale' by data_quality (freshness=108000s); Signal is stale: 113395s old (threshold=3600s) |

### Event 6: `rainbow_signal_validated`

| Field | Value |
|-------|-------|
| event_id | `3f70863e-dffb-42f3-880e-e4555e081c99` |
| provider_id | `rainbow` |
| source_id | `rainbow:ta` |
| validator_verdict | pass |
| is_actionable | True |
| direction | long |
| confidence | 0.85 |
| symbol | BTC/USDT:USDT |
| redaction_status | clean |

### Event 7: `rainbow_signal_validated`

| Field | Value |
|-------|-------|
| event_id | `e86439d6-85bb-4c96-96fa-501ecce2beea` |
| provider_id | `rainbow` |
| source_id | `rainbow:llm` |
| validator_verdict | pass |
| is_actionable | True |
| direction | short |
| confidence | 0.72 |
| symbol | ETH/USDT:USDT |
| redaction_status | clean |

*No production Shadowlock writes were performed.*