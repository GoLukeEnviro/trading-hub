# Global Orchestrator Fleet Inventory — Read-Only Audit

**Date:** 2026-06-10 07:22 UTC
**Branch:** feat/si-v2-foundation  
**HEAD:** eeacf1baba7c57e2d49aa49468d6ea338cf2a124  
**Working tree:** clean (1 untracked backup file)

---

## Executive Verdict

**🟡 YELLOW** (Healthscore: 60/100)

The fleet is larger than expected. Core trading stack is healthy but fragmented across 6 Docker networks and 4+ compose projects. Weather bots exist but are on an isolated network not reachable from the orchestrator.

---

## What Exists

- **22 containers** (18 running, 2 exited, 2 service containers)
- **14 Docker networks**
- **8 compose files** across the project tree
- **3 owned services** (weatherhermes, btc5m-bot, shadowlock) with Hermes Agent maintainer labels
- **1 weatherbot source repo** at `/home/hermes/projects/trading/weatherbot/` (GoLukeEnviro/weatherbot-hermes)
- **1 weatherhermes persistent deployment** at `/home/hermes/projects/trading/weatherhermes_persistent/weatherbot_master/`

---

## Global Container Inventory

### Trading Fleet

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| trading-freqtrade-freqforge-1 | ✅ Up | freqtradeorg/freqtrade:stable | trading_hermes-net | 127.0.0.1:8086→8080 | Trade bot (FreqForge_Override) | ACTIVE_CANONICAL |
| trading-freqtrade-freqforge-canary-1 | ✅ Up | freqtradeorg/freqtrade:stable | trading_hermes-net | 127.0.0.1:8081→8080 | Trade bot (FreqForge_Override) | ACTIVE_CANONICAL |
| trading-freqtrade-regime-hybrid-1 | ✅ Up | freqtradeorg/freqtrade:stable | trading_hermes-net | 127.0.0.1:8085→8080 | Trade bot (RegimeSwitchingHybrid) | ACTIVE_CANONICAL |
| trading-freqai-rebel-1 | ✅ Up | freqtrade-freqai-rebel:custom | trading_hermes-net | 127.0.0.1:8087→8080 | Trade bot (RebelLiquidation) | ACTIVE_CANONICAL |
| trading-freqtrade-webserver-1 | ✅ Up (healthy) | freqtradeorg/freqtrade:stable | trading_hermes-net | 127.0.0.1:8180→8080 | API/UI webserver | ACTIVE_CANONICAL |

### Signal / Risk / UI

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| trading-ai-hedge-fund-1 | ✅ Up (healthy) | trading-ai-hedge-fund-crypto:latest | trading_hermes-net, proxy-net | 127.0.0.1:8410→8080 | Signal generation | ACTIVE_CANONICAL |
| trading-guardian | ✅ Up | guardian-trading-guardian | trading_hermes-net | — | Risk guard (bash loop) | ACTIVE_CANONICAL |
| trading-dashboard | ✅ Up | trading-dashboard:stable | trading_hermes-net, proxy-net | 127.0.0.1:5000→5000 | Dashboard UI | ACTIVE_CANONICAL |

### Infrastructure

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| trading-hermes-watchdog-1 | ✅ Up | alpine:latest | trading_hermes-net | — | Healthcheck (broken target) | ACTIVE_BUT_DEGRADED |
| trading-caddy-1 | ✅ Up | caddy:alpine | (host) | — | Reverse proxy / Tailscale | ACTIVE_CANONICAL |
| trading-docker-proxy-1 | ✅ Up | tecnativa/docker-socket-proxy:latest | proxy-net | 2375/tcp | Docker socket proxy | UTILITY_ONLY |
| hermes-green | ✅ Up | nousresearch/hermes-agent:latest | trading_hermes-net, proxy-net | 127.0.0.1:8083→9119 | Hermes Orchestrator | ACTIVE_CANONICAL |

### Weather Fleet

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| weatherhermes | ✅ Up (healthy) | weatherhermes:latest | ki-fabrik | 127.0.0.1:9090→9090 | Weather prediction bot | ACTIVE_BUT_UNMONITORED |
| btc5m-bot | ✅ Up (healthy) | btc5m-bot:latest | ki-fabrik | 127.0.0.1:9091→9090 | BTC 5-min Polymarket bot | ACTIVE_BUT_UNMONITORED |

### Mem0 Stack

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| green-mem0 | ✅ Up (healthy) | hermes-mem0-local-api:stable | trading_hermes-net | 127.0.0.1:8788→8787 | Memory API | UTILITY_ONLY |
| green-ollama | ✅ Up (healthy) | ollama/ollama:latest | trading_hermes-net | 11434/tcp | LLM inference | UTILITY_ONLY |
| green-qdrant | ✅ Up | qdrant/qdrant:latest | trading_hermes-net | 6333-6334/tcp | Vector DB | UTILITY_ONLY |

### Other Running

