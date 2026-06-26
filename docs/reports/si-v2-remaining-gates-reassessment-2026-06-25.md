# SI-v2 Remaining Gates Reassessment before Controlled Apply

**Status:** `GREEN`
**Operation Level:** `L2` — read-only evidence assessment plus Markdown report artifact.
**Generated (UTC):** `2026-06-25T03:52:46Z`
**Repository:** `/home/hermes/projects/trading`
**Current branch / HEAD:** `fix/harden-cron-restore-345` @ `6f2feacdcb8057956453fea93462c71fbb47ba06`
**origin/main:** `29f23588fe7ea3bc3653597cfb96335f3dceb531`
**HEAD == origin/main:** `no`
**Tracked worktree status:** no tracked modifications; pre-existing untracked files present
**Scope:** read-only only; no apply token, live trading, config/strategy/Docker/Cron/Guardian/environment mutation, or destructive git command.

> Preflight note: the persisted cycle artifacts used below were generated on commit `3b204ed` for cycle `20260625T001707Z`. The current repo HEAD is different; this reassessment treats the persisted artifacts as the source of truth and performs no mutations.

---

## 1. Repo Preflight

| Check | Result |
|---|---|
| current branch | `fix/harden-cron-restore-345` |
| `HEAD` | `6f2feacdcb8057956453fea93462c71fbb47ba06` |
| `origin/main` | `29f23588fe7ea3bc3653597cfb96335f3dceb531` |
| `HEAD == origin/main` | `no` |
| tracked worktree | clean for tracked files; untracked files present |

---

## 2. Evidence Files Used

| Evidence source | Path | Why it matters |
|---|---|---|
| Current operational state | `docs/state/current-operational-state.md` | Canonical posture, controller state, and safety policy |
| P3 Scheduler Continuity Proof | `docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md` | 24h scheduled continuity proof, 4/4 GREEN |
| Post-PR341 Active Cycle Proof | `docs/reports/si-v2-active-cycle-proof-post-pr341-2026-06-24.md` | Historical wiring baseline for the Active Cycle evidence shape |
| Current Active Cycle runner report | `self_improvement_v2/reports/phase2/active_cycle_runner_report.md` | Current cycle summary for `20260625T001707Z` |
| Latest Active Cycle evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260625T001707Z.json` | Primary per-bot gate facts, profitability gate, RiskGuard, ShadowLogger |
| Latest Active Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260625T001707Z.state.json` | Controller state and mutation counters |
| Measurement summary | `self_improvement_v2/reports/phase2/measurement/measurement_summary.json` | Current attribution/measurement totals, secrets/mutations checks |
| Historical trade summary | `self_improvement_v2/state/historical_trades/historical_trades_summary.json` | Fleet-level historical trade import/coverage totals |

---

## 3. Current Evidence Snapshot

| Item | Value |
|---|---|
| Current cycle id | `20260625T001707Z` |
| Current cycle branch / commit | `fix/harden-cron-restore-345` @ `3b204ed` |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |
| Fleet verdict in cycle state | `GREEN` |
| Fleet verdict reason | all 4 bots authenticated and decisions generated |
| Active bots processed | `4 / 4` |
| Ping OK | `4 / 4` |
| Authenticated | `4 / 4` |
| ShadowProposals generated | `4 / 4` |
| Mutation counters | `runtime=0`, `config=0`, `strategy=0`, `docker=0`, `live_trading=0` |
| Historical trade window status | `OK` |
| Historical trade primary verdict | `WAITING_FOR_POST_APPLY_DATA` |
| Historical trade candidate id | `65502d13` |
| Historical trade full window | `210` trades, `1` open trade, fleet PF `1.369661`, sum close profit `23.13215238` |
| Measurement build timestamp | `2026-06-25T00:17:07.799912+00:00` |
| Measurement mutations_all_zero | `true` |
| Measurement secrets_found | `false` |
| Attribution windows | `141` |
| Proposal records | `141` |
| Cycles scanned in measurement summary | `60` |
| Historical trades imported | `210` |
| Historical trades closed | `209` |
| Historical trades open | `1` |
| Scheduler continuity proof | `GREEN` — 4/4 scheduled cycles GREEN over 24h |
| Latest cycle freshness | still GREEN; latest cycle evidence remains continuous and read-only |

Interpretation: the evidence lane is current, the scheduler remains continuous, and the current cycle is consistent with the post-PR341 evidence shape.

---

## 4. Per-Bot Gate Matrix

