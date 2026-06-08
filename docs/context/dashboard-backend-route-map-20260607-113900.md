# Dashboard-Backend-Route Map — 2026-06-07 11:39 UTC

## Audit Scope
Read-only meta-context audit of all dashboards, backends, routes, ports, containers, reverse-proxy mappings,
health endpoints, authentication boundaries, and documentation on this VPS.

**Auditor:** Hermes Orchestrator (automated)
**Mode:** read_only_deep_audit
**Safety:** No services restarted, no files modified (except this report), no secrets exposed.

---

## 1. Executive Verdict

| Metric | Value |
|---|---|
| **Healthscore** | **78 / 100 — YELLOW** |
| **Scope** | 20 containers, 9 Caddy routes, 14 exposed ports |
| **Safety** | Confirmed read-only. Zero mutations. |
| **Critical Issues** | 1 active (Telegram polling conflicts fleet-wide) |
| **P1 Issues** | 1 (RizzCoach DB errors) |
| **P2 Issues** | 2 (stale momentum route, 6 unrouted services) |
| **P3 Issues** | 3 (no route-map docs, no Caddyfile docs, mem0 extraction error) |

**Bottom Line:** Core infrastructure healthy. All containers running, all backends responsive on internal networks.
Caddy routing works for 9 active Tailnet routes. Main operational risk is fleet-wide Telegram polling conflict
degrading notification reliability. No security exposure found — all ports bound to 127.0.0.1, all Tailnet routes
require Tailscale auth.

---

## 2. Container Inventory

| # | Container Name | Image | Host Port → Container Port | Docker Status | Health | Network(s) |
|---|---|---|---|---|---|---|
| 1 | trading-caddy-1 | caddy:alpine | host network (:3000) | Up 13 min | — | host |
| 2 | trading-dashboard | python:3.13-slim | 127.0.0.1:5000 → 5000 | Up 9h | — | bridge |
| 3 | weatherhermes | weatherhermes:latest | 127.0.0.1:9090 → 9090 | Up 9h | healthy | bridge |
| 4 | btc5m-bot | btc5m-bot:latest | 127.0.0.1:9091 → 9090 | Up 9h | healthy | bridge |
| 5 | trading-freqtrade-freqforge-canary-1 | freqtradeorg/freqtrade:stable | 127.0.0.1:8081 → 8080 | Up 9h | healthy | hermes-net |
| 6 | trading-freqtrade-regime-hybrid-1 | freqtradeorg/freqtrade:stable | 127.0.0.1:8085 → 8080 | Up 8h | healthy | hermes-net |
| 7 | trading-freqtrade-freqforge-1 | freqtradeorg/freqtrade:stable | 127.0.0.1:8086 → 8080 | Up 9h | healthy | hermes-net |
| 8 | trading-freqai-rebel-1 | freqtrade-freqai-rebel:custom | 127.0.0.1:8087 → 8080 | Up 9h | healthy | hermes-net |
| 9 | trading-freqtrade-webserver-1 | freqtradeorg/freqtrade:stable | 127.0.0.1:8180 → 8080 | Up 9h | healthy | hermes-net |
| 10 | trading-ai-hedge-fund-1 | trading-ai-hedge-fund-crypto:latest | 127.0.0.1:8410 → 8080 | Up 9h | healthy | hermes-net, proxy-net |
| 11 | hermes-green | 1292e00cf20d (hermes-agent) | 127.0.0.1:8642 → 8642, 127.0.0.1:8083 → 9119 | Up 8h | — | hermes-net, proxy-net |
| 12 | green-mem0 | hermes-mem0-local-api:stable | 127.0.0.1:8788 → 8787 | Up 9h | healthy | hermes-net |
| 13 | green-ollama | ollama/ollama:latest | internal only (:11434) | Up 9h | healthy | hermes-net |
| 14 | green-qdrant | qdrant/qdrant:latest | internal only (:6333-6334) | Up 9h | — | hermes-net |
| 15 | trading-docker-proxy-1 | tecnativa/docker-socket-proxy | internal only (:2375) | Up 9h | — | proxy-net |
| 16 | trading-hermes-watchdog-1 | alpine:latest | none | Up 9h | — | hermes-net |
| 17 | trading-guardian | guardian-trading-guardian | none | Up 9h | — | — |
| 18 | rizzcoach-app-1 | rizzcoach-app | 127.0.0.1:8088 → 3000 | Up 9h | healthy | rizzcoach_default |
| 19 | polymarket-fadi | node:20-slim | 127.0.0.1:9092 → 3001 | Up 9h | — | ki-fabrik |
| 20 | claude-worker | claude-worker:latest | 127.0.0.1:5050 → 5000 | Up 9h | healthy | bridge |

