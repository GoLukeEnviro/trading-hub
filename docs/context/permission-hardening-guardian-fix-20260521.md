# Permission Hardening Guardian Fix — 2026-05-21

## Breaking-Change Assessment

**NO BREAKING CHANGES.** All Freqtrade bot containers remained running throughout. Only the `trading-guardian` container was rebuilt and restarted.

## What Changed and Why

### Problem
The active `trading-guardian` Docker container ran v1 of `external_cron_guardian.sh` which lacked any permission drift detection. The Hermes gateway process (root) and container writers (UID 1000) regularly create files that become unreadable by cron jobs (UID 10000), causing cascading `Permission denied` errors across drawdown_guard, fleet_risk_update, and memory-backfill.

### Solution
Added a permission drift guard (Section 5) to the guardian script that:
- Checks 3 directories for correct mode (2775) and group (10000)
- Checks 5 critical runtime files for correct mode and group
- Checks cron dir for root:root files
- Supports `PERMISSION_GUARD_MODE=check` (report only) and `repair` (fix drift)
- Runs every 5 minutes inside the guardian loop
- Never touches configs, strategies, DBs, model files, or any path not explicitly listed

## Files Edited

| File | Change |
|------|--------|
| `orchestrator/guardian/scripts/external_cron_guardian.sh` | Added Section 5 permission drift guard (122 new lines) |
| `trading-guardian` Docker image | Rebuilt with updated script |

## Backups Created

Location: `orchestrator/backups/20260521T105935Z-permission-hardening/`

| Backup File | Original |
|-------------|----------|
| `external_cron_guardian.sh.bak` | v1 Docker guardian script (134 lines, no perm guard) |
| `external_cron_guardian_host_v2.sh.bak` | Host v2 script (163 lines, has perm guard but not running) |
| `guardian_loop.sh.bak` | Unchanged guardian loop |
| `Dockerfile.bak` | Unchanged Dockerfile |

Pre-replace container inspect: `docs/context/trading-guardian-inspect-before-permission-hardening-20260521T110700Z.json`

## Guardian Rebuild/Restart Details

- Old image tagged as `trading-guardian:pre-permission-hardening-backup` (sha256:3f38c5bd586c)
- New image: `trading-guardian:permission-hardening-candidate` → tagged as `trading-guardian:latest`
- Container recreated with identical volume mounts and restart policy
- Zero Freqtrade bot restarts
- First successful guardian cycle logged at 2026-05-21T11:05:24Z

## Permission Contract

### Directories (mode=2775, gid=10000)
| Path | Verified |
|------|----------|
| freqtrade/shared/ | OK |
| freqtrade/logs/ | OK |
| orchestrator/logs/ | OK |

### Files
| Path | Mode | GID | Status |
|------|------|-----|--------|
| freqtrade/shared/primo_signal_state.json | 0644 | 10000 | OK |
| freqtrade/shared/fleet_risk_state.json | 0644 | 10000 | Repaired every cycle (container writer resets) |
| freqtrade/shared/.fleet_risk_state.json.lock | 0664 | 10000 | OK |
| orchestrator/logs/memory-backfill.log | 0664 | 10000 | OK |
| freqtrade/logs/fleet_risk_update.log | 0664 | 10000 | OK |

### Cron Dir
| Path | Fix |
|------|-----|
| /opt/data/profiles/orchestrator/cron/jobs.json | root:root → root:10000 0640 (auto-repaired) |

## Validation Results

| Check | Result |
|-------|--------|
| trading-guardian stays up | PASS |
| No Freqtrade bot restarted | PASS (all Up 11-45h) |
| DrawdownGuard signal check | PASS (FRESH, fleet verdict completed) |
| Momentum reads signal JSON | PASS (fresh=True, 3 pairs) |
| Regime-Hybrid reads signal JSON | PASS (fresh=True, 3 pairs) |
| Memory backfill log writable by hermes | PASS |
| FleetRisk updater runs clean | PASS |
| No Honcho references | PASS |
| No active Permission denied errors | PASS (22 historical, 0 new after fix) |

## Remaining Risks Before Live Trading

1. **fleet_risk_state.json mode race**: The Freqtrade container (UID 1000) writes this file with mode 600 due to container umask. The guardian repairs it every 5 minutes, but there is a window where drawdown_guard may encounter mode 600. This is cosmetic (file is still group-readable by GID 10000). Root fix requires patching the container's umask or adding `os.umask(0o022)` before the write in fleet_risk_manager.py.

2. **Hermes gateway permission regression**: The gateway process may continue writing root:root 0600 files. The guardian's Section 5c now auto-corrects this for the cron dir, but if new root:root files appear in other directories, they will only be caught if added to the PERM_FILES list.

3. **No RiskGuard/Judge service deployed** (spec only, not a permission issue).

## Rollback Instructions

```bash
# 1. Stop and remove the new guardian
docker stop trading-guardian
docker rm trading-guardian

# 2. Recreate with the pre-fix image
docker run -d --name trading-guardian \
  --restart unless-stopped \
  -v /home/hermes/projects/trading:/guardian/data \
  -v /opt/data/profiles/orchestrator/cron:/guardian/cron \
  -v /opt/data/profiles/orchestrator/scripts:/guardian/scripts \
  -v /var/run/docker.sock:/var/run/docker.sock \
  trading-guardian:pre-permission-hardening-backup

# 3. Restore backup script (if needed)
cp orchestrator/backups/20260521T105935Z-permission-hardening/external_cron_guardian.sh.bak \
   orchestrator/guardian/scripts/external_cron_guardian.sh
```

## Overlap with Inline Patches

| Protection | Scope | Status |
|------------|-------|--------|
| `os.fchmod(0o644)` in fleet_risk_manager.py | Write path for fleet_risk_state.json | Active, complementary |
| `os.fchmod(0o644)` in trading_pipeline.py | Write path for primo_signal_state.json | Active, complementary |
| Guardian Section 5 (this fix) | Detects drift from ALL sources | Active, every 5 min |

The inline patches prevent regressions from the code's own write path. The guard detects regressions from external sources (Hermes root process, container restarts, manual operations). Both are needed.
