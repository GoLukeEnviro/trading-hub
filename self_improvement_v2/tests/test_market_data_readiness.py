"""Tests for market-data readiness (issue #34).

Validates the canonical candle schema and the OHLCV consistency rules
defined in the market data readiness specification.

Covers:
- Valid candles accepted
- NaN/infinity rejected
- Negative price rejected
- High < max(open, close) rejected
- Low > min(open, close) rejected
- Close outside [low, high] rejected
- Naive timestamp rejected
- Duplicate timestamp rejected
- Malformed pair/exchange/timeframe rejected
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# ---------------------------------------------------------------------------
# Canonical candle schema
# ---------------------------------------------------------------------------

CANONICAL_CANDLE_FIELDS = frozenset({
    "pair", "exchange", "timeframe", "timestamp",
    "open", "high", "low", "close", "volume",
})

REQUIRED_CANDLE_FIELDS = frozenset({
    "pair", "exchange", "timeframe", "timestamp",
    "open", "high", "low", "close", "volume",
})

STRING_FIELDS = frozenset({"pair", "exchange", "timeframe"})
FLOAT_FIELDS = frozenset({"open", "high", "low", "close", "volume"})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class CandleValidationError(ValueError):
    """Typed candle validation error."""


def validate_candle(candle: dict) -> list[str]:
    """Validate a single candle against the canonical schema.

    Returns a list of error messages. Empty list = valid.
    """
    errors: list[str] = []

    # Check all required fields present
    for field in REQUIRED_CANDLE_FIELDS:
        if field not in candle:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # String fields: non-empty
    for field in STRING_FIELDS:
        val = candle.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{field} must be a non-empty string, got {val!r}")

    # Timestamp: timezone-aware UTC
    ts = candle.get("timestamp")
    if ts is None:
        errors.append("timestamp is None")
    elif not isinstance(ts, datetime):
        errors.append(f"timestamp must be a datetime, got {type(ts).__name__}")
    else:
        if ts.tzinfo is None:
            errors.append("timestamp must be timezone-aware (got naive datetime)")
        elif ts.tzinfo != UTC:
            errors.append(f"timestamp must be in UTC, got {ts.tzinfo}")

    # Float fields: finite, non-negative where applicable
    for field in FLOAT_FIELDS:
        val = candle.get(field)
        if val is None:
            errors.append(f"{field} is None")
            continue
        if isinstance(val, bool):
            errors.append(f"{field} is bool, not a valid float")
            continue
        if not isinstance(val, (int, float)):
            errors.append(f"{field} must be a number, got {type(val).__name__}: {val!r}")
            continue
        fval = float(val)
        if fval != fval:  # NaN
            errors.append(f"{field} is NaN")
        if fval == float("inf") or fval == float("-inf"):
            errors.append(f"{field} is infinite")
        if fval < 0 and field in ("volume",):
            errors.append(f"{field} is negative ({fval})")

    # Price fields: non-negative
    for field in ("open", "high", "low", "close"):
        val = candle.get(field)
        if isinstance(val, (int, float)):
            if float(val) < 0:
                errors.append(f"{field} is negative ({float(val)})")

    # Consistency: high >= max(open, close)
    try:
        high = float(candle["high"])
        open_p = float(candle["open"])
        close = float(candle["close"])
        low = float(candle["low"])

        if high < max(open_p, close):
            errors.append(
                f"high ({high}) < max(open={open_p}, close={close})"
            )

        # Consistency: low <= min(open, close)
        if low > min(open_p, close):
            errors.append(
                f"low ({low}) > min(open={open_p}, close={close})"
            )

        # Consistency: close between low and high
        if close < low or close > high:
            errors.append(
                f"close ({close}) outside [low={low}, high={high}]"
            )
    except (TypeError, ValueError):
        errors.append("Cannot validate OHLCV consistency — non-numeric values")

    return errors


def validate_candle_sequence(candles: list[dict]) -> list[str]:
    """Validate a sequence of candles for ordering, gaps, and duplicates.

    Returns a list of error messages. Empty list = valid.
    """
    errors: list[str] = []
    if not candles:
        return ["Empty candle sequence"]

    seen_timestamps: dict[str, set[str]] = {}  # pair -> set of isoformat timestamps

    prev_ts: datetime | None = None
    prev_pair: str | None = None

    for i, candle in enumerate(candles):
        pair = candle.get("pair", "?")
        ts = candle.get("timestamp")

        if isinstance(ts, datetime):
            ts_iso = ts.isoformat()

            # Duplicate check within pair
            pair_ts_set = seen_timestamps.setdefault(pair, set())
            if ts_iso in pair_ts_set:
                errors.append(f"Candle {i} ({pair} @ {ts_iso}): duplicate timestamp")
            pair_ts_set.add(ts_iso)

            # Ordering check (within same pair)
            if prev_pair is not None and prev_pair == pair and prev_ts is not None:
                if ts < prev_ts:
                    errors.append(
                        f"Candle {i} ({pair} @ {ts_iso}): "
                        f"timestamp before previous ({prev_ts.isoformat()})"
                    )

            prev_ts = ts
            prev_pair = pair

    return errors


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_valid_candle(**overrides: object) -> dict:
    """Create a valid candle with optional overrides."""
    candle = {
        "pair": "BTC/USDT",
        "exchange": "binance",
        "timeframe": "1h",
        "timestamp": datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        "open": 50000.0,
        "high": 51000.0,
        "low": 49500.0,
        "close": 50500.0,
        "volume": 100.0,
    }
    candle.update(overrides)
    return candle


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCandleSchema:
    def test_valid_candle_accepted(self) -> None:
        """A valid candle must produce no errors."""
        candle = _make_valid_candle()
        errors = validate_candle(candle)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_missing_required_field(self) -> None:
        """Missing required field must produce an error."""
        candle = _make_valid_candle()
        del candle["close"]
        errors = validate_candle(candle)
        assert any("Missing" in e and "close" in e for e in errors)

    def test_nan_price_rejected(self) -> None:
        """NaN price must be rejected."""
        candle = _make_valid_candle(open=float("nan"))
        errors = validate_candle(candle)
        assert any("NaN" in e for e in errors)

    def test_infinity_price_rejected(self) -> None:
        """Infinity price must be rejected."""
        candle = _make_valid_candle(high=float("inf"))
        errors = validate_candle(candle)
        assert any("infinite" in e for e in errors)

    def test_negative_volume_rejected(self) -> None:
        """Negative volume must be rejected."""
        candle = _make_valid_candle(volume=-1.0)
        errors = validate_candle(candle)
        assert any("negative" in e for e in errors)

    def test_negative_price_rejected(self) -> None:
        """Negative price must be rejected."""
        candle = _make_valid_candle(open=-100.0)
        errors = validate_candle(candle)
        assert any("negative" in e for e in errors)

    def test_high_below_max_open_close(self) -> None:
        """High below max(open, close) must be rejected."""
        candle = _make_valid_candle(high=49000.0, open=50000.0, close=51000.0)
        errors = validate_candle(candle)
        assert any("high" in e and "max" in e for e in errors)

    def test_low_above_min_open_close(self) -> None:
        """Low above min(open, close) must be rejected."""
        candle = _make_valid_candle(low=52000.0, open=50000.0, close=49000.0)
        errors = validate_candle(candle)
        assert any("low" in e and "min" in e for e in errors)

    def test_close_outside_range(self) -> None:
        """Close outside [low, high] must be rejected."""
        candle = _make_valid_candle(close=55000.0, high=52000.0, low=48000.0)
        errors = validate_candle(candle)
        assert any("close" in e and "outside" in e for e in errors)

    def test_naive_timestamp_rejected(self) -> None:
        """Naive timestamp must be rejected."""
        candle = _make_valid_candle(timestamp=datetime(2026, 6, 1, 0, 0))
        errors = validate_candle(candle)
        assert any("naive" in e for e in errors)

    def test_non_utc_timestamp_rejected(self) -> None:
        """Non-UTC timestamp must be rejected."""
        from datetime import timezone, timedelta

        candle = _make_valid_candle(
            timestamp=datetime(2026, 6, 1, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        )
        errors = validate_candle(candle)
        assert any("UTC" in e for e in errors)

    def test_bool_price_rejected(self) -> None:
        """Bool price must be rejected."""
        candle = _make_valid_candle(open=True)
        errors = validate_candle(candle)
        assert any("bool" in e for e in errors)

    def test_empty_pair_rejected(self) -> None:
        """Empty pair string must be rejected."""
        candle = _make_valid_candle(pair="")
        errors = validate_candle(candle)
        assert any("pair" in e for e in errors)


class TestCandleSequence:
    def test_empty_sequence(self) -> None:
        """Empty sequence must be rejected."""
        errors = validate_candle_sequence([])
        assert len(errors) > 0

    def test_duplicate_timestamps(self) -> None:
        """Duplicate timestamps within pair must be rejected."""
        ts = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        candles = [
            _make_valid_candle(pair="BTC/USDT", timestamp=ts),
            _make_valid_candle(pair="BTC/USDT", timestamp=ts),
        ]
        errors = validate_candle_sequence(candles)
        assert any("duplicate" in e.lower() for e in errors)

    def test_out_of_order(self) -> None:
        """Out-of-order timestamps must be rejected."""
        candles = [
            _make_valid_candle(
                pair="BTC/USDT",
                timestamp=datetime(2026, 6, 2, 0, 0, tzinfo=UTC),
            ),
            _make_valid_candle(
                pair="BTC/USDT",
                timestamp=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
            ),
        ]
        errors = validate_candle_sequence(candles)
        assert any("before" in e for e in errors)

    def test_valid_sequence(self) -> None:
        """Valid chronological sequence must produce no errors."""
        candles = [
            _make_valid_candle(
                pair="BTC/USDT",
                timestamp=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
            ),
            _make_valid_candle(
                pair="BTC/USDT",
                timestamp=datetime(2026, 6, 1, 1, 0, tzinfo=UTC),
            ),
        ]
        errors = validate_candle_sequence(candles)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_different_pairs_no_conflict(self) -> None:
        """Same timestamp for different pairs is allowed."""
        ts = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        candles = [
            _make_valid_candle(pair="BTC/USDT", timestamp=ts),
            _make_valid_candle(pair="ETH/USDT", timestamp=ts),
        ]
        errors = validate_candle_sequence(candles)
        assert len(errors) == 0, f"Unexpected errors: {errors}"
