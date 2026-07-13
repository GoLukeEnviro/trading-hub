# H3B Runtime-Control Proof — 2026-07-13 (systemd Permission Fix + Full Proof Matrix)

**Date:** 2026-07-13 06:30–07:00 UTC
| **Gate:** | `H3B_RUNTIME_CONTROL_DEGRADED` (first push, **superseded**) → `H3B_RUNTIME_CONTROL_GREEN` (final, see Addendum 2) |
**Classification:** A2 — approved (`APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION` + `APPROVED_H3B_SYSTEMD_PERMISSION_FIX_AND_RUNTIME_PROOF`)

## Goal

Fix the `BLOCKED_BY_EXECUTOR_RUNTIME_DIRECTORY_PERMISSIONS` blocker from PR #558 via a systemd unit change, then run the full Issue #531 runtime-control proof matrix.

## Precondition: GID check

```
$ getent group hermes
hermes:x:10000:deploy
$ docker exec -u 10000 hermes id
uid=10000(hermes) gid=10000(hermes) groups=10000(hermes)
```

Host group `hermes` has exactly GID `10000`, matching the Hermes container. Proceeded.

## Backup before mutation

* Fresh Restic snapshot `377258fd` (tag `h3b-systemd-permission-fix-<ts>`).
* Root-only backup of the unit file at `/root/backups/h3b-systemd-permission-fix-20260713/` (`hermes-root-executor.service` + SHA-256; no pre-existing drop-ins to back up).

## systemd fix applied

New drop-in `/etc/systemd/system/hermes-root-executor.service.d/10-hermes-group-permissions.conf`:

```ini
[Service]
Group=hermes
RuntimeDirectoryMode=0750
RuntimeDirectoryPreserve=restart
```

`User=root` left unchanged. `systemctl daemon-reload` + a single `systemctl restart hermes-root-executor.service`.

**Result:**

| Check | Before | After |
|---|---|---|
| `MainPID` | `468055` | `531456` (new, stable) |
| `NRestarts` | `0` | `0` |
| `/run/hermes-root-executor` owner:mode | `root:root 0750` | `root:hermes 0750` |
| `/run/hermes-root-executor/executor.sock` owner:mode | `root:root 0660` | `root:hermes 0660` |
| Host/container inode | mismatched (stale) | **matched immediately** — `RuntimeDirectoryPreserve=restart` kept the same tmpfs directory across the restart, so no container recreate was needed this time |
| Journal | — | clean, no crash, no restart loop |

## Bugs found and fixed in this branch (with tests)

Once the socket became reachable, three further defects surfaced — each one blocked part of the proof matrix and was fixed with regression tests, per the run's authorization to fix H3B-related client/daemon bugs in-branch:

### 1. `ExecutorResponse` schema mismatch (client bug)

`hermes_root/schema.py`'s `ExecutorResponse` only parsed `request_id`/`correlation_id`/`decision`/`reason`/`result`/`audit_seq` — but neither the v1 nor the legacy daemon response ever contains `result` or `audit_seq` (confirmed via a raw socket capture: the real v1 response has `schema_version`, `returncode`, `stdout`, `stderr`, `started_at`, `finished_at`, `duration_ms`, `resource_key`, `action`, `execution_class`, `audit_id`). The client was silently dropping `action`, `execution_class`, `audit_id`, and all output fields.

**Fix:** `ExecutorResponse` now mirrors the real wire format for both protocols (v1-only fields default to empty/zero for legacy responses). Updated `client.py` (removed dead redaction of the never-populated `result` field, with a comment explaining stdout/stderr are not redacted and callers must do their own secret scanning for display) and `__main__.py`'s human/JSON output. Added `test_v1_response_fields_parsed` and `test_legacy_shaped_response_parses_with_defaults`.

### 2. CLI argv duplication (client bug, affected nearly every action)

`hermes_root/__main__.py`'s `_build_argv()` built the **full** command (e.g. `["docker", "ps"]`) and sent it as the request's `argv`. But the daemon's `hermes_root/actions.py::build_argv()` treats `argv` as *extras* and prepends its own fixed base command (`["docker", "ps", *argv]`) — so the daemon ended up running `docker ps docker ps` (`docker: 'docker ps' accepts no arguments`). Actions requiring exactly one extra argument (`docker_inspect`, `systemctl_status`, `docker_stop`, `docker_remove`, `systemctl_restart`) would have been rejected outright (`invalid_argv_for_action`) the same way, and `docker_create` would have produced a nonsensical duplicated command.

