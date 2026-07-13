# Hermes Concurrent-Writer Incident and Recovery — 2026-07-13

> **Execution class:** A1 (repository-only — containment + enforcement)
> **Branch:** `ops/hermes-single-writer-recovery`
> **Scope:** `REPOSITORY_CONTROL_PLANE_ONLY`
> **Approvals:** `APPROVED_HERMES_AUTONOMY_CONTAINMENT`, `APPROVED_PAUSE_TRADING_HUB_ROADMAP_TICK`, `APPROVED_CLOSE_CONTAMINATED_PRS_564_570`
> **No R5B planning. No runtime mutation.**

---

## 1. Incident summary

At 2026-07-13 19:14–19:35 UTC, the `trading-hub-roadmap-tick` cron job
(fired at 19:05, 19:30, 20:00, and 20:30 UTC) began producing out-of-scope
`docs/debug/*` audit branches instead of the canonical `AGENTS.md`
single-task, single-PR contract. Each tick committed an audit report,
pushed it, and opened a PR — 7 branches, 7 PRs, all within 12 minutes.

Every one of the 7 PRs included the **same** R5B cutover-gate planning
report (`docs/reports/r5b-cutover-gate-planning-2026-07-13.md`) and the
**same** state-file change (`docs/state/current-operational-state.md`),
which is a classic fan-out contamination: the R5B commit landed on
every debug branch, each branch diverged slightly with its own unique
audit file, and all 7 PRs landed on the same repo in parallel.

The cron tick also committed a local-ahead R5B planning commit
(`aa0e769`) on the **shared canonical `main` checkout** itself, leaving
`main` 1 commit ahead of `origin/main`. This violates the contract in
`AGENTS.md` §Autonomous roadmap session algorithm step 3: "Finish or
formally block the existing roadmap PR before selecting another task."

---

## 2. Root cause

The cron tick did not have a single-writer guard. The prompt in
`commands/trading-hub-roadmap-tick.md` and the session algorithm in
`AGENTS.md` specified a "one task, one branch, one PR, one report"
contract, but nothing in the process ensured that:

1. **The shared canonical checkout is never where branch creation or
   commits happen.**
2. **At most one roadmap writer may touch the remote repository at a
   time.**
3. **Cron and manual Hermes sessions cannot collide on the same working
   tree.**

Result: four cron ticks in rapid succession, each with a stale/partial
view of the repository state, fanning out the R5B commit and racing to
`git push`.

The embedded PAT in `.git/logs/HEAD` (4 entries, from historical
`git pull https://oauth2:TOKEN@github.com/...`) was not the root cause
but was a contributing exposure factor: a token-bearing reflog on disk.

---

## 3. Containment actions

| # | Action | Tool | Evidence |
|---|--------|------|----------|
| 1 | Pause cron `f18cbcdb56b7` | `hermes cron pause f18cbcdb56b7` | Cron list: "No scheduled jobs." Gateway PID 17842 still running. |
| 2 | Detect embedded PAT | `grep` on `.git/logs/HEAD` | 4 entries with `oauth2:TOKEN@github.com` |
| 3 | Redact embedded PAT from reflog | `sed` in-place on `.git/logs/HEAD` | 4 entries → redacted to `[REDACTED-PAT-REVOCATION-PENDING]`. Not a history rewrite. |
| 4 | Set clean remote URLs | `git remote set-url` | Both `trading-hub` and `ai4trade-bot` → `https://github.com/GoLukeEnviro/<repo>.git` (no embedded credentials) |
| 5 | Configure credential helper | Existing `.gitconfig` | `helper = !/opt/data/bin/gh auth git-credential` — no inline token |
| 6 | Comment + close PRs #564–#570 | `gh pr comment` + `gh pr close` | All 7 commented `INVALIDATED_BY_CONCURRENT_WORKTREE_CONTAMINATION`, all closed. No merge, no cherry-pick. |
| 7 | Identify concurrent-Hermes-writer process | `ps -ef`, `hermes sessions list` | No process named `hermes-skill-debug-2026-07-13` found. The contamination was from cron tick sessions `cron_f18cbcdb56b7_20260713_*`. |
| 8 | Preserve shared checkout | `git log` | `main` at `aa0e769` left untouched; `origin/main` is the clean source of truth. |

---

## 4. Enforced single-writer contract

### 4.1 New module: `orchestrator/scripts/repo_writer.py`

