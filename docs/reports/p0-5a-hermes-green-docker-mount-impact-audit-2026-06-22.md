# P0-5a: hermes-green Docker Mount Impact Audit

**Date:** 2026-06-22  
**Auditor:** Hermes Meta-Orchestrator (L0 read-only audit)  
**Baseline:** `main` at `9fe0b9c`  
**Methodology:** Static code analysis + runtime read-only Docker inspection + proxy parity testing  

---

## Executive Verdict

**YELLOW** — Script compatibility fixes are required before removing the direct Docker socket mount.

**Key finding:** The `docker-proxy` now supports `EXEC=1` and `POST=1`, which means `docker exec` **works through the proxy**. However, three scripts hardcode `DOCKER_HOST=unix:///var/run/docker.sock` with stale comments saying "docker-proxy blocks exec calls" — this was true when `EXEC=0` but is **no longer accurate**. Once these scripts are updated to respect the `DOCKER_HOST` environment variable (or default to `tcp://docker-proxy:2375`), the direct socket mount can be safely removed.

---

## 1. hermes-green Mount Inventory

| Mount | Source → Target | Mode | Risk if Removed | Current Function |
|-------|----------------|------|-----------------|-----------------|
| **Docker socket** | `/var/run/docker.sock` → `/var/run/docker.sock` | `:ro` | Scripts with hardcoded `DOCKER_HOST=unix:///...` break | Used by `container_watchdog.sh`, `freqtrade_monitor.py`, `quality_hub_monitor.py` |
| Projects | `/home/hermes/projects` → `/home/hermes/projects` | `:rw` | **BREAKS ALL AGENT WORK** — repo access, PR creation, reports, cron write paths | Hermes reads/writes the entire trading repo |
| SSH keys | `/opt/hermes/ssh` → `/home/hermes/.ssh` | `:ro` | GitHub SSH access breaks | `git push` over SSH (`git@github.com-trading`) |
| Hermes config | `/opt/hermes-green/config` → `/opt/data` | (rw) | Hermes profile breaks | Hermes runtime config, memory, cron state |
| Weatherbot | `/home/hermes/.../weatherbot_master` → `...` | `:ro` | Weather bot breaks | Weather data module |
| Telegram script | `/opt/hermes-green/scripts/...` → `...` | `:ro` | Telegram settle delay breaks | Container init script |

### Environment (no secrets shown)

| Variable | Value |
|----------|-------|
| `DOCKER_HOST` | `tcp://docker-proxy:2375` |
| `HERMES_DASHBOARD_INSECURE` | `1` |
| `HERMES_DASHBOARD_PORT` | `9119` |
| `PUID` / `PGID` | `10000` / `10000` |

### Networks

| Network | Membership | Internal? |
|---------|-----------|-----------|
| `hermes-net` | ✅ | No |
| `proxy-net` | ✅ (`172.27.0.3`) | **Yes** |
| `trading_hermes-net` | ✅ (`172.26.0.9`) | No |

### Key Observation

`hermes-green` has **both** the direct socket mount (`/var/run/docker.sock:ro`) **and** the proxy environment (`DOCKER_HOST=tcp://docker-proxy:2375`). Docker CLI inside the container uses the proxy by default (via `DOCKER_HOST`), but three scripts explicitly **override** `DOCKER_HOST` to force the Unix socket.

---

## 2. docker-proxy Configuration

| Setting | Value | Meaning |
|---------|-------|---------|
| `CONTAINERS` | `1` | `docker ps`, `docker inspect` ✅ |
| `EXEC` | `1` | `docker exec` ✅ |
| `POST` | `1` | POST operations (start/stop/exec) ✅ |
| `INFO` | `1` | `docker info` ✅ |
| `SERVICES` | `1` | Service listing ✅ |
| `NETWORKS` | `1` | `docker network inspect` ✅ |
| `ALLOW_RESTARTS` | `0` | `docker restart` ❌ |
| `ALLOW_START` | `0` | `docker start` ❌ |
| `ALLOW_STOP` | `0` | `docker stop` ❌ |
| `BUILD` | `0` | `docker build` ❌ |
| `COMMIT` | `0` | `docker commit` ❌ |
| `AUTH` | (redacted) | Authentication |

### Proxy Parity Test Results (read-only)

| Operation | Proxy Result | Verdict |
|-----------|-------------|---------|
| `docker info` | ✅ `ServerVersion: 29.1.3` | GREEN |
| `docker ps` | ✅ All containers listed | GREEN |
| `docker inspect freqforge` | ✅ `running` | GREEN |
| `docker inspect regime-hybrid` | ✅ `running` | GREEN |
| `docker inspect canary` | ✅ `running` | GREEN |
| `docker inspect freqai-rebel` | ✅ `running` | GREEN |
| `docker exec freqforge sh -lc 'true'` | ✅ `EXEC_OK` | **GREEN** |

