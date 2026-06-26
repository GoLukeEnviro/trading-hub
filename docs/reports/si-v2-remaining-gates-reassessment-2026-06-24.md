# SI-v2 Remaining Gates Reassessment before Controlled Apply

**Status:** `GREEN_WITH_HUMAN_APPROVAL_REQUIRED` for per-bot evidence completeness; `CONTROLLED_APPLY_BLOCKED` at fleet level.
**Operation Level:** `L2` — read-only evidence assessment plus this Markdown report.
**Generated (UTC):** `2026-06-24T20:38:51Z`
**Repository:** `/home/hermes/projects/trading`
**Branch / HEAD:** `main` @ `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71`
**Scope:** no apply, no approval token, no runtime/config/strategy/Docker/Cron/Guardian/environment mutation, no live trading.

---

## 1. Repo Preflight

| Check | Result |
|---|---|
| current branch | `main` |
| `HEAD` | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| `origin/main` after fetch | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| `HEAD == origin/main` | `yes` |
| tracked worktree status before report | clean (`tracked_dirty_count=0`; pre-existing untracked files left untouched) |

---

## 2. Evidence Files Used

| Evidence source | Path / value |
|---|---|
| Current operational state | `docs/state/current-operational-state.md` |
| Post-PR341 proof report | `docs/reports/si-v2-active-cycle-proof-post-pr341-2026-06-24.md` |
| Root-instruction alignment context | `docs/context/2026-06-24-root-agent-instructions-si-v2-loop-alignment.md` |
| P3 Scheduler Continuity Proof | `docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md` |
| Latest Active Cycle evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260624T181701Z.json` |
| Latest Active Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260624T181701Z.state.json` |
| Latest scheduled cycle log | `/opt/data/logs/si-v2-active-cycle/cycle-20260624T181700Z.log` |
| Measurement summary | `self_improvement_v2/reports/phase2/measurement/measurement_summary.json` |
| Attribution report | `self_improvement_v2/reports/phase2/measurement/attribution_report.md` |
| Shadow logs | `self_improvement_v2/reports/phase2/shadow_logs/shadow_<bot>.jsonl` |

The P3 report established 4/4 scheduled cycles GREEN over the audited 24h window. A newer scheduled cycle, `20260624T181701Z`, is also GREEN and is used as the latest per-bot gate matrix source.

---

## 3. Scheduler / Continuity Gate

| Cycle ID | Fleet verdict | Ping OK | ShadowProposals | Historical window | Profitability gate | Mutations | Branch |
|---|---|---:|---:|---|---|---|---|
| `20260623T181740Z` | `GREEN` | `4/4` | `4` | pre-PR341 / not required for this reassessment | `blocked` | all `0` | `main` |
| `20260624T002122Z` | `GREEN` | `4/4` | `4` | `OK` | `blocked` | all `0` | `feat/si-v2-active-cycle-historical-evidence` |
| `20260624T061755Z` | `GREEN` | `4/4` | `4` | `OK` | `blocked` | all `0` | `main` |
| `20260624T121756Z` | `GREEN` | `4/4` | `4` | `OK` | `blocked` | all `0` | `docs/align-root-agent-instructions-si-v2-342` |
| `20260624T181701Z` | `GREEN` | `4/4` | `4` | `OK` | `blocked` | all `0` | `main` |

Scheduler continuity is not the current blocker. The latest scheduled cycle also runs on `main` at `0cf5a4d`.

---

## 4. Fleet-Level Gate State

| Gate | Result | Evidence |
|---|---|---|
| Active bot identities | `OK` — all 4 canonical bots present | latest evidence `bots[]` |
| Ping/auth | `OK` — `4/4`, all `AUTHENTICATED` | latest evidence + latest cycle log |
| Historical evidence | `OK` — `historical_trade_window.status=OK` | latest evidence |
| Historical primary verdict | `WAITING_FOR_POST_APPLY_DATA` | latest evidence; expected because no apply occurred |
| Telemetry preservation | `OK` — per-bot `evidence_window` preserved | latest evidence `per_bot_decisions[]` |
| ShadowProposals | `OK` — 4 generated | latest state/log |
| RiskGuard | `PASS_SHADOW_ONLY` for all 4 | latest `safety_results[]` |
| ShadowLogger | `LOGGED` for all 4 | latest `safety_results[]`, shadow logs |
| Mutation safety | `OK` — runtime/config/strategy/Docker/live-trading all `0` | latest state/log |
| Measurement ledger | `OK` — `mutations_all_zero=True`, `secrets_found=False` | `measurement_summary.json` |
| Profitability gate | `blocked` | latest evidence `profitability_gate.verdict` |
| Apply actuator | not invoked | no apply/actuator state fields; no token; mutation counters all `0` |

### Profitability gate summary

| Field | Value |
|---|---:|
| fleet verdict | `blocked` |
| candidate bots | `2` |
| blocked bots | `2` |
| inconclusive bots | `0` |
| fleet net PnL | `20.47289845` |
| fleet profit factor | `3.4693` |
| max drawdown pct | `2.1074` |
| total trades | `211` |
| reason | `blocked_bots: freqtrade-regime-hybrid, freqai-rebel` |

Controlled Apply remains blocked at fleet level because the profitability gate is still `blocked`.

---

## 5. Per-Bot Gate Matrix

