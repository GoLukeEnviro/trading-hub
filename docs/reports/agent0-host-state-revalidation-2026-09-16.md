# Agent0 Host-State Revalidation — 2026-09-16

**Execution class:** A0 (read-only host validation) + bounded L3 namespace bootstrap authorised under #730
**Host:** `Agent0` (Hetzner KVM, Ubuntu 26.04.1 LTS, kernel 7.0.0-31-generic), tailnet `agent0-1`
**Commit at validation:** `ddd96fa38693bea41ffd959c32134a1122291134` (`main`, clean)
**Hermes:** v0.21.3 (2026.9.14), upstream `40f2702b`, git install, Python 3.11.16
**Related:** #730, `agent0-takeover-plan-2026-09-16.md`

> This report supersedes the out-of-tree note `trading-hub-agent0-host-state-20260915.md`.
> It exists because Agent0 previously had **no** repo writer namespace, so no in-repo
> record could be produced. That blocker is now resolved (see §4).

## 1. Why this validation exists

Luke rebuilt the VPS and updated the Hermes backend and desktop app. Old version
numbers, host paths, user IDs and runtime blockers are **historical hints only** and
were re-derived against this host rather than inherited. No legacy Hermes upgrade or
cutover script was executed.

## 2. Execution location (verified, not assumed)

| Question | Verified result | Evidence |
|---|---|---|
| Host | `Agent0` — **not** HermesTrader | `hostname`, `hostnamectl` |
| User / UID | `hermes` 10000:10000 | `id` |
| Repo path | `/home/hermes/trading-hub` | `git remote -v` |
| Commit | `ddd96fa` == `origin/main` | `git rev-parse HEAD origin/main` |
| Worktree | clean (0 entries) | `git status --porcelain` |
| Hermes version | **0.21.3** (2026.9.14) | `hermes --version` |
| Hermes services | `hermes-gateway` + `hermes-serve` active | `systemctl is-active` |
| Cron ticker | gateway running, heartbeat 57 s, **0 jobs** | `hermes cron status` |
| Hermes profiles | only `default` (no `trading-hub-orchestrator`) | `hermes profile list` |
| Docker daemon | 29.8.0 active | `docker info` |
| Docker objects | **0 containers, 0 images, 0 volumes** | `docker ps -aq \| wc -l` |
| `hermes-root-executor.service` | **absent** (no unit, no `/etc/hermes-root-executor`, no socket) | `systemctl status` |
| `/opt/data`, `/workspace` | **absent** before this task (§4) | `stat` |

A second tailnet host `hermestrader` (100.96.132.39) is **online** and reachable
(7 ms) but is a separate machine; see §5.

## 3. Dry-run trading check — FAIL (concrete defect)

| Check | Result | Evidence |
|---|---|---|
| Expected canonical fleet | 5 services: freqforge, canary, regime-hybrid, webserver, rainbow | `docker-compose.hermestrader-dryrun.yml` |
| Compose definition valid | PASS | `docker compose config` exit 0; 5 services; 8 named volumes; `user: 10000:10000` ×5 |
| Running bots | **0/5** — no container, no volume | `docker ps -a` |
| "5/5 healthy" | **not reproducible** (that claim is historical HermesTrader state) | `docker ps -a` empty |
| Pinned R5A images | **absent and not obtainable locally** | `docker images` empty |
| Image provenance lock | PASS — lock intact, hashes match `main` | `Dockerfile.hermes10000` `7ca1e4f9b150…`, `entrypoint.sh` `7e1890ed32c9…`, `ops/ai4trade-rainbow.lock.yml` match |
| Rainbow build context | PASS — checkout at pin `6e850c8f8ba1…`, `rainbow.Dockerfile` `faa2e3d8c351…` == lock | `git -C ~/ai4trade-bot rev-parse HEAD` + sha256 |
| `r5a_recovery verify-only` | `BLOCKED_COMMAND_FAILED:image` | executed read-only |
| `r5a_recovery start-existing` / `deploy-locked` | `BLOCKED_INVALID_DOCKER_INSPECT_JSON` | injected run, 1 docker call |
| Greenfield image rebuild | `BaselineBuildError: IMAGE_LOCK_MISSING_OR_INVALID` + gate | lock `locked`; rebuild requires `baseline_pending` |
| Strategy + configs | PASS — present, **all 5 `dry_run=true`** (Bitget futures) | JSON parse |
| Current market data / strategy evaluation | **none** — no process, therefore no data flow | no container |
| Exchange egress | PASS — `api.bitget.com` 200 | `curl` |
| Freqtrade runtime viable | PASS — base image pullable, `freqtrade 2026.6` (Py 3.14.6, CCXT 4.5.61) | `docker run --network none` probe |
| Writable dry-run DBs | none exist → nothing to overwrite; volume names free | `docker volume ls` |
| Privileged execution path | **absent** — no executor service | `systemctl status` |
| Kill switch effective | **`HALT_NEW`** (fail-closed) | `get_kill_mode()`; cause: `var/kill_switch.json` absent and `/freqtrade/shared` does not exist ⇒ `_FAIL_CLOSED_STATE` |
| Kill switch tracked file | `freqtrade/shared/kill_switch.json` = `NORMAL` (not the effective path here) | read-only |
| RiskGuard in trading path | **not wired** — no trading path exists | no container |

