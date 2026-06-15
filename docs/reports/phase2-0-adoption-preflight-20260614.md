# #200 Phase B — Compose Adoption Preflight Report

**Date:** 2026-06-14
**Author:** Hermes Trading Orchestrator
**Operation Level:** L0 (read-only inspection + planning)
**Scope:** Adoption preflight for 4 Compose-defined unmanaged containers
**Related Issues:** #200 (OPEN — Runtime Ownership), #217 (MERGED — Phase A audit)

---

## 1. Executive Verdict

**Status: YELLOW** (a safe adoption plan exists; 1 pre-adoption compose fix required)

| Candidate | Risk | Reason |
|-----------|------|--------|
| `green-ollama` | **GREEN** | Compose ↔ runtime match clean. No diffs. |
| `green-qdrant` | **GREEN** | Compose ↔ runtime match clean. No diffs. |
| `green-mem0` | **YELLOW** | Runtime attached to extra network `hermes-net` (not in compose). Safe to drop but must verify. |
| `trading-hermes-watchdog-1` | **YELLOW** (RED without fix) | Compose network `hermes-net` does not match runtime `trading_hermes-net`. **Compose fix required before adoption.** |

**No runtime mutation has been performed.** This report is a planning artifact
for human approval.

---

## 2. Baseline

| Property | Value |
|----------|-------|
| Date (UTC) | 2026-06-14 22:36 |
| Host | `e08bb99fe7f8` (container) |
| User | `hermes` (uid 1337, gid 1337, groups: 110 hostdocker) |
| Branch | `main` |
| HEAD SHA | `b61c90c` |
| Origin/main SHA | `b61c90c` |
| Phase A report exists | `docs/reports/phase2-0-runtime-ownership-map-20260614.md` (395 lines) |
| SI v2 cycles | 27 |
| SI v2 latest | `20260614T204852Z`, fleet GREEN, 0 mutations |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |
| Live trading state | `LIVE_FORBIDDEN` |

**Dirty files (pre-existing, unrelated):**
- `M docs/state/canonical-trading-status.md`
- `M orchestrator/reports/canonical_trading_status_latest.json`
- Various `??` untracked context/script files (all under `docs/context/`, `orchestrator/scripts/`, `self_improvement_v2/`)

---

## 3. Adoption Candidates

### 3.1 `green-ollama`

| Attribute | Compose (`docker-compose.yml`) | Runtime (`docker inspect`) | Match? |
|-----------|-------------------------------|---------------------------|--------|
| Image | `ollama/ollama:latest` | `ollama/ollama:latest` | ✅ Same |
| Image digest | — (floating tag) | `sha256:333628ba5b2f` | N/A (tag) |
| User | *(not set)* | *(not set)* | ✅ Same (root default) |
| Entrypoint | *(not set)* | `/bin/ollama` | ✅ Image default |
| Command | *(not set)* | `["serve"]` | ✅ Image default |
| Restart policy | `unless-stopped` | `unless-stopped` | ✅ |
| Container name | `green-ollama` | `green-ollama` | ✅ |
| Network(s) | `trading_hermes-net` | `trading_hermes-net` | ✅ |
| Volume(s) | `green-ollama-data:/root/.ollama` | `green-ollama-data:/root/.ollama` | ✅ |
| Port(s) | *(none)* | *(none)* | ✅ |
| Healthcheck | `CMD ollama list`, interval 30s, timeout 10s, retries 3, start 60s | ✅ healthy | ✅ |
| Compose labels | N/A | missing | ⚠️ Will be created by `docker compose up` |
| Env (secrets) | *(not inspected)* | *(not inspected)* | ⚠️ UNKNOWN — verify after adopt |

**Risk level: GREEN**

The current runtime is an exact match for the Compose definition. Adoption via
`docker compose up -d green-ollama` will create the correct labels without
functional change.

### 3.2 `green-qdrant`