| Container | Status | Image | Networks | Ports | Role | Classification |
|---|---|---|---|---|---|---|
| shadowlock | ✅ Up (healthy) | shadowlock:latest | trading_hermes-net | — | Shadow logger / audit | ACTIVE_CANONICAL |
| rizzcoach-app-1 | ✅ Up (healthy) | rizzcoach-app | rizzcoach_default | 127.0.0.1:8088→3000 | External app | DO_NOT_TOUCH |
| claude-worker | ✅ Up (healthy) | claude-worker:latest | (default bridge) | 127.0.0.1:5050→5000 | External worker | DO_NOT_TOUCH |

### Stopped / Exited

| Container | Status | Image | Role | Classification |
|---|---|---|---|---|
| polymarket-fadi | ❌ Exited (127) | node:20-slim | Dead polymarket bot | STALE_CONTAINER |
| a0-v2 | ⏹️ Exited (0) | agent0ai/agent-zero:latest | Agent Zero (manual stop) | STALE_CONTAINER |

---

## Weather Bot Findings

### Claim: "three additional bots" (weather, weather2, weatherbot/weatherhermes)

**Status: 2 running + 1 source-only (no dedicated container)**

| Claimed | Reality | Classification |
|---|---|---|
| **weather** | ✅ `weatherhermes` container, port 9090, Caddy route `/weather*` → :9090 | ACTIVE_BUT_UNMONITORED |
| **weather2** | ✅ **btc5m-bot** container (NOT a separate weather bot), port 9091, Caddy route `/weather2*` → :9091 | ACTIVE_BUT_UNMONITORED |
| **weatherbot** | ❌ Only source code at `/home/hermes/projects/trading/weatherbot/` (GoLukeEnviro/weatherbot-hermes git repo). No dedicated container running. | SOURCE_ONLY |

**Key finding:** `/weather2` was believed to be a second weather bot but it routes to the `btc5m-bot` — the BTC 5-minute Polymarket bot. It's NOT a weather service. The naming is misleading.

### Network isolation problem

Both weatherhermes and btc5m-bot are on the **`ki-fabrik`** Docker network. Hermes-Green (orchestrator) is NOT on this network. Neither DNS nor direct IP reachability works from the orchestrator.

| Check | weatherhermes | btc5m-bot |
|---|---|---|
| DNS from hermes-green | ❌ Fail | ❌ Fail |
| Direct IP from hermes-green | ❌ Fail | ❌ Fail |
| host.docker.internal | ❌ Fail | ❌ Fail |
| Via Caddy route | ⚠️ Public (tailnet) | ⚠️ Public (tailnet) |

---

## Network Topology

| Network | Members |
|---|---|
| **trading_hermes-net** | All Freqtrade bots + webserver + watchdog + hermes-green + guardian + dashboard + ai-hedge-fund + shadowlock + mem0/ollama/qdrant |
| **trading_proxy-net** | docker-proxy + dashboard + ai-hedge-fund + hermes-green |
| **ki-fabrik** | **weatherhermes**, **btc5m-bot** |
| **proxy-net** | docker-proxy |
| **rizzcoach_default** | rizzcoach-app-1 |
| **hermes_memory** | (green containers — shared with Mem0 v2) |
| **Others** | bridge, host, none, agenten_auto_trade, paperclip-docker, freqai-rebel-net |

---

## Route Matrix (Caddyfile)

| Route | Upstream | Container | HTTP Status | Classification |
|---|---|---|---|---|
| `/dashboard*` → agent0.ts.net | 127.0.0.1:5000 | trading-dashboard | ✅ 200 (HTML) | ACTIVE |
| `/weather*` → agent0.ts.net | 127.0.0.1:9090 | weatherhermes | ⚠️ Unknown from Caddy | ACTIVE (isolated) |
| `/weather2*` → agent0.ts.net | 127.0.0.1:9091 | btc5m-bot | ⚠️ Unknown from Caddy | ACTIVE (misnamed) |
| `trade.taile6801f.ts.net` | 127.0.0.1:8081 | freqforge-canary | ✅ | ACTIVE |
| `regime-hybrid.taile6801f.ts.net` | 127.0.0.1:8085 | regime-hybrid | ✅ | ACTIVE |
| `rizzcoach.taile6801f.ts.net` | 127.0.0.1:8088 | rizzcoach-app-1 | ✅ | EXTERNAL |
| Default | 127.0.0.1:8082 | (unknown, port 8082) | ❓ | UNKNOWN_NEEDS_REVIEW |
| `momentum` (commented) | :8084 | — | ❌ (dead) | STALE_ROUTE |
| `webserver` (commented) | :8092 | — | ❌ (dead) | STALE_ROUTE |

---

## Telegram Ownership Matrix

