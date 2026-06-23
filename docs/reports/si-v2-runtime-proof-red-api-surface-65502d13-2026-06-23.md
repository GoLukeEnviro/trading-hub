# SI-v2 Runtime Proof Rerun — 65502d13 (TOKENDED, RED on API Surface)

## Status
**RUNTIME_PROOF_RED** 🔴

## Self-Improvement Verdict
**RUNTIME_PROOF_BLOCKED** — Proof C (file visibility + process cmdline) GREEN, but Proof A (Freqtrade `show_config` API) reports `tradable_balance_ratio: expected=0.99, got=None`. Effective overlay is loaded by Freqtrade; the API endpoint simply does not surface `tradable_balance_ratio` as a field, so the comparison mismatches on a key the API does not expose.

## Token Gate
- runtime activation token: `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION=APPROVE` ✅
- reload token: `APPROVE_SI_V2_FREQFORGE_RELOAD_65502D13=APPROVE` ✅
- Both tokens present in the executing shell. Gate PASSED.

## Repo State
- Branch: `main`
- HEAD: `a29ed6c88329fb1475a8799db63140fd841586c3`
- `origin/main`: `a29ed6c88329fb1475a8799db63140fd841586c3`
- PR #336 merge commit (`a29ed6c`): present as ancestor of HEAD ✅

## Runtime Health Preflight
- FreqForge: `Up 2 hours (healthy)` ✅
- FreqForge Canary: `Up 3 hours` ✅
- Regime Hybrid: `Up 3 hours` ✅
- FreqAI Rebel: `Up About an hour` ✅
- Rainbow producer: GREEN, fresh (signals age 73.2s) ✅

## Direct FreqForge Proof (before proof script)
- Process cmdline: `/usr/local/bin/python3.13 /home/ftuser/.local/bin/freqtrade trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json --strategy FreqForge_Override`
- Overlay file (`/freqtrade/user_data/overlay_65502d13.json`): EXISTS ✅
- Overlay content:
  ```json
  {
    "max_open_trades": 3,
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.99
  }
  ```
- Base config `dry_run=true` ✅ (preserved)
- No reload required — process already uses overlay.

## RuntimeEffectProof (via `compute_apply_result`)
| Field | Value |
|-------|-------|
| `proof_status` | **RED** |
| `file_visible_to_bot` | true ✅ (Proof C step 1) |
| `process_command_uses_overlay` | true ✅ (Proof C step 2) |
| `effective_config_contains_expected_values` | true ✅ (offline draft check) |
| `loaded_config_contains_expected_values` | false ❌ (Proof A mismatch) |
| `proof_method` | `""` (Proof A set mismatches, no fallback triggered) |
| `dry_run_true` | true ✅ |
| `live_trading_false` | true ✅ |
| `strategy_unchanged` | true ✅ |
| `restart_required` | true (computed from `loaded_ok=false`) |
| `errors` | `["api_effective_config_mismatch: tradable_balance_ratio: expected=0.99, got=None"]` |

### Effective values (from `show_config` REST response)
| Key | API returned | Expected (overlay) |
|-----|--------------|--------------------|
| `dry_run` | `True` | true |
| `max_open_trades` | `3.0` | 3 ✅ |
| `stake_amount` | `"unlimited"` | "unlimited" ✅ |
| `tradable_balance_ratio` | **`None`** | 0.99 ❌ (API does not surface this key) |
| `strategy` | `"FreqForge_Override"` | (unchanged from base) ✅ |

The `show_config` response **does not include `tradable_balance_ratio` as a key at all** — it is not a field the Freqtrade REST API exposes. The returned keys are: `api_version, available_capital, bot_name, dry_run, entry_pricing, exchange, exit_pricing, force_entry_enable, margin_mode, max_entry_position_adjustment, max_open_trades, minimal_roi, order_types, position_adjustment_enable, runmode, short_allowed, stake_amount, stake_currency, stake_currency_decimals, state, stoploss, stoploss_on_exchange, strategy, strategy_version, timeframe, timeframe_min, timeframe_ms, trading_mode, trailing_only_offset_is_reached, trailing_stop, trailing_stop_positive, trailing_stop_positive_offset, unfilledtimeout, use_custom_stoploss, version`.

Keys that match the expected overlay: `max_open_trades`, `stake_amount`, `strategy`. Key that the API does not surface: `tradable_balance_ratio`.

## ControlledApplyResult
- mode: `BLOCKED` (cascaded from RED proof)
- `mutation_counter_should_increment`: **false** (blocked per rule: requires GREEN)
- `measurement_allowed`: **false** (blocked per rule: requires `APPLIED_WITH_RUNTIME_PROOF`)
- Per Phase 6 hard rule: **do not measure, do not increment counter.** Observed.

