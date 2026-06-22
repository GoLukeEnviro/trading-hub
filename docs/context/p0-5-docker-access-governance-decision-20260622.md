# P0-5 Docker Access Governance Decision

**Date:** 2026-06-22  
**Decision Maker:** Luke (system owner)  
**Status:** ACCEPTED — operational risk governed by guardrails below  
**Supersedes:** P0-5c socket mount removal (deferred indefinitely)

---

## Decision

**The direct Docker socket mount (`/var/run/docker.sock:/var/run/docker.sock:ro`) on `hermes-green` will remain in place.** The risk is explicitly accepted and governed.

## Rationale

Hermes/Agent Zero requires Docker execution authority for:
- Container health checks (`docker ps`, `docker inspect`, `docker logs`)
- Fleet diagnostics (`docker exec` against 4 Freqtrade bots for SQLite queries, config validation)
- SI-v2 active cycle telemetry reads (4/4 bot verification)
- Controlled operational interventions (cron-triggered repairs, log rotation)

Removing the socket mount (P0-5c) was blocked by compose/container config drift that would make `docker compose up` produce a **different container** than the running one. Fixing that drift is a separate P1 concern that must not block the SI-v2 loop.

**The Docker socket is operationally needed now. Its removal is optional, not P0.**

---

## Why This Is Not Blocking the SI-v2 Loop

The SI-v2 observation loop depends on reliable Docker API access for reading all four Freqtrade bots. P0-5b already made all monitoring scripts proxy-compatible, so the scripts work with **both** the direct socket and the proxy. The socket's presence or absence is now transparent to the code path.

SI-v2 can proceed with:
- Active cycle reads (4/4 bots)
- Measurement ledger appends
- ShadowProposal generation
- All mutation counters at 0

---

## Security Note

`/var/run/docker.sock:ro` is **not** read-only in the security sense. The `:ro` flag prevents the Docker daemon from writing back to the container's filesystem, but the container can still:
- Read all container state
- Execute arbitrary commands in any container via `docker exec`
- Start/stop containers (if the Docker API allows)
- Inspect all secrets mounted into any container

This is treated as a powerful host-access capability, not a passive read mount.

---

## Guardrails

### Allowed without additional approval (L0/L1 operations)

- `docker ps` — list containers
- `docker inspect` — read container state
- `docker logs` — read container logs
- `docker exec` for **read-only** checks (e.g. `sqlite3` queries, `cat config.json`)
- Health checks and heartbeat verification
- SI-v2 verification runs (4/4 bot telemetry)
- `container_watchdog.sh`, `freqtrade_monitor.py`, `quality_hub_monitor.py`

### Requires explicit human approval (L3 operations)

- `docker compose up` / `docker compose down`
- Container restart / recreate / stop / start
- Image pull / build / tag
- Volume creation / deletion / mount changes
- Network creation / deletion
- `chmod` / `chown` on mounted project or runtime directories
- Cron schedule mutations
- Any operation that can affect trading runtime behavior
- Freqtrade config changes

### Forbidden unless emergency-approved

- `docker system prune`
- Volume deletion
- Network deletion
- `dry_run=false` (live trading activation)
- Secret printing / logging / committing
- Broad recursive permission repair
- Uncontrolled auto-healing that mutates containers

---

## Access Paths

| Path | Mechanism | Current Status |
|------|-----------|----------------|
| Direct socket | `/var/run/docker.sock:ro` mount in `hermes-green` | ✅ Active (accepted risk) |
| Docker proxy | `DOCKER_HOST=tcp://docker-proxy:2375` (EXEC=1, POST=1) | ✅ Active (parallel path) |
| Proxy-only (future) | Remove socket mount, rely on proxy only | Deferred — requires compose drift fix first |

Both paths are active simultaneously. Scripts respect the environment `DOCKER_HOST` variable (P0-5b), which defaults to the proxy inside `hermes-green`.

---

## Future Revisit Conditions

The socket mount removal may be revisited when ALL of the following are true:

1. Compose file is reconciled with the running container (P1 issue)
2. `docker compose config` output matches `docker inspect hermes-green` (no drift)
3. Image tag is pinned in compose (not `:latest`)
4. `env_file` path resolves correctly
5. All init-script mounts are represented in compose
6. A controlled recreate test passes without functional regression

Even then, removal is optional — the guardrails above may suffice for long-term governance.

---

## Compose Drift (Separate P1 Follow-up)

The P0-5c attempt revealed three drift issues that must be tracked separately:

| Issue | Compose File | Running Container | Risk |
|-------|-------------|-------------------|------|
| `env_file` path | `/opt/hermes-green/.env` (not found) | Loaded from `/opt/data/.env` via volume mount | Compose recreate fails |
| Init script mount | Not listed | `01b-orchestrator-autostart` is mounted | Autostart breaks on recreate |
| Image tag | `:latest` | `:c11.2-hermes-home` | Wrong image on recreate |

**Tracked as:** `P1: Reconcile hermes-green Compose definition with live runtime before future recreate`

---

## References

- P0-5a audit: `docs/reports/p0-5a-hermes-green-docker-mount-impact-audit-2026-06-22.md`
- P0-5b script changes: commit `f1fd086`
- P0-5c RED report: `docs/reports/p0-5c-hermes-green-socket-mount-removal-2026-06-22.md`
- P0 security status: `docs/reports/p0-security-status-2026-06-22.md`
