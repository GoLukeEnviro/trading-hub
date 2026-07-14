"""Canonical raw-trade window scope for C4 measurement decisions.

This module is deliberately pure: it validates explicit UTC boundaries,
selects trade observations, and computes decision metrics without reading a
database, calling an API, or mutating runtime state.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, pstdev

WINDOW_SCOPE_METHOD = "close_in_window_or_open_at_window_end/v1"
AUTHORITATIVE_DRAWDOWN_METHOD = "continuation"


@dataclass(frozen=True)
class C4Trade:
    """Raw trade observation required by the C4 window selector."""

    trade_id: str
    opened_at_utc: str
    closed_at_utc: str | None
    profit_abs: float
    profit_ratio: float
    notional: float


@dataclass(frozen=True)
class C4MeasurementInput:
    """Explicit raw inputs for one C4 measurement window."""

    measurement_start_utc: str
    measurement_end_utc: str
    continuation_start_equity: float
    lifetime_start_equity: float
    trades: tuple[C4Trade, ...]


@dataclass(frozen=True)
class ScopedCanaryMetrics:
    """Metrics computed solely from trades realized in the selected window."""

    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    daily_loss_count: int
    avg_profit_per_trade: float | None
    notional_exposure: float

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "daily_loss_count": self.daily_loss_count,
            "avg_profit_per_trade": self.avg_profit_per_trade,
            "notional_exposure": self.notional_exposure,
        }


@dataclass(frozen=True)
class DrawdownCalculations:
    """Named drawdown methods retained in C4 evidence."""

    lifetime_pct: float | None
    window_relative_pct: float | None
    continuation_pct: float | None
    authoritative_method: str = AUTHORITATIVE_DRAWDOWN_METHOD

    def to_dict(self) -> dict[str, object]:
        return {
            "authoritative_method": self.authoritative_method,
            "lifetime": {
                "value_pct": self.lifetime_pct,
                "authoritative": False,
            },
            "window_relative": {
                "value_pct": self.window_relative_pct,
                "authoritative": False,
            },
            "continuation": {
                "value_pct": self.continuation_pct,
                "authoritative": True,
            },
        }


@dataclass(frozen=True)
class WindowScopedMeasurement:
    """Validated selection, calculated metrics, and scope provenance."""

    measurement_start_utc: str
    measurement_end_utc: str
    included_trade_ids: tuple[str, ...]
    realized_trade_ids: tuple[str, ...]
    open_at_window_end_trade_ids: tuple[str, ...]
    excluded_trade_ids: tuple[str, ...]
    metrics: ScopedCanaryMetrics
    drawdown_calculations: DrawdownCalculations
    scope_method: str = WINDOW_SCOPE_METHOD

    @property
    def included_trade_count(self) -> int:
        return len(self.included_trade_ids)

    @property
    def realized_trade_count(self) -> int:
        return len(self.realized_trade_ids)

    @property
    def open_at_window_end_trade_count(self) -> int:
        return len(self.open_at_window_end_trade_ids)

    @property
    def excluded_trade_count(self) -> int:
        return len(self.excluded_trade_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "measurement_start_utc": self.measurement_start_utc,
            "measurement_end_utc": self.measurement_end_utc,
            "scope_method": self.scope_method,
            "included_trade_count": self.included_trade_count,
            "realized_trade_count": self.realized_trade_count,
            "open_at_window_end_trade_count": self.open_at_window_end_trade_count,
            "excluded_trade_count": self.excluded_trade_count,
            "included_trade_ids": list(self.included_trade_ids),
            "realized_trade_ids": list(self.realized_trade_ids),
            "open_at_window_end_trade_ids": list(self.open_at_window_end_trade_ids),
            "excluded_trade_ids": list(self.excluded_trade_ids),
            "metrics": self.metrics.to_dict(),
            "metric_authority": {
                "notional_exposure": "open_at_window_end",
                "max_drawdown_pct": "continuation",
                "total_trades": "window_realized",
                "win_rate": "window_realized",
                "profit_factor": "window_realized",
                "sharpe_ratio": "window_realized",
                "daily_loss_count": "window_realized",
                "avg_profit_per_trade": "window_realized",
            },
            "drawdown_calculations": self.drawdown_calculations.to_dict(),
        }


def _parse_boundary(value: str, field_name: str) -> datetime:
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _validated_trades(
    trades: tuple[C4Trade, ...],
) -> tuple[tuple[C4Trade, datetime, datetime | None], ...]:
    validated: list[tuple[C4Trade, datetime, datetime | None]] = []
    seen_ids: set[str] = set()
    for trade in trades:
        if not trade.trade_id:
            raise ValueError("trade_id is required")
        if trade.trade_id in seen_ids:
            raise ValueError(f"duplicate trade_id: {trade.trade_id}")
        seen_ids.add(trade.trade_id)
        opened_at = _parse_boundary(trade.opened_at_utc, "opened_at_utc")
        closed_at = _parse_boundary(trade.closed_at_utc, "closed_at_utc") if trade.closed_at_utc is not None else None
        if closed_at is not None and closed_at < opened_at:
            raise ValueError(f"trade {trade.trade_id}: closed_at_utc precedes opened_at_utc")
        for field_name, value in (
            ("profit_abs", trade.profit_abs),
            ("profit_ratio", trade.profit_ratio),
            ("notional", trade.notional),
        ):
            if not math.isfinite(value):
                raise ValueError(f"trade {trade.trade_id}: {field_name} must be finite")
        if trade.notional < 0:
            raise ValueError(f"trade {trade.trade_id}: notional must be >= 0")
        validated.append((trade, opened_at, closed_at))
    return tuple(validated)


def _max_drawdown_pct(
    pnls: tuple[float, ...],
    *,
    starting_equity: float,
) -> float | None:
    if not pnls:
        return None
    equity = starting_equity
    peak = starting_equity
    maximum = 0.0
    has_positive_peak = peak > 0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            has_positive_peak = True
            maximum = max(maximum, (peak - equity) / peak * 100.0)
    return maximum if has_positive_peak else None


def _profit_factor(pnls: tuple[float, ...]) -> float | None:
    gross_profit = sum(value for value in pnls if value > 0)
    gross_loss = abs(sum(value for value in pnls if value < 0))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def _sharpe_ratio(ratios: tuple[float, ...]) -> float | None:
    if len(ratios) < 2:
        return None
    deviation = pstdev(ratios)
    if deviation == 0:
        return None
    return mean(ratios) / deviation * math.sqrt(len(ratios))


def build_window_scoped_measurement(
    input_: C4MeasurementInput,
) -> WindowScopedMeasurement:
    """Validate, select, and calculate one canonical C4 measurement window.

    Realized performance metrics use only trades whose close timestamp is in
    the inclusive ``[start, end]`` interval. Trades active at ``end`` remain
    visible as exposure evidence but their future PnL is excluded. Max
    drawdown uses the continuation calculation authoritatively; lifetime and
    window-relative values are retained as explicitly non-authoritative audit
    calculations.
    """

    start = _parse_boundary(input_.measurement_start_utc, "measurement_start_utc")
    end = _parse_boundary(input_.measurement_end_utc, "measurement_end_utc")
    if start >= end:
        raise ValueError("measurement_start_utc must be before measurement_end_utc")
    if input_.continuation_start_equity <= 0:
        raise ValueError("continuation_start_equity must be > 0")
    if input_.lifetime_start_equity <= 0:
        raise ValueError("lifetime_start_equity must be > 0")

    validated = _validated_trades(input_.trades)
    realized: list[tuple[C4Trade, datetime]] = []
    open_at_end: list[C4Trade] = []
    excluded: list[C4Trade] = []
    lifetime_realized: list[tuple[C4Trade, datetime]] = []

    for trade, opened_at, closed_at in validated:
        if closed_at is not None and closed_at <= end:
            lifetime_realized.append((trade, closed_at))
        if closed_at is not None and start <= closed_at <= end:
            realized.append((trade, closed_at))
        elif opened_at <= end and (closed_at is None or closed_at > end):
            open_at_end.append(trade)
        else:
            excluded.append(trade)

    realized.sort(key=lambda item: (item[1], item[0].trade_id))
    lifetime_realized.sort(key=lambda item: (item[1], item[0].trade_id))

    realized_trades = tuple(item[0] for item in realized)
    realized_pnls = tuple(trade.profit_abs for trade in realized_trades)
    realized_ratios = tuple(trade.profit_ratio for trade in realized_trades)
    lifetime_pnls = tuple(item[0].profit_abs for item in lifetime_realized)

    daily_pnls: dict[object, float] = defaultdict(float)
    for trade, closed_at in realized:
        daily_pnls[closed_at.date()] += trade.profit_abs

    drawdowns = DrawdownCalculations(
        lifetime_pct=_max_drawdown_pct(
            lifetime_pnls,
            starting_equity=input_.lifetime_start_equity,
        ),
        window_relative_pct=_max_drawdown_pct(
            realized_pnls,
            starting_equity=0.0,
        ),
        continuation_pct=_max_drawdown_pct(
            realized_pnls,
            starting_equity=input_.continuation_start_equity,
        ),
    )
    wins = sum(1 for value in realized_pnls if value > 0)
    metrics = ScopedCanaryMetrics(
        total_trades=len(realized_trades),
        win_rate=(wins / len(realized_trades) if realized_trades else None),
        profit_factor=_profit_factor(realized_pnls),
        sharpe_ratio=_sharpe_ratio(realized_ratios),
        max_drawdown_pct=drawdowns.continuation_pct,
        daily_loss_count=sum(1 for value in daily_pnls.values() if value < 0),
        avg_profit_per_trade=(mean(realized_pnls) if realized_pnls else None),
        notional_exposure=sum(trade.notional for trade in open_at_end),
    )
    included_ids = tuple(trade.trade_id for trade in realized_trades) + tuple(trade.trade_id for trade in open_at_end)

    return WindowScopedMeasurement(
        measurement_start_utc=start.isoformat(),
        measurement_end_utc=end.isoformat(),
        included_trade_ids=included_ids,
        realized_trade_ids=tuple(trade.trade_id for trade in realized_trades),
        open_at_window_end_trade_ids=tuple(trade.trade_id for trade in open_at_end),
        excluded_trade_ids=tuple(trade.trade_id for trade in excluded),
        metrics=metrics,
        drawdown_calculations=drawdowns,
    )


__all__ = [
    "AUTHORITATIVE_DRAWDOWN_METHOD",
    "WINDOW_SCOPE_METHOD",
    "C4MeasurementInput",
    "C4Trade",
    "DrawdownCalculations",
    "ScopedCanaryMetrics",
    "WindowScopedMeasurement",
    "build_window_scoped_measurement",
]
