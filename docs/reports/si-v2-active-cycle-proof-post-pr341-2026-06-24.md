# SI-v2 Active Cycle Proof after PR #341

**Status:** `GREEN`
**Operation Level:** `L2` — read-only runtime/API observation plus report/evidence artifacts.
**Timestamp (UTC):** `2026-06-24T05:50:58Z` runner start; cycle id `20260624T055059Z`.
**Repository:** `/home/hermes/projects/trading`
**Branch / HEAD:** `main` @ `f14b286a2d1cf501a1aff552d3449c5ceae4a10d` (`feat(si-v2): add historical evidence to active cycle`)
**Purpose:** prove current `main` after PR #341 reads all four dry-run bots, persists historical trade evidence into the Active Cycle bundle/per-bot decisions, emits ShadowProposal evidence, and performs zero runtime/config/strategy/Docker/live-trading mutations.

---

## Commands Used

```bash
cd /home/hermes/projects/trading
git fetch origin main --prune
git rev-parse HEAD
git rev-parse refs/remotes/origin/main
git merge-base --is-ancestor f14b286a2d1cf501a1aff552d3449c5ceae4a10d HEAD

env -u APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION     -u APPROVE_SI_V2_FREQFORGE_RELOAD_65502D13     -u APPROVE_SI_V2_APPLY     -u APPROVE_SI_V2_CONTROLLED_APPLY     /opt/data/scripts/si-v2-active-cycle-runner.sh
```

Notes:

- Used the existing scheduled wrapper; no new runner was invented.
- No approval token was provided.
- No Docker Compose operation, Docker restart, config edit, strategy edit, cron edit, Guardian edit, proposal apply, or live-trading action was run.
- The wrapper started a credential-free local Rainbow DB stub on `127.0.0.1` for this cycle and stopped it cleanly at exit.

---

## Repo Preflight

| Check | Result |
|---|---:|
| current branch | `main` |
| `HEAD` | `f14b286a2d1cf501a1aff552d3449c5ceae4a10d` |
| `origin/main` after fetch | `f14b286a2d1cf501a1aff552d3449c5ceae4a10d` |
| `HEAD == origin/main` | `yes` |
| PR #341 merge commit is HEAD | `yes` |
| PR #341 merge commit ancestor of HEAD | `yes` |
| tracked diff after run, before this report | none |

Pre-existing untracked files were present before the run and left untouched. This report is the only intentional new docs artifact from this proof step.

---

## Evidence Artifacts

| Artifact | Path / Value |
|---|---|
| Runner log | `/opt/data/logs/si-v2-active-cycle/cycle-20260624T055058Z.log` |
| Evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260624T055059Z.json` |
| Evidence bundle SHA-256 | `694641dea7025f49de82a378a6a4d0ce3ad8ecf5ab0214dc70af5eb4252a9aa0` |
| Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260624T055059Z.state.json` |
| Cycle state SHA-256 | `cd06eaf8beb68460218e9a7761d0e77cb31686d92ead14725b02345e58ae5773` |
| Project-native runner report | `self_improvement_v2/reports/phase2/active_cycle_runner_report.md` |
| Measurement summary | `self_improvement_v2/reports/phase2/measurement/measurement_summary.json` |
| Telemetry history latest file | `self_improvement_v2/state/telemetry_history/telemetry_20260624.jsonl` |
| Telemetry history records in latest file | `2` |
| Latest telemetry cycles in file | `20260624T002122Z, 20260624T055059Z` |

---

## 4-Bot Active-Cycle Result

| Bot | Ping OK | Auth | Status HTTP | Decision | RiskGuard | ShadowLogger | Historical summary | Evidence summary historical | Walk-forward status | Approval status | Approval eligible |
|---|---:|---|---:|---|---|---|---|---|---|---|---:|
| `freqtrade-freqforge` | `True` | `AUTHENTICATED` | `200` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `OK` | `OK` | `PASS_REVIEW` | `PENDING_HUMAN` | `True` |
| `freqtrade-freqforge-canary` | `True` | `AUTHENTICATED` | `200` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `OK` | `OK` | `PASS_REVIEW` | `PENDING_HUMAN` | `True` |
| `freqtrade-regime-hybrid` | `True` | `AUTHENTICATED` | `200` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `OK` | `OK` | `NEGATIVE_NET_METRICS` | `PENDING_HUMAN` | `False` |
| `freqai-rebel` | `True` | `AUTHENTICATED` | `200` | `SHADOW_PROPOSAL` | `PASS_SHADOW_ONLY` | `LOGGED` | `OK` | `OK` | `NEGATIVE_NET_METRICS` | `PENDING_HUMAN` | `False` |

