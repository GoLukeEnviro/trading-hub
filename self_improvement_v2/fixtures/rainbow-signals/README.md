# Rainbow Signal Fixtures

> **Purpose:** Sanitized, synthetic signal examples for contract validation (trading-hub #79).
> **Schema version:** 1
> **Status:** Ready for validator consumption

## Fixture Overview

| File | Event Type | Validity | Expected Validator Result |
|------|-----------|----------|--------------------------|
| `valid_long_signal.json` | `signal` | ✅ Valid | PASS — all required fields present |
| `valid_short_signal.json` | `signal` | ✅ Valid | PASS — LLM-sourced signal with model_id |
| `no_signal.json` | `no_signal` | ✅ Valid | PASS — explicit no-signal with zero confidence |
| `heartbeat.json` | `heartbeat` | ✅ Valid | PASS — system health, no trading signal |
| `stale_signal.json` | `signal` | ✅ Valid (semantically stale) | PASS schema, WARN on staleness check |
| `malformed_missing_required_fields.json` | (missing) | ❌ Invalid | FAIL — missing event_type, symbol, direction, confidence, timestamp |
| `partial_metadata_signal.json` | `signal` | ✅ Valid (partial) | PASS — null signal_strength is allowed |

## Schema

All valid fixtures conform to the Rainbow Signal Provider Contract (#51):

| Field | Status | Notes |
|-------|--------|-------|
| `event_type` | Required | `"signal"`, `"no_signal"`, or `"heartbeat"` |
| `schema_version` | Required | Currently `1` |
| `source_system` | Required | Fixed `"rainbow"` |
| `source_id` | Required | e.g. `"rainbow:ta"`, `"rainbow:llm"` |
| `strategy_id` | Required | e.g. `"rainbow_v1"` |
| `model_id` | Optional | e.g. `"claude-sonnet-4"` |
| `symbol` | Required | Trading pair |
| `timeframe` | Optional | Candle timeframe or null |
| `timestamp_utc` | Required | ISO-8601 UTC |
| `emitted_at_utc` | Optional | ISO-8601 UTC |
| `direction` | Required | `"long"`, `"short"`, `"no_signal"` |
| `confidence` | Required | Float 0.0–1.0 |
| `signal_strength` | Optional | Float 0.0–1.0 |
| `regime_hint` | Optional | String or null |
| `metadata` | Required | Object (may be empty) |
| `redaction_status` | Required | `"clean"`, `"redacted"`, `"unchecked"` |

## Stale Behavior

- `stale_signal.json` has `data_quality.status: "stale"` with `freshness_seconds: 108000` (30h)
- Validator must accept the JSON as syntactically valid but flag the signal as stale
- Stale signals must NOT be used for current trading decisions

## Malformed Behavior

- `malformed_missing_required_fields.json` intentionally omits `event_type`, `symbol`, `direction`, `confidence`, and `timestamp_utc`
- Validator must fail validation with clear error messages for each missing field
- The fixture is valid JSON but invalid per contract schema

## Redaction Assumptions

- No API keys, tokens, secrets, or private data are present in any fixture
- All values are synthetic
- `redaction_status` indicates whether the source system has checked the envelope
