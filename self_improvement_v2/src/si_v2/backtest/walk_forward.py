"""Walk-forward validation for backtest result stability.

Splits trade history into train/test windows and validates that
out-of-sample performance is stable and positive.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate

# Minimum trades per split for valid walk-forward analysis
MIN_TRADES_PER_SPLIT: int = 10


class TrainWindow(BaseModel):
    """Index range for the training portion of a walk-forward window."""

    model_config = ConfigDict(strict=True)

    start_idx: int
    end_idx: int


class TestWindow(BaseModel):
    """Index range for the testing portion of a walk-forward window."""

    model_config = ConfigDict(strict=True)

    start_idx: int
    end_idx: int


class WalkForwardWindow(BaseModel):
    """A single train/test split for walk-forward analysis."""

    model_config = ConfigDict(strict=True)

    train: TrainWindow
    test: TestWindow


class WalkForwardResult(BaseModel):
    """Result of walk-forward validation across multiple windows."""

    model_config = ConfigDict(strict=False)

    in_sample_metrics: BacktestResult
    out_of_sample_metrics: BacktestResult
    stability_score: float
    passed: bool
    reason: str


class WalkForwardValidator:
    """Validates backtest results using walk-forward analysis."""

    def validate(
        self,
        trades: list[dict[str, str | int | float]],
        candidate: MutationCandidate,
        bot_config: BotConfig,
        runner: BacktestRunner,
        n_splits: int = 3,
    ) -> WalkForwardResult:
        """Perform walk-forward validation on a mutation candidate.

        Args:
            trades: List of trade record dicts.
            candidate: Mutation candidate to validate.
            bot_config: Bot configuration.
            runner: BacktestRunner instance for running sub-backtests.
            n_splits: Number of train/test splits.

        Returns:
            WalkForwardResult with stability score and pass/fail.
        """
        if len(trades) < MIN_TRADES_PER_SPLIT * n_splits:
            return WalkForwardResult(
                in_sample_metrics=self._empty_result(bot_config, candidate),
                out_of_sample_metrics=self._empty_result(bot_config, candidate),
                stability_score=0.0,
                passed=False,
                reason=f"insufficient data: {len(trades)} trades < {MIN_TRADES_PER_SPLIT * n_splits} required",
            )

        windows = self._split_windows(len(trades), n_splits)

        in_sample_results: list[BacktestResult] = []
        out_of_sample_results: list[BacktestResult] = []

        for window in windows:
            train_trades = trades[window.train.start_idx : window.train.end_idx]
            test_trades = trades[window.test.start_idx : window.test.end_idx]

            # Run backtest for training window (in-sample)
            in_sample = runner.run(candidate, bot_config)
            # Compute metrics from train trades
            is_metrics = self._compute_metrics_from_trades(
                train_trades, bot_config, candidate, in_sample.duration_seconds
            )
            in_sample_results.append(is_metrics)

            # Run backtest for testing window (out-of-sample)
            out_sample = runner.run(candidate, bot_config)
            oos_metrics = self._compute_metrics_from_trades(
                test_trades, bot_config, candidate, out_sample.duration_seconds
            )
            out_of_sample_results.append(oos_metrics)

        avg_in_sample = self._average_results(in_sample_results, bot_config, candidate)
        avg_out_sample = self._average_results(out_of_sample_results, bot_config, candidate)

        stability_score = self._compute_stability(out_of_sample_results)

        oos_profit_positive = avg_out_sample.profit_total_pct > 0
        stability_ok = stability_score > 0.5

        passed = oos_profit_positive and stability_ok
        reasons: list[str] = []
        if not oos_profit_positive:
            reasons.append("out_of_sample profit_pct <= 0")
        if not stability_ok:
            reasons.append(f"stability_score {stability_score:.3f} <= 0.5")
        reason = "; ".join(reasons) if reasons else "all criteria met"

        return WalkForwardResult(
            in_sample_metrics=avg_in_sample,
            out_of_sample_metrics=avg_out_sample,
            stability_score=stability_score,
            passed=passed,
            reason=reason,
        )

    def _split_windows(self, total_trades: int, n_splits: int) -> list[WalkForwardWindow]:
        """Split trade data into n walk-forward windows.

        Each window uses the first 70% for training and last 30% for testing.

        Args:
            total_trades: Total number of trades available.
            n_splits: Number of splits to create.

        Returns:
            List of WalkForwardWindow with train/test index ranges.
        """
        split_size = total_trades // n_splits
        windows: list[WalkForwardWindow] = []

        for i in range(n_splits):
            start = i * split_size
            # Last split takes any remaining trades
            end = (i + 1) * split_size if i < n_splits - 1 else total_trades

            train_size = int((end - start) * 0.7)
            train_end = start + train_size

            windows.append(
                WalkForwardWindow(
                    train=TrainWindow(start_idx=start, end_idx=train_end),
                    test=TestWindow(start_idx=train_end, end_idx=end),
                )
            )

        return windows

    def _compute_metrics_from_trades(
        self,
        trades: list[dict[str, str | int | float]],
        bot_config: BotConfig,
        candidate: MutationCandidate,
        duration_seconds: float,
    ) -> BacktestResult:
        """Compute backtest metrics from a trade slice.

        Args:
            trades: Trade records for this window.
            bot_config: Bot configuration.
            candidate: Mutation candidate.
            duration_seconds: Duration from the runner backtest.

        Returns:
            BacktestResult computed from the trade slice.
        """
        if not trades:
            return self._empty_result(bot_config, candidate)

        total = len(trades)
        profit_total_pct = sum(float(t.get("profit_pct", 0.0)) for t in trades)
        profit_total_abs = sum(float(t.get("profit_abs", 0.0)) for t in trades)

        wins = sum(1 for t in trades if float(t.get("profit_abs", 0.0)) > 0)
        win_rate_pct = (wins / total) * 100.0 if total > 0 else 0.0

        # Compute max drawdown
        peak = 0.0
        cumulative = 0.0
        max_dd = 0.0
        for t in trades:
            cumulative += float(t.get("profit_abs", 0.0))
            if cumulative > peak:
                peak = cumulative
            if peak > 0:
                dd = (peak - cumulative) / peak
                max_dd = max(max_dd, dd)

        min_trades = int(bot_config.schedules.get("min_trades", "5"))
        passed = profit_total_pct > 0 and max_dd < 0.15 and total >= min_trades

        return BacktestResult(
            bot_id=bot_config.bot_id,
            candidate_sha256=candidate.candidate_sha256,
            total_trades=total,
            profit_total_pct=profit_total_pct,
            profit_total_abs=profit_total_abs,
            max_drawdown_pct=max_dd,
            win_rate_pct=win_rate_pct,
            sharpe=None,
            profit_factor=None,
            duration_seconds=duration_seconds,
            passed=passed,
            ts=datetime.now(UTC),
        )

    def _average_results(
        self,
        results: list[BacktestResult],
        bot_config: BotConfig,
        candidate: MutationCandidate,
    ) -> BacktestResult:
        """Average multiple BacktestResult instances.

        Args:
            results: List of BacktestResult to average.
            bot_config: Bot configuration for the averaged result.
            candidate: Mutation candidate for the averaged result.

        Returns:
            Averaged BacktestResult.
        """
        if not results:
            return self._empty_result(bot_config, candidate)

        n = len(results)
        avg_profit_pct = sum(r.profit_total_pct for r in results) / n
        avg_profit_abs = sum(r.profit_total_abs for r in results) / n
        avg_trades = sum(r.total_trades for r in results) // n
        avg_dd = sum(r.max_drawdown_pct for r in results) / n
        avg_win_rate = sum(r.win_rate_pct for r in results) / n
        avg_duration = sum(r.duration_seconds for r in results) / n

        min_trades = int(bot_config.schedules.get("min_trades", "5"))
        passed = avg_profit_pct > 0 and avg_dd < 0.15 and avg_trades >= min_trades

        return BacktestResult(
            bot_id=bot_config.bot_id,
            candidate_sha256=candidate.candidate_sha256,
            total_trades=avg_trades,
            profit_total_pct=avg_profit_pct,
            profit_total_abs=avg_profit_abs,
            max_drawdown_pct=avg_dd,
            win_rate_pct=avg_win_rate,
            sharpe=None,
            profit_factor=None,
            duration_seconds=avg_duration,
            passed=passed,
            ts=datetime.now(UTC),
        )

    def _compute_stability(self, results: list[BacktestResult]) -> float:
        """Compute stability score from out-of-sample results.

        stability_score = 1.0 - (std of profit_pct / max of abs values), clamped 0-1.

        Args:
            results: List of out-of-sample BacktestResult.

        Returns:
            Stability score between 0.0 and 1.0.
        """
        if not results:
            return 0.0

        profits = [r.profit_total_pct for r in results]
        if len(profits) < 2:
            return 1.0

        mean_profit = sum(profits) / len(profits)
        variance = sum((p - mean_profit) ** 2 for p in profits) / (len(profits) - 1)
        std_profit = math.sqrt(variance)

        max_abs = max(abs(p) for p in profits)
        if max_abs == 0:
            return 1.0

        raw_score = 1.0 - (std_profit / max_abs)
        return max(0.0, min(1.0, raw_score))

    def _empty_result(self, bot_config: BotConfig, candidate: MutationCandidate) -> BacktestResult:
        """Create an empty (failed) BacktestResult.

        Args:
            bot_config: Bot configuration.
            candidate: Mutation candidate.

        Returns:
            Empty BacktestResult with passed=False.
        """
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
            ts=datetime.now(UTC),
        )