Fleet result:

| Metric | Value |
|---|---:|
| fleet verdict | `GREEN` |
| total bots | `4` |
| ping ok | `4` |
| ping failed | `0` |
| status authenticated | `4` |
| shadow proposals | `4` |
| no-proposal decisions | `0` |

---

## Historical Evidence Status

| Check | Result |
|---|---|
| root evidence bundle has `historical_trade_window` | `yes` |
| `historical_trade_window.status` | `OK` |
| `historical_trade_window.primary_verdict` | `WAITING_FOR_POST_APPLY_DATA` |
| windows present | `full, post_apply, pre_apply` |
| each per-bot decision has `historical_trade_summary` | `True` |
| each `evidence_summary` has `historical_trade_summary` | `True` |
| telemetry `evidence_window` still present in every `evidence_summary` | `True` |
| telemetry history runs observed | `5` |
| telemetry history freshness | `fresh` |

Interpretation: PR #341 wiring is visible in the persisted evidence bundle and in all per-bot decisions. The historical trade window is present and currently reports `WAITING_FOR_POST_APPLY_DATA`, which is expected for evidence-only post-merge proof without a controlled apply.

---

## ShadowProposal / Approval / Apply Semantics

| Metric | Value |
|---|---:|
| ShadowProposal count | `4` |
| NO_PROPOSAL count | `0` |
| proposals requiring human approval | `4` |
| approval eligible count | `2` |
| profitability gate verdict | `blocked` |
| profitability gate candidates | `2` |
| profitability gate blocked | `2` |
| proposal applied | `false / absent` |
| apply or actuator keys present in decisions/safety results | `False` |

Interpretation: The cycle generated ShadowProposal evidence for all four bots, but no proposal was applied. Approval/apply semantics remain guarded: proposals require human approval, no approval token was used, and no apply-actuator path was invoked.

---

## Safety Counters

| Counter / Safety Check | Value |
|---|---:|
| runtime_mutations | `0` |
| config_mutations | `0` |
| strategy_mutations | `0` |
| docker_mutations | `0` |
| live_trading_mutations | `0` |
| Measurement ledger `mutations_all_zero` | `True` |
| Measurement ledger `secrets_found` | `False` |
| ledger cycles scanned | `56` |
| bot measurement points | `224` |
| proposal records | `125` |

---

## Rainbow / External Signal Observation

| Metric | Value |
|---|---:|
| status | `SUCCESS` |
| source | `read_only` |
| count | `50` |
| errors | `0` |
| fresh | `True` |
| freshness seconds | `88` |
| freshness max seconds | `900` |

---

## Validation Matrix

| Check | Passed |
|---|---:|
| `expected_bots_present` | `True` |
| `all_ping_ok` | `True` |
| `all_status_authenticated` | `True` |
| `all_decisions_present` | `True` |
| `all_historical_trade_summary_present` | `True` |
| `all_evidence_summary_historical_present` | `True` |
| `all_evidence_summary_telemetry_window_present` | `True` |
| `historical_trade_window_ok` | `True` |
| `mutation_counters_zero` | `True` |
| `proposal_applied_false_or_absent` | `True` |
| `apply_actuator_not_invoked` | `True` |
| `secrets_found_false` | `True` |

---

## Blocker

None for the post-PR-#341 read-only Active Cycle Evidence Proof.

Caveat: This is not an approval-to-apply result. The historical window remains `WAITING_FOR_POST_APPLY_DATA`; profitability gate is fleet-level `blocked` because only two bots are approval-eligible in this cycle. That is safe and expected for an evidence-only proof.

---

## Recommended Next Step

Proceed to Issue #342 Docs-only Alignment as the next small governance/docs PR. Keep PR #311 separate, and treat PR #330 as stale/superseded until it is reconciled against this post-#341 evidence shape.

Suggested sequence remains:

1. `DONE` — PR #341 merged.
2. `DONE` — fresh read-only Active Cycle Proof on current `main` after PR #341.
3. `NEXT` — Issue #342 Docs-only Alignment.
4. `THEN` — P3 Scheduler Continuity Proof.
5. `LATER` — decide whether #330 is updated, superseded, or closed; handle #311 separately.
