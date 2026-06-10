# Controlled Read-Only Runtime Probe Plan — SI v2 Phase L

> **Status:** Planning document plus schema/redaction groundwork.
> **Runtime execution remains unimplemented in this phase; only typed evidence and fail-closed redaction helpers exist.**
> **No Docker, Freqtrade, Telegram, ai4trade-bot, exchange, database, cron, Hermes scheduler, or live runtime command was executed to create this document.**

---

## 1. Purpose

Phase L defines the first future controlled read-only runtime probe for the real
Docker/Freqtrade environment without performing that probe now.

The future probe goal is narrow:

> Observe runtime state, collect safety evidence, and abort on uncertainty —
> without mutating containers, configs, strategies, databases, cron state,
> orders, credentials, or live trading behaviour.

This document is a planning boundary for a later Phase M titled:

> **Controlled Read-Only Runtime Probe Execution**

Phase M is not authorized by this document. Phase M may execute only after a
separate explicit human approval ceremony that names the exact target context,
exact allowlisted command list, exact evidence location, exact redaction policy,
maximum runtime duration, and abort conditions.

---

## 2. Current Safety Posture

| Area | Phase L posture |
|------|-----------------|
| Live trading state | Assume `LIVE_FORBIDDEN` unless a later approval proves otherwise |
| Real adapters | Not activated |
| Docker/Freqtrade access | Not performed in Phase L |
| Telegram access | Not performed in Phase L |
| ai4trade runtime access | Not performed in Phase L |
| Cron activation | Forbidden |
| Strategy mutation | Forbidden |
| Database access | Forbidden |
| Secret handling | Forbidden to read or print |
| Evidence output | Future sanitized artifacts only, under an explicitly approved evidence directory |

The probe must preserve the core invariant from previous SI v2 phases:

> SI v2 remains advisory, dry-run/proposal-only, approval-gated, and unable to
> create real financial exposure.

---

## 3. Scope for a Future Approved Probe

A future Phase M may observe only these categories, and only after explicit
human approval:

| Observable category | Future intent | Mutation risk | Phase M requirement |
|---------------------|---------------|---------------|---------------------|
| Container presence | Confirm expected service names are visible | Low if read-only | Exact read-only container listing command must be approved |
| Container health status | Confirm runtime health/status labels or health checks | Low if read-only | Output must be summarized and redacted |
| Service process presence | Confirm expected service process exists | Medium if container exec is used | Must be read-only, bounded, and explicitly approved |
| Freqtrade `dry_run` status | Confirm no live execution path is enabled | High if config is read unsafely | Must use a redacted, minimal status source approved in Phase M |
| Read-only API health | Confirm explicitly approved health endpoints respond | Medium due network/auth risk | Must be endpoint allowlisted; no auth secrets printed |
| Redacted log snippets | Inspect recent errors/warnings only | Medium due accidental secret leakage | Tail size, paths, and redaction rules must be approved first |

A future probe must not infer safety from a single green indicator. Container
presence, health, dry-run status, logs, RiskGuard availability, and ShadowLogger
availability are separate evidence classes.

---

## 4. Explicitly Forbidden Categories

The future probe must never include these categories unless a separate phase is
approved with a higher risk classification and rollback plan. Phase M is not
such a phase.

| Forbidden category | Reason |
|--------------------|--------|
| Restarts, starts, stops, reloads, rebuilds, recreates, prunes | Runtime mutation and outage risk |
| Exec-based mutation | Could alter container state, strategy state, files, orders, or credentials |
| Config writes | Can change trading/runtime behaviour |
| Strategy writes | Can change trading decisions and requires separate approval path |
| Database writes | Can corrupt trading history, ledgers, or Freqtrade state |
| Order creation or cancellation | Real financial exposure risk |
| Cron activation or scheduler mutation | Can trigger repeated runtime side effects |
| Token, credential, wallet, exchange key, Telegram token, or chat ID reads | Secret exposure risk |
| Full live config reads by default | High probability of embedded secrets or sensitive paths |
| Live strategy file reads by default | Outside the minimum runtime proof scope |
| ai4trade-bot runtime imports or direct source coupling | Boundary violation; REST boundary remains separate |
| Remote push | Not part of runtime evidence collection |

---

## 5. Future Read-Only Command Allowlist Design

Phase L does not approve exact commands. It defines categories that may be
converted into an exact command list during the Phase M approval ceremony.

Every future command must be documented with:

1. Purpose
2. Read-only justification
3. Expected output shape
4. Redaction requirement
5. Failure mode
6. Abort condition
7. Maximum runtime / timeout
8. Evidence storage policy

### 5.1 Container Presence Category