| Owner Candidate | Source | Telegram Active? | Token Status | Risk | Recommendation |
|---|---|---|---|---|---|
| **hermes-green (Orchestrator)** | `/opt/hermes-green/.env` | ✅ Yes (intended) | Active | Low — intended owner | KEEP AS SOLE OWNER |
| **trading-freqtrade-webserver-1** | Env from deploy (not from .env) | ✅ Yes (inherited) | Uses same token | **Medium** — should be reviewed | KEEP only if orchestrator needs relay path |
| **4 trade bots** | Env removed in #41 | ❌ Disabled | Removed | None | ✅ Already fixed |
| **weatherhermes** | Container env | ❌ No Telegram env | — | None | No Telegram needed |
| **btc5m-bot** | Container env | ❌ No Telegram env | — | None | No Telegram needed |
| **hermes-green `.env` file** | `/opt/hermes-green/.env` | ❌ Token is commented out (`# TELEGRAM_BOT_TOKEN`) | Disabled | Low | Confirms intended owner is not the file, but the runtime |

---

## Orchestrator Visibility Matrix

| Logical Alias | Current Target | DNS Reachable | HTTP Ping | Monitoring Method |
|---|---|---|---|---|
| **trading.freqforge** | trading-freqtrade-freqforge-1:8080 | ✅ | ✅ `/api/v1/ping` | HTTP ping |
| **trading.freqforge-canary** | trading-freqtrade-freqforge-canary-1:8080 | ✅ | ✅ `/api/v1/ping` | HTTP ping |
| **trading.regime-hybrid** | trading-freqtrade-regime-hybrid-1:8080 | ✅ | ✅ `/api/v1/ping` | HTTP ping |
| **trading.rebel** | trading-freqai-rebel-1:8080 | ✅ | ✅ `/api/v1/ping` | HTTP ping |
| **trading.webserver** | trading-freqtrade-webserver-1:8080 | ✅ | ✅ `/api/v1/ping` | HTTP ping |
| **signal.ai-hedge-fund** | trading-ai-hedge-fund-1:8080 | ✅ | ✅ `/health` | HTTP health |
| **risk.guardian** | trading-guardian | ✅ | ❌ (not HTTP) | Docker status / log freshness |
| **ui.dashboard** | trading-dashboard:5000 | ✅ | ❌ (no health endpoint) | Docker status / page fetch |
| **utility.weather** | weatherhermes:9090 | ❌ (ki-fabrik) | ❌ (isolated) | Via Caddy route or network connect |
| **utility.btc5m** | btc5m-bot:9090 | ❌ (ki-fabrik) | ❌ (isolated) | Via Caddy route or network connect |
| **utility.mem0** | green-mem0:8787 | ✅ | ✅ (internal) | Health check (Docker) |
| **audit.shadowlock** | shadowlock | ✅ | — | Docker status / file freshness |

---

## Do Not Touch / Stale / Remove Later

| Item | Reason | Suggested Action |
|---|---|---|
| **polymarket-fadi** | Exited (127), dead | Remove after confirming no data needed |
| **a0-v2** | Exited (0), manual stop | Remove after confirming no data needed |
| **momentum** route (commented) | Decommissioned 2026-06-09 | Already commented — keep or remove |  
| **webserver :8092** route (commented) | Stale port | Already commented — keep or remove |
| **Default :8082** Caddy route | Unknown service | Investigate — is this an orphan? |
| **rizzcoach-app-1** | External app, not owned | Do NOT touch |
| **claude-worker** | External worker, not owned | Do NOT touch |
| **Agenten_Auto_Trade/** compose | Old fleet, superseded by docker-compose.yml | Can remove after verification |
| **freqai-rebel docker-compose.yml** | Has own volume `freqai-rebel-data` | Verify this is still used by current container |
| **Port 8082** default Caddy target | Unknown route receiver | Investigate — may be stale |

---

## Risks

- **Do NOT rename containers physically** — `docker rename` breaks Docker DNS, Caddy routes, and compose reconciliation
- **Do NOT connect hermes-green to `ki-fabrik` network** yet — requires testing that it doesn't break existing routing
- **Do NOT change weatherhermes or btc5m-bot** without a separate plan — they have Polymarket private keys and need careful handling
- **Default Caddy route to :8082** is unresolved — must be traced before any Caddy changes

---

## Recommended Fix Plan

### Phase 1-1: Watchdog Fix
**Scope:** Replace `host.docker.internal` with Docker container names in watchdog command.

### Phase 1-2: Orchestrator Network Bridge
**Scope:** Connect hermes-green to `ki-fabrik` network, or establish an alternative monitoring path to weatherhermes and btc5m-bot.

### Phase 2: Unified Health Registry
**Scope:** Build a central health check that polls all services from hermes-green. Store results in a structured format.

### Phase 3: Stale Cleanup
**Scope:** Remove polymarket-fadi, a0-v2, commented routes, Agenten_Auto_Trade compose.

---

## Approval Tokens for Next Phases

```text
APPROVE_ISSUE42B_WATCHDOG_DOCKER_DNS_FIX
APPROVE_ISSUE42C_ORCHESTRATOR_NETWORK_BRIDGE
APPROVE_ISSUE43_UNIFIED_HEALTH_REGISTRY
APPROVE_ISSUE44_STALE_CLEANUP
```
