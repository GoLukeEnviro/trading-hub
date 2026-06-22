# P0-5c: hermes-green Socket Mount Removal — BLOCKED by Config Drift

**Date:** 2026-06-22  
**Operation Level:** L3 (attempted, rolled back)  
**Verdict:** **RED — Cannot proceed safely due to compose/container config drift**

---

## Executive Summary

P0-5c (removing the direct `/var/run/docker.sock` mount from `hermes-green`) was approved and initiated. The compose file edit was correct (exactly one line removed, verified). However, **recreation of the container failed** because the running `hermes-green` container has significant configuration drift from the `docker-compose.yml` file.

**No mutation occurred.** The compose file was reverted to its original state. No containers were restarted, stopped, or recreated.

---

## What was done

1. ✅ Phase 0 Preflight: `main` at `f1fd086`, synced, clean
2. ✅ Phase 1 Snapshot: Complete (at `/opt/data/reports/p0-5c-hermes-green-socket-removal-20260622T201246Z/`)
3. ✅ Phase 2 Compose edit: Removed exactly one line, diff verified
4. ❌ Phase 3 Runtime rollout: BLOCKED — `docker compose up` failed

---

## Root Cause: Compose ↔ Container Config Drift

### 1. Missing `env_file`

The compose file references:
```yaml
env_file: /opt/hermes-green/.env
```

This path **does not exist** on the host. Docker Compose returns exit code 14 ("env file not found"). The actual `.env` file lives at `/opt/data/.env` (mapped into the container at `/opt/data/.env` via the `/opt/hermes-green/config:/opt/data` volume mount).

### 2. Mount Drift

The running container has mounts NOT present in `docker-compose.yml`:

| Mount in running container | In docker-compose.yml? |
|---------------------------|----------------------|
| `/opt/hermes-green/scripts/01b-orchestrator-autostart → /etc/cont-init.d/01b-orchestrator-autostart:ro` | ❌ **NO** |
| `/opt/hermes-green/scripts/99-telegram-settle-delay → /etc/cont-init.d/99-telegram-settle-delay:ro` | ✅ Yes |

The compose file is missing the `01b-orchestrator-autostart` init script mount.

### 3. Docker Compose CLI Not Available

Neither `docker compose` (Go plugin) nor `docker-compose` (Python) was installed. Docker Compose v2.30.0 was installed during this attempt as a Go plugin at `~/.docker/cli-plugins/docker-compose`.

### 4. Image Tag Mismatch

- Compose file: `nousresearch/hermes-agent:latest`
- Running container: `nousresearch/hermes-agent:c11.2-hermes-home`

A recreate would pull `latest` and replace the pinned `c11.2-hermes-home` tag.

---

## Impact Assessment

A successful `docker compose up -d --no-deps hermes-green` from the current compose file would produce a **different container**:

- ❌ Missing `01b-orchestrator-autostart` init script (orchestrator autostart breaks)
- ❌ Different image tag (`:latest` vs `:c11.2-hermes-home`)
- ❌ Missing env vars from `/opt/hermes-green/.env` (compose can't load the file)
- ❌ Potential loss of runtime state

This would likely **break Hermes orchestrator auto-start** and potentially **break agent execution**.

---

## Rollback Performed

```bash
# Reverted compose file to pre-edit state
cp /opt/data/reports/p0-5c-.../docker-compose-before.yml docker-compose.yml
# Verified: socket mount restored, git diff clean
# No container was recreated
```

**No runtime mutation occurred.** The running `hermes-green` container is unchanged.

---

## Recommended Next Steps

Before P0-5c can be retried, the compose file must be reconciled with the actual container configuration:

1. **Fix `env_file` path:** Either move the `.env` to `/opt/hermes-green/.env` or update the compose reference to match the actual path
2. **Add missing mount:** Add `/opt/hermes-green/scripts/01b-orchestrator-autostart` to the compose file
3. **Pin image tag:** Change `:latest` to `:c11.2-hermes-home` in the compose file
4. **Test compose config:** Run `docker compose config` and compare output with `docker inspect hermes-green`
5. **Only then retry P0-5c** with the reconciled compose file

These fixes should be done in a separate PR before attempting P0-5c again.

---

## Evidence

- Snapshot directory: `/opt/data/reports/p0-5c-hermes-green-socket-removal-20260622T201246Z/`
- Pre-edit compose backup: `docker-compose-before.yml`
- Container inspect (before): `inspect-before-hermes-green.json`
- Compose diff (reverted): No remaining diff

## Non-Goals (unchanged)

- No proxy permission hardening
- No other mount changes
- No trading changes
- No ShadowLock changes
- No credential changes
- No guardian changes

---

*Operation Level: L3 (attempted, aborted, rolled back)*  
*Status: RED — compose/container drift blocks safe recreation*  
*Next Step: Reconcile compose file with running container, then retry P0-5c*
