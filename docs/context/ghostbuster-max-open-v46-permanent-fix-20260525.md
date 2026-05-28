# GhostBuster + max_open_trades v4.6 Permanent Fix — 2026-05-25

## Scope

- Fix `ghostbuster.log` `PermissionError` permanently.
- Keep GhostBuster in safe detection-only mode.
- Re-verify the v4.5 `max_open_trades` root-cause repair for regressions.
- Re-run the required verification stack.

## Root Cause

GhostBuster appended directly to `/home/hermes/projects/trading/orchestrator/logs/ghostbuster.log` with a plain `open(..., "a")`.
When the file drifted to a non-group-writable state (`0644`), cron-context execution as `hermes` lost write access and the job failed.

## Structural Fix Applied

### 1. Log file hardening in `orchestrator/scripts/ghostbuster.py`

Added:
- `LOG_PATH`, `LOG_FILE_MODE=0o664`, `LOG_DIR_MODE=0o2775`
- Hermes UID/GID discovery via `pwd` / `grp`
- `secure_path_permissions(...)`
- `atomic_append_log(...)`
- explicit `SAFE_DETECTION_ONLY_MODE = True` guard

Behavior now:
- creates the log directory if missing
- creates the log file if missing
- forces ownership to `hermes:hermes` where permitted
- forces mode `0664`
- writes via temp file + `os.replace()` + final `chown/chmod`

### 2. Cron profile sync

Updated both locations:
- `/home/hermes/projects/trading/orchestrator/scripts/ghostbuster.py`
- `/opt/data/profiles/orchestrator/scripts/ghostbuster.py`

### 3. Immediate filesystem repair

Normalized live log file to:
- `/home/hermes/projects/trading/orchestrator/logs/ghostbuster.log`
- owner/group: `hermes:hermes`
- mode: `0664`

## Verification

### GhostBuster log recreation / append test

Executed as user `hermes`:
1. backed up previous log
2. removed live `ghostbuster.log`
3. ran GhostBuster once → file recreated as `0664 10000:10000`
4. ran GhostBuster again → append succeeded and size increased
5. executed profile copy from `/opt/data/.../ghostbuster.py` as `hermes` → append succeeded again

Observed result:
- recreated file: `0664`, uid/gid `10000:10000`
- second append: successful
- profile-script append: successful

Backup retained at:
- `/home/hermes/projects/trading/orchestrator/logs/ghostbuster.log.pre-v46.20260525T051648Z.bak`

### Ancillary cron permission drift found during verification

GhostBuster surfaced a separate read issue on `/opt/data/profiles/orchestrator/cron/jobs.json` (`root:root 0600`).
That was normalized back to readable cron-safe permissions (`group=10000`, mode `0640`) so GhostBuster can scan jobs again in cron context.

### max_open_trades regression check

Live configs verified:
- FreqForge: `dry_run=true`, `max_open_trades=5`
- Canary: `dry_run=true`, `max_open_trades=3`
- Regime-Hybrid: `dry_run=true`, `max_open_trades=5`
- Rebel: `dry_run=true`, `max_open_trades=0`

`system_optimizer.py` re-run confirmed:
- consecutive-loss expiry path no longer re-locks the fleet
- restore path sees the correct baseline values (`5 / 3 / 5`)
- expired guard state is cleaned without reapplying `max_open_trades=0`

### Required run verification

Executed:
- GhostBuster (as `hermes`, profile script): PASS
- `system_optimizer.py`: PASS
- `trading_pipeline.py --dry-run`: PASS
- `quality-hub-monitor` manual cron trigger: dispatched successfully
- `Fleet Report (alle 4h)` manual cron trigger: dispatched successfully

## Safety

- No live trading enabled.
- No exchange credentials added.
- No destructive prune/remove logic added to GhostBuster.
- GhostBuster remains detection-only.
- Trading pipeline was verified in `--dry-run` mode to avoid paper-portfolio mutation during validation.
