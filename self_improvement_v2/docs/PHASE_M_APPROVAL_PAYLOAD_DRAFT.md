# Phase M Approval Payload Draft — Controlled Read-Only Runtime Probe

## 1. Purpose

This document is the human-facing approval payload draft for **Issue #17** after the SI v2 foundation was merged into `main`.

It is **approval-review-only**. It does **not** execute Phase M and it does **not** authorize runtime mutation.

Scope of this refreshed draft:

- update the target context from the pre-merge branch to the canonical post-merge `main` state
- prepare an Option B candidate allowlist for a controlled read-only runtime observation
- keep every command exact, bounded, and reviewable before execution
- keep all runtime observation commands disabled until separate explicit human approval
- mark everything else as not approved

## 2. Canonical Post-Merge Context

Repository cleanup and SI v2 foundation integration are complete.

| Field | Value |
|---|---|
| Repository | `GoLukeEnviro/trading-hub` |
| Canonical branch | `main` |
| Canonical commit | `abbc6211cb462aa6683a006d566ad7a279280316` |
| SI v2 foundation PR | `#36` |
| Export-history extraction PR | `#42` |
| Old feature branch | `feat/si-v2-foundation` deleted after merge |
| Current local project path | `/home/hermes/projects/trading` |
| Current expected test baseline | `484 pytest items` / `483 passed, 1 skipped` |

Any stale reference to `feat/si-v2-foundation` or pre-merge SHAs is no longer canonical.

## 3. Non-Negotiable Safety Statement

The future probe, if separately approved, must not:

- create, cancel, modify, or simulate real orders
- enable live execution
- change `dry_run`
- write configs, strategies, databases, cron state, scheduler state, or job definitions
- restart, stop, start, reload, rebuild, recreate, or prune services or containers
- read or print secrets, tokens, keys, cookies, wallet material, chat IDs, or account credentials
- store raw output by default
- mutate files outside the explicitly approved evidence path
- proceed from observation to repair, deployment, restart, cron activation, or strategy mutation

A successful read-only probe does **not** authorize live trading, deployment, cron activation, strategy mutation, or remediation.

## 4. Refreshed Approval-Ready Payload Text

```text
APPROVE_PHASE_M_READ_ONLY_RUNTIME_PROBE

Issue: #17
Phase: M
Mode: controlled read-only runtime probe review
Repository: GoLukeEnviro/trading-hub
Local path: /home/hermes/projects/trading
Expected branch: main
Expected commit: abbc6211cb462aa6683a006d566ad7a279280316
Probe ID: phase-m-readonly-runtime-probe-postmerge-20260610-001
Evidence path: self_improvement_v2/reports/runtime_probe/phase-m-readonly-runtime-probe-postmerge-20260610-001/
Raw output stored by default: false
Sanitized evidence schema: RuntimeProbeEvidence
Redaction policy: PHASE_M_REDACTION_POLICY_V3
Abort policy: PHASE_M_ABORT_CRITERIA_V3
Execution authorization: no

Target mode decision: Option B prepared, not approved for execution.
Option B means: controlled read-only runtime observation may be approved later only with the exact command allowlist below and only after all preflight checks pass.

I confirm this payload is limited to review/preparation only.
I confirm no runtime observation command may be executed until a separate explicit approval is given.
I confirm no mutation, live execution, live account action, secret read, config write, strategy write, database write, cron change, scheduler change, or service lifecycle action is approved by this draft.
```

## 5. Target Context Decision

**Decision:** prepare Option B, but do not execute it.

Approved for preparation only:

- local shell session on the project host
- repository path `/home/hermes/projects/trading`
- canonical branch `main`
- canonical commit `abbc6211cb462aa6683a006d566ad7a279280316`
- evidence directory under `self_improvement_v2/reports/runtime_probe/`
- read-only observations only, if later separately approved

Not approved by this draft:

- service restart/stop/start/reload/rebuild/recreate/prune
- config write
- strategy write
- database write
- order action
- cron or scheduler mutation
- credential/token/chat-ID/account-secret access
- raw output storage by default
- any command not explicitly listed in the final execution approval

## 6. Option B Candidate Command Allowlist — Prepared, Not Executable Yet

This allowlist is a **candidate execution allowlist**. It is not executable until a later approval repeats the exact commands, target context, evidence path, redaction policy, timeout policy, and abort criteria.

### 6.1 Repository Preflight Commands

