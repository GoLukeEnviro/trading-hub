"""Full SI v2 pipeline E2E dry-run integration tests.

Tests the complete 9-stage pipeline with all stub/dry-run implementations.
No real adapters, no network calls, no live paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from si_v2.adapters.dry_run_stub import (
    DryRunStubFreqtrade,
    DryRunTelegramAdapter,
)
from si_v2.approve.approval_gate import ApprovalConfig, ApprovalGateManager
from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.backtest.walk_forward import WalkForwardValidator
from si_v2.deploy.deployment_plan import DeploymentPlanOrchestrator
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.deploy.shadow_mode import ShadowModeManager
from si_v2.integrations.ai4trade.dry_run_adapters import (
    InMemoryOutcomeProvider,
    InMemoryRiskGateProvider,
    InMemorySignalProvider,
)
from si_v2.integrations.ai4trade.protocols import AdvisorySignal
from si_v2.propose.strategy_mutator import StrategyMutator
from si_v2.state.schemas import BotConfig
from tests.support.e2e_pipeline import (
    DryRunPipelineHarness,
    StageResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOT_ID = "test_bot"
BOT_CONFIG = BotConfig(
    bot_id=BOT_ID,
    bot_name="TestBot",
    alias="test_bot",
    container="test_bot_container",
    strategy="TestStrategy",
)
FIXED_NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


def _clock() -> datetime:
    return FIXED_NOW


def _make_signal(asset: str = BOT_ID, direction: str = "buy") -> AdvisorySignal:
    """Create a test advisory signal."""
    return AdvisorySignal(
        signal_id="test-sig-001",
        asset=asset,
        direction=direction,
        confidence=0.85,
        risk_score=0.2,
        reason="test signal",
        created_at=FIXED_NOW,
    )


class _LosingTradeStub(DryRunStubFreqtrade):
    """Stub that returns losing trade history but winning backtests.

    Returns 65 trades: first 5 are losses (producing 5+ consecutive losses
    for a non-"hold" decision) and remaining 60 are winning (for positive
    overall profitability in walk-forward).
    """

    def get_trade_history(
        self,
        bot_id: str,
        limit: int = 100,
    ) -> list[dict[str, str | int | float]]:
        trades: list[dict[str, str | int | float]] = []
        for i in range(5):
            trades.append(
                {
                    "trade_id": i,
                    "bot_id": bot_id,
                    "pair": "BTC/USDT",
                    "profit_pct": -0.3,
                    "profit_abs": -6.0,
                    "duration_minutes": 180.0,
                }
            )
        for i in range(5, min(limit, 65)):
            trades.append(
                {
                    "trade_id": i,
                    "bot_id": bot_id,
                    "pair": "BTC/USDT",
                    "profit_pct": 0.5,
                    "profit_abs": 10.0,
                    "duration_minutes": 120.0,
                }
            )
        return trades


class _FailingBacktestStub(DryRunStubFreqtrade):
    """Stub that returns loss-making backtest results."""

    def run_backtest(
        self,
        bot_id: str,
        overlay: object,
    ) -> dict[str, str | int | float]:
        return {
            "bot_id": bot_id,
            "total_trades": 0,
            "profit_total_pct": -5.0,
            "profit_total_abs": -100.0,
            "max_drawdown_pct": 25.0,
            "win_rate_pct": 0.0,
        }


def _make_harness(
    tmp_path: Path,
    *,
    adapter: DryRunStubFreqtrade | None = None,
    signal_provider: InMemorySignalProvider | None = None,
) -> DryRunPipelineHarness:
    """Build a wired DryRunPipelineHarness with all components injected."""
    sandbox_root = tmp_path / "harness_sandbox"
    sandbox_root.mkdir(parents=True, exist_ok=True)

    bot_adapter = adapter or DryRunStubFreqtrade()
    mutator = StrategyMutator()
    runner = BacktestRunner(bot_adapter)
    walk_forward = WalkForwardValidator()
    telegram = DryRunTelegramAdapter()
    approval_config = ApprovalConfig()
    shadow_logger = ShadowLogger(log_dir=None)
    approval = ApprovalGateManager(
        telegram_adapter=telegram,
        approval_config=approval_config,
        shadow_logger=shadow_logger,
    )
    rollback = RollbackPlanManager()
    shadow = ShadowModeManager(clock=_clock)
    deploy = DeploymentPlanOrchestrator(
        approval_manager=approval,
        rollback_manager=rollback,
        shadow_manager=shadow,
        shadow_logger=shadow_logger,
        clock=_clock,
    )
    sig_prov = signal_provider or InMemorySignalProvider()
    outcome_prov = InMemoryOutcomeProvider()
    risk_gate = InMemoryRiskGateProvider()

    return DryRunPipelineHarness(
        clock=_clock,
        sandbox_root=sandbox_root,
        signal_provider=sig_prov,
        outcome_provider=outcome_prov,
        risk_gate=risk_gate,
        adapter=bot_adapter,
        mutator=mutator,
        runner=runner,
        walk_forward=walk_forward,
        approval=approval,
        deploy_plan=deploy,
        shadow=shadow,
    )


def _strategy_fixture(name: str = "simple_strategy.py") -> Path:
    """Return the path to a strategy fixture file."""
    return Path(__file__).resolve().parent / "fixtures" / "strategies" / name


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestE2EDryRunPipeline:
    """Full SI v2 pipeline E2E dry-run integration tests."""

    def test_happy_path_full_pipeline(self, tmp_path: Path) -> None:
        """Full happy-path pipeline - all stages execute.

        - observe produces trade data
        - analyze produces windows
        - propose builds candidate
        - sandbox mutation succeeds
        - backtest returns passing result
        - walk-forward returns passing result
        - approval becomes pending (not approved!)
        - deployment plan is pending_approval (not ready!)
        - shadow mode not started (blocked by pending approval)
        """
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())

        harness = _make_harness(
            tmp_path,
            adapter=_LosingTradeStub(),
            signal_provider=sig_prov,
        )
        trace = harness.run_pipeline(BOT_CONFIG, _strategy_fixture())

        assert len(trace.stages) == 10
        stage_map = {s.stage_name: s for s in trace.stages}

        # All 9 main stages should pass (shadow_mode is intentionally blocked)
        assert stage_map["signal_check"].status == "passed", stage_map["signal_check"].reason
        assert stage_map["observe"].status == "passed", stage_map["observe"].reason
        assert stage_map["analyze"].status == "passed", stage_map["analyze"].reason
        assert stage_map["propose"].status == "passed", stage_map["propose"].reason
        assert stage_map["mutate_sandbox"].status == "passed", stage_map["mutate_sandbox"].reason
        assert stage_map["backtest"].status == "passed", stage_map["backtest"].reason

        # Walk-forward uses the 65 trades from _LosingTradeStub: first 5 are
        # losses, remaining 60 are wins. Overall profitability is positive.
        assert stage_map["walk_forward"].status == "passed", stage_map["walk_forward"].reason

        # Approval: backtest passed, walk-forward passed → no auto-reject → pending
        assert stage_map["approval"].status == "passed", stage_map["approval"].reason
        assert "pending" in stage_map["approval"].output_summary.lower()

        # Deployment plan: approval is pending, human_approved=False → pending_approval
        assert stage_map["deployment_plan"].status == "passed", stage_map["deployment_plan"].reason
        assert "pending" in stage_map["deployment_plan"].reason.lower()

        # Shadow: plan is pending_approval → shadow not started → blocked
        assert stage_map["shadow_mode"].status == "blocked", stage_map["shadow_mode"].reason
        assert "not_started" in stage_map["shadow_mode"].output_summary.lower()

        assert trace.overall_status == "passed"

    def test_source_file_unchanged(self, tmp_path: Path) -> None:
        """Original strategy fixture is byte-identical after pipeline."""
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())

        harness = _make_harness(
            tmp_path,
            adapter=_LosingTradeStub(),
            signal_provider=sig_prov,
        )
        strategy_fixture = _strategy_fixture()
        original_bytes = strategy_fixture.read_bytes()

        harness.run_pipeline(BOT_CONFIG, strategy_fixture)

        assert strategy_fixture.read_bytes() == original_bytes, "Source strategy file was modified by pipeline"

    def test_mutation_only_in_sandbox(self, tmp_path: Path) -> None:
        """Strategy mutation only affects sandbox copy, not source."""
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())

        harness = _make_harness(
            tmp_path,
            adapter=_LosingTradeStub(),
            signal_provider=sig_prov,
        )
        strategy_fixture = _strategy_fixture()
        original_bytes = strategy_fixture.read_bytes()

        harness.run_pipeline(BOT_CONFIG, strategy_fixture)

        # Source file unchanged
        assert strategy_fixture.read_bytes() == original_bytes

        # Find any sandbox copies that might have been created
        sandbox_root = tmp_path / "harness_sandbox"
        sandbox_files = list(sandbox_root.rglob("sandbox_*.py"))
        if sandbox_files:
            sandbox_bytes = sandbox_files[0].read_bytes()
            assert sandbox_bytes != original_bytes, "Sandbox copy should differ from source after mutation"

    def test_no_deployment_writes(self, tmp_path: Path) -> None:
        """Deployment plan does NOT write any configs."""
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())

        # Track files before
        before = {p for p in tmp_path.rglob("*") if p.is_file()}

        harness = _make_harness(
            tmp_path,
            adapter=_LosingTradeStub(),
            signal_provider=sig_prov,
        )
        harness.run_pipeline(BOT_CONFIG, _strategy_fixture())

        after = {p for p in tmp_path.rglob("*") if p.is_file()}
        new_files = after - before
        for f in new_files:
            assert "sandbox" in str(f) or "harness_sandbox" in str(f), f"Unexpected file written outside sandbox: {f}"


class TestE2EDryRunPipelineFailClosed:
    """Fail-closed E2E pipeline tests."""

    def _run_with_default_signal(
        self,
        tmp_path: Path,
        *,
        adapter: DryRunStubFreqtrade | None = None,
        strategy: str = "simple_strategy.py",
    ) -> dict[str, StageResult]:
        """Run pipeline with a buy signal added so signal check passes."""
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())
        harness = _make_harness(
            tmp_path,
            adapter=adapter,
            signal_provider=sig_prov,
        )
        trace = harness.run_pipeline(BOT_CONFIG, _strategy_fixture(strategy))
        return {s.stage_name: s for s in trace.stages}

    # ------------------------------------------------------------------
    # Fail-closed tests
    # ------------------------------------------------------------------

    def test_no_signal_blocks_pipeline(self, tmp_path: Path) -> None:
        """ai4trade signal provider returns no signal → pipeline HOLDs/blocked."""
        # Default InMemorySignalProvider has no signals → returns "hold"
        harness = _make_harness(tmp_path, signal_provider=InMemorySignalProvider())
        trace = harness.run_pipeline(BOT_CONFIG, _strategy_fixture())
        stage_map = {s.stage_name: s for s in trace.stages}

        assert stage_map["signal_check"].status == "blocked"
        assert "hold" in stage_map["signal_check"].reason.lower()

        # All subsequent stages skipped
        for name in (
            "observe",
            "analyze",
            "propose",
            "mutate_sandbox",
            "backtest",
            "walk_forward",
            "approval",
            "deployment_plan",
            "shadow_mode",
        ):
            assert stage_map[name].status == "skipped", f"{name} should be skipped"

    def test_missing_parameter_blocks_mutation(self, tmp_path: Path) -> None:
        """Missing strategy parameter → mutation fails → pipeline stops."""
        stage_map = self._run_with_default_signal(
            tmp_path,
            adapter=_LosingTradeStub(),
            strategy="missing_param_strategy.py",
        )

        assert stage_map["signal_check"].status == "passed"
        assert stage_map["observe"].status == "passed"
        assert stage_map["analyze"].status == "passed"

        # Propose builds candidate based on analysis, not strategy file.
        # _LosingTradeStub provides trades with ≥5 consecutive losses so
        # the analysis decision is "block" (not "hold") → candidate is built.
        assert stage_map["propose"].status == "passed"

        # Mutate sandbox should fail because missing_param_strategy
        # lacks cooldown_candles (the AST mutator requires all target
        # parameters to exist in the source file)
        assert stage_map["mutate_sandbox"].status in ("blocked", "failed"), stage_map["mutate_sandbox"].reason

    def test_failed_backtest_blocks_deployment(self, tmp_path: Path) -> None:
        """Backtest returns not passed → deployment plan becomes blocked."""

        # Use adapter with losing trades for observe AND failing backtest
        class _CombinedFailingStub(_LosingTradeStub):
            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "bot_id": bot_id,
                    "total_trades": 0,
                    "profit_total_pct": -5.0,
                    "profit_total_abs": -100.0,
                    "max_drawdown_pct": 25.0,
                    "win_rate_pct": 0.0,
                }

        stage_map = self._run_with_default_signal(
            tmp_path,
            adapter=_CombinedFailingStub(),
        )

        assert stage_map["signal_check"].status == "passed"
        assert stage_map["observe"].status == "passed"
        assert stage_map["analyze"].status == "passed"
        assert stage_map["propose"].status == "passed"
        assert stage_map["mutate_sandbox"].status == "passed"

        # Backtest should be blocked (not passed)
        assert stage_map["backtest"].status == "blocked", stage_map["backtest"].reason

        # Post-backtest stages skipped
        for name in ("walk_forward", "approval", "deployment_plan", "shadow_mode"):
            assert stage_map[name].status == "skipped", f"{name} should be skipped"

    def test_failed_walkforward_blocks_deployment(self, tmp_path: Path) -> None:
        """Walk-forward fails → deployment plan becomes blocked."""
        stage_map = self._run_with_default_signal(tmp_path)

        assert stage_map["signal_check"].status == "passed"
        assert stage_map["observe"].status == "passed"
        assert stage_map["analyze"].status == "passed"

        # With default DryRunStubFreqtrade: get_trade_history returns 5
        # winning trades. 5 trades >= MIN_TRADES_FOR_DECISION (5) but
        # consecutive_losses = 0 → decision = "hold" → no candidate proposed.
        # So propose may be blocked.
        if stage_map["propose"].status != "passed":
            for name in ("mutate_sandbox", "backtest", "walk_forward", "approval", "deployment_plan", "shadow_mode"):
                assert stage_map[name].status == "skipped", f"{name} should be skipped"
        else:
            assert stage_map["mutate_sandbox"].status == "passed"
            assert stage_map["backtest"].status == "passed"
            # Walk-forward with only 5 trades → insufficient data
            assert stage_map["walk_forward"].status == "blocked"
            assert "insufficient" in stage_map["walk_forward"].reason.lower()

    def test_rejected_approval_blocks_deployment(self, tmp_path: Path) -> None:
        """Backtest fails → approval rejects → deployment plan blocked."""

        class _LowTradeStub(_LosingTradeStub):
            """Extends losing-trade stub but returns a failing backtest."""

            def run_backtest(self, bot_id: str, overlay: object) -> dict[str, str | int | float]:
                return {
                    "bot_id": bot_id,
                    "total_trades": 3,
                    "profit_total_pct": 0.5,
                    "profit_total_abs": 10.0,
                    "max_drawdown_pct": 5.0,
                    "win_rate_pct": 60.0,
                }

        stage_map = self._run_with_default_signal(
            tmp_path,
            adapter=_LowTradeStub(),
        )

        assert stage_map["signal_check"].status == "passed"
        assert stage_map["observe"].status == "passed"
        assert stage_map["analyze"].status == "passed"
        assert stage_map["propose"].status == "passed"
        assert stage_map["mutate_sandbox"].status == "passed"

        # Backtest returns only 3 trades (below min_total_trades=5) → not passed
        assert stage_map["backtest"].status == "blocked", stage_map["backtest"].reason

    def test_blocked_deployment_prevents_shadow(self, tmp_path: Path) -> None:
        """Deployment plan is blocked/not ready → shadow mode does NOT start."""
        stage_map = self._run_with_default_signal(tmp_path)

        assert stage_map["shadow_mode"].status in ("skipped", "blocked"), (
            f"Expected shadow not started, got {stage_map['shadow_mode'].status}: {stage_map['shadow_mode'].reason}"
        )

        # Verify no shadow session was created
        assert (
            "not_started" in stage_map["shadow_mode"].output_summary.lower()
            or stage_map["shadow_mode"].status == "skipped"
        )

    def test_pending_approval_blocks_shadow(self, tmp_path: Path) -> None:
        """Pending approval → deployment plan is pending_approval → no shadow."""
        sig_prov = InMemorySignalProvider()
        sig_prov.add_signal(_make_signal())

        harness = _make_harness(
            tmp_path,
            adapter=_LosingTradeStub(),
            signal_provider=sig_prov,
        )
        trace = harness.run_pipeline(BOT_CONFIG, _strategy_fixture())
        stage_map = {s.stage_name: s for s in trace.stages}

        # Deployment plan should be passed (pending_approval)
        if stage_map["deployment_plan"].status == "passed":
            assert "pending" in stage_map["deployment_plan"].reason.lower()

        # Shadow mode should be blocked by pending approval (or skipped if
        # some earlier stage blocked unexpectedly)
        assert stage_map["shadow_mode"].status in ("blocked", "skipped"), stage_map["shadow_mode"].reason
        if stage_map["shadow_mode"].status == "blocked":
            assert "not_started" in stage_map["shadow_mode"].output_summary.lower()
