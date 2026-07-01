"""Tests for SI-v2 Autonomy Policy — policy-as-code for autonomous dry-run decisions.

Test coverage:
  1. All gates pass → AUTO_DRY_RUN_APPROVED
  2. Non-canary target with mutation → AUTO_DRY_RUN_BLOCKED
  3. Kill switch HALT_NEW → blocked
  4. Kill switch EMERGENCY → blocked
  5. dry_run false → blocked
  6. RiskGuard FAIL → blocked
  7. Unsafe parameter → blocked
  8. Active measurement window → deferred
  9. Missing rollback → blocked
  10. Observability-only non-canary candidate → approved only if no runtime/bot mutation
"""

from __future__ import annotations

from si_v2.autonomy import (
    AutonomyPolicyInput,
    evaluate_autonomy_policy,
)


def _make_input(
    *,
    candidate_id: str = "test_candidate_001",
    candidate_sha: str = "a1b2c3d4e5f6",
    target_bot: str = "freqtrade-freqforge-canary",
    hypothesis: str = "test_hypothesis",
    parameter_overlay: dict[str, int | float] | None = None,
    source_cycle: str = "cycle_001",
    confidence: float | None = 0.85,
    dry_run_all_true: bool = True,
    kill_switch_mode: str = "NORMAL",
    riskguard_status: str = "PASS",
    active_measurement_candidate_id: str | None = None,
    rollback_available: bool = True,
    allowlist_compatible: bool = True,
    canary_first: bool = True,
    open_trades_on_target: int | None = None,
) -> AutonomyPolicyInput:
    return AutonomyPolicyInput(
        candidate_id=candidate_id,
        candidate_sha=candidate_sha,
        target_bot=target_bot,
        hypothesis=hypothesis,
        parameter_overlay=parameter_overlay or {"max_open_trades": 2},
        source_cycle=source_cycle,
        confidence=confidence,
        dry_run_all_true=dry_run_all_true,
        kill_switch_mode=kill_switch_mode,
        riskguard_status=riskguard_status,
        active_measurement_candidate_id=active_measurement_candidate_id,
        rollback_available=rollback_available,
        allowlist_compatible=allowlist_compatible,
        canary_first=canary_first,
        open_trades_on_target=open_trades_on_target,
    )


class TestAutonomyPolicyApproved:
    """All gates pass → AUTO_DRY_RUN_APPROVED."""

    def test_all_gates_pass(self) -> None:
        input_ = _make_input()
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons
        assert decision.candidate_id == "test_candidate_001"
        assert decision.candidate_sha == "a1b2c3d4e5f6"
        assert decision.target_bot == "freqtrade-freqforge-canary"
        assert decision.reasons == ()
        assert "approved" in decision.required_next_step.lower()

    def test_with_cooldown_candles(self) -> None:
        input_ = _make_input(parameter_overlay={"cooldown_candles": 4})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons

    def test_with_rsi_period(self) -> None:
        input_ = _make_input(parameter_overlay={"rsi_period": 14})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons

    def test_with_stoploss(self) -> None:
        input_ = _make_input(parameter_overlay={"stoploss_pct": -0.02})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons

    def test_with_take_profit(self) -> None:
        input_ = _make_input(parameter_overlay={"take_profit_pct": 0.05})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons

    def test_with_stake_factor(self) -> None:
        input_ = _make_input(parameter_overlay={"stake_factor": 1.5})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons

    def test_with_max_open_trades(self) -> None:
        input_ = _make_input(parameter_overlay={"max_open_trades": 2})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons


