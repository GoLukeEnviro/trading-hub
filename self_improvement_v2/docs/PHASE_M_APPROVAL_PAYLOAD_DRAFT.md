# Phase M Approval Payload Draft — Controlled Read-Only Runtime Probe

## 1. Purpose

This document is the human-facing approval payload for **Issue #17**.
It is **approval-review-only**. It does **not** execute Phase M and it does **not** authorize any runtime mutation.

Scope of this draft:
- review a controlled read-only probe plan
- keep the target context explicit
- keep every approved command exact and read-only
- mark everything else as not approved until the human supplies exact values

## 2. Non-Negotiable Safety Statement

The future probe, if approved, must not:
- touch Docker
- touch Freqtrade runtime, configs, strategies, databases, RPC, REST, or WebSocket endpoints
- touch Telegram APIs, tokens, or chat IDs
- touch exchanges or live accounts
- touch cron or Hermes scheduler state
- touch ai4trade-bot runtime endpoints
- expose secrets
- store raw output by default
- mutate files, services, jobs, or runtime state

## 3. Approval-Ready Payload Text

```text
APPROVE_PHASE_M_READ_ONLY_RUNTIME_PROBE

Issue: #17
Phase: M
Mode: controlled read-only runtime probe review
Target context: repository-local shell context for /home/hermes/projects/trading on branch feat/si-v2-foundation; no Docker/container host, Freqtrade runtime, Telegram endpoint, exchange endpoint, live database, cron target, or scheduler target is approved in this draft.
Repository: GoLukeEnviro/trading-hub
Local path: /home/hermes/projects/trading
Expected branch: feat/si-v2-foundation
Expected base commit: ffd603116fa78e2765d3c7fcc7fbe54ec4adbd7e
Probe ID: phase-m-readonly-runtime-probe-20260610-001
Evidence path: self_improvement_v2/reports/runtime_probe/phase-m-readonly-runtime-probe-20260610-001/
Raw output stored by default: false
Sanitized evidence schema: RuntimeProbeEvidence
Redaction policy: PHASE_M_REDACTION_POLICY_V3
Abort policy: PHASE_M_ABORT_CRITERIA_V3
Human approval required: yes
Execution authorization: no

I confirm this payload is limited to read-only review only.
I confirm no runtime command may be executed until a human explicitly approves this payload.
I confirm no live trading, live config reads, live strategy reads, live DB reads, cron access, scheduler access, or external runtime access is approved here.
```

## 4. Target Context Decision

**Decision:** keep the target context strictly local and repository-bound.

Approved context:
- local shell session
- repository path `/home/hermes/projects/trading`
- branch `feat/si-v2-foundation`
- review commit `ffd603116fa78e2765d3c7fcc7fbe54ec4adbd7e`

Not approved in this draft:
- any Docker host or container name
- any Freqtrade bot name or endpoint
- any Telegram endpoint or token-bearing target
- any exchange endpoint
- any live database URL or file
- any cron or Hermes scheduler target

## 5. Approval-Ready Command Allowlist

These commands are exact, bounded, and read-only.
They can be used for preflight verification only.

| ID | Exact command | Purpose | Read-only justification | Timeout | Expected output shape | Redaction requirement | Abort condition |
|---|---|---|---|---:|---|---|---|
| A-01 | `pwd` | Confirm the working directory | Prints the current path only | 5s | One absolute path line | No redaction expected | Abort if path is not `/home/hermes/projects/trading` |
| A-02 | `git branch --show-current` | Confirm current branch | Reads repo metadata only | 5s | One branch name line | No redaction expected | Abort if branch is not `feat/si-v2-foundation` |
| A-03 | `git rev-parse HEAD` | Confirm current commit | Reads repo metadata only | 5s | One full SHA line | No redaction expected | Abort if HEAD drifts from `ffd603116fa78e2765d3c7fcc7fbe54ec4adbd7e` |
| A-04 | `git status --short --untracked-files=all` | Confirm working tree cleanliness | Reads git index and worktree state only | 10s | Empty output if clean; otherwise short status lines | If any sensitive path names appear unexpectedly, redact them before human-facing reporting | Abort if unrelated dirty files exist |

## 6. NOT APPROVED / NEEDS HUMAN VALUES

These categories remain out of scope until the human provides exact values.
No executable command is approved here.

| Category | Missing human value | Why it cannot be inferred safely |
|---|---|---|
| Docker metadata observation | exact Docker host/socket path and exact container name(s) | guessing a host or container could target the wrong runtime or imply a forbidden runtime path |
| Freqtrade dry-run confirmation | exact approved safe method and exact target instance | live config, runtime, and strategy targets are explicitly off-limits in this draft |
| Read-only health checks for any runtime endpoint | exact endpoint URL and exact output bounds | endpoint guesses can hit live services or leak secrets |
| Log snippet review | exact log source, exact time/line bounds, exact component filter | unbounded logs can expose secrets and unrelated runtime state |
| Telegram target inspection | exact allowed target and exact redaction-safe fields | Telegram tokens and chat IDs are explicitly disallowed here |
| Wallet-specific redaction claim | an explicit approved wallet rule and tests | this draft does not claim a dedicated wallet redaction rule; wallet-like values must remain an abort trigger until separately approved |

## 7. Evidence Path Decision

**Decision:** use one explicit evidence directory only.

Approved evidence path:
- `self_improvement_v2/reports/runtime_probe/phase-m-readonly-runtime-probe-20260610-001/`

Evidence files expected there, if the human later approves execution:
- probe summary
- sanitized output summary
- command transcript metadata
- abort notes, if any

Raw output policy:
- `raw_output_stored=false` by default
- raw output may only be enabled by a separate explicit human decision

## 8. Redaction Policy Alignment

This draft aligns the approval payload with the currently approved runtime-probe redaction behavior by using only redaction classes that are already covered by the payload text.

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

Canonical placeholders used by this draft:
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
- `[REDACTED_VALUE]` when a generic sensitive field cannot be classified more specifically

**Wallet-specific redaction is not claimed as approved in this draft.**
If wallet-like content appears during any future probe, it must trigger abort or a separate approved revision before execution.

## 9. Abort Criteria

Abort the future probe immediately if any of the following occurs:

1. branch drift from `feat/si-v2-foundation`
2. HEAD drift from `ffd603116fa78e2765d3c7fcc7fbe54ec4adbd7e`
3. working tree is dirty outside the approved evidence path
4. any command differs from the exact allowlist in Section 5
5. any command needs a value that is not explicitly approved in Section 4 or 6
6. any output contains secrets, tokens, credentials, wallet-like values, or account IDs
7. any redaction failure occurs
8. any runtime mutation, live config read, live strategy read, live DB read, cron access, scheduler access, exchange access, or Telegram access is attempted
9. `raw_output_stored` would be set to `true` without explicit human approval
10. the evidence path differs from the exact path in Section 7
11. the target context becomes ambiguous at execution time
12. any Docker/Freqtrade/runtime endpoint appears without a human-supplied exact value
13. any future probe reveals a mismatch between payload text and implemented redaction behavior
14. any safety rule from the Phase L plan is violated

## 10. Submission Verdict

This draft is now suitable to be presented to the human for explicit approval **as a read-only review payload only**.

It is **not** approval of execution.
It is **not** approval of runtime access.
It is **not** approval to execute Phase M.
