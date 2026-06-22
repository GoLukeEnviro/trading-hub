# Compose Split Preflight — Read-Only Inventory (#256)

**Date:** 2026-06-22  
**Base Commit:** `b550b56`  
**Author:** Hermes Agent (orchestrator profile)  
**Status:** Read-only analysis — NO runtime mutation performed

---

## 1. Inventory

### 1.1 Active Compose Files

| File | Lines | Purpose |
|---|---|---|
| `docker-compose.yml` | 369 | Root — all production services |
| `docker-compose.ai-hedge-fund-crypto.yml` | 30 | AI hedge fund stack (legacy, partial) |

### 1.2 Historical / Archive Compose Files (not in active use)

| File | Location |
|---|---|
| `freqtrade/docker-compose.fleet.yml` | Freqtrade fleet (archived) |
| `freqtrade/bots/fomo-phase3/docker-compose.fomo.yml` | Fomo bot (decommissioned) |
| `var/trading-self-improvement/artifacts/.../docker-compose.fleet.yml` | Historical snapshot |
| `var/trading-self-improvement/artifacts/.../docker-compose.fomo.yml` | Historical snapshot |
| `Agenten_Auto_Trade/ops/lab/docker-compose.freqtrade-lab.example.yml` | Lab example (not deployed) |

---

## 2. Service Inventory (`docker-compose.yml`)

| # | Service | Domain | Container Name | Image | Risk |
|---|---|---|---|---|---|
| 1 | `docker-proxy` | **Infra** | — | `tecnativa/docker-socket-proxy` | 🟢 GREEN |
| 2 | `trading-dashboard` | **Infra** | `trading-dashboard` | `trading-dashboard:stable` | 🟢 GREEN |
| 3 | `caddy` | **Infra** | — | `caddy:alpine` | 🟢 GREEN |
| 4 | `hermes-watchdog` | **Infra** | — | `alpine:latest` | 🟢 GREEN |
| 5 | `hermes-green` | **Memory** | `hermes-green` | `nousresearch/hermes-agent` | 🟡 YELLOW |
| 6 | `green-qdrant` | **Memory** | `green-qdrant` | `qdrant/qdrant:latest` | 🟢 GREEN |
| 7 | `green-ollama` | **Memory** | `green-ollama` | `ollama/ollama:latest` | 🟢 GREEN |
| 8 | `green-mem0` | **Memory** | `green-mem0` | `hermes-mem0-local-api:stable` | 🟡 YELLOW |
| 9 | `ai-hedge-fund` | **Signal** | — | `trading-ai-hedge-fund-crypto:latest` | 🟢 GREEN |
| 10 | `shadowlock` | **Signal** | — | (build from ./shadowlock) | 🟢 GREEN |
| 11 | `freqtrade-freqforge` | **Fleet** | — | `freqtradeorg/freqtrade:stable` | 🟢 GREEN |
| 12 | `freqtrade-regime-hybrid` | **Fleet** | — | `freqtradeorg/freqtrade:stable` | 🟢 GREEN |
| 13 | `freqtrade-freqforge-canary` | **Fleet** | — | `freqtradeorg/freqtrade:stable` | 🟢 GREEN |
| 14 | `freqai-rebel` | **Fleet** | — | `freqtrade-freqai-rebel:custom` | 🟢 GREEN |
| 15 | `freqtrade-webserver` | **Fleet** | — | `freqtradeorg/freqtrade:stable` | 🟡 YELLOW |

### 2.1 Risk Classification

| Risk | Meaning | Count |
|---|---|---|
| 🟢 GREEN | Directly adoptable — standard image, no special deps | 12 |
| 🟡 YELLOW | Contains env-specific paths, external volume deps, or runtime state | 3 |
| 🔴 RED | Not anfassen ohne separaten Fix | 0 |

### 2.2 YELLOW Services — Details

- **`hermes-green`**: Bind-mounts `/opt/hermes-green/config:/opt/data`, SSH key mount, env file `/opt/hermes-green/.env`. Must verify path resolution after split.
- **`green-mem0`**: Env file `/home/hermes/projects/trading/.env`, bind-mounts `/opt/data/local-memory/app/`. Depends on `green-qdrant` + `green-ollama`. Startup order critical.
- **`freqtrade-webserver`**: Shares `freqforge/user_data` bind-mount. Must stay aligned with `freqtrade-freqforge` file paths.

---

## 3. Volume Inventory