class TestAutonomyPolicyBlocked:
    """Various conditions that should block."""

    def test_non_canary_target(self) -> None:
        input_ = _make_input(
            target_bot="freqtrade-freqforge",
            canary_first=False,
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("non_canary" in r for r in decision.reasons)

    def test_kill_switch_halt_new(self) -> None:
        input_ = _make_input(kill_switch_mode="HALT_NEW")
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("halt_new" in r.lower() for r in decision.reasons)

    def test_kill_switch_emergency(self) -> None:
        input_ = _make_input(kill_switch_mode="EMERGENCY")
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("emergency" in r.lower() for r in decision.reasons)

    def test_dry_run_false(self) -> None:
        input_ = _make_input(dry_run_all_true=False)
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("dry_run" in r.lower() for r in decision.reasons)

    def test_riskguard_fail(self) -> None:
        input_ = _make_input(riskguard_status="FAIL")
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("riskguard" in r.lower() for r in decision.reasons)

    def test_unsafe_parameter(self) -> None:
        input_ = _make_input(parameter_overlay={"exchange": "binance"})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("forbidden" in r.lower() for r in decision.reasons)

    def test_unknown_parameter(self) -> None:
        input_ = _make_input(parameter_overlay={"unknown_param": 42})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("unsafe" in r.lower() for r in decision.reasons)

    def test_missing_rollback(self) -> None:
        input_ = _make_input(rollback_available=False)
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("rollback" in r.lower() for r in decision.reasons)

    def test_not_allowlist_compatible(self) -> None:
        input_ = _make_input(allowlist_compatible=False)
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("allowlist" in r.lower() for r in decision.reasons)

    def test_not_canary_first(self) -> None:
        input_ = _make_input(canary_first=False)
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("canary_first" in r.lower() for r in decision.reasons)

    def test_empty_parameter_overlay(self) -> None:
        input_ = AutonomyPolicyInput(
            candidate_id="test_candidate_001",
            candidate_sha="a1b2c3d4e5f6",
            target_bot="freqtrade-freqforge-canary",
            hypothesis="test_hypothesis",
            parameter_overlay={},
            source_cycle="cycle_001",
            confidence=0.85,
            dry_run_all_true=True,
            kill_switch_mode="NORMAL",
            riskguard_status="PASS",
            active_measurement_candidate_id=None,
            rollback_available=True,
            allowlist_compatible=True,
            canary_first=True,
            open_trades_on_target=None,
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("empty" in r.lower() for r in decision.reasons)

    def test_forbidden_strategy_key(self) -> None:
        input_ = _make_input(parameter_overlay={"strategy": "SomeStrategy"})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("forbidden" in r.lower() for r in decision.reasons)

    def test_forbidden_pair_whitelist(self) -> None:
        input_ = _make_input(parameter_overlay={"pair_whitelist": ["BTC/USDT"]})
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons
        assert any("forbidden" in r.lower() for r in decision.reasons)

    def test_multiple_blockers(self) -> None:
        """Multiple violations should all be reported."""
        input_ = _make_input(
            dry_run_all_true=False,
            kill_switch_mode="HALT_NEW",
            riskguard_status="FAIL",
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED"
        assert len(decision.reasons) >= 3


class TestAutonomyPolicyDeferred:
    """Conditions that should defer rather than block."""

    def test_active_measurement_window(self) -> None:
        input_ = _make_input(
            active_measurement_candidate_id="other_candidate_002",
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_DEFERRED", decision.reasons
        assert any("measurement" in r.lower() for r in decision.reasons)

    def test_same_candidate_measuring(self) -> None:
        """If the same candidate is already being measured, it should pass."""
        input_ = _make_input(
            candidate_id="test_candidate_001",
            active_measurement_candidate_id="test_candidate_001",
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_APPROVED", decision.reasons


class TestAutonomyPolicyEdgeCases:
    """Edge cases and boundary conditions."""

    def test_unknown_kill_switch_mode(self) -> None:
        input_ = _make_input(kill_switch_mode="UNKNOWN")
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons

    def test_riskguard_unknown(self) -> None:
        input_ = _make_input(riskguard_status="UNKNOWN")
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons

    def test_observability_only_non_canary(self) -> None:
        """Non-canary with no mutation should be blocked (no canary-first)."""
        input_ = _make_input(
            target_bot="freqtrade-regime-hybrid",
            canary_first=False,
            parameter_overlay={"max_open_trades": 2},
        )
        decision = evaluate_autonomy_policy(input_)
        assert decision.status == "AUTO_DRY_RUN_BLOCKED", decision.reasons

    def test_to_dict_approved(self) -> None:
        input_ = _make_input()
        decision = evaluate_autonomy_policy(input_)
        d = decision.to_dict()
        assert d["status"] == "AUTO_DRY_RUN_APPROVED"
        assert d["candidate_id"] == "test_candidate_001"
        assert d["candidate_sha"] == "a1b2c3d4e5f6"
        assert d["target_bot"] == "freqtrade-freqforge-canary"
        assert d["reasons"] == []
        assert "approved" in d["required_next_step"].lower()

    def test_to_dict_blocked(self) -> None:
        input_ = _make_input(dry_run_all_true=False)
        decision = evaluate_autonomy_policy(input_)
        d = decision.to_dict()
        assert d["status"] == "AUTO_DRY_RUN_BLOCKED"
        assert len(d["reasons"]) > 0

    def test_to_dict_deferred(self) -> None:
        input_ = _make_input(
            active_measurement_candidate_id="other_candidate",
        )
        decision = evaluate_autonomy_policy(input_)
        d = decision.to_dict()
        assert d["status"] == "AUTO_DRY_RUN_DEFERRED"
        assert len(d["reasons"]) > 0
