"""ATR-based risk position sizing contract (Phase 1C, Issue #597).

Tests written first (TDD RED). Implementation follows in
:mod:`si_v2.risk.atr_position_sizing`.

A1 scope. No strategy, Freqtrade config, Docker or runtime mutation.
"""
from __future__ import annotations

from dataclasses import asdict

import pytest

from si_v2.risk.atr_position_sizing import (
    SIZING_CAPPED_NOTIONAL,
    SIZING_INVALID_INPUT,
    SIZING_MIN_NOTIONAL_FAIL,
    SIZING_OK,
    PositionSizingInput,
    calculate_position_size,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**overrides) -> PositionSizingInput:
    defaults = dict(
        equity=10_000.0,
        risk_fraction=0.01,       # 1% risk
        atr_value=50.0,            # ATR 50
        atr_multiplier=2.0,        # 2x ATR = 100 stop distance
        entry_price=5000.0,
        min_notional=0.1,          # low enough for standard scenario
        max_notional=1_000_000.0,  # effectively no cap for standard scenarios
        precision=2,
        fee_slippage_pct=0.1,      # 0.1% buffer
        leverage=1.0,
    )
    defaults.update(overrides)
    return PositionSizingInput(**defaults)


# ---------------------------------------------------------------------------
# Normal sizing
# ---------------------------------------------------------------------------


class TestNormalSizing:
    def test_standard_usdt_futures(self) -> None:
        inp = _make_input()
        result = calculate_position_size(inp)
        assert result.status == SIZING_OK
        # allowed_risk = 10000 * 0.01 = 100
        # stop_distance = 50 * 2.0 = 100
        # raw = 100 / 100 = 1.0
        assert result.raw_size == pytest.approx(1.0, rel=1e-9)
        # fee buffer: 1.0 * (1 - 0.001) = 0.999 -> rounded down to 0.99
        assert result.capped_size == pytest.approx(0.99, rel=1e-2)
        assert result.decision == "ACCEPTED"

    def test_low_volatility_larger_position(self) -> None:
        inp = _make_input(atr_value=10.0, atr_multiplier=1.5)
        # risk = 100, stop = 15, raw = 6.666...
        result = calculate_position_size(inp)
        assert result.status == SIZING_OK
        assert result.raw_size == pytest.approx(100.0 / 15.0, rel=1e-9)

    def test_high_volatility_smaller_position(self) -> None:
        inp = _make_input(atr_value=200.0, atr_multiplier=2.0)
        # risk = 100, stop = 400, raw = 0.25
        result = calculate_position_size(inp)
        assert result.raw_size == pytest.approx(0.25, rel=1e-9)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    @pytest.mark.parametrize("bad,field", [
        (0.0, "equity"),
        (-100.0, "equity"),
        (float("nan"), "equity"),
        (float("inf"), "equity"),
    ])
    def test_invalid_equity_rejected(self, bad: float, field: str) -> None:
        inp = _make_input(**{field: bad})
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT

    @pytest.mark.parametrize("bad,field", [
        (0.0, "risk_fraction"),
        (-0.02, "risk_fraction"),
        (1.5, "risk_fraction"),   # > 1.0 (100% risk)
        (float("nan"), "risk_fraction"),
    ])
    def test_invalid_risk_fraction_rejected(self, bad: float, field: str) -> None:
        inp = _make_input(**{field: bad})
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT

    @pytest.mark.parametrize("bad", [0.0, -10.0, float("nan"), float("inf")])
    def test_invalid_atr_rejected(self, bad: float) -> None:
        inp = _make_input(atr_value=bad)
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan")])
    def test_invalid_atr_multiplier_rejected(self, bad: float) -> None:
        inp = _make_input(atr_multiplier=bad)
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT

    @pytest.mark.parametrize("bad", [0.0, -100.0, float("nan")])
    def test_invalid_entry_price_rejected(self, bad: float) -> None:
        inp = _make_input(entry_price=bad)
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT


# ---------------------------------------------------------------------------
# Caps — portfolio / bot / order
# ---------------------------------------------------------------------------


class TestCaps:
    def test_max_notional_cap_applied(self) -> None:
        # With large enough risk budget, position should be capped
        inp = _make_input(equity=1_000_000.0, max_notional=500.0)
        result = calculate_position_size(inp)
        # raw would be huge, but max_notional caps at 500
        assert result.status == SIZING_CAPPED_NOTIONAL
        assert result.capped_size <= 500.0

    def test_min_notional_within_budget(self) -> None:
        # When raw size is below min_notional but risk budget allows
        inp = _make_input(equity=10_000.0, risk_fraction=0.02, atr_value=10.0,
                          atr_multiplier=2.0, min_notional=5.0)
        # risk=200, stop=20, raw=10 which exceeds min_notional=5 -> OK
        result = calculate_position_size(inp)
        assert result.status == SIZING_OK

    def test_min_notional_exceeds_risk_budget(self) -> None:
        # Very tight risk budget + high min_notional -> raw falls below min
        inp = _make_input(equity=100.0, risk_fraction=0.005, atr_value=10.0,
                          atr_multiplier=2.0, min_notional=500.0)
        # risk=0.50, stop=20, raw=0.025, notional=0.02*5000=100 < min 500 → FAIL
        result = calculate_position_size(inp)
        assert result.status == SIZING_MIN_NOTIONAL_FAIL
        assert result.decision == "REJECTED"


