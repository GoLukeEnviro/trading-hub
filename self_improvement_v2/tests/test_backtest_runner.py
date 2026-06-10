"""Unit tests for BacktestRunner with DryRunStub adapter."""

from __future__ import annotations

from si_v2.adapters.dry_run_stub import DryRunStubFreqtrade
from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.state.schemas import BotConfig, MutationCandidate


def _make_candidate(**overrides: str | int | float | dict[str, float | int]) -> MutationCandidate:
    """Create a test MutationCandidate with sensible defaults."""
    defaults: dict[str, str | int | float | dict[str, float | int]] = {
        "bot_id": "test_bot",
        "bot_name": "Test Bot",
        "candidate_sha256": "abcd1234efgh5678",
        "source_decision": "mutate",
        "parameters": {
            "rsi_period": 14,
            "stoploss_pct": -0.02,
            "take_profit_pct": 0.035,
            "stake_factor": 1.0,
            "max_open_trades": 2,
            "cooldown_candles": 9,
        },
        "active_overlay_candidates": {},
    }
    defaults.update(overrides)
    return MutationCandidate(**defaults)  # type: ignore[arg-type]


def _make_bot_config(**overrides: str | dict[str, str]) -> BotConfig:
    """Create a test BotConfig with sensible defaults."""
    defaults: dict[str, str | dict[str, str]] = {
        "bot_id": "test_bot",
        "bot_name": "Test Bot",
        "alias": "test_alias",
        "container": "test_container",
        "strategy": "TestStrategy",
    }
    defaults.update(overrides)
    return BotConfig(**defaults)  # type: ignore[arg-type]


class TestBacktestRunner:
    """Tests for BacktestRunner."""

    def test_pass_with_dry_run_stub(self) -> None:
        """DryRunStub returns positive profit, low drawdown, 42 trades — should pass."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.passed is True
        assert result.total_trades == 42
        assert result.profit_total_pct == 3.5
        assert result.bot_id == "test_bot"
        assert result.candidate_sha256 == "abcd1234efgh5678"

    def test_fail_low_trades(self) -> None:
        """Results with fewer than min_trades should fail."""

        class LowTradeAdapter:
            def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
                return {"bot_id": bot_id}

            def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
                return []

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "total_trades": 2,
                    "profit_total_pct": 5.0,
                    "profit_total_abs": 100.0,
                    "max_drawdown_pct": 0.05,
                    "win_rate_pct": 80.0,
                }

        runner = BacktestRunner(LowTradeAdapter())  # type: ignore[arg-type]
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.passed is False
        assert result.total_trades == 2

    def test_fail_high_drawdown(self) -> None:
        """Results with drawdown >= 0.15 should fail."""

        class HighDDAdapter:
            def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
                return {"bot_id": bot_id}

            def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
                return []

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "total_trades": 20,
                    "profit_total_pct": 2.0,
                    "profit_total_abs": 40.0,
                    "max_drawdown_pct": 0.20,
                    "win_rate_pct": 55.0,
                }

        runner = BacktestRunner(HighDDAdapter())  # type: ignore[arg-type]
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.passed is False

    def test_fail_negative_profit(self) -> None:
        """Results with negative profit should fail."""

        class NegProfitAdapter:
            def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
                return {"bot_id": bot_id}

            def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
                return []

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "total_trades": 30,
                    "profit_total_pct": -5.0,
                    "profit_total_abs": -100.0,
                    "max_drawdown_pct": 0.10,
                    "win_rate_pct": 30.0,
                }

        runner = BacktestRunner(NegProfitAdapter())  # type: ignore[arg-type]
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.passed is False
        assert result.profit_total_pct == -5.0

    def test_fail_closed_on_empty_result(self) -> None:
        """Empty adapter result should fail closed."""

        class EmptyAdapter:
            def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
                return {}

            def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
                return []

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {}

        runner = BacktestRunner(EmptyAdapter())  # type: ignore[arg-type]
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.passed is False
        assert result.total_trades == 0

    def test_custom_min_trades_from_config(self) -> None:
        """BotConfig schedules can override min_trades."""

        class MarginalAdapter:
            def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
                return {}

            def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
                return []

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "total_trades": 3,
                    "profit_total_pct": 1.0,
                    "profit_total_abs": 20.0,
                    "max_drawdown_pct": 0.05,
                    "win_rate_pct": 60.0,
                }

        runner = BacktestRunner(MarginalAdapter())  # type: ignore[arg-type]
        candidate = _make_candidate()
        config = _make_bot_config(schedules={"min_trades": "3"})

        result = runner.run(candidate, config)

        assert result.passed is True
        assert result.total_trades == 3

    def test_result_has_timestamp(self) -> None:
        """Result should have a UTC timestamp."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        candidate = _make_candidate()
        config = _make_bot_config()

        result = runner.run(candidate, config)

        assert result.ts is not None
        assert result.ts.tzinfo is not None

    def test_overlay_builds_correctly(self) -> None:
        """Verify overlay is built from candidate parameters."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        candidate = _make_candidate()

        overlay = runner._build_overlay(candidate)

        assert overlay.max_open_trades == 2
        assert overlay.stoploss == -0.02
        assert overlay.stake_amount == 20.0