| Attribute | Compose (`docker-compose.yml`) | Runtime (`docker inspect`) | Match? |
|-----------|-------------------------------|---------------------------|--------|
| Image | `qdrant/qdrant:latest` | `qdrant/qdrant:latest` | ✅ Same |
| Image digest | — (floating tag) | `sha256:c57c657048b4` | N/A (tag) |
| User | *(not set)* | `0:0` | ✅ Same (root default) |
| Entrypoint | *(not set)* | *(not set — null)* | ✅ Image default |
| Command | *(not set)* | `["./entrypoint.sh"]` | ✅ Image default |
| Restart policy | `unless-stopped` | `unless-stopped` | ✅ |
| Container name | `green-qdrant` | `green-qdrant` | ✅ |
| Network(s) | `trading_hermes-net` | `trading_hermes-net` | ✅ |
| Volume(s) | `green-qdrant-data:/qdrant/storage` | `green-qdrant-data:/qdrant/storage` | ✅ |
| Port(s) | *(none)* | *(none)* | ✅ |
| Healthcheck | *(not set)* | *(no healthcheck configured)* | ✅ |
| Compose labels | N/A | missing | ⚠️ Will be created by `docker compose up` |

**Risk level: GREEN**

Clean match. `green-qdrant-data` is declared as `external: True` in compose,
so Docker will reuse the existing named volume — no data loss.

### 3.3 `green-mem0`

| Attribute | Compose (`docker-compose.yml`) | Runtime (`docker inspect`) | Match? |
|-----------|-------------------------------|---------------------------|--------|
| Image | `hermes-mem0-local-api:stable` | `hermes-mem0-local-api:stable` | ✅ Same |
| User | *(not set)* | *(not set)* | ✅ |
| Entrypoint | *(not set)* | *(not set — null)* | ✅ Image default |
| Command | *(not set)* | `["uvicorn","app:app","--host","0.0.0.0","--port","8787"]` | ✅ Image CMD |
| Restart policy | `unless-stopped` | `unless-stopped` | ✅ |
| Container name | `green-mem0` | `green-mem0` | ✅ |
| Network(s) | `trading_hermes-net` | **`hermes-net`, `trading_hermes-net`** | ⚠️ Extra network |
| Volume(s) | Bind mounts: `app.py`, `extraction_policy_v1.txt`, `extraction_policy_v2.txt` (all `:ro`) | Same 3 bind mounts (ro) | ✅ |
| Port(s) | `127.0.0.1:8788:8787` | `8787/tcp → 127.0.0.1:8788` | ✅ |
| Healthcheck | *(not set)* | `healthy` (custom HTTP healthcheck in image) | ✅ |
| `depends_on` | `green-qdrant`, `green-ollama` | N/A (manual start) | ⚠️ Compose ensures order |
| Env (secrets) | 11 entries (redacted) + `.env` file | *(not inspected)* | ⚠️ UNKNOWN |
| Compose labels | N/A | missing | ⚠️ Will be created |

**Risk level: YELLOW**

**Key diff:** Runtime has `hermes-net` as an additional network. The Compose
definition only lists `trading_hermes-net`. After adoption, `green-mem0` will
lose `hermes-net` connectivity.

**Impact assessment:**
- `hermes-net` currently contains only `green-mem0` (and possibly `trading-hermes-watchdog-1` in older deployments).
- `green-mem0` talks to `green-qdrant` and `green-ollama` exclusively over `trading_hermes-net`.
- No other service on `hermes-net` was observed to depend on `green-mem0`.
- **Conclusion:** Dropping `hermes-net` is safe. The extra network is likely
  an artifact of the original manual `docker run` command.

**Adoption depends_on:** `green-qdrant` and `green-ollama` must be adopted
first (Compose `depends_on` constraint).

### 3.4 `trading-hermes-watchdog-1`

