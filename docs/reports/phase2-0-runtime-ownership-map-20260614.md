# Phase 2.0 — Runtime Ownership Map Audit

**Date:** 2026-06-14
**Author:** Hermes Trading Orchestrator
**Operation Level:** L0 (read-only audit)
**Scope:** All running Docker containers on the trading host
**Related Issues:** #200 (OPEN — Runtime Ownership), #44 (CLOSED parent), #176 (CLOSED Stage A), #201 (P2 hardening)
**Related PRs:** #216 (merged — roadmap v2 canonical)

---

## 1. Executive Verdict

**Status: YELLOW**

The SI v2 Scheduled Observation Loop is **GREEN** and operational. 27 fleet
cycles have been completed with 0 mutations across all counters. The controller
remains safely `PAUSED / L3_REPOSITORY_ONLY`.

However, **7 of 20 running containers have no Compose ownership labels** and
cannot be managed by `docker compose` lifecycle commands. Of these 7:

- **4 are adopt candidates** — service definitions already exist in
  `docker-compose.yml` but the running instances were started outside Compose
  (`docker run`), so they lack `com.docker.compose.project` labels.
- **3 are external to the trading project** — they run on the `ki-fabrik`
  network with mounts pointing to other user directories.

This drift does not currently break the SI v2 loop, does not create live-trading
risk, and does not require immediate runtime mutation. It is a governance and
reproducibility blocker: if the host were rebuilt from `docker-compose.yml`
alone, these containers would not be recreated, and their state would be lost.

**No adopt action is authorized by this report.** Any adoption requires
separate explicit approval because it may involve Compose edits or container
recreation.

---

## 2. Repository Baseline