**Fix:** rewrote `_build_argv()` to return only the resource-specific extras for every action, matching `hermes_root/actions.py` exactly. Added a parametrized contract test (`test_cli_extras_match_daemon_builder`) that runs the CLI's extras through the real daemon-side builder for all 8 actions and asserts the exact final command.

### 3. `docker_compose_config` flag ordering (daemon bug)

`actions.py` built `["docker", "compose", "config", *argv]` — but `docker compose`'s `-f`/`--file` flag must precede the `config` subcommand; placing it after produces `unknown shorthand flag: 'f' in -f`. Fixed to `["docker", "compose", "-f", argv[0], "config"]` with `_require_argv_len(argv, 1)`, matching the pattern already used for `docker_inspect`/`systemctl_status`. Client-side extras updated to `[compose_file]` (single element). Test case updated.

**This fix is source-correct and unit-tested, but could not be verified end-to-end** — see below.

## New environmental blocker found (not a code bug, not fixed)

`docker exec -u 10000 hermes docker compose version` → `docker: 'compose' is not a docker command.` `docker info --format '{{json .ClientInfo}}'` confirms `"Plugins":[]` — the Hermes container image (`nousresearch/hermes-agent:latest`) ships the Docker CLI with **zero** CLI plugins, no `docker compose`, no standalone `docker-compose`. This is an image-packaging gap, not something fixable by a code change in this repo, and installing a plugin into the running container or rebuilding its image is out of this run's scope (no image/Dockerfile changes authorized).

## Proof matrix results

### Positive v1 proof — PASSED

```
$ python3 -m hermes_root executor_health --class A0 --json   # as uid 10000
{
  "decision": "ALLOWED", "reason": "ok",
  "action": "executor_health", "execution_class": "A0",
  "audit_id": "f700afc1-9119-4612-a7a8-f2274035fce4",
  "correlation_id": "<exact match>"
}
```

### Read-only action-proof matrix — 4/5 PASSED

| Action | Result |
|---|---|
| `executor_health` | ✅ ALLOWED |
| `docker_ps` | ✅ ALLOWED, `returncode=0`, real container list (after argv fix) |
| `docker_inspect` (Hermes container) | ✅ ALLOWED, `returncode=0` |
| `systemctl_status` (the executor unit itself) | ✅ ALLOWED, `returncode=0`, output shows the new drop-in |
| `docker_compose_config` | ❌ **BLOCKED** — `docker compose` plugin absent in the Hermes image (see above); code is correct, environment is not |

### Security proof matrix — 7/7 PASSED

| Test | Result |
|---|---|
| Wrong UID (as root, via canonical client) | `BLOCKED` / `peer_uid_not_allowed` |
| Missing A2 approval (client-side) | Validation error, exit 2, no request sent |
| Missing A2 approval (server-side, raw request bypassing client validation) | `BLOCKED` / `approval_reference_missing_or_invalid` |
| A3 (even with a valid approval reference) | `BLOCKED` / `a3_never_authorized` |
| Kill switch | prior state absent → enabled → `BLOCKED`/`emergency_disable_switch_active` → restored to absent → normal A0 access confirmed working again |
| Locking | two barrier-synced concurrent requests, same `resource_key`: first `ALLOWED`, second `BLOCKED`/`resource_locked` |
| Timeout | isolated mocked unit test `test_timeout_blocks` (no live allowlisted action runs long enough to exceed `MIN_TIMEOUT=1s` naturally; this directly exercises the real `subprocess.TimeoutExpired` handling code path with zero risk of orphaned live resources) |
| Isolated mutation lifecycle | `docker_create` → `docker_inspect` → `docker_stop` → `docker_remove` on a uniquely-named disposable container, all `ALLOWED`/`returncode=0`; `docker ps -a --filter name=...` empty afterward — proven absent |

### Audit correlation — PASSED

16/16 of this session's correlation IDs found in `/opt/data/hermes/audit/runtime-actions.jsonl` with matching `action`/`execution_class`/`decision`/`reason`/`peer_uid`. All required fields present (`audit_id`, `correlation_id`, `peer_uid`, `action`, `execution_class`, `decision`, `reason`, `resource_key`, `duration_ms`, `daemon_version=2.0.0-repo`, `approval_reference_redacted`). Secret scan (key-pattern + token-shape heuristic) over all 16 entries: **0 hits**.

