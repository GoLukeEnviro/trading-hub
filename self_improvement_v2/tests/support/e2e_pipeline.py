"""E2E dry-run pipeline support code for SI v2 integration tests.

Provides PipelineTrace/StageResult models, an injectable DryRunPipelineHarness
that orchestrates all 9 pipeline stages, and a create_e2e_scenario fixture
factory that produces deterministic test data.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from si_v2.adapters.dry_run_stub import (
    DryRunStubFreqtrade,
    DryRunTelegramAdapter,
)
from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter
from si_v2.analyze.performance_analyzer import PerformanceAnalyzer
from si_v2.approve.approval_gate import (
    ApprovalConfig,
    ApprovalGateManager,
)
from si_v2.backtest.backtest_runner import BacktestRunner
from si_v2.backtest.walk_forward import (
    WalkForwardResult,
    WalkForwardValidator,
)
from si_v2.deploy.deployment_plan import (
    DeploymentPlan,
    DeploymentPlanOrchestrator,
)
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.deploy.shadow_mode import ShadowModeManager
from si_v2.integrations.ai4trade.dry_run_adapters import (
    InMemoryOutcomeProvider,
    InMemoryRiskGateProvider,
    InMemorySignalProvider,
)
from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    OutcomeProvider,
    RiskGateProvider,
    SignalProvider,
)
from si_v2.observe.trade_exporter import TradeExporter
from si_v2.propose.strategy_adapter.mutator import (
    StrategyMutator as ASTStrategyMutator,
)
from si_v2.propose.strategy_adapter.sandbox import StrategySandbox
from si_v2.propose.strategy_adapter.schema import (
    StrategyMutationRequest,
    StrategyParameterName,
)
from si_v2.propose.strategy_adapter.validator import (
    StrategySandboxValidator,
)
from si_v2.propose.strategy_mutator import StrategyMutator
from si_v2.state.schemas import (
    AnalysisResult,
    BacktestResult,
    BotConfig,
    MutationCandidate,
)


class StageResult(BaseModel):
    """Result of a single pipeline stage."""

    stage_name: str
    status: str  # "passed" | "skipped" | "blocked" | "failed"
    reason: str = ""
    input_summary: str = ""
    output_summary: str = ""
    safety_flags: list[str] = []


class PipelineTrace(BaseModel):
    """Full trace of a pipeline execution with per-stage results."""

    stages: list[StageResult]
    started_at: str
    completed_at: str
    overall_status: str  # "passed" | "failed" | "blocked"
    error: str = ""


class DryRunPipelineHarness:
    """Dry-run pipeline orchestrator for E2E testing.

    Uses dependency injection for ALL external boundaries.
    Only InMemory/DryRun/stub/fixture implementations.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        sandbox_root: Path,
        signal_provider: SignalProvider,
        outcome_provider: OutcomeProvider,
        risk_gate: RiskGateProvider,
        adapter: FreqtradeAdapter,
        mutator: StrategyMutator,
        runner: BacktestRunner,
        walk_forward: WalkForwardValidator,
        approval: ApprovalGateManager,
        deploy_plan: DeploymentPlanOrchestrator,
        shadow: ShadowModeManager,
    ) -> None:
        """Initialize with all injected dependencies."""
        self._clock = clock
        self._sandbox_root = sandbox_root
        self._signal_provider = signal_provider
        self._outcome_provider = outcome_provider
        self._risk_gate = risk_gate
        self._adapter = adapter
        self._mutator = mutator
        self._runner = runner
        self._walk_forward = walk_forward
        self._approval = approval
        self._deploy_plan = deploy_plan
        self._shadow = shadow

    def run_pipeline(
        self,
        bot_config: BotConfig,
        strategy_fixture: Path,
        candidate_params: dict[str, float | int] | None = None,
    ) -> PipelineTrace:
        """Execute the full 9-stage pipeline.

        Stages:
          0. signal_check  — consult the signal provider
          1. observe       — TradeExporter with stub adapter
          2. analyze       — PerformanceAnalyzer on trade data
          3. propose       — StrategyMutator builds MutationCandidate
          4. mutate_sandbox — StrategySandbox + AST mutator on tmp_path
          5. backtest      — BacktestRunner with stub adapter
          6. walk_forward  — WalkForwardValidator with stub data
          7. approval      — ApprovalGateManager with DryRunTelegramAdapter
          8. deployment_plan — DeploymentPlanOrchestrator
          9. shadow_mode   — ShadowModeManager with injected clock

        Returns:
            PipelineTrace with results for all stages.
        """
        _ = candidate_params  # reserved for future use
        started_at = self._clock().isoformat()
        stages: list[StageResult] = []
        blocked = False
        error = ""

        # ── Stage 0: signal_check ──
        signal_check_result = self._run_signal_check(bot_config)
        stages.append(signal_check_result)
        blocked = signal_check_result.status in ("blocked", "failed")

        # ── Stage 1: observe ──
        trade_data: list[dict[str, str | int | float]] = []
        if not blocked:
            obs_result, trade_data = self._run_observe(bot_config)
            stages.append(obs_result)
            if obs_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("observe", "prior stage blocked"))

        # ── Stage 2: analyze ──
        analysis_result = None
        if not blocked:
            ana_result, analysis_result = self._run_analyze(bot_config, trade_data)
            stages.append(ana_result)
            if ana_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("analyze", "prior stage blocked"))

        # ── Stage 3: propose ──
        candidate: MutationCandidate | None = None
        if not blocked:
            prop_result, candidate = self._run_propose(bot_config, analysis_result)
            stages.append(prop_result)
            if prop_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("propose", "prior stage blocked"))

        # ── Stage 4: mutate_sandbox ──
        if not blocked and candidate is not None:
            sand_result, _sandbox_plan = self._run_mutate_sandbox(
                bot_config,
                candidate,
                strategy_fixture,
            )
            stages.append(sand_result)
            if sand_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("mutate_sandbox", "prior stage blocked or no candidate"))

        # ── Stage 5: backtest ──
        backtest_result: BacktestResult | None = None
        if not blocked and candidate is not None:
            bt_result, backtest_result = self._run_backtest(candidate, bot_config)
            stages.append(bt_result)
            if bt_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("backtest", "prior stage blocked or no candidate"))

        # ── Stage 6: walk_forward ──
        wf_result_obj = None
        if not blocked and candidate is not None and backtest_result is not None:
            wf_result, wf_result_obj = self._run_walk_forward(
                candidate,
                bot_config,
                trade_data,
            )
            stages.append(wf_result)
            if wf_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("walk_forward", "prior stage blocked or no candidate"))

        # ── Stage 7: approval ──
        approval_decision = None
        cond = not blocked and candidate is not None and backtest_result is not None and wf_result_obj is not None
        if cond:
            assert candidate is not None
            assert backtest_result is not None
            assert wf_result_obj is not None
            app_result, approval_decision = self._run_approval(
                backtest_result,
                wf_result_obj,
                bot_config,
                candidate,
            )
            stages.append(app_result)
            if app_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("approval", "prior stage blocked or missing results"))

        # ── Stage 8: deployment_plan ──
        plan = None
        cond2 = (
            not blocked
            and candidate is not None
            and backtest_result is not None
            and wf_result_obj is not None
            and approval_decision is not None
        )
        if cond2:
            assert candidate is not None
            assert backtest_result is not None
            assert wf_result_obj is not None
            assert approval_decision is not None
            dp_result, plan = self._run_deployment_plan(
                candidate,
                bot_config,
                backtest_result,
                wf_result_obj,
                approval_decision,
            )
            stages.append(dp_result)
            if dp_result.status != "passed":
                blocked = True
        else:
            stages.append(self._skipped("deployment_plan", "prior stage blocked or missing results"))

        # ── Stage 9: shadow_mode ──
        if not blocked and plan is not None:
            sh_result = self._run_shadow_check(bot_config, plan)
            stages.append(sh_result)
        else:
            stages.append(self._skipped("shadow_mode", "prior stage blocked or no plan"))

        completed_at = self._clock().isoformat()

        if error:
            overall_status = "failed"
        elif blocked:
            overall_status = "blocked"
        elif any(s.status == "failed" for s in stages):
            overall_status = "failed"
        else:
            overall_status = "passed"

        return PipelineTrace(
            stages=stages,
            started_at=started_at,
            completed_at=completed_at,
            overall_status=overall_status,
            error=error,
        )

    @staticmethod
    def _skipped(stage: str, reason: str) -> StageResult:
        """Create a 'skipped' StageResult."""
        return StageResult(stage_name=stage, status="skipped", reason=reason)

    # ------------------------------------------------------------------
    # Internal stage runners
    # ------------------------------------------------------------------

    def _run_signal_check(self, bot_config: BotConfig) -> StageResult:
        """Stage 0: check the signal provider for an advisory signal."""
        signal: AdvisorySignal = self._signal_provider.get_latest_signal(
            bot_config.bot_id,
        )
        if signal.direction == "hold":
            return StageResult(
                stage_name="signal_check",
                status="blocked",
                reason=(f"Signal provider returned '{signal.direction}' direction; pipeline HOLD"),
                input_summary=f"asset={signal.asset}",
                output_summary=(f"direction={signal.direction} confidence={signal.confidence}"),
            )
        return StageResult(
            stage_name="signal_check",
            status="passed",
            reason="Signal received, direction actionable",
            input_summary=f"asset={signal.asset}",
            output_summary=(f"direction={signal.direction} confidence={signal.confidence}"),
        )

    def _run_observe(
        self,
        bot_config: BotConfig,
    ) -> tuple[StageResult, list[dict[str, str | int | float]]]:
        """Stage 1: export trade data via TradeExporter."""
        try:
            exporter = TradeExporter(self._adapter)
            trades = exporter.export_trades(bot_config.bot_id, limit=100)
            return StageResult(
                stage_name="observe",
                status="passed",
                reason=f"Exported {len(trades)} trades",
                input_summary=f"bot_id={bot_config.bot_id}",
                output_summary=f"trades={len(trades)}",
            ), trades
        except Exception as exc:
            return StageResult(
                stage_name="observe",
                status="failed",
                reason=f"Trade export failed: {exc}",
            ), []

    def _run_analyze(
        self,
        bot_config: BotConfig,
        trades: list[dict[str, str | int | float]],
    ) -> tuple[StageResult, object]:
        """Stage 2: run PerformanceAnalyzer on trade data."""
        try:
            analyzer = PerformanceAnalyzer()
            analysis = analyzer.analyze(
                trades,
                bot_id=bot_config.bot_id,
                bot_name=bot_config.bot_name,
            )
            return StageResult(
                stage_name="analyze",
                status="passed",
                reason=f"decision={analysis.decision}",
                input_summary=f"trades={len(trades)}",
                output_summary=(f"decision={analysis.decision} windows={list(analysis.windows.keys())}"),
            ), analysis
        except Exception as exc:
            return StageResult(
                stage_name="analyze",
                status="failed",
                reason=f"Analysis failed: {exc}",
            ), None

    def _run_propose(
        self,
        bot_config: BotConfig,
        analysis_result: object,
    ) -> tuple[StageResult, MutationCandidate | None]:
        """Stage 3: build a MutationCandidate."""
        try:
            analysis = (
                AnalysisResult.model_validate(analysis_result)
                if not isinstance(analysis_result, AnalysisResult)
                else analysis_result
            )
            candidate = self._mutator.build_candidate(
                bot_config.bot_id,
                analysis,
                [],
            )
            if candidate is None:
                return StageResult(
                    stage_name="propose",
                    status="blocked",
                    reason=(f"No candidate proposed (decision={analysis.decision})"),
                    input_summary=f"decision={analysis.decision}",
                    output_summary="candidate=None",
                ), None
            return StageResult(
                stage_name="propose",
                status="passed",
                reason=f"Candidate proposed: {candidate.candidate_sha256}",
                input_summary=f"decision={analysis.decision}",
                output_summary=(f"sha={candidate.candidate_sha256} params={dict(candidate.parameters)}"),
            ), candidate
        except Exception as exc:
            return StageResult(
                stage_name="propose",
                status="failed",
                reason=f"Proposal failed: {exc}",
            ), None

    def _run_mutate_sandbox(
        self,
        bot_config: BotConfig,
        candidate: MutationCandidate,
        strategy_fixture: Path,
    ) -> tuple[StageResult, object]:
        """Stage 4: copy strategy to sandbox, apply AST mutation, validate."""
        try:
            sandbox_root = self._sandbox_root / f"sandbox_{candidate.candidate_sha256}"
            sandbox_root.mkdir(parents=True, exist_ok=True)

            # Build parameter changes from metadata_only_candidates
            changes: dict[StrategyParameterName, int] = {}
            for param_name, param_value in candidate.metadata_only_candidates.items():
                try:
                    spn = StrategyParameterName(param_name)
                    changes[spn] = param_value
                except ValueError:
                    continue

            if not changes:
                # No metadata changes — still copy the strategy to sandbox
                # for consistency but skip AST mutation
                sandbox = StrategySandbox()
                request = StrategyMutationRequest(
                    bot_id=bot_config.bot_id,
                    strategy_name=bot_config.strategy,
                    source_path=strategy_fixture,
                    sandbox_root=sandbox_root,
                    parameter_changes={},
                    candidate_sha=candidate.candidate_sha256,
                )
                plan = sandbox.create(request)
                return StageResult(
                    stage_name="mutate_sandbox",
                    status="passed",
                    reason=("No metadata changes; strategy copied to sandbox (no AST mutation needed)"),
                    input_summary=f"strategy={strategy_fixture.name}",
                    output_summary=f"sandbox={plan.sandbox_path}",
                ), plan

            # Create sandbox copy
            sandbox = StrategySandbox()
            request = StrategyMutationRequest(
                bot_id=bot_config.bot_id,
                strategy_name=bot_config.strategy,
                source_path=strategy_fixture,
                sandbox_root=sandbox_root,
                parameter_changes=changes,
                candidate_sha=candidate.candidate_sha256,
            )
            plan = sandbox.create(request)

            # Apply AST mutation
            ast_mutator = ASTStrategyMutator()
            plan = ast_mutator.apply(plan, changes)

            # Validate
            validator = StrategySandboxValidator()
            result = validator.validate(plan)

            if result.status != "ok":
                compile_flag = ["compile_error"] if result.compile_error is not None else []
                return StageResult(
                    stage_name="mutate_sandbox",
                    status="failed",
                    reason=f"Sandbox validation failed: {result.reason}",
                    input_summary=f"changes={dict(changes)}",
                    output_summary=f"status={result.status}",
                    safety_flags=compile_flag,
                ), plan

            return StageResult(
                stage_name="mutate_sandbox",
                status="passed",
                reason="Strategy mutated in sandbox and validated",
                input_summary=f"changes={dict(changes)}",
                output_summary=(f"changed={[str(p) for p in plan.changed_parameters]}"),
            ), plan

        except ValueError as exc:
            return StageResult(
                stage_name="mutate_sandbox",
                status="blocked",
                reason=f"Mutation blocked: {exc}",
            ), None
        except Exception as exc:
            return StageResult(
                stage_name="mutate_sandbox",
                status="failed",
                reason=f"Sandbox mutation failed: {exc}",
            ), None

    def _run_backtest(
        self,
        candidate: MutationCandidate,
        bot_config: BotConfig,
    ) -> tuple[StageResult, BacktestResult | None]:
        """Stage 5: run backtest via BacktestRunner."""
        try:
            result = self._runner.run(candidate, bot_config)
            status = "passed" if result.passed else "blocked"
            return StageResult(
                stage_name="backtest",
                status=status,
                reason=(f"profit={result.profit_total_pct} trades={result.total_trades} dd={result.max_drawdown_pct}"),
                input_summary=f"candidate={candidate.candidate_sha256}",
                output_summary=(f"passed={result.passed} profit={result.profit_total_pct}"),
            ), result
        except Exception as exc:
            return StageResult(
                stage_name="backtest",
                status="failed",
                reason=f"Backtest failed: {exc}",
            ), None

    def _run_walk_forward(
        self,
        candidate: MutationCandidate,
        bot_config: BotConfig,
        trades: list[dict[str, str | int | float]],
    ) -> tuple[StageResult, object]:
        """Stage 6: run walk-forward validation."""
        try:
            wf_result = self._walk_forward.validate(
                trades,
                candidate,
                bot_config,
                self._runner,
                n_splits=3,
            )
            status = "passed" if wf_result.passed else "blocked"
            return StageResult(
                stage_name="walk_forward",
                status=status,
                reason=(f"stability={wf_result.stability_score} reason={wf_result.reason}"),
                input_summary=(f"trades={len(trades)} candidate={candidate.candidate_sha256}"),
                output_summary=(f"passed={wf_result.passed} stability={wf_result.stability_score}"),
            ), wf_result
        except Exception as exc:
            return StageResult(
                stage_name="walk_forward",
                status="failed",
                reason=f"Walk-forward failed: {exc}",
            ), None

    def _run_approval(
        self,
        backtest_result: BacktestResult,
        walk_forward_result: object,
        bot_config: BotConfig,
        candidate: MutationCandidate,
    ) -> tuple[StageResult, object]:
        """Stage 7: run approval gate."""
        try:
            wf = (
                WalkForwardResult.model_validate(walk_forward_result)
                if not isinstance(walk_forward_result, WalkForwardResult)
                else walk_forward_result
            )
            decision = self._approval.evaluate(
                backtest_result=backtest_result,
                walk_forward_result=wf,
                bot_config=bot_config,
                candidate=candidate,
            )
            status = "passed" if decision.status.value == "pending" else "blocked"
            return StageResult(
                stage_name="approval",
                status=status,
                reason=(f"status={decision.status.value} reason={decision.reason}"),
                input_summary=f"candidate={candidate.candidate_sha256}",
                output_summary=f"decision={decision.status.value}",
            ), decision
        except Exception as exc:
            return StageResult(
                stage_name="approval",
                status="failed",
                reason=f"Approval failed: {exc}",
            ), None

    def _run_deployment_plan(
        self,
        candidate: MutationCandidate,
        bot_config: BotConfig,
        backtest_result: BacktestResult,
        walk_forward_result: object,
        approval_decision: object,
    ) -> tuple[StageResult, object]:
        """Stage 8: build deployment plan."""
        try:
            wf = (
                WalkForwardResult.model_validate(walk_forward_result)
                if not isinstance(walk_forward_result, WalkForwardResult)
                else walk_forward_result
            )
            human_approved = False  # Phase K: humans never approve
            plan = self._deploy_plan.build_deployment_plan(
                candidate=candidate,
                bot_config=bot_config,
                backtest_result=backtest_result,
                walk_forward_result=wf,
                human_approved=human_approved,
            )

            status = "passed"
            if plan.status in ("blocked", "rejected"):
                status = "blocked"

            return StageResult(
                stage_name="deployment_plan",
                status=status,
                reason=f"status={plan.status} phase={plan.phase.value}",
                input_summary=f"candidate={candidate.candidate_sha256}",
                output_summary=f"status={plan.status}",
            ), plan
        except Exception as exc:
            return StageResult(
                stage_name="deployment_plan",
                status="failed",
                reason=f"Deployment plan failed: {exc}",
            ), None

    def _run_shadow_check(
        self,
        bot_config: BotConfig,
        plan: object,
    ) -> StageResult:
        """Stage 9: check whether shadow mode was started."""
        try:
            dp = DeploymentPlan.model_validate(plan) if not isinstance(plan, DeploymentPlan) else plan

            if dp.status == "ready_for_shadow":
                status = self._shadow.get_shadow_status(bot_config.bot_id)
                return StageResult(
                    stage_name="shadow_mode",
                    status="passed",
                    reason=f"Shadow session started; status={status.value}",
                    output_summary=f"status={status.value}",
                )
            else:
                return StageResult(
                    stage_name="shadow_mode",
                    status="blocked",
                    reason=(f"Shadow not started: deployment status is '{dp.status}'"),
                    input_summary=f"plan_status={dp.status}",
                    output_summary="shadow=not_started",
                )
        except Exception as exc:
            return StageResult(
                stage_name="shadow_mode",
                status="failed",
                reason=f"Shadow check failed: {exc}",
            )


