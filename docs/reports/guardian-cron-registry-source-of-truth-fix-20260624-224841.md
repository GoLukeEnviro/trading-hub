# Guardian Cron Registry Source-of-Truth Fix

**Date (UTC):** 2026-06-24T22:48:41Z  •  **Operation Level:** L2  •  **Author:** Claude Code (Claudio)

## Verdict

- **PR / Containment objective:** **GREEN**
  > *trading-guardian now observes the canonical 58-job Hermes cron registry, read-only.*
- **Overall scheduler / restore safety:** **YELLOW** — stale restore vector remains open (P1/P0 follow-up).

This PR must NOT be read as a blanket GREEN. It fixes the Guardian's source-of-truth and
contains the restore/overwrite risk on the Guardian path only.

## Summary

`trading-guardian` was bind-mounted to the **stale/orphan** host cron registry
(`/opt/data/profiles/orchestrator/cron`, 12 jobs, no SI-v2) instead of the **canonical live**
registry that `hermes-green`'s scheduler uses (`/opt/hermes-green/config/profiles/orchestrator/cron`,
58 jobs, SI-v2 `64866012641a` present). Root cause was proven by **inode identity**. The fix is a
single-line compose change repointing `/guardian/cron` to the canonical registry and making it
**read-only**, so the Guardian becomes a pure observer and can no longer overwrite the live
registry via its backup-restore (§1) or permission-repair (§5c) code paths.

## Safety

- **Operation level:** L2 (controlled `trading-guardian` recreate only).
- **Changed:** `orchestrator/guardian/docker-compose.yml` — 1 line (mount source + `:ro`).
- **Not changed:** strategies, bot configs, SI-v2 logic, restore script, backup, Dockerfile,
  hermes-green, Freqtrade bots.
- **No Freqtrade bot restarted:** confirmed (4 bot container IDs unchanged).
- **`hermes-green` not restarted:** confirmed (container ID unchanged).
- **SI-v2 schedule not changed:** SI-v2 job intact, no manual cycle run.
- **No apply-token, no `dry_run=false`.**

## Before State

| Aspect | Value |
|---|---|
| Canonical live registry (host) | `/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json` (inode `1079284`, 58 jobs, SI-v2 present, owner `hermes:hermes`) |
| = inside `hermes-green` | `/opt/data/profiles/orchestrator/cron/jobs.json` (bind `/opt/hermes-green/config`→`/opt/data`) |
| Stale/orphan registry (host) | `/opt/data/profiles/orchestrator/cron/jobs.json` (inode `129767`, 12 jobs, **no** SI-v2, mtime 2026-06-13) |
| Guardian observed registry | `/guardian/cron/jobs.json` → **stale 12-job file** (bind `/opt/data/.../cron`→`/guardian/cron`, rw) |
| SI-v2 visible to Guardian | **no** |
| Guardian container ID (before) | `360ecf1a3b91` |

## Change Implemented

`orchestrator/guardian/docker-compose.yml`, line 10:

```diff
-      - /opt/data/profiles/orchestrator/cron:/guardian/cron
+      - /opt/hermes-green/config/profiles/orchestrator/cron:/guardian/cron:ro
```

**Why `:ro` and not `:rw`:** the baked Guardian script `external_cron_guardian.sh` writes to
`/guardian/cron` in two places — §1 (`cp backup → jobs.json` if missing/invalid) and §5c
(`chmod/chgrp` root:root files). Pointed `:rw` at the **live** registry, a single "invalid JSON"
blip would have let §1 copy the **stale 11-job backup** over the live 58-job registry, deleting
SI-v2. `:ro` makes the Guardian a pure observer; §1/§5c become safe no-ops (and the canonical
files are `hermes:hermes`, not root:root, so §5c finds nothing anyway).

**Why this option over alternatives:** the canonical registry is a reachable host path
(`/opt/hermes-green/config/...`), and a root container can read it despite mode-700 hermes-owned
parents (verified). So Option A (mount repoint) is the minimal, durable, compose-tracked fix — no
image rebuild, no `docker exec` indirection (Option B), no mirror/symlink (Option C).

## Validation (real outputs)

**git diff (only file changed):**
```
orchestrator/guardian/docker-compose.yml
```

**Compose render confirms `:ro`:**
```
source: /opt/hermes-green/config/profiles/orchestrator/cron
target: /guardian/cron
read_only: true
```

**Guardian now reads the canonical registry (58 jobs, SI-v2 visible):**
```
job_count= 58
contains_si_v2_id= True
contains_si_v2_name= True
```

