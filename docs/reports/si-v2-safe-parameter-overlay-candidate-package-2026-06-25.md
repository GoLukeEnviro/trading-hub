# SI-v2 Safe-Parameter-Overlay Candidate Package for 2/4 Approval-Eligible Bots

**Status:** `GREEN_WITH_HUMAN_APPROVAL_REQUIRED` / `CONTROLLED_APPLY_BLOCKED`  
**Operation Level:** `L2` — read-only evidence assessment, Markdown report artifact only.  
**Generated (UTC):** `2026-06-25T12:05:00Z`  
**Repository:** `/home/hermes/projects/trading`  
**Current branch / HEAD:** `main` @ `f5b138545d881584a95d6b538972f21a8fb1d37d`  
**origin/main:** `f5b138545d881584a95d6b538972f21a8fb1d37d`  
**HEAD == origin/main:** `yes`  

> This report is read-only. No approval token was requested, exported, or used. No runtime, config, strategy, Docker, Cron, Guardian, or live-trading mutation was performed. No files were written to runtime mounts. The parameter overlays below are **read-only drafts** for human review, not applied overlays.

---

## 1. Purpose

Produce a complete, read-only apply-decision package for the two approval-eligible bots from the latest valid Active Cycle evidence, and document the two blocked bots with their negative-metric reasons. Controlled Apply remains blocked because the fleet-level profitability gate is still `blocked`.

---

## 2. Evidence Files Used

| Evidence source | Path | SHA-256 |
|---|---|---|
| Current operational state | `docs/state/current-operational-state.md` | `57e85fafa11a237888a7e3e84130ea9dab122348861e18a9c68a140cd487a98b` |
| P3 Scheduler Continuity Proof | `docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md` | `dc0c2bf18391b643d173347ab7fd012641c1eb171ea02cefb7bd28ef3a0693fe` |
| Post-PR341 Active Cycle Proof | `docs/reports/si-v2-active-cycle-proof-post-pr341-2026-06-24.md` | `e5c92029dc1b83abf42a89f738c4201f456f20eaea1319033d2aaba2299e8814` |
| Remaining Gates Reassessment | `docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md` | `455ead248d8cebd40cbcc7093494c1fe2e3c61525d68babc2dbad166a9e6a390` |
| Latest Active Cycle evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260625T001707Z.json` | `ce4946078aca92db18567d21776b84ff40db85615c925366485c04f8c92cd107` |
| Latest Active Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260625T001707Z.state.json` | `f6ddf0c12107be02a7fa3ee05bc9e7f3d4a4d378a1a9cc34c4da8e0aba534742` |
| Historical trade summary | `self_improvement_v2/state/historical_trades/historical_trades_summary.json` | (current store snapshot used for totals) |

All evidence is from the scheduled cycle `20260625T001707Z`, recorded on branch `fix/harden-cron-restore-345` @ `3b204ed`. The evidence bundle is treated as the source of truth; the report is written after `main` was updated to include PR #346 (restore hardening).

---

## 3. Fleet-Level Gate Snapshot

| Item | Value |
|---|---|
| Cycle id | `20260625T001707Z` |
| Controller state | `PAUSED / L3_REPOSITORY_ONLY` |
| Fleet verdict | `GREEN` |
| Active bots processed | `4 / 4` |
| Ping OK | `4 / 4` |
| Authenticated | `4 / 4` |
| ShadowProposals generated | `4 / 4` |
| Approval eligible | `2 / 4` |
| Mutation counters | `runtime=0`, `config=0`, `strategy=0`, `docker=0`, `live_trading=0` |
| Historical trade window status | `OK` |
| Historical trade primary verdict | `WAITING_FOR_POST_APPLY_DATA` |
| Historical trade candidate id | `65502d13` |
| Profitability gate verdict | `blocked` |
| Controlled Apply | `APPLY_BLOCKED` |

---

## 4. Per-Bot Gate Matrix

