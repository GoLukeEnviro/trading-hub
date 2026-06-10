"""Test guardrails: safe parameters, forbidden keys, and validation."""

from __future__ import annotations

from si_v2.propose.safe_parameters import (
    FORBIDDEN_KEYS,
    guard_candidate,
    validate_safe_parameter,
)


class TestGuardCandidate:
    """Tests for the guard_candidate function."""

    def test_all_safe_keys_passes(self) -> None:
        """All SAFE_PARAMETERS keys should pass guard."""
        params = {"rsi_period": 14, "stoploss_pct": -0.02, "cooldown_candles": 5}
        assert guard_candidate(params) is True

    def test_all_safe_keys_full_set(self) -> None:
        """All 6 safe parameters should pass."""
        params = {
            "rsi_period": 14,
            "stoploss_pct": -0.02,
            "take_profit_pct": 0.035,
            "stake_factor": 1.0,
            "max_open_trades": 2,
            "cooldown_candles": 9,
        }
        assert guard_candidate(params) is True

    def test_forbidden_key_fails(self) -> None:
        """Parameters with forbidden keys should fail."""
        params = {"dry_run": True}
        assert guard_candidate(params) is False

    def test_mixed_keys_fails(self) -> None:
        """Mix of safe and forbidden keys should fail."""
        params = {"rsi_period": 14, "exchange": "binance"}
        assert guard_candidate(params) is False

    def test_unknown_key_fails(self) -> None:
        """Unknown keys not in SAFE_PARAMETERS should fail."""
        params = {"unknown_param": 42}
        assert guard_candidate(params) is False

    def test_empty_params_fails(self) -> None:
        """Empty parameter dict should fail."""
        assert guard_candidate({}) is False

    def test_each_forbidden_key_fails(self) -> None:
        """Every key in FORBIDDEN_KEYS should fail individually."""
        for key in FORBIDDEN_KEYS:
            assert guard_candidate({key: "value"}) is False


class TestValidateSafeParameter:
    """Tests for the validate_safe_parameter function."""

    def test_rsi_period_valid(self) -> None:
        """Valid rsi_period should pass."""
        assert validate_safe_parameter("rsi_period", 14) is True

    def test_rsi_period_too_low(self) -> None:
        """rsi_period below range should fail."""
        assert validate_safe_parameter("rsi_period", 1) is False

    def test_rsi_period_too_high(self) -> None:
        """rsi_period above range should fail."""
        assert validate_safe_parameter("rsi_period", 51) is False

    def test_rsi_period_boundary_low(self) -> None:
        """rsi_period at lower boundary should pass."""
        assert validate_safe_parameter("rsi_period", 2) is True

    def test_rsi_period_boundary_high(self) -> None:
        """rsi_period at upper boundary should pass."""
        assert validate_safe_parameter("rsi_period", 50) is True

    def test_stoploss_pct_valid(self) -> None:
        """Valid stoploss_pct should pass."""
        assert validate_safe_parameter("stoploss_pct", -0.02) is True

    def test_stoploss_pct_boundary_low(self) -> None:
        """stoploss_pct at lower boundary should pass."""
        assert validate_safe_parameter("stoploss_pct", -0.5) is True

    def test_stoploss_pct_boundary_high(self) -> None:
        """stoploss_pct at upper boundary should pass."""
        assert validate_safe_parameter("stoploss_pct", -0.001) is True

    def test_stoploss_pct_positive_fails(self) -> None:
        """Positive stoploss_pct should fail."""
        assert validate_safe_parameter("stoploss_pct", 0.01) is False

    def test_take_profit_pct_valid(self) -> None:
        """Valid take_profit_pct should pass."""
        assert validate_safe_parameter("take_profit_pct", 0.035) is True

    def test_take_profit_pct_boundary_low(self) -> None:
        """take_profit_pct at lower boundary should pass."""
        assert validate_safe_parameter("take_profit_pct", 0.001) is True

    def test_take_profit_pct_boundary_high(self) -> None:
        """take_profit_pct at upper boundary should pass."""
        assert validate_safe_parameter("take_profit_pct", 0.5) is True

    def test_stake_factor_valid(self) -> None:
        """Valid stake_factor should pass."""
        assert validate_safe_parameter("stake_factor", 1.0) is True

    def test_stake_factor_too_low(self) -> None:
        """stake_factor below range should fail."""
        assert validate_safe_parameter("stake_factor", 0.05) is False

    def test_stake_factor_too_high(self) -> None:
        """stake_factor above range should fail."""
        assert validate_safe_parameter("stake_factor", 6.0) is False

    def test_max_open_trades_valid(self) -> None:
        """Valid max_open_trades should pass."""
        assert validate_safe_parameter("max_open_trades", 5) is True

    def test_max_open_trades_boundary_low(self) -> None:
        """max_open_trades at lower boundary should pass."""
        assert validate_safe_parameter("max_open_trades", 1) is True

    def test_max_open_trades_boundary_high(self) -> None:
        """max_open_trades at upper boundary should pass."""
        assert validate_safe_parameter("max_open_trades", 20) is True

    def test_cooldown_candles_valid(self) -> None:
        """Valid cooldown_candles should pass."""
        assert validate_safe_parameter("cooldown_candles", 10) is True

    def test_cooldown_candles_boundary_low(self) -> None:
        """cooldown_candles at lower boundary should pass."""
        assert validate_safe_parameter("cooldown_candles", 0) is True

    def test_cooldown_candles_boundary_high(self) -> None:
        """cooldown_candles at upper boundary should pass."""
        assert validate_safe_parameter("cooldown_candles", 100) is True

    def test_unknown_parameter_fails(self) -> None:
        """Unknown parameter name should fail."""
        assert validate_safe_parameter("unknown_param", 42) is False