| Attribute | Compose (`docker-compose.yml`) | Runtime (`docker inspect`) | Match? |
|-----------|-------------------------------|---------------------------|--------|
| Image | `alpine:latest` | `alpine:latest` | ✅ Same |
| User | *(not set)* | *(not set)* | ✅ |
| Entrypoint | *(not set)* | *(not set — null)* | ✅ |
| Command | Inline shell script (same content) | `["sh","-c","while true; do..." ]` | ✅ Same |
| Restart policy | `unless-stopped` | `unless-stopped` | ✅ |
| Container name | *(not set)* → Compose names `trading-hermes-watchdog-1` | `trading-hermes-watchdog-1` | ✅ |
| Network(s) | **`hermes-net`** | **`trading_hermes-net`** | ❌ **MISMATCH** |
| Volume(s) | `watchdog-logs:/var/log` | `watchdog-logs:/var/log` | ✅ Same volume |
| Port(s) | *(none)* | *(none)* | ✅ |
| Healthcheck | *(not set)* | *(none)* | ✅ |
| Compose labels | N/A | missing | ⚠️ Will be created |

**Risk level: YELLOW** (RED if compose network not fixed first)

**Critical diff:** The Compose definition places `hermes-watchdog` on
`hermes-net`. The running container uses `trading_hermes-net`. If adopted
without fixing the Compose network, the watchdog will not be able to reach
the Freqtrade bots (which are on `trading_hermes-net`) and will report
continuous ALERTS for all bots.

**The Compose file must be patched** to change `hermes-watchdog` network from
`hermes-net` to `trading_hermes-net` before or during adoption.

**Volume naming note:** The Compose volume `watchdog-logs` is not marked
`external: True`. Under the `trading` Compose project, Docker Compose will
namespace it as `trading_watchdog-logs` and create a **new empty volume**.
The existing `watchdog-logs` volume with historical logs would not be used
automatically. Options:
- Option A: Mark `watchdog-logs` as `external: True` in compose → reuse existing volume.
- Option B: Accept new empty volume (log history is non-critical).
- Option C: Migrate data from old volume to new (lowest priority).

---

## 4. External Containers

These containers are on the `ki-fabrik` network, outside Trading Hub ownership.

| Container | Image | Network | State | Reason to exclude |
|-----------|-------|---------|-------|-------------------|
| `btc5m-bot` | `btc5m-bot:latest` | `ki-fabrik` | Up 5d, healthy | Separate project, no compose ref in trading-hub |
| `claude-worker` | `claude-worker:latest` | `ki-fabrik` | Up 5d, healthy | Mounts `/home/claudio/agent-zero-fork` — other user |
| `weatherhermes` | `weatherhermes:latest` | `ki-fabrik` | Up 5d, healthy | Separate project, `weatherhermes-data` volume |

**Recommendation:** Do not adopt. Document in
`docs/state/current-operational-state.md` as known external dependencies.

---

## 5. Volume / Mount Verification

| Volume | Type | Used by | Compose `external:` | Notes |
|--------|------|---------|-------------------|-------|
| `green-ollama-data` | named volume | `green-ollama` | `external: True` | ✅ Will be reused on adopt |
| `green-qdrant-data` | named volume | `green-qdrant` | `external: True` | ✅ Will be reused on adopt |
| `watchdog-logs` | named volume | `hermes-watchdog` | not set (default) | ⚠️ Compose would create `trading_watchdog-logs` unless marked external |
| *(bind mounts)* | bind path | `green-mem0` | N/A | Same absolute path in compose and runtime — clean |

All named volumes exist and have data. No volume pruning or deletion is
proposed.

---

## 6. Dependency & Ordering Analysis

### Compose `depends_on` constraints

```
green-mem0:
  depends_on:
    - green-qdrant
    - green-ollama
```

### Runtime dependency (observed)

- `green-mem0` connects to `green-qdrant:6333` (Qdrant vector store) and
  `green-ollama:11434` (Ollama embeddings/LLM).