| Field | Requirement |
|-------|-------------|
| Purpose | Determine whether expected container names are present |
| Read-only justification | Listing metadata should not change container state |
| Expected output shape | Bounded table or JSON summary: container name, status, image/tag, created age |
| Redaction requirement | Remove registry credentials, internal hostnames, private infrastructure identifiers if present |
| Failure mode | Docker socket unavailable, permission denied, unexpected command output |
| Abort condition | Command is not exact-approved; output includes secrets; output indicates unknown live container topology |

### 5.2 Container Health Status Category

| Field | Requirement |
|-------|-------------|
| Purpose | Determine whether expected containers report healthy/running/unhealthy states |
| Read-only justification | Reading health metadata should not mutate container state |
| Expected output shape | One row per approved target: name, status, health, restart count if safely exposed |
| Redaction requirement | Remove container IDs beyond short hashes if not needed; remove host paths and labels that may reveal secrets |
| Failure mode | Missing health metadata, inaccessible target, ambiguous multiple matches |
| Abort condition | Health source requires config/secret access; status contradicts expected safety assumptions |

### 5.3 Service Process Presence Category

| Field | Requirement |
|-------|-------------|
| Purpose | Confirm the expected service process is present without controlling it |
| Read-only justification | Process listing is observational only when bounded and non-interactive |
| Expected output shape | Sanitized summary: process name/pattern present or absent; no full environment dump |
| Redaction requirement | Strip environment variables, command-line credentials, tokens, URLs with credentials, account identifiers |
| Failure mode | Command would require interactive shell, full env exposure, or privileged process introspection |
| Abort condition | Any command would expose environment variables or allow mutation; any target requires shell access not pre-approved |

### 5.4 Freqtrade `dry_run` Status Category

| Field | Requirement |
|-------|-------------|
| Purpose | Confirm Freqtrade is not in live mode before any later observation is trusted |
| Read-only justification | A minimal status query may be observational if it does not read secrets or mutate state |
| Expected output shape | Boolean/tri-state summary: `dry_run_confirmed`, `dry_run_false`, or `unknown` with evidence source |
| Redaction requirement | Never print full config; redact exchange names, account identifiers, keys, Telegram fields, URLs with credentials |
| Failure mode | Dry-run status cannot be determined without reading sensitive config; status source unavailable |
| Abort condition | `dry_run=false`, dry-run unknown after approved checks, or evidence requires exposing secrets |

### 5.5 Read-Only API Health Category

| Field | Requirement |
|-------|-------------|
| Purpose | Confirm explicitly approved local/read-only health endpoints respond |
| Read-only justification | Health endpoints should not change server state when endpoint semantics are documented |
| Expected output shape | HTTP status code, latency bucket, service version/build if safe, health verdict |
| Redaction requirement | Remove auth headers, tokens, cookies, request IDs if account-linked, internal URLs if needed |
| Failure mode | Non-allowlisted host, auth challenge, TLS/certificate error, timeout, unexpected body |
| Abort condition | Endpoint is not on exact allowlist; response includes secrets; endpoint is not health-only |

### 5.6 Redacted Log Snippet Category

| Field | Requirement |
|-------|-------------|
| Purpose | Capture bounded recent warnings/errors for context, not full logs |
| Read-only justification | Tail-style retrieval is observational if bounded and redacted before storage/reporting |
| Expected output shape | Last N lines or time-bounded snippets summarized by severity and component |
| Redaction requirement | Mandatory redaction before display or storage; raw output not stored unless explicitly approved |
| Failure mode | Logs contain credentials, full order payloads, account identifiers, or excessive volume |
| Abort condition | Redaction cannot be guaranteed; log source includes secrets; requested tail exceeds approved bound |

---

## 6. Future RuntimeProbeEvidence Model

The future evidence record should be schema-defined before any probe executes.
Issue #19 now implements the typed `RuntimeProbeEvidence` model and sanitized
summary types in `src/si_v2/runtime_probe/models.py`, while probe execution
remains out of scope.

| Field | Type concept | Required | Description |
|-------|--------------|----------|-------------|
| `timestamp_utc` | ISO-8601 UTC string | Yes | Time the evidence item was collected |
| `probe_id` | Stable string | Yes | Unique identifier for the approved Phase M run |
| `target` | String | Yes | Approved target alias, not secret-bearing host details |
| `command_category` | Enum-like string | Yes | One of the approved categories from this plan |
| `sanitized_output_summary` | String/object | Yes | Human-readable evidence after redaction |
| `raw_output_stored` | Boolean | Yes | Whether raw output was stored; default should be `false` |
| `redaction_applied` | Boolean | Yes | Whether the redaction pipeline was applied before reporting |
| `safety_verdict` | `GREEN` / `YELLOW` / `RED` | Yes | Verdict for this evidence item |
| `abort_reason` | String or null | Yes | Required when verdict is `RED`; optional for `YELLOW` |