| Bot | Present | Ping/Auth | Historical window | ShadowProposal | Walk-forward verdict | Profitability gate | Approval eligible | Approval status | RiskGuard | ShadowLogger | Mutations zero | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `freqtrade-freqforge` | yes | `OK / AUTHENTICATED / 200` | `OK` | `b52975eefc17e525` | `PASS_REVIEW` (+24.78, PF 1.5831) | `candidate` | `true` | `PENDING_HUMAN` | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-freqforge-canary` | yes | `OK / AUTHENTICATED / 200` | `OK` | `8c87c0e21b7b1469` | `PASS_REVIEW` (+3.98, PF 1.8824) | `candidate` | `true` | `PENDING_HUMAN` | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-regime-hybrid` | yes | `OK / AUTHENTICATED / 200` | `OK` | `56d2d20e7e035e51` | `NEGATIVE_NET_METRICS` (−7.25, PF 0.5760) | `blocked` | `false` | `PENDING_HUMAN` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | `APPLY_BLOCKED` |
| `freqai-rebel` | yes | `OK / AUTHENTICATED / 200` | `OK` | `950cbdfa01018951` | `NEGATIVE_NET_METRICS` (−0.52, PF 0.5407) | `blocked` | `false` | `PENDING_HUMAN` (`approval_negative_net_metrics`) | `PASS_SHADOW_ONLY` | `LOGGED` | `0` | `APPLY_BLOCKED` |

---

## 5. Candidate Package — `freqtrade-freqforge`

| Field | Value |
|---|---|
| `bot_id` | `freqtrade-freqforge` |
| `candidate_sha256` | `b52975eefc17e525` |
| `hypothesis` | `reinforce_profitable_pair_cluster_v1` |
| `mutation_policy` | `safe_parameter_overlay_only` |
| `decision_type` | `SHADOW_PROPOSAL` |
| `base_mode` | `proposal_only` |

### Evidence bundle reference

| Field | Value |
|---|---|
| Evidence bundle path | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260625T001707Z.json` |
| Evidence bundle SHA-256 | `ce4946078aca92db18567d21776b84ff40db85615c925366485c04f8c92cd107` |
| Cycle state path | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260625T001707Z.state.json` |
| Cycle state SHA-256 | `f6ddf0c12107be02a7fa3ee05bc9e7f3d4a4d378a1a9cc34c4da8e0aba534742` |
| Historical window | `full`, `post_apply`, `pre_apply` present; primary verdict `WAITING_FOR_POST_APPLY_DATA` |
| Historical candidate id | `65502d13` |

### Walk-forward / profitability metrics

| Metric | Value |
|---|---|
| `evaluation_status` | `PASS_REVIEW` |
| `metrics_source` | `real` |
| `total_net_pnl` | `+24.78409503` |
| `profit_factor` | `1.5831090594239663` |
| `total_trades` | `78` |
| `max_drawdown_pct` | `2.1073916084371036` |
| `win_rate_pct` | `0.0` (not computed from source) |
| `total_fees` | `0.0` |
| `total_funding` | `0.0` |
| `total_slippage` | `0.0` |

### Historical summary (from `historical_trades_summary.json`)

| Metric | Value |
|---|---|
| `closed_trades` | `78` |
| `wins` | `62` |
| `losses` | `16` |
| `sum_close_profit_abs` | `24.78409503` |
| `newest_close_date` | `2026-06-23 06:20:47.000000` |
| `open_trades` | `0` |

### Approval status

| Field | Value |
|---|---|
| `approval_eligible` | `true` |
| `requires_human_approval` | `true` |
| `approval_status` | `PENDING_HUMAN` |
| `approval_reason_codes` | `[]` |
| `promotion_blocked` | `false` |
| `promotion_block_reason_codes` | `[]` |

### Read-only parameter-overlay draft

> **Important:** The evidence bundle shows `parameters: {}` and `expected_new_values: null` for this proposal. The candidate is therefore **metadata-only** at this stage. The overlay below is an **illustrative read-only draft** derived from the hypothesis name for human reconciliation. It must not be written to a runtime mount without a separate payload-design step and explicit L3 approval.

```json
{
  "pairlist_config": {
    "method": "StaticPairList",
    "pairs": ["SOL/USDT:USDT", "ETH/USDT:USDT", "ARB/USDT:USDT", "BTC/USDT:USDT"]
  },
  "max_open_trades": 4,
  "stake_amount": "unlimited",
  "dry_run": true,
  "___hypothesis": "reinforce_profitable_pair_cluster_v1",
  "___candidate_sha256": "b52975eefc17e525",
  "___target_bot": "freqtrade-freqforge"
}
```

