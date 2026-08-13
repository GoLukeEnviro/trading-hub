# Canonical Funding Data Contract — Gate-0 Selection Backtest

**Date:** 2026-08-13
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #705 (A1; follow-up of #697)
**Execution class:** A1 (repository-only; no runtime, no data download, no live trading)

## Purpose

Define the canonical funding data contract for the Gate-0 selection backtest
(`FreqForge_Gate0_Core_v1`, #604/#702). This contract documents the data
source, the confirmed history limit, the coverage acceptance criterion, the
handling of missing rates (fail-closed, no silent gaps), and the fallback
source evaluation. It is the A1 prerequisite that closes the coverage gap
from #697 (`next_action=DEFINE_CANONICAL_FUNDING_DATA_CONTRACT`,
`FUNDING_HISTORY=INCOMPLETE_CONFIRMED_NATIVE_LIMIT`).

## 1. Data source

| Field | Value |
|---|---|
| Source | Bitget REST `history-fund-rate` (v2 `/api/v2/mix/market/history-fund-rate`, v3 `/api/v3/market/history-fund-rate`) |
| CCXT path | `bitget.fetch_funding_rate_history(symbol, since, limit, params)` — same underlying REST endpoint |
| Product type | `USDT-FUTURES` (linear perpetuals) |
| Pairs | `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT` |
| Funding interval | 8h (Bitget USDT-FUTURES); persisted as 1h `funding_rate` candle type in the native dataset |
| Pagination | page/cursor, `limit` max 100 per page |
| Auth | public read-only, no credentials |

## 2. Confirmed history limit (~90 days)

Empirically verified twice, independently:

1. **REST probes (2026-08-02, A0, #693/#696):** v2 `pageNo=1..3` and v3
   `cursor=1..3` both return 100/100/70 rows; `pageNo/cursor >= 4` return 0.
   Oldest reachable: **2026-05-05 (~90 days)**.
2. **Native CCXT run (2026-08-03, A2, #697):**
   `fetch_funding_rate_history` (limit 100) returned 100–101 points per pair
   covering **2026-07-01 → 2026-08-03 (~90 days)** — congruent with the REST
   finding.

**Contract value:** `FUNDING_HISTORY_LIMIT_DAYS = 90` (reproducible cap).

## 3. Fallback source evaluation (deliverable 2)

| Candidate | Verdict | Reason |
|---|---|---|
| Bitget Websocket history replay | **VERWORFEN** | WS channels are real-time only; no public historical replay endpoint. Third-party archives (Tardis.dev, CryptoHFTData) exist but are external commercial data. |
| External archives (Tardis.dev, CryptoHFTData, etc.) | **VERWORFEN** | `external_data_mix=PROHIBITED` (Luke, #697 comment `5179705029`). Mixing external funding into the canonical dataset is prohibited. |
| Synthetic funding / `funding_rate=0` fill | **VERWORFEN** | `synthetic_funding=PROHIBITED`, `funding_rate_zero=PROHIBITED` (same decision). |
| REST + native mix | **VERWORFEN** | Both paths share the same ~90-day cap; a mix adds no coverage and violates `external_data_mix=PROHIBITED`. |

**Conclusion:** no policy-compliant fallback source exists. The canonical
funding input for the selection backtest is the **native Freqtrade download**
(`--candle-types mark funding_rate`, decision B of the Freqtrade-native data
contract), with the documented ~90-day gap handled fail-closed.

## 4. Coverage acceptance criterion

The selection backtest cost model requires complete funding history for the
full backtest window (warm-up start through selection end):

| Field | Value |
|---|---|
| `FUNDING_COVERAGE_REQUIRED_FROM` | `2024-12-01T00:00:00Z` (warm-up start) |
| `FUNDING_COVERAGE_REQUIRED_TO` | `2026-06-30T00:00:00Z` (selection end, holdout excluded) |
| Alignment | matches `REQUIRED_COVERAGE["funding_rate"]["1h"]` in `freqtrade_native_data_contract.py` (native `to` = last-candle `2026-06-30T23:00:00Z` covers the day boundary) |
| Grace | **none** — partial funding is the confirmed native limit; no grace is granted |

**Status:** `FUNDING_STATUS = "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"` — the
canonical dataset does **not** satisfy the criterion. Per Luke's decision
(`REJECT_INCOMPLETE_FUNDING`, Gate-0 disposition `EXTEND`), the selection
backtest (#702) is **not authorized** until a new canonical funding data
contract exists.

## 5. Missing-rate handling (fail-closed, no silent gaps)

Implemented in `self_improvement_v2/src/si_v2/research/backtest_contract.py`
(issue #705):

- `FundingCoverage` — measured window (first/last/rate_count) per pair.
- `compute_funding_coverage()` — deterministic measurement over the
  deduplicated millisecond-keyed rows.
- `validate_funding_coverage()` — fail-closed:
  `FUNDING_COVERAGE_EMPTY`, `FUNDING_COVERAGE_START_LATE`,
  `FUNDING_COVERAGE_END_EARLY`.
- `funding_coverage_report()` — canonical evidence dict (pair, status,
  source, history limit, measured window, required window, `coverage_ok`).
- `convert_funding_to_freqtrade_with_coverage()` — fail-closed adapter:
  validates coverage **before** materializing; on incomplete coverage it
  raises and writes **no** partial funding file.
- `convert_funding_to_freqtrade()` — unchanged (audit-helper only, backward
  compatible; documented as not load-compatible until proven).

## 6. Validation

| Check | Result |
|---|---|
| `test_backtest_contract.py` (incl. 18 new funding-contract tests) | 63/63 pass |
| Ruff (changed files) | clean |
| `git diff --check` | clean |
| CI (Main Gate + Offline Smoke) | per PR checks |

## 7. Safety status

```text
DATA_DOWNLOAD=NO            (A2, not authorized)
BACKTEST_EXECUTED=NO
HOLDOUT_INSPECTED=NO
SYNTHETIC_FUNDING=NO
FUNDING_RATE_ZERO=NO
EXTERNAL_DATA_MIX=NO
LIVE_TRADING=NO
RUNTIME_MUTATION=NO
```

## 8. Next steps

1. Merge this A1 contract (Standing Owner Authorization, ADR-2026-08-04).
2. Define a new canonical funding data contract (longer history) — the
   Gate-0 follow-up requirement from #697.
3. Only then: create/execute the A2 selection backtest (#702) and record the
   Gate-0 edge decision.
