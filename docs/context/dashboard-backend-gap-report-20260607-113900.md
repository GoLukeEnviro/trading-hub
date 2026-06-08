# Dashboard-Backend Gap Report — 2026-06-07 11:39 UTC

**Healthscore:** 78/100 — YELLOW
**Scope:** 20 containers, 9 Caddy routes, 14 localhost ports, 0 public ports

---

## Gap Summary

| Gap ID | Severity | Service | Symptom | Root Cause | Risk | Fix Recommendation | Validation |
|---|---|---|---|---|---|---|---|
| GAP-01 | **P1** | ALL Freqtrade bots + hermes-green | Telegram `Conflict: terminated by other getUpdates request` | Multiple bot instances polling same Telegram token simultaneously | Notification delivery unreliable across entire fleet | Investigate token separation or staggered polling; known issue from prior sessions | `docker logs --tail 50 <bot> 2>&1 \| grep -c Conflict` == 0 |
| GAP-02 | **P2** | rizzcoach-app-1 | `PrismaClientKnownRequestError` on session save & workspace fetch | SQLite busy/locking under concurrent access | Session loss, degraded UX | Consider SQLite WAL mode or migration to PostgreSQL | No PrismaClientKnownRequestError in 24h logs |
| GAP-03 | **P2** | trading-caddy-1 | momentum.taile6801f.ts.net returns static 404, no backend exists | Stale route from decommissioned Momentum bot | Operator confusion, log noise | Remove route block from Caddyfile or add comment marking as decommissioned | `curl` returns clean 404 or route removed |
| GAP-04 | **P2** | 6 services | FreqForge (8086), Rebel (8087), AI-Hedge (8410), Hermes Dash (8083), Polymarket (9092), Claude (5050) have no Caddy route | Never added after migration to per-hostname routing | Inconvenient remote access | Add Caddy routes for services that need Tailnet access; document intent for rest | New routes return 200 via Tailnet |
| GAP-05 | **P3** | Docs | No canonical route-map document existed before this audit | Documentation gap | Knowledge silo, onboarding friction | This report serves as v1; keep updated on route changes | File exists at `docs/context/dashboard-backend-route-map-*` |
| GAP-06 | **P3** | Caddyfile | Zero comments in Caddyfile explaining route topology | No documentation convention | Maintenance burden, risk of accidental breaking changes | Add inline comments per route block | Visual inspection |
| GAP-07 | **P3** | green-mem0 | `Error parsing extraction response: Unterminated string` | LLM output truncation during memory extraction | Occasional memory quality degradation | Monitor; if persistent, increase LLM max_tokens or add retry logic | No parsing errors in 24h |
| GAP-08 | **P4** | trade.taile6801f.ts.net | Routes to canary (8081), not main freqforge (8086) | Naming from old subpath era where "trade" meant canary | Naming confusion | Rename to `canary.taile6801f.ts.net` or document explicitly | Caddyfile comment explains naming |
| GAP-09 | **P4** | trading-caddy-1 | Old 502 errors (ports 8082/8084/8092) still visible in logs | Pre-migration Caddyfile config | Log noise only | No action needed; logs rotate naturally | Stale errors age out of log buffer |

---

## Safest Next Fix Batch

### Immediate (Read-only safe, zero risk):
1. **Create this documentation** ✅ DONE
2. Add Caddyfile comments explaining each route

### Next Sprint (Low risk, requires Caddy reload):
3. Remove stale momentum route from Caddyfile
4. Clarify trade.taile6801f.ts.net → canary naming (comment or rename)

### Requires Coordination (Medium risk):
5. Telegram polling conflict resolution (may need bot token separation)
6. RizzCoach DB investigation
7. Add Tailnet routes for FreqForge main + Rebel if desired

### Do NOT Touch:
- Caddy host network mode
- Docker socket proxy ACLs
- green-stack data volumes (mem0, qdrant, ollama)
- Freqtrade .env.freqtrade
- Any trading bot config without explicit approval
