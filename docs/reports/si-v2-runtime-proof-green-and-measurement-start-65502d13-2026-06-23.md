# SI-v2 Runtime Proof GREEN — Candidate 65502d13 (post PR #337)

**Date:** 2026-06-23
**Status:** **RUNTIME_PROOF_GREEN** ✅ (composite proof via `api_plus_merged_missing_keys`)
**Operation Level:** L3 (Token-Gate APPROVED)
**Proposal:** `65502d13` (freqforge, `safe_parameter_overlay_only`, `reinforce_profitable_pair_cluster_v1`)
**Operator:** Hermes (orchestrator profile, L3 session)
**Evidence directory:** `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-post337-20260623T193732Z/`

---

## 1. Status

**Overall:** Runtime proof GREEN. Controlled apply ACTUATOR_VERIFIED. Mutation counter
allowed. Measurement window started.

The composite (A,B) proof introduced in PR #337 correctly handles the Freqtrade 2026.3
REST API surface gap on `tradable_balance_ratio`:

- **Proof A (Freqtrade `show_config` REST)** classifies expected keys into
  matched / missing / mismatched.
- `max_open_trades` and `stake_amount` were matched by Proof A
  (`api_matched_keys = ["max_open_trades", "stake_amount"]`).
- `tradable_balance_ratio` was missing from the API response
  (`api_missing_keys = ["tradable_balance_ratio"]`).
- No mismatches (`api_mismatched_keys = []`).
- **Proof B (deterministic merged-config)** validated the missing key.
- Composite verdict: `proof_method = "api_plus_merged_missing_keys"`,
  `proof_status = "GREEN"`.

## 2. Token Gate

| Token | Value | Status |
|---|---|---|
| `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION` | `APPROVE` | ✅ PRESENT |
| `APPROVE_SI_V2_FREQFORGE_RELOAD_65502D13` | `APPROVE` | ✅ PRESENT |

Both tokens present in the executing shell. Gate PASSED.

## 3. Preflight