## Mutation Ledger
- **Not updated.** Per Phase 7 hard rule: only after Phase 5 + Phase 6 are GREEN. They are not.
- No canonical ledger writer invoked. Per Phase 7 fallback rule: do not fake hidden state, do not claim ledger update.

## Measurement
- #1: **Not started.** Blocked at `measurement_allowed=false`.
- #2: **Not started.**
- Baseline (for reference only — no measurement active):
  - Candidate `65502d13`
  - `max_open_trades`: 5 → 3
  - `stake_amount`: 50 → "unlimited"
  - `tradable_balance_ratio`: 0.95 → 0.99
  - walk-forward: +23.88 USDT, PF 1.56, DD 2.19%, 77 trades

## Safety
- `dry_run=false`: never set ✅
- Live trading: not enabled ✅
- Other bots: untouched (canary, regime-hybrid, freqai-rebel all unchanged) ✅
- Strategy files: unchanged ✅
- Pairlists: unchanged ✅
- Docker / Compose: no broad actions, no `docker compose up -d` ✅
- Secrets: not printed, not exposed ✅

## Failure Classification
**RUNTIME_PROOF_RED** — exact blocker:

> `check_effective_config_from_api` (Proof A) reports a mismatch on `tradable_balance_ratio`, but the Freqtrade `show_config` REST endpoint does **not expose `tradable_balance_ratio` as a response field at all** (the key is absent from the response payload, hence the comparison yields `got=None`).
>
> The overlay **is** loaded into Freqtrade — Proof C (`file_visible_to_bot=true`, `process_command_uses_overlay=true`) and the API surface both confirm `max_open_trades=3`, `stake_amount="unlimited"`, `strategy="FreqForge_Override"`. The single failing key is one the API does not serialize.

## Decision per Hard Rules
- Do not measure. ✅ (not started)
- Do not increment mutation counter. ✅ (not incremented)
- Do not claim GREEN. ✅
- Do not open a new code-fix PR (per user instruction). ✅
- Do not start a new optimization iteration. ✅
- Follow-up issue recorded for the API-surface gap; no hidden state mutation.

## Rollback
The overlay currently in place (`freqforge/user_data/overlay_65502d13.json`) is loaded by FreqForge with `dry_run=true` and matches the approved parameter values. No rollback is required for safety. If a rollback is desired:

```bash
rm -f /home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json
```

A targeted FreqForge reload would then be required to drop the overlay from the process cmdline:

```bash
# Targeted reload only — do not run docker compose up -d
docker restart trading-freqtrade-freqforge-1
```

## Follow-up Issue (to be filed by user approval)
Title: **"SI-v2: Proof A API-surface gap — `tradable_balance_ratio` not exposed by Freqtrade `show_config`"**

Body summary:
- Proof A (`check_effective_config_from_api`) compares overlay keys to the `show_config` REST response.
- `tradable_balance_ratio` is not in the response payload, so the comparison yields `got=None` for any non-default value.
- Two viable paths (user to choose, no auto-applied):
  1. Drop `tradable_balance_ratio` from Proof A expected_keys; rely on Proof B (`compute_merged_config`) for this parameter and Proof C for the rest. Conservative — preserves safety gates.
  2. Use Freqtrade RPC `/api/v1/balance` or in-container `show_config.json` dump to read the full merged config including keys the REST surface omits. Wider blast radius (more API surface).
- Per user policy ("Phased risk decomposition", "separate PRs, never bundled"): this needs its own PR, not a hotfix on this rerun.

## Evidence Files
- Directory: `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-tokened-20260623T191005Z/`
- `runtime-effect-proof-65502d13.json` — canonical `ApplyActuatorResult`
- `runtime-effect-proof-65502d13.live.log` — full live proof run log
- `freqforge-direct-proof-before.txt` — process cmdline + overlay + base config snapshot
- `freqforge-show-config.json` — raw `show_config` response payload
- `script-audit.log` — `si_v2_apply_actuator_audit.py --mode audit` output (fleet binding GREEN, overlay at correct path)
- `runtime-health-preflight.txt` — `docker ps` + Rainbow producer readiness (GREEN)
- `repo-preflight.txt` — branch/head/origin_main/status
- `pr336-presence.txt` — `a29ed6c` merge-base ancestor of HEAD = true
- `token-gate.txt` — both tokens present
- `context.txt` — run metadata

## Nächster Schritt
**Fix the exact blocker above. Do not measure.**

User decision required on the follow-up issue: choose path (1) conservative Proof A key-set reduction or (2) richer API surface read, then queue as a separate PR. No code change, no measurement, no new optimization iteration until the proof path is GREEN.

---

*Report generated: 2026-06-23T19:10 UTC*
*Evidence directory: `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-tokened-20260623T191005Z/`*
*Previous attempt: `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-20260623T175317Z/` (blocked on token gate)*
*PR #336 merge commit: `a29ed6c88329fb1475a8799db63140fd841586c3`*
