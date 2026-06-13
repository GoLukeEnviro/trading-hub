# SI v2 Phase 2 — Multi-Bot Read/Analyze/Shadow-Proposal Report

**Timestamp (UTC):** 2026-06-13T11:36:50.712463+00:00
**Cycle ID:** `20260613T113650Z`
**Branch:** `feat/si-v2-readonly-freqtrade-jwt-auth`
**Commit SHA:** `8eebadc`
**Registry:** `self_improvement_v2/config/freqtrade_bots.readonly.json`

---

## Executive Summary

This cycle advances the SI v2 Self-Improvement Loop from a single-bot proof (PR #207) to a fleet-level cycle. The loop loads the readonly Freqtrade bot registry, performs authenticated REST reads against all enabled bots, analyzes the per-bot evidence, and emits either a metadata-only ShadowProposal or an explicit `NO_PROPOSAL` decision per bot. Every ShadowProposal is passed through the existing shadow-only safety path (RiskGuard-style check + ShadowLogger + documented `PENDING_HUMAN` state). No runtime, config, or live-trading mutation occurs in this cycle.

---

## Bots Processed

| # | bot_id | base_url | enabled | auth_type |
|---|--------|----------|---------|-----------|
| 1 | `freqtrade-freqforge` | `http://trading-freqtrade-freqforge-1:8080` | True | `env_basic_jwt` |
| 2 | `freqtrade-regime-hybrid` | `http://trading-freqtrade-regime-hybrid-1:8080` | True | `env_basic_jwt` |
| 3 | `freqtrade-freqforge-canary` | `http://trading-freqtrade-freqforge-canary-1:8080` | True | `env_basic_jwt` |
| 4 | `freqai-rebel` | `http://trading-freqai-rebel-1:8080` | True | `env_basic_jwt` |

---

## Per-Bot Evidence (Redacted)

### `freqtrade-freqforge`

| Field | Value |
|-------|-------|
| base_url | `http://trading-freqtrade-freqforge-1:8080` |
| auth_type | `env_basic_jwt` |
| username_env | `SI_V2_FREQTRADE_FREQFORGE_USERNAME` |
| password_env | `SI_V2_FREQTRADE_FREQFORGE_PASSWORD` |

**Unauthenticated `/api/v1/ping`:**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/ping` |
| method | `GET` (unauthenticated) |
| status_code | `200` |
| ok | `True` |
| response_summary | `{"status": "pong"}` |

**Authenticated `/api/v1/status` (after JWT login attempt):**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/status` |
| method | `GET` (Bearer JWT) |
| status_code | `200` |
| ok | `True` |
| auth_outcome | `AUTHENTICATED` |
| open_trades | `0` |
| missing_env_vars | `none` |
| auth_error_summary | `none` |
| response_summary | `[{"amount": 0.0007, "amount_precision": 0.0001, "amount_requested": 0.00078277, "base_currency": "BTC", "close_date": null, "close_profit": null, "close_profit_abs": null, "close_profit_pct": null, "c` |

### `freqtrade-regime-hybrid`

| Field | Value |
|-------|-------|
| base_url | `http://trading-freqtrade-regime-hybrid-1:8080` |
| auth_type | `env_basic_jwt` |
| username_env | `SI_V2_FREQTRADE_REGIME_HYBRID_USERNAME` |
| password_env | `SI_V2_FREQTRADE_REGIME_HYBRID_PASSWORD` |

**Unauthenticated `/api/v1/ping`:**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/ping` |
| method | `GET` (unauthenticated) |
| status_code | `200` |
| ok | `True` |
| response_summary | `{"status": "pong"}` |

**Authenticated `/api/v1/status` (after JWT login attempt):**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/status` |
| method | `GET` (Bearer JWT) |
| status_code | `200` |
| ok | `True` |
| auth_outcome | `AUTHENTICATED` |
| open_trades | `0` |
| missing_env_vars | `none` |
| auth_error_summary | `none` |
| response_summary | `[]` |

### `freqtrade-freqforge-canary`

| Field | Value |
|-------|-------|
| base_url | `http://trading-freqtrade-freqforge-canary-1:8080` |
| auth_type | `env_basic_jwt` |
| username_env | `SI_V2_FREQTRADE_FREQFORGE_CANARY_USERNAME` |
| password_env | `SI_V2_FREQTRADE_FREQFORGE_CANARY_PASSWORD` |

**Unauthenticated `/api/v1/ping`:**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/ping` |
| method | `GET` (unauthenticated) |
| status_code | `200` |
| ok | `True` |
| response_summary | `{"status": "pong"}` |

**Authenticated `/api/v1/status` (after JWT login attempt):**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/status` |
| method | `GET` (Bearer JWT) |
| status_code | `200` |
| ok | `True` |
| auth_outcome | `AUTHENTICATED` |
| open_trades | `0` |
| missing_env_vars | `none` |
| auth_error_summary | `none` |
| response_summary | `[{"amount": 0.0004, "amount_precision": 0.0001, "amount_requested": 0.00041151, "base_currency": "BTC", "close_date": null, "close_profit": null, "close_profit_abs": null, "close_profit_pct": null, "c` |

### `freqai-rebel`

| Field | Value |
|-------|-------|
| base_url | `http://trading-freqai-rebel-1:8080` |
| auth_type | `env_basic_jwt` |
| username_env | `SI_V2_FREQTRADE_FREQAI_REBEL_USERNAME` |
| password_env | `SI_V2_FREQTRADE_FREQAI_REBEL_PASSWORD` |

**Unauthenticated `/api/v1/ping`:**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/ping` |
| method | `GET` (unauthenticated) |
| status_code | `200` |
| ok | `True` |
| response_summary | `{"status": "pong"}` |

**Authenticated `/api/v1/status` (after JWT login attempt):**

| Field | Value |
|-------|-------|
| endpoint | `/api/v1/status` |
| method | `GET` (Bearer JWT) |
| status_code | `200` |
| ok | `True` |
| auth_outcome | `AUTHENTICATED` |
| open_trades | `0` |
| missing_env_vars | `none` |
| auth_error_summary | `none` |
| response_summary | `[]` |

---

## Per-Bot Decision: ShadowProposal or NO_PROPOSAL

| bot_id | decision | candidate_sha256 | hypothesis | reason |
|--------|----------|------------------|------------|--------|
| `freqtrade-freqforge` | `SHADOW_PROPOSAL` | `5a9e54cf4348d0a3` | `telemetry_status_endpoint_observable_v1` | `-` |
| `freqtrade-regime-hybrid` | `SHADOW_PROPOSAL` | `6bbe2afe58033939` | `telemetry_status_endpoint_observable_v1` | `-` |
| `freqtrade-freqforge-canary` | `SHADOW_PROPOSAL` | `d205f897ee4a623f` | `telemetry_status_endpoint_observable_v1` | `-` |
| `freqai-rebel` | `SHADOW_PROPOSAL` | `b6dd6bf1a5cc2856` | `telemetry_status_endpoint_observable_v1` | `-` |

---

## Safety Validation Table

| bot_id | decision | RiskGuard | ShadowLogger | approval_status |
|--------|----------|-----------|--------------|-----------------|
| `freqtrade-freqforge` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `PENDING_HUMAN` |
| `freqtrade-regime-hybrid` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `PENDING_HUMAN` |
| `freqtrade-freqforge-canary` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `PENDING_HUMAN` |
| `freqai-rebel` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `PENDING_HUMAN` |

---

## Fleet-Level Interpretation

| Metric | Value |
|--------|-------|
| total_bots | `4` |
| ping_ok_count | `4` |
| ping_failed_count | `0` |
| status_authenticated_count | `4` |
| status_yellow_missing_env_count | `0` |
| status_failed_count | `0` |
| shadow_proposal_count | `4` |
| no_proposal_count | `0` |

**Fleet verdict:** 
`GREEN` — all 4 bots authenticated and decisions generated

---

## Safety Confirmation

| Property | Value |
|----------|-------|
| runtime_mutations | `0` |
| config_mutations | `0` |
| live_trading_mutations | `0` |
| controller_state | `PAUSED / L3_REPOSITORY_ONLY` |
| secrets_in_repo | `No` |
| secrets_printed | `No` |
| tokens_persisted | `No` |
| shadow_proposals_executed | `0` |
| all_shadow_proposals_have_pending_human | `Yes` |

---

## Mutation Counters

| Counter | Value | Verified |
|---------|-------|----------|
| runtime_mutations | `0` | ✅ |
| config_mutations | `0` | ✅ |
| live_trading_mutations | `0` | ✅ |
| docker_mutations | `0` | ✅ |
| network_mutations | `0` | ✅ |
| healthcheck_mutations | `0` | ✅ |
| ci_mutations | `0` | ✅ |
| strategy_mutations | `0` | ✅ |
| freqs_total_GET | `8` | ✅ |
| freqs_total_POST | `4` | ✅ |
| freqs_total_PUT_or_DELETE | `0` | ✅ |

---

## Final Verdict

**Fleet verdict:** `GREEN`

**Reason:** all 4 bots authenticated and decisions generated

The Self-Improvement Loop reached **GREEN**: all four bots were read successfully (ping + authenticated status) and a ShadowProposal or NO_PROPOSAL decision was generated for each.