*Draft note:* The pair list is inferred from the top-performing pairs in the walk-forward window. The actual overlay must be reconciled against the current base config (`/freqtrade/user_data/config.json` inside the container) and the approved parameter payload before any runtime proof or apply.

### Expected apply gates

| Gate | Required value before apply |
|---|---|
| `approval_status` | `APPROVED` by explicit human decision |
| `approval_eligible` | `true` |
| `profitability_gate.bot_verdict` | `candidate` |
| `walk_forward_net_metrics.evaluation_status` | `PASS_REVIEW` |
| `mutation_policy` | `safe_parameter_overlay_only` |
| `dry_run` preserved | `true` in overlay and merged config |
| `RuntimeEffectProof.proof_status` | `GREEN` (API or composite) |
| `RuntimeEffectProof.proof_method` | `api`, `api_plus_merged_missing_keys`, or `merged_fallback` |
| `ControlledApplyResult.mode` | `ACTUATOR_VERIFIED` |
| Mutation counter increment | Only after proof is GREEN |

### Rollback requirement

| Field | Value |
|---|---|
| Rollback trigger | Any of: proof RED, controlled apply not `ACTUATOR_VERIFIED`, overlay not visible in process cmdline, `dry_run` missing in merged config, live-trading flag drift, measurement abort condition met. |
| Rollback action | Remove the overlay file from the bind-mounted config directory; restart the bot only if the reload token `APPROVE_SI_V2_FREQFORGE_RELOAD_<candidate>` is present; otherwise escalate. |
| Rollback evidence | Capture `show_config` diff before/after, process cmdline before/after, and mutation-record artifact. |
| Rollback safety | Never broad `docker compose up -d`; targeted reload or overlay removal only. |

### Measurement start condition

Measurement may be registered **only** after:

1. Human approval recorded.
2. Parameter payload reconciled (non-empty `parameters` and `expected_new_values`).
3. Runtime composite proof GREEN.
4. Controlled apply returns `ACTUATOR_VERIFIED`.
5. Mutation-record artifact written to the evidence directory.

Measurement #1 is the next scheduled SI-v2 active cycle after apply. Measurement #2 is the following cycle.

---

## 6. Candidate Package — `freqtrade-freqforge-canary`

| Field | Value |
|---|---|
| `bot_id` | `freqtrade-freqforge-canary` |
| `candidate_sha256` | `8c87c0e21b7b1469` |
| `hypothesis` | `reinforce_profitable_pair_cluster_v1` |
| `mutation_policy` | `safe_parameter_overlay_only` |
| `decision_type` | `SHADOW_PROPOSAL` |
| `base_mode` | `proposal_only` |

### Evidence bundle reference

Same bundle/state files and hashes as §5.

### Walk-forward / profitability metrics

| Metric | Value |
|---|---|
| `evaluation_status` | `PASS_REVIEW` |
| `metrics_source` | `real` |
| `total_net_pnl` | `+3.97978314` |
| `profit_factor` | `1.8823683297309348` |
| `total_trades` | `59` |
| `max_drawdown_pct` | `0.757621510842902` |
| `win_rate_pct` | `0.0` |
| `total_fees` | `0.0` |
| `total_funding` | `0.0` |
| `total_slippage` | `0.0` |

### Historical summary (from `historical_trades_summary.json`)

| Metric | Value |
|---|---|
| `closed_trades` | `58` |
| `wins` | `53` |
| `losses` | `5` |
| `sum_close_profit_abs` | `6.22192711` |
| `newest_close_date` | `2026-06-23 06:18:37.068000` |
| `open_trades` | `1` |

### Approval status

| Field | Value |
|---|---|
| `approval_eligible` | `true` |
| `requires_human_approval` | `true` |
| `approval_status` | `PENDING_HUMAN` |
| `approval_reason_codes` | `[]` |
| `promotion_blocked` | `false` |
| `promotion_block_reason_codes` | `[]` |

