"""Performance analyzer for computing trading metrics per time window.

Computes win rate, profit factor, max drawdown, Sharpe ratio, and
consecutive losses for 12h, 24h, and 72h windows.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from si_v2.state.schemas import AnalysisResult, WindowStats

# Default analysis windows
DEFAULT_WINDOWS: tuple[str, ...] = ("12h", "24h", "72h")

# Minimum number of trades required for a mutation decision
MIN_TRADES_FOR_DECISION: int = 5


class PerformanceAnalyzer:
    """Analyzes trading performance across time windows."""

    def analyze(
        self,
        trades: list[dict[str, str | int | float]],
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        bot_id: str = "unknown",
        bot_name: str = "Unknown Bot",
    ) -> AnalysisResult:
        """Compute performance metrics per window.

        Args:
            trades: List of trade record dicts with at minimum 'profit_pct' and 'profit_abs'.
            windows: Time window names to compute stats for.
            bot_id: Bot identifier for the result.
            bot_name: Human-readable bot name for the result.

        Returns:
            AnalysisResult with per-window WindowStats and a decision.
        """
        window_stats: dict[str, WindowStats] = {}

        for window_name in windows:
            stats = self._compute_window_stats(trades)
            window_stats[window_name] = stats

        total_trades = len(trades)
        decision = self._compute_decision(window_stats, total_trades)

        return AnalysisResult(
            bot_id=bot_id,
            bot_name=bot_name,
            decision=decision,
            windows=window_stats,
            ts=datetime.now(UTC),
        )

    def _compute_window_stats(self, trades: list[dict[str, str | int | float]]) -> WindowStats:
        """Compute statistics for a single window of trades.

        Args:
            trades: List of trade records.

        Returns:
            WindowStats with computed metrics.
        """
        if not trades:
            return WindowStats(
                trades=0,
                wins=0,
                losses=0,
                pnl_abs=0.0,
                max_drawdown_pct=0.0,
                consecutive_losses=0,
            )

        wins = 0
        losses = 0
        pnl_abs = 0.0
        max_drawdown_pct = 0.0
        peak_pnl = 0.0
        max_consecutive_losses = 0
        current_consecutive = 0

        gross_profit = 0.0
        gross_loss = 0.0
        returns: list[float] = []

        for trade in trades:
            profit_pct = float(trade.get("profit_pct", 0.0))
            profit_abs = float(trade.get("profit_abs", 0.0))
            pnl_abs += profit_abs

            if profit_abs > 0:
                wins += 1
                gross_profit += profit_abs
                current_consecutive = 0
            else:
                losses += 1
                gross_loss += abs(profit_abs)
                current_consecutive += 1
                max_consecutive_losses = max(max_consecutive_losses, current_consecutive)

            if pnl_abs > peak_pnl:
                peak_pnl = pnl_abs
            drawdown = peak_pnl - pnl_abs
            if peak_pnl > 0:
                dd_pct = drawdown / peak_pnl
                max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            returns.append(profit_pct)

        win_rate_pct: float | None = None
        total = wins + losses
        if total > 0:
            win_rate_pct = (wins / total) * 100.0

        profit_factor: float | None = None
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")

        sharpe: float | None = None
        if len(returns) >= 2:
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            std_ret = math.sqrt(variance)
            if std_ret > 0:
                sharpe = mean_ret / std_ret

        return WindowStats(
            trades=total,
            wins=wins,
            losses=losses,
            win_rate_pct=win_rate_pct,
            pnl_abs=round(pnl_abs, 8),
            profit_factor=profit_factor,
            max_drawdown_pct=round(max_drawdown_pct, 6),
            sharpe=sharpe,
            consecutive_losses=max_consecutive_losses,
        )

    def _compute_decision(self, window_stats: dict[str, WindowStats], total_trades: int) -> str:
        """Compute the overall decision based on window statistics.

        Args:
            window_stats: Per-window statistics.
            total_trades: Total number of trades across windows.

        Returns:
            Decision string: 'hold', 'mutate', or 'block'.
        """
        if total_trades < MIN_TRADES_FOR_DECISION:
            return "hold"

        for stats in window_stats.values():
            if stats.consecutive_losses >= 5:
                return "block"

        return "hold"
