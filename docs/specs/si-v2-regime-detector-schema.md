# SI v2 Canonical Regime Detector Schema

**Status:** Draft Specification  
**Owner:** Self-Improvement Intelligence Layer — Phase 1  
**Last updated:** 2026-06-11  
**Parent issue:** [#55](https://github.com/GoLukeEnviro/trading-hub/issues/55)  
**Depends on:** [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48)

## Purpose

Define the canonical regime-detection event schema and integration boundary used by
Shadowlock, attribution, ai4trade/Rainbow signals, and future meta-learning.
This document is a **design/spec-first artifact** — it defines the contract before
any runtime implementation proceeds.

---

## 1. Regime Event Schema

### 1.1 Canonical Regime Labels

| Label       | Description                                | Typical Condition                                              |
|-------------|--------------------------------------------|----------------------------------------------------------------|
| `BULLISH`   | Strong directional upward movement         | ADX > 25, price above major EMAs, positive slope               |
| `BEARISH`   | Strong directional downward movement       | ADX > 25, price below major EMAs, negative slope               |
| `NEUTRAL`   | No strong directional conviction           | ADX <= 25, price within bands, ranging / weak trend            |
| `UNKNOWN`   | Insufficient data to determine regime      | Missing OHLCV, NaN rates, or degraded data source              |

### 1.2 Schema Definition (JSON / Pydantic-compatible)

```json
{
  "regime": "BULLISH | BEARISH | NEUTRAL | UNKNOWN",
  "confidence": 0.0,
  "timeframe": "15m",
  "data_source": "bitget_futures",
  "detected_at": "2026-06-11T12:00:00Z",
  "model_version": "v1.0.0",
  "schema_version": "1",
  "metadata": {}
}
```

#### Field Descriptions

| Field            | Type      | Required | Description                                                     |
|------------------|-----------|----------|-----------------------------------------------------------------|
| `regime`         | `string`  | yes      | One of: `BULLISH`, `BEARISH`, `NEUTRAL`, `UNKNOWN`             |
| `confidence`     | `float`   | yes      | Confidence score in `[0.0, 1.0]` inclusive. `0.0` for UNKNOWN. |
| `timeframe`      | `string`  | yes      | Candlestick timeframe the regime was detected on (e.g. `15m`, `1h`, `4h`). |
| `data_source`    | `string`  | yes      | Identifier of the data provider (e.g. `bitget_futures`, `binance_spot`). |
| `detected_at`    | `string`  | yes      | ISO 8601 UTC timestamp of when the regime was determined.      |
| `model_version`  | `string`  | yes      | Semver of the regime detection model that produced this event. |
| `schema_version` | `string`  | yes      | Version of this schema document (integer string for easy comparison). |
| `metadata`       | `object`  | no       | Optional freeform bag for provider-specific metrics (ADX, ATR%, EMA slope, etc.). |

### 1.3 Pydantic Model (Reference)

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class RegimeEvent(BaseModel):
    """A canonical regime detection event."""

    regime: str = Field(
        ...,
        description="One of: BULLISH, BEARISH, NEUTRAL, UNKNOWN",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0.0, 1.0]",
    )
    timeframe: str = Field(
        ...,
        description="Candlestick timeframe (e.g. 15m, 1h, 4h)",
    )
    data_source: str = Field(
        ...,
        description="Data provider identifier",
    )
    detected_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp",
    )
    model_version: str = Field(
        ...,
        description="Semver of the detection model",
    )
    schema_version: str = Field(
        default="1",
        description="Schema version string",
    )
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Provider-specific metrics bag",
    )

    def __hash__(self) -> int:
        return hash(
            (self.regime, self.detected_at, self.timeframe, self.data_source),
        )
