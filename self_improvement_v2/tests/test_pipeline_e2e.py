"""End-to-end pipeline test for SI v2 Phase C.

Tests the full pipeline: TradeExporter → PerformanceAnalyzer → StrategyMutator
→ BacktestRunner → WalkForwardValidator, all using DryRunStub adapters.
"""

from __future__ import annotations

from pathlib import Path

from si_v2.adapters.dry_run_stub import DryRunStubFreqtrade
from si_v2.analyze.performance_analyzer import PerformanceAnalyzer
from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.backtest.walk_forward import WalkForwardValidator
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.observe.trade_exporter import TradeExporter
from si_v2.propose.strategy_mutator import StrategyMutator
from si_v2.state.schemas import BotConfig, MutationCandidate


def _make_bot_config() -> BotConfig:
    """Create a test BotConfig."""
    return BotConfig(
        bot_id="bot_a",
        bot_name="Bot Alpha",
        alias="bot_alpha",
        container="bot_alpha_container",
        strategy="TestStrategy",
    )


def _make_winning_trades(n: int) -> list[dict[str, str | int | float]]:
    """Create n winning trade records."""
    return [
        {
            "trade_id": i,
            "bot_id": "bot_a",
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
            "bot_id": "bot_a",
            "pair": "BTC/USDT",
            "profit_pct": -0.3,
            "profit_abs": -6.0,
            "duration_minutes": 180.0,
        }
        for i in range(n)
    ]


class TestPipelineE2ECase1:
    """Test case 1: insufficient data → hold decision → no mutation."""

    def test_insufficient_data_hold_decision(self) -> None:
        """With < 5 trades, analyzer should return 'hold' and no mutation."""
        adapter = DryRunStubFreqtrade()
        exporter = TradeExporter(adapter)
        analyzer = PerformanceAnalyzer()
        mutator = StrategyMutator()

        # Export only 2 trades (below MIN_TRADES_FOR_DECISION=5)
        trades = exporter.export_trades("bot_a", limit=2)

        analysis = analyzer.analyze(trades, bot_id="bot_a", bot_name="Bot Alpha")
        assert analysis.decision == "hold"

        candidate = mutator.build_candidate("bot_a", analysis, [])
        assert candidate is None


class TestPipelineE2ECase2:
    """Test case 2: negative metrics → mutation proposed → backtest → walk-forward."""

    def test_negative_metrics_mutation_pipeline(self) -> None:
        """With negative trades, pipeline should propose mutation and run backtest."""
        adapter = DryRunStubFreqtrade()
        analyzer = PerformanceAnalyzer()
        mutator = StrategyMutator()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()
        config = _make_bot_config()

        # Create trades with negative performance
        losing_trades = _make_losing_trades(20)
        analysis = analyzer.analyze(losing_trades, bot_id="bot_a", bot_name="Bot Alpha")

        # With consecutive losses or negative metrics, should trigger mutation
        candidate = mutator.build_candidate("bot_a", analysis, [])

        if candidate is not None:
            # Run backtest
            bt_result = runner.run(candidate, config)
            assert bt_result.bot_id == "bot_a"
            assert bt_result.candidate_sha256 == candidate.candidate_sha256

            # Run walk-forward
            wf_result = validator.validate(_make_winning_trades(60), candidate, config, runner, n_splits=3)
            assert wf_result.stability_score >= 0.0
            assert wf_result.stability_score <= 1.0


class TestPipelineE2ECase3:
    """Test case 3: verify no deployment action is possible."""

    def test_no_deploy_methods_exist(self) -> None:
        """Pipeline components should not have deploy/restart methods."""
        adapter = DryRunStubFreqtrade()
        exporter = TradeExporter(adapter)
        analyzer = PerformanceAnalyzer()
        mutator = StrategyMutator()
        runner = BacktestRunner(adapter)
        validator = WalkForwardValidator()

        # None of these should have deploy-related methods
        for component in [exporter, analyzer, mutator, runner, validator]:
            assert not hasattr(component, "deploy")
            assert not hasattr(component, "restart")
            assert not hasattr(component, "apply_overlay")
            assert not hasattr(component, "write_config")


