# ai4trade REST Boundary Prototype — Phase J

> **Stub-Server-Only — No real ai4trade-bot calls.**
> Phase J implements a localhost-only REST boundary to validate the
> contract shape between SI v2 and an ai4trade-like signal service.

---

## 1. Purpose

Validate the REST API contract for these operations:

| Operation | Endpoint | Method | Status |
|-----------|----------|--------|--------|
| Service health | `/health` | GET | ✅ |
| Latest signal | `/signals/latest?asset=` | GET | ✅ |
| Signal by ID | `/signals/{signal_id}` | GET | ✅ |
| Outcome by ID | `/outcomes/{signal_id}` | GET | ✅ |
| Risk evaluation | `/risk/evaluate` | POST | ✅ |

All operations are **stub-only** in Phase J — they return deterministic
fixture data from a local test server.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────┐
│  SI v2 Integration Layer                                   │
│                                                            │
│  RestSignalProvider ──► Ai4tradeRestBoundaryClient ──►     │
│  RestOutcomeProvider ──► Ai4tradeRestBoundaryClient ──►    │
│  RestRiskGateProvider ──► Ai4tradeRestBoundaryClient ──►   │
│                                                            │
│  NetworkGuard: localhost-only, http-only, no credentials   │
└────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌──────────────────┐    ┌──────────────────────┐
│ InMemory stubs   │    │ Ai4tradeStubServer   │
│ (Phase F)        │    │ (Phase J, test only) │
│ No network       │    │ 127.0.0.1:random     │
└──────────────────┘    └──────────────────────┘
```

---

## 3. Files

| File | Purpose |
|------|---------|
| `rest_models.py` | SI v2-owned REST DTOs (no ai4trade-bot imports) |
| `rest_boundary.py` | `NetworkGuard` + `Ai4tradeRestBoundaryClient` |
| `rest_adapters.py` | REST-backed protocol adapter implementations |
| `tests/support/ai4trade_stub_server.py` | Test-only stub server on 127.0.0.1 |
| `tests/test_ai4trade_rest_boundary.py` | Contract tests (all fail-closed cases) |

---

## 4. Network Guard

The `NetworkGuard` in `rest_boundary.py` rejects:

| Violation | Example | Behavior |
|-----------|---------|----------|
| Non-localhost host | `http://ai4trade.example.com` | `ValueError` |
| Non-http scheme | `file:///etc/passwd` | `ValueError` |
| Credentials in URL | `http://user:pass@127.0.0.1` | `ValueError` |
| Path traversal | `http://127.0.0.1/../../../etc` | `ValueError` |
| Unknown scheme | `ssh://127.0.0.1` | `ValueError` |

---

## 5. Fail-Closed Cases

The REST boundary fails closed in these scenarios:

| Scenario | Client Behavior |
|----------|----------------|
| 404 Not Found | Returns `None` (signal/outcome not found) |
| 4xx Client Error | Returns `None` |
| 5xx Server Error | Returns `None` |
| Timeout | Returns `None` |
| Invalid JSON | Returns `None` |
| Schema mismatch | Returns `None` |
| Unreachable server | Returns `None` |
| Non-localhost URL | Raises `ValueError` at construction |

---

## 6. Limitations (Phase J)

- **Stub server only** — no real ai4trade-bot calls
- **localhost only** — production URL allowlist not implemented
- **No authentication** — no token, API key, or TLS
- **No audit logging** — adapter-level audit exists in RealAdapterBase,
  but REST client does not record calls yet
- **No rate limiting** — call budget exists in `CallBudgetChecker`, but
  REST client does not enforce it yet
- **No retry policy** — no automatic retries (design doc specifies
  max 1 retry for read-only ops)
- **No discovery** — base_url must be explicitly provided

---

## 7. Preconditions for Real ai4trade REST Calls

Before any real ai4trade-bot HTTP call is made:

1. [ ] Explicit human approval (GitHub Issue or approved PR)
2. [ ] Service URL allowlist (production, staging, local)
3. [ ] Auth design (token, API key, or mTLS)
4. [ ] Audit logging (every call recorded to ShadowLogger)
5. [ ] Rate limiting (CallBudgetChecker max 60 calls/min)
6. [ ] Failure budget (max N failed calls before auto-disable)
7. [ ] Rollback plan (revert to InMemory stubs)
8. [ ] Dry-run observation (72h shadow mode)
9. [ ] All 415+ Phase J tests pass
10. [ ] SOC-2 or equivalent checks if production financial data flows