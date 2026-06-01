# Hermes Runtime Ownership Contract

**Created:** 2026-06-01
**Status:** ACTIVE
**Purpose:** Define canonical owner/group/mode for every runtime directory and state file. No permission repair may deviate from this contract.

---

## Identity Map

| Identity | UID | GID | Where Used |
|----------|-----|-----|------------|
| root | 0 | 0 | Hermes gateway process, trading-guardian, Docker daemon |
| hermes (container) | 10000 | 10000 | Hermes cron scheduler, Hermes subagent terminals |
| ftuser (freqforge/canary/regime) | 10000 | 10000 | Freqtrade stable bots |
| ftuser (freqai-rebel) | 1000 | 1000 | FreqAI Rebel bot |
| project tree owner | 1337 | 1337 | /home/hermes/projects/trading/ (host filesystem) |

## Bind Mount Truth

```
Host path:                    Container path (inside hermes-green):
/opt/hermes-green/config  →  /opt/data
/home/hermes/projects     →  /home/hermes/projects (rw)
```

The cron scripts directory `/opt/data/profiles/orchestrator/scripts/` IS `/opt/hermes-green/config/profiles/orchestrator/scripts/` on the host.

## Directory Ownership Contract

| Directory | Owner:Group | Mode | Writer | Notes |
|-----------|-------------|------|--------|-------|
| `orchestrator/scripts/` (project) | 1337:1337 | 2775 (setgid) | Git, Hermes agent | Git-tracked source of truth |
| `orchestrator/scripts/` (cron) | hermes:hermes (10000:10000) | 755 | Deploy script only | Deployed from Git, never edited directly |
| `orchestrator/state/` | 1337:1337 | 2775 (setgid) | system_optimizer.py, drawdown_guard.py, various cron scripts | State files are rw-rw-r-- |
| `orchestrator/logs/` | hermes:hermes (10000:10000) | 2775 (setgid) | All cron scripts | Cron-internal logs |
| `orchestrator/config/` | 1337:1337 | 2775 | Hermes agent | Config backups |
| `docs/context/` | 1337:1337 | 2775 (setgid) | Hermes agent | Documentation |
| `cron/` | hermes:hermes (10000:10000) | 755 | Hermes gateway (writes jobs.json as root:root, guardian fixes to 10000:10000) |
| `freqtrade/shared/` | 1337:hermes (10000) | 2775 (setgid) | trading_pipeline.py, system_optimizer.py, fleet_risk_manager.py |
| `freqtrade/logs/` | hermes:hermes (10000:10000) | 2775 (setgid) | Freqtrade bots |

## File Ownership Contract

### jobs.json
| Attribute | Value |
|-----------|-------|
| Path | `cron/jobs.json` |
| Canonical owner | root:10000 |
| Canonical mode | 0640 |
| Writer | Hermes gateway (root) |
| Reader | Hermes cron scheduler (UID 10000) |
| Repair | trading-guardian every 5 min: chgrp 10000, chmod 640 |

### State Files (orchestrator/state/)
All state files: owner 1337:1337 or root:1337 or 1337:hermes, mode 664.
Writer-specific notes:

| File | Writer | Notes |
|------|--------|-------|
| `drawdown_state.json` | drawdown_guard.py (root via docker exec) | Written as root:1337 664 |
| `drawdown_state_prev.json` | drawdown_guard.py | Copy of previous state |
| `consec_loss_state.json` | system_optimizer.py (root via docker exec) | Written as root:1337 664 |
| `container_watchdog_state.json` | container_watchdog.sh | Written as 1337:1337 664 |
| `equity_high.json` | system_optimizer.py | Written as 1337:1337 664 |
| `fleet_risk_state.json` | fleet_risk_update_watchdog.sh | Written as hermes:hermes via trading-guardian |
| `primo_signal_state.json` | trading_pipeline.py | Written via Docker exec into containers |

### Cron Scripts (orchestrator/scripts/)
| Attribute | Value |
|-----------|-------|
| Canonical owner | hermes:hermes (10000:10000) |
| Canonical mode | 711 (rwx--x--x) for .py, 711 for .sh |
| Source | Git-tracked project tree (1337:1337 775) |
| Deployer | `deploy_cron_scripts.sh` |

The deploy script copies from project tree to cron dir and sets ownership.

## Permission Repair Rules

### Single Source of Repair: trading-guardian
The trading-guardian container (every 5 min) is the ONLY component that may modify ownership/mode.

### What trading-guardian repairs (scoped):
1. `cron/jobs.json`: root:root → root:10000 0640
2. Explicit PERM_FILES list with expected mode:group
3. Explicit PERM_DIRS list with expected mode 2775 and group 10000

### What NO component may do:
- Broad `find -chown -chmod` over `/opt/data/profiles/orchestrator/` or subdirectories
- `chmod 777` anywhere
- Recursive `chown` over the full project tree
- Modify ownership of files not in the PERM_FILES contract
- Change script ownership in the project tree (1337:1337)

### What ghostbuster.py does:
- REPORT-ONLY for permission drift (warns, does not fix)
- Actual fix deferred to trading-guardian

## Deployment Model

```
Git (source of truth)                    Runtime (deployed copy)
1337:1337 775                              hermes:hermes 711
/home/hermes/projects/trading/              /opt/data/profiles/orchestrator/
  orchestrator/scripts/*.py --deploy-->      orchestrator/scripts/*.py
  orchestrator/scripts/*.sh --deploy-->      orchestrator/scripts/*.sh

Deploy tool: orchestrator/scripts/deploy_cron_scripts.sh
Never edit runtime scripts directly.
```

## Rollback

If a deploy causes issues:
1. Stop the deploy
2. `git checkout -- orchestrator/scripts/` to restore project tree
3. Re-run deploy to sync the restored version
4. Verify with `python3 -c "import ast; ast.parse(open('script.py').read())"` for syntax

## Violations

Any script or process that silently modifies ownership outside the trading-guardian's explicit contract is a violation and must be reported and fixed.