- **Repo:** `main` at `9c3b016adca119082d93b736b5b1b4fb364977e6` (= PR #337 squash commit). HEAD == origin/main.
- **PR #336 merge commit `a29ed6c`**: ancestor of HEAD ✅
- **PR #337 merge commit `9c3b016`**: HEAD ✅
- **Fleet:** 4/4 Freqtrade containers up + Webserver. FreqForge `Up 3 hours (healthy)`.
- **Rainbow:** `verdict=GREEN`, 50 signals, freshest 27s old, uptime 37975s, healthy.
- **Candidate:** `65502d13` — `freqtrade-freqforge`, `safe_parameter_overlay_only`.
- **No `dry_run=false`, no live trading, no secrets observed.**

## 4. Direct FreqForge Proof

- **Process cmdline:**
  `/usr/local/bin/python3.13 /home/ftuser/.local/bin/freqtrade trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json --strategy FreqForge_Override`
- **Overlay file:** `/freqtrade/user_data/overlay_65502d13.json` — EXISTS ✅
- **Overlay content:**
  ```json
  { "max_open_trades": 3, "stake_amount": "unlimited", "tradable_balance_ratio": 0.99 }
  ```
- **Base config key params:** `dry_run=True`, `max_open_trades=5`, `stake_amount=50`, `tradable_balance_ratio=0.95` (overlay values override these at runtime via multi-config stacking).
- No reload required — process already references overlay.

## 5. RuntimeEffectProof

| Field | Value |
|---|---|
| `proof_status` | **GREEN** ✅ |
| `proof_method` | **`api_plus_merged_missing_keys`** |
| `file_visible_to_bot` | true |
| `process_command_uses_overlay` | true |
| `loaded_config_contains_expected_values` | true |
| `effective_config_contains_expected_values` | true |
| `api_matched_keys` | `("max_open_trades", "stake_amount")` |
| `api_missing_keys` | `("tradable_balance_ratio",)` |
| `api_mismatched_keys` | `()` |
| `dry_run_true` | true |
| `live_trading_false` | true |
| `strategy_unchanged` | true |
| `restart_required` | false |
| `errors` | `()` |

### Effective values (verified)

| Key | Source | Value |
|---|---|---|
| `max_open_trades` | API (matched) | `3.0` |
| `stake_amount` | API (matched) | `"unlimited"` |
| `tradable_balance_ratio` | Merged (API-missing) | `0.99` |
| `dry_run` | API | `True` |
| `strategy` | API | `FreqForge_Override` (unchanged) |

## 6. ControlledApplyResult

| Field | Value |
|---|---|
| `mode` | **`ACTUATOR_VERIFIED`** |
| `eligible` | true |
| `token_provided` | true |
| `actuator_result.status` | `APPLIED_WITH_RUNTIME_PROOF` |
| `mutation_counter_should_increment` | **true** |
| `measurement_allowed` | **true** |
| `warnings` | `()` |
| `errors` | `()` |

## 7. Mutation Ledger

- **Status:** Mutation record written to evidence directory.
- **Path:** `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-post337-20260623T193732Z/mutation-record-65502d13.json`
- **Canonical ledger writer (`si_v2.measurement.ledger.build_ledger`) is scan-based** — it ingests `active_cycle_*.state.json` artifacts. The next scheduled SI-v2 active cycle will read the proof + apply result files from this evidence dir and produce the canonical measurement ledger via the existing pipeline.
- No hidden state. No faked counter increment.

### Proof reference

- `runtime-effect-proof-65502d13.json` — canonical `ApplyActuatorResult`
- `controlled-apply-result-65502d13.json` — controlled-apply wiring output
- `freqforge-direct-proof.txt` — process cmdline + overlay + base config snapshot
- `runtime-health-preflight.txt` — docker ps + Rainbow producer readiness (GREEN)
- `repo-preflight.txt` — branch/head/origin_main/PR-337-ancestor
- `mutation-record-65502d13.json` — canonical mutation record artifact

## 8. Measurement Plan

### Measurement #1 — scheduled

- **Trigger:** next scheduled SI-v2 active cycle after this proof GREEN.
- **Cycle ID requirement:** `>= 20260623T193732Z`.
- **Checks:**
  - 4/4 bots authenticated and reachable.
  - Rainbow producer fresh (signals age < 900s).
  - FreqForge process still references overlay path (`--config .../overlay_65502d13.json`).
  - Overlay file content unchanged.
  - No additional SI-v2 mutations in this cycle.
  - FreqForge `mean_profit_all_percent` vs baseline (+2.42%, trend improving, 42 trades).
- **Metrics to collect:** PnL (USDT), profit_factor, max_drawdown_pct, trade_count.
- **Compare against:** 061729Z baseline (see `si-v2-controlled-apply-proof-65502d13-2026-06-23.md`).

### Measurement #2 — scheduled

- **Trigger:** next cycle after measurement #1.
- **Checks:** same as measurement #1, plus two-cycle trend comparison; no regression vs baseline.

### Baseline (for reference)

| Parameter | Before | After (overlay) |
|---|---|---|
| `max_open_trades` | 5 | 3 |
| `stake_amount` | 50 | `"unlimited"` |
| `tradable_balance_ratio` | 0.95 | 0.99 |

Walk-forward (out-of-sample): **+23.88 USDT, PF 1.56, DD 2.19%, 77 trades** (PASS_REVIEW).

### Abort conditions

- `dry_run=false` detected anywhere.
- Live trading mutation detected.
- Strategy file modified.
- Any other bot touched.
- FreqForge overlay path missing from process cmdline.
- Rainbow producer not fresh for two consecutive cycles.

### Next report

`docs/reports/si-v2-measurement-1-65502d13-<cycle-id>.md` after the next scheduled cycle.

## 9. Safety

| Check | Status |
|---|---|
| `dry_run=false` | never set ✅ |
| Live trading | not enabled ✅ |
| Other bots | untouched (canary, regime-hybrid, freqai-rebel all unchanged) ✅ |
| Strategy files | unchanged ✅ |
| Pairlists | unchanged ✅ |
| Docker / Compose | no broad actions, no `docker compose up -d` ✅ |
| Secrets | not printed, not exposed ✅ |
| Rollback path | documented (see below) ✅ |

## 10. Rollback

If measurement #1 shows regression or any abort condition fires:

```bash
# 1. Remove the overlay file (live runtime drop)
rm -f /home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json

# 2. Targeted FreqForge restart so the process cmdline drops the overlay arg
docker restart trading-freqtrade-freqforge-1
```

Rollback is strictly safer than the current state (overlay file removed → bot reverts to base config `max_open_trades=5`, `stake_amount=50`, `tradable_balance_ratio=0.95`).

## 11. PR

- Branch: `report/si-v2-65502d13-runtime-proof-green`
- Commit: (created in this report PR)
- PR title: `docs(si-v2): record runtime proof green for 65502d13`
- Files staged:
  - `docs/reports/si-v2-runtime-proof-green-and-measurement-start-65502d13-2026-06-23.md` (this report)

## 12. Related PRs

| PR | Description | Status |
|---|---|---|
| #336 | Multi-config runtime proof (`check_process_uses_overlay`, `process_command_uses_overlay`) | Merged (`a29ed6c`) |
| #337 | API-surface-aware composite proof (PR #337) | Merged (`9c3b016`) |
| #338 (this) | Record runtime proof GREEN for 65502d13 | Open |

---

*Report generated: 2026-06-23T19:37 UTC*
*Evidence directory: `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-post337-20260623T193732Z/`*
*PR #336 merge commit: `a29ed6c88329fb1475a8799db63140fd841586c3`*
*PR #337 merge commit: `9c3b016adca119082d93b736b5b1b4fb364977e6`*