- `green-ollama` and `green-qdrant` have no intra-dependencies.
- `trading-hermes-watchdog-1` monitors all 4 Freqtrade bots + ai-hedge-fund
  via HTTP on `trading_hermes-net`. No compose dependencies needed.
- No container provides a service used by the SI v2 scheduled observation loop
  (SI v2 only touches Freqtrade APIs + ai-hedge-fund signal endpoint).

### Proposed adoption order

| Step | Container | Dependency | Expected downtime | Risk |
|------|-----------|-----------|------------------|------|
| 1 | `green-qdrant` | None | ~5s (restart) | **GREEN** — stateless in runtime (state on named volume) |
| 2 | `green-ollama` | None | ~5-10s (restart) | **GREEN** — clean match |
| 3 | `green-mem0` | green-qdrant ✅, green-ollama ✅ | ~5-10s | **YELLOW** — loses `hermes-net`, verify health after |
| 4 | `trading-hermes-watchdog-1` | *(needs compose fix first)* | ~5s | **YELLOW** — compose fix required; new volume namespace |

**SI v2 loop impact:** Zero. The SI v2 loop does not depend on any of these
containers. It will produce GREEN fleet verdicts throughout adoption.

---

## 7. Snapshot Plan (commands listed, NOT executed)

Create snapshot directory:
```bash
mkdir -p /home/hermes/archive/#200-adoption-preflight/$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_DIR=/home/hermes/archive/#200-adoption-preflight/$(date -u +%Y%m%dT%H%M%SZ)
```

### Per-container snapshots

```bash
# green-ollama
docker inspect green-ollama > $SNAPSHOT_DIR/green-ollama.inspect.json
docker logs --tail 300 green-ollama > $SNAPSHOT_DIR/green-ollama.logs.tail.txt
docker image inspect ollama/ollama:latest > $SNAPSHOT_DIR/green-ollama.image.json

# green-qdrant
docker inspect green-qdrant > $SNAPSHOT_DIR/green-qdrant.inspect.json
docker logs --tail 300 green-qdrant > $SNAPSHOT_DIR/green-qdrant.logs.tail.txt
docker image inspect qdrant/qdrant:latest > $SNAPSHOT_DIR/green-qdrant.image.json

# green-mem0
docker inspect green-mem0 > $SNAPSHOT_DIR/green-mem0.inspect.json
docker logs --tail 300 green-mem0 > $SNAPSHOT_DIR/green-mem0.logs.tail.txt
docker image inspect hermes-mem0-local-api:stable > $SNAPSHOT_DIR/green-mem0.image.json

# trading-hermes-watchdog-1
docker inspect trading-hermes-watchdog-1 > $SNAPSHOT_DIR/trading-hermes-watchdog-1.inspect.json
docker logs --tail 300 trading-hermes-watchdog-1 > $SNAPSHOT_DIR/trading-hermes-watchdog-1.logs.tail.txt
docker image inspect alpine:latest > $SNAPSHOT_DIR/trading-hermes-watchdog-1.image.json
```

### Compose config snapshot

```bash
cp docker-compose.yml $SNAPSHOT_DIR/docker-compose.yml.pre-adopt
docker compose config > $SNAPSHOT_DIR/docker-compose.resolved.pre-adopt.yaml 2>/dev/null || true
```

### Health snapshot (before any change)

```bash
docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' > $SNAPSHOT_DIR/docker-ps.pre-adopt.txt
curl -s http://localhost:8086/api/v1/ping > $SNAPSHOT_DIR/freqforge-ping.pre.txt 2>/dev/null || true
curl -s http://localhost:8085/api/v1/ping > $SNAPSHOT_DIR/regime-hybrid-ping.pre.txt 2>/dev/null || true
curl -s http://localhost:8081/api/v1/ping > $SNAPSHOT_DIR/canary-ping.pre.txt 2>/dev/null || true
curl -s http://localhost:8087/api/v1/ping > $SNAPSHOT_DIR/rebel-ping.pre.txt 2>/dev/null || true
```

