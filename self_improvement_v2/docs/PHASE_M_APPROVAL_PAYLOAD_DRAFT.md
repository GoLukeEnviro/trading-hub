# Phase M.0 Approval Payload Draft — Controlled Read-Only Runtime Probe

> **Issue:** #16
> **Status:** Draft payload only.
> **No runtime command in this document has been executed.**

---

## 1. Purpose

This document converts the Phase L planning document into a concrete human
approval payload draft for the future Phase M:

> **Controlled Read-Only Runtime Probe Execution**

This is not approval. Phase M remains blocked until a human operator replaces
all placeholders, verifies every command, and explicitly signs the approval
ceremony.

---

## 2. Non-Negotiable Safety Rules

1. No mutation of Docker, Freqtrade, configs, strategies, databases, cron,
   Hermes scheduler state, orders, credentials, or live trading state.
2. No command may run unless it appears exactly in the approved allowlist.
3. No `docker restart`, `docker stop`, `docker start`, `docker reload`,
   `docker rebuild`, `docker recreate`, `docker prune`, or equivalent mutation.
4. No Freqtrade order, trade, config-write, strategy-write, database-write, or
   backtest command.
5. No Telegram API calls and no Telegram token/chat ID reads.
6. No ai4trade-bot runtime HTTP calls, imports, source copy, vendor, submodule,
   or clone.
7. No exchange access.
8. No live database access.
9. No cron activation, scheduler mutation, or `jobs.json` edit.
10. No secret, wallet, credential, API key, or token reads.
11. Abort if `dry_run=false`, if live trading is detected, or if dry-run status
    cannot be confirmed safely from approved evidence.
12. Abort if redaction fails before user-facing output or evidence storage.

---

## 3. Approval Payload Template

The operator must fill every `TO_BE_FILLED_BY_HUMAN` value before Phase M can
start. Any remaining placeholder is an automatic abort.

```text
APPROVE_PHASE_M_READ_ONLY_RUNTIME_PROBE

Phase title: Controlled Read-Only Runtime Probe Execution
Target context: TO_BE_FILLED_BY_HUMAN
Repository path: /home/hermes/projects/trading
Expected branch: feat/si-v2-foundation
Expected base commit: 6a7f118dc2f99c2d3b684dd9d4f13dcbe73f123e or a later explicitly reviewed SI v2 docs-only/backlog commit
Evidence path: self_improvement_v2/reports/runtime_probe/TO_BE_FILLED_BY_HUMAN_PROBE_ID
Raw output storage: false
Maximum runtime duration: 10 minutes
Per-command timeout: 15 seconds unless explicitly overridden below
Redaction policy: PHASE_M_REDACTION_POLICY_V1 from this document
Abort conditions: PHASE_M_ABORT_CRITERIA_V1 from this document
No-op confirmation: I understand this phase must not mutate Docker, Freqtrade,
configs, strategies, databases, cron, scheduler state, orders, credentials, or
live runtime state. I understand a GREEN verdict authorizes no live trading.
```

---

## 4. Target Context Draft

The exact target context is intentionally not guessed in this repository.
The human approval must provide:

| Field | Required value |
|-------|----------------|
| Host/context | Exact shell/profile/host where the read-only probe is allowed |
| Repo path | `/home/hermes/projects/trading` unless explicitly changed |
| Docker host | Exact Docker context or socket path, if Docker metadata is allowed |
| Container aliases | Exact approved aliases and exact container names |
| Freqtrade status source | Exact safe method for `dry_run` confirmation |
| API endpoints | Exact local/read-only health URLs, if any |
| Log sources | Exact approved log source and max line/time bounds, if any |

If exact container names, endpoints, or log sources are not provided, their
corresponding allowlist entries remain disabled.

---

## 5. Exact Command Allowlist Draft

Commands below are a draft allowlist for the approval payload. They must be
copied into the final approval with all placeholders replaced by exact values.
Commands marked `DISABLED_UNTIL_FILLED` must not run while placeholders remain.

