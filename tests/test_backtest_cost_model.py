from __future__ import annotations

import pytest

from backtests.cost_model.cost_calculator import (
    calc_enter_fee,
    calc_exit_fee,
    calc_funding_cost,
    calc_gross_pnl,
    calc_net_pnl,
    calc_slippage_cost,
    compute_aggregate_metrics,
    compute_trade_result,
)
from backtests.cost_model.models import (
    CostConfig,
    TradeInput,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _long_trade(entry: float = 100.0, exit_: float = 110.0, qty: float = 1.0, hold: float = 24.0) -> TradeInput:
    return TradeInput(entry_price=entry, exit_price=exit_, quantity=qty, side="long", hold_hours=hold)


def _short_trade(entry: float = 100.0, exit_: float = 90.0, qty: float = 1.0, hold: float = 24.0) -> TradeInput:
    return TradeInput(entry_price=entry, exit_price=exit_, quantity=qty, side="short", hold_hours=hold)


def _costly_config() -> CostConfig:
    return CostConfig(entry_fee_rate=0.01, exit_fee_rate=0.01, slippage_rate=0.01, funding_rate_per_8h=0.005)


# ===========================================================================
# Fee calculation
# ===========================================================================


class TestFeeCalculation:
    def test_entry_fee_default(self) -> None:
        fee = calc_enter_fee(_long_trade())
        assert fee == pytest.approx(100.0 * 1.0 * 0.0005, rel=1e-9)

    def test_exit_fee_default(self) -> None:
        fee = calc_exit_fee(_long_trade())
        assert fee == pytest.approx(110.0 * 1.0 * 0.0005, rel=1e-9)

    def test_entry_fee_zero_rate(self) -> None:
        cfg = CostConfig(entry_fee_rate=0.0)
        fee = calc_enter_fee(_long_trade(), cfg)
        assert fee == 0.0

    def test_fees_scales_with_quantity(self) -> None:
        fee_small = calc_enter_fee(_long_trade(qty=1.0))
        fee_large = calc_enter_fee(_long_trade(qty=10.0))
        assert fee_large == pytest.approx(fee_small * 10.0, rel=1e-9)


# ===========================================================================
# Slippage calculation
# ===========================================================================


class TestSlippageCalculation:
    def test_slippage_scales_with_price(self) -> None:
        cost = calc_slippage_cost(_long_trade(entry=100.0, exit_=101.0, qty=1.0))
        assert cost > 0

    def test_zero_slippage_rate(self) -> None:
        cfg = CostConfig(slippage_rate=0.0)
        cost = calc_slippage_cost(_long_trade(), cfg)
        assert cost == 0.0


# ===========================================================================
# Funding calculation
# ===========================================================================


class TestFundingCalculation:
    def test_long_pays_funding(self) -> None:
        cost = calc_funding_cost(_long_trade(entry=100.0, exit_=110.0, qty=1.0, hold=8.0))
        assert cost > 0

    def test_short_receives_funding(self) -> None:
        cost = calc_funding_cost(_short_trade(entry=100.0, exit_=90.0, qty=1.0, hold=8.0))
        assert cost < 0

    def test_zero_funding_rate(self) -> None:
        cfg = CostConfig(funding_rate_per_8h=0.0)
        cost = calc_funding_cost(_long_trade(), cfg)
        assert cost == 0.0

    def test_no_hold_funding_is_zero(self) -> None:
        cost = calc_funding_cost(_long_trade(hold=0.0))
        assert cost == 0.0


# ===========================================================================
# Gross PnL
# ===========================================================================


class TestGrossPnl:
    def test_long_profitable(self) -> None:
        pnl = calc_gross_pnl(_long_trade(entry=100.0, exit_=110.0, qty=1.0))
        assert pnl == 10.0

    def test_long_losing(self) -> None:
        pnl = calc_gross_pnl(_long_trade(entry=100.0, exit_=90.0, qty=1.0))
        assert pnl == -10.0

    def test_short_profitable(self) -> None:
        pnl = calc_gross_pnl(_short_trade(entry=100.0, exit_=90.0, qty=1.0))
        assert pnl == 10.0

    def test_short_losing(self) -> None:
        pnl = calc_gross_pnl(_short_trade(entry=100.0, exit_=110.0, qty=1.0))
        assert pnl == -10.0

    def test_zero_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            _long_trade(entry=100.0, exit_=110.0, qty=0.0)


# ===========================================================================
# Net PnL (gross + costs)
# ===========================================================================


class TestNetPnl:
    def test_long_net_less_than_gross(self) -> None:
        trade = _long_trade(entry=100.0, exit_=110.0, qty=1.0)
        gross = calc_gross_pnl(trade)
        net = calc_net_pnl(trade)
        assert net < gross

    def test_costs_can_turn_positive_to_negative(self) -> None:
        """High costs make a small gross-positive trade net-negative."""
        cfg = _costly_config()
        trade = _long_trade(entry=100.0, exit_=101.0, qty=1.0)
        net = calc_net_pnl(trade, cfg)
        assert net < 0

    def test_compute_trade_result_includes_breakdown(self) -> None:
        trade = _long_trade(entry=100.0, exit_=110.0, qty=1.0)
        result = compute_trade_result(trade)
        assert result.costs.entry_fee > 0
        assert result.costs.exit_fee > 0
        assert result.costs.total_cost > 0
        assert result.net_pnl < result.gross_pnl


# ===========================================================================
# Aggregate metrics
# ===========================================================================


class TestAggregateMetrics:
    def test_empty_results(self) -> None:
        agg = compute_aggregate_metrics([])
        assert agg.total_trades == 0
        assert agg.total_net_pnl == 0.0

    def test_win_rate(self) -> None:
        results = [
            compute_trade_result(_long_trade(entry=100.0, exit_=110.0, qty=1.0)),
            compute_trade_result(_long_trade(entry=100.0, exit_=105.0, qty=1.0)),
            compute_trade_result(_long_trade(entry=100.0, exit_=90.0, qty=10.0)),
        ]
        agg = compute_aggregate_metrics(results)
        assert 0 < agg.win_rate_pct < 100

    def test_total_fees(self) -> None:
        results = [
            compute_trade_result(_long_trade(qty=1.0)),
            compute_trade_result(_short_trade(qty=1.0)),
        ]
        agg = compute_aggregate_metrics(results)
        assert agg.total_fees > 0

    def test_max_drawdown(self) -> None:
        trades = [
            _long_trade(entry=100.0, exit_=90.0, qty=1.0),
            _long_trade(entry=100.0, exit_=110.0, qty=1.0),
            _long_trade(entry=100.0, exit_=80.0, qty=1.0),
        ]
        results = [compute_trade_result(t) for t in trades]
        agg = compute_aggregate_metrics(results)
        assert agg.max_drawdown_pct > 0

    def test_profit_factor(self) -> None:
        """Profit factor is > 1 when net profitable."""
        trades = [_long_trade(entry=100.0, exit_=120.0, qty=1.0) for _ in range(3)]
        results = [compute_trade_result(t) for t in trades]
        agg = compute_aggregate_metrics(results)
        assert agg.profit_factor > 1.0


# ===========================================================================
# Invalid input handling
# ===========================================================================


class TestInvalidInputHandling:
    def test_negative_prices_rejected(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            _long_trade(entry=-100.0, exit_=-90.0, qty=1.0)

    def test_zero_entry_price_rejected(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            _long_trade(entry=0.0, exit_=10.0, qty=1.0)

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            _long_trade(entry=100.0, exit_=110.0, qty=-1.0)

    def test_config_rejects_negative_rates(self) -> None:
        with pytest.raises(ValueError):
            CostConfig(entry_fee_rate=-0.01)


# ===========================================================================
# TradeResult property checks
# ===========================================================================


class TestTradeResultProperties:
    def test_is_profitable_net_positive(self) -> None:
        trade = _long_trade(entry=100.0, exit_=200.0, qty=1.0)
        result = compute_trade_result(trade)
        assert result.is_profitable_net is True

    def test_is_profitable_net_negative(self) -> None:
        cfg = _costly_config()
        trade = _long_trade(entry=100.0, exit_=101.0, qty=1.0)
        result = compute_trade_result(trade, cfg)
        assert result.is_profitable_net is False
