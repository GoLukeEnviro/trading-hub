from __future__ import annotations

from decimal import Decimal

from si_v2.risk.dynamic_exits import (
    calculate_dynamic_exit,
    calculate_dynamic_exit_from_row,
)

D = Decimal


def test_long_atr_produces_stop_below_entry_and_take_profit_above_entry() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=D("2"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.direction == "long"
    assert result.mode == "atr"
    assert result.stop_loss == D("98")
    assert result.take_profit == D("104")
    assert result.risk_distance == D("2")
    assert result.reward_distance == D("4")
    assert result.risk_reward_ratio == D("2")
    assert result.reason_codes == ()


def test_short_atr_produces_stop_above_entry_and_take_profit_below_entry() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="short",
        mode="atr",
        atr=D("2"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.stop_loss == D("102")
    assert result.take_profit == D("96")
    assert result.risk_distance == D("2")
    assert result.reward_distance == D("4")
    assert result.risk_reward_ratio == D("2")
    assert result.reason_codes == ()


def test_long_bollinger_mode_uses_lower_mid_upper_distance_correctly() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="bollinger_distance",
        bollinger_lower=D("95"),
        bollinger_mid=D("100"),
        bollinger_upper=D("110"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("1"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.stop_loss == D("95")
    assert result.take_profit == D("110")
    assert result.risk_distance == D("5")
    assert result.reward_distance == D("10")
    assert result.risk_reward_ratio == D("2")


def test_short_bollinger_mode_uses_upper_mid_lower_distance_correctly() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="short",
        mode="bollinger_distance",
        bollinger_lower=D("95"),
        bollinger_mid=D("100"),
        bollinger_upper=D("110"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("1"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.stop_loss == D("110")
    assert result.take_profit == D("95")
    assert result.risk_distance == D("10")
    assert result.reward_distance == D("5")
    assert result.risk_reward_ratio == D("0.5")


def test_fixed_mode_works_deterministically() -> None:
    kwargs = dict(
        entry_price=D("100"),
        direction="long",
        mode="fixed",
        stop_multiplier=D("1"),
        take_profit_multiplier=D("1"),
        minimum_risk_distance=D("1.2345665"),
        candle_count=50,
        minimum_candles=20,
    )

    first = calculate_dynamic_exit(**kwargs)
    second = calculate_dynamic_exit(**kwargs)

    assert first == second
    assert first.status == "valid"
    assert first.stop_loss == D("98.765434")
    assert first.take_profit == D("101.234566")
    assert first.risk_distance == D("1.234566")
    assert first.reward_distance == D("1.234566")
    assert first.risk_reward_ratio == D("1")


def test_missing_atr_blocks_atr_mode() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=None,
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "missing_atr" in result.reason_codes
    assert result.stop_loss is None
    assert result.take_profit is None


def test_missing_bollinger_values_blocks_bollinger_mode() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="bollinger_distance",
        bollinger_lower=None,
        bollinger_mid=D("100"),
        bollinger_upper=D("110"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("1"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "missing_bollinger_values" in result.reason_codes


def test_zero_entry_price_blocks() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("0"),
        direction="long",
        mode="fixed",
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("1"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "invalid_entry_price" in result.reason_codes


def test_negative_atr_blocks() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=D("-1"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("0.5"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "invalid_atr" in result.reason_codes


def test_insufficient_candles_blocks() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=D("2"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("0.5"),
        candle_count=5,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "insufficient_candles" in result.reason_codes


def test_low_volatility_minimum_distance_protection() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=D("0.1"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("2"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.risk_distance == D("2")
    assert result.stop_loss == D("98")
    assert result.reward_distance == D("0.2")
    assert "minimum_risk_distance_applied" in result.reason_codes


def test_high_volatility_max_distance_protection_if_configured() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="atr",
        atr=D("50"),
        stop_multiplier=D("1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("1"),
        maximum_stop_distance=D("10"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.risk_distance == D("10")
    assert result.stop_loss == D("90")
    assert "maximum_stop_distance_applied" in result.reason_codes


def test_deterministic_rounding_uses_half_even_quantization() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="fixed",
        stop_multiplier=D("1"),
        take_profit_multiplier=D("1"),
        minimum_risk_distance=D("1.2345665"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "valid"
    assert result.risk_distance == D("1.234566")
    assert result.take_profit == D("101.234566")
    assert result.stop_loss == D("98.765434")


def test_missing_columns_block_from_row_mapping_input() -> None:
    row = {
        "entry_price": D("100"),
        "direction": "long",
        "mode": "atr",
        "stop_multiplier": D("1"),
        "take_profit_multiplier": D("2"),
        "minimum_risk_distance": D("0.5"),
        "candle_count": 50,
        "minimum_candles": 20,
    }

    result = calculate_dynamic_exit_from_row(row)

    assert result.status == "blocked"
    assert "missing_columns" in result.reason_codes


def test_negative_multiplier_blocks() -> None:
    result = calculate_dynamic_exit(
        entry_price=D("100"),
        direction="long",
        mode="fixed",
        stop_multiplier=D("-1"),
        take_profit_multiplier=D("2"),
        minimum_risk_distance=D("1"),
        candle_count=50,
        minimum_candles=20,
    )

    assert result.status == "blocked"
    assert "invalid_parameters" in result.reason_codes
