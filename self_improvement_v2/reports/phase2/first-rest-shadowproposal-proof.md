# SI v2 Phase 2 — Read-Only REST ShadowProposal Proof with JWT Auth

**Date:** 2026-06-13T10:04:06Z
**Proof script:** `self_improvement_v2/src/si_v2/proofs/first_rest_shadowproposal_proof.py`
**Branch:** `feat/si-v2-readonly-freqtrade-jwt-auth`

---

## Executive Summary

This proof demonstrates that the SI v2 controller can read real dry-run bot
telemetry from exactly one Freqtrade bot via REST GET with JWT authentication
and produce exactly one ShadowProposal artifact that passes through the
existing safety chain: RiskGuard-style validation, ShadowLogger logging, and
a documented pending-human approval state.

**Root cause (this PR):** `/api/v1/ping` is unauthenticated but `/api/v1/status`
requires JWT authentication. The previous proof (PR #205) could only reach
`/api/v1/ping`. This PR adds minimal JWT auth so `/api/v1/status` can be
fetched.

**Implementation:** HTTP Basic Auth to `POST /api/v1/token/login`, in-memory
JWT Bearer token for authenticated `GET /api/v1/status`.

**Secret handling:** Environment variable references only in the registry.
No committed credentials. No persisted tokens. No printed secrets.

**Safety:** One bot, one-shot proof, shadow-only proposal. Controller remains
PAUSED / L3_REPOSITORY_ONLY.

---

## Prior Proof Chain

| PR | What | Status |
|----|------|--------|
| #205 | First REST ShadowProposal proof (ping only) | OPEN |
| #206 | Fix registry to use Docker DNS URLs | MERGED |
| #207 (this) | Add minimal JWT auth for /api/v1/status | PENDING |

---

## Scope and Non-Goals

### In Scope
- Load bot registry with env-reference auth metadata
- Select exactly one bot: `freqtrade-freqforge`
- Call unauthenticated REST GET `/api/v1/ping` for reachability
- Authenticate via HTTP Basic Auth to `POST /api/v1/token/login`
- Fetch authenticated REST GET `/api/v1/status`
- Build a metadata-only `MutationCandidate` (no executable config change)
- RiskGuard-style local check that blocks runtime
- ShadowLogger entry (in-memory mode)
- Pending-human approval artifact
- Proof report with JWT auth section

### Non-Goals (explicitly excluded)
- No live trading enablement
- No Freqtrade PUT/PATCH/DELETE
- No `/api/v1/balance` or `/api/v1/show_config` (future iteration)
- No WebSocket usage
- No Docker commands or container inspection
- No Freqtrade CLI calls
- No config mutation or strategy edits
- No Telegram delivery (in-memory adapter)
- No new infrastructure, cron jobs, or healthcheck issues
- No full ApprovalGateManager integration (requires backtest/walk-forward objects)
- No TelemetryStore or persistent telemetry

---

## Registry Auth Metadata Shape

```json
"auth": {
  "type": "env_basic_jwt",
  "username_env": "SI_V2_FREQTRADE_FREQFORGE_USERNAME",
  "password_env": "SI_V2_FREQTRADE_FREQFORGE_PASSWORD"
}
```

All four bots follow the same pattern with bot-specific env var names.
No real credentials are stored in the repository.

---

## REST GET Snapshots

### /api/v1/ping (unauthenticated, reachability)

| Field | Value |
|-------|-------|
| Endpoint | `/api/v1/ping` |
| Method | `GET` |
| Auth required | No |
| Status code | `200` |
| OK | `True` |
| Response summary | `{"status": "pong"}` |
| Fetched at | `2026-06-13T10:04:06.842860+00:00` |

### /api/v1/status (authenticated, bot status)

| Field | Value |
|-------|-------|
| Endpoint | `/api/v1/status` |
| Method | `GET` |
| Auth required | Yes (Bearer JWT) |
| Status code | `0` |
| OK | `False` |
| Response summary | `YELLOW: missing env vars (SI_V2_FREQTRADE_FREQFORGE_USERNAME, SI_V2_FREQTRADE_FREQFORGE_PASSWORD)` |
| Fetched at | `2026-06-13T10:04:06.842947+00:00` |

### Auth (token_login)

| Field | Value |
|-------|-------|
| Method | `POST /api/v1/token/login` |
| Auth type | HTTP Basic Auth (from env vars) |
| Result | `YELLOW_MISSING_ENV_VARS` |
| Missing env vars | `SI_V2_FREQTRADE_FREQFORGE_USERNAME, SI_V2_FREQTRADE_FREQFORGE_PASSWORD` |

---

## ShadowProposal Generated

| Field | Value |
|-------|-------|
| Type | `MutationCandidate` (metadata-only) |
| candidate_sha256 | `d7b9876860104535` |
| bot_id | `freqtrade-freqforge` |
| base_mode | `proposal_only` |
| requires_human_approval | `True` |
| Parameters | `{'dry_run': 1}` |
| Metadata-only candidates | `{'proof_phase2_ping': 1, 'proof_phase2_status_auth': 1}` |
| Source | `real_freqtrade_rest_get_ping_and_status` |

---

## Safety Gate Results

### RiskGuard (Proof-Only)

| Field | Value |
|-------|-------|
| Result | `PASS_SHADOW_ONLY` |
| Reason | `candidate d7b9876860104535 for freqtrade-freqforge is proposal_only, requires human approval, and contains no forbidden parameters. Runtime application is blocked.` |
| Details | proposal_only=True; runtime_blocked=True |

### ShadowLogger (In-Memory)

| Field | Value |
|-------|-------|
| Result | `LOGGED` |
| Entries | `1` |
| Phase | `proof` |
| Decision | `hold` |

### Approval Gate (Documented Pending-Human Artifact)

| Field | Value |
|-------|-------|
| Artifact type | `shadow_proposal_pending_human` |
| Proposal ID | `d7b9876860104535` |
| Approval status | `PENDING_HUMAN` |

---

## Mutation Confirmation Matrix

| Property | Value | Verified |
|----------|-------|----------|
| Bots contacted | 1 (freqtrade-freqforge) | ✅ |
| REST GET only (data) | Yes | ✅ |
| REST POST (auth only) | 1 (token_login) | ✅ |
| REST PUT/PATCH/DELETE | 0 | ✅ |
| WebSocket used | No | ✅ |
| Docker commands | 0 | ✅ |
| Freqtrade CLI calls | 0 | ✅ |
| Runtime mutations | 0 | ✅ |
| Config mutations | 0 | ✅ |
| Controller PAUSED | Yes | ✅ |
| Controller L3_REPOSITORY_ONLY | Yes | ✅ |
| ShadowProposals generated | 1 | ✅ |
| ShadowProposals executed | 0 | ✅ |
| RiskGuard exercised | Yes (PASS_SHADOW_ONLY) | ✅ |
| ShadowLogger exercised | Yes (LOGGED) | ✅ |
| ApprovalGate path exercised | Yes (PENDING_HUMAN) | ✅ |
| Secrets in repo | No | ✅ |
| Secrets printed | No | ✅ |
| Tokens persisted | No | ✅ |

---

## Explicit Non-Goals (Not Changed in This PR)

- No docker-compose.yml change
- No network change
- No port change
- No depends_on change
- No service change
- No healthcheck change
- No runtime mutation
- No controller activation
- No full telemetry system

---

## Final Verdict

Proof result: see console output

