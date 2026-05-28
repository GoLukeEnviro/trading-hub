# Guardian Permission Model — Post-Cleanup State

**Date:** 2026-05-28
**Status:** ACTIVE — reflects current production state

---

## What Changed

The Guardian script `external_cron_guardian.sh` had Section 5 with
find+chgrp+chmod repair loops that ran every 5 minutes.

These were removed because:
1. They masked the real problem (UID mismatch)
2. They caused I/O overhead and timeout risk
3. The shared-group model makes them unnecessary

**Backup of original:** `external_cron_guardian.sh.pre-cleanup`

---

## Current Guardian Behavior

| Section | Function | Status |
|---------|----------|--------|
| 1 | jobs.json health + backup restore | ACTIVE |
| 2 | Stuck jobs detection | ACTIVE |
| 3 | Signal freshness + heartbeat/pipeline trigger | ACTIVE |
| 4 | Critical script existence check | ACTIVE |
| 5 | Permission drift repair | DISABLED |
| 6 | Summary/alert count | ACTIVE |

---

## Timeout Investigation

The Guardian timed out once at 23:50 CEST on 2026-05-28.
Root cause: Network call in Section 3 (hermes-agent pipeline trigger hung).
Not related to permission changes. CPU time was only 126ms for a 120s timeout.

Post-cleanup runs complete in ~80-100ms with Exit 0.

---

## Restore chown in Sections 1 and 4

Sections 1 and 4 contain `chown 10000:10000` for restored/copied files.
These are NOT repair loops — they are one-time ownership fixes after
backup restore or script copy operations. They should remain as-is.

These operate on `/opt/hermes/config/profiles/orchestrator/` (Hermes agent config),
not on trading bot runtime paths.

---

*Generated 2026-05-28*