### 5.1 Repository Preflight Commands

These commands prove the repository context before any runtime observation.
They do not access Docker, Freqtrade, Telegram, ai4trade, exchanges, live DBs,
cron, or strategy paths.

| ID | Status | Command | Purpose | Timeout |
|----|--------|---------|---------|---------|
| `repo-01` | enabled | `pwd` | Confirm current directory | 5s |
| `repo-02` | enabled | `git branch --show-current` | Confirm branch | 5s |
| `repo-03` | enabled | `git rev-parse HEAD` | Confirm commit | 5s |
| `repo-04` | enabled | `git status --short --untracked-files=all` | Abort on dirty tree outside evidence path | 5s |

### 5.2 Docker Metadata Commands

These commands are read-only Docker metadata observations. They are disabled
until the human approval names exact target containers. Do not use globs or
broad unbounded output.

| ID | Status | Command | Purpose | Timeout |
|----|--------|---------|---------|---------|
| `docker-presence-01` | `DISABLED_UNTIL_FILLED` | `docker --host TO_BE_FILLED_BY_HUMAN_DOCKER_HOST ps --filter name=TO_BE_FILLED_EXACT_CONTAINER_NAME --format '{{.Names}}\t{{.Status}}\t{{.Image}}'` | Confirm exact container presence/status | 15s |
| `docker-health-01` | `DISABLED_UNTIL_FILLED` | `docker --host TO_BE_FILLED_BY_HUMAN_DOCKER_HOST inspect --format '{{json .State.Health}}' TO_BE_FILLED_EXACT_CONTAINER_NAME` | Read health object only; no full inspect | 15s |
| `docker-state-01` | `DISABLED_UNTIL_FILLED` | `docker --host TO_BE_FILLED_BY_HUMAN_DOCKER_HOST inspect --format '{{.Name}}\t{{.State.Status}}\t{{.State.Running}}\t{{.State.Restarting}}\t{{.State.OOMKilled}}' TO_BE_FILLED_EXACT_CONTAINER_NAME` | Read bounded state fields only | 15s |
| `docker-process-01` | `DISABLED_UNTIL_FILLED` | `docker --host TO_BE_FILLED_BY_HUMAN_DOCKER_HOST top TO_BE_FILLED_EXACT_CONTAINER_NAME -eo pid,comm` | Confirm process presence without command args/env | 15s |

Forbidden Docker forms for Phase M include but are not limited to:
`restart`, `stop`, `start`, `reload`, `kill`, `exec`, `cp`, `compose up`,
`compose down`, `build`, `recreate`, `prune`, and full unfiltered `inspect`.

### 5.3 Freqtrade Dry-Run Confirmation

No default Freqtrade command is approved in this draft because full config,
REST, RPC, WebSocket, and database reads may expose secrets or live state.
The human operator must provide a minimal, redacted, read-only method before
Phase M can claim `dry_run_confirmed`.

| ID | Status | Command/API | Purpose | Timeout |
|----|--------|-------------|---------|---------|
| `freqtrade-dry-run-01` | `DISABLED_PENDING_HUMAN_METHOD` | `TO_BE_FILLED_BY_HUMAN_SAFE_DRY_RUN_STATUS_METHOD` | Confirm `dry_run` without full config or secret exposure | 15s |

Abort if this method is missing, if it returns `dry_run=false`, or if it
requires reading secrets, full configs, live databases, or strategy files.

### 5.4 Read-Only API Health Commands

No API health endpoint is enabled by default. The human approval must list exact
localhost or explicitly approved health endpoints. Authenticated endpoints are
disallowed unless the approval also describes how auth can be checked without
reading or printing secrets.