| ID | Exact command | Purpose | Read-only justification | Timeout | Expected output shape | Redaction requirement | Abort condition |
|---|---|---|---|---:|---|---|---|
| A-01 | `pwd` | Confirm working directory | Prints current path only | 5s | One absolute path | No redaction expected | Abort if not `/home/hermes/projects/trading` |
| A-02 | `git branch --show-current` | Confirm branch | Reads git metadata only | 5s | One branch name | No redaction expected | Abort if not `main` |
| A-03 | `git rev-parse HEAD` | Confirm commit | Reads git metadata only | 5s | One full SHA | No redaction expected | Abort if not `abbc6211cb462aa6683a006d566ad7a279280316` |
| A-04 | `git status --short --untracked-files=all` | Confirm working tree cleanliness | Reads git index/worktree metadata only | 10s | Empty if clean; short status otherwise | Redact sensitive path names if present | Abort if dirty outside approved evidence path |
| A-05 | `python -m py_compile self_improvement_v2/src/si_v2/runtime_probe/models.py self_improvement_v2/src/si_v2/runtime_probe/redaction.py` | Confirm runtime-probe support modules compile | Local Python compile only | 30s | Compile success/failure | No secrets expected | Abort on compile failure |
| A-06 | `python -m pytest self_improvement_v2/tests/test_runtime_probe_models.py self_improvement_v2/tests/test_runtime_probe_redaction.py -q` | Confirm evidence/redaction tests | Local test run only | 120s | pytest summary | No secrets expected | Abort on test failure |

### 6.2 Candidate Runtime Observation Commands

These commands are prepared as Option B candidates only. They must be re-approved exactly before execution.

| ID | Exact command | Purpose | Read-only justification | Timeout | Expected output shape | Redaction requirement | Abort condition |
|---|---|---|---|---:|---|---|---|
| B-01 | `docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'` | List visible containers by name/status/image | Metadata listing only; no lifecycle action | 10s | Bounded table | Redact private registry/account fragments if present | Abort if command errors, output includes secrets, or unexpected live-risk topology appears |
| B-02 | `docker inspect --format '{{json .State}}' trading-freqtrade-freqforge-1` | Read container state metadata for FreqForge | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-03 | `docker inspect --format '{{json .State}}' trading-freqtrade-freqforge-canary-1` | Read container state metadata for FreqForge canary | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-04 | `docker inspect --format '{{json .State}}' trading-freqtrade-regime-hybrid-1` | Read container state metadata for Regime Hybrid | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-05 | `docker inspect --format '{{json .State}}' trading-freqai-rebel-1` | Read container state metadata for FreqAI Rebel | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-06 | `docker inspect --format '{{json .State}}' trading-freqtrade-webserver-1` | Read container state metadata for Freqtrade webserver | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-07 | `docker inspect --format '{{json .State}}' trading-ai-hedge-fund-1` | Read container state metadata for ai-hedge-fund | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |
| B-08 | `docker inspect --format '{{json .State}}' trading-hermes-watchdog-1` | Read container state metadata for watchdog | State metadata only | 10s | JSON state object | No env/config fields allowed | Abort if container missing, inspect exposes env/config, or output is not state-only |

### 6.3 Candidate Health Endpoint Commands

These remain **candidate only** until the exact host/network context is confirmed immediately before execution.

| ID | Exact command | Purpose | Read-only justification | Timeout | Expected output shape | Redaction requirement | Abort condition |
|---|---|---|---|---:|---|---|---|
| C-01 | `curl -fsS --max-time 5 http://trading-freqtrade-freqforge-1:8080/api/v1/ping` | FreqForge ping | Health-only GET | 5s | Small JSON/text pong | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |
| C-02 | `curl -fsS --max-time 5 http://trading-freqtrade-freqforge-canary-1:8080/api/v1/ping` | FreqForge canary ping | Health-only GET | 5s | Small JSON/text pong | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |
| C-03 | `curl -fsS --max-time 5 http://trading-freqtrade-regime-hybrid-1:8080/api/v1/ping` | Regime Hybrid ping | Health-only GET | 5s | Small JSON/text pong | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |
| C-04 | `curl -fsS --max-time 5 http://trading-freqai-rebel-1:8080/api/v1/ping` | FreqAI Rebel ping | Health-only GET | 5s | Small JSON/text pong | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |
| C-05 | `curl -fsS --max-time 5 http://trading-freqtrade-webserver-1:8080/api/v1/ping` | Freqtrade webserver ping | Health-only GET | 5s | Small JSON/text pong | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |
| C-06 | `curl -fsS --max-time 5 http://trading-ai-hedge-fund-1:8080/health` | ai-hedge-fund health | Health-only GET | 5s | Small health JSON/text | No headers/tokens/cookies printed | Abort on auth challenge, non-health body, timeout, or secret-like output |