---

## 3. Route Matrix (Caddyfile → Tailnet)

Caddy listens on `127.0.0.1:3000` (host network mode). Tailscale Funnel/Serve forwards Tailnet hostnames to Caddy.

### Active Routes

| Route ID | Hostname | Path | Upstream | Container | Exposure | Frontend | API | WS | Auth | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | agent0.taile6801f.ts.net | /dashboard* | 127.0.0.1:5000 | trading-dashboard | Tailnet | Flask SSR | N/A | N/A | Tailscale | GREEN |
| R02 | agent0.taile6801f.ts.net | /weather* | 127.0.0.1:9090 | weatherhermes | Tailnet | Built-in | N/A | N/A | Tailscale | GREEN |
| R03 | agent0.taile6801f.ts.net | /weather2* | 127.0.0.1:9091 | btc5m-bot | Tailnet | Built-in | N/A | SSE/flush | Tailscale | GREEN |
| R04 | agent0.taile6801f.ts.net | / → /dashboard | redir | — | Tailnet | — | — | — | Tailscale | GREEN |
| R05 | trade.taile6801f.ts.net | /* | 127.0.0.1:8081 | freqforge-canary | Tailnet | Freqtrade UI | /api/v1/* | flush | Tailscale | YELLOW |
| R06 | regime-hybrid.taile6801f.ts.net | /* | 127.0.0.1:8085 | regime-hybrid | Tailnet | Freqtrade UI | /api/v1/* | flush | Tailscale | YELLOW |
| R07 | webserver.taile6801f.ts.net | /* | 127.0.0.1:8180 | webserver | Tailnet | Freqtrade UI | /api/v1/* | flush | Tailscale | YELLOW |
| R08 | rizzcoach.taile6801f.ts.net | /* | 127.0.0.1:8088 | rizzcoach-app | Tailnet | Next.js | /api/* | N/A | Tailscale | YELLOW |
| R09 | momentum.taile6801f.ts.net | /* | 404 "disabled" | — | Tailnet | — | — | — | — | RED (stale) |

### Unrouted Services (localhost only, no Caddy route)

| Service | Port | Container | Should be routed? | Notes |
|---|---|---|---|---|
| FreqForge Main | 8086 | freqforge | Possibly | Active bot, no Tailnet route |
| FreqAI Rebel | 8087 | freqai-rebel | Possibly | Active bot, no Tailnet route |
| AI-Hedge-Fund | 8410 | ai-hedge-fund | Probably not | Internal signal engine |
| Hermes-Green Dashboard | 8083 | hermes-green (9119) | Possibly | Hermes TUI/Dashboard |
| Hermes-Green Agent | 8642 | hermes-green | No | Internal agent API |
| Polymarket-Fadi | 9092 | polymarket-fadi | Possibly | Paper trading frontend |
| Claude-Worker | 5050 | claude-worker | No | Internal worker |
| green-mem0 | 8788 | green-mem0 | No | Internal memory API |
| green-ollama | — | green-ollama | No | Internal LLM |
| green-qdrant | — | green-qdrant | No | Internal vector DB |
| docker-proxy | — | docker-proxy | No | Internal Docker API |

---

## 4. Port & Listener Matrix

| Port | Bound To | Container | Purpose | Publicly Exposed? |
|---|---|---|---|---|
| 3000 | 127.0.0.1 | trading-caddy-1 | Caddy HTTP listener | No (Tailnet only) |
| 5000 | 127.0.0.1 | trading-dashboard | Flask trading dashboard | No (via Caddy) |
| 5050 | 127.0.0.1 | claude-worker | Claude worker API | No |
| 8081 | 127.0.0.1 | freqforge-canary | Freqtrade UI (canary) | No (via Caddy) |
| 8083 | 127.0.0.1 | hermes-green | Hermes Dashboard (9119 mapped) | No |
| 8085 | 127.0.0.1 | regime-hybrid | Freqtrade UI | No (via Caddy) |
| 8086 | 127.0.0.1 | freqforge | Freqtrade UI (main) | No |
| 8087 | 127.0.0.1 | freqai-rebel | Freqtrade UI (rebel) | No |
| 8088 | 127.0.0.1 | rizzcoach-app | RizzCoach Next.js | No (via Caddy) |
| 8180 | 127.0.0.1 | webserver | Freqtrade Webserver mode | No (via Caddy) |
| 8410 | 127.0.0.1 | ai-hedge-fund | Signal engine API | No |
| 8642 | 127.0.0.1 | hermes-green | Hermes Agent API | No |
| 8788 | 127.0.0.1 | green-mem0 | Mem0 memory API | No |
| 9090 | 127.0.0.1 | weatherhermes | Weather dashboard | No (via Caddy) |
| 9091 | 127.0.0.1 | btc5m-bot | BTC 5m bot dashboard | No (via Caddy) |
| 9092 | 127.0.0.1 | polymarket-fadi | Polymarket frontend | No |

**ALL ports bound to 127.0.0.1. Zero public exposure.** ✅

---

## 5. Health Check Results

| Service | Method | Result | Verdict |
|---|---|---|---|
| green-mem0 | `GET /health` via 172.26.0.11:8787 | `{"status":"ok","backend":"local-mem0","vector_store":"qdrant",...}` | GREEN |
| green-qdrant | `GET /healthz` via 172.26.0.10:6333 | `healthz check passed` | GREEN |
| green-ollama | `GET /api/version` via 172.26.0.2:11434 | `{"version":"0.24.0"}` | GREEN |
| hermes-green | `GET /health` via 172.26.0.13:8642 | `{"status":"ok","platform":"hermes-agent"}` | GREEN |
| ai-hedge-fund | `GET /health` via 172.26.0.12:8080 | `{"status":"ok","signal_file_exists":true,"signal_age_seconds":517}` | GREEN |
| All Freqtrade bots | Docker healthcheck | All report "healthy" | GREEN |
| weatherhermes | Docker healthcheck | "healthy" | GREEN |
| btc5m-bot | Docker healthcheck | "healthy" | GREEN |
| rizzcoach | Docker healthcheck | "healthy" | GREEN |
| claude-worker | Docker healthcheck | "healthy" | GREEN |

---

## 6. Auth & Exposure Review

### Authentication Boundaries

| Boundary | Mechanism | Status |
|---|---|---|
| Tailnet → Caddy | Tailscale identity headers (Tailscale-User-Login, Tailscale-User-Name) | Active |
| Caddy → Backend | No additional auth (trusts Tailnet) | By design |
| Host → Container | All ports bound to 127.0.0.1 | Verified |
| Container → Container | Docker internal networks (hermes-net, proxy-net, etc.) | Isolated |
| Public internet | No ports exposed (0.0.0.0 binding) | Verified |

**Verdict: GREEN.** No public exposure. All routes require Tailscale auth. Internal services on Docker-internal networks.

---

## 7. Log Findings

### Active Errors

| Service | Error Pattern | Severity | Frequency | Impact |
|---|---|---|---|---|
| ALL Freqtrade bots (4x) | `telegram.error.Conflict: terminated by other getUpdates request` | P1 | Continuous | Telegram notification delivery degraded for all bots |
| hermes-green | `Telegram polling conflict (1/5)` | P1 | Every ~20s | Hermes Telegram delivery competing with bots |
| rizzcoach-app | `Failed to save session: PrismaClientKnownRequestError` | P2 | Intermittent | Session persistence failures |
| rizzcoach-app | `Failed to fetch profile workspaces` | P2 | Intermittent | Workspace data unavailable |
| green-mem0 | `Error parsing extraction response: Unterminated string` | P3 | Rare | Single extraction failure, self-healing |
| ai-hedge-fund | `BrokenPipeError: [Errno 32] Broken pipe` | P4 | Rare | Transient client disconnect |
| trading-caddy-1 | Old 502 errors to ports 8082/8084/8092 | P4 | Historical | Pre-restart, now resolved |
| trading-caddy-1 | `aborting with incomplete response` for 8081/8085/8180 | P4 | Occasional | Slow Freqtrade UI + client timeout |

### Telegram Conflict Root Cause
Multiple Freqtrade bots share the same Telegram bot token OR have competing long-poll sessions.
When hermes-green also polls the same token, all instances conflict. This is a known architectural issue
documented in previous sessions.

---

## 8. Broken/Stale/Duplicate Routes

| Route | Issue | Verdict |
|---|---|---|
| R09 momentum.taile6801f.ts.net | Returns static 404 "disabled". No backend exists. Stale route. | RED |
| agent0.taile6801f.ts.net /favicon.ico | No handler in current Caddyfile. Falls through to empty response. | P4 |
| trade.taile6801f.ts.net | Proxies to canary (8081), not main freqforge (8086). Naming mismatch? | P3 |

### Caddyfile Route Hygiene Notes
- The Caddyfile was recently migrated from subpath routing (agent0.taile6801f.ts.net/trade, /momentum, etc.)
  to per-hostname routing (trade.taile6801f.ts.net, momentum.taile6801f.ts.net, etc.)
- Old 502 errors from before the migration are still in Caddy logs (historical only)
- `handle_path` strips the path prefix before forwarding — this is correct for /dashboard*, /weather*, /weather2*
- No TLS termination needed — Tailscale handles TLS at the funnel layer, Caddy only sees HTTP on localhost

---

## 9. Documentation Findings

### Existing Relevant Docs
- `docs/context/trading-dashboard-surface-audit-20260603.md` — describes dashboard.py surface ✅
- `docs/context/bot-mapping.md` — authoritative bot A-D mapping ✅
- `docs/context/trading-dashboard-external-access-20260602.md` — external access notes ✅
- `docs/context/system-lageplan-2026-06-02.md` — system layout ✅

### Missing Documentation
1. **No canonical route-map document** — which Tailnet hostnames map to which containers/ports
2. **No Caddyfile documentation** — no comments explaining route topology or migration history
3. **No routing intent matrix** — which services SHOULD be routed vs localhost-only
4. **No RizzCoach deployment docs** — compose file inaccessible from Hermes container
5. **No Polymarket deployment docs** — no compose file found in search paths
6. **No compose inventory overview** — 9 compose files scattered across project, no index

---

## 10. Technical Debt & Gaps

| ID | Severity | Description | Risk |
|---|---|---|---|
| GAP-01 | P1 | Telegram polling conflicts — all bots + hermes-green competing | Notification delivery degraded |
| GAP-02 | P2 | RizzCoach SQLite DB busy/locking errors | Session loss, user-visible errors |
| GAP-03 | P2 | Stale momentum route in Caddyfile | Operator confusion, 502 noise |
| GAP-04 | P2 | 6 services unrouted (no Tailnet access) | Inconvenient for remote ops |
| GAP-05 | P3 | No canonical route-map documentation | Knowledge silo, onboarding friction |
| GAP-06 | P3 | No Caddyfile comments/documentation | Maintenance burden |
| GAP-07 | P3 | green-mem0 LLM extraction parsing errors | Memory quality degradation |
| GAP-08 | P4 | trade.taile6801f.ts.net → canary, not main | Naming confusion |
| GAP-09 | P4 | Old Caddyfile 502 errors still in logs | Log noise |

---

## 11. Recommended Fix Plan

### Batch 1 (Low Risk, High Value)
| # | Fix | Risk | Impact | Rollback | Validation |
|---|---|---|---|---|---|
| 1 | Remove stale momentum route from Caddyfile (or document as intentional) | Minimal | Cleaner routing, less log noise | Re-add the block | `curl -sS -I https://momentum.taile6801f.ts.net/` should 404 cleanly |
| 2 | Add comments to Caddyfile explaining each route block | None | Better maintainability | Remove comments | Visual inspection |

### Batch 2 (Medium Risk, High Value)
| # | Fix | Risk | Impact | Rollback | Validation |
|---|---|---|---|---|---|
| 3 | Resolve Telegram polling conflicts (assign unique tokens or schedule non-overlapping polls) | Medium — bot restarts needed | Reliable notifications for all bots | Restore old config | `docker logs --tail 50 <bot>` shows no Conflict errors |
| 4 | Create canonical route-map doc (this report can serve as v1) | None | Onboarding, auditability | Remove doc | File exists and is accurate |

### Batch 3 (Lower Priority)
| # | Fix | Risk | Impact | Rollback | Validation |
|---|---|---|---|---|---|
| 5 | Add Caddy routes for freqforge (8086) and freqai-rebel (8087) if Tailnet access desired | Low | Remote access to all bot UIs | Remove routes | `curl` via Tailnet returns 200 |
| 6 | Investigate RizzCoach DB locking (SQLite → PostgreSQL?) | Medium | Stable sessions | Revert DB | No PrismaClientKnownRequestError in logs |
| 7 | Investigate green-mem0 extraction error (LLM output truncation) | Low | Better memory quality | N/A | No parsing errors in 24h |

---

## 12. Do-Not-Touch / High-Risk Areas

| Area | Why |
|---|---|
| Caddy host network mode | Changing this breaks all routing. Requires careful testing. |
| Docker socket proxy (proxy-net) | Internal security boundary. Do not modify ACLs without review. |
| Tailscale Funnel/Serve config | Manages external TLS. Modifying without understanding breaks Tailnet routing. |
| green-stack (mem0, ollama, qdrant) | Memory infrastructure. Data loss risk if recreated without backup. |
| Freqtrade .env.freqtrade | Contains exchange credentials. Never expose or modify. |
| Trading bot configs | Changes require explicit approval per SOUL.md rules. |

---

## 13. Exact Evidence Appendix

### Commands Executed
```bash
# Phase 0
date -u && hostname && whoami && pwd && uname -a
git -C /home/hermes/projects/trading status --short
git -C /home/hermes/projects/trading branch --show-current

# Phase 1
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
ss -ltnp
find /home/hermes/projects/trading -maxdepth 4 \( -iname '*compose*.yml' -o -iname 'Caddyfile' \)

# Phase 2
cat /home/hermes/projects/trading/Caddyfile
docker inspect --format '...' (per container)
docker network ls --format '{{.Name}}\t{{.Scope}}'

# Phase 3
curl -sS --max-time 3 http://<IP>:<PORT>/<path> (per service)
docker exec trading-caddy-1 wget -qO- http://localhost:2019/config/

# Phase 4
cat /home/hermes/projects/trading/docker-compose.yml
head -60 /home/hermes/projects/trading/dashboard.py

# Phase 5
docker logs --tail 50 <container> | grep -iE 'error|exception|failed|...'
```

### Key Evidence Snippets

**Caddyfile (current, 48 lines):**
- 9 route blocks on :3000 (127.0.0.1 only)
- agent0 host: /dashboard, /weather, /weather2 + redirect
- Dedicated hosts: trade, momentum (404), regime-hybrid, webserver, rizzcoach

**Telegram Conflict (repeated across 5 containers):**
```
telegram.error.Conflict: terminated by other getUpdates request;
make sure that only one bot instance is running
```

**RizzCoach DB Error:**
```
Failed to save session: Error [PrismaClientKnownRequestError]:
Failed to fetch profile workspaces: Error [PrismaClientKnownRequestError]:
```

**Health Response (green-mem0):**
```json
{"status":"ok","backend":"local-mem0","vector_store":"qdrant",
 "llm_provider":"ollama","llm_model":"gpt-oss:120b",
 "embedder_provider":"ollama","embedder_model":"qwen3-embedding:4b",
 "cloud_required":false}
```