Observation (not fixed, not a bug): the wrong-UID rejection does **not** appear in the audit log — `peer_uid` is checked before any audit write. This means unauthorized connection attempts currently leave no audit trace. Worth a deliberate decision in a future task, not changed here.

Observation (not fixed): `repository_commit` is logged as the literal string `"unknown"` in every audit entry — the daemon's constructor default was never overridden with a real commit hash at install time. Traceability gap, not a security issue.

### Stability proof — PASSED

`hermes-root-executor.service` unchanged since the fix restart (`MainPID=531456`, `NRestarts=0`), both host and container socket visible, Hermes container healthy, kill switch absent, zero disposable containers remain, networks/volumes unchanged, working tree contains only the intended 5 fix files.

## Validation

* `git diff --check`: clean
* `pytest tests/test_hermes_root_client.py tests/test_hermes_root_daemon.py -q`: **84 passed** (75 pre-existing/fixed + 9 new: response-schema regression tests, CLI/daemon argv contract tests)
* Main Gate: pending on this push

## Gate status

```
H3B_RUNTIME_CONTROL_DEGRADED
```

**Blocker:**

```
BLOCKED_BY_MISSING_DOCKER_COMPOSE_PLUGIN_IN_HERMES_IMAGE
```

Per the explicit rule for this run, `H3B_RUNTIME_CONTROL_GREEN` requires the complete Issue #531 proof matrix to pass. Every other required proof passed cleanly — positive v1 proof, 4 of 5 read-only actions, the full security-proof matrix (wrong UID, missing/invalid approval both client- and server-side, A3, kill switch, locking, timeout, isolated mutation lifecycle), and audit correlation with a clean secret scan. The sole remaining gap is `docker_compose_config`, blocked by a missing CLI plugin in the Hermes container image — not a code defect (the daemon and client code for this action are now correct and unit-tested).

`H3B_RUNTIME_CONTROL_GREEN` requires, in a separate explicitly-approved run: installing the `docker compose` CLI plugin into the Hermes container image (or an equivalent capability), followed by a live re-verification of `docker_compose_config` specifically.

## References

- Issue #531 — H3B Root-Executor Client Activation
- PR #557 (`a5a8cbe`) — stale bind mount diagnosis
- PR #558 (`091ea22`) — bind mount fixed, runtime-directory permission blocker found
- This run — permission blocker fixed, full proof matrix executed, one new environmental blocker found and precisely isolated
- Backups: Restic snapshot `377258fd`; `/root/backups/h3b-systemd-permission-fix-20260713/`
## Addendum 2 — 2026-07-13: H3B GREEN promotion after human-attested credential rotation