**Single-sentence defect:** Agent0 has **no dry-run fleet at all**; the canonical R5A
images are locally built tags on HermesTrader, are distributed nowhere, and the
recovery contract fails closed against a fresh host (`--pull never` plus exact image
ID) while the rebuild path only starts from `status: baseline_pending`.

### 3.1 SI-v2 read-only cycle: process PASS, content RED

Two full read-only cycles were executed on this host
(`self_improvement_v2/src/si_v2/loop/active_cycle_runner.py`, venv
`/home/hermes/trading-hub/.venv`, commit `ddd96fa`, branch `main`):

| Criterion | Result |
|---|---|
| Cycle completes | PASS (exit 2 = RED verdict, not a crash) |
| Unique cycle ids | `20260915T155511Z`, `20260915T160745Z` |
| Readable evidence artifact | `reports/phase2/evidence/active_cycle_<id>.json` (36,497 B) |
| Cycle state + ledger | `status: SUCCESS`, 2 cycles, 8 bot points, `mutations_all_zero: True` |
| Mutation counters | **all 0** (runtime/config/live_trading/docker/strategy) |
| Rainbow (opt-in via `SI_V2_RAINBOW_ENABLED=true`) | `SUCCESS`, 7 signals, `source=fixture`; default `DISABLED` (fail-closed) |
| **Bot telemetry** | **0/4** — all `ping_failed` |
| Fleet verdict | **RED** — "all 4 bots failed /api/v1/ping; no telemetry collected" |

The three stages are distinct and must not be conflated: **process started** (yes) /
**bot processes current market data** (no) / **SI-v2 reads bot data** (works
technically, but contains no bot data). Fixture signals are **not** operational proof.

## 4. Repo writer namespace bootstrap (the one L3 mutation performed)

### 4.1 Root cause of `WRITER_IDENTITY_MISMATCH` — every guard condition evaluated separately

The guard order in `_validate_production_writer_environment` is: euid/user → repo_root
→ lock_path → worktree_parent equality → lock parent → worktree parent → lock file.
The reported error was the **first** failing condition of the path phase
(`lock parent … is missing`), so every condition **after** it was never evaluated and
is invisible in the error text. "Create the missing directory" was therefore not a
sufficient fix claim. Measured state, before and after:

| # | Guard condition | Required | Before | After |
|---|---|---|---|---|
| 1 | euid / passwd user | 10000 / `hermes` | PASS | PASS |
| 2 | canonical repo path | `/workspace/projects/trading-hub` | PASS (both sides absent ⇒ equal) | PASS |
| 3 | lock path | `/opt/data/state/repo-writer/hermes-repo-writer.lock` | PASS (equality only) | PASS |
| 4 | worktree parent path | `/opt/data/projects/trading-hub-worktrees` | PASS (equality only) | PASS |
| 5 | lock parent | is_dir, `0:0`, **not** writer-writable | `(-1,-1,False,False)` FAIL | `(0,0,True,False)` PASS |
| 6 | worktree parent | is_dir, `10000:10000`, writer-writable | `(-1,-1,False,False)` FAIL | `(10000,10000,True,True)` PASS |
| 7 | lock file | regular, `10000:10000`, `0600`, writer rw | `(-1,-1,False,0,False)` FAIL | `(10000,10000,True,384,True)` PASS |

Conditions 6 and 7 were latent co-causes hidden behind the reported error.

Two further conditions the error text never surfaces: `_validate_sandbox` requires the
lock to physically resolve inside `/opt/data/state` (symlink-safe realpath), and
forbids the worktree parent inside the shared checkout
(`/workspace/projects/trading-hub(/|$)`, `/workspace/projects/ai4trade-bot(/|$)`), and
requires it inside `/opt/data`.

Note on condition 2: `_resolved_path()` resolves symlinks and compares the caller's
path against the **same** default, so a symlink at `/workspace/projects/trading-hub`
resolves identically on both sides and passes. A missing `/workspace` also passes
(`strict=False`). This condition is a no-op for the default constructors and only
bites when a caller passes a divergent path (covered by
`tests/test_repo_writer.py::test_host_repo_path_is_rejected`).