**The proxy now fully supports `docker exec`** — the stale comments in scripts are incorrect.

---

## 3. Static Dependency Analysis

### Scripts that hardcode `DOCKER_HOST=unix:///var/run/docker.sock`

| # | Script | Line | Current Code | Runs inside hermes-green? | Bruchrisiko |
|---|--------|------|-------------|--------------------------|-------------|
| **1** | `orchestrator/scripts/container_watchdog.sh` | `:42` | `export DOCKER_HOST="unix:///var/run/docker.sock"` | Yes (Hermes cron, 30min) | **HOCH** — override forces socket path, proxy ignored |
| **2** | `orchestrator/scripts/freqtrade_monitor.py` | `:24` | `_DOCKER_HOST = "unix:///var/run/docker.sock"` | Yes (Hermes cron) | **HOCH** — override forces socket path for all `docker exec`/`inspect` calls |
| **3** | `orchestrator/scripts/quality_hub_monitor.py` | `:26` | `_DOCKER_HOST = "unix:///var/run/docker.sock"` | Yes (Hermes cron) | **HOCH** — override forces socket path |

### Scripts that use Docker but respect `DOCKER_HOST` or use no override

| Script | Docker Usage | Runs inside hermes-green? | Bruchrisiko |
|--------|-------------|--------------------------|-------------|
| `orchestrator/scripts/drawdown_guard.py` | `docker inspect`, `docker exec` (line 85, 172) | Yes (Hermes cron) | **NIEDRIG** — no DOCKER_HOST override, uses `DOCKER_HOST` env |
| `freqtrade/shared/fleet_watcher.py` | `docker inspect` (line 1011) | Yes (strategy-side) | **NIEDRIG** — uses subprocess without explicit DOCKER_HOST override |
| `dashboard.py` | `docker exec`, `docker ps` (lines 126, 283, 975) | No (separate `trading-dashboard` container) | **NIEDRIG** — not affected by hermes-green mount |
| `orchestrator/guardian/scripts/external_cron_guardian.sh` | `docker exec`, `docker ps` | **No** (runs on HOST via systemd) | **NIEDRIG** — host has direct socket access |
| SI v2 `real_docker_adapter.py` | `docker inspect` (line 212) | Yes (active cycle runner) | **NIEDRIG** — uses subprocess, no DOCKER_HOST override |

### Scripts that test for `/var/run/docker.sock` presence

| Script | Line | Code | Purpose |
|--------|------|------|---------|
| `orchestrator/scripts/drawdown_guard.py` | `:131` | `if not Path("/var/run/docker.sock").is_socket():` | Docker availability detection (graceful fallback) |
| `orchestrator/scripts/container_watchdog.sh` | `:44` | `if [ -S /var/run/docker.sock ]` | Docker availability detection (graceful fallback) |

---

## 4. Breakpoint Analysis

| Component | Current Dependency | What breaks if socket removed | Safe Fix | Test Required | Verdict |
|-----------|-------------------|-------------------------------|----------|---------------|---------|
| `container_watchdog.sh` | Hardcoded `DOCKER_HOST=unix://` | Container health checks fail → fallback to file-based heuristic (reduced accuracy) | Remove `export DOCKER_HOST=...`, use inherited env (`tcp://docker-proxy:2375`) | Run via cron, verify `docker inspect` returns running status for 4 bots | **YELLOW** |
| `freqtrade_monitor.py` | Hardcoded `_DOCKER_HOST=unix://` | Fleet monitoring fails → no balance/status data → Telegram alert degradation | Replace `_DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://docker-proxy:2375")` | Run script, verify 4/4 bot data | **YELLOW** |
| `quality_hub_monitor.py` | Hardcoded `_DOCKER_HOST=unix://` | Quality hub report fails → stale report | Same fix as freqtrade_monitor.py | Run script, verify report generation | **YELLOW** |
| `drawdown_guard.py` | Uses env `DOCKER_HOST` | **Nothing breaks** — already uses proxy env | No fix needed | Already working via proxy | **GREEN** |
| SI v2 active cycle runner | Uses env `DOCKER_HOST` | **Nothing breaks** — no explicit socket override | No fix needed | Run cycle, verify 4/4 bot telemetry | **GREEN** |
| `fleet_watcher.py` | Uses env `DOCKER_HOST` | **Nothing breaks** | No fix needed | Strategy-side, not directly affected | **GREEN** |
| External cron guardian | Host-level socket access | **Nothing breaks** — runs on host, not in container | No fix needed | N/A | **GREEN** |
| `/home/hermes/projects:rw` mount | Agent repo access | **BREAKS EVERYTHING** — repo reads/writes, PR creation, cron write paths | Do NOT remove in P0-5 | N/A | **RED** (do not touch) |
| SSH mount (`/opt/hermes/ssh`) | GitHub SSH push | `git push` fails → no PR creation | Do NOT remove in P0-5 | N/A | **RED** (do not touch) |