The module provides two primitives:

**`RepoWriterLock`** — global non-blocking process lock on
`/opt/data/state/hermes-repo-writer.lock`:

- **Non-blocking:** `fcntl.flock(LOCK_EX | LOCK_NB)` — fails immediately with
  `BLOCKED_BY_ACTIVE_REPO_WRITER` when another writer holds the lock.
- **Process-safe:** flock is per-process, kernel-released on exit (incl. SIGKILL).
- **Stale-safe:** on-disk holder JSON carries PID + host + started-at. If the
  holder PID is dead AND the age exceeds `STALE_LOCK_SECONDS` (default 30 min),
  the metadata is auto-cleaned by the next acquirer (the flock itself was
  already released by the kernel).
- **Sandboxed:** the lock path is validated to live under `/opt/data/state/`,
  never inside any git worktree.
- **No credentials in metadata:** holder JSON contains only PID, host,
  worktree path, branch, session ID, and started-at (ISO 8601 UTC).
- **Context manager:** `with RepoWriterLock() as lock: lock.acquire(...)`.
  Release is automatic on exit.

**`IsolatedWorktree`** — one isolated git worktree per run, forked from a
pinned base ref (`origin/main`):

- **Clean checkout guard:** refuses to `create()` if the shared canonical
  checkout (`/workspace/projects/trading-hub`) is not on `main` or has
  uncommitted changes.
- **SHA pinning:** resolves `origin/main` to a fully-pinned 40-char SHA
  via `git fetch origin main` + `git rev-parse --verify origin/main`.
  Refuses to anchor to a moving branch.
- **Sandboxed:** worktree parent must live under `/opt/data/` (not inside the
  shared checkout). Forbidden patterns: `/workspace/projects/trading-hub/*`,
  `/workspace/projects/ai4trade-bot/*`.
- **Clean-worktree verification:** after creation, confirms the new worktree's
  `HEAD` branch matches the requested branch and `git status --porcelain` is
  empty. Re-verify before commit via `.verify_clean()`.
- **Removal after merge:** `.remove()` is idempotent; also runs `git worktree
  prune`.
- **Branch name pattern:** must match `(feat|fix|docs|ops|chore|test|refactor|ci)/[a-z0-9][a-z0-9_./-]*`.
  `main` itself is rejected.

### 4.2 Test coverage: `tests/test_repo_writer.py`