| ID | Status | Command/API | Purpose | Timeout |
|----|--------|-------------|---------|---------|
| `api-health-01` | `DISABLED_UNTIL_FILLED` | `TO_BE_FILLED_BY_HUMAN_EXACT_HEALTH_REQUEST` | Confirm health-only endpoint | 15s |

Abort if the endpoint is not health-only, not exact, not local/approved, or
returns credentials, account identifiers, order data, trade payloads, or secrets.

### 5.5 Redacted Log Snippet Commands

No log snippet command is enabled by default. If approved, log reads must be
bounded by exact source, max lines, and component/time filter.

| ID | Status | Command | Purpose | Timeout |
|----|--------|---------|---------|---------|
| `logs-01` | `DISABLED_UNTIL_FILLED` | `TO_BE_FILLED_BY_HUMAN_EXACT_BOUNDED_LOG_SNIPPET_COMMAND` | Collect redacted warning/error snippet | 15s |

Abort if redaction cannot be applied before display/storage, if logs contain
credentials, or if the requested tail is unbounded.

---

## 6. Evidence Path

Default draft evidence path:

```text
self_improvement_v2/reports/runtime_probe/TO_BE_FILLED_BY_HUMAN_PROBE_ID/
```

Required files for Phase M:

```text
APPROVAL.md
COMMAND_ALLOWLIST.md
evidence.jsonl
redaction_report.md
abort_report.md        # only if any RED condition occurs
```

Default raw-output policy:

```text
raw_output_stored=false
```

Raw output storage is not approved by this draft. If the human operator wants
raw output storage, that must be explicitly added to the approval with path,
retention, access control, and redaction/containment rationale.

---

## 7. Redaction Policy V1

Apply redaction before any user-facing report or normal evidence write.
The future probe must abort if redaction fails.

| Class | Replacement |
|-------|-------------|
| API keys | `[REDACTED_API_KEY]` |
| Exchange keys/secrets | `[REDACTED_EXCHANGE_SECRET]` |
| Telegram bot tokens | `[REDACTED_TELEGRAM_TOKEN]` |
| Telegram chat IDs | `[REDACTED_TELEGRAM_CHAT_ID]` when user/account-linked |
| Credential-bearing URLs | Remove userinfo and secret query parameters |
| Authorization headers | `[REDACTED_AUTH_HEADER]` |
| Cookies/session IDs | `[REDACTED_SESSION]` |
| Wallet addresses | `[REDACTED_WALLET]` unless explicitly approved |
| Account identifiers | Stable non-reversible alias when needed |
| Private infrastructure identifiers | Redact private IPs/internal hostnames/host paths when needed |

The probe must never intentionally read secrets. Redaction is only a containment
backstop for accidental exposure.

---

## 8. Abort Criteria V1

Phase M must abort immediately on any of the following:

1. Approval payload missing or ambiguous.
2. Dirty working tree outside the approved evidence path.
3. Unexpected branch or HEAD drift.
4. Any command/API request not exactly on the allowlist.
5. Any command attempts mutation or ambiguous side effects.
6. Docker or Freqtrade state contradicts safety assumptions.
7. Live trading detected or `dry_run=false`.
8. `dry_run` cannot be confirmed from approved evidence.
9. Secret exposure risk detected before execution.
10. Output contains credentials, tokens, wallet data, or account secrets.
11. Redaction fails or cannot be verified.
12. RiskGuard unavailable during a safety-relevant decision.
13. ShadowLogger unavailable during evidence/decision logging.
14. API endpoint requires unapproved auth.
15. Log source includes secrets or unbounded content.
16. Runtime duration or call budget exceeded.

---

## 9. Phase M Status

Phase M remains **BLOCKED** until a human operator approves the final payload.
This draft intentionally leaves target-specific placeholders unfilled rather
than guessing live infrastructure details.

A complete approval must name exact targets and exact commands. A GREEN verdict
from Phase M would authorize only the approved read-only observations; it would
not authorize live trading, strategy mutation, cron activation, real adapter
deployment, restarts, or order creation.
