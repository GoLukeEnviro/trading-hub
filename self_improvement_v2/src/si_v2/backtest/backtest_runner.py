"""Backtest runner using dependency-injected FreqtradeAdapter.

Runs backtests through the adapter protocol, maps raw results to BacktestResult,
and applies pass/fail criteria (profit > 0, drawdown < 15%, min trades).
"""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate, MutationOverlay

# Default minimum trades threshold
DEFAULT_MIN_TRADES: int = 5


class BacktestRunner:
    """Runs backtests via a FreqtradeAdapter and evaluates results."""

    def __init__(self, adapter: FreqtradeAdapter) -> None:
        """Initialize with a FreqtradeAdapter instance.

        Args:
            adapter: FreqtradeAdapter implementation for running backtests.
        """
        self._adapter = adapter

    def run(self, candidate: MutationCandidate, bot_config: BotConfig) -> BacktestResult:
        """Run a backtest for a mutation candidate and evaluate pass/fail.

        Args:
            candidate: Mutation candidate to backtest.
            bot_config: Bot configuration for context.

        Returns:
            BacktestResult with pass/fail evaluation.
        """
        overlay = self._build_overlay(candidate)
        raw = self._adapter.run_backtest(bot_config.bot_id, overlay)
        now = datetime.now(UTC)

        # Fail closed if adapter returns empty or missing critical data
        if not raw or "profit_total_pct" not in raw or "total_trades" not in raw:
            return BacktestResult(
                bot_id=bot_config.bot_id,
                candidate_sha256=candidate.candidate_sha256,
                total_trades=0,
                profit_total_pct=0.0,
                profit_total_abs=0.0,
                max_drawdown_pct=0.0,
                win_rate_pct=0.0,
                sharpe=None,
                profit_factor=None,
                duration_seconds=0.0,
                passed=False,
                ts=now,
            )

        total_trades = int(raw.get("total_trades", 0))
        profit_total_pct = float(raw.get("profit_total_pct", 0.0))
        profit_total_abs = float(raw.get("profit_total_abs", 0.0))
        max_drawdown_raw = float(raw.get("max_drawdown_pct", 0.0))
        # Normalize: values > 1.0 are treated as percentages (e.g. 5.0 = 5%)
        max_drawdown_pct = max_drawdown_raw / 100.0 if max_drawdown_raw > 1.0 else max_drawdown_raw
        win_rate_raw = float(raw.get("win_rate_pct", 0.0))
        # win_rate_pct: values > 100 are treated as ratio*1000, otherwise keep as-is
        win_rate_pct = win_rate_raw
        sharpe_raw = raw.get("sharpe")
        sharpe: float | None = float(sharpe_raw) if sharpe_raw is not None else None
        profit_factor_raw = raw.get("profit_factor")
        profit_factor: float | None = float(profit_factor_raw) if profit_factor_raw is not None else None
        duration_seconds = float(raw.get("duration_seconds", 0.0))

        min_trades = self._get_min_trades(bot_config)
        passed = profit_total_pct > 0 and max_drawdown_pct < 0.15 and total_trades >= min_trades

        return BacktestResult(
            bot_id=bot_config.bot_id,
            candidate_sha256=candidate.candidate_sha256,
            total_trades=total_trades,
            profit_total_pct=profit_total_pct,
            profit_total_abs=profit_total_abs,
            max_drawdown_pct=max_drawdown_pct,
            win_rate_pct=win_rate_pct,
            sharpe=sharpe,
            profit_factor=profit_factor,
            duration_seconds=duration_seconds,
            passed=passed,
            ts=now,
        )

    def _build_overlay(self, candidate: MutationCandidate) -> MutationOverlay:
        """Build a MutationOverlay from candidate parameters.

        Args:
            candidate: Mutation candidate with parameters.

        Returns:
            MutationOverlay with safe parameter values.
        """
        params = candidate.parameters
        return MutationOverlay(
            max_open_trades=int(params.get("max_open_trades", 3)),
            stake_amount=float(params.get("stake_factor", 1.0)) * 20.0,
            stoploss=float(params.get("stoploss_pct", -0.02)),
            minimal_roi={"0": float(params.get("take_profit_pct", 0.035))},
        )

    def _get_min_trades(self, bot_config: BotConfig) -> int:
        """Extract min_trades from bot config or return default.

        Args:
            bot_config: Bot configuration.

        Returns:
            Minimum number of trades required to pass.
        """
        raw = bot_config.schedules.get("min_trades", str(DEFAULT_MIN_TRADES))
        return int(raw)
