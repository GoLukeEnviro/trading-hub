# R5B Gate 1 — Legacy Rainbow Credential Isolation Evidence Report

**Date:** 2026-07-14
**Operator:** Hermes (cron roadmap tick)
**Execution class:** A0/A1 (read-only evidence, no runtime mutation)
**Issue:** #583 — [R5B][Gate 1] Legacy Rainbow credential isolation evidence task
**Parent:** #580 — R5B A2 / Gate 1 Preflight

---

## TL;DR

**Verdict: PASS** — Legacy Rainbow credentials are structurally isolated from the canonical HermesTrader dry-run fleet. No shared credential stores, no shared env files, no shared secret volumes. Rainbow operates in credential-free read-only mode by design. The UNVERIFIED status from Issue #580 is now **RESOLVED (PASS)**.

---

## 1. Evidence Protocol

This report proves credential isolation **without exposing credential values** by examining:

1. **Compose-level credential configuration** — env vars, env files, secret mounts
2. **Config-level credential references** — exchange keys, API tokens, passwords
3. **Code-level credential usage** — auth headers, API keys in client code
4. **Volume/network separation** — shared vs. isolated storage
5. **Source-of-truth hierarchy** — repo-committed configs vs. runtime injection

---

## 2. Compose-Level Analysis

### Canonical HermesTrader compose (`docker-compose.hermestrader-dryrun.yml`)

The Rainbow service definition (lines 233–264):

```yaml
rainbow:
    build:
      context: ${AI4TRADE_CONTEXT:-../ai4trade-bot}
      dockerfile: rainbow.Dockerfile
    user: "10000:10000"
    environment:
      - RAINBOW_CONFIG=/app/config/rainbow.internal.yml
      - RAINBOW_READ_ONLY=true
    volumes:
      - ./config/rainbow.internal.yml:/app/config/rainbow.internal.yml:ro
      - rainbow-storage:/app/rainbow/storage
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    networks:
      - trading_internal
      - trading_egress
```

**Key findings:**
- **No `env_file` directive** — Rainbow does not load any `.env` file
- **No secret mounts** — no Docker secrets, no bind-mounted credential files
- **No exchange credentials** in environment variables
- **Only two env vars**: `RAINBOW_CONFIG` (config path) and `RAINBOW_READ_ONLY=true` (safety flag)
- **Read-only volume mounts** — config is mounted `:ro`
- **Separate named volume** `rainbow-storage` — not shared with any Freqtrade bot
- **No published ports** — Rainbow is only reachable on the internal Docker network

### Rainbow include file (`services/rainbow/rainbow.include.yml`)

Identical configuration fragment. Same findings: no credentials, no env files, no secrets.

### Rainbow dependency lock (`ops/ai4trade-rainbow.lock.yml`)

Pinned to ai4trade-bot SHA `6e850c8f8ba1d8a0ad45250f130280e4171c001d`. Builds from an immutable checkout (`AI4TRADE_CONTEXT=/opt/data/projects/ai4trade-bot-r5a-6e850c8`). No credential references.

---

## 3. Config-Level Analysis

### Rainbow internal config (`config/rainbow.internal.yml`)

```yaml
read_only: true

evaluation:
  enabled: false

# No exchange credentials configured here — the relevant setting defaults
# to empty. Real credentials, if ever needed, are injected at deploy time
# via environment, never committed to the repository.
```

**Key findings:**
- `read_only: true` — blocks POST/DELETE with HTTP 405
- `evaluation.enabled: false` — no evaluation logic active
- **Explicit comment** confirms no credentials are configured
- Only two keys accepted by `RainbowSettings` (`extra="forbid"` enforcement)

### No `.env` files for Rainbow

Repository search for `*.env*` files found only:
- `orchestrator/control/controller.env.example` — this is the SI-v2 controller env, not Rainbow

No `.env.rainbow`, no `.env.production`, no `.env.secret` files exist in the repository.

---

## 4. Code-Level Analysis

### Rainbow client (`self_improvement_v2/src/si_v2/rainbow/client.py`)

The client's docstring explicitly states:

> **No secrets or auth headers are used.**

The HTTP request (lines 297–301):
```python
request = Request(
    url=url,
    headers={"Accept": "application/json"},
    method="GET",
)
```

- **No Authorization header**
- **No API key header**
- **No Bearer token**
- **Plain HTTP GET** — no credentials in URL, no auth in headers

### Active cycle runner (`self_improvement_v2/src/si_v2/loop/active_cycle_runner.py`)

The `_RAINBOW_CONFIG` dictionary (lines 142–156):
```python
_RAINBOW_CONFIG = {
    "enabled": False,
    "mode": "fixture",
    "fixture_path": "...",
    "max_records": None,
    "base_url": None,
    "endpoint_path": "/signals/latest",
    "timeout_seconds": 30,
    "freshness_max_seconds": 900,
}
```

- **No credential fields** in the config
- **Default disabled** — must be explicitly enabled
- **Default fixture mode** — no network calls
- **`base_url` defaults to None** — read_only mode without base_url fails closed

### Repository-wide credential search

