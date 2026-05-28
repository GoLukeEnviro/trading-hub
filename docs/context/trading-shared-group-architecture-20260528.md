# Trading Fleet Shared-Group Permission Architecture

**Date:** 2026-05-28
**Status:** CANONICAL — Do not modify without understanding the UID implications below.

---

## Core Architecture Decision

**UID 10000 is the canonical runtime UID for all freqtrade trading bots.**

The custom Docker image `freqtrade-hermes10000:stable` was explicitly built with
UID/GID 10000 for the `ftuser` user. This was a deliberate design choice, not an accident.

```dockerfile
# Dockerfile.hermes10000
FROM freqtradeorg/freqtrade:stable
USER root
RUN groupmod -g 10000 ftuser \
 && usermod -u 10000 -g 10000 ftuser \
 && chown -R 10000:10000 /home/ftuser
USER ftuser
```

**Switching containers to UID 1337 (hermes) is UNSAFE.** It would break:
- /home/ftuser/ ownership (Python cache, pip, temp files)
- Internal freqtrade paths that assume ftuser (UID 10000)
- Potentially cause subtle runtime errors hours later

---

## The Problem: UID Drift

| Component | UID | Writes to |
|-----------|-----|-----------|
| Container (freqtrade) | 10000 | user_data/, shared/ |
| Host user hermes | 1337 | user_data/, shared/ |
| Guardian service | 1337 | signal files, jobs.json |

Same files, different UIDs = constant permission drift.
Previous "fix": Guardian chown repair loops every 5 minutes.
Result: I/O overhead, timeout risk, the loops were part of the problem.

---

## The Solution: Shared-Group Model

Instead of forcing one UID, use a **common group** for cooperative access.

### Host Setup

```bash
# 1. Create host group matching container GID
groupadd -g 10000 ftuser

# 2. Add hermes to the group
usermod -aG ftuser hermes

# 3. Set runtime directories to shared ownership + setgid
chown -R 1337:10000 <runtime-path>
find <runtime-path> -type d -exec chmod 2775 {} \;
find <runtime-path> -type f -exec chmod g+rw {} \;
```

### Why setgid (2775)?

The setgid bit ensures new files inherit the group `ftuser (10000)`.
So files created by the container (UID 10000, GID 10000) get group 10000.
And files created by hermes (UID 1337, in group 10000) also get group 10000.
Both can write via group permissions. No drift. No repair loops.

### Validated On

| Bot | Date | Result |
|-----|------|--------|
| freqforge-canary | 2026-05-28 23:50 | STABLE — container writes, hermes writes, no drift |
| regime-hybrid | 2026-05-29 00:01 | STABLE — container writes, hermes writes, no drift |

---

## Guardian Changes

The `external_cron_guardian.sh` had a Section 5 with find+chgrp+chmod repair loops.
These were **removed** (backup: `external_cron_guardian.sh.pre-cleanup`).

Guardian is now **monitoring-only** for permissions:
- Jobs.json health check — KEPT
- Signal freshness detection — KEPT
- Stale signal heartbeat/pipeline trigger — KEPT
- Script existence check — KEPT
- Backup/restore for jobs.json — KEPT
- Permission drift auto-fix — REMOVED (no longer needed)

---

## Anti-Patterns Avoided

| Anti-Pattern | Why It's Wrong |
|-------------|----------------|
| `user: "1337:1337"` on containers | Breaks ftuser home/cache, Python internals |
| Global `chown -R 1337:1337` on runtime dirs | Same problem in reverse |
| Guardian chown repair loops | Causes drift/timeout, treats symptom not cause |
| Rebuilding image for UID 1337 | Unnecessary, working image exists |
| ACL-based permissions | Complex, hard to debug, overkill |

---

## Git Hygiene

Runtime state files must NOT be tracked in Git:
- `**/primo_signal_state.json` — in .gitignore
- `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal` — in .gitignore
- `shared/hermes_signal.json` — in .gitignore
- `logs/` — in .gitignore

The fixture file `hermes_signal_fixture_20260520.json` IS tracked because
it's referenced by bot configs as `research_signal_file`.

---

## Rollout Status

| Bot | Shared-Group Applied | Status |
|-----|---------------------|--------|
| freqforge-canary | YES | STABLE |
| regime-hybrid | YES | STABLE |
| freqforge | NO | Next rollout candidate |
| freqai-rebel | NO | After freqforge |
| freqtrade-webserver | NO | Different image (freqtrade:stable, ftuser) |

---

## Rollback

If shared-group causes issues on a bot:
```bash
# Revert to hermes-only ownership
chown -R hermes:hermes <runtime-path>
chmod -R 755 <runtime-path>
```
And re-enable Guardian Section 5 from the backup:
```bash
cp external_cron_guardian.sh.pre-cleanup external_cron_guardian.sh
```

---

## File Ownership Rules

| Path | Owner | Group | Pattern |
|------|-------|-------|---------|
| /home/hermes/projects/trading/** | hermes (1337) | hermes (1337) | Source code, configs |
| /home/hermes/projects/trading/*/user_data/ | hermes (1337) | ftuser (10000) | Runtime data (2775) |
| /home/hermes/projects/trading/freqtrade/shared/ | hermes (1337) | ftuser (10000) | Shared signals (2775) |
| /opt/hermes/config/** | root or 10000 | ftuser (10000) | Hermes agent config |
| /etc/**, /root/** | root | root | System files |

**Rule: Repo files = hermes:hermes. Runtime dirs = hermes:ftuser with setgid.**

---

*Generated 2026-05-28 — Validated on freqforge-canary and regime-hybrid*