| Volume | Type | External | Used By |
|---|---|---|---|
| `green-qdrant-data` | named | ✅ yes | `green-qdrant` |
| `green-ollama-data` | named | ✅ yes | `green-ollama` |
| `freqai-rebel-data` | named | ❌ no | `freqai-rebel` |
| `watchdog-logs` | named | ✅ yes | `hermes-watchdog` |
| `caddy_data` | named | ✅ yes | `caddy` |
| `caddy_config` | named | ✅ yes | `caddy` |

### 3.1 Named Bind Mounts (also need mapping in split)

| Mount | Source | Target | Used By |
|---|---|---|---|
| `./dashboard.py` | read-only | `/app/dashboard.py` | `trading-dashboard` |
| `./ai-hedge-fund-crypto/output` | rw | `/app/output` | `ai-hedge-fund` |
| `./freqforge/user_data` | rw | `/freqtrade/user_data` | `freqtrade-freqforge`, `freqtrade-webserver` |
| `./freqtrade/bots/regime-hybrid/user_data` | rw | `/freqtrade/user_data` | `freqtrade-regime-hybrid` |
| `./freqforge-canary/user_data` | rw | `/freqtrade/user_data` | `freqtrade-freqforge-canary` |
| `./freqtrade/bots/freqai-rebel/user_data` | rw | `/freqtrade/user_data` | `freqai-rebel` |
| `./freqtrade/shared` | rw | `/freqtrade/shared` | all Freqtrade bots |
| `./freqtrade/shared/primo_signal_state.json` | ro | `.../primo_signal_state.json` | all Freqtrade bots |
| `./Caddyfile` | ro | `/etc/caddy/Caddyfile` | `caddy` |

---

## 4. Network Inventory

| Network | Driver | Internal | External | Used By |
|---|---|---|---|---|
| `hermes-net` | bridge | no | no | Freqtrade bots, dashboard, ai-hedge-fund, shadowlock |
| `proxy-net` | bridge | **yes** | no | docker-proxy, dashboard, hermes-green |
| `trading_hermes-net` | — | — | **yes** | hermes-green, green-qdrant, green-ollama, green-mem0, hermes-watchdog |

**Network Drift Note:** `trading_hermes-net` is `external: true` — it already exists outside compose scope. This means it was created manually or by another compose file. The split must preserve this external network reference.

---

## 5. Service → Domain Mapping (Proposed Split)

| Domain | Target File | Services | Networks | Volumes |
|---|---|---|---|---|
| **Infra** | `compose/infra.yml` | docker-proxy, trading-dashboard, caddy, hermes-watchdog | proxy-net, hermes-net, trading_hermes-net | watchdog-logs, caddy_data, caddy_config |
| **Memory** | `compose/memory.yml` | green-qdrant, green-ollama, green-mem0 | trading_hermes-net | green-qdrant-data, green-ollama-data |
| **Signal** | `compose/signal.yml` | ai-hedge-fund, shadowlock | hermes-net | — |
| **Fleet** | `compose/fleet.yml` | freqtrade-freqforge, freqtrade-regime-hybrid, freqtrade-freqforge-canary, freqai-rebel, freqtrade-webserver | hermes-net | freqai-rebel-data |
| **Orchestrator** | stays in root `docker-compose.yml` | hermes-green | proxy-net, hermes-net, trading_hermes-net | — |

Note: `hermes-green` uses the most diverse network profile (all 3 networks). Keeping it in the root file avoids cross-file dependency issues. If split later, it would need all three networks declared or imported.

---

## 6. SI v2 Artifact Path Check

All SI v2 evidence/report/apply/impact paths are under `self_improvement_v2/reports/phase2/`. These are **relative to the Compose project directory** — they are NOT Docker volumes and are unaffected by Compose split as long as the project root stays `/home/hermes/projects/trading`.

**No changes needed for SI v2 in Compose Split.**

---

## 7. Rollback / Adoption Notes

| Risk | Mitigation |
|---|---|
| Service name changes would break `container_name` references between services | Preserve all `container_name` and service names exactly |
| Network name changes would break cross-service DNS | Preserve all network names exactly |
| Volume name changes would lose data | Preserve all volume names exactly |
| `depends_on` ordering lost between files | Each file must redeclare cross-file deps explicitly, or keep depends_on in root |
| Env file paths are absolute (`/opt/hermes-green/.env`) | These are not affected by Compose file location |
| A split compose file invalid without root networks | Each file must include its own `networks:` section (duplicated from root) |

---

## 8. Safety Confirmation

- ✅ No Docker containers restarted
- ✅ No `docker compose up`
- ✅ No `docker compose down`
- ✅ No config writes
- ✅ No strategy writes
- ✅ No secrets output
- ✅ No live trading
- ✅ No `dry_run=false`
- ✅ All SI v2 artifact paths unchanged
- ✅ Read-only audit only
