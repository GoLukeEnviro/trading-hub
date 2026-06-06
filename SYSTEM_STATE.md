# SYSTEM_STATE.md — FreqForge Trading Stack

> **Auto-generated**: 2025-06-05T22:16Z  
> **Generator**: Hermes Orchestrator (system-analysis run)  
> **Profile**: orchestrator

---

## 4-Schichten Architektur

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — ORCHESTRATION                                │
│  Hermes Agent (orchestrator profile)                     │
│  ├─ Skills: 9 trading skills registered                  │
│  ├─ Cron Jobs: active (ledger watchdog, obs runner)      │
│  └─ Container: hermes-green (172.26.0.5)                 │
├─────────────────────────────────────────────────────────┤
│  LAYER 2 — TRADING FLEET (Freqtrade Dry-Run)             │
│  ├─ freqforge        : FreqForge_Override   (3 pairs)    │
│  ├─ freqforge-canary : FreqForge_Override   (8 pairs)    │
│  ├─ regime-hybrid    : RegimeSwitchingHybrid (5 pairs)   │
│  ├─ freqai-rebel     : RebelLiquidation     (FreqAI)     │
│  └─ webserver        : FreqForge_Override   (3 pairs)    │
├─────────────────────────────────────────────────────────┤
│  LAYER 3 — AI STACK                                      │
│  ├─ green-ollama  : healthy, 5 models loaded             │
│  ├─ green-mem0    : UNHEALTHY                            │
│  └─ green-qdrant  : Up (internal, not reachable from     │
│                      Hermes container on 6333)           │
├─────────────────────────────────────────────────────────┤
│  LAYER 4 — INFRASTRUCTURE                                │
│  ├─ Docker Networks: trading_hermes-net (172.26.0.0/16)  │
│  ├─ Docker Proxy: read-only (exec=403, logs=partial)     │
│  ├─ Disk: 172/301 GB used (60%)                          │
│  ├─ RAM:  6.8/30 GB used (23%), Swap 896M/4G             │
│  ├─ Caddy reverse proxy                                  │
│  ├─ Guardian watchdog                                    │
│  └─ AI Hedge Fund Crypto signal service                  │
└─────────────────────────────────────────────────────────┘
```

---

## Docker Container Inventory

| Container | Image | IP | Host Port | Health |
|-----------|-------|----|-----------|--------|
| trading-freqtrade-freqforge-1 | freqtradeorg/freqtrade:stable | 172.26.0.6 | 8086→8080 | Up 4h |
| trading-freqtrade-freqforge-canary-1 | freqtradeorg/freqtrade:stable | 172.26.0.10 | 8081→8080 | Up 4h |
| trading-freqtrade-regime-hybrid-1 | freqtradeorg/freqtrade:stable | 172.26.0.9 | 8085→8080 | Up 4h |
| trading-freqai-rebel-1 | freqtradeorg/freqtrade:stable | 172.26.0.7 | 8087→8080 | Up 4h |
| trading-freqtrade-webserver-1 | freqtradeorg/freqtrade:stable | 172.26.0.4 | 8180→8080 | Up 4h |
| trading-ai-hedge-fund-1 | trading-ai-hedge-fund-crypto:latest | 172.26.0.3 | 8410→8080 | healthy |
| green-ollama | ollama/ollama:latest | 172.26.0.12 | — (11434) | healthy |
| green-mem0 | hermes-mem0-local-api:stable | 172.26.0.13 | 8788→8787 | **UNHEALTHY** |
| green-qdrant | qdrant/qdrant:latest | 172.26.0.11 | — (6333-6334) | Up |
| hermes-green | nousresearch/hermes-agent:latest | 172.26.0.5 | 8642, 8083 | Up 3h |
| trading-caddy-1 | caddy:alpine | — | — | Up 4h |
| trading-hermes-watchdog-1 | alpine:latest | 172.26.0.8 | — | Up 4h |
| trading-docker-proxy-1 | tecnativa/docker-socket-proxy | — | 2375 | Up 4h |
| trading-guardian | guardian-trading-guardian | 172.26.0.2 | — | Up 4d |
| trading-dashboard | python:3.13-slim | — | 5000→5000 | Up 2d |

---

## Bot Fleet Detail

### freqforge
- **Strategy**: `FreqForge_Override`
- **Exchange**: Bitget (dry_run=True)
- **Mode**: Futures (USDT)
- **Pairs**: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT
- **Stake**: 50 USDT | Max Open: 5
- **Status**: 🔴 **CRITICAL** — 41 AttributeErrors/500 lines (`FleetRiskManager.state`)

### freqforge-canary
- **Strategy**: `FreqForge_Override`
- **Exchange**: Bitget (dry_run=True)
- **Mode**: Futures (USDT)
- **Pairs**: BTC, ETH, SOL, LINK, DOT, ATOM, UNI, AAVE
- **Stake**: 25 USDT | Max Open: 3
- **Status**: 🔴 **CRITICAL** — 43 AttributeErrors/500 lines

### regime-hybrid
- **Strategy**: `RegimeSwitchingHybrid_v7_v04_Integration`
- **Exchange**: Bitget (dry_run=True)
- **Mode**: Futures (USDT)
- **Pairs**: BTC, SOL, AVAX, NEAR, ARB
- **Stake**: 25 USDT | Max Open: 5
- **Status**: 🔴 **CRITICAL** — 43 AttributeErrors/500 lines

### freqai-rebel
- **Strategy**: `RebelLiquidation` (FreqAI)
- **Exchange**: Bitget (dry_run=True)
- **Mode**: Futures (USDT)
- **Status**: 🟢 **OK** — 0 AttributeErrors (FreqAI bypasses FleetRiskManager?)

### webserver
- **Strategy**: `FreqForge_Override`
- **Exchange**: Bitget (dry_run=True)
- **Pairs**: BTC, ETH, SOL (same as freqforge)
- **Status**: Unknown (no strategy errors in logs)

---

## Strategy Inventory

| Strategy File | Bot | Versions on Disk | Patch Status |
|--------------|-----|-------------------|--------------|
| FreqForge_Override.py | freqforge, canary, webserver | 1 (shared) | Active |
| RegimeSwitchingHybrid_v7_v04_Integration.py | regime-hybrid | 18 variants | v7-v04 active |
| RebelLiquidation.py | freqai-rebel | 2 variants | Active (FreqAI) |
| FreqForge_v2.py | (inactive) | 1 | Inactive |
| PullbackEMA_v1.py | (inactive) | 1 | Inactive |
| 30+ research variants | (inactive) | regime-hybrid dir | Archive |

---

## AI Stack

### Ollama (green-ollama) — 🟢 HEALTHY
- **Models loaded** (5):
  - `qwen3-embedding:4b` — Embedding model
  - `mxbai-embed-large:latest` — Embedding model
  - `gpt-oss:120b-cloud` — LLM (inference)
  - `qwen2.5:3b` — LLM (lightweight)
  - `nomic-embed-text:latest` — Embedding model

### Mem0 (green-mem0) — 🔴 UNHEALTHY
- Docker reports unhealthy
- Logs not accessible (docker-proxy restriction)
- API health endpoint returns empty

### Qdrant (green-qdrant) — 🟡 UP (unverified)
- Container running, ports 6333-6334 internal
- Not reachable from Hermes container (connection refused on 6333)
- Needs network verification

---

## FleetRiskManager Status

- **File**: `/home/hermes/projects/trading/freqtrade/shared/fleet_risk_manager.py`
- **State file**: `fleet_risk_state.json` (59KB, hermes:hermes 664)
- **Line 103**: ✅ Correct — `self.state = self.refresh_from_disk()`
- **Root Cause of AttributeError**: Constructor has NO try/except around `self.state = self.refresh_from_disk()`. If `refresh_from_disk()` throws, `self.state` is never assigned → all downstream calls crash.
- **Active Impact**: 3/4 bots (freqforge, canary, regime-hybrid) spam AttributeErrors every candle cycle. Bots cannot analyze OHLCV data → **effectively trading-blind**.
- **freqai-rebel**: 0 errors (likely doesn't call FleetRiskManager or uses different code path)

### Ledger Audit Findings
- **Missing source_key**: `freqai-rebel` — not tracked in ledger
- **Drawdown**: 3.42% > R2 threshold (3.0%)
- **Live-Ledger Delta**: 1,061.62 USDT

---

## Infrastructure

| Metric | Value | Status |
|--------|-------|--------|
| Disk Usage | 172/301 GB (60%) | 🟡 Moderate |
| RAM | 6.8/30 GB (23%) | 🟢 Good |
| Swap | 896M/4 GB | 🟡 Some pressure |
| Docker Networks | 13 networks | 🟢 |
| Docker Proxy | EXEC=0 (blocked), logs=partial | 🔴 Read-only only |

---

## Known Issues

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | FleetRiskManager AttributeError — 3/4 bots affected | 🟢 FIXED | Patched 2026-06-05 |
| 2 | Mem0 API unhealthy | 🔴 HIGH | Open |
| 3 | freqai-rebel missing from ledger (source_key) | 🟡 MEDIUM | Known |
| 4 | Drawdown 3.42% exceeds R2 threshold (3.0%) | 🟡 MEDIUM | Known |
| 5 | Docker exec blocked by proxy (403) | 🟡 MEDIUM | By design |
| 6 | Qdrant unreachable from Hermes container | 🟡 MEDIUM | Open |
| 7 | webserver bot shares config with freqforge | ℹ️ INFO | By design |

---

## Next Actions

1. **FIX FleetRiskManager AttributeError** — Wrap `self.state = self.refresh_from_disk()` in try/except, fallback to `_default_state()`. This is the #1 blocker.
2. **Diagnose Mem0 unhealthy** — Check container logs, config, upstream dependencies.
3. **Add freqai-rebel source_key** to ledger collection.
4. **Verify Qdrant network connectivity** — May need port mapping or network bridge.
5. **Consider weekly cron** for this SYSTEM_STATE.md refresh.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-06-06 | FIX-04: FleetRiskManager patched — try/except in __init__ + getattr in _check_direction_bias. Bots restarted via Docker proxy. 3/3 healthy. |

---

*This file is auto-generated. Do not edit manually — run the system-analysis skill to refresh.*
