"""Data models for realistic backtest cost calculations.

Defines the core types used by the cost model and walk-forward evaluator.
All types are plain Python dataclasses with typed fields — no Pydantic
dependency needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Cost configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostConfig:
    """Tunable cost parameters for backtest simulation.

    All rates are fractional (0.001 = 0.1 %).
    Defaults target conservative Bitget futures estimates.
    """

    entry_fee_rate: float = 0.0005       # 0.05 % taker fee
    exit_fee_rate: float = 0.0005        # 0.05 % taker fee
    slippage_rate: float = 0.0005        # 0.05 % slippage per leg
    funding_rate_per_8h: float = 0.0001  # 0.01 % per 8h (annualised ~11 %)
    # Leverage (for margin-based funding, not position sizing)
    leverage: float = 1.0

    def __post_init__(self) -> None:
        """Validate rates are non-negative."""
        for name, val in {
            "entry_fee_rate": self.entry_fee_rate,
            "exit_fee_rate": self.exit_fee_rate,
            "slippage_rate": self.slippage_rate,
            "funding_rate_per_8h": self.funding_rate_per_8h,
        }.items():
            if val < 0:
                raise ValueError(f"{name} must be >= 0, got {val}")
        if self.leverage <= 0:
            raise ValueError(f"leverage must be > 0, got {self.leverage}")


# Default conservative config
DEFAULT_COST_CONFIG = CostConfig()


# ---------------------------------------------------------------------------
# Per-trade breakdown
# ---------------------------------------------------------------------------


@dataclass
class CostBreakdown:
    """Itemised cost components for a single trade."""

    entry_fee: float = 0.0
    exit_fee: float = 0.0
    slippage_cost: float = 0.0
    funding_cost: float = 0.0  # positive = paid, negative = received
    total_cost: float = 0.0


# ---------------------------------------------------------------------------
# Trade input and result
# ---------------------------------------------------------------------------


@dataclass
class TradeInput:
    """Minimal trade description consumed by the cost model.

    Prices are in quote currency, quantity in base currency.
    """

    entry_price: float
    exit_price: float
    quantity: float  # base currency amount
    side: str  # "long" or "short"
    # Held time in hours (for funding accrual)
    hold_hours: float = 0.0


@dataclass
class TradeResult:
    """Fully calculated trade with costs applied."""

    entry_price: float
    exit_price: float
    quantity: float
    side: str
    hold_hours: float

    gross_pnl: float
    gross_return_pct: float
    costs: CostBreakdown
    net_pnl: float
    net_return_pct: float

    # Derived
    @property
    def is_profitable_net(self) -> bool:
        """True when net PnL is strictly positive."""
        return self.net_pnl > 0.0

    @property
    def entry_cost(self) -> float:
        """Total cost at entry (entry fee + entry slippage)."""
        half_slip = self.costs.slippage_cost / 2.0
        return self.costs.entry_fee + half_slip if self.costs.slippage_cost > 0 else self.costs.entry_fee


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


@dataclass
class WalkForwardWindow:
    """A single train/test window split."""
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass
class WindowMetrics:
    """Net metrics for one walk-forward window."""
    window_label: str  # "train" or "test"
    trade_count: int
    gross_pnl: float
    net_pnl: float
    total_fees: float
    total_slippage: float
    total_funding: float
    win_rate_pct: float
    max_drawdown_pct: float
    avg_net_pnl: float
    avg_return_pct: float
    profit_factor: float  # gross profit / gross loss, inf if no losses


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all trades."""

    total_trades: int
    total_gross_pnl: float
    total_net_pnl: float
    total_fees: float
    total_slippage: float
    total_funding: float
    win_rate_pct: float
    max_drawdown_pct: float
    avg_net_pnl: float
    avg_return_pct: float
    profit_factor: float
    windows: List[WindowMetrics] = field(default_factory=list)
