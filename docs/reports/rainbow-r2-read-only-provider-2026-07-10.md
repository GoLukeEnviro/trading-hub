# Rainbow R2 — Read-Only Provider Enablement Report

**Issue:** #491
**Parent Tracker:** #489
**Canonical Roadmap:** #423
**Branch:** `feat/rainbow-r2-read-only-provider`
**Base SHA:** `8c167c85551f5f5bc6c4b8d8ab8281643e3b790f`
**Head SHA:** *(set on commit)*
**Date:** 2026-07-10

## Observation

The RainbowSignalProviderClient existed with fixture-only and disabled modes. The canonical endpoint `/signals/canonical/latest` was documented in the upstream contract but had no client support. No status resolver existed to track provider health across Active Cycles.

## Cause

R1 reconciled the contract snapshot. R2 extends the client to consume both upstream endpoints and adds a status resolver for Active Cycle evidence.

## Implementation

### client.py changes

| Change | Description |
|--------|-------------|
| `canonical_endpoint_path` | New config field defaulting to `/signals/canonical/latest` |
| `is_canonical_endpoint` | Property detecting which endpoint is configured |
| Endpoint branching | `_get_latest_read_only_signals` dispatches to canonical or crypto mapper |
| `_canonical_direction_to_hub` | Maps bullish→long, bearish→short, neutral→flat |
| `_map_canonical_signal_to_envelope` | Full mapper for upstream canonical envelope fields |
| Actionability enforcement | Rejects payloads where `can_execute != false` or `dry_run_only != true` |

### status_resolver.py (new file)

| Component | Description |
|-----------|-------------|
| `ProviderStatus` | Constants: DISABLED, FIXTURE_ONLY, CONFIGURED, DEGRADED, UNAVAILABLE |
| `ProviderHealthEvidence` | Dataclass with provider_id, status, mode, endpoint, base_url_configured, consecutive_failures, last_checked_utc, errors |
| `RainbowStatusResolver` | State machine: resolve() maps config to status; record_failure/record_success track consecutive failures; is_unavailable triggers at threshold (default 3) |

## Provider State Machine

```
enabled=false ──────────→ DISABLED
enabled=true, mode=fixture ──→ FIXTURE_ONLY
enabled=true, mode=read_only, base_url set ──→ CONFIGURED
enabled=true, mode=read_only, no base_url ──→ DEGRADED
3+ consecutive failures ──→ UNAVAILABLE
successful recovery ──→ resets failure count
```

## Canonical Endpoint Behavior

| Input | Result |
|-------|--------|
| bullish | long |
| bearish | short |
| neutral | flat |
| unknown direction | Rejected |
| missing id/source/asset/created_at/confidence | Rejected |
| can_execute=true | Rejected (actionability violation) |
| dry_run_only=false | Rejected (actionability violation) |
| No actionability field | Default fail-closed (can_execute=false, dry_run_only=true) |
| metadata.canonical_symbol | NOT used (PR #66 behavior excluded) |

## Active Cycle Evidence

`ProviderHealthEvidence` is emitted per resolution call. It contains:
- provider_id, status, mode, endpoint, base_url_configured
- consecutive_failures, last_checked_utc, errors
- No secrets, no auth headers, no raw producer data
- Actionability is always can_execute=false, dry_run_only=true

## Network Boundary Verification

- HTTP GET only (enforced by upstream API design and client implementation)
- No POST, no credentials, no Authorization header
- NetworkGuard (localhost-only) unchanged and equally strict
- No delivery-worker path activated

## PR #488 Overlap Decision

PR #488 (`codex/rainbow-contract-companion`) overlaps on `client.py` with `canonical_symbol` logic that depends on unmerged PR #66. **PR #488 remains blocked.** R2 implements its own canonical endpoint support without copying PR #488 code.

## Tests

| Test Suite | Result |
|------------|--------|
| `test_rainbow_canonical_and_status.py` (new, 28 tests) | PASS |
| `test_rainbow_read_only_client.py` | PASS |
| `test_rainbow_contract_snapshot.py` | PASS |
| `test_rainbow_contract_drift_guard.py` | PASS |
| `test_rainbow_signal_validator.py` | PASS |
| `test_rainbow_client_fixture_harness.py` | PASS |
| `test_rainbow_fixture_review_report.py` | PASS |
| `test_rainbow_offline_golden_path.py` | PASS |
| Ruff (all changed Python files) | PASS |
| `git diff --check` | PASS |

## CI

*(to be filled after PR)*

## Safety Invariants

- ✅ No runtime producer started
- ✅ No credentials introduced
- ✅ No POST, no order path
- ✅ No PR #66 delivery-worker activation
- ✅ NetworkGuard unchanged
- ✅ Fail-closed validation unchanged
- ✅ No C4/D1/D2 authorization produced
- ✅ No secrets or credentials

## Known Limitations

- Status resolver is configuration-based only; no live health-check HTTP call is made in this PR (the Active Cycle runner performs that separately)
- Canonical endpoint mapper assumes upstream returns CanonicalSignalEnvelope dicts; field names differ from the CryptoSignal endpoint

## Rollback

`git revert` of the merge commit on `main` restores the previous state. No data migration required.

## Next Gate

`R2_READ_ONLY_PROVIDER_MERGED_R3_SELECTED`
