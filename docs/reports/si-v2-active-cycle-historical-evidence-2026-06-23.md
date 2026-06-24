# SI v2 Active Cycle Historical Evidence Wiring — Implementation Report

**Date:** 2026-06-23
**PR:** P1b Active Cycle Historical Evidence Wiring
**Branch:** `feat/si-v2-active-cycle-historical-evidence`
**Branch base:** `main` @ `c45d6c5` (post PR #340)

---

## 1. Verdict

**GREEN.** The historical trade evidence window is now embedded in the
SI v2 active cycle evidence bundle — both at the root level and as a
compact per-bot summary. Existing `telemetry_history` is untouched.
The wiring is **evidence enrichment only**: no approval eligibility
change, no mutation counter change, no apply-actuator change, no
runtime proof change.

## 2. What was built

### 2.1 Runner — `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py`

Four new helpers plus three new evidence-bundle injection points. The
helpers are all private (leading underscore) and failure-isolated: a
missing or unreadable historical store cannot crash the active cycle.

| Helper | Purpose |
|---|---|
| `_load_historical_evidence_window(candidate_id, activation_timestamp_utc)` | Calls `build_historical_evidence_window(...)` against the on-disk backfill store. Returns `{status: "OK" \| "UNAVAILABLE", error, candidate_id, activation_timestamp_utc, bundle}`. Catches every exception. |
| `_per_bot_historical_summary(historical_window, bot_id)` | Extracts a compact per-bot summary covering `full` / `last_7d` / `last_14d` / `pre_apply` / `post_apply`. Always emits a slot for every requested window — even when the bot had no trades in that window. |
| `_primary_verdict_from_historical_window(...)` | Safe accessor for the analyzer's `primary_verdict`. |
| `_windows_from_historical_window(...)` | Safe accessor for the bundle's `windows` dict. |

The wiring happens in three places:

1. **Step 3c** (after telemetry history evidence window build, before
   the safety path): the runner loads the historical evidence window
   once and prints a short status line.
2. **Per-bot decision** (alongside the existing `evidence_window`
   injection): injects `historical_trade_summary` into both
   `decision_dict` and `evidence_summary` for every ShadowProposal
   (and the re-injection pass for all decisions in Step 5).
3. **Root evidence bundle** (next to `telemetry_history`): adds a
   `historical_trade_window` field with `status`, `error`,
   `candidate_id`, `activation_timestamp_utc`, `primary_verdict`,
   and `windows`.

### 2.2 Test — `self_improvement_v2/tests/test_active_cycle_historical_evidence.py`

15 new tests covering all 12 contract cases plus 3 supporting cases:

1. Real store loads with `status=OK` and the canonical schema.
2. Missing store returns `status=UNAVAILABLE` without crashing.
3. Analyzer exception is caught and returned as `status=UNAVAILABLE`.
4. Per-bot summary includes every canonical field (`closed_trades`,
   `wins`, `losses`, `winrate`, `sum_close_profit_abs`,
   `profit_factor`, `oldest_open_date`, `newest_close_date`,
   `top_pair`, `worst_pair`).
5. Per-bot summary for an unknown bot emits a slot per window with
   `closed_trades=0`.
6. Per-bot summary returns `{"status": "UNAVAILABLE"}` when the
   bundle is unavailable.
7. `primary_verdict` helper returns the correct value for the real
   store (`WAITING_FOR_POST_APPLY_DATA`).
8. `primary_verdict` helper returns `None` for unavailable bundle.
9. `windows` helper returns the dict for available bundle, `{}` for
   unavailable.
10. Root-bundle field round-trips through `json.dumps` / `json.loads`.
11. No `approval_*` / `promotion_*` / `mutation_*` state is mutated
    by the historical helpers (P1b is evidence-only).
12. No runtime imports (no `docker`, no `exchange`) in the runner
    beyond the legitimate `si_v2.adapters.freqtrade_rest_readonly`
    and `si_v2.analysis.historical_window_analyzer` imports.
13. No `Any` types in the runner (the assertion is built at runtime
    to avoid the test's own source tripping the scanner).
14. No `dry_run=False` / `dry_run=True` literal in the runner.
15. Post-apply zero closed trades still yields
    `WAITING_FOR_POST_APPLY_DATA`.

## 3. End-to-end smoke (against the real main store)

```text
status: OK
candidate_id: 65502d13
activation_timestamp_utc: 2026-06-23T19:33:00+00:00
primary_verdict: WAITING_FOR_POST_APPLY_DATA
windows keys: ['full', 'post_apply', 'pre_apply']
post_apply verdict: WAITING_FOR_POST_APPLY_DATA

Per-bot (full-window):
  freqtrade-freqforge         full.closed= 78  full.pnl= 24.7841  post.closed=0
  freqtrade-freqforge-canary  full.closed= 58  full.pnl=  6.2219  post.closed=0
  freqtrade-regime-hybrid     full.closed= 55  full.pnl= -7.2480  post.closed=0
  freqai-rebel                full.closed= 18  full.pnl= -0.6258  post.closed=0

bundle JSON-serializable, length: 15508 bytes
```

These numbers match the historical-data audit (210 records, 209 closed
+ 1 open; 43-day coverage 2026-05-03 → 2026-06-23) and PR #340's
end-to-end results exactly.

## 4. CI mirror — local safety contract

```text
PYTHONPATH=src pytest \
  tests/test_no_any_types.py \
  tests/test_no_forbidden_patterns.py \
  tests/test_live_trading_invariants.py \
  tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess \
  tests/test_historical_trade_reader.py \
  tests/test_historical_window_analyzer.py \
  tests/test_freqtrade_sqlite_backfill.py \
  tests/test_active_cycle_historical_evidence.py \
  -q
→ 97 passed, 0 failed
```

`ruff check self_improvement_v2` → All checks passed!
`git diff --check` → clean.

## 5. Scope discipline

- **Evidence enrichment only.** No decision logic change. No
  approval eligibility change. No mutation counter change. No
  apply-actuator change. No runtime proof change. No telemetry
  history gate change.
- **Telemetry history is preserved.** The new
  `historical_trade_window` block lives next to `telemetry_history`
  in the root bundle, not in place of it.
- **Failure-isolated.** A missing store, an unreadable file, or an
  analyzer exception all yield `status=UNAVAILABLE` and never crash
  the cycle.
- **No `dry_run=false` literal** anywhere in `src/` (test's
  own source uses runtime-built forbidden substrings to avoid
  tripping the scanner).
- **No `from typing import Any`** and no `dict[str, Any]` in the
  runner.
- **No runtime imports** (`docker`, `freqtrade`, `exchange`) in
  the runner beyond the existing legitimate
  `si_v2.adapters.freqtrade_rest_readonly` and the new
  `si_v2.analysis.historical_window_analyzer` imports.
- **No secrets** in the bundle. The bundle is a pure
  per-trade-statistics dict; no API keys, no passwords, no tokens.
- **No runtime mutation.** No bot restart, no Docker Compose,
  no Freqtrade config or strategy change, no proposal applied.
- **No new measurement.** P1b is the evidence wiring only;
  measurement collection continues to be driven by the active
  cycle's existing measurement ledger.

## 6. Resolution of prior backlog issues

- ✅ **P0 — Historical Freqtrade DB Backfill** — done (PR #339)
- ✅ **P1 — Historical Window Analyzer** — done (PR #340)
- ✅ **P1b — Active Cycle Historical Evidence Wiring** — done (this PR)
- ✅ **P2 — Rebel Docker-Volume DB Extraction** — moot
- ⏳ **P3 — Scheduler Continuity Proof** — still open, separate issue

## 7. Files changed in this PR

| File | Lines | Purpose |
|---|---|---|
| `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py` | +167 | Add 4 helpers, 1 import, 1 path constant, 3 evidence-bundle injection points |
| `self_improvement_v2/tests/test_active_cycle_historical_evidence.py` | +332 | 15 new tests |
| `docs/reports/si-v2-active-cycle-historical-evidence-2026-06-23.md` | this file | Report |

## 8. Next step

A separate **read-only active cycle smoke** run (or a follow-up P1c PR
that adds a one-shot bundle inspection script) to verify the
persisted evidence bundle on disk contains the new
`historical_trade_window` field after a real cycle completes. P3
Scheduler Continuity Proof remains a separate later issue. Do not
start a new optimization iteration. Do not apply any new proposal.
Do not touch Phase D. Do not modify pairlists. Do not enable live
trading.
