"""Test performance analyzer with various trade scenarios."""

from __future__ import annotations

from si_v2.analyze.performance_analyzer import PerformanceAnalyzer


class TestPerformanceAnalyzer:
    """Tests for the PerformanceAnalyzer class."""

    def test_empty_trades_returns_hold(self, analyzer: PerformanceAnalyzer) -> None:
        """Empty trades list should result in 'hold' decision."""
        result = analyzer.analyze([], bot_id="bot_a", bot_name="Bot A")
        assert result.decision == "hold"
        assert result.bot_id == "bot_a"

    def test_empty_trades_zero_stats(self, analyzer: PerformanceAnalyzer) -> None:
        """Empty trades should produce zero stats in all windows."""
        result = analyzer.analyze([], bot_id="bot_a", bot_name="Bot A")
        for _window_name, stats in result.windows.items():
            assert stats.trades == 0
            assert stats.wins == 0
            assert stats.losses == 0
            assert stats.pnl_abs == 0.0
            assert stats.win_rate_pct is None
            assert stats.consecutive_losses == 0

    def test_winning_trades(self, analyzer: PerformanceAnalyzer) -> None:
        """Winning trades should produce positive stats."""
        trades = [
            {"profit_pct": 1.5, "profit_abs": 30.0},
            {"profit_pct": 2.0, "profit_abs": 40.0},
            {"profit_pct": 0.5, "profit_abs": 10.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        stats = result.windows["12h"]
        assert stats.wins == 3
        assert stats.losses == 0
        assert stats.pnl_abs == 80.0
        assert stats.win_rate_pct == 100.0
        assert stats.consecutive_losses == 0

    def test_losing_trades(self, analyzer: PerformanceAnalyzer) -> None:
        """Losing trades should produce negative stats."""
        trades = [
            {"profit_pct": -1.5, "profit_abs": -30.0},
            {"profit_pct": -2.0, "profit_abs": -40.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        stats = result.windows["12h"]
        assert stats.wins == 0
        assert stats.losses == 2
        assert stats.pnl_abs == -70.0
        assert stats.consecutive_losses == 2

    def test_mixed_trades(self, analyzer: PerformanceAnalyzer) -> None:
        """Mix of winning and losing trades."""
        trades = [
            {"profit_pct": 2.0, "profit_abs": 40.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": 1.5, "profit_abs": 30.0},
            {"profit_pct": -0.5, "profit_abs": -10.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        stats = result.windows["12h"]
        assert stats.trades == 4
        assert stats.wins == 2
        assert stats.losses == 2
        assert stats.pnl_abs == 40.0
        assert stats.win_rate_pct == 50.0

    def test_windows_created(self, analyzer: PerformanceAnalyzer) -> None:
        """All default windows should be present in the result."""
        result = analyzer.analyze([], bot_id="bot_a", bot_name="Bot A")
        assert "12h" in result.windows
        assert "24h" in result.windows
        assert "72h" in result.windows

    def test_insufficient_trades_hold(self, analyzer: PerformanceAnalyzer) -> None:
        """Fewer than 5 trades should always result in 'hold'."""
        trades = [
            {"profit_pct": -5.0, "profit_abs": -100.0},
            {"profit_pct": -5.0, "profit_abs": -100.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        assert result.decision == "hold"

    def test_consecutive_losses_block(self, analyzer: PerformanceAnalyzer) -> None:
        """5+ consecutive losses should result in 'block' decision."""
        trades = [
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        assert result.decision == "block"

    def test_profit_factor_computed(self, analyzer: PerformanceAnalyzer) -> None:
        """Profit factor should be computed when there are losses."""
        trades = [
            {"profit_pct": 2.0, "profit_abs": 40.0},
            {"profit_pct": -1.0, "profit_abs": -20.0},
            {"profit_pct": 1.0, "profit_abs": 20.0},
            {"profit_pct": -0.5, "profit_abs": -10.0},
            {"profit_pct": 1.5, "profit_abs": 30.0},
        ]
        result = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot A")
        stats = result.windows["12h"]
        assert stats.profit_factor is not None
        # gross_profit = 90, gross_loss = 30, factor = 3.0
        assert stats.profit_factor == 3.0