**Mount is read-only (inspect + write-test):**
```
/opt/hermes-green/config/profiles/orchestrator/cron -> /guardian/cron RW=false
WRITE_BLOCKED_OK (:ro wirksam)  ->  "sh: can't create /guardian/cron/jobs.json: Read-only file system"
```

**Container before → after diff (only Guardian recreated):**
```
-trading-guardian  360ecf1a3b91  Up 13 days
+trading-guardian  4f80c27e19ac  Up Less than a second
(hermes-green, freqforge, freqforge-canary, regime-hybrid, freqai-rebel, webserver, ai-hedge: UNCHANGED)
```

**No restore/chmod failure loop under `:ro`:** first post-recreate Guardian run logged
`perm_drift=0` — the prior `PERM_DRIFT_CRON`/`PERM_REPAIR` cron-dir noise **disappeared** (canonical
files are hermes-owned, not root:root). No `RESTORED`/`CRITICAL` triggered (jobs.json valid).

**Canonical registry integrity (the sha256 drift is normal scheduler churn, not this change):**
```
job_count=58, valid_json=True, contains_si_v2_id=True, contains_si_v2_name=True
SI_V2_JOB= {"id":"64866012641a","name":"si-v2-active-cycle (6h, log-only)","enabled":true,
            "schedule":{"expr":"17 */6 * * *"},"next_run_at":"2026-06-25T00:17:00+00:00"}
owner=hermes:hermes mode=600  (writer = hermes-green scheduler, NOT guardian/root)
Guardian mount RW=false -> Guardian can NEVER be the mutation source
```
Note: the canonical `jobs.json` sha256 changed between snapshots (`5e971302…`→`3d0949…`) because
hermes-green continuously rewrites `next_run_at`. The correct sentinel for a live file is
**structural integrity** (58 jobs + SI-v2 + valid JSON + owner hermes), which holds. The Guardian
cannot have caused the drift (proven read-only).

**Static checks:** `git diff --check` OK; secret-scan on diff: none.

## Evidence

- SI-v2 job ID `64866012641a` **visible to Guardian** (was: no).
- `si-v2-active-cycle (6h, log-only)` **visible to Guardian** (was: no).
- 4-bot fleet unchanged (no restart, same container IDs).
- No mutation, no apply-token, no `dry_run=false`.
- Guardian sees the canonical 58-job registry read-only; writes blocked.

## Remaining Risks

1. **Stale restore vector (P1/P0 — open, NOT mitigated by this PR):** scheduled job
   `607f1890215d` ("cron-guardian", `0 */6 * * *`) runs `restore_cron_jobs.sh` inside the hermes
   scheduler. There, `/opt/data/.../jobs.json` resolves to the **live** registry. The script's guard
   (`if CURRENT_COUNT >= 10: skip`) currently holds (58 ≥ 10 → no-op), but if the live registry ever
   drops below 10 jobs, it would `cp` the **stale 11-job backup** (no SI-v2) over the live registry,
   deleting SI-v2 and reducing 58 → 11. → Follow-up issue: harden restore (merge-safe/non-destructive,
   SI-v2 survival, no 58→11 regression).
2. **Container-name false positive (separate PR):** baked `external_cron_guardian.sh` hardcodes
   `ai-hedge-fund-crypto` (lines 93/114/120); real container is `trading-ai-hedge-fund-1`. Log shows
   `CONTAINER_DOWN`/`CONTAINER_RESTART_FAILED` every 5 min. Still present after this fix (expected —
   different root cause, needs image rebuild).
3. **Host-side monitors referencing stale `/opt/data/.../cron`** (`system_optimizer.py`,
   `quality_hub_monitor.py`, `observation_runner.py`, `ghostbuster.py`, `hermes_standby_monitor.py`)
   only if they run on the host rather than inside hermes-green — out of scope here.

## Rollback

Revert the one compose line to `- /opt/data/profiles/orchestrator/cron:/guardian/cron`, then:
```
docker compose --project-directory orchestrator/guardian \
  -f orchestrator/guardian/docker-compose.yml up -d trading-guardian
```
Verify `/guardian/cron/jobs.json` = 12 jobs (stale). Trivial; affects only trading-guardian.

## Final Verdict

- **GREEN** for the containment objective: Guardian observes the canonical 58-job registry, read-only,
  SI-v2 visible, writes blocked, no bot/hermes-green restart, canonical integrity preserved.
- **YELLOW** overall until the stale restore vector (follow-up) is hardened.

## Next Step

Open/execute the follow-up: **"Harden Hermes cron restore backup and restore guard"** (see
`docs/reports/_followup-issue-harden-cron-restore-backup.md`). The container-name false positive is a
parallel, lower-priority follow-up PR.
