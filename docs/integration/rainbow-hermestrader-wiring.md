# Rainbow → HermesTrader Integration Wiring (R7A)

**ADR:** [ADR-2026-07-11-hermes-r7a-dryrun-topology.md](../decisions/ADR-2026-07-11-hermes-r7a-dryrun-topology.md)
**Issue:** #504 (R7A), #496 (R7 Measurement)
**Compose:** `docker-compose.hermestrader-dryrun.yml`

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                trading_internal (bridge)             │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ freqforge│  │ canary   │  │ regime-hybrid    │  │
│  │ :8086    │  │ :8081    │  │ :8085            │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────────┐    │
│  │ webserver        │  │ rainbow              │    │
│  │ :8180            │  │ :8000 (internal)     │    │
│  └──────────────────┘  └──────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────┐              │
│  │ freqai-rebel (profile: rebel)    │              │
│  │ :8087  NOT in default start      │              │
│  └──────────────────────────────────┘              │
└─────────────────────────────────────────────────────┘
         ↑ internal only, no external ports on rainbow
```

---

## SI-v2 Wiring

SI-v2 connects to Rainbow via the internal network:

```env
SI_V2_RAINBOW_BASE_URL=http://rainbow:8000
SI_V2_RAINBOW_MODE=read_only
SI_V2_RAINBOW_ENABLED=true
```

**Mutation Counter must remain 0** while `read_only` mode is active.

---

## Rainbow Properties

| Property | Value |
|----------|-------|
| Network | `trading_internal` (bridge, internal) |
| Published ports | **None** — internal only |
| Mode | `ta_collector` |
| Evaluation | `false` |
| Delivery Worker | `false` |
| Health endpoint | `GET /health` (port 8000, internal) |
| Heartbeat | `/app/rainbow/storage/heartbeat_rainbow.json` |
| Storage | Docker volume `rainbow-storage` → `/app/rainbow/storage` |
| Config | `config/rainbow.internal.yml` (read-only mount) |
| Healthcheck tool | `python3` (not `curl` — image does not include it) |
| Fail-closed freshness | 300 seconds max age |

---

## Build Context

Rainbow builds from the ai4trade-bot repository:

```yaml
build:
  context: ${AI4TRADE_CONTEXT:-../ai4trade-bot}
```

**Pin verification:** The ai4trade-bot commit must be recorded in the deployment report.
- `bbcaf25` — Rainbow R1 contract baseline (documented reference)
- `b65510a` — PR-2 proposed runtime/vendoring pin (must be verified at deploy time)

---

## Safety Invariants

1. Rainbow is **advisory only** — never an order, apply, or runtime authority.
2. No exchange credentials in the committed config (deploy-time injection only).
3. No `ports:` mapping on the Rainbow service.
4. SI-v2 consumes Rainbow evidence via GET-only HTTP.
5. If Rainbow health fails or data is stale (>300s), SI-v2 must fail-closed.
6. Rainbow mutation counter must be 0 in read-only mode.

---

## Verification

```bash
# Config renders cleanly
docker compose -f docker-compose.hermestrader-dryrun.yml config

# Rainbow health (from inside the network)
docker exec <si-v2-container> python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://rainbow:8000/health').read())"

# Mutation counter check
echo "SI_V2_RAINBOW_MODE must be read_only"
echo "Mutation counter must be 0"
```