**Status:** `H3B_RUNTIME_CONTROL_GREEN` (PR #559 squash-merged 2026-07-13, Issue #531 closed).

### Reconciliation of the credential-rotation gate

The first two push iterations of this PR kept the gate at `H3B_RUNTIME_CONTROL_DEGRADED` because the proof matrix could not independently verify the external GitHub-side revocation of the credential that was briefly exposed through unredacted executor stdout during `docker_compose_config` re-verification. All other criteria for GREEN were already satisfied (complete Issue #531 matrix, redacted/data-minimized Compose validation, zero leak-spread, all tests green).

On 2026-07-13, the repository owner **human-attested** the external rotation:

```
COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED
confirmed_by=Luke
scope=H3B_PR559_INCIDENT
```

This is the required A2 human-confirmation gate for H3B. The agent did **not** independently verify the GitHub-side revocation event; the attestation itself is the gate. The secret-spread scan (generic patterns only, no content ever printed) was re-run against the final state of the branch, PR #559 body and full comment thread, this report, `current-operational-state.md`, the executor audit log, and `root`/`deploy` shell history — **zero matches** anywhere.

### Final reconciliation against earlier stale claims

| Earlier stale claim (first push of this PR) | Reconciled status |
|---|---|
| `BLOCKED_BY_MISSING_DOCKER_COMPOSE_PLUGIN_IN_HERMES_IMAGE` | Already retracted in the first Addendum; the actual defect was a non-deployed `actions.py` fix, corrected and live-verified. |
| `docker_compose_config` is blocked | **Retracted** — `docker_compose_config` is live-verified as `ALLOWED` with `config --quiet`, `stdout_len=0`, `stderr_len=0`. |
| `H3B_RUNTIME_CONTROL_DEGRADED` (Root Executor safety table) | **Retracted** — Root Executor is 🟢 Reachable and fully proven from Hermes. |
| `Main Gate: pending on this push` | **Superseded** — Main Gate is green on the final head. |
| `external human confirmation remains missing` | **Superseded** — confirmed by the human operator 2026-07-13. |

### Snapshot / correlation references (sanitized)

- Restic snapshot: `377258fd` (tag `h3b-systemd-permission-fix-<ts>`)
- Unit-file backup: `/root/backups/h3b-systemd-permission-fix-20260713/`
- Executor audit log: `/opt/data/hermes/audit/runtime-actions.jsonl` — every H3B session correlation ID is present with `repository_commit=ea26ff7a9899f4af7e462bcd8ef288c203cb4ff9` (or later, fail-closed).
- Main Gate: pass (run `29246191120` at the time of the previous push, then re-run on the GREEN-promotion commit).
- PR #559: `https://github.com/GoLukeEnviro/trading-hub/pull/559`
- Issue #531: `https://github.com/GoLukeEnviro/trading-hub/issues/531`
- Final head SHA (post-merge): captured in the squash-merge comment on PR #559 and the Issue #531 closure comment.

### R5A readiness (separate, not started)

`H3B_RUNTIME_CONTROL_GREEN` is now satisfied. R5A (HermesTrader deployment) remains **blocked** by:

- `APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT`
- `BACKUP_GATE_GREEN`
- explicit human approval for R5A

R5A is **not started** in this run.

## Addendum 1 — 2026-07-13 (Same-Branch Follow-Up): Execution-Boundary Correction, Secret-Exposure Incident, and Full Resolution

**Supersedes:** the `BLOCKED_BY_MISSING_DOCKER_COMPOSE_PLUGIN_IN_HERMES_IMAGE` verdict earlier in this report. The GREEN promotion that followed this addendum is in Addendum 2 above.

### Execution-boundary misdiagnosis, corrected

The earlier verdict tested `docker compose` availability **inside the Hermes container**. That is not where `docker_compose_config` executes. `hermes_root/actions.py` builds a `docker compose ...` argv; `hermes-root-executor.service` runs it via `subprocess.run()` on the **host**, as `User=root`. The host has Docker Compose v5.3.1 fully installed (`/usr/libexec/docker/cli-plugins/docker-compose`), confirmed via `systemctl show ... -p ExecStart -p Environment -p User -p Group` and a direct host-side `docker compose version` call.

The real defect: the earlier `-f`-ordering fix in `hermes_root/actions.py` was committed to the repository but **never deployed** to `/usr/local/sbin/hermes_root/actions.py` (the file the running daemon actually imports) — client and daemon fixes had silently diverged. Confirmed via `diff` and fixed with a verified, backed-up, syntax-checked atomic package deploy.

`BLOCKED_BY_MISSING_DOCKER_COMPOSE_PLUGIN_IN_HERMES_IMAGE` is retracted everywhere it appears in this report, the PR body, and `current-operational-state.md`.

### Secret-exposure incident

While re-verifying `docker_compose_config` after the deploy fix, a live-rendered Compose configuration exposed a repository credential through unredacted executor stdout. The credential was revoked and replaced outside the agent context. No credential value is retained in repository evidence, chat-adjacent artifacts, or this report.

A leak-spread scan (generic secret patterns only — `github_pat_`, `ghp_`, `GH_TOKEN=`, `GITHUB_TOKEN=`, `Authorization: Bearer` — no content ever printed) found **zero** matches across: the git working tree and this branch's full diff/log, PR #559 body and comments, Issue #531 comments, this repository's `docs/reports/h3b-*.md` files, the executor audit log, and both `root`/`deploy` shell histories on the host.

### Root-cause fixes (this branch, same PR)

1. **Data minimization** — `docker_compose_config` now runs `config --quiet` instead of `config`. This action validates a configuration; it has no legitimate reason to render and return a fully resolved document (including plaintext environment values) at all. `--quiet` reports the same validation errors via exit code, prints nothing on success.
2. **Defense-in-depth redaction** — a new `redact_text_output()` in `hermes_root/redact.py` catches known credential shapes (GitHub PAT/token prefixes, Bearer headers) and `key=value` / `"key": value` / `key: value` patterns for TOKEN/SECRET/PASSWORD/API_KEY/PRIVATE_KEY/ACCESS_KEY/AUTH/CREDENTIAL-named fields. Applied unconditionally at both daemon response-construction points (`_finish_v1`, `_handle_legacy`) and again at the client boundary. No debug bypass, no raw-output flag.
3. **Multi-file Compose contract** — `--file` now repeats (1–4), matching the real Hermes stack (`compose.yaml` + `compose.override.yaml`). Each path is independently validated: absolute, no `..`, `realpath`-resolved inside an allowlisted `/opt/stacks` root, must exist as a regular file.

### Regression tests (canary secrets only — no real credentials in any test)

- Daemon boundary: v1 and legacy response payloads redact env-style, YAML-style, JSON-style, and Bearer-style canary secrets; normal output is unaffected; audit log confirmed clean.
- Client/CLI boundary: `ExecutorResponse.stdout`/`.stderr`, CLI `--json` output, and CLI human-readable output all redact the same canary secrets independently (defense in depth).
- Multi-file contract: valid 1–4 file cases, >4 rejected, path traversal rejected, symlink escape rejected, missing file rejected, outside-allowlisted-root rejected — all daemon-side, all backed by the real `hermes_root.actions.build_argv`.

### Live re-verification (post-fix, metadata only — stdout/stderr never printed to chat or report)

Multi-file `docker_compose_config` against the canonical Hermes stack (`compose.yaml` + `compose.override.yaml`), as Hermes UID/GID 10000, via the canonical client:

```
decision: ALLOWED
reason: ok
returncode: 0
action: docker_compose_config
execution_class: A0
correlation_id: <exact match>
audit_id: <present>
duration_ms: 70
stdout_len: 0
stderr_len: 0
secret_pattern_hits: []
```

### repository_commit traceability fix

Every audit entry previously logged `repository_commit="unknown"` — nothing ever told the running daemon what commit was deployed. `hermes_root/daemon.py::main()` now requires `HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT` from the environment (a valid 7–40 hex character SHA) and fails closed (`SystemExit`) if it is missing or malformed.

Deployed and verified: a fresh `executor_health` request's audit entry now shows `repository_commit=ea26ff7a9899f4af7e462bcd8ef288c203cb4ff9` (the exact commit deployed), `daemon_version=2.0.0-repo`.

### Repository-managed systemd fixes

Both host-side systemd changes applied during this H3B effort are now codified as transactional, idempotent installer scripts under `ops/systemd/`:

- `install-hermes-executor-permissions-fix.sh` — the `Group=hermes` / `RuntimeDirectoryMode=0750` / `RuntimeDirectoryPreserve=restart` drop-in (root/GID preconditions, timestamped backup, atomic install, merged-unit verification, ownership verification, restart, automatic rollback with health check on failure, `--check` mode for precondition-only validation).
- `install-repository-commit-env.sh` — the `EnvironmentFile=` drop-in and the commit env file itself (same transactional pattern).

Both scripts were used for the final live deploy in this run (not just written and left untested) — this is the actual mechanism that produced the current running state, not a parallel manual path.

### Non-mocked timeout proof

The original `test_timeout_blocks` only mocked `subprocess.run` entirely — it proved the daemon *would* handle a `TimeoutExpired` exception, not that a real, long-running subprocess is actually bounded and cleaned up. A new `test_real_timeout_with_real_subprocess` forces `actions.build_argv` to return a real `sleep` command for one test only (never added to the production action registry — no permanent generic-shell or sleep capability introduced), sends it through the real `AF_UNIX` socket server with `timeout=1`, and verifies: genuine `subprocess.TimeoutExpired` handling, bounded wall-clock duration (~1s, not the full 5.417s sleep), correct `decision`/`reason`/`correlation_id`, a matching audit entry, and — via `pgrep` on a duration-specific marker — no orphaned child process.

### Final validation

- `git diff --check`: clean
- `bash -n` on both new installer scripts: clean
- `pytest tests/test_hermes_root_client.py tests/test_hermes_root_daemon.py tests/test_ops_systemd_installers.py -q`: **122 passed**
- Full repo suite: **812 passed, 52 skipped**
- Live re-verification: positive v1 proof, all 5/5 read-only actions (including the now-fixed `docker_compose_config`), full 7/7 security-proof matrix, isolated mutation lifecycle, audit correlation — all re-confirmed after the final restart

### Outstanding gate (external, not code)

**`H3B_RUNTIME_CONTROL_GREEN` is withheld pending explicit confirmation that the exposed credential has been revoked and replaced.** That confirmation is a human action outside this repository and this agent's reach — it cannot be verified from within the H3B proof matrix. Everything else required for GREEN (complete Issue #531 proof matrix, redacted/data-minimized Compose validation, zero known leak-spread, all tests green) is satisfied as of this commit.
