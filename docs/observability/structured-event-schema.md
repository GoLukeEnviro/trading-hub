# Structured Event Schema and Report Correlation

Date: 2026-06-15
Issues: #255

## Purpose

This document defines the lightweight structured event schema for operational
logging and report correlation in the Trading Hub.  It does **not** replace
[Shadowlock](../specs/shadowlock-writer-spec.md) or the unified audit trail
from PR #259 — it provides a common envelope that makes it easier to correlate
events across components during diagnostics.

## Schema v1.0

Every operational event is a JSON object with these fields:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `schema_version` | ✅ | `string` | `"1.0"` |
| `timestamp_utc` | ✅ | `string` (ISO-8601) | UTC timestamp of the event |
| `correlation_id` | recommended | `string` | Run/cycle identifier for cross-component correlation |
| `component` | ✅ | `string` | Source component, e.g. `trading_pipeline`, `fleet_healthcheck` |
| `event_type` | ✅ | `string` | Dotted event name, e.g. `riskguard_verdict`, `signal_cycle.stale` |
| `severity` | ✅ | `string` | One of: `debug`, `info`, `warning`, `error`, `critical` |
| `message` | ✅ | `string` | Human-readable description |
| `metadata` | no | `object` | Extra structured data (must not contain credentials) |

## Redaction rule

Never include the following keys in any event's `metadata` or at any nesting
level: `api_key`, `api_secret`, `password`, `jwt_secret_key`, `passphrase`,
`private_key`, `token`, or any path containing `exchange.secret` or
`exchange.key`.  The schema validator (`orchestrator/scripts/structured_event.py`)
rejects events with these fields.

## Correlation

Each pipeline run should use a single `correlation_id`.  The helper function
`generate_correlation_id()` in `orchestrator/scripts/structured_event.py`
produces a timestamp-based ID (format `YYYYMMDD-HHMMSS-XXXXX`).

## Where logs and reports live

| Component | Log/report path |
|-----------|----------------|
| Trading pipeline | `orchestrator/logs/shadow_decisions.jsonl` |
| Bridge | stdout/stderr (Docker logs) |
| Primo agent | `/logs/primo.log` (inside container) |
| Fleet healthcheck | `orchestrator/reports/fleet_health_latest.json` |
| ShadowLogger | `orchestrator/logs/shadow_decisions.jsonl` |

## How to correlate a failed cycle

1. Find the pipeline run timestamp in `orchestrator/logs/signal_bridge.log`.
2. Extract the `correlation_id` from any structured event logged during that
   run (the pipeline should include it if it uses `build_event()`).
3. Grep all log files for that `correlation_id` to find:
   - Primo signal fetch attempts
   - RiskGuard decision entries
   - ShadowLogger audit entries
   - Fleet health reports

If no `correlation_id` is present, fall back to the pipeline run timestamp.

## Relationship to the unified audit trail

The unified audit contracts (PR #259, issue #248) verify that signal decisions,
RiskGuard verdicts, kill-switch events, and Freqtrade-facing dry-run actions
are captured in an append-only, credential-free audit log at
`orchestrator/logs/shadow_decisions.jsonl`.  The structured event schema
defined here can be used as the **entry format** for that audit trail,
ensuring every audit entry is self-describing and correlatable.