| Property | Value |
|----------|-------|
| Repository | `GoLukeEnviro/trading-hub` |
| Main HEAD | `202d45e8955e0629121f3ef4a339d3914e5724da` |
| Canonical roadmap | `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` (PR #216, merged 2026-06-14) |
| Live trading state | `LIVE_FORBIDDEN` |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |

---

## 3. Issue Reconciliation

| Issue | Title | Status | Role |
|-------|-------|--------|------|
| #44 | Parent / Stage 0 | CLOSED | Not a blocker. Historical parent. |
| #200 | Runtime Ownership | OPEN | **Current top Runtime Ownership blocker.** |
| #176 | Stage A | CLOSED | Stage A complete. Stage B deferred. |
| #201 | Hardening | OPEN (P2) | Hardening, not an immediate blocker. |

---

## 4. SI v2 Scheduled Loop Truth

| Metric | Value |
|--------|-------|
| Total fleet cycles completed | 27 |
| Latest cycle | `active_cycle_20260614T204852Z` |
| Total bots | 4 |
| Ping OK | 4 / 4 |
| Ping failed | 0 |
| Status authenticated | 4 / 4 |
| Shadow proposals | 0 |
| Fleet verdict | `GREEN` |
| Runtime mutations | 0 |
| Config mutations | 0 |
| Live-trading mutations | 0 |
| Docker mutations | 0 |
| Strategy mutations | 0 |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |
| Secrets in bundle | No |

**Conclusion:** The SI v2 loop is healthy and the controller is safely isolated.
#200 does **not** currently break the scheduled observation loop.

### Rainbow (External Signals)

| Metric | Value |
|--------|-------|
| Runtime source status | `SUCCESS` (read_only) |
| Signal count | 3 |
| Symbols | SOL/USDT, ETH/USDT, BTC/USDT |
| Confidence avg | 0.85 |
| Scoring gate | 0 / 10 — **blocked by producer freshness**, not plumbing |

The `read_only` pipeline landed via PRs #212–#215. The scoring gate remains
0/10 because the upstream `signals.db` producer is stale. This is a separate
blocker from #200 and does not affect loop health.

---

## 5. Controller Isolation Truth

The controller is `PAUSED / L3_REPOSITORY_ONLY`. It performs repository-only
operations and does not issue runtime mutations, config changes, or Docker
commands.

Stage B controller isolation (hardening before activation) is **future work**,
not a current loop blocker. The controller is not activated and cannot act
beyond repository operations.

---

## 6. Compose File Inventory

| File | Project | Services defined | Status |
|------|---------|-----------------|--------|
| `docker-compose.yml` | `trading` | 15 | Canonical fleet compose |
| `orchestrator/guardian/docker-compose.yml` | `guardian` | 1 | Guardian service |
| `freqtrade/docker-compose.fleet.yml` | (reference) | — | Fleet template, not primary |
| `freqtrade/bots/freqai-rebel/docker-compose.yml` | (reference) | — | Bot-specific override |
| 7× `docker-compose.yml.bak*` | — | — | Historical backups |

### Services defined in `docker-compose.yml` (project: `trading`)

| # | Service | Running? | Managed? |
|---|---------|----------|----------|
| 1 | `docker-proxy` | Yes | Yes |
| 2 | `trading-dashboard` | Yes | Yes |
| 3 | `ai-hedge-fund` | Yes | Yes |
| 4 | `hermes-green` | Yes | Yes |
| 5 | `green-qdrant` | Yes | **No** (label drift) |
| 6 | `green-ollama` | Yes | **No** (label drift) |
| 7 | `green-mem0` | Yes | **No** (label drift) |
| 8 | `freqtrade-freqforge` | Yes | Yes |
| 9 | `freqtrade-regime-hybrid` | Yes | Yes |
| 10 | `freqtrade-freqforge-canary` | Yes | Yes |
| 11 | `freqai-rebel` | Yes | Yes |
| 12 | `freqtrade-webserver` | Yes | Yes |
| 13 | `hermes-watchdog` | Yes | **No** (label drift) |
| 14 | `caddy` | Yes | Yes |
| 15 | `shadowlock` | Yes | Yes |

**Key finding:** Services 5, 6, 7, and 13 are **defined in** `docker-compose.yml`
but the running containers lack Compose labels. They were started outside Compose
(via `docker run` or a wrapper script), creating an ownership mismatch.

---

## 7. Running Container Inventory

20 containers were observed at audit time.

| # | Container | Image | Status | Compose Project |
|---|-----------|-------|--------|-----------------|
| 1 | `trading-docker-proxy-1` | `tecnativa/docker-socket-proxy:latest` | Up 5 days | trading |
| 2 | `trading-dashboard` | `trading-dashboard:stable` | Up 5 days (healthy) | trading |
| 3 | `trading-ai-hedge-fund-1` | `trading-ai-hedge-fund-crypto:hermes1337-c3` | Up 2 days (healthy) | trading |
| 4 | `hermes-green` | `nousresearch/hermes-agent:c11.2-hermes-home` | Up 2 days | trading |
| 5 | `trading-caddy-1` | `caddy:alpine` | Up 5 days | trading |
| 6 | `trading-freqtrade-freqforge-1` | `freqtrade-hermes1337:freqforge-c5` | Up 9 hours | trading |
| 7 | `trading-freqtrade-regime-hybrid-1` | `freqtrade-hermes1337:regime-hybrid-c5` | Up 9 hours | trading |
| 8 | `trading-freqtrade-freqforge-canary-1` | `freqtrade-hermes1337:canary-c5` | Up 9 hours | trading |
| 9 | `trading-freqai-rebel-1` | `freqtrade-hermes1337:freqai-rebel-c25` | Up 9 hours | trading |
| 10 | `trading-freqtrade-webserver-1` | `freqtrade-hermes1337:webserver-c5` | Up 2 days | trading |
| 11 | `trading-shadowlock-1` | `shadowlock:hermes1337-c4` | Up 2 days (healthy) | trading |
| 12 | `trading-guardian` | `guardian-trading-guardian` | Up 3 days | guardian |
| 13 | `rizzcoach-app-1` | `rizzcoach-app` | Up 5 days (healthy) | rizzcoach (external) |
| 14 | `btc5m-bot` | `btc5m-bot:latest` | Up 5 days (healthy) | *(none)* |
| 15 | `claude-worker` | `claude-worker:latest` | Up 5 days (healthy) | *(none)* |
| 16 | `green-mem0` | `hermes-mem0-local-api:stable` | Up 4 days (healthy) | *(none)* |
| 17 | `green-ollama` | `ollama/ollama:latest` | Up 5 days (healthy) | *(none)* |
| 18 | `green-qdrant` | `qdrant/qdrant:latest` | Up 5 days | *(none)* |
| 19 | `trading-hermes-watchdog-1` | `alpine:latest` | Up 4 days | *(none)* |
| 20 | `weatherhermes` | `weatherhermes:latest` | Up 5 days (healthy) | *(none)* |

---

## 8. Compose Project Grouping

| Compose Project | Config File | Working Dir | Container Count |
|----------------|-------------|-------------|-----------------|
| `trading` | `/home/hermes/projects/trading/docker-compose.yml` | `/home/hermes/projects/trading` | 11 |
| `guardian` | `orchestrator/guardian/docker-compose.yml` | `orchestrator/guardian` | 1 |
| `rizzcoach` | `/home/claudio/rizzcoach/docker-compose.yml` | `/home/claudio/rizzcoach` | 1 |
| *(unmanaged)* | — | — | 7 |
| **Total** | | | **20** |

---

## 9. Unmanaged Container Drift

7 containers have no `com.docker.compose.project` label.

### Adopt Candidates (4)

These services are **already defined in `docker-compose.yml`** but the running
containers were started outside Compose. Adoption means bringing them under
Compose management (recreate with `docker compose up`).

| Container | Compose Service | Image | Network | Why Unmanaged |
|-----------|----------------|-------|---------|---------------|
| `green-mem0` | `green-mem0` | `hermes-mem0-local-api:stable` | `trading_hermes-net` | Started via `docker run`, not `docker compose up`. Service definition exists but labels missing. |
| `green-ollama` | `green-ollama` | `ollama/ollama:latest` | `trading_hermes-net` | Same pattern. Service defined, labels missing. |
| `green-qdrant` | `green-qdrant` | `qdrant/qdrant:latest` | `trading_hermes-net` | Same pattern. Service defined, labels missing. |
| `trading-hermes-watchdog-1` | `hermes-watchdog` | `alpine:latest` | `trading_hermes-net` | Started via `docker run` with inline command. Service defined in compose, labels missing. |

**Adoption risk:** Recreating these containers under Compose will briefly
interrupt the service. Data volumes (`green-ollama-data`, `green-qdrant-data`,
`trading_watchdog-logs`) must be verified against the compose volume mappings
before recreation. Requires explicit approval.

### External / Document-Only Candidates (3)

These containers belong to other projects or users. They are **not** defined in
the trading `docker-compose.yml` and should remain outside trading-project
ownership.

| Container | Image | Network | Mount Source | Owner Evidence |
|-----------|-------|---------|-------------|----------------|
| `btc5m-bot` | `btc5m-bot:latest` | `ki-fabrik` | `btc5m-data` volume | Separate project, `ki-fabrik` network. No trading compose reference. |
| `claude-worker` | `claude-worker:latest` | `ki-fabrik` | `/home/claudio/agent-zero-fork` | Mount points to `/home/claudio/` — different user/project. |
| `weatherhermes` | `weatherhermes:latest` | `ki-fabrik` | `weatherhermes-data` volume | Separate project, `ki-fabrik` network. |

**Recommendation:** Document these as external dependencies in
`docs/state/current-operational-state.md` so they are tracked but not adopted.

### Unknown / Needs Proof (0)

No containers were classified as unknown. All 7 unmanaged containers were
definitively classified.

---

## 10. Volume / Mount / Network Authority Map

### Named Volumes (trading-relevant)

| Volume | Used By | Authority |
|--------|---------|-----------|
| `freqforge_data` | `trading-freqtrade-freqforge-1` | Compose-managed |
| `regime_hybrid_data` | `trading-freqtrade-regime-hybrid-1` | Compose-managed |
| `freqforge_canary_data` | `trading-freqtrade-freqforge-canary-1` | Compose-managed |
| `freqai_rebel_data` / `freqai-rebel-data` | `trading-freqai-rebel-1` | Compose-managed |
| `shared-signals` | `ai-hedge-fund`, signal consumers | Compose-managed |
| `shared-data` | Multiple trading services | Compose-managed |
| `fleet-dashboard-data` | `trading-dashboard` | Compose-managed |
| `trading_caddy-data` / `trading_caddy-config` | `trading-caddy-1` | Compose-managed |
| `green-ollama-data` | `green-ollama` | **Unmanaged** (adopt candidate) |
| `green-qdrant-data` | `green-qdrant` | **Unmanaged** (adopt candidate) |
| `trading_watchdog-logs` | `trading-hermes-watchdog-1` | **Unmanaged** (adopt candidate) |
| `btc5m-data` | `btc5m-bot` | **External** |
| `weatherhermes-data` | `weatherhermes` | **External** |
| `a0-v2-agents` / `a0-v2-usr` | `claude-worker` | **External** |

### Networks

| Network | Containers | Authority |
|---------|-----------|-----------|
| `trading-network` | Trading fleet services | Compose-managed |
| `trading_hermes-net` | hermes-green, green-*, watchdog, shadowlock | Compose-defined; some members unmanaged |
| `trading_proxy-net` | docker-proxy, caddy | Compose-managed |
| `ki-fabrik` | btc5m-bot, claude-worker, weatherhermes | **External** — separate host network |
| `hermes_memory` | (local-memory stack) | External |

---

## 11. SI v2 Scheduler / Wrapper Authority

| Script | Path | Schedule | Authority |
|--------|------|----------|-----------|
| SI v2 Active Cycle | `orchestrator/scripts/si_v2_active_cycle_cron.sh` | Every 6 hours (Hermes cron) | Hermes scheduler |
| SI Bot A Daily | `orchestrator/scripts/si_bot_a_daily.sh` | Daily | Hermes scheduler |
| SI Bot B Daily | `orchestrator/scripts/si_bot_b_daily.sh` | Daily | Hermes scheduler |

The SI v2 loop runs via the Hermes cronjob scheduler. It invokes read-only
fleet inspection, signal analysis, and shadow proposal generation. It does not
perform runtime mutations.

---

## 12. SI v2 Loop Impact

The 7 unmanaged containers do **not** participate in the SI v2 loop's decision
pathway. The loop interacts with:

- 4 Freqtrade bots (all Compose-managed, `GREEN`)
- `ai-hedge-fund` signal core (Compose-managed, `healthy`)
- `shadowlock` evidence layer (Compose-managed, `healthy`)

The unmanaged `green-*` containers (mem0/ollama/qdrant) are used by the Hermes
local-memory stack, not by the SI v2 trading loop. The watchdog container
monitors Freqtrade bot health but is not in the loop's decision chain.

**Conclusion:** #200 ownership drift has **zero impact** on the current SI v2
scheduled observation loop correctness.

---

## 13. Risk Classification

| Category | Level | Finding |
|----------|-------|---------|
| SI v2 loop health | **GREEN** | 27 cycles, 0 mutations, fleet GREEN, controller PAUSED |
| Unmanaged-container drift | **YELLOW** | 7 containers lack compose labels; 4 are adoptable, 3 are external |
| Rainbow producer freshness | **YELLOW** | Scoring gate 0/10 due to stale `signals.db`; pipeline plumbing is sound |
| Live-trading risk | **GREEN** | No live trading, no `dry_run=false`, no secrets exposed |
| Secret/socket risk | **GREEN** | No fresh evidence of secret or socket exposure |
| Controller safety | **GREEN** | Controller PAUSED / L3_REPOSITORY_ONLY, isolation intact |

**Overall: YELLOW** — system is operationally safe but has governance/reproducibility gaps that should be resolved before any host rebuild or live-readiness evaluation.

---

## 14. Minimal Remediation Plan

### Phase A — Document (this PR)

This report establishes the ownership map, drift classification, and
remediation plan as a versioned repo artifact. No runtime action.

### Phase B — Adopt 4 compose-defined containers (requires approval)

Recreate `green-mem0`, `green-ollama`, `green-qdrant`, and `hermes-watchdog`
under Compose management so they acquire proper labels.

**Steps (per container):**
1. Verify the compose service definition matches the running container's config (image, volumes, network, environment).
2. Snapshot current container config: `docker inspect <container>`.
3. Stop and remove the unmanaged container.
4. Recreate via `docker compose up -d <service>`.
5. Verify labels present: `docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' <container>`.
6. Verify health check passes.

**Risk:** Brief downtime per container. Data volumes persist (named volumes).
Requires explicit approval.

### Phase C — Document 3 external containers

Add `btc5m-bot`, `claude-worker`, `weatherhermes` to the external-dependencies
section of `docs/state/current-operational-state.md` as known-but-not-owned.
No adoption needed.

### Phase D — Verify ownership via drift monitor

After Phase B, run the ownership drift monitor
(`orchestrator/scripts/hermes_ownership_drift_monitor.py`) to confirm the
managed count is 15 and unmanaged count is reduced to the 3 external containers
(plus `rizzcoach` which is managed by a different project).

---

## 15. Rollback / Safety Notes

- **This PR is documentation-only.** No runtime state is changed. Rollback is
  simply reverting the file.
- Phase B adoption has a rollback path: if `docker compose up` fails, the
  container can be recreated from the `docker inspect` snapshot or from the
  compose service definition.
- Named volumes (`green-ollama-data`, `green-qdrant-data`,
  `trading_watchdog-logs`) are independent of container lifecycle and survive
  container recreation.
- No data deletion, no volume removal, no network changes are proposed.

---

## 16. Issue-Ready Follow-ups

| Follow-up | Scope | Approval | Blocks |
|-----------|-------|----------|--------|
| Adopt 4 containers into Compose | Phase B | Required (L3) | Closes the adopt-candidate portion of #200 |
| Document 3 external containers | Phase C | Not needed (L2) | Completes #200 documentation |
#201 hardening | P2 | Not needed now | Future |
| Stage B controller isolation | Future | Required (L3) | Required before controller activation |
| Rainbow producer freshness | Separate | TBD | Unblocks scoring gate |

---

## 17. Exact Next Recommended Task

**Decision gate: Which of the 7 unmanaged containers are adopted?**

This report provides the evidence. The next step is a **separate approval
decision**:

1. **Adopt** (4): `green-mem0`, `green-ollama`, `green-qdrant`,
   `trading-hermes-watchdog-1` — already defined in `docker-compose.yml`,
   just need Compose-managed recreation.
2. **External / document-only** (3): `btc5m-bot`, `claude-worker`,
   `weatherhermes` — add to external-dependency docs.

Upon approval for Phase B adoption, execute the per-container adoption sequence
from Section 14 with snapshot → recreate → verify → log.

No adopt action is authorized by this report alone.