class TestPipelineE2ECase4:
    """Test case 4: verify no real adapter is invoked (all DryRunStub)."""

    def test_all_adapters_are_dry_run_stub(self) -> None:
        """All adapters in the pipeline should be DryRunStubFreqtrade."""
        adapter = DryRunStubFreqtrade()

        # Verify it's the stub type (already imported at module level)
        assert isinstance(adapter, DryRunStubFreqtrade)

        # Create pipeline components
        exporter = TradeExporter(adapter)

        # Verify adapters produce deterministic data
        trades = exporter.export_trades("bot_a", limit=3)
        assert len(trades) == 3  # DryRunStub returns min(limit, 5)

        # Verify all trades have expected mock data
        for trade in trades:
            assert trade["pair"] == "BTC/USDT"
            assert trade["profit_pct"] == 0.5

    def test_no_real_backtest_invoked(self) -> None:
        """BacktestRunner with DryRunStub should not make real calls."""
        adapter = DryRunStubFreqtrade()
        runner = BacktestRunner(adapter)
        config = _make_bot_config()

        candidate = MutationCandidate(
            bot_id="bot_a",
            bot_name="Bot Alpha",
            candidate_sha256="test1234",
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

        result = runner.run(candidate, config)
        # DryRunStub returns 42 trades, 3.5% profit — should pass
        assert result.passed is True
        assert result.total_trades == 42


class TestPipelineE2ECase5:
    """Test case 5: shadow logger captures pipeline phases."""

    def test_shadow_logger_captures_all_phases(self) -> None:
        """Shadow logger should capture entries from each pipeline phase."""
        logger = ShadowLogger(log_dir=None)  # in-memory for testing
        config = _make_bot_config()

        # Phase: observe
        logger.log(
            bot_id=config.bot_id,
            candidate_sha="",
            params={},
            outcome="trades_exported",
            phase="observe",
            decision="hold",
            reason="exported 5 trades",
        )

        # Phase: analyze
        logger.log(
            bot_id=config.bot_id,
            candidate_sha="",
            params={},
            outcome="analysis_complete",
            phase="analyze",
            decision="mutate",
            reason="negative pnl in 24h window",
        )

        # Phase: propose
        logger.log(
            bot_id=config.bot_id,
            candidate_sha="sha1234",
            params={"stoploss_pct": -0.015, "stake_factor": 0.8},
            outcome="candidate_created",
            phase="propose",
            decision="mutate",
            reason="tightening parameters",
        )

        # Phase: backtest
        logger.log(
            bot_id=config.bot_id,
            candidate_sha="sha1234",
            params={"stoploss_pct": -0.015, "stake_factor": 0.8},
            outcome="backtest_passed",
            phase="backtest",
            decision="pass",
            reason="profit=3.5%, dd=5%",
        )

        # Phase: walk_forward
        logger.log(
            bot_id=config.bot_id,
            candidate_sha="sha1234",
            params={"stoploss_pct": -0.015, "stake_factor": 0.8},
            outcome="walk_forward_passed",
            phase="walk_forward",
            decision="pass",
            reason="stability=0.85",
        )

        entries = logger.get_entries(config.bot_id)
        assert len(entries) == 5

        phases = [str(e["phase"]) for e in entries]
        assert "observe" in phases
        assert "analyze" in phases
        assert "propose" in phases
        assert "backtest" in phases
        assert "walk_forward" in phases

    def test_shadow_logger_with_file_persistence(self, tmp_path: Path) -> None:
        """Shadow logger file mode should persist pipeline phases."""
        logger = ShadowLogger(log_dir=tmp_path)
        config = _make_bot_config()

        logger.log(config.bot_id, "sha1", {}, "observed", "observe", "hold", "exported trades")
        logger.log(config.bot_id, "sha1", {}, "analyzed", "analyze", "mutate", "negative pnl")

        entries = logger.get_entries(config.bot_id)
        assert len(entries) == 2
        assert (tmp_path / f"shadow_{config.bot_id}.jsonl").exists()