## 7. Explicitly Not Approved

No command is approved unless it appears in the final execution approval exactly as written.

Not approved:

- `docker restart`, `docker stop`, `docker start`, `docker compose up`, `docker compose down`, `docker compose restart`, `docker compose pull`, `docker compose build`, `docker system prune`
- `docker exec` unless separately approved with a specific non-secret, non-mutating command
- reading `.env` files
- reading full Freqtrade config files
- reading Telegram token sources
- reading exchange credential sources
- reading private databases or live trade ledgers
- writing any file outside the approved evidence path
- closing issues as part of execution
- pushing commits as part of execution
- cron, scheduler, or jobs mutation

## 8. Evidence Path Decision

Approved evidence path for a later execution approval:

```text
self_improvement_v2/reports/runtime_probe/phase-m-readonly-runtime-probe-postmerge-20260610-001/
```

Expected files if later approved and executed:

- `APPROVAL.md`
- `COMMAND_ALLOWLIST.md`
- `evidence.jsonl` with sanitized summaries only
- `redaction_report.md`
- `abort_report.md` only if any RED condition occurs
- `runtime_probe_review_report.md`

Raw output policy:

- `raw_output_stored=false` by default
- raw output may only be enabled by a separate explicit human decision
- if raw output is accidentally produced, it must be redacted before display or storage

## 9. Redaction Policy Alignment

Approved redaction classes in this draft:

- API-key-like values
- exchange-secret-like values
- Telegram-token-like values
- credentials embedded in URLs
- Authorization headers
- Cookie headers
- account identifiers
- private host/IP fragments
- high-entropy strings

Canonical placeholders:

- `[REDACTED_API_KEY]`
- `[REDACTED_EXCHANGE_SECRET]`
- `[REDACTED_TELEGRAM_TOKEN]`
- `[REDACTED_CREDENTIALS]`
- `[REDACTED_QUERY_VALUE]`
- `[REDACTED_AUTH_HEADER]`
- `[REDACTED_COOKIE]`
- `[REDACTED_ACCOUNT_IDENTIFIER]`
- `[REDACTED_PRIVATE_HOST]`
- `[REDACTED_HIGH_ENTROPY]`
- `[REDACTED_VALUE]`

Wallet-specific redaction is not claimed as approved in this draft. Wallet-like content must trigger abort or a separate approved revision before execution.

## 10. Abort Criteria

Abort the future probe immediately if any of the following occurs:

1. branch drift from `main`
2. HEAD drift from `abbc6211cb462aa6683a006d566ad7a279280316`
3. working tree is dirty outside the approved evidence path
4. any command differs from the exact allowlist in the final approval
5. any command needs a value that is not explicitly approved
6. any output contains secrets, tokens, credentials, wallet-like values, or account IDs
7. any redaction failure occurs
8. any mutation, config write, strategy write, database write, cron access, scheduler mutation, exchange action, or Telegram access is attempted
9. `raw_output_stored` would be set to `true` without explicit human approval
10. the evidence path differs from the exact path in this document
11. the target context becomes ambiguous at execution time
12. any endpoint requires authentication not explicitly approved
13. any health endpoint returns non-health content or unexpectedly large output
14. any safety rule from `CONTROLLED_READ_ONLY_RUNTIME_PROBE_PLAN.md` is violated

## 11. Submission Verdict

This refreshed draft is suitable for review as `REFRESH_PHASE_M_APPROVAL_PAYLOAD`.

It is **not** approval of execution.
It is **not** approval of runtime mutation.
It is **not** approval to run Phase M.

## 12. Next Required Human Decision

Before any execution, the operator must choose one of these paths:

- **Option A:** repository-local preflight only
- **Option B:** controlled read-only runtime observation using the candidate allowlist above
- **Option C:** stop and revise the payload again

Recommended next step: review this refreshed payload and decide whether to request `APPROVE_PHASE_M_READ_ONLY_RUNTIME_PROBE_OPTION_B` as a separate execution approval.