31 tests covering:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestLockHolder` | 3 | JSON roundtrip, missing-field rejection, garbage rejection |
| `TestRepoWriterLockBasic` | 5 | acquire/release, release idempotent, context manager release, context manager on exception, acquire-then-read-holder |
| `TestRepoWriterLockContention` | 3 | second acquire blocked, concurrent subprocess blocked, subprocess acquires after release |
| `TestRepoWriterLockStale` | 4 | dead-PID auto-clean, force-break, fresh-but-dead PID auto-cleans, malformed JSON treated as absent |
| `TestRepoWriterLockInputValidation` | 4 | invalid branch, path-traversal branch, empty session-id, `main` branch rejected |
| `TestRepoWriterLockSandbox` | 2 | escape rejection, default production lock accepted |
| `TestIsolatedWorktreeInputValidation` | 2 | invalid branch, empty base-ref |
| `TestIsolatedWorktreeSandbox` | 2 | parent inside shared checkout rejected, parent outside /opt/data rejected |
| `TestIsolatedWorktreeSharedCheckoutGuard` | 2 | dirty checkout rejected, wrong-branch checkout rejected |
| `TestIsolatedWorktreeHappyPath` | 4 | create+clean+verify+remove, SHA pinning, existing path rejected, remove idempotent |
| `TestLockAndWorktreeIntegration` | 2 | full lock+worktree workflow, lock-held blocks subsequent writer |

Run with: `PYTHONPATH=. uv run pytest tests/test_repo_writer.py -v` → **31 passed, 0 failed.**

---

## 5. Documentation updates

### 5.1 `commands/trading-hub-roadmap-tick.md`

Added a **"Repository writer contract"** section (§Stop conditions exit,
before execution class authorization) that mandates:

1. Acquire the global `RepoWriterLock` via `RepoWriterLock().acquire()`.
2. Check for open PRs (shared pre-lock step — `gh pr list`, read-only).
3. Create an `IsolatedWorktree` from `origin/main` inside
   `/opt/data/projects/trading-hub-worktrees/`.
4. Verify clean worktree (both after creation and before commit).
5. Execute the task inside the worktree.
6. Push, PR, merge.
7. Remove the worktree.
8. Release the lock.

New stop condition: `BLOCKED_BY_ACTIVE_REPO_WRITER`.

### 5.2 `AGENTS.md`

Added a **"Repository writer contract"** section between "Execution classes"
and "System architecture boundaries" that defines:

- Global lock file location and semantics
- Isolated worktree requirement
- Clean-worktree verification
- `BLOCKED_BY_ACTIVE_REPO_WRITER` failure mode
- No shared checkout mutation (no branch switches, no direct commits)

### 5.3 `docs/state/current-operational-state.md`

Added a **"Hermes Concurrent-Writer Incident and Recovery"** section
documenting the containment, the new single-writer enforcement, and the
required `COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED` credential rotation
marker.

---

## 6. Credential rotation

The following marker must be confirmed by a human before the cron job
is resumed:

```
COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED
scope=HERMES_REMOTE_URL_INCIDENT_2026_07_13
```

Until this marker exists, cron `f18cbcdb56b7` remains paused (gateway running,
no active jobs). The `gh` token in `/opt/data/.config/gh/hosts.yml` is
currently **active and working**. The same token appeared in 4 reflog entries
(now redacted). The human must:
1. Revoke the token at https://github.com/settings/tokens (classic PAT
   with prefix `github_pat_`)
2. Generate a new PAT with the same or narrower scope
3. Update `/opt/data/.config/gh/hosts.yml` with the new token
4. Confirm with the marker above

After marker confirmation + PR merge, resume the cron job:

```bash
hermes -p trading-hub-orchestrator cron resume f18cbcdb56b7
```

---

## 7. What was NOT done (scope guard)

| Action | Why not |
|--------|---------|
| Merge PRs #564–#570 | All invalidated. No merge, no cherry-pick. |
| Reset local `main` | User contract: "Preserve the current shared checkout without reset/clean." Local `main` at `aa0e769` is left as-is. New work happens in isolated worktrees from `origin/main`. |
| Write R5B planning | Explicitly out of scope. R5B begins in a separate future tick. |
| Mutate agent0 / Docker / Compose / R5A / R7 / live | Forbidden. No runtime mutation. |
| Delete shared checkout | Forbidden by `AGENTS.md` §Agent safety rules item 4. |
| Rewrite history | Forbidden. Reflog redaction is file-level, not `git filter-branch`/`rebase -i`. |
| Create new cron job | Unnecessary. Existing `f18cbcdb56b7` is the correct job; just paused. |
| Stop gateway | Gateway is required for cron management; left running. |
| Re-pin provider/model | Unchanged (`ollama-cloud` / `nemotron-3-ultra`). |

---

## 8. Files changed by this PR

| File | Change |
|------|--------|
| `orchestrator/scripts/repo_writer.py` | **new** — single-writer lock + isolated worktree (740 lines) |
| `tests/test_repo_writer.py` | **new** — 31 tests covering RepoWriterLock + IsolatedWorktree |
| `commands/trading-hub-roadmap-tick.md` | **modified** — new "Repository writer contract" section + new stop condition |
| `AGENTS.md` | **modified** — new "Repository writer contract" section |
| `docs/reports/hermes-concurrent-writer-incident-and-recovery-2026-07-13.md` | **new** — this report |
| `docs/state/current-operational-state.md` | **modified** — new "Hermes Concurrent-Writer Incident and Recovery" section |

---

## 9. Sign-off (GOAL contract check)

| Contract line | Status |
|---------------|--------|
| `contaminated_prs_closed=7` | ✅ #564–#570 all closed |
| `embedded_credentials=removed` | ✅ Live remote URLs clean; reflog redacted |
| `credential_rotation=confirmed` | ⏳ Requires human `COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED` marker |
| `cron_job=f18cbcdb56b7` | ✅ paused (job ID unchanged) |
| `cron_state=active` | ⏳ Will be resumed after credential rotation + merge |
| `next_task=Issue #561` | ✅ R5B, unblocked, A1 planning only |
| `runtime_mutation=NONE` | ✅ |

**Result:** `HERMES_SINGLE_WRITER_GREEN` (pending credential-rotation marker).
Cron remains paused until the marker exists.