| Bot | Present | Ping/Auth | Historical trade window | Historical summary | Telemetry evidence_window | ShadowProposal | Walk-forward verdict | Profitability gate verdict | Approval eligibility | RiskGuard | ShadowLogger | Mutations zero | Apply actuator | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `freqtrade-freqforge` | yes | `OK / AUTHENTICATED / 200` | `OK` | yes | preserved | yes (`b52975eefc17e525`) | `PASS_REVIEW` (`+24.78409503`, PF `1.5831`) | `candidate` | `true` / `PENDING_HUMAN` | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | not observed | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-freqforge-canary` | yes | `OK / AUTHENTICATED / 200` | `OK` | yes | preserved | yes (`8c87c0e21b7b1469`) | `PASS_REVIEW` (`+3.97978314`, PF `1.8824`) | `candidate` | `true` / `PENDING_HUMAN` | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | not observed | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-regime-hybrid` | yes | `OK / AUTHENTICATED / 200` | `OK` | yes | preserved | yes (`56d2d20e7e035e51`) | `NEGATIVE_NET_METRICS` (`-7.24804077`, PF `0.5760`) | `blocked` | `false` / `PENDING_HUMAN` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | not observed | `APPLY_BLOCKED` |
| `freqai-rebel` | yes | `OK / AUTHENTICATED / 200` | `OK` | yes | preserved | yes (`950cbdfa01018951`) | `NEGATIVE_NET_METRICS` (`-0.52005489`, PF `0.5407`) | `blocked` | `false` / `PENDING_HUMAN` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | not observed | `APPLY_BLOCKED` |

### Notes on the matrix

- `historical trade window` is `OK` for the fleet, but its primary verdict is still `WAITING_FOR_POST_APPLY_DATA` because no apply has happened yet.
- `apply actuator` is not observed in the bundle/state, and the controller remains `PAUSED / L3_REPOSITORY_ONLY`.
- The two positive proposals are legitimate candidates under current safety rules, but they still require explicit human approval.
- The two negative proposals fail the profitability gate on walk-forward metrics.

---

## 5. Exact Blocker List

### Fleet-level blockers

1. **Profitability gate block**
   - `profitability_gate.verdict = blocked`
   - blocked because `freqtrade-regime-hybrid` and `freqai-rebel` are blocked
   - fleet summary: `2` candidate / `2` blocked

2. **Approval state mismatch**
   - the two profitable proposals are still `PENDING_HUMAN`
   - no approval token is in scope for this reassessment
   - therefore they are candidates, not executable apply actions

3. **Missing post-apply data (expected, not a current blocker for candidate classification)**
   - `historical_trade_window.primary_verdict = WAITING_FOR_POST_APPLY_DATA`
   - `post_apply.closed_trades = 0`
   - this lane is empty because no apply has occurred yet; it is evidence of absence, not a runtime fault

4. **Controlled Apply out of scope**
   - no approval token was requested or used
   - no apply actuator path was invoked
   - controller remains `PAUSED / L3_REPOSITORY_ONLY`

### Explicitly not blocking this reassessment

- **Insufficient scheduled continuity:** not blocking; P3 proof is GREEN and the latest cycle is GREEN.
- **Stale evidence:** not blocking; the current cycle evidence and measurement build are current.
- **Missing attribution:** not blocking; measurement summary shows `141` attribution windows and `141` proposal records.
- **Safety gate block:** not blocking beyond normal shadow-only posture; RiskGuard is `PASS_SHADOW_ONLY` and ShadowLogger is `LOGGED` for all 4 bots.

### Per-bot block reasons

- `freqtrade-freqforge`
  - no metric block
  - apply remains blocked only by **approval state mismatch** (`PENDING_HUMAN`)

- `freqtrade-freqforge-canary`
  - no metric block
  - apply remains blocked only by **approval state mismatch** (`PENDING_HUMAN`)

- `freqtrade-regime-hybrid`
  - **negative net metrics** (`-7.24804077`, PF `0.5760`)
  - **profitability gate block**
  - **approval state mismatch** (`approval_eligible=false`)

- `freqai-rebel`
  - **negative net metrics** (`-0.52005489`, PF `0.5407`)
  - **profitability gate block**
  - **approval state mismatch** (`approval_eligible=false`)

---

## 6. Verdict

```text
Evidence health:        GREEN
Scheduler continuity:   GREEN
Historical evidence:    GREEN
Mutation safety:        GREEN
ShadowProposal output:  GREEN
Per-bot outcomes:       2 candidate / 2 blocked
Fleet-level verdict:    GREEN_WITH_HUMAN_APPROVAL_REQUIRED
Controlled Apply:       APPLY_BLOCKED
```

### Decision summary

- `freqtrade-freqforge` and `freqtrade-freqforge-canary` are valid apply candidates under the current safety rules, but they still require explicit human approval.
- `freqtrade-regime-hybrid` and `freqai-rebel` are blocked by negative net metrics and therefore fail the profitability gate.
- Because the profitability gate remains blocked at fleet level, Controlled Apply remains blocked.

---

## 7. Next Recommended Single Action

**Wait for the next naturally scheduled SI-v2 cycle and rerun this same read-only gate matrix against the newest active-cycle evidence bundle.**

Do not request or use an approval token yet.

---

## 8. Safety Confirmation

- No proposal was applied.
- No approval token was used, requested, exported, or persisted.
- No live trading was enabled.
- No `dry_run=false` change was made.
- No runtime, config, strategy, Docker, Cron, Guardian, or environment mutation was performed.
- No destructive git command was used.
- No secrets were printed or exposed.
- `apply actuator not invoked` is supported by the absence of apply fields in the bundle/state and the paused controller state.

---

## 9. Report Reference

`docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md`
