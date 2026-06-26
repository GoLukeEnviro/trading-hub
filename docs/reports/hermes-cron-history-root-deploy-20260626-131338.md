# Hermes Cron History Root Deploy — YELLOW Report

**Date (UTC):** 2026-06-26 13:13:38
**Auditor:** Hermes (orchestrator profile)
**Operation Level:** L3 root-gated file-level deploy
**Final Status:** **YELLOW — sudo binary unavailable in Hermes Agent environment**
**Approval token received:** yes (`APPROVE_ROOT_DEPLOY` received)
**Root command executed:** no (tooling missing)
**No restart, no jobs.json edit, no trading param change, no broad chmod/chown.**

---

## Executive Verdict

**YELLOW — 70/100**

L2-Tooling (PRs #365/#366/#367) GREEN, runtime-Tool deployed und funktional, Patch-Inhalt SHA-verifiziert bereit. `APPROVE_ROOT_DEPLOY` Token erhalten. **Aber**: die Hermes-Agent-Umgebung hat **kein `sudo` Binary** (`command not found`, exit 127). Der einzige vom Credential-Regelwerk zugelassene Eskalations-Pfad ist damit nicht ausführbar.

Es ist **kein Token-Problem**, **kein Passwort-Problem**, **kein Permission-Problem auf der Datei** — es ist eine **Tooling-Lücke** in der Laufzeit-Umgebung des Agenten.

Keine Credentials wurden gesucht, gedruckt oder anderweitig angefasst. `su` wurde **nicht** versucht (braucht Passwort, das wir nicht haben und das die Credential-Regel zu suchen verbietet).

## Root Credential Handling

| Check | Result |
| --- | --- |
| Credential source printed | **no** |
| Credential source searched for (grep/find/history/env) | **no** |
| Root approval received | **yes** (`APPROVE_ROOT_DEPLOY` × 2) |
| Root command limited to approved helper | **yes** (only one command attempted) |
| Other root-escalation paths tried (su, doas, runuser, …) | **no** |
| `su` with guessed passwords | **no** (forbidden by Credential Rules) |

## Root Deploy Attempt

| Check | Result |
| --- | --- |
| Approval token received | yes (`APPROVE_ROOT_DEPLOY`) |
| Helper executed | **no** — `sudo` binary missing |
| Helper script path | `/opt/data/profiles/orchestrator/state/cron_history_patches/deploy_patched_scheduler.sh` (executable, mode 0755) |
| First attempt | `sudo bash /opt/data/...` → exit 127, `sudo: command not found` |
| Second attempt (after re-approval) | same exit 127, same error |
| Backup created | no (deploy never ran) |
| SHA verified | n/a |
| py_compile in helper | n/a |
| DONE reported | no |

### Environment Facts (from this session)

```text
$ id
uid=1337(hermes) gid=1337(hermes) groups=1337(hermes),110(hostdocker)

$ command -v sudo && sudo -V
sudo: command not found          ← the actual blocker

$ command -v su; command -v doas; command -v runuser
/usr/bin/su                      ← present, setuid, needs password
doas: missing
runuser: missing

$ ls -la /opt/hermes/cron/
drwxr-xr-x 2 10000 10000 ...
-rw-r--r-- 1 10000 10000 97387 ... scheduler.py
```

The Hermes Agent's runtime environment does not ship `sudo`. It ships `su` (setuid-root), but `su` requires the root password, which we deliberately do not search for or guess per the credential rules. The deploy helper is idempotent and SHA-verified — running it as root is the only safe mutation path, and that requires the `sudo` binary.

## Post-Deploy Verify

| Check | Result |
| --- | --- |
| `--status` | `state: unpatched` (pre-deploy state preserved) |
| `--verify` | `ok: False, reason: target not in 'patched' state: unpatched` (correctly reports no patch yet) |
| `scheduler.py` py_compile | **PASS** (in-process, bypasses `/opt/hermes/cron/__pycache__` permission) |
| Markers present | **no** (deploy did not run) |

## Natural Observation

| Check | Before | After |
| --- | ---: | ---: |
| `cron_history.sqlite` rows | 0 | n/a (deploy did not run, observation deferred) |
| latest scheduler-written row | (none) | n/a |
| `jobs.json` selected timestamps | captured `e79cf65e9ea87f5a` | n/a |

Observation phase **not started** — depends on successful deploy.

## Restart Gate

| Field | Value |
| --- | --- |
| `restart_required` | unknown — depends on whether Python reloads `.py` after deploy |
| `restart_performed` | **no** |
| approval needed | `APPROVE_RESTART` (separate prompt, if required after observation) |
| `APPROVE_ROOT_DEPLOY` re-tried | yes, same exit 127 |

## Runtime Safety Checklist

| Item | Status |
| --- | --- |
| `jobs.json` edited | **no** |
| Service restart | **no** |
| Broad `chmod`/`chown` | **no** |
| Trading parameter changes | **no** |
| Secrets exposed | **no** |
| Credential search | **no** |
| `su` with guessed passwords | **no** |

## Rollback

**Not applicable** — no deploy happened. `/opt/hermes/cron/scheduler.py` is unchanged:

```
SHA256: f2816dea78a62445a3291f9ef77e1efd179bd963fc1c378b97d80de630524ce6
Size:   97387 bytes
Mode:   0644
Owner:  10000:10000
```

The deploy artifact remains ready at `/opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.patched` (SHA `ce820537e98bc25ae590eba20399bb6ead58297cbd5c2dd7b7cac6f28a99d74a`, 99185 bytes).

## Final Status

**YELLOW: tool-side blocker — `sudo` binary missing in Hermes Agent environment.**

Real blockers (in priority order):

1. **Provide sudo capability** (or any root-exec mechanism hermes can use without password search):
   - Option A: install `sudo` package in the agent's runtime image and configure passwordless sudo for `hermes` on the approved helper script only.
   - Option B: a setuid-root wrapper that allows hermes to copy the SHA-verified patched file into `/opt/hermes/cron/scheduler.py` after re-verifying the SHA — designed exactly for this kind of one-shot admin action.
   - Option C: a manual deploy by an out-of-band operator with sudo access (i.e. you, on your workstation) — paste the `DONE.` output back so the agent can run Phase 3-6.

2. After deploy + verify pass: start Phase 4 (Observation). If `cron_history.sqlite` does not gain a row within a bounded window, stop and request `APPROVE_RESTART`.

3. After observation passes (one real scheduler-written row exists): Phase 6 writes this report's `GREEN` update and closes the cron-history repair campaign.

## Recommendation

**Do not retry the same `sudo bash ...` command again.** It will fail identically. Pick one of the three options above and tell the agent which one to use.

If Option A (install sudo): the agent itself can attempt `apt-get install -y sudo` if it has a privileged path — but this is a different root action and requires its own approval. Better: configure the runtime image ahead of the next session.

If Option B (setuid wrapper): the agent can author one in the repo, you sign off, install it as root manually, then the agent can use it without `sudo`.

If Option C (manual deploy): you run the command on your workstation and paste the output:

```bash
sudo bash /opt/data/profiles/orchestrator/state/cron_history_patches/deploy_patched_scheduler.sh
```

Once the agent sees `DONE.` (or equivalent success) from that command, it will continue Phase 3 → 4 → 5 → 6.

## Acceptance Criteria Status

| Criterion | Status |
| --- | --- |
| Root credential is never exposed | ✅ |
| Root deploy only occurs after `APPROVE_ROOT_DEPLOY` | ✅ |
| Only approved helper command is run as root | ✅ (single command, run twice with token, both failed at the tooling layer) |
| `scheduler.py` verify and py_compile pass after deploy | ⏸ DEFERRED (no deploy yet) |
| No restart occurs | ✅ |
| No `jobs.json` direct edit | ✅ |
| No secrets exposed | ✅ |
| Full GREEN requires real scheduler-written `cron_history.sqlite` row | ⏸ DEFERRED |
| If restart is needed, stop and request `APPROVE_RESTART` | ⏸ DEFERRED (depends on observation result) |

## Files in this PR

- `docs/reports/hermes-cron-history-root-deploy-20260626-131338.md` — this report (YELLOW).
- **No runtime backups**, **no SQLite DBs**, **no logs**, **no env/secrets**.

Commit message (when ready): `docs: record Hermes cron history root deploy status (YELLOW — sudo binary unavailable)`.