---

## 5. Recommended P0-5b Repo Fix

The following three-file patch makes all Docker-using scripts proxy-compatible:

### `container_watchdog.sh` (line 42)
**Before:**
```bash
export DOCKER_HOST="unix:///var/run/docker.sock"
```
**After:**
```bash
# Respect inherited DOCKER_HOST (proxy by default); only force socket as fallback
export DOCKER_HOST="${DOCKER_HOST:-tcp://docker-proxy:2375}"
```

### `freqtrade_monitor.py` (line 24)
**Before:**
```python
_DOCKER_HOST = "unix:///var/run/docker.sock"
```
**After:**
```python
_DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://docker-proxy:2375")
```

### `quality_hub_monitor.py` (line 26)
**Before:**
```python
_DOCKER_HOST = "unix:///var/run/docker.sock"
```
**After:**
```python
_DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://docker-proxy:2375")
```

### Stale Comments to Update

All three scripts have comments like `"docker-proxy blocks exec calls"` or `"EXEC=0"`. These are outdated since the proxy now has `EXEC=1` and `POST=1`. Comments should be updated.

---

## 6. Recommended P0-5c Runtime Rollout (L3, separate PR)

**Only after P0-5b is merged and verified:**

1. Snapshot: `docker inspect hermes-green > /opt/data/reports/snapshots/hermes-green-pre-p05c.json`
2. Edit `docker-compose.yml` — remove ONLY this line from `hermes-green`:
   ```yaml
   - /var/run/docker.sock:/var/run/docker.sock:ro
   ```
3. Apply: `docker compose up -d --no-deps hermes-green` (no other containers touched)
4. Verify:
   - Hermes Dashboard: `curl -s http://127.0.0.1:8083/health`
   - `container_watchdog.sh`: verify 4/4 bots `running`
   - `freqtrade_monitor.py`: verify 4/4 bot data
   - `quality_hub_monitor.py`: verify report generation
   - SI v2 active cycle: 4/4 bots, `mutations=0`, `approval=PENDING_HUMAN`
5. Rollback: re-add the mount line, `docker compose up -d --no-deps hermes-green`

**Do NOT touch in P0-5c:**
- `/home/hermes/projects:rw` — agent lifecycle depends on it
- `/opt/hermes/ssh:ro` — GitHub SSH depends on it
- `/opt/hermes-green/config:/opt/data` — Hermes runtime depends on it
- `trading-guardian` container — separate scope, separate audit

---

## 7. Additional Risk: `trading-guardian`

The `trading-guardian` container also has `/var/run/docker.sock:/var/run/docker.sock:ro` mounted directly. This is **out of scope** for P0-5 but should be tracked as a separate hardening item. The guardian runs `external_cron_guardian.sh` which uses `docker exec` and `docker ps`.

---

## 8. Non-Goals

- ❌ No Docker mount changes (this is an audit only)
- ❌ No runtime mutation
- ❌ No container restart
- ❌ No credential changes
- ❌ No ShadowLock change
- ❌ No live trading
- ❌ No `trading-guardian` hardening (separate scope)

---

## 9. No-Secret Guarantee

No secret values were read, printed, or stored during this audit. Only Docker metadata (container names, statuses, network IPs, environment variable names) was collected. The `AUTH` environment variable of `docker-proxy` was intentionally redacted.

---

## 10. Rollback Considerations for Future L3 Rollout

If P0-5c causes issues after deployment:

1. **Immediate rollback:** Re-add the socket mount line to `docker-compose.yml`, run `docker compose up -d --no-deps hermes-green`
2. **Script rollback:** If P0-5b script changes cause issues, revert the commit and restart cron jobs
3. **No data loss risk:** Socket mount removal does not affect volumes, databases, or persistent state
4. **Monitoring:** Watch for `container_watchdog.sh` silent failures (file-based fallback is less accurate but non-fatal)

---

*Report path: `docs/reports/p0-5a-hermes-green-docker-mount-impact-audit-2026-06-22.md`*  
*Operation Level: L0 (read-only inspection)*  
*Next Step: P0-5b repo fix (3 scripts) → then P0-5c L3 runtime rollout*