# ---------------------------------------------------------------------------
# Precision & rounding
# ---------------------------------------------------------------------------


class TestPrecision:
    def test_rounds_down_to_precision(self) -> None:
        # raw = 100 / (10*2) = 5.0, fee: 5*(1-0.001)=4.995 -> precision 2 -> 4.99
        inp = _make_input(equity=20_000.0, risk_fraction=0.005, atr_value=10.0,
                          atr_multiplier=2.0, precision=2)
        # risk=100, stop=20, raw=5, after fee 4.995 -> round down 4.99
        result = calculate_position_size(inp)
        assert result.capped_size == pytest.approx(4.99, rel=0.01)

    def test_precision_0_rounds_to_integer(self) -> None:
        inp = _make_input(precision=0, atr_value=100.0)
        # risk=100, stop=200, raw=0.5, fee=0.4995 -> round down to 0
        result = calculate_position_size(inp)
        assert result.capped_size == 0.0


# ---------------------------------------------------------------------------
# Fee / slippage buffer
# ---------------------------------------------------------------------------


class TestFeeBuffer:
    def test_fee_reduces_size(self) -> None:
        no_fee = _make_input(fee_slippage_pct=0.0)
        with_fee = _make_input(fee_slippage_pct=0.2)
        res_no = calculate_position_size(no_fee)
        res_with = calculate_position_size(with_fee)
        assert res_with.capped_size < res_no.capped_size

    def test_negative_fee_treated_as_zero(self) -> None:
        inp = _make_input(fee_slippage_pct=-0.5)
        result = calculate_position_size(inp)
        assert result.status == SIZING_OK


# ---------------------------------------------------------------------------
# Leverage
# ---------------------------------------------------------------------------


class TestLeverage:
    def test_leverage_scales_notional(self) -> None:
        # leverage 1x vs 5x — raw_size scales with 1/leverage
        no_lev = _make_input(leverage=1.0)
        lev5 = _make_input(leverage=5.0)
        res1 = calculate_position_size(no_lev)
        res5 = calculate_position_size(lev5)
        # With leverage, we need less margin per contract
        assert res5.raw_size == pytest.approx(res1.raw_size, rel=0.01)

    def test_zero_leverage_rejected(self) -> None:
        inp = _make_input(leverage=0.0)
        result = calculate_position_size(inp)
        assert result.status == SIZING_INVALID_INPUT


# ---------------------------------------------------------------------------
# SizingDecision output
# ---------------------------------------------------------------------------


class TestSizingDecision:
    def test_decision_contains_all_fields(self) -> None:
        inp = _make_input()
        result = calculate_position_size(inp)
        d = asdict(result)
        assert "status" in d
        assert "raw_size" in d
        assert "capped_size" in d
        assert "risk_budget" in d
        assert "stop_distance" in d
        assert "effective_risk" in d
        assert "decision" in d

    def test_effective_risk_never_exceeds_budget(self) -> None:
        for _ in range(20):
            import random
            random.seed(0)
            inp = _make_input(
                equity=random.uniform(500, 50_000),
                risk_fraction=random.uniform(0.001, 0.05),
                atr_value=random.uniform(5, 500),
                atr_multiplier=random.uniform(1.0, 4.0),
            )
            result = calculate_position_size(inp)
            if result.status == SIZING_OK:
                assert result.effective_risk <= result.risk_budget * 1.01, \
                    f"eff_risk={result.effective_risk} > budget={result.risk_budget}"


# ---------------------------------------------------------------------------
# Conservative rounding
# ---------------------------------------------------------------------------


class TestConservativeRounding:
    def test_never_rounds_up(self) -> None:
        inp = _make_input(
            equity=10_000, risk_fraction=0.01, atr_value=30, atr_multiplier=2.0,
            precision=1,
        )
        # raw = 100/60 = 1.6666..., fee * 0.999 = 1.665..., round down: 1.6
        result = calculate_position_size(inp)
        assert result.capped_size <= 1.7  # safety margin, should be 1.6
        # Verify it didn't round up
        assert result.capped_size == pytest.approx(1.6, abs=0.1)
