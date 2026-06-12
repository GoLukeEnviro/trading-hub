# Market Data Readiness Specification — SI v2, Issue #34

## Purpose

Define the canonical requirements for safe, read-only market-data ingestion
that can feed backtest, walk-forward, and proposal-weight validation stages
without introducing look-ahead, survivorship, or leakage bias.

## Scope

This specification covers **read-only market-data readiness** only.
It does not implement ingestion code — it defines the contracts that
ingestion code must satisfy. A follow-up implementation issue will
build data-source adapters that conform to this specification.

---

## 1. Approved and Rejected Data-Source Categories

### Approved

- Public exchange OHLCV REST endpoints (e.g., Binance, Bitget, Coinbase).
- Freqtrade data download output (`.feather` files from `freqtrade download-data`).
- Verified CSV/Parquet dumps with unambiguous provenance.
- Exchange WebSocket aggregates persisted to time-series storage.

### Rejected

- Third-party paid-API data without public verification.
- User-uploaded CSV/Parquet of unknown provenance.
- DEX pool data unless the full pool-reserve history is available.
- Derived candles (aggregated from trades) unless the original trade data
  is also retained.

---

## 2. Canonical Candle and Market-Observation Schema

Every ingested observation must be representable in this canonical schema:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pair` | str | yes | Normalized pair ID (e.g., `BTC/USDT`) |
| `exchange` | str | yes | Exchange name (e.g., `binance`, `bitget`) |
| `timeframe` | str | yes | Candle interval (e.g., `1h`, `4h`, `1d`) |
| `timestamp` | datetime(tz-aware) | yes | Candle open time, UTC |
| `open` | float | yes | Open price |
| `high` | float | yes | High price |
| `low` | float | yes | Low price |
| `close` | float | yes | Close price |
| `volume` | float | yes | Volume in base currency |
| `trade_count` | int | no | Number of trades (optional) |
| `source_hash` | str | no | Content hash of raw source row |

---

## 3. Timestamp, Timezone, Ordering, and Uniqueness Rules

- **Timezone**: All timestamps must be timezone-aware UTC.
  Naive timestamps are rejected.
- **Granularity**: Timestamps must align to the timeframe boundary.
  A `1h` candle must have a timestamp at `:00` minutes.
- **Ordering**: Candles must be in strict chronological ascending order
  within each pair/exchange/timeframe group.
- **Uniqueness**: The combination of (pair, exchange, timeframe, timestamp)
  must be unique within a group.
  Duplicate timestamps for the same group are rejected.

---

## 4. OHLCV Finite-Value and Price-Consistency Validation

ALL of the following must hold for every candle:

- `open`, `high`, `low`, `close` are finite floats (not NaN, not infinity).
- `volume` is a finite non-negative float.
- `open`, `high`, `low`, `close` are non-negative.
- `high >= max(open, close)` — high is at least the extreme of open/close.
- `low <= min(open, close)` — low is at most the extreme of open/close.
- `close` is between `low` and `high` (inclusive).

Violations produce typed rejection records, not silent corrections.

---

## 5. Missing Candles, Gaps, Duplicates, and Partial-Candle Policy

- **Missing candles**: Small gaps (≤ 2× the timeframe) are acceptable
  and do not invalidate the series. Larger gaps are flagged.
- **Gaps > 5× the timeframe**: The series is considered incomplete for
  that group. Walk-forward validation must reject data with such gaps
  unless the gap period coincides with verified exchange downtime.
- **Duplicates**: Strictly prohibited. Duplicate timestamps within a
  group produce hard validation failures.
- **Partial candles**: Rejected. Every candle must have a full OHLCV set.
  In-progress (unclosed) candles from real-time feeds must be excluded
  from backtest/walk-forward datasets.

---

## 6. Corporate Action or Symbol-Transition Policy

- **Symbol changes** (e.g., `BTC/USDT` → `BTC/USDC`): Each symbol variant
  is treated as a separate pair. Cross-symbol continuity is not assumed.
- **Reverse splits / consolidations**: If a symbol changes its tick size,
  units, or decimal places in a way that would make pre-event candle prices
  non-comparable with post-event prices, the two periods are treated as
  separate series with an explicit transition marker.
- **Futures funding rates**: For perpetual futures, funding-rate data
  must be associated with the candle series but does not modify OHLCV.

---

## 7. Pair, Exchange, Timeframe, and Source Provenance

Every dataset must carry:

- `pair`: Canonical normalized pair name.
- `exchange`: Canonical exchange name from a known allowlist.
- `timeframe`: Canonical interval identifier.
- `source`: A human-readable source description.
- `source_fingerprint`: A content-hash of the raw source (used for
  deduplication and cache validation).

---

## 8. Content Hashes and Immutable Raw-Cache Policy

- Each raw source file must have a content hash (SHA-256) recorded at
  ingestion time.
- The raw cache is **immutable**: once ingested, rows are never updated
  in place. If re-ingestion is required, a new cache version is created
  with a new schema version.
- The content hash of the raw source is part of the cache metadata.

---

## 9. Derived-Cache Rebuildability

- Derived caches (aggregated statistics, feature matrices) must be
  rebuildable from the raw immutable cache.
- The build process must be deterministic: same raw cache + same code +
  same config = byte-identical derived cache.
- Build parameters are recorded in cache metadata.

---

## 10. Read-Only Ingestion Boundaries

- The ingestion pipeline **never modifies** the raw source data.
- The ingestion pipeline **never writes** to the exchange, the filesystem
  outside the designated cache directory, or any operational database.
- The ingestion pipeline **never calls** exchange trading endpoints.
- All ingestion is `mode=ro` with respect to the source.
- The ingestion process must fail closed if any of these boundaries
  cannot be enforced for a given source.

---

## 11. Backtest and Walk-Forward Split Requirements

- Backtest data must be split into **training** (in-sample) and **test**
  (out-of-sample) periods.
- The split must be temporal: training data is strictly older than
  test data.
- Walk-forward validation requires **N windows**, each with a training
  segment and a test segment of defined lengths.
- Training segments must not overlap with test segments.
- Minimum training segment length: 90 days.
- Minimum test segment length: 30 days.
- Walk-forward window count: at least 3.
- A gap of at least 1 candle must exist between training and test
  segments to prevent information leakage from adjacent periods.

---

## 12. Look-Ahead, Survivorship, Leakage, and Timestamp-Alignment Controls

- **Look-ahead**: Prohibited. All features used in a training candle must
  be computable from data available at or before the candle's timestamp.
- **Survivorship bias**: All assets that existed during the training period
  must be included, even if they were later delisted.
- **Leakage**: No future data may be used to inform a past decision.
  This includes:
  - Using future returns to label past candles.
  - Using future volatility to filter past candles.
  - Using data from trading sessions that had not yet occurred.
- **Timestamp alignment**: All features must be aligned to the
  candle's open timestamp. Forward-filled values are acceptable only
  for stationary or slow-moving features.

---

## 13. Fail-Closed Behavior for Insufficient or Conflicting Data

If any of the following conditions is met, the backtest/walk-forward
pipeline must refuse to start and produce a typed error:

- Fewer than the minimum required candles for at least one pair/exchange/
  timeframe group.
- Any group has gaps > 5× the timeframe not explained by exchange downtime.
- Any group has duplicate timestamps.
- Any candle fails OHLCV consistency validation.
- The training segment has fewer candles than the minimum required.
- Fewer walk-forward windows than the minimum required.
- The walk-forward configuration produces overlapping training segments
  or test segments.

---

## 14. Backtest and Walk-Forward Acceptance-Threshold Review

- Backtests with fewer than 30 trades on the test segment are considered
  non-significant and must not trigger weight proposals.
- Walk-forward runs where more than 30% of windows show negative
  out-of-sample returns are considered failing and must not trigger
  proposals.
- Sharpe ratio < 0.5 on the test segment is a yellow flag.
- Maximum drawdown > 30% on the test segment is a red flag.
- These thresholds are review parameters, not hard rejections — they
  may be refined through SI v2 proposal policy (issue #35).

---

## Specification Version

`schema_version = "1.0"`
