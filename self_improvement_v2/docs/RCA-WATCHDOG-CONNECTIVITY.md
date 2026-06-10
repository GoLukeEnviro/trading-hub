# Watchdog Connectivity Target — Root Cause Analysis

**Issue:** [#39 — Fix watchdog connectivity target for dry-run stack monitoring](https://github.com/GoLukeEnviro/trading-hub/issues/39)  
**Date:** 2026-06-10  
**Status:** ✅ Already resolved

---

## 1. Discovery

The Phase M.2 dry-run signal validation report noted that watchdog
connectivity was using `host.docker.internal` instead of Docker container
names, causing timeouts and false negatives.

---

## 2. Investigation

### 2.1 Current Watchdog Container

The running watchdog container (`trading-hermes-watchdog-1`, image:
`alpine:latest`) was inspected:

| Check | Result |
|-------|--------|
| Current command | `wget` to Docker container names (correct) |
| `host.docker.internal` usage | ❌ Not present |
| Targets | `trading-freqtrade-freqforge-1:8080`, `trading-freqtrade-regime-hybrid-1:8080`, etc. |

The current watchdog correctly uses Docker container names for its health
checks. This is the correct approach for Docker networking.

### 2.2 docker-compose.yml Comparison

| File | `host.docker.internal` Usage | Status |
|------|---------------------------|--------|
| `docker-compose.yml` (current) | ✅ Uses Docker container names | Correct |
| `docker-compose.yml.bak.issue41` (historical) | ❌ Used `host.docker.internal` | Fixed |

### 2.3 Root Cause

The original `docker-compose.yml` used `host.docker.internal` with port
mappings for watchdog health checks. This was incorrect because:

1. `host.docker.internal` resolves to the Docker host from within containers,
   not to other containers.
2. Port mappings (`8080->8086`, etc.) are on the host interface
   (`127.0.0.1`), not reachable via `host.docker.internal`.
3. The correct approach is to use Docker service/container names directly
   (Docker DNS resolution).

### 2.4 Resolution

The fix was already applied in the current `docker-compose.yml` (likely as
part of the docker-compose audit/cleanup work). All watchdog targets now
use correct Docker container names.

The historical `docker-compose.yml.bak.issue41` preserves the old config
for reference.

---

## 3. Verification

```bash
# Check watchdog container command (no host.docker.internal)
docker inspect trading-hermes-watchdog-1 --format '{{json .Config.Cmd}}' | grep -c "host.docker.internal" || echo "✅ No host.docker.internal references"

# Check current docker-compose.yml
grep -c "host.docker.internal" docker-compose.yml || echo "✅ No host.docker.internal in docker-compose.yml"
```

---

## 4. Regression Prevention

| Prevention | Status |
|-----------|--------|
| docker-compose.yml uses Docker container names | ✅ Already fixed |
| `.bak.issue41` preserves the old config for reference | ✅ Historical |
| Future compose changes should use container names | 🔶 Process note |

---

## 5. Related Documents

| Document | Location |
|----------|----------|
| Phase M.2 Probe Report | `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md` |
| Fleet Inventory Audit | `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/fleet_inventory_audit_20260610.md` |
| docker-compose.yml (current) | `docker-compose.yml` |
| docker-compose.yml (historical) | `docker-compose.yml.bak.issue41` |