### Read-only parameter-overlay draft

> Same metadata-only warning as §5: `parameters: {}` and `expected_new_values: null`. The overlay below is illustrative only.

```json
{
  "pairlist_config": {
    "method": "StaticPairList",
    "pairs": ["SOL/USDT:USDT", "ETH/USDT:USDT", "BTC/USDT:USDT"]
  },
  "max_open_trades": 3,
  "stake_amount": "unlimited",
  "dry_run": true,
  "___hypothesis": "reinforce_profitable_pair_cluster_v1",
  "___candidate_sha256": "8c87c0e21b7b1469",
  "___target_bot": "freqtrade-freqforge-canary"
}
```

### Expected apply gates

Same as §5, with the canary-specific reload token `APPROVE_SI_V2_FREQFORGE_CANARY_RELOAD_<candidate>` if a reload becomes necessary.

### Rollback requirement

Same pattern as §5, scoped to the canary container and canary bind-mounted config directory.

### Measurement start condition

Same as §5. The canary should be measured independently from the main FreqForge bot to preserve the canary/baseline comparison.

---

## 7. Blocked-Bot Documentation — `freqtrade-regime-hybrid`

| Field | Value |
|---|---|
| `bot_id` | `freqtrade-regime-hybrid` |
| `candidate_sha256` | `56d2d20e7e035e51` |
| `hypothesis` | `observe_underperforming_pair_cluster_v1` |
| `mutation_policy` | `safe_parameter_overlay_only` |
| `decision_type` | `SHADOW_PROPOSAL` |

### Block reasons

1. **Negative net metrics** — `total_net_pnl = -7.24804077`, `profit_factor = 0.576015973817196`.
2. **Profitability gate bot verdict = `blocked`**.
3. **`approval_eligible = false`** with reason code `approval_negative_net_metrics`.
4. **Fleet-level profitability gate blocked** — even if this bot were fixed, the fleet gate would need to turn `candidate` or `green`.

### Relevant negative metrics

| Metric | Value |
|---|---|
| `evaluation_status` | `NEGATIVE_NET_METRICS` |
| `total_net_pnl` | `−7.24804077` |
| `profit_factor` | `0.576015973817196` |
| `total_trades` | `55` |
| `max_drawdown_pct` | `0.7655838879347948` |
| `walk_forward_net_metrics.promotion_blocked` | `true` |
| `walk_forward_net_metrics.promotion_block_reason_codes` | `["walk_forward_net_metrics_negative"]` |

### Why no apply package is produced

The bot fails the profitability gate and is not approval-eligible. Generating an apply package would be a false positive and would violate the rule that the profitability gate must be `candidate` or better before an overlay is considered for controlled apply.

### Data required for reconsideration

| Item | Needed to unblock |
|---|---|
| Durable positive walk-forward window | At least one subsequent cycle with `evaluation_status == PASS_REVIEW`, `profit_factor > 1.0`, and positive `total_net_pnl`. |
| Historical evidence stability | Per-bot `historical_trade_summary` remains `OK` and the new positive window is statistically significant (e.g. ≥30 trades or clear trend reversal). |
| Pair/cluster diagnostics | Which pairs drive losses; whether regime-detector settings need adjustment. |
| RiskGuard re-evaluation | Must remain `PASS_SHADOW_ONLY` or better, with no new block reason codes. |

---

## 8. Blocked-Bot Documentation — `freqai-rebel`

| Field | Value |
|---|---|
| `bot_id` | `freqai-rebel` |
| `candidate_sha256` | `950cbdfa01018951` |
| `hypothesis` | `observe_underperforming_pair_cluster_v1` |
| `mutation_policy` | `safe_parameter_overlay_only` |
| `decision_type` | `SHADOW_PROPOSAL` |

### Block reasons

1. **Negative net metrics** — `total_net_pnl = -0.52005489`, `profit_factor = 0.5406697698685771`.
2. **Profitability gate bot verdict = `blocked`**.
3. **`approval_eligible = false`** with reason code `approval_negative_net_metrics`.
4. **Fleet-level profitability gate blocked**.

### Relevant negative metrics