---

## 8. Future L3 Command Plan (NOT executed today)

### Prerequisite: Fix Compose for hermes-watchdog

Before adoption step 4, patch `docker-compose.yml`:

```patch
  hermes-watchdog:
    networks:
-    - hermes-net
+    - trading_hermes-net
```

Optionally also mark `watchdog-logs` as external to preserve log history:

```yaml
volumes:
  watchdog-logs:
    external: true
```

### Step 1 — Adopt green-qdrant

```bash
docker stop green-qdrant
docker rm green-qdrant
docker compose -f docker-compose.yml up -d green-qdrant
# Verify
docker inspect green-qdrant --format '{{index .Config.Labels "com.docker.compose.project"}}'
docker ps --filter name=green-qdrant --format '{{.Names}}|{{.Status}}'
```

### Step 2 — Adopt green-ollama

```bash
docker stop green-ollama
docker rm green-ollama
docker compose -f docker-compose.yml up -d green-ollama
# Verify
docker inspect green-ollama --format '{{index .Config.Labels "com.docker.compose.project"}}'
docker ps --filter name=green-ollama --format '{{.Names}}|{{.Status}}'
# Wait for health
sleep 30
docker ps --filter name=green-ollama --format '{{.Names}}|{{.Status}}'
```

### Step 3 — Adopt green-mem0

```bash
docker stop green-mem0
docker rm green-mem0
docker compose -f docker-compose.yml up -d green-mem0
# Verify
docker inspect green-mem0 --format '{{index .Config.Labels "com.docker.compose.project"}}'
docker ps --filter name=green-mem0 --format '{{.Names}}|{{.Status}}'
# Health check (HTTP, takes ~5s)
sleep 10
curl -s http://127.0.0.1:8788/health
docker inspect green-mem0 --format '{{.State.Health.Status}}'
```

### Step 4 — Adopt hermes-watchdog (after compose fix)

```bash
docker stop trading-hermes-watchdog-1
docker rm trading-hermes-watchdog-1
docker compose -f docker-compose.yml up -d hermes-watchdog
# Verify
docker inspect trading-hermes-watchdog-1 --format \
  '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}'
docker ps --filter name=watchdog --format '{{.Names}}|{{.Status}}'
```

### Final verification

```bash
# All 4 containers have compose labels
for c in green-qdrant green-ollama green-mem0 trading-hermes-watchdog-1; do
  echo "$c: $(docker inspect "$c" --format '{{index .Config.Labels "com.docker.compose.project"}}')"
done
# Fleet still GREEN
cat self_improvement_v2/reports/phase2/active_cycle_runner_report.md | grep fleet_verdict
# Unmanaged count reduced (should be 3: btc5m-bot, claude-worker, weatherhermes)
docker ps --format '{{.Names}}' | while read c; do
  p=$(docker inspect "$c" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)
  if [ -z "$p" ]; then echo "UNMANAGED: $c"; fi
done
```

---

## 9. Rollback Plan

| Scenario | Rollback |
|----------|----------|
| Container fails health after adopt | `docker compose down <service>` then `docker run ...` with old params from snapshot |
| Data volume not found | Volumes are `external: True` for green-* data — compose reuses them. For watchdog, if `trading_watchdog-logs` was created empty, stop + rename old volume back. |
| green-mem0 loses hermes-net connectivity | Add `hermes-net` back to compose definition or confirm no dependent service lost |
| SI v2 loop broken | Immediate abort on first RED health. Loop depends on Freqtrade bots, not these containers — unlikely. |

**Rollback principle:** One container at a time. Verify after each. Abort on
first failure. Never `docker compose down` the full project. Never prune
volumes.

---

## 10. Current Unmanaged Risk After Adoption

After Phase B adoption, unmanaged count drops from 7 to **3**:

