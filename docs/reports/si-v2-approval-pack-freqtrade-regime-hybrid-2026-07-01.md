# SI-v2 Approval Pack — freqtrade-regime-hybrid

- Timestamp UTC: 2026-07-01T08:41:03.973409+00:00
- Operation Level: L2
- Mutation status: none

## Candidate

| Field | Value |
|-------|-------|
| bot_id | `freqtrade-regime-hybrid` |
| candidate_sha256 | `9658ccc051ef03a5` |
| hypothesis | `observe_underperforming_pair_cluster_v1` |
| decision_type | `SHADOW_PROPOSAL` |
| approval_status | `PENDING_HUMAN` |
| approval_eligible | true |
| source cycle | `20260701T061755Z` |

## Approval Decision

| Field | Value |
|-------|-------|
| Decision | **SELECTED_FOR_HUMAN_REVIEW** |
| Apply Approval | **NOT_APPROVED** |
| Reason | best eligible observability candidate, but not canary-first |

## Required-Before-Apply Checklist

| Criterion | Status | Note |
|-----------|--------|------|
| Qualified candidate | ✅ | `freqtrade-regime-hybrid` / `observe_underperforming_pair_cluster_v1` |
| Allowlist-compatible | ✅ | observability-only, no trading mutation |
| Canary-first | ❌ | **regime-hybrid is not a canary** — blocks apply |
| dry_run=true | ✅ | fleet-wide confirmed |
| Kill switch NORMAL | ✅ | confirmed |
| Rollback snapshot path | ⏳ | not prepared (apply not approved) |
| Human approval token | ❌ | not issued |
| No conflicting measurement window | ✅ | measurement window closed (KEEP_CANARY_OVERLAY) |

## Allowed Next Action

- Prepare this approval pack only
- No apply
- No restart
- No rollback
- No watcher enablement
- No jobs.json change
- No Docker/Compose mutation
- No live trading

## Next Step

For a real apply, a separate human approval step is required.

This document does not define or issue an approval token. The candidate hash is evidence identity only, not an execution credential.

The apply path must be canary-first or demonstrably contain no runtime/bot mutation. Any runtime actuator approval must use the implemented SI-v2 actuator gate from code, not a report-defined token name.
