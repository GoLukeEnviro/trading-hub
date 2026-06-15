# ai4trade REST Integration Design

**Status:** Design Document — No Implementation
**Date:** 2026-06-15
**Issue:** #24
**Parent:** #15 (Master Roadmap)

## Objective

Design the future real ai4trade REST integration after the localhost stub boundary has proven the contract.

## Dependencies

- #17 — Controlled read-only runtime probe (allows verifying connectivity)
- #19 — ai4trade API contract (defines expected schema)
- #23 — Stub boundary validation (ensures contract before real calls)

## 1. Service URL Allowlist

Only the following URLs may be contacted by the integration:

| Environment | URL | Purpose |
|-------------|-----|---------|
| Production | `https://api.ai4trade.io/v1` | Live signal exchange |
| Staging | `https://staging-api.ai4trade.io/v1` | Pre-release validation |
| Local stub | `http://localhost:8410` | Offline development (existing) |

**Hard rule:** Any URL not in this list must be rejected at the config layer. No DNS rebinding, no IP override, no proxy bypass.

## 2. Authentication Strategy

| Principle | Rule |
|-----------|------|
| No secret leakage | API keys must never appear in logs, reports, or error messages |
| Environment sourcing | Keys read from `AI4TRADE_API_KEY` env var only |
| No persistence | Keys held in memory, never written to disk |
| Rotation | Key change requires container restart |
| Scoping | Read-only API key with signal-fetch-only scope |

**Auth flow:**
1. Check `AI4TRADE_API_KEY` env var at startup
2. Fail closed if missing (no anonymous access)
3. Pass key via `Authorization: Bearer <key>` header
4. Never log the key value (log `***REDACTED***` instead)

## 3. Timeout, Retry, and Failure Budget

### Timeout
| Operation | Timeout |
|-----------|---------|
| Single signal fetch | 10 seconds |
| Connection establish | 5 seconds |
| TLS handshake | 5 seconds |

### Retry
- Max 2 retries per request
- Exponential backoff: 1s, 4s
- No retry on HTTP 4xx (client error)
- Retry on 5xx, timeout, connection error

### Failure Budget
| Window | Max Failures | Action |
|--------|-------------|--------|
| 1 hour | 5 | Log warning |
| 1 hour | 10 | Circuit-breaker: stop all calls for 15 minutes |
| 1 day  | 30 | Raise alert: manual intervention required |

## 4. Schema Compatibility

- Expected response schema documented as a Pydantic model or typed dict
- Schema version field in response (`schema_version: int`)
- Mismatch → reject response, log warning, count toward failure budget
- Breaking schema change → new API version at different URL path

## 5. Rollback / No-Op Behavior

- If ai4trade is unreachable: fall back to local stub (existing behavior)
- If auth fails: block all calls, log error, no fallback to anonymous
- If schema mismatches: reject response, continue with last known good data
- No automatic reconnection — retry triggered by next cycle

## 6. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Protocol | HTTPS only | TLS mandatory for production |
| Auth header | Bearer token | Standard, no custom scheme |
| Circuit breaker | In-process | No external dependency needed |
| Stub fallback | Explicit opt-in | Must not happen silently |

## Safety Guarantees

- No live trading enablement
- No exchange credentials
- No automatic failover to production without explicit approval
- All changes gated behind `AI4TRADE_ENABLED=false` default