| Bot | Present | Ping/Auth | Hist. summary | Telemetry | ShadowProposal | Walk-forward | Profit gate | Approval | RiskGuard / ShadowLogger | Mutations | Apply actuator | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `freqtrade-freqforge` | yes | OK / `AUTHENTICATED` | `OK` | preserved | yes (`c92a9007fcb7a340`) | `PASS_REVIEW`, PnL `24.78409503`, PF `1.583109`, trades `78` | `candidate` | `PENDING_HUMAN`, eligible `true` | `PASS_SHADOW_ONLY` / `LOGGED` | all `0` | no | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-freqforge-canary` | yes | OK / `AUTHENTICATED` | `OK` | preserved | yes (`90a6831c162d7cd8`) | `PASS_REVIEW`, PnL `3.97978314`, PF `1.882368`, trades `59` | `candidate` | `PENDING_HUMAN`, eligible `true` | `PASS_SHADOW_ONLY` / `LOGGED` | all `0` | no | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-regime-hybrid` | yes | OK / `AUTHENTICATED` | `OK` | preserved | yes (`4536b648d5fb4914`) | `NEGATIVE_NET_METRICS`, PnL `-7.24804077`, PF `0.576016`, trades `55` | `blocked` | `PENDING_HUMAN`, eligible `false` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` / `LOGGED` | all `0` | no | `APPLY_BLOCKED` |
| `freqai-rebel` | yes | OK / `AUTHENTICATED` | `OK` | preserved | yes (`86349581dd8f000c`) | `NEGATIVE_NET_METRICS`, PnL `-1.04293895`, PF `0.074723`, trades `19` | `blocked` | `PENDING_HUMAN`, eligible `false` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` / `LOGGED` | all `0` | no | `APPLY_BLOCKED` |

### Important proposal-quality note

All four latest ShadowProposals are `base_mode=proposal_only`, `requires_human_approval=true`, `mutation_policy=safe_parameter_overlay_only`, and currently carry `parameters={}` with metadata-only candidate fields. Therefore even the two per-bot candidates are not a token-ready runtime action. They are candidates for human review/reconciliation, not apply instructions.

---

## 6. Block Reasons

### Fleet-level blockers

1. `profitability_gate_block`: fleet profitability gate verdict is `blocked` because `freqtrade-regime-hybrid` and `freqai-rebel` are blocked.
2. `controlled_apply_out_of_scope`: no approval token was supplied or requested; Controlled Apply is explicitly out of scope.
3. `controller_paused_repository_only`: controller state remains `PAUSED / L3_REPOSITORY_ONLY`.
4. `post_apply_data_absent_expected`: `historical_trade_window.primary_verdict=WAITING_FOR_POST_APPLY_DATA` and per-bot `post_apply.closed_trades=0`; this is expected before any apply and prevents post-apply performance claims.
5. `metadata_only_empty_parameters`: current ShadowProposals contain metadata-only candidates with `parameters={}`; a future apply discussion must reconcile a concrete safe overlay proposal before any token discussion.

### Per-bot blockers

| Bot | Block reasons |
|---|---|
| `freqtrade-freqforge` | no per-bot metric block; still `PENDING_HUMAN`; post-apply data absent by design; metadata-only/empty parameters must be reconciled before any runtime action |
| `freqtrade-freqforge-canary` | no per-bot metric block; still `PENDING_HUMAN`; post-apply data absent by design; metadata-only/empty parameters must be reconciled before any runtime action |
| `freqtrade-regime-hybrid` | `NEGATIVE_NET_METRICS`, `approval_negative_net_metrics`, profitability bot verdict `blocked` |
| `freqai-rebel` | `NEGATIVE_NET_METRICS`, `approval_negative_net_metrics`, profitability bot verdict `blocked` |

No scheduler-continuity blocker, no historical-evidence blocker, no telemetry-preservation blocker, no RiskGuard/ShadowLogger evidence blocker, and no mutation-safety blocker were found.

---

## 7. Fleet-Level Verdict

```text
Evidence health:        GREEN
Scheduler continuity:   GREEN
Historical evidence:    GREEN
ShadowProposal output:  GREEN
Mutation safety:        GREEN
Per-bot candidates:     2 candidate / 2 blocked
Human approval state:   required for all proposals; not provided
Profitability gate:     BLOCKED at fleet level
Controlled Apply:       APPLY_BLOCKED
```

Decision-rule application:

- Required safety/evidence gates are present, so the fleet is not RED.
- Evidence is complete enough for a remaining-gates decision, so the fleet is not YELLOW for missing evidence.
- Two proposals are per-bot candidates and still require human approval, so the candidate state is `GREEN_WITH_HUMAN_APPROVAL_REQUIRED`.
- Because the fleet-level profitability gate remains `blocked`, Controlled Apply remains `APPLY_BLOCKED`.

---

## 8. Next Recommended Single Action

Do **not** request an approval token and do **not** run Controlled Apply.

Next single action: create a focused read-only follow-up that converts the two candidate ShadowProposals (`freqtrade-freqforge`, `freqtrade-freqforge-canary`) from metadata-only evidence into a concrete, reviewable safe-parameter-overlay candidate package, while separately documenting why `freqtrade-regime-hybrid` and `freqai-rebel` remain blocked by negative net metrics.

Only after that package exists and the fleet-level profitability gate is no longer blocked should a Controlled-Apply discussion be reopened.

---

## 9. Safety Confirmation

- No proposal was applied.
- No approval token was used, requested, exported, or persisted.
- No live trading was enabled.
- No `dry_run=false` change was made.
- No Docker, Compose, Cron, Guardian, Freqtrade config, strategy, environment, scheduler, or runtime mutation was performed.
- No PR #311 or PR #330 action was taken.
- No cleanup or destructive git command was run.
