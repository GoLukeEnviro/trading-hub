# Hermes Green Permission Fix — 2026-05-28

## Executive Summary

Hermes Green permission issues are resolved for the known orchestrator runtime blockers.

The correct operating model is:

- Keep the container root-init model.
- Do not force Compose-level `user: "1337:1337"`.
- Let the container initialize as root.
- Hermes runtime processes drop to UID/GID `10000:10000`.
- Runtime-owned profile artifacts must be readable/writable by UID/GID `10000:10000`.

## Failed Strategy

A direct Compose-level UID switch was tested:

```yaml
user: "1337:1337"
```

This failed because the image requires root during startup/init.

Observed failure:

```text
mkdir: cannot create directory '/opt/data': Permission denied
```

That strategy was abandoned.

## Correct Runtime Model

Validation showed:

```text
PID 1 / init shell: root
Hermes runtime processes: UID/GID 10000:10000
default docker exec id: root, expected
```

Therefore, the right fix is targeted host-side ownership for mounted runtime artifacts, not forcing the full container user.

## Fixed Blockers

Original blockers:

```text
/opt/hermes-green/config/profiles/orchestrator/config.yaml
/opt/hermes-green/config/profiles/orchestrator/gateway.lock
```

Follow-up blockers:

```text
/opt/hermes-green/config/profiles/orchestrator/sessions/sessions.json
/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json
```

Final target state:

```text
10000:10000 700 /opt/hermes-green/config/profiles/orchestrator
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/config.yaml
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/sessions/sessions.json
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/cron/jobs.json
```

`gateway.lock` is runtime-owned and managed by the runtime; mode may be normalized by the application.

## Backups

Targeted permission backup directories:

```text
/root/hermes-permission-backups/20260528-170709
/root/hermes-permission-backups/sessions-cron-20260528-175435
```

## Validation Result

Validation after targeted fixes:

```text
hermes-green status: running
restart_count: 0
runtime UID/GID: 10000:10000
known Permission Denied errors for config.yaml/gateway.lock/sessions.json/jobs.json: gone
rollback: not needed
```

## Explicit Non-Changes

The following were intentionally not changed:

* No sudoers changes.
* No Docker group changes.
* No `/etc/restic` changes.
* No `/opt/backups` changes.
* No `freqtrade-*` container changes.
* No broad recursive `chown` or `chmod`.
* No Compose-level `user: "1337:1337"`.
