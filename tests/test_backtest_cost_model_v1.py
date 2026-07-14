from __future__ import annotations

import pytest

from backtests.cost_model import (
    CostConfig,
    TradeInput,
    calc_all_costs,
    calc_mark_to_market_pnl,
    compute_aggregate_metrics,
    compute_trade_result,
)


def test_funding_payment_reduces_net_pnl() -> None:
    trade = TradeInput(
        entry_price=100.0,
        exit_price=100.0,
        quantity=1.0,
        side="long",
        hold_hours=8.0,
    )
    result = compute_trade_result(
        trade,
        CostConfig(
            entry_fee_rate=0.0,
            exit_fee_rate=0.0,
            slippage_rate=0.0,
            funding_rate_per_8h=0.01,
        ),
    )
    assert result.costs.funding_cost == pytest.approx(1.0)
    assert result.net_pnl == pytest.approx(-1.0)


def test_funding_credit_increases_net_pnl_and_stays_signed_in_aggregate() -> None:
    trade = TradeInput(
        entry_price=100.0,
        exit_price=100.0,
        quantity=1.0,
        side="short",
        hold_hours=8.0,
    )
    result = compute_trade_result(
        trade,
        CostConfig(
            entry_fee_rate=0.0,
            exit_fee_rate=0.0,
            slippage_rate=0.0,
            funding_rate_per_8h=0.01,
        ),
    )
    assert result.costs.funding_cost == pytest.approx(-1.0)
    assert result.costs.total_cost == pytest.approx(-1.0)
    assert result.net_pnl == pytest.approx(1.0)
    assert compute_aggregate_metrics([result]).total_funding == pytest.approx(-1.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entry_price", 0.0),
        ("entry_price", -1.0),
        ("exit_price", 0.0),
        ("exit_price", -1.0),
        ("quantity", 0.0),
        ("quantity", -1.0),
        ("hold_hours", -1.0),
    ],
)
def test_trade_input_rejects_non_physical_values(field: str, value: float) -> None:
    values: dict[str, object] = {
        "entry_price": 100.0,
        "exit_price": 101.0,
        "quantity": 1.0,
        "side": "long",
        "hold_hours": 1.0,
    }
    values[field] = value
    with pytest.raises(ValueError, match=field):
        TradeInput(**values)  # type: ignore[arg-type]


def test_trade_input_rejects_unknown_side_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="side"):
        TradeInput(100.0, 101.0, 1.0, "buy", 1.0)
    with pytest.raises(ValueError, match="entry_price"):
        TradeInput(float("nan"), 101.0, 1.0, "long", 1.0)


def test_signed_funding_rate_is_supported() -> None:
    config = CostConfig(funding_rate_per_8h=-0.01)
    trade = TradeInput(100.0, 100.0, 1.0, "long", 8.0)
    assert calc_all_costs(trade, config).funding_cost < 0


def test_mark_to_market_uses_the_canonical_cost_engine() -> None:
    trade = TradeInput(100.0, 110.0, 1.0, "long", 8.0)
    config = CostConfig(
        entry_fee_rate=0.001,
        exit_fee_rate=0.001,
        slippage_rate=0.001,
        funding_rate_per_8h=0.01,
    )
    mtm = calc_mark_to_market_pnl(
        trade,
        mark_price=90.0,
        elapsed_hours=4.0,
        config=config,
    )
    expected_gross = -10.0
    expected_entry_fee = 0.1
    expected_entry_slippage = 0.1
    expected_funding = 95.0 * 0.01 * 0.5
    assert mtm == pytest.approx(
        expected_gross - expected_entry_fee - expected_entry_slippage - expected_funding
    )
