# SI v2 Phase 2 — Multi-Bot Read/Analyze/Shadow-Proposal Report

**Timestamp (UTC):** 2026-06-13T11:10:45.687023+00:00
**Cycle ID:** `20260613T111045Z`
**Branch:** `feat/si-v2-readonly-freqtrade-jwt-auth`
**Commit SHA:** `1789f76`
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
| status_code | `0` |
| ok | `False` |
| auth_outcome | `YELLOW_MISSING_ENV_VARS` |
| open_trades | `0` |
| missing_env_vars | `SI_V2_FREQTRADE_FREQFORGE_USERNAME, SI_V2_FREQTRADE_FREQFORGE_PASSWORD` |
| auth_error_summary | `none` |
| response_summary | `YELLOW: missing env vars (SI_V2_FREQTRADE_FREQFORGE_USERNAME, SI_V2_FREQTRADE_FREQFORGE_PASSWORD)` |

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
| status_code | `0` |
| ok | `False` |
| auth_outcome | `YELLOW_MISSING_ENV_VARS` |
| open_trades | `0` |
| missing_env_vars | `SI_V2_FREQTRADE_REGIME_HYBRID_USERNAME, SI_V2_FREQTRADE_REGIME_HYBRID_PASSWORD` |
| auth_error_summary | `none` |
| response_summary | `YELLOW: missing env vars (SI_V2_FREQTRADE_REGIME_HYBRID_USERNAME, SI_V2_FREQTRADE_REGIME_HYBRID_PASSWORD)` |

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
| status_code | `0` |
| ok | `False` |
| auth_outcome | `YELLOW_MISSING_ENV_VARS` |
| open_trades | `0` |
| missing_env_vars | `SI_V2_FREQTRADE_FREQFORGE_CANARY_USERNAME, SI_V2_FREQTRADE_FREQFORGE_CANARY_PASSWORD` |
| auth_error_summary | `none` |
| response_summary | `YELLOW: missing env vars (SI_V2_FREQTRADE_FREQFORGE_CANARY_USERNAME, SI_V2_FREQTRADE_FREQFORGE_CANARY_PASSWORD)` |

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
| status_code | `0` |
| ok | `False` |
| auth_outcome | `YELLOW_MISSING_ENV_VARS` |
| open_trades | `0` |
| missing_env_vars | `SI_V2_FREQTRADE_FREQAI_REBEL_USERNAME, SI_V2_FREQTRADE_FREQAI_REBEL_PASSWORD` |
| auth_error_summary | `none` |
| response_summary | `YELLOW: missing env vars (SI_V2_FREQTRADE_FREQAI_REBEL_USERNAME, SI_V2_FREQTRADE_FREQAI_REBEL_PASSWORD)` |

---

## Per-Bot Decision: ShadowProposal or NO_PROPOSAL

| bot_id | decision | candidate_sha256 | hypothesis | reason |
|--------|----------|------------------|------------|--------|
| `freqtrade-freqforge` | `SHADOW_PROPOSAL` | `2ec09d92bb7ccd2f` | `telemetry_reachability_baseline_established` | `-` |
| `freqtrade-regime-hybrid` | `SHADOW_PROPOSAL` | `e41638504c52a01d` | `telemetry_reachability_baseline_established` | `-` |
| `freqtrade-freqforge-canary` | `SHADOW_PROPOSAL` | `bddb24e5aa1b3101` | `telemetry_reachability_baseline_established` | `-` |
| `freqai-rebel` | `SHADOW_PROPOSAL` | `d4425fc934dedfd6` | `telemetry_reachability_baseline_established` | `-` |

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
| status_authenticated_count | `0` |
| status_yellow_missing_env_count | `4` |
| status_failed_count | `0` |
| shadow_proposal_count | `4` |
| no_proposal_count | `0` |

**Fleet verdict:** 
`YELLOW` — all 4 bots reachable (/ping=200) but JWT env vars not set; loop logic executed with reachability-only evidence

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
| freqs_total_POST | `0` | ✅ |
| freqs_total_PUT_or_DELETE | `0` | ✅ |

---

## Final Verdict

**Fleet verdict:** `YELLOW`

**Reason:** all 4 bots reachable (/ping=200) but JWT env vars not set; loop logic executed with reachability-only evidence

The Self-Improvement Loop reached **YELLOW**: the loop logic executed end-to-end for all four bots, but the required JWT env vars were not present in this session, so the `/api/v1/status` fetch could not be authenticated. Per-bot ShadowProposals were generated from the reachability evidence with the documented pending-human approval path. Setting the env vars and re-running will promote this to GREEN.

