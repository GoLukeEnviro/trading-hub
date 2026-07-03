# Rainbow Producer Boot-Persistence Plan

> **Status:** Draft — requires explicit approval before enabling any auto-start mechanism
> **Date:** 2026-07-03
> **Issue:** #325 — Phase D
> **Dependencies:** Phase A (persistent paths) ✅, Phase B (factory logging) ✅, Phase C (controlled restart) ⬜

---

## 1. Goal

Enable the Rainbow Producer to survive host reboots, container restarts, and non-interactive process termination without manual operator intervention. The producer must automatically resume signal production after any system-level restart.

## 2. Current State

| Component | Status | Detail |
|-----------|--------|--------|
| Persistent PID path | ✅ | `/opt/data/rainbow/rainbow-producer.pid` |
| Persistent log path | ✅ | `/opt/data/rainbow/rainbow-producer.log` |
| Factory logging | ✅ | `setup_logging()` in `create_app()` — committed to `ai4trade-bot` |
| Readiness checker | ✅ | `orchestrator/scripts/rainbow_producer_readiness_check.py` — 26 tests |
| Manager script | ✅ | `orchestrator/scripts/rainbow_producer_manager.sh` — start/stop/status/restart/health |
| Producer currently | ⬜ **Stopped** | Last run ended 2026-06-25T17:40:35Z |
| Auto-restart | ❌ **Not enabled** | Requires explicit approval |

## 3. Auto-Start Options

### Option A — Cron-based restart (recommended first step)

A cron job that runs every 5 minutes and checks if the producer is running. If not, starts it.

```cron
*/5 * * * * /opt/data/trading/orchestrator/scripts/rainbow_producer_manager.sh status || /opt/data/trading/orchestrator/scripts/rainbow_producer_manager.sh start
```

**Pros:** Simple, auditable, reversible, no system config changes.
**Cons:** Up to 5-minute gap after reboot before producer resumes.

### Option B — systemd service

A systemd unit file that starts the producer on boot and restarts it on failure.

```ini
[Unit]
Description=Rainbow Producer
After=network.target

[Service]
Type=simple
User=hermes
WorkingDirectory=/opt/data/ai4trade-bot
ExecStart=/opt/data/ai4trade-bot/.venv/bin/python3 -m uvicorn rainbow.main:create_app --factory --host 127.0.0.1 --port 8000 --log-level info
Restart=on-failure
RestartSec=10
PIDFile=/opt/data/rainbow/rainbow-producer.pid

[Install]
WantedBy=multi-user.target
```

**Pros:** Immediate restart on boot, configurable restart policy, standard Linux mechanism.
**Cons:** Requires sudo/systemd access, harder to audit, more invasive.

### Option C — Docker container

Run the Rainbow producer as a Docker container with `restart: unless-stopped`.

**Pros:** Consistent with existing fleet architecture, Docker-native restart policy.
**Cons:** Requires Dockerfile update, port mapping, network configuration.

## 4. Approval Gate

Before any auto-start mechanism is enabled, ALL of the following must be true:

| # | Requirement | Status |
|---|-------------|:------:|
| 1 | Phase C controlled restart completed and verified | ⬜ |
| 2 | Readiness checker reports GREEN after restart | ⬜ |
| 3 | At least 1 successful SI-v2 Active Cycle with fresh Rainbow signals | ⬜ |
| 4 | Explicit `APPROVED_RAINBOW_AUTO_START` marker in `docs/decisions/` | ⬜ |
| 5 | Rollback plan documented (disable auto-start, revert to manual) | ⬜ |

## 5. Rollback Plan

If auto-start causes issues:

1. **Cron:** Remove or comment the cron line: `crontab -e`
2. **systemd:** `sudo systemctl disable rainbow-producer && sudo systemctl stop rainbow-producer`
3. **Docker:** `docker stop rainbow-producer && docker rm rainbow-producer`

After rollback, the producer can still be started manually via the manager script.

## 6. Safety Invariants

- No change to SI-v2 scoring logic
- No bypass of Rainbow freshness guard (900s)
- No synthetic re-timestamping
- No `dry_run=false`
- No live trading mutation
- No change to `can_execute=False` / `dry_run_only=True`