| Metric | Value |
|---|---|
| `evaluation_status` | `NEGATIVE_NET_METRICS` |
| `total_net_pnl` | `−0.52005489` |
| `profit_factor` | `0.5406697698685771` |
| `total_trades` | `22` |
| `max_drawdown_pct` | `0.1109716880276453` |
| `walk_forward_net_metrics.promotion_blocked` | `true` |
| `walk_forward_net_metrics.promotion_block_reason_codes` | `["walk_forward_net_metrics_negative"]` |

### Why no apply package is produced

Same as §7: negative net metrics make the proposal ineligible for approval. No overlay draft is produced.

### Data required for reconsideration

| Item | Needed to unblock |
|---|---|
| Durable positive walk-forward window | Future cycle(s) with `PASS_REVIEW`, `profit_factor > 1.0`, positive `total_net_pnl`. Given only 22 trades, the sample is thin; a longer window or additional backfill may be needed. |
| FreqAI model/feature diagnostics | Whether the model is stale, underfit, or suffering from a recent regime shift. |
| RiskGuard/ShadowLogger | Continued `PASS_SHADOW_ONLY` and `LOGGED` status. |

---

## 9. Cross-Cutting Safety Notes

### Metadata-only payload gap

Both approval-eligible proposals currently carry `parameters: {}` and `expected_new_values: null`. This means:

- The candidates are **approved only as concepts**, not as ready runtime overlays.
- Before any controlled apply, a separate payload-design step must populate `parameters` and `expected_new_values` with concrete, approved key/value pairs.
- The illustrative overlays in §5 and §6 are **not** the approved payload; they are placeholders for human review.

### Controlled Apply remains blocked

| Gate | Status |
|---|---|
| Human approval for candidates | `PENDING` |
| Parameter payload reconciliation | `PENDING` (metadata-only) |
| Runtime composite proof | `NOT_YET_RUN` |
| Fleet profitability gate | `blocked` |
| Controlled Apply | `APPLY_BLOCKED` |

Even if the two candidates were approved and payload-reconciled, the fleet-level profitability gate is `blocked` because two bots remain negative. Controlled Apply cannot proceed until either:

- the two blocked bots turn `candidate` or better, **or**
- an explicit fleet-level decision is made to exclude the blocked bots from the apply scope (this is outside the current autonomous rule set and requires human escalation).

---

## 10. Verdict

```text
Evidence health:                    GREEN
Scheduler continuity:               GREEN
Historical evidence:                GREEN
ShadowProposal output:              GREEN
Mutation safety:                    GREEN
Per-bot outcomes:                   2 candidate / 2 blocked
Candidate payload readiness:        METADATA_ONLY (parameters={})
Human approval state:               PENDING for all proposals
Profitability gate:                 BLOCKED at fleet level
Controlled Apply:                   APPLY_BLOCKED
Apply token:                        NOT REQUESTED / NOT PROVIDED
Runtime mutation:                   NONE
```

---

## 11. Next Recommended Single Action

**Reconcile the parameter payload for the two candidate proposals before any approval or runtime proof discussion.**

Specifically:

1. Define concrete `parameters` and `expected_new_values` for `b52975eefc17e525` and `8c87c0e21b7b1469`.
2. Validate that the proposed keys are safe-parameter-overlay compatible (no `dry_run=false`, no secrets, no strategy/pairlist logic changes outside overlay scope).
3. Run a read-only `compute_apply_result` dry-run against the reconciled payload to confirm the composite proof path can be exercised.
4. Only then consider an explicit human approval ceremony.

Do not request or set approval tokens until the payload is concrete and the fleet profitability gate is no longer `blocked`.

---

## 12. Safety Confirmation

- No proposal was applied.
- No approval token was used, requested, exported, or persisted.
- No live trading was enabled.
- No `dry_run=false` change was made or drafted.
- No runtime, config, strategy, Docker, Cron, Guardian, or environment mutation was performed.
- No destructive git command was used.
- No secrets were printed or exposed.
- No files were written to runtime-mounted Freqtrade directories.
- The parameter overlays in this report are read-only illustrative drafts, not applied config changes.

---

## 13. Report Reference

`docs/reports/si-v2-safe-parameter-overlay-candidate-package-2026-06-25.md`