| Container | Future status | Action required |
|-----------|--------------|-----------------|
| `green-ollama` | Compose-managed ✅ | None |
| `green-qdrant` | Compose-managed ✅ | None |
| `green-mem0` | Compose-managed ✅ | None |
| `trading-hermes-watchdog-1` | Compose-managed ✅ | Compose fix required first |
| `btc5m-bot` | External (ki-fabrik) | Document only |
| `claude-worker` | External (ki-fabrik) | Document only |
| `weatherhermes` | External (ki-fabrik) | Document only |

---

## 11. Remaining Unknowns

| Unknown | Risk | Resolution needed before adopt? |
|---------|------|--------------------------------|
| Env/secret values in `green-mem0` runtime vs compose | Low | No — compose reads same `.env` file |
| `watchdog-logs` volume namespace behavior | Low | Yes — either mark `external: True` or accept empty new volume |
| `hermes-net` is not used by any trading service after green-mem0 drops it | Low | No — confirm by checking `hermes-net` containers |
| SI v2 cycle count after adopt | None | Verify naturally on next cycle |

---

## 12. Human Approval Gates

| Gate | Condition | Who |
|------|-----------|-----|
| 1 | Approval to fix compose: change `hermes-watchdog` network from `hermes-net` to `trading_hermes-net` | Human |
| 2 | Approval to adopt 4 containers in order via `docker compose up -d` | Human |
| 3 | Approval to mark `watchdog-logs` as `external: True` (or not) | Human |
| 4 | Post-adoption verification of fleet health (SI v2 next cycle) | Human + SI v2 |

---

## 13. Exact Next Recommended Task

**Decision gate:**

1. **Approve compose fix** — Patch `hermes-watchdog` network from `hermes-net`
   to `trading_hermes-net` in `docker-compose.yml`. This is a low-risk config
   change (L2) but requires a commit/pr.
2. **Approve adoption** — Execute Phase C: stop 4 unmanaged containers one at
   a time, recreate via `docker compose up -d`, verify after each. This is L3
   (runtime mutation).
3. **Decide on `watchdog-logs`** — Mark as external or accept new volume?

**Recommended next step (smallest safe increment):**

> **Approve and execute compose fix for hermes-watchdog network.**
> 
> Change `hermes-net` → `trading_hermes-net` in `docker-compose.yml`,
> commit as a doc/config PR, merge. Then the adoption steps are execute-only.

---

## 14. Decision: Compose Fix Required Before L3 Adoption

**Date:** 2026-06-14

The following Compose fixes were approved (L2) and applied in a separate PR
before any L3 adoption is attempted:

### Fix 1 — `hermes-watchdog` network

```diff
  hermes-watchdog:
    networks:
-    - hermes-net
+    - trading_hermes-net
```

**Why:** The runtime container `trading-hermes-watchdog-1` uses
`trading_hermes-net` (where all Freqtrade bots and ai-hedge-fund are
reachable). The Compose definition incorrectly specified `hermes-net`.
Without this fix, adoption via `docker compose up -d hermes-watchdog` would
place the watchdog on `hermes-net`, where it cannot reach the trading bots,
causing persistent false ALERTS.

### Fix 2 — `watchdog-logs` external volume

```diff
  volumes:
-  watchdog-logs: null
+  watchdog-logs:
+    external: true
```

**Why:** The runtime container uses volume `watchdog-logs` (created
2026-06-10). Without `external: true`, Compose would namespace it as
`trading_watchdog-logs` and create an empty volume, losing log history.
Marking it external preserves the existing data.

### Adoption remains blocked

L3 adoption of all 4 containers (green-qdrant, green-ollama, green-mem0,
trading-hermes-watchdog-1) remains **blocked** until:

1. This Compose fix PR is merged.
2. Human approval for Phase B2 L3 adoption is given.

Refer to `SEC-03` (Phase B2) for the adoption execution plan.

