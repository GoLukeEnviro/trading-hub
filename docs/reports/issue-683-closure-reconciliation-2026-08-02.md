# Issue #683 — Read-Only Closure Reconciliation Report

**Date:** 2026-08-02
**Execution class:** A0 (read-only) / A1 (repository-only report)
**Result:** `BLOCKED_BY_MISSING_A2_MARKER` — runtime closure NOT achieved

## Summary

Issue #683 ([P0][A2][Recovery] Restore HermesTrader control plane, dry-run fleet
and native roadmap cron) requires a **runtime baseline green** before closure.
This reconciliation re-verifies every acceptance criterion **read-only** from
the Hermes agent (UID 10000) through the restored root-executor client path.

**Verdict: the runtime baseline is NOT green. The dry-run fleet is stopped,
the writer lock is missing, the roadmap cron is missing, and the deployed
executor does not serve the repository action surface (PR #677/#678).**
The original A2 marker (`APPROVED_A2_HERMESTRADER_RUNTIME_RECOVERY`, valid
until 2026-08-01T18:00:00Z) has **expired**. No self-approval is possible.

## Criterion-by-criterion evidence (all collected 2026-08-02, read-only)

### 1. Executor service active

```
$ systemctl is-active hermes-root-executor.service
active

$ python3 hermes_root client → executor_health
{"decision": "ALLOWED", "reason": "ok", "stdout": "healthy", "audit_id": "76a974ba-7757-4b78-a9a8-53c9e61e1187"}
```

✅ **PASS** — service active, SO_PEERCRED path works (UID 10000 → root daemon).

### 2. Executor action surface (provenance coherence)

Repository `main` (PR #677 `c4dbeea`, #678 `b675708`) defines 75 structured
actions. The deployed daemon rejects most of them:

```
fs_stat                     → BLOCKED reason=unknown_action
fs_ls                       → BLOCKED reason=unknown_action
systemctl_is_active         → BLOCKED reason=unknown_action
executor_version            → BLOCKED reason=unknown_action
executor_provenance         → BLOCKED reason=unknown_action
executor_audit_tail         → BLOCKED reason=unknown_action
docker_ps                   → ALLOWED (returns empty container list — see fleet)
executor_health             → ALLOWED
```

❌ **FAIL** — the running daemon is NOT the repository implementation. This is
exactly the incident fact #683 documents: repository implementation,
operational documentation and deployed runtime have drifted apart. The
one-time root bootstrap from #683 Phase 1 either did not run or was rolled
back; the deployed daemon still exposes only the older partial action set.

### 3. SO_PEERCRED

✅ **PASS** — the Unix socket (`/run/hermes-root-executor/executor.sock`,
`root:hermes 0660`) accepted a UID-10000 client and returned structured,
audited responses. Peer-credential authentication is kernel-enforced.

### 4. Writer lock

```
$ ls -la /opt/data/state/repo-writer/
ls: cannot access '/opt/data/state/repo-writer/': No such file or directory
```

❌ **FAIL** — `/opt/data/state/repo-writer/` (with
`hermes-repo-writer.lock`, `root:root` parent, `10000:10000 0600` lock file)
does **not exist**. The mandatory repository writer contract from AGENTS.md
cannot be exercised. (This reconciliation deliberately used a fresh isolated
worktree without the lock — the lock is required for production writer
sessions, which remain unavailable.)

### 5. Dry-run fleet 5/5

```
$ docker ps -a --filter "name=hermestrader-dryrun"
hermestrader-dryrun-rainbow-1                   Exited (0) 4 days ago
hermestrader-dryrun-freqtrade-freqforge-1       Exited (130) 4 days ago
hermestrader-dryrun-freqtrade-webserver-1       Exited (0) 4 days ago
hermestrader-dryrun-freqtrade-regime-hybrid-1   Exited (130) 4 days ago
hermestrader-dryrun-freqtrade-freqforge-canary-1 Exited (130) 4 days ago
```

❌ **FAIL** — all 5 canonical services are **stopped** (exited ~4 days ago).
`docker ps` (running only) shows zero containers.

### 6. dry_run=true configs

```
freqforge/user_data/config.example.json               → dry_run=True futures
freqforge-canary/user_data/config.example.json        → dry_run=True futures
freqtrade/bots/regime-hybrid/user_data/config.example.json → dry_run=True futures
freqtrade/bots/webserver/user_data/config.example.json    → dry_run=True futures
freqtrade/bots/freqai-rebel/user_data/config.example.json  → dry_run=True futures
```

✅ **PASS** — all approved service configs remain `dry_run=true`, futures.
`freqai-rebel` remains profile-gated and NOT authorized.

### 7. Native gateway active

```
$ systemctl is-active hermes-gateway hermes-dashboard hermes-native.target
active / active / active
$ hermes -p trading-hub-orchestrator gateway status
✓ Gateway is running (PID: 1609337)
```

✅ **PASS** — native systemd gateway + dashboard active.

### 8. Exactly one roadmap cron

```
$ hermes -p trading-hub-orchestrator cron list
No scheduled jobs.
```

❌ **FAIL** — **zero** cron jobs. The single canonical
`trading-hub-roadmap-tick` job (`*/30 * * * *`, workdir
`/workspace/projects/trading-hub`, deliver=local) is missing.

### 9. Kill switch / live trading

```
freqtrade/shared/kill_switch.json → {"mode": "NORMAL", ...}
```

✅ **PASS** — kill switch NORMAL, live trading NOT enabled, no orders, no
credentials deployed.

## Gate status

```
EXECUTOR_SERVICE=ACTIVE
EXECUTOR_ACTION_SURFACE=FAIL (unknown_action on fs_*, systemctl, provenance)
SO_PEERCRED=PASS
WRITER_LOCK=FAIL (directory missing)
DRYRUN_FLEET=0_OF_5 (all stopped)
NATIVE_GATEWAY=ACTIVE
ROADMAP_CRON=ZERO_ACTIVE
DRY_RUN_CONFIGS=PASS (5/5 dry_run=true)
LIVE_TRADING=NO
HOLDOUT_INSPECTED=NO
```

## Required unblock (human action only)

The original A2 marker expired 2026-08-01T18:00:00Z. Hermes cannot
self-approve a runtime mutation. The following is required to proceed:

```text
APPROVED_A2_HERMESTRADER_RUNTIME_RECOVERY_V2
issued_by=Luke
host=HermesTrader
execution_class=A2
purpose=Restore dry-run fleet, writer lock, roadmap cron; deploy repository executor action surface
approval_scope=ISSUE_683_ONLY
live_trading=PROHIBITED
dry_run_false=PROHIBITED
```

Until that marker exists, this issue remains **open** and
`BLOCKED_BY_MISSING_A2_MARKER`. No closure comment is valid.

## Recommendation

1. Luke issues a fresh time-limited A2 marker for the #683 Phase 1–5 recovery
   (or delegates it to the root operator / Claude Code path as defined in the
   #683 execution-role clarification).
2. After the recovery baseline is green, re-run this read-only reconciliation
   GOAL from the Hermes agent and close #683 with evidence.
3. Do NOT start #604 ratification proposal or snapshot-v2 planning as a
   substitute — the runtime baseline is a prerequisite for any A2 runtime step.

## Report scope

- This report is A0/A1 only. No runtime, Docker, cron, host, or repository
  mutation was performed during this reconciliation.
- Evidence collected via: `systemctl`, `docker ps`, `hermes cron`,
  `hermes_root` client over the SO_PEERCRED socket, config JSON reads,
  `ls` on state paths.
