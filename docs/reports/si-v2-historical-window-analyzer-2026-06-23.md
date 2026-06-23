# SI v2 Historical Window Analyzer — Implementation Report

**Date:** 2026-06-23
**PR:** P1 Historical Window Analyzer (companion to PR #339 backfill)
**Branch:** `feat/si-v2-historical-window-analyzer`
**Branch base:** `main` @ `1f56e1a9` (post PR #339)

---

## 1. Verdict

**GREEN.** The historical trade store is now consumable by an analyzer that
exposes per-bot and fleet-level performance windows. The analyzer correctly
emits `WAITING_FOR_POST_APPLY_DATA` for the post-activation window because
no FreqForge trade has closed since the `2026-06-23T19:33:00Z` overlay
activation (the bot is on 15m timeframe, sparse; measurement #2 will
re-evaluate this once trades accumulate).

## 2. What was built

### 2.1 Reader — `self_improvement_v2/src/si_v2/backfill/historical_trade_reader.py`

Read-only consumer of the JSONL store produced by PR #339.

- Loads every `historical_trades_<bot_id>.jsonl` file in `store_dir`.
- Validates `schema_version == 1`; mismatches are skipped with a warning.
- Skips corrupt JSONL lines with a warning instead of crashing.
- Filters: `bot_id`, time window (`start_utc` / `end_utc`, inclusive),
  `only_closed` / `only_open`, exact-match `pair`.
- Returns `(records, ReadStats)` where `ReadStats` carries the per-file
  load counters (lines_total, lines_kept, lines_skipped_corrupt, etc.).
- Hard rule: no runtime imports (no `docker`, `freqtrade`, `exchange` in
  any `import X` / `from X` line). Asserted by a unit test.

### 2.2 Analyzer — `self_improvement_v2/src/si_v2/analysis/historical_window_analyzer.py`

Pure read-only analysis layer.

Per-bot metrics (`WindowMetrics.to_dict()`):
- `total_trades`, `closed_trades`, `open_trades`
- `wins`, `losses`, `winrate`
- `sum_close_profit_abs`, `average_close_profit_abs`,
  `sum_close_profit_ratio`
- `gross_profit`, `gross_loss`, `profit_factor`
  (Python `inf` when only winners exist; `None` when no closed trades)
- `best_trade_abs`, `worst_trade_abs`
- `oldest_open_date`, `newest_close_date`
- `top_pairs` / `worst_pairs` (top 5 by PnL each)

Fleet summary (`FleetSummary.to_dict()`):
- `bots_covered`, `total_trades`, `closed_trades`, `open_trades`
- `wins`, `losses`, `winrate`
- `sum_close_profit_abs`, `fleet_profit_factor`
- `strongest_bot` / `weakest_bot` (by `sum_close_profit_abs`)
- `coverage_start` / `coverage_end` (across all bots for that window)
- `data_completeness` ∈ {`complete`, `empty`}

Windows supported:
- `full` — every record in the store
- `last_7d` — closed trades with `close_date` in the last 7 days
- `last_14d` — closed trades with `close_date` in the last 14 days
- `pre_apply` — closed trades with `close_date < activation_timestamp_utc`
- `post_apply` — closed trades with `close_date >= activation_timestamp_utc`

Verdict policy:
- `post_apply` with `closed_trades < MIN_POST_APPLY_CLOSED_TRADES` (1)
  → `WAITING_FOR_POST_APPLY_DATA` (default behaviour).
- `post_apply` with ≥1 closed trade but < 5 → `YELLOW`
- `post_apply` with ≥5 closed trades → `GREEN`
- Other windows: `GREEN` if any closed trades, otherwise `YELLOW`.

### 2.3 Evidence bundle — `build_historical_evidence_window(...)`

Convenience wrapper that returns a JSON-serializable
`si_v2.historical_evidence_window/v1` bundle containing the
`full` / `pre_apply` / `post_apply` windows plus a `primary_verdict`
derived from the post-apply window. Designed to be called by the SI v2
active cycle once that flow is wired in. The active cycle is intentionally
**not** modified in this PR.

## 3. Tests

Two new test files in `self_improvement_v2/tests/`:

- `test_historical_trade_reader.py` (12 tests)
  - Load counts
  - `bot_id` filter
  - Status filter (`only_closed` / `only_open`)
  - `pair` filter
  - Time window filter
  - Corrupt line handling
  - Schema mismatch handling
  - `FileNotFoundError` on invalid `store_dir`
  - `ValueError` on mutually exclusive filters
  - `list_bots` / `iter_pairs` helpers
  - No-runtime-imports contract check (string scan of the source file)
  - `TradeRecord.is_closed` property

- `test_historical_window_analyzer.py` (15 tests)
  - Per-bot basic metrics (counts, PnL, winrate, PF, best/worst trade,
    top/worst pairs)
  - Per-bot open-trade handling (PF = `inf` when only winners)
  - Per-bot empty input
  - Fleet summary with strongest/weakest/coverage bounds
  - Fleet summary empty
  - `analyze_windows` on full fixture store
  - `analyze_windows` pre-apply split
  - `analyze_windows` post-apply with zero closed trades → `WAITING_FOR_POST_APPLY_DATA`
  - `analyze_windows` post-apply with trades (PF + verdict)
  - `analyze_windows` last-7d with fixed `now`
  - `analyze_windows` requires `activation_utc` for apply windows
  - `build_historical_evidence_window` post-apply waiting
  - `build_historical_evidence_window` with post-apply data
  - No-runtime-imports contract (string scan of the analyzer source)
  - `json.dumps` round-trip (no `object`-typed leaks)

## 4. End-to-end smoke (against the real `main` store)

Input: `self_improvement_v2/state/historical_trades/`
(4 JSONL files, 210 records, 209 closed + 1 open)

```text
=== Windows: closed_trade count + pnl + verdict ===
  full             closed=209  pnl= 23.1322  PF=1.369661  verdict=GREEN
  last_7d          closed= 28  pnl=  3.7541  PF=2.019254  verdict=GREEN
  last_14d         closed= 51  pnl= -2.0219  PF=0.798608  verdict=GREEN
  pre_apply        closed=209  pnl= 23.1322  PF=1.369661  verdict=GREEN
  post_apply       closed=  0  pnl=  0.0000  PF=None      verdict=WAITING_FOR_POST_APPLY_DATA
```

Fleet strongest/weakest (full):
- strongest: `freqtrade-freqforge` (+24.78 USDT)
- weakest: `freqtrade-regime-hybrid` (-7.25 USDT)
- coverage: 2026-05-03 → 2026-06-23 (52 days)

`build_historical_evidence_window(...)` for candidate `65502d13`:
- `primary_verdict`: `WAITING_FOR_POST_APPLY_DATA` ✅ (correct — overlay
  just activated ~25 min before this report was written; no closed
  post-apply trades yet)

## 5. CI mirror — local safety contract

```text
PYTHONPATH=src pytest \
  tests/test_no_any_types.py \
  tests/test_no_forbidden_patterns.py \
  tests/test_live_trading_invariants.py \
  tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess \
  tests/test_historical_trade_reader.py \
  tests/test_historical_window_analyzer.py \
  tests/test_freqtrade_sqlite_backfill.py \
  -q
→ 83 passed, 0 failed
```

`git diff --check` is clean.

The pre-existing failures in `tests/test_source_readiness_summary.py`
and `tests/test_offline_quality_gate.py` are on `main` and unrelated to
this PR (they depend on rainbow/episode manifest artifacts that are not
present in this build).

## 6. Scope discipline

- No runtime mutation. No bot restart, no Docker Compose, no Freqtrade
  config or strategy change, no proposal applied.
- No `dry_run=false` literal anywhere in `src/` (the closest match in
  the diff is "No live trading" and "Dry-run mode must remain enabled").
- No secrets in output. The bundle's contract test explicitly scans
  for the keys `api_key`, `password`, `token`, `secret` and asserts
  their absence at every level.
- No `from typing import Any`. All dict types use `dict[str, object]`
  (Python 3.9+ syntax).
- No new files under `si_v2/backfill/__init__.py` exports — the
  reader is a sibling of the backfill module and is not re-exported
  from the package init. The analyzer lives under a new
  `si_v2/analysis/` package.

## 7. Resolution of prior backlog issues

- ✅ **P0 — Historical Freqtrade DB Backfill** — done (PR #339)
- ✅ **P1 — Historical Window Analyzer** — done (this PR)
- ✅ **P2 — Rebel Docker-Volume DB Extraction** — moot (all 4 bot DBs are host-bind-mounted)
- ⏳ **P3 — Scheduler Continuity Proof** — still open, separate issue

## 8. Files changed in this PR

| File | Lines | Purpose |
|---|---|---|
| `self_improvement_v2/src/si_v2/backfill/historical_trade_reader.py` | +260 | Read-only store loader |
| `self_improvement_v2/src/si_v2/analysis/historical_window_analyzer.py` | +469 | Per-bot + fleet window analysis |
| `self_improvement_v2/tests/test_historical_trade_reader.py` | +248 | Reader tests |
| `self_improvement_v2/tests/test_historical_window_analyzer.py` | +368 | Analyzer tests |
| `docs/reports/si-v2-historical-window-analyzer-2026-06-23.md` | this file | Report |

## 9. Next step

A separate PR (P1b) wires `build_historical_evidence_window(...)` into
the SI v2 active cycle evidence bundle. P3 Scheduler Continuity Proof
remains a separate later issue. Do not start a new optimization
iteration. Do not apply any new proposal. Do not touch Phase D. Do not
modify pairlists. Do not enable live trading.
