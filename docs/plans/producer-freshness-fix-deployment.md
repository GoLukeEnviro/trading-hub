# Producer Freshness — Implementation Plan

> **Status:** L3 Plan (ready for approval, NOT for execution without authorization)
> **Grounded at:** `b5131dc` (main, after PR #263 — state reconciliation)
> **Current blocker:** Producer Freshness / Scoring Eligibility
> **Rainbow scoring gate:** 0/10 — no fresh signals available

---

## 1. Problem Statement

The SI v2 Rainbow scoring gate is at **0/10** because the freshness guard
correctly rejects all available signals. The root cause is structural:

**Root cause:** There is no active producer writing fresh signals to the Rainbow
`signals.db`. The existing 3 signals (`BTC/USD`, `ETH/USD`, `SOL/USDT`) were
written on `2026-06-14T01:04:16Z` — over 24h stale — and the `freshness_max_seconds`
threshold is 900s (15 min).

**What is NOT broken:**
- The freshness guard works correctly (fail-closed) and must stay in place.
- The scoring eligibility gate (`_is_rainbow_cycle_scoring_eligible`) is correct.
- The Rainbow client (`RainbowSignalProviderClient`) validates and maps correctly.
- The stub server (`rainbow_db_stub_server.py`) is a valid read-only HTTP source
  — it just has nothing fresh to serve.

---

## 2. Solution: The ai4trade-bot Rainbow Service

The ai4trade-bot repo (`/opt/data/ai4trade-bot/`) already contains a complete
Rainbow signal producer:

| Component | File | Purpose |
|-----------|------|---------|
| Rainbow Engine | `rainbow/main.py` (FastAPI + uvicorn) | Full signal pipeline |
| Signal Store | `rainbow/processor/store.py` (SQLite) | Persists signals to `signals.db` |
| TA Collector | `rainbow/collectors/ta_collector.py` | Technical analysis every 60s |
| Scorer | `rainbow/processor/scorer.py` | Combines collector outputs |
| REST API | `rainbow/distribution/api.py` | Serves `/signals/latest`, `/health`, etc. |
| Dockerfile | `rainbow.Dockerfile` | Container build for the service |
| Docker Compose | `docker-compose.yml` (rainbow service) | Port 8000, healthcheck, volume mounts |

### 2.1 Current State of ai4trade-bot

- **Docker Compose exists** at `/opt/data/ai4trade-bot/docker-compose.yml`
- **Rainbow Dockerfile exists** at `/opt/data/ai4trade-bot/rainbow.Dockerfile`
- **`signals.db` exists** at `/opt/data/ai4trade-bot/rainbow/storage/signals.db` (28KB, stale)
- **No `.env` file** — the service cannot start without API keys
- **No running container** — `docker ps` does not list any ai4trade-bot/rainbow container

### 2.2 Dependencies for Deployment

The Rainbow service requires these runtime dependencies to produce fresh signals:

| Dependency | Source | Risk Level |
|-----------|--------|------------|
| Bitget exchange API key | `.env` → `exchanges/bitget.py` | **HIGH** (credential) |
| LLM API key (Claude) | `.env` → LLM evaluator | **HIGH** (credential) |
| Market data access | HTTP to Bitget API, CoinGecko | LOW (read-only) |

The Rainbow service CAN start in a degraded mode without all collectors active.
The TA collector (most important for signal freshness) only needs Bitget
OHLCV data — no API key required if the exchange config allows public endpoints.

### 2.3 Signal Producer Contract

The running Rainbow FastAPI service exposes:

| Endpoint | Method | Returns | Freshness |
|----------|--------|---------|-----------|
| `/health` | GET | `{"status": "healthy", "collectors": {...}}` | Real-time |
| `/signals/latest` | GET | List of Rainbow signal dicts | Current timestamps |
| `/signals/canonical/latest` | GET | CanonicalSignalEnvelope list | Current timestamps |

The SI v2 cycle's `_get_latest_read_only_signals()` connects to
`{base_url}/signals/latest` and maps the response through
`_map_crypto_signal_to_envelope()`. The mapping:
- Preserves original `timestamp_utc` from the DB (fresh from collector)
- Sets `emitted_at_utc` = now
- Sets `can_execute = False`, `dry_run_only = True`
- Includes `provider_mode = "read_only"` metadata

---

## 3. Implementation Options

### Option A — Real Producer Container ✅ PREFERRED

Deploy the ai4trade-bot Rainbow service as a Docker container under a
controlled compose profile.

**Files to create/change:**
1. `orchestrator/profiles/rainbow-producer.yml` — Minimal compose override
   (binds signals.db, sets env vars for SI v2 integration)
2. `orchestrator/scripts/start_rainbow_producer.sh` — Wrapper that:
   - Validates preconditions (DB exists, port free, not already running)
   - Starts the container (no live trading, no exchange orders)
   - Waits for healthcheck
   - Reports status
3. `.env.example` updates or a separate `.env.rainbow` with documented
   required/recommended vars
4. SI v2 cycle config: set `SI_V2_RAINBOW_BASE_URL=http://localhost:8000`

**Pros:**
- Real fresh signals with actual market analysis
- No synthetic timestamps
- Full Rainbow pipeline (TA, sentiment, LLM evaluation)
- Scoring eligibility can advance from 0/10 to 10/10

**Cons:**
- Requires runtime Docker operations (L3)
- Requires credential configuration (.env with exchange/LLM keys)
- Build time for the rainbow container (multi-stage Dockerfile)
- Container adds memory/CPU footprint to the fleet

**Runtime approval token:** `APPROVE_RAINBOW_PRODUCER_DEPLOY`

### Option B — Repo-Only Producer Script ⚠️ VALIDATION ONLY

Create a lightweight stdlib HTTP server under `orchestrator/scripts/` that
reads from `signals.db` and serves proper §5 envelopes with documentation
that it is NOT scoring-eligible.

**Files to create:**
1. `orchestrator/scripts/rainbow_producer_mock.py` — Dry-run mock that:
   - Connects to the existing signals.db
   - Serves envelopes via `GET /healthz` and `GET /signals/latest`
   - Uses real `emitted_at_utc` = now
   - Preserves original `timestamp_utc` (stale)
   - Sets `data_quality.status = "degraded"` with `freshness_seconds` showing age
   - NEVER marks data as scoring-eligible
   - Safety: `can_execute=False`, `dry_run_only=True`

**Pros:**
- No Docker operations required
- No credential exposure
- Useful for development, integration testing, and pipeline validation

**Cons:**
- **NOT a scoring fix** — signals remain stale, `fresh=False`
- Can only validate the pipeline, not advance scoring eligibility
- Adds no real market data freshness

**Decision:** Option B is useful for **development/CI only**. Only Option A
can fix the scoring gate. Option B may be a stepping stone to validate the
SI v2 → Rainbow pipeline end-to-end before L3 deployment.

### Option C — Timestamp-Only Cron Updater ❌ REJECTED

Creating a cron/SI v2 cycle hook that re-stamps old signal timestamps to
current UTC in the DB.

**Rejected because:** This would bypass the freshness guard, creating the
illusion of fresh signals without real market analysis. The user explicitly
directed: *"Nicht synthetische Freshness als Shortcut. Das würde nur den
Guard umgehen."* This artifact would not be distinguishable as real vs.
synthetic and would undermine the scoring integrity.

---

## 4. Option A — Detailed Deployment Plan

### 4.1 Preflight Checklist (read-only, no approval needed)

```bash
# 1. Verify the Rainbow service files exist
ls -la /opt/data/ai4trade-bot/rainbow/main.py
ls -la /opt/data/ai4trade-bot/rainbow/distribution/api.py
ls -la /opt/data/ai4trade-bot/rainbow.Dockerfile

# 2. Verify signals.db exists and has data
ls -la /opt/data/ai4trade-bot/rainbow/storage/signals.db
sqlite3 /opt/data/ai4trade-bot/rainbow/storage/signals.db \
  "SELECT count(*), max(timestamp) FROM signals"

# 3. Verify port 8000 is free
ss -tlnp | grep ':8000 ' || echo "Port 8000 free"

# 4. Verify current SI v2 Rainbow config
grep -r "RAINBOW" /home/hermes/projects/trading/.env 2>/dev/null || echo "No Rainbow env vars set"
```

### 4.2 Credential Configuration (L3 — requires APPROVE_RAINBOW_PRODUCER_DEPLOY)

The Rainbow service needs at minimum a Bitget API key for market data.
Create `.env` at `/opt/data/ai4trade-bot/.env`:

```bash
# Required for market data
BITGET_API_KEY=...
BITGET_SECRET_KEY=...
BITGET_PASSPHRASE=...

# Optional signal enhancements (omit to start degraded)
# ANTHROPIC_API_KEY=...
```

**Safety rules:**
- Never log the `.env` file content
- Never commit `.env` to the repository
- `.env` is already in `ai4trade-bot/.gitignore` (verify before deploy)
- The Rainbow service is **read-only** with respect to trading — it only
  reads market data, never places orders

### 4.3 Compose Profile (L3 — requires APPROVE_RAINBOW_PRODUCER_DEPLOY)

Create `orchestrator/profiles/rainbow-producer.yml`:

```yaml
# Rainbow Producer Profile
# This profile starts the ai4trade-bot Rainbow signal producer
# as a standalone service. It is READ-ONLY: no orders, no trades,
# no exchange write operations.
#
# Activation: docker compose -f orchestrator/profiles/rainbow-producer.yml up -d
# Deactivation: docker compose -f orchestrator/profiles/rainbow-producer.yml down
services:
  rainbow-producer:
    build:
      context: /opt/data/ai4trade-bot
      dockerfile: rainbow.Dockerfile
    container_name: trading-rainbow-producer-1
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - /opt/data/ai4trade-bot/rainbow/storage:/app/rainbow/storage
      - /opt/data/ai4trade-bot/rainbow/config:/app/rainbow/config:ro
    env_file:
      - /opt/data/ai4trade-bot/.env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import json,urllib.request; json.loads(urllib.request.urlopen('http://localhost:8000/health').read())['status'] == 'healthy' or exit(1)"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
    networks:
      - trading_network  # For SI v2 cycle access via container name

networks:
  trading_network:
    external: true
```

### 4.4 SI v2 Cycle Reconfiguration (L3 — requires APPROVE_RAINBOW_PRODUCER_DEPLOY)

After the producer is running, update the SI v2 cycle configuration:

```bash
# Set the Rainbow base URL to point to the producer
echo 'export SI_V2_RAINBOW_ENABLED=true' >> /home/hermes/projects/trading/.env
echo 'export SI_V2_RAINBOW_MODE=read_only' >> /home/hermes/projects/trading/.env
echo 'export SI_V2_RAINBOW_BASE_URL=http://localhost:8000' >> /home/hermes/projects/trading/.env
```

Or for container-name access (if on same Docker network):
```bash
echo 'export SI_V2_RAINBOW_BASE_URL=http://rainbow-producer:8000' >> /home/hermes/projects/trading/.env
```

### 4.5 Validation

```bash
# 1. Healthcheck
curl -s http://localhost:8000/health | python3 -m json.tool

# 2. Signals endpoint returns data
curl -s http://localhost:8000/signals/latest | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Count: {len(data)}')
if data:
    print(f'Latest timestamp: {data[0].get(\"timestamp\", \"N/A\")}')
    print(f'Freshness (seconds): {(datetime.now() - datetime.fromisoformat(data[0][\"timestamp\"])).total_seconds()}')
"

# 3. SI v2 cycle recognizes freshness
cd /home/hermes/projects/trading
python3 -m si_v2.loop.active_cycle_runner --dry-run --rainbow-only

# 4. Scoring eligibility check
python3 self_improvement_v2/tests/test_rainbow_freshness_contract.py -v

# 5. Safety invariants
python3 -c "
from si_v2.rainbow.client import RainbowSignalProviderClient
from si_v2.rainbow.validator import RainbowSignalEnvelopeValidator
# Verify can_execute=False on all envelopes
"
```

### 4.6 Rollback Plan

```bash
# Step 1 — Stop the producer
docker compose -f orchestrator/profiles/rainbow-producer.yml down
docker rm trading-rainbow-producer-1 2>/dev/null || true

# Step 2 — Remove the image (optional, frees disk)
docker rmi trading-rainbow-producer:latest 2>/dev/null || true

# Step 3 — Restore SI v2 cycle config to stub server
sed -i '/SI_V2_RAINBOW_BASE_URL/d' /home/hermes/projects/trading/.env
echo 'export SI_V2_RAINBOW_BASE_URL=http://127.0.0.1:8765' >> /home/hermes/projects/trading/.env

# Step 4 — Restart stub server if needed
python3 /home/hermes/projects/trading/orchestrator/scripts/rainbow_db_stub_server.py \
  --db /opt/data/ai4trade-bot/rainbow/storage/signals.db \
  --port 8765 &

# Step 5 — Verify rollback
curl -s http://127.0.0.1:8765/health
python3 self_improvement_v2/tests/test_rainbow_freshness_contract.py -v
```

---

## 5. Scoring Gate Path

| Step | Condition | Current | Target |
|------|-----------|---------|--------|
| 1 | Producer running, serving fresh signals | ❌ (no container) | ✅ (after L3 deploy) |
| 2 | `fresh=True` on Rainbow cycle observation | ❌ (stale signals → `fresh=False`) | ✅ (after Option A) |
| 3 | Scoring-eligible cycles `>= 10/10` | 0/10 | 10/10 |
| 4 | History gate met (`history_gate_required=10`) | ❌ | ✅ |
| 5 | ShadowProposal promotion allowed | ❌ | ✅ |

Each step gates the next. No shortcuts.

---

## 6. Test Coverage

The following tests already exist and validate freshness invariants:

| Test File | Test | Validates |
|-----------|------|-----------|
| `test_rainbow_freshness_contract.py` | `test_read_only_rainbow_freshness_round_trip` | Fresh signal (60s) → `fresh=True`, stale (3600s) → `fresh=False` |
| `test_rainbow_read_only_client.py` | Various | Client → DB mapping, envelope validation |
| `test_active_cycle_runner.py` | `test_fixture_signals_are_never_fresh` | Fixture mode → `fresh=False` always |
| `test_active_cycle_runner.py` | `test_read_only_env_override_freshness_guard` | Env-override freshness guard |
| `test_rainbow_db_stub_server.py` | Various | Stub server HTTP + response format |

### Tests to Add (in a follow-up PR after deployment)

The following tests should be added when the producer is deployed, to validate
the real producer pipeline:

1. **Fresh signal accepted** — Mock RainbowFastAPI server, pass fresh envelope
   through `_load_rainbow_signals()`, expect `fresh=True`, scoring-eligible
2. **Stale signal rejected** — Same mock with stale timestamp, expect
   `fresh=False`, NOT scoring-eligible
3. **Synthetic signal rejected for scoring** — A signal with
   `data_quality.status == "unavailable"` should still count as a valid signal
   (not an error) but downstream scoring should recognize it's synthetic
4. **Missing timestamp rejected** — Envelope without `timestamp_utc` should
   fail validation → `errors > 0` → NOT scoring-eligible
5. **Timezone normalization** — Timestamps in various formats should all
   normalize correctly: `2026-06-14T01:04:16Z`, `2026-06-14T01:04:16+00:00`,
   `2026-06-14 01:04:16`
6. **No live trading mutation** — Every mapped envelope must have
   `actionability.can_execute = False` and `actionability.dry_run_only = True`,
   verified via schema validation

---

## 7. Approval Gates

| Gate | Token | Required For | Risk Level |
|------|-------|-------------|------------|
| G1 | — | Preflight inspection (Section 4.1) | L0 |
| G2 | — | Plan review and approval | L1 |
| G3 | `APPROVE_RAINBOW_PRODUCER_DEPLOY` | Runtime deployment: build, start, configure | L3 |
| G4 | (separate approval) | Adding exchange/LLM API keys to `.env` | L3 |
| G5 | (separate approval) | Enabling SI v2 scoring cycle promotion | L3 |

**G3 — APPROVE_RAINBOW_PRODUCER_DEPLOY must be explicitly issued.**
The plan is read-only until this token is presented. No Docker, no container
creation, no config mutation, no credential handling prior to G3.

---

## 8. Order of Operations

```
Phase 1 (current PR) ──→ Phase 2 (L3 approval) ──→ Phase 3 (validation)
     │                        │                          │
     ├─ Plan review          ├─ APPROVE_RAINBOW_PRODUCER ├─ curl /health ✓
     ├─ Preflight inspect    ├─ Configure .env           ├─ /signals/latest ✓
     ├─ Test current state   ├─ Build rainbow container  ├─ fresh=True in cycle
     └─ Document findings    ├─ Start container          ├─ scoring 1/10→10/10
                              ├─ Set SI v2 base_url       └─ history gate met
                              └─ Validate healthcheck    └─ Walk-forward enabled
```

---

## 9. Related Issues and Documents

| Reference | Link |
|-----------|------|
| Rainbow §5 envelope contract | `self_improvement_v2/contracts/rainbow_signal_envelope.schema.json` |
| Rainbow Signal Provider Client | `self_improvement_v2/src/si_v2/rainbow/client.py` |
| Active Cycle Runner | `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py` |
| Current Operational State | `docs/state/current-operational-state.md` (§3, Phase 2.1) |
| Roadmap v2 | `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` (§Phase 2.1) |
| ai4trade-bot Rainbow | `/opt/data/ai4trade-bot/rainbow/main.py` |
| Stub Server (current fallback) | `orchestrator/scripts/rainbow_db_stub_server.py` |

---

## Appendix A — Execution Record (2026-06-15)

### Actual Deployment Model

**Chosen:** Direct uvicorn process + s6 supervision + manager script

**Why not Docker:** The rainbow.Dockerfile has a missing `core` module
dependency (`from core.heartbeat_writer import ...`). Fixing the
Dockerfile requires either bundling `core/` or restructuring the build
context — deferred to follow-up.

**Why not systemd:** Container environment (s6 init, no systemd).

### Deployment Steps (Actual)

1. Created `rainbow/config.yaml` with corrected asset names (`BTCUSDT`
   instead of `BTC`) for Bitget API compatibility.
2. Started uvicorn via ai4trade-bot `.venv`:
   ```
   .venv/bin/uvicorn rainbow.main:create_app --host 127.0.0.1 --port 8000 --factory
   ```
3. Created s6 service at `/run/service/rainbow-producer/` for auto-restart.
4. Created `orchestrator/scripts/rainbow_producer_manager.sh` for
   start/stop/status/restart.
5. Created `orchestrator/scripts/rainbow_producer_acceptance_test.py`
   for repeatable validation.
6. Set SI v2 env vars:
   - `SI_V2_RAINBOW_ENABLED=true`
   - `SI_V2_RAINBOW_MODE=read_only`
   - `SI_V2_RAINBOW_BASE_URL=http://localhost:8000`

### Validation Results (2026-06-15 19:52 UTC)

| Check | Result |
|-------|--------|
| GET /health | ✅ 200, healthy, ta=running |
| GET /signals/latest | ✅ 21 signals (18 fresh + 3 stale) |
| Freshest signal age | ✅ 93s (threshold 900s) |
| fresh=True | ✅ |
| Scoring eligible | ✅ (all 5 conditions) |
| can_execute=False | ✅ 21/21 envelopes |
| dry_run_only=True | ✅ 21/21 envelopes |
| Mutation counters | ✅ All 0 |
| Controller state | ✅ PAUSED / L3_REPOSITORY_ONLY |

### What Was NOT Changed

- No Docker compose changes
- No Freqtrade bot restarts
- No strategy promotion
- No live trading enablement
- No scheduler cadence change
- No credential exposure (public Bitget API only)

### Rollback Commands

```bash
# Stop producer
orchestrator/scripts/rainbow_producer_manager.sh stop
# Or via s6
rm -rf /run/service/rainbow-producer

# Remove SI v2 Rainbow env config
sed -i '/SI_V2_RAINBOW_BASE_URL/d; /SI_V2_RAINBOW_ENABLED/d; /SI_V2_RAINBOW_MODE/d' .env

# Restart stub server as fallback
python3 orchestrator/scripts/rainbow_db_stub_server.py \
  --db /opt/data/ai4trade-bot/rainbow/storage/signals.db \
  --port 8765 &

# Verify rollback
python3 orchestrator/scripts/rainbow_producer_acceptance_test.py
```

### Remaining Risks

1. **s6 supervision not fully verified.** The supervise directory exists
   and the process survives SIGTERM, but the service was not registered
   through the canonical s6-rc compile path.
2. **TA collector uses public Bitget API.** No rate-limiting issues
   observed at 120s interval, but Bitget could change their public API.
3. **No auto-restart across container restarts.** If the Hermes container
   restarts, the producer must be manually restarted via the manager
   script or re-created if the s6 service directory persists.
4. **Asset names mismatch.** The producer uses `BTCUSDT` format (Bitget)
   while the SI v2 envelope schema uses `BTC/USDT:USDT`. The SI v2
   client only checks that `symbol` is non-empty, so this is cosmetic
   for now but should be aligned.