Recommended future storage layout, subject to approval:

```text
self_improvement_v2/reports/runtime_probe/<probe_id>/
  APPROVAL.md
  COMMAND_ALLOWLIST.md
  evidence.jsonl          # sanitized summaries only by default
  redaction_report.md
  abort_report.md         # only if any RED condition occurs
```

Raw outputs should not be stored by default. If raw storage is approved later,
it must use a separate explicitly named directory with restricted access and a
retention rule; redacted summaries remain the default evidence artifact.

---

## 7. Mandatory Redaction Rules

Redaction must happen before output is printed in a user-facing report or stored
as normal evidence. Issue #19 implements fail-closed summary redaction helpers
in `src/si_v2/runtime_probe/redaction.py`. Failed redaction is treated as a
probe abort, not as a warning to ignore.

| Sensitive class | Redaction requirement |
|-----------------|----------------------|
| API keys | Replace with `[REDACTED_API_KEY]` |
| Exchange keys/secrets | Replace with `[REDACTED_EXCHANGE_SECRET]` |
| Telegram bot tokens | Replace with `[REDACTED_TELEGRAM_TOKEN]` |
| Telegram chat IDs | Replace with `[REDACTED_TELEGRAM_CHAT_ID]` when user/account-linked |
| URLs with credentials | Preserve scheme/host if safe; replace userinfo/query secret fields |
| Bearer/basic auth headers | Replace complete header value |
| Cookies/session IDs | Replace complete cookie/session value |
| Account identifiers | Replace with stable non-reversible aliases when needed |
| Private infrastructure identifiers | Replace private IPs, internal hostnames, or host paths when needed |
| Wallet addresses | Replace with `[REDACTED_WALLET]` unless explicitly approved for display |

Minimum pattern families for the future redactor:

- Key/value pairs whose key contains `key`, `secret`, `token`, `password`,
  `passphrase`, `credential`, `authorization`, `cookie`, or `chat_id`
- Credential-bearing URLs with `userinfo@host` or secret query parameters
- Known token-like strings for Telegram and common exchange/API formats
- Long high-entropy strings above an approved threshold
- Environment-variable style assignments containing sensitive names

The future probe must never read `TELEGRAM_BOT_TOKEN`, exchange keys, wallet
material, or chat IDs intentionally. Redaction is a backstop for accidental
exposure, not permission to collect secrets.

---

## 8. Approval Ceremony Required Before Phase M

Phase M must not proceed until the operator gives explicit written approval
after reviewing this plan. The approval must be specific enough that a later
audit can determine exactly what was authorized.

Required approval fields:

| Approval field | Required content |
|----------------|------------------|
| Phase title | `Controlled Read-Only Runtime Probe Execution` |
| Exact command list | Every command or API request to run, with arguments, timeouts, and target aliases |
| Exact target host/context | Local shell, container host, profile, repo path, and any target aliases |
| Exact output storage location | Approved directory under `self_improvement_v2/` or another explicitly approved evidence path |
| Exact redaction policy | Pattern set, raw-output policy, reporting policy |
| Maximum runtime duration | Hard wall-clock limit and per-command timeout |
| Abort conditions | Complete list of stop conditions from this document plus any operator additions |
| Rollback/no-op confirmation | Statement that Phase M performs no mutation and requires no rollback beyond aborting |
| Stash quarantine awareness | Confirmation that Phase L.0 quarantine stash is not part of Phase M evidence |
| Live trading state assumption | Explicit statement that unknown state means `LIVE_FORBIDDEN` and no orders are allowed |

Recommended approval phrase format:

```text
APPROVE_PHASE_M_READ_ONLY_RUNTIME_PROBE
Target context: <exact host/profile/repo>
Command allowlist: <exact commands/API requests>
Evidence path: <exact path>
Redaction policy: <named policy/version>
Max duration: <duration>
Abort conditions: <list or reference>
No-op confirmation: I understand this phase must not mutate Docker, Freqtrade,
configs, strategies, databases, cron, orders, credentials, or live runtime state.
```

If any required approval field is missing, Phase M must stop before running a
single runtime command.

---

## 9. Abort Criteria and Safety Gates

A future read-only runtime probe must abort immediately when any criterion below
is met. Aborting is the safe outcome and must be reported as `RED` when the
probe cannot safely continue.