Searched for patterns: `RAINBOW.*KEY`, `RAINBOW.*SECRET`, `RAINBOW.*TOKEN`, `RAINBOW.*API`, `RAINBOW.*PASSWORD`, `RAINBOW.*EXCHANGE`, `exchange.*key`, `exchange.*secret`, `api_key`, `api_secret`, `EXCHANGE_KEY`, `EXCHANGE_SECRET`

**Result: 0 matches** — no Rainbow credential references exist anywhere in the repository.

---

## 5. Volume/Network Separation

| Resource | Canonical Fleet (Freqtrade bots) | Rainbow | Shared? |
|----------|----------------------------------|---------|---------|
| Named volumes | `freqforge-db`, `canary-db`, `regime-hybrid-db`, `webserver-db`, `rebel-db` | `rainbow-storage` | **No** — separate volumes |
| Log volumes | `freqforge-logs`, `canary-logs`, `regime-hybrid-logs`, `rebel-logs` | None | **No** — Rainbow has no log volume |
| Networks | `trading_internal` + `trading_egress` | `trading_internal` + `trading_egress` | **Shared networks** (required for SI-v2 cycle to read signals) |
| Published ports | `8086`, `8081`, `8085`, `8180`, `8087` (all 127.0.0.1) | **None** | **No** — Rainbow has no published ports |
| Config mounts | Per-bot `config.example.json` (ro) | `rainbow.internal.yml` (ro) | **No** — different config files |
| Shared modules | `freqtrade/shared:ro` | None | **No** — Rainbow doesn't mount shared modules |

**Network sharing is by design** — the SI-v2 active cycle runner needs to reach Rainbow's HTTP endpoint to read signals. This is a one-way, credential-free HTTP GET. Rainbow has no published ports and no external network exposure.

---

## 6. Credential Isolation Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    HermesTrader Host                         │
│                                                              │
│  ┌─────────────────────┐    ┌──────────────────────────┐    │
│  │ Canonical Fleet      │    │ Rainbow (Legacy)          │    │
│  │ (Freqtrade bots)     │    │                           │    │
│  │                      │    │ • No credentials in repo  │    │
│  │ • Exchange creds via │    │ • RAINBOW_READ_ONLY=true  │    │
│  │   env_file (runtime) │    │ • No env_file             │    │
│  │ • dry_run=true       │    │ • No secret mounts        │    │
│  │ • Published ports    │    │ • No published ports      │    │
│  └──────────┬───────────┘    │ • Credential-free HTTP    │    │
│             │                └──────────┬───────────────┘    │
│             │                           │                    │
│             └───────────┬───────────────┘                    │
│                         │                                    │
│                  trading_internal                            │
│                  (Docker bridge, internal)                   │
│                                                              │
│  Credential boundary:                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Canonical fleet credentials are injected at runtime  │   │
│  │ via env_file (never committed). Rainbow has NO       │   │
│  │ credential configuration at any layer.                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Verifiable Evidence Protocol

For future audits, credential isolation can be verified without exposing values:

| Check | Method | Expected Result | Actual Result |
|-------|--------|----------------|---------------|
| No credential env vars in compose | `grep -r "RAINBOW.*KEY\|RAINBOW.*SECRET" docker-compose*.yml` | 0 matches | ✅ 0 matches |
| No credential env vars in config | `grep -r "api_key\|api_secret\|exchange.*key" config/rainbow.internal.yml` | 0 matches | ✅ 0 matches |
| No auth headers in client code | `grep -r "Authorization\|Bearer\|api_key" self_improvement_v2/src/si_v2/rainbow/client.py` | 0 matches | ✅ 0 matches |
| No env files for Rainbow | `find . -name "*.env*" -not -path "./.git/*"` | No Rainbow env files | ✅ Only `controller.env.example` found |
| Read-only mode enforced | `grep "RAINBOW_READ_ONLY" docker-compose*.yml` | `true` | ✅ `RAINBOW_READ_ONLY=true` |
| No published ports | `grep "ports:" -A1 services/rainbow` in compose | No ports | ✅ No ports for Rainbow |
| Separate storage volume | `grep "rainbow-storage" docker-compose*.yml` | Separate volume | ✅ `rainbow-storage` is unique |

---

## 8. Conclusion

**Legacy Rainbow credential isolation: RESOLVED (PASS)**

All seven verification checks pass. Rainbow operates in a credential-free, read-only mode by architectural design:

1. **No credentials in repository** — zero credential references found at any layer
2. **No credential injection mechanism** — no env_file, no secret mounts, no credential volumes
3. **Read-only by design** — `RAINBOW_READ_ONLY=true` enforced at compose level, `read_only: true` at config level, HTTP GET-only client
4. **Fail-closed defaults** — Rainbow is disabled by default, fixture mode by default, read_only without base_url fails closed
5. **Structural separation** — separate named volumes, no published ports, no shared credential stores
6. **Verifiable without value exposure** — the evidence protocol above can be re-run by any auditor without reading credential values

This resolves the UNVERIFIED item from Issue #580. The R5B Gate 1 preflight now has **0 remaining UNVERIFIED items** (freqai-rebel config status was resolved PASS in PR #584).

---

*Generated 2026-07-14 by Hermes (cron roadmap tick). A0/A1 only — no runtime mutation.*
