# P0-5b: Hermes Docker Proxy Script Compatibility

**Date:** 2026-06-22  
**Depends on:** P0-5a audit (`a5e788a`)  
**Next step:** P0-5c L3 runtime rollout (remove socket mount)

## What changed

Three Hermes monitoring scripts no longer force `DOCKER_HOST=unix:///var/run/docker.sock`. They now respect the environment-provided `DOCKER_HOST` (which is `tcp://docker-proxy:2375` inside `hermes-green`).

| Script | Before | After |
|--------|--------|-------|
| `container_watchdog.sh:42` | `export DOCKER_HOST="unix:///var/run/docker.sock"` | Removed — inherits env `DOCKER_HOST` |
| `freqtrade_monitor.py:24` | `_DOCKER_HOST = "unix:///var/run/docker.sock"` | Removed — uses `os.environ.copy()` in subprocess |
| `quality_hub_monitor.py:26` | `_DOCKER_HOST = "unix:///var/run/docker.sock"` | Removed — uses `os.environ.copy()` in subprocess |

## Why direct socket removal is NOT part of this PR

The direct `/var/run/docker.sock` mount in `hermes-green` remains until P0-5c. This PR only makes scripts compatible with the proxy so that P0-5c can safely remove the mount.

## Stale comments updated

All three scripts had comments claiming "docker-proxy blocks exec calls (EXEC=0)". The proxy now has `EXEC=1` and `POST=1` enabled — `docker exec` works through the proxy (verified in P0-5a audit).

## Validation

```bash
bash -n orchestrator/scripts/container_watchdog.sh  # OK
ruff check orchestrator/scripts/freqtrade_monitor.py orchestrator/scripts/quality_hub_monitor.py  # pre-existing lint only
grep -Rni 'unix:///var/run/docker.sock' orchestrator/scripts/{container_watchdog.sh,freqtrade_monitor.py,quality_hub_monitor.py}  # CLEAN
pytest tests/  # 299 passed, 1 skipped
```