def create_e2e_scenario(tmp_path: Path) -> dict:
    """Create deterministic scenario data for E2E tests.

    Returns a dict with all components needed to construct and run
    the DryRunPipelineHarness.

    Args:
        tmp_path: pytest tmp_path for sandbox root.

    Returns:
        dict with keys:
            bot_config: BotConfig for a test bot
            trade_data: list of deterministic trade records
            strategy_fixture_path: Path to the simple strategy fixture
            candidate_params: expected parameter changes
            clock: callable returning a fixed datetime
            sandbox_root: tmp_path / "sandbox"
            signal_provider: InMemorySignalProvider
            outcome_provider: InMemoryOutcomeProvider
            risk_gate: InMemoryRiskGateProvider
            adapter: DryRunStubFreqtrade
            mutator: StrategyMutator
            runner: BacktestRunner
            walk_forward: WalkForwardValidator
            approval: ApprovalGateManager
            deploy_plan: DeploymentPlanOrchestrator
            shadow: ShadowModeManager
            harness: DryRunPipelineHarness
    """
    base_path = Path(__file__).resolve().parent.parent
    strategy_fixture_path = base_path / "fixtures" / "strategies" / "simple_strategy.py"
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir(parents=True, exist_ok=True)

    # Fixed clock for deterministic tests
    fixed_now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return fixed_now

    # Bot config
    bot_config = BotConfig(
        bot_id="test_bot",
        bot_name="TestBot",
        alias="test_bot",
        container="test_bot_container",
        strategy="TestStrategy",
    )

    # Trade data that triggers mutation (negative PnL trades to produce
    # a non-"hold" decision from the analyzer)
    trade_data: list[dict[str, str | int | float]] = [
        {
            "trade_id": i,
            "bot_id": "test_bot",
            "pair": "BTC/USDT",
            "profit_pct": -0.3,
            "profit_abs": -6.0,
            "duration_minutes": 180.0,
        }
        for i in range(30)
    ]

    # In-memory providers
    signal_provider = InMemorySignalProvider()
    outcome_provider = InMemoryOutcomeProvider()
    risk_gate = InMemoryRiskGateProvider()

    # Adapter and pipeline components
    adapter = DryRunStubFreqtrade()
    mutator = StrategyMutator()
    runner = BacktestRunner(adapter)
    walk_forward = WalkForwardValidator()
    telegram_adapter = DryRunTelegramAdapter()
    approval_config = ApprovalConfig()
    shadow_logger = ShadowLogger(log_dir=None)
    approval = ApprovalGateManager(
        telegram_adapter=telegram_adapter,
        approval_config=approval_config,
        shadow_logger=shadow_logger,
    )
    rollback_manager = RollbackPlanManager()
    shadow = ShadowModeManager(clock=clock)
    deploy_plan = DeploymentPlanOrchestrator(
        approval_manager=approval,
        rollback_manager=rollback_manager,
        shadow_manager=shadow,
        shadow_logger=shadow_logger,
        clock=clock,
    )

    harness = DryRunPipelineHarness(
        clock=clock,
        sandbox_root=sandbox_root,
        signal_provider=signal_provider,
        outcome_provider=outcome_provider,
        risk_gate=risk_gate,
        adapter=adapter,
        mutator=mutator,
        runner=runner,
        walk_forward=walk_forward,
        approval=approval,
        deploy_plan=deploy_plan,
        shadow=shadow,
    )

    return {
        "bot_config": bot_config,
        "trade_data": trade_data,
        "strategy_fixture_path": strategy_fixture_path,
        "candidate_params": {},
        "clock": clock,
        "sandbox_root": sandbox_root,
        "signal_provider": signal_provider,
        "outcome_provider": outcome_provider,
        "risk_gate": risk_gate,
        "adapter": adapter,
        "mutator": mutator,
        "runner": runner,
        "walk_forward": walk_forward,
        "approval": approval,
        "deploy_plan": deploy_plan,
        "shadow": shadow,
        "harness": harness,
    }