### 4.2 What was created (only what was genuinely missing; nothing overwritten)

Pre-state capture: `agent0-writer-namespace-pre-state-20260916.txt`. No lock file
existed anywhere on the host (`find / -xdev -name 'hermes-repo-writer.lock*'` empty).
No path was replaced, no existing lock was touched, no symlink was rewritten.

| Path | Owner:group | Mode | Note |
|---|---|---|---|
| `/opt/data` | `root:root` | 0755 | contract parent |
| `/opt/data/state` | `root:root` | 0755 | |
| `/opt/data/state/repo-writer` | `root:root` | 0755 | not writer-writable, as required |
| `/opt/data/state/repo-writer/hermes-repo-writer.lock` | `hermes:hermes` | 0600 | regular file, 0 bytes |
| `/opt/data/projects` | `root:root` | 0755 | |
| `/opt/data/projects/trading-hub-worktrees` | `hermes:hermes` | 0755 | writer-writable |
| `/workspace/projects/trading-hub` | `root:root` | symlink | → `/home/hermes/trading-hub` |

`/workspace/projects/trading-hub` is a symlink to the **existing** checkout. No second
diverging checkout was created and **no guard was modified**.

### 4.3 Validation (all passed)

```text
identity / lock-parent / worktree-parent / lock-file guard conditions : ALL PASS
acquire + assert_held                                                : OK
holder   pid=281492 host=Agent0 device=2049 inode=1433366
is_locked() (self)                                                   : True
release() + assert_held() after release                              : LOCK_NOT_HELD (correct)
second concurrent writer (separate process)                          : BLOCKED_BY_ACTIVE_REPO_WRITER
   reported holder: pid=281717 branch='docs/holder-probe-20260916' host='Agent0'
is_locked() after holder exit                                        : False
isolated worktree from pinned origin/main                            : created OK
worktree path   /opt/data/projects/trading-hub-worktrees/docs__agent0-takeover-plan-20260916
worktree HEAD   ddd96fa == origin/main                               : YES
verify_clean() + assert_held() before mutation                       : OK
shared checkout                                                      : 0 dirty entries, main, ddd96fa
```

### 4.4 Rollback (safe return path)

Remove exactly these paths; nothing else depends on them yet:

```bash
sudo rm /workspace/projects/trading-hub          # symlink only
sudo rmdir /workspace/projects /workspace
sudo rm /opt/data/state/repo-writer/hermes-repo-writer.lock
sudo rmdir /opt/data/state/repo-writer /opt/data/state
sudo rmdir /opt/data/projects/trading-hub-worktrees /opt/data/projects
sudo rmdir /opt/data
```

The repository is untouched by this bootstrap (no commit, no branch, no config change
in the shared checkout), so no repo-level rollback is required.

## 5. HermesTrader (unchanged — no access, nothing attempted)

Every permitted access path from Agent0 was tested and **none works**: SSH as
`hermes`/`deploy`/`root`/`operator`/`ubuntu` → `Permission denied (publickey,password)`;
SSH with Agent0's root key → denied; `tailscale ssh` → denied (Agent0 has
`RunSSH=false`, HermesTrader offers no Tailscale SSH); no agent keys, no vault entries,
no provider CLI or credentials. HermesTrader is reachable **passively read-only** only
(Caddy/Cockpit on 22/80/443/8443/9091).

Container, image, data and dataset inventory is host-local by nature, so no inventory
was possible. No access probe was repeated and nothing on HermesTrader was touched.
The existing Windows access path (`hermestrader-root`) to the intended source
100.96.132.39 is the operator-side route to verify and use for the inventory.

## 6. Security finding — deviation from the documented R0 privilege model

`docs/state/current-operational-state.md` records "sudo for Hermes = **Nicht
vorhanden**" and "docker.sock for Hermes = **Nicht vorhanden**". On this rebuilt host
`hermes` instead has `NOPASSWD:ALL` (`/etc/sudoers.d/hermes`) **and** `docker` group
membership (983). `sudo` was used here exclusively for read-only inspection and the
authorised namespace bootstrap; the broad rights are **not** treated as authorisation
to bypass the prescribed executor.

Recommendation: keep the executor as the only privileged path, and **narrow the
sudo/docker rights only after** a verified executor and verified operator access
exist, so no administrative lockout is created.

## 7. Scope statement

No strategy, config, `dry_run` value, container, service, cron job, credential,
kill-switch state, package or firewall rule was changed. Docker object counts remain
0/0/0. No Hermes upgrade was performed and no cutover was attempted. No live trading.
