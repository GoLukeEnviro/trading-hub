# ADR-2026-08-04 — Standing Owner Authorization

## Metadata

- **Date:** 2026-08-04
- **Status:** Accepted
- **Source:** Issue #605 comment `5179703046` (`OWNER_STANDING_AUTHORIZATION_V1`), GitHub user `GoLukeEnviro` (Luke), 2026-08-04T13:25:43Z
- **Funding decision source:** Issue #697 comment `5179705029` (`HUMAN_DECISION_ON_CANONICAL_FUNDING_DATA_CONTRACT`), GitHub user `GoLukeEnviro` (Luke), 2026-08-04T13:25:54Z

## Context

The Trading Hub roadmap previously required a unique, per-task human approval
marker for A2 execution, A1 merges, and A3 authorization. This produced
repeated blocking states (`BLOCKED_BY_MISSING_A2_MARKER`,
`READY_FOR_HUMAN_MERGE`) that did not reflect the owner's actual standing
intent and delayed legitimate, technically gated work.

Luke has issued a durable standing authorization for the whole Trading Hub
project (comment `5179703046`), explicitly superseding per-task human marker
requirements.

## Decision

Luke grants a permanent Standing Owner Authorization for all recurring human
Trading Hub gates:

```text
OWNER_STANDING_AUTHORIZATION_V1
scope=TRADING_HUB_PROJECT
owner=Luke
confirmed_by=Luke
human_gate_policy=STANDING_APPROVED
approval_marker_recheck=NOT_REQUIRED
authorization_duration=UNTIL_EXPLICITLY_REVOKED_OR_SUPERSEDED
supersedes=PER_TASK_HUMAN_MARKER_REQUIREMENTS
```

### Scope

```text
A0
A1 repository mutation
A1 merge
A2 dry-run runtime
roadmap decisions
issue reconciliation
A3 human authorization after all technical live prerequisites are green
```

### Not lifted conditions

The standing authorization replaces recurring human approvals only. It does
**not** replace any technical gate:

```text
CI_REQUIRED
MERGE_GUARD_REQUIRED
WRITER_LOCK_REQUIRED
BRANCH_PROTECTION_REQUIRED
SNAPSHOT_REQUIRED
CANARY_REQUIRED
ALLOWLIST_REQUIRED
ROLLBACK_REQUIRED
AUDIT_REQUIRED
MEASUREMENT_REQUIRED
RISKGUARD_REQUIRED
KILL_SWITCH_REQUIRED
C4_KEEP_REQUIRED_FOR_LIVE_FLEET_ROLLOUT
RUNTIME_BASELINE_REQUIRED
BREAKGLASS_REQUIRED
REVOCATION_PROOF_REQUIRED
```

### Revocation

Only an explicit newer owner marker deactivates or replaces the standing
authorization:

```text
OWNER_STANDING_AUTHORIZATION_REVOKED
OWNER_STANDING_AUTHORIZATION_SUPERSEDED
```

### Consequence

Missing individual human markers are no longer valid blockers. A1 PRs may be
merged autonomously after green CI and a green merge guard. A2 may run within
an explicit issue scope once all technical guardrails exist. A3 requires no
new individual human confirmation but remains technically fully blocked until
every live prerequisite is green. The standing authorization is not a
technical gate bypass.

## Funding decision (carried)

```text
HUMAN_DECISION_ON_CANONICAL_FUNDING_DATA_CONTRACT
decision=REJECT_INCOMPLETE_FUNDING_FOR_CANONICAL_GATE0_SELECTION
gate0_disposition=EXTEND
selection_backtest_authorized=NO
synthetic_funding=PROHIBITED
funding_rate_zero=PROHIBITED
external_data_mix=PROHIBITED
```

`NO_VALID_SELECTION_BACKTEST_AUTHORIZATION` — no selection backtest may run
on the frozen dataset until a new canonical funding data contract exists.

## Consequences

- `READY_FOR_HUMAN_MERGE` is no longer a terminal state while the standing
  authorization is active. The merge path is:
  `CI_GREEN → MERGE_GUARD_READY → EXACT_HEAD_REVERIFIED → MERGE → POST_MERGE_RECONCILIATION`.
- Per-task human marker searches are discontinued.
- Live trading remains prohibited until C4 KEEP and all technical live
  guardrails are green.

## Related

- Issue #605 (canonical tracker), comment `5179703046`
- Issue #697 (A2 dataset run), comment `5179705029`
- ADR-2026-07-19-canonical-program-governance.md
- ADR-2026-07-19-roadmap-autonomous-merge-controller.md
