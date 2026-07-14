"""Cost calculation functions for backtest simulation.

All functions are pure, deterministic, and operate on the dataclass types
defined in ``models.py``.
"""

from __future__ import annotations

from .models import (
    DEFAULT_COST_CONFIG,
    AggregateMetrics,
    CostBreakdown,
    CostConfig,
    TradeInput,
    TradeResult,
    WindowMetrics,
)

# ---------------------------------------------------------------------------
# Per-trade calculators
# ---------------------------------------------------------------------------


def calc_enter_fee(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Entry fee = notional * entry_fee_rate."""
    notional = trade.entry_price * trade.quantity
    return notional * config.entry_fee_rate


def calc_exit_fee(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Exit fee = notional_at_exit * exit_fee_rate."""
    notional = trade.exit_price * trade.quantity
    return notional * config.exit_fee_rate


def calc_slippage_cost(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Slippage cost on entry and exit = notional * slippage_rate * 2."""
    avg_notional = (trade.entry_price + trade.exit_price) / 2.0 * trade.quantity
    return 2.0 * avg_notional * config.slippage_rate


def calc_funding_cost(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Funding paid or received.

    For long trades: positive funding = cost (paying).
    For short trades: positive funding = credit (receiving).
    Uses average notional * funding_rate_per_8h * (hold_hours / 8).
    """
    avg_notional = (trade.entry_price + trade.exit_price) / 2.0 * trade.quantity
    raw = avg_notional * config.funding_rate_per_8h * (trade.hold_hours / 8.0)
    if trade.side == "long":
        return raw  # long pays funding
    elif trade.side == "short":
        return -raw  # short receives funding
    return 0.0


def calc_gross_pnl(trade: TradeInput) -> float:
    """Gross (pre-cost) profit or loss for a single trade.

    Long:  (exit - entry) * quantity
    Short: (entry - exit) * quantity
    """
    if trade.side == "long":
        return (trade.exit_price - trade.entry_price) * trade.quantity
    elif trade.side == "short":
        return (trade.entry_price - trade.exit_price) * trade.quantity
    return 0.0


def calc_gross_return_pct(trade: TradeInput) -> float:
    """Gross return as percentage of entry notional."""
    notional = trade.entry_price * trade.quantity
    if notional == 0:
        return 0.0
    return (calc_gross_pnl(trade) / notional) * 100.0


def calc_net_pnl(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Net PnL = gross PnL minus all costs."""
    gross = calc_gross_pnl(trade)
    costs = calc_all_costs(trade, config)
    return gross - costs.total_cost


def calc_net_return_pct(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> float:
    """Net return as percentage of entry notional."""
    notional = trade.entry_price * trade.quantity
    if notional == 0:
        return 0.0
    return (calc_net_pnl(trade, config) / notional) * 100.0


# ---------------------------------------------------------------------------
# Composite calculators
# ---------------------------------------------------------------------------


def calc_all_costs(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> CostBreakdown:
    """Compute all cost components for a single trade."""
    entry_fee = calc_enter_fee(trade, config)
    exit_fee = calc_exit_fee(trade, config)
    slippage = calc_slippage_cost(trade, config)
    funding = calc_funding_cost(trade, config)
    breakdown = CostBreakdown(
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        slippage_cost=slippage,
        funding_cost=funding,
        total_cost=entry_fee + exit_fee + slippage + funding,
    )
    return breakdown


def compute_trade_result(trade: TradeInput, config: CostConfig = DEFAULT_COST_CONFIG) -> TradeResult:
    """Produce a full TradeResult for a single trade."""
    gross = calc_gross_pnl(trade)
    gross_pct = calc_gross_return_pct(trade)
    costs = calc_all_costs(trade, config)
    net = gross - costs.total_cost
    net_pct = calc_net_return_pct(trade, config)

    return TradeResult(
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        quantity=trade.quantity,
        side=trade.side,
        hold_hours=trade.hold_hours,
        gross_pnl=gross,
        gross_return_pct=gross_pct,
        costs=costs,
        net_pnl=net,
        net_return_pct=net_pct,
    )


def calc_mark_to_market_pnl(
    trade: TradeInput,
    *,
    mark_price: float,
    elapsed_hours: float,
    config: CostConfig = DEFAULT_COST_CONFIG,
) -> float:
    """Return signed unrealized PnL with costs accrued through the mark.

    This is the canonical mark-to-market companion to
    :func:`compute_trade_result`.  Only entry fee/slippage are charged while
    the position is open; funding retains its sign, so a credit increases
    equity.  Exit costs are charged only by the closed-trade calculation.
    """
    marked = TradeInput(
        entry_price=trade.entry_price,
        exit_price=mark_price,
        quantity=trade.quantity,
        side=trade.side,
        hold_hours=elapsed_hours,
    )
    gross = calc_gross_pnl(marked)
    entry_fee = calc_enter_fee(marked, config)
    entry_slippage = (
        marked.entry_price * marked.quantity * config.slippage_rate
    )
    funding = calc_funding_cost(marked, config)
    return gross - entry_fee - entry_slippage - funding


# ---------------------------------------------------------------------------
# Aggregate calculators
# ---------------------------------------------------------------------------


def compute_aggregate_metrics(
    results: list[TradeResult],
    windows: list[WindowMetrics] | None = None,
) -> AggregateMetrics:
    """Aggregate a list of TradeResult into summary metrics."""
    n = len(results)
    if n == 0:
        return AggregateMetrics(
            total_trades=0,
            total_gross_pnl=0.0,
            total_net_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            total_funding=0.0,
            win_rate_pct=0.0,
            max_drawdown_pct=0.0,
            avg_net_pnl=0.0,
            avg_return_pct=0.0,
            profit_factor=0.0,
            windows=windows or [],
        )

    total_gross = sum(r.gross_pnl for r in results)
    total_net = sum(r.net_pnl for r in results)
    total_fees = sum(r.costs.entry_fee + r.costs.exit_fee for r in results)
    total_slippage = sum(r.costs.slippage_cost for r in results)
    total_funding = sum(r.costs.funding_cost for r in results)
    wins = sum(1 for r in results if r.is_profitable_net)
    win_rate = (wins / n) * 100.0

    # Equity curve for max drawdown (peak-to-trough)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in results:
        equity += r.net_pnl
        if equity > peak:
            peak = equity
        if peak > 0:  # only measure drawdown from positive peaks
            dd = peak - equity
            if dd / peak > max_dd:
                max_dd = dd / peak
        elif equity < max_dd * -1:  # equity is below zero, track absolute trough
            max_dd = max(max_dd, abs(equity) / (abs(equity) + 1.0))

    avg_net = total_net / n if n > 0 else 0.0
    total_notional = sum(r.entry_price * r.quantity for r in results)
    avg_return = (total_net / total_notional * 100.0) if total_notional > 0 else 0.0

    # Profit factor
    gross_profit = sum(r.net_pnl for r in results if r.net_pnl > 0)
    gross_loss = abs(sum(r.net_pnl for r in results if r.net_pnl < 0))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    return AggregateMetrics(
        total_trades=n,
        total_gross_pnl=total_gross,
        total_net_pnl=total_net,
        total_fees=total_fees,
        total_slippage=total_slippage,
        total_funding=total_funding,
        win_rate_pct=win_rate,
        max_drawdown_pct=max_dd * 100.0,
        avg_net_pnl=avg_net,
        avg_return_pct=avg_return,
        profit_factor=profit_factor,
        windows=windows or [],
    )