| Abort criterion | Required action |
|-----------------|-----------------|
| Dirty working tree outside the approved evidence path | Stop before runtime access |
| Unexpected branch or HEAD drift | Stop before runtime access |
| Command/API request not on exact allowlist | Do not run it |
| Command attempts mutation or has ambiguous side effects | Do not run it |
| Docker or Freqtrade state differs from expected safety assumptions | Stop and report `RED` or `YELLOW` depending on exposure |
| Live trading is detected or `dry_run` is false | Stop and report `RED` |
| `dry_run` cannot be confirmed from approved evidence | Stop and report `YELLOW` or `RED`; do not infer safety |
| Secret exposure risk is detected before execution | Do not run the command |
| Output contains credentials, tokens, wallet data, or account secrets | Stop reporting raw output; redact; mark `RED` if containment uncertain |
| Redaction fails or cannot be verified | Stop and mark `RED` |
| RiskGuard unavailable during a safety-relevant decision | Continue read-only evidence only if safe; block decisions/mutations |
| ShadowLogger unavailable during evidence/decision logging | Continue read-only evidence only with warning; block writes/decisions |
| API endpoint requires auth not explicitly approved | Do not call it |
| Log source appears to include secrets or excessive unbounded content | Do not read or store it |
| Runtime duration or call budget exceeded | Stop the probe |

### GREEN / YELLOW / RED Verdict Criteria

| Verdict | Meaning | Minimum conditions |
|---------|---------|--------------------|
| `GREEN` | Read-only probe completed safely | Exact allowlist followed; no mutation; no secrets; dry-run confirmed; evidence redacted; no aborts |
| `YELLOW` | Probe produced partial evidence with uncertainty | Read-only invariant held, but some targets unavailable, dry-run unknown, or non-critical evidence incomplete |
| `RED` | Probe blocked or unsafe | Live mode detected, command not allowlisted, mutation attempt, secret exposure, redaction failure, or safety assumption violated |

A `GREEN` runtime probe does not authorize live trading, strategy mutation,
cron activation, real adapter deployment, or order creation. It only proves the
specific approved observations completed safely.

---

## 10. Phase M Runbook Draft — Controlled Read-Only Runtime Probe Execution

This is a draft for the next phase. It is not approval to execute.

### Phase M Title

**Controlled Read-Only Runtime Probe Execution**

### Phase M Objective

Collect bounded read-only runtime evidence from explicitly approved targets,
redact it, store sanitized evidence, and report a GREEN/YELLOW/RED verdict.

### Phase M Non-Negotiable Rules

1. Do not mutate Docker, containers, files, configs, strategies, databases,
   cron, scheduler state, orders, credentials, or live trading state.
2. Do not run any command not present in the exact approved allowlist.
3. Do not read secrets intentionally.
4. Do not print raw output until redaction has been applied.
5. Abort on `dry_run=false`, unknown live state requiring unsafe inspection, or
   any sign of live-money risk.
6. Keep all evidence within the approved evidence path.
7. Do not use or inspect the Phase L.0 quarantine stash as probe evidence.
8. Do not proceed from observation to repair, restart, deployment, cron
   activation, or strategy mutation.

### Phase M Execution Skeleton

| Step | Action | Stop condition |
|------|--------|----------------|
| M0 | Verify approval payload is complete | Missing field |
| M1 | Verify branch, HEAD, and clean working tree | Drift or dirty tree |
| M2 | Create approved evidence directory | Path not approved or outside scope |
| M3 | Execute allowlisted read-only observations one by one | Any command fails safety precheck |
| M4 | Redact each output before display/storage | Redaction failure |
| M5 | Write sanitized `RuntimeProbeEvidence` records | Evidence path issue |
| M6 | Assign GREEN/YELLOW/RED verdict | Any RED criterion |
| M7 | Report without proposing mutation | Any request to mutate requires new phase |

---

## 11. Remaining Gaps Before Phase M

Phase M still needs all of the following before execution:

1. Exact command/API allowlist approved by the human operator
2. Exact target host/context approved by the human operator
3. Evidence directory approved and confirmed writable without touching live paths
4. Redaction policy converted from this document into an operator-approved checklist
5. Raw-output storage policy decided; default remains no raw storage
6. Per-command timeout and maximum phase duration approved
7. RiskGuard and ShadowLogger availability expectations declared
8. Dry-run confirmation method selected without full secret-bearing config reads
9. Log snippet scope limited by line count/time window/component
10. Final abort checklist copied into the Phase M prompt

---

## 12. Phase L Confirmation

This document still does not implement a probe adapter, runtime runner, cron
job, or scheduler integration. It now includes repository support for the
evidence schema class and fail-closed redaction helpers only.
It does not approve runtime access. It does not change live trading state.
