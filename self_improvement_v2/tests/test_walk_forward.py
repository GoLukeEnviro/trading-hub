"""Unit tests for WalkForwardValidator."""

from __future__ import annotations

from si_v2.adapters.dry_run_stub import DryRunStubFreqtrade
from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.backtest.walk_forward import WalkForwardValidator
from si_v2.state.schemas import BotConfig, MutationCandidate


def _make_candidate() -> MutationCandidate:
    """Create a test MutationCandidate with sensible defaults."""
    return MutationCandidate(
        bot_id="test_bot",
        bot_name="Test Bot",
        candidate_sha256="abcd1234efgh5678",
        source_decision="mutate",
        parameters={
            "rsi_period": 14,
            "stoploss_pct": -0.02,
            "take_profit_pct": 0.035,
            "stake_factor": 1.0,
            "max_open_trades": 2,
            "cooldown_candles": 9,
        },
        active_overlay_candidates={},
    )


def _make_bot_config() -> BotConfig:
    """Create a test BotConfig with sensible defaults."""
    return BotConfig(
        bot_id="test_bot",
        bot_name="Test Bot",
        alias="test_alias",
        container="test_container",
        strategy="TestStrategy",
    )


def _make_profitable_trades(n: int) -> list[dict[str, str | int | float]]:
    """Create n profitable trade records."""
    return [
        {
            "trade_id": i,
            "bot_id": "test_bot",
            "pair": "BTC/USDT",
            "profit_pct": 0.5,
            "profit_abs": 10.0,
            "duration_minutes": 120.0,
        }
        for i in range(n)
    ]


def _make_losing_trades(n: int) -> list[dict[str, str | int | float]]:
    """Create n losing trade records."""
    return [
        {
            "trade_id": i,
            "bot_id": "test_bot",
            "pair": "BTC/USDT",
            "profit_pct": -0.3,
            "profit_abs": -6.0,
            "duration_minutes": 120.0,
        }
        for i in range(n)
    ]


class TestWalkForwardValidator:
    """Tests for WalkForwardValidator."""

    def test_insufficient_data_fails(self) -> None:
        """Fewer than 10 * n_splits trades should fail closed."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()
        trades = _make_profitable_trades(5)

        result = validator.validate(trades, candidate, config, runner, n_splits=3)

        assert result.passed is False
        assert "insufficient" in result.reason.lower()

    def test_profitable_trades_pass(self) -> None:
        """Sufficient profitable trades should pass walk-forward."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()
        # 3 splits * 10 = 30 minimum trades, give 60 for safety
        trades = _make_profitable_trades(60)

        result = validator.validate(trades, candidate, config, runner, n_splits=3)

        assert result.passed is True
        assert result.stability_score > 0.5
        assert result.out_of_sample_metrics.profit_total_pct > 0

    def test_losing_trades_fail(self) -> None:
        """All losing trades should fail walk-forward."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()
        trades = _make_losing_trades(60)

        result = validator.validate(trades, candidate, config, runner, n_splits=3)

        assert result.passed is False
        assert result.out_of_sample_metrics.profit_total_pct < 0

    def test_stability_score_range(self) -> None:
        """Stability score should be between 0.0 and 1.0."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()
        trades = _make_profitable_trades(60)

        result = validator.validate(trades, candidate, config, runner, n_splits=3)

        assert 0.0 <= result.stability_score <= 1.0

    def test_split_windows_correct_count(self) -> None:
        """Should produce exactly n_splits windows."""
        validator = WalkForwardValidator()
        windows = validator._split_windows(60, 3)

        assert len(windows) == 3

    def test_split_windows_cover_all_trades(self) -> None:
        """Windows should cover all trades without gaps."""
        validator = WalkForwardValidator()
        windows = validator._split_windows(60, 3)

        # First window starts at 0
        assert windows[0].train.start_idx == 0
        # Last window ends at total
        assert windows[-1].test.end_idx == 60

    def test_split_windows_train_70_test_30(self) -> None:
        """Each window should have 70/30 train/test split."""
        validator = WalkForwardValidator()
        windows = validator._split_windows(30, 3)

        for window in windows:
            total_window = window.test.end_idx - window.train.start_idx
            train_size = window.train.end_idx - window.train.start_idx
            ratio = train_size / total_window
            assert abs(ratio - 0.7) < 0.05  # approximately 70%

    def test_empty_trades_fail(self) -> None:
        """Empty trade list should fail."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()

        result = validator.validate([], candidate, config, runner, n_splits=3)

        assert result.passed is False
        assert result.stability_score == 0.0

    def test_result_has_in_and_out_sample(self) -> None:
        """Result should have both in-sample and out-of-sample metrics."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        candidate = _make_candidate()
        config = _make_bot_config()
        trades = _make_profitable_trades(60)

        result = validator.validate(trades, candidate, config, runner, n_splits=3)

        assert result.in_sample_metrics is not None
        assert result.out_of_sample_metrics is not None
        assert result.in_sample_metrics.bot_id == "test_bot"
        assert result.out_of_sample_metrics.bot_id == "test_bot"