```

### 1.4 Versioning Strategy

- `schema_version` increments when backward-incompatible changes are made to
  the event schema (field removal, type change, required→optional flip).
- `model_version` follows SemVer for the regime detection model/algorithm.
- Backward-compatible additions (new optional field, new regime label variant)
  bump `model_version` minor and leave `schema_version` unchanged.
- Schema migration requires a reviewed migration plan per the hard safety rules.

---

## 2. Regime-to-Signal/Trade Attachment Rules

### 2.1 Attachment to Signals

Every `CryptoSignal` produced by the Rainbow Intelligence Engine **must** carry
a `regime` field matching one of the four canonical labels, plus the originating
`RegimeEvent` reference.

```json
{
  "signal_id": "sig_abc123",
  "action": "long",
  "confidence": 0.72,
  "regime": "BULLISH",
  "regime_event": {
    "detected_at": "2026-06-11T12:00:00Z",
    "confidence": 0.85,
    "timeframe": "15m",
    "model_version": "v1.0.0"
  }
}
```

**Rules:**
1. A signal **must not** exceed its regime event's confidence — i.e. `signal.confidence <= regime_event.confidence`.
2. When `regime == "UNKNOWN"`, the signal must default to `regime = "NEUTRAL"` for
   downstream compatibility, but MUST preserve `UNKNOWN` in the attachment metadata.
3. Each signal references exactly **one** regime event (the most recent at decision time).

### 2.2 Attachment to Trades

Trades recorded by Shadowlock **must** embed the regime active at entry time.

```json
{
  "trade_id": "trade_def456",
  "entry_time": "2026-06-11T12:15:00Z",
  "entry_regime": "BULLISH",
  "entry_regime_event": { ... }
}
```

**Rules:**
1. Entry regime is snapshotted once at trade open and does not change for the
   lifetime of the trade.
2. Exit/close may record `exit_regime` independently for attribution analysis.
3. Regime-hybrid strategies may use the entry regime to select strategy branch.

### 2.3 Attachment to Decisions

Decisions (entry, exit, hold, cancel) from RiskGuard/Judge **should** reference
the regime that was active at decision time for auditability.

```
decision_record = {
    "decision_id": "dec_789ghi",
    "action": "block_entry",
    "reason": "regime_confidence_below_threshold",
    "active_regime": "NEUTRAL",
    "regime_event_ref": "..."
}
```

---

## 3. Unknown / Insufficient-Data Behavior

### 3.1 Trigger Conditions

`UNKNOWN` regime is emitted when any of the following hold:

| Condition                        | Example                                                  |
|----------------------------------|----------------------------------------------------------|
| Missing required OHLCV columns   | `close` or `volume` entirely absent                      |
| Excessive NaN / null rate        | More than 30% of window values are NaN                   |
| Degraded data source             | Exchange API returned empty or error response            |
| Fresh connection / cold start    | No historical data cached yet (< 100 candles available)  |
| Model confidence below threshold | Internal confidence < 0.3 (detector-specific)            |

### 3.2 UNKNOWN Emission Rules

1. `UNKNOWN` events carry `confidence = 0.0` and `metadata = {}`.
2. The `data_source` field still identifies the attempted source.
3. Downstream consumers **must not** trade on `UNKNOWN` regimes.
4. When a consumer receives `UNKNOWN`:
   - **Default**: Treat the regime as `NEUTRAL` for compatibility.
   - **Escalate**: Log a warning; if 3+ consecutive `UNKNOWN` events for the
     same market, escalate to the operator via the alert channel.
5. The detector **should** include a `reason` string in `metadata.reason` when
   emitting `UNKNOWN` (e.g. `"insufficient_data"`, `"source_unavailable"`).

### 3.3 Recovery

After emitting `UNKNOWN`, the detector retries on the next cycle. Once
sufficient data is available and confidence meets threshold, it resumes
normal label emission.

---

## 4. Versioning and Compatibility Rules

### 4.1 Schema Version Lifecycle

| Version | Status     | Notes                                      |
|---------|------------|--------------------------------------------|
| `1`     | Current    | Initial canonical schema (this document).  |
| `2`+    | Future     | Requires migration plan per hard rules.    |

### 4.2 Forward Compatibility

New `regime` labels may be added in minor `model_version` bumps only if they
do not conflict with existing label semantics. Downstream consumers **must**
treat unrecognized labels as `NEUTRAL` with a logged warning.

### 4.3 Backward Compatibility

All existing consumers that read `regime` as a string field **must** remain
functional when the schema version is `1`. Field additions are optional-only.
Consumers written against this spec **must**:
- Accept unknown optional fields without error.
- Default `UNKNOWN` to `NEUTRAL` for decision logic.
- Log a warning on `schema_version > 1` but continue processing.

### 4.4 Model Version Rules

| Change Type               | `model_version` Bump | Migration Required |
|---------------------------|----------------------|--------------------|
| New model algorithm       | Minor                | No                 |
| New label addition        | Minor                | No                 |
| Confidence range change   | Major                | Yes                |
| Break existing label semantics | Major           | Yes                |
| Bugfix, no contract change | Patch               | No                 |

---

## 5. Backward Compatibility with Existing Regime-Hybrid Strategy Attachment

### 5.1 Existing v1 Labels → Canonical Mapping

The current `regime-detector-spec.md` (v1.0) defines fine-grained labels. The
canonical v2 schema maps them as follows:

| v1 Label             | v2 Canonical Label | Notes                           |
|----------------------|--------------------|---------------------------------|
| `strong_trend_up`    | `BULLISH`          | High-confidence bullish         |
| `weak_trend_up`      | `BULLISH`          | Lower-confidence bullish        |
| `strong_trend_down`  | `BEARISH`          | High-confidence bearish         |
| `weak_trend_down`    | `BEARISH`          | Lower-confidence bearish        |
| `ranging`            | `NEUTRAL`          | No strong directional signal    |
| `high_volatility`    | `NEUTRAL`          | Treated as uncertain direction  |
| `choppy`             | `NEUTRAL`          | Whipsaw, no conviction          |

### 5.2 Weight Multiplier Mapping

For the existing regime-hybrid strategy (`RegimeSwitchingHybrid_v7_v04_Integration`)
that uses weight multipliers, the canonical labels carry **recommended ranges**:

| Canonical Label | Default Weight Multiplier | Range           |
|-----------------|---------------------------|-----------------|
| `BULLISH`       | `1.10`                    | `[1.00, 1.20]`  |
| `BEARISH`       | `0.85`                    | `[0.70, 1.00]`  |
| `NEUTRAL`       | `0.80`                    | `[0.60, 1.00]`  |
| `UNKNOWN`       | `0.50`                    | `[0.40, 0.60]`  |

### 5.3 Integration Rule

The existing regime-hybrid Freqtrade strategy **may** consume canonical v2
regime labels by reading the `regime` field directly. When the strategy
receives a canonical label it can map to its internal v1 branches, it uses
the corresponding weight multiplier. Unrecognized labels fall through to
`NEUTRAL` behavior.

**No strategy mutation is required** — the translation happens at the
regime-event attachment layer (Shadowlock or signal generator).

---

## Safety and Constraints

- No live trading decisions are made based on this schema alone.
- No automatic weight changes: weight multiplier ranges are recommendations
  only; actual weights are determined by the consuming strategy.
- No schema migration without a reviewed migration plan (enforced by Phase 1
  hard safety rules).
- Runtime reading of regime events is read-only and requires no side effects.

---

## References

- [Issue #55 — Canonical Regime Detector Schema](https://github.com/GoLukeEnviro/trading-hub/issues/55)
- [Existing v1 Spec — docs/specs/regime-detector-spec.md](regime-detector-spec.md)
- [Shadowlock Indexer Spec](shadowlock-indexer-spec.md)
- [Self-Improvement Signal Intelligence Spec](self-improvement-signal-intelligence-spec.md)
- [Phase 1 Readiness Matrix](../state/current-operational-state.md)
