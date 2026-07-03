# Operator Approval UX Contract

> **Status:** Ratified
> **Date:** 2026-07-03
> **Issue:** #310-E
> **Purpose:** Define the minimum human review surface before any capital, live-trading, or fleet-rollout discussion.

---

## 1. Required Fields

Every approval document MUST contain these fields:

| Field | Type | Required | Example |
|---|---|---|---|
| `title` | string | ✅ | "Live Canary Rollback Approval" |
| `approval_token` | string | ✅ | `APPROVED_LIVE_CANARY_ROLLBACK` |
| `author` | string | ✅ | "Luke (GoLukeEnviro)" |
| `date_utc` | ISO 8601 | ✅ | "2026-07-03T04:57:00Z" |
| `scope` | string | ✅ | "Rollback freqtrade-freqforge-canary to dry-run mode" |
| `rationale` | string | ✅ | "max_drawdown_pct = 82.79% exceeds critical threshold of 20.0%" |
| `risk_assessment` | string | ✅ | "Low — canary was never activated in live mode" |
| `rollback_plan` | string (path) | ✅ | "var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json" |

## 2. Approval Expiry

| Scope | Default Expiry | Max Expiry |
|---|---|---|
| Read-only audit / report | 30 days | 90 days |
| Config change (dry-run) | 7 days | 14 days |
| Live canary activation | 24 hours | 48 hours |
| Live fleet rollout | 1 hour | 4 hours |
| Emergency override | Immediate | N/A (must be re-evaluated) |

After expiry, the approval is **void**. A new approval document must be created.

## 3. Reviewer Identity

| Field | Required | Description |
|---|---|---|
| GitHub username | ✅ | Must match a known repository collaborator |
| Role | ✅ | "operator", "maintainer", "owner" |
| Verification method | ✅ | GitHub Issue/PR comment, signed commit, or approval marker file |

## 4. Scope Boundaries

Every approval MUST explicitly list:

- **What IS authorized** — specific actions, targets, and duration
- **What is NOT authorized** — explicit exclusions (e.g., "No fleet rollout, no pair expansion, no key deployment")
- **Fail-closed condition** — what happens if the approval is used outside its scope (default: BLOCKED)

## 5. Approval Token Convention

Tokens follow the pattern:

```
APPROVED_<SCOPE>[_<TARGET>]
```

Examples:
- `APPROVED_LIVE_CANARY_TRANSITION`
- `APPROVED_EXECUTE_LIVE_CANARY`
- `APPROVED_LIVE_CANARY_ROLLBACK`
- `APPROVED_LIVE_FLEET_ROLLOUT`
- `APPROVED_RAINBOW_PRODUCER_DEPLOY`
- `APPROVED_RAINBOW_AUTO_START`

Tokens are stored in `docs/decisions/APPROVED_<TOKEN>.md`.

## 6. No-Approval Automation

The following actions MUST NEVER be automated without explicit human approval:

- ❌ Live trading enablement (`dry_run=false`)
- ❌ Exchange key deployment
- ❌ Fleet-wide config changes
- ❌ Strategy promotion
- ❌ Pair expansion
- ❌ Capital allocation changes
- ❌ Auto-restart enablement (cron/systemd)

## 7. Safety Invariants

| Invariant | Enforcement |
|---|---|
| Approval must be explicitly documented | File in `docs/decisions/` |
| Approval must have an expiry | Field in approval document |
| Approval must list scope boundaries | Field in approval document |
| Approval must reference a rollback plan | Field in approval document |
| No auto-approval | Every approval requires a human action (GitHub comment, signed commit, or marker file creation) |
