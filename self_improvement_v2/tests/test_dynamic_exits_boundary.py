"""Boundary tests for dynamic_exits.py — edge cases, normalization, serialization.

Tests cover the remaining ~16% uncovered lines:
- Unsupported direction/mode
- Inconsistent bollinger values
- Maximum stop < minimum risk distance
- Stop loss / take profit <= 0
- Risk/reward distance <= 0
- Negative candle count
- Direction/mode normalization edge cases
- to_dict serialization
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from si_v2.risk.dynamic_exits import (
    DynamicExitResult,
    calculate_dynamic_exit,
    calculate_dynamic_exit_from_row,
)

D = Decimal


class TestUnsupportedDirection:
    def test_unknown_direction_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="unknown", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_direction" in result.reason_codes

    def test_empty_direction_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_direction" in result.reason_codes

    def test_none_direction_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction=None, mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_direction" in result.reason_codes

    def test_int_direction_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction=123, mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_direction" in result.reason_codes


class TestUnsupportedMode:
    def test_unknown_mode_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="unknown",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_mode" in result.reason_codes

    def test_empty_mode_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_mode" in result.reason_codes

    def test_none_mode_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode=None,
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "unsupported_mode" in result.reason_codes


class TestInconsistentBollingerValues:
    def test_upper_not_greater_than_mid_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="bollinger_distance",
            bollinger_upper=D("100"), bollinger_mid=D("100"), bollinger_lower=D("95"),
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "inconsistent_bollinger_values" in result.reason_codes

    def test_mid_not_greater_than_lower_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="bollinger_distance",
            bollinger_upper=D("110"), bollinger_mid=D("95"), bollinger_lower=D("95"),
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "inconsistent_bollinger_values" in result.reason_codes

    def test_reversed_bollinger_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="bollinger_distance",
            bollinger_upper=D("95"), bollinger_mid=D("100"), bollinger_lower=D("110"),
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "inconsistent_bollinger_values" in result.reason_codes


class TestMaximumStopDistance:
    def test_max_stop_less_than_min_risk_blocks(self) -> None:
        """When max_stop_distance < min_risk_distance, should block."""
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("5"), maximum_stop_distance=D("3"),
            candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes

    def test_max_stop_zero_blocks(self) -> None:
        """Zero max_stop_distance should block."""
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), maximum_stop_distance=D("0"),
            candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes

    def test_max_stop_negative_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), maximum_stop_distance=D("-1"),
            candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes


class TestNegativeCandleCount:
    def test_negative_candle_count_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=-5, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes

    def test_zero_minimum_candles_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=0,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes

    def test_negative_minimum_candles_blocks(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=-1,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes


class TestStopLossTakeProfitBoundaries:
    def test_stop_loss_at_zero_blocks(self) -> None:
        """Stop loss exactly at zero should block."""
        result = calculate_dynamic_exit(
            entry_price=D("0.000001"), direction="long", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("0.000001"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes

    def test_take_profit_at_zero_blocks(self) -> None:
        """Take profit exactly at zero should block."""
        result = calculate_dynamic_exit(
            entry_price=D("0.000001"), direction="short", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("0.000001"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "blocked"
        assert "invalid_parameters" in result.reason_codes


class TestDirectionNormalization:
    def test_long_uppercase(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="LONG", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "valid"
        assert result.direction == "long"

    def test_short_uppercase(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="SHORT", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "valid"
        assert result.direction == "short"

    def test_long_with_whitespace(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="  long  ", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "valid"
        assert result.direction == "long"


class TestModeNormalization:
    def test_fixed_uppercase(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="FIXED",
            stop_multiplier=D("1"), take_profit_multiplier=D("1"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "valid"
        assert result.mode == "fixed"

    def test_atr_with_whitespace(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="  atr  ",
            atr=D("2"), stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        assert result.status == "valid"
        assert result.mode == "atr"


class TestToDictSerialization:
    def test_valid_result_to_dict(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="atr",
            atr=D("2"), stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        d = result.to_dict()
        assert d["status"] == "valid"
        assert d["stop_loss"] == "98.000000"
        assert d["take_profit"] == "104.000000"
        assert d["risk_reward_ratio"] == "2.000000"
        assert d["reason_codes"] == []

    def test_blocked_result_to_dict(self) -> None:
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="unknown", mode="fixed",
            stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("1"), candle_count=50, minimum_candles=20,
        )
        d = result.to_dict()
        assert d["status"] == "blocked"
        assert d["stop_loss"] is None
        assert d["take_profit"] is None
        assert "unsupported_direction" in d["reason_codes"]

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce JSON-serializable output."""
        import json
        result = calculate_dynamic_exit(
            entry_price=D("100"), direction="long", mode="atr",
            atr=D("2"), stop_multiplier=D("1"), take_profit_multiplier=D("2"),
            minimum_risk_distance=D("0.5"), candle_count=50, minimum_candles=20,
        )
        d = result.to_dict()
        # Should not raise
        json.dumps(d)


class TestFromRowEdgeCases:
    def test_row_with_unsupported_mode(self) -> None:
        row = {
            "entry_price": D("100"), "direction": "long", "mode": "unknown",
            "stop_multiplier": D("1"), "take_profit_multiplier": D("2"),
            "minimum_risk_distance": D("1"), "candle_count": 50, "minimum_candles": 20,
        }
        result = calculate_dynamic_exit_from_row(row)
        assert result.status == "blocked"
        assert "unsupported_mode" in result.reason_codes

    def test_row_with_unsupported_direction(self) -> None:
        row = {
            "entry_price": D("100"), "direction": "unknown", "mode": "fixed",
            "stop_multiplier": D("1"), "take_profit_multiplier": D("2"),
            "minimum_risk_distance": D("1"), "candle_count": 50, "minimum_candles": 20,
        }
        result = calculate_dynamic_exit_from_row(row)
        assert result.status == "blocked"
        assert "unsupported_direction" in result.reason_codes

    def test_row_missing_columns_fixed(self) -> None:
        """Missing common columns should block."""
        row = {"entry_price": D("100"), "direction": "long", "mode": "fixed"}
        result = calculate_dynamic_exit_from_row(row)
        assert result.status == "blocked"
        assert "missing_columns" in result.reason_codes


class TestDynamicExitResultDataclass:
    def test_frozen_dataclass(self) -> None:
        """DynamicExitResult should be frozen (immutable)."""
        result = DynamicExitResult(
            status="valid", mode="fixed", direction="long",
            stop_loss=None, take_profit=None,
            risk_distance=None, reward_distance=None,
            risk_reward_ratio=None,
        )
        with pytest.raises(AttributeError):
            result.status = "blocked"  # type: ignore[misc]

    def test_repr(self) -> None:
        result = DynamicExitResult(
            status="valid", mode="fixed", direction="long",
            stop_loss=D("98"), take_profit=D("104"),
            risk_distance=D("2"), reward_distance=D("4"),
            risk_reward_ratio=D("2"),
        )
        r = repr(result)
        assert "valid" in r
        assert "long" in r
