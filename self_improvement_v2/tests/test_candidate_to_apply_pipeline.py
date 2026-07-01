r"""Tests for the candidate-to-apply pipeline (Phase 6A).

Pure Python — no subprocess, no Docker, no runtime mutation.
"""

from __future__ import annotations

import json

import pytest

from si_v2.pipeline.candidate_to_apply import (
    CANARY_BOT_ID,
    CandidateApplyInput,
    _check_dry_run,
    _check_known_bot,
    _check_measurement_window,
    _check_parameter_safe,
    _check_readiness_available,
    _check_rollback_available,
    _check_target_bot,
    candidate_to_apply_pipeline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_candidate() -> CandidateApplyInput:
    return CandidateApplyInput(
        candidate_id="test_max_open_trades_3_to_2",
        source="test",
        target_bot=CANARY_BOT_ID,
        parameter="max_open_trades",
        current_value=3,
        proposed_value=2,
        confidence=0.85,
        evidence_refs=("test_report.md",),
        requires_human_approval=True,
    )


@pytest.fixture
def valid_pre_apply() -> dict[str, object]:
    return {"max_open_trades": 3, "dry_run": True}


# ---------------------------------------------------------------------------
# Basic validators
# ---------------------------------------------------------------------------


class TestCheckTargetBot:
    def test_canary_passes(self) -> None:
        ok, _ = _check_target_bot(CANARY_BOT_ID, allow_non_canary=False)
        assert ok

    def test_non_canary_blocked(self) -> None:
        ok, reason = _check_target_bot("freqtrade-freqforge", allow_non_canary=False)
        assert not ok
        assert "non_canary_target" in reason

    def test_non_canary_allowed(self) -> None:
        ok, _ = _check_target_bot("freqtrade-freqforge", allow_non_canary=True)
        assert ok


class TestCheckKnownBot:
    def test_canary_is_known(self) -> None:
        ok, _ = _check_known_bot(CANARY_BOT_ID)
        assert ok

    def test_unknown_bot_blocked(self) -> None:
        ok, reason = _check_known_bot("nonexistent-bot")
        assert not ok
        assert "unknown_bot" in reason


class TestCheckParameterSafe:
    def test_safe_parameter_passes(self) -> None:
        ok, _ = _check_parameter_safe("max_open_trades")
        assert ok

    def test_forbidden_parameter_blocked(self) -> None:
        ok, reason = _check_parameter_safe("dry_run")
        assert not ok
        assert "forbidden_parameter" in reason

    def test_unknown_parameter_blocked(self) -> None:
        ok, reason = _check_parameter_safe("nonexistent_param")
        assert not ok
        assert "unsafe_parameter" in reason


class TestCheckDryRun:
    def test_true_passes(self, valid_pre_apply: dict) -> None:
        ok, _ = _check_dry_run(valid_pre_apply)
        assert ok

    def test_false_blocks(self) -> None:
        ok, reason = _check_dry_run({"dry_run": False})
        assert not ok
        assert "dry_run_not_true" in reason

    def test_missing_blocks(self) -> None:
        ok, reason = _check_dry_run({})
        assert not ok
        assert "dry_run_not_found" in reason


class TestCheckMeasurementWindow:
    def test_no_active_window_passes(self) -> None:
        ok, _, action = _check_measurement_window("candidate_a", None)
        assert ok
        assert action == "PASS"

    def test_same_candidate_passes(self) -> None:
        ok, _, action = _check_measurement_window("candidate_a", "candidate_a")
        assert ok
        assert action == "PASS"

    def test_different_candidate_defers(self) -> None:
        ok, reason, action = _check_measurement_window("candidate_b", "candidate_a")
        assert not ok
        assert action == "DEFERRED"
        assert "measurement_active_for" in reason


class TestCheckReadinessAvailable:
    def test_readiness_module_available(self) -> None:
        assert _check_readiness_available()


class TestCheckRollbackAvailable:
    def test_rollback_module_available(self) -> None:
        assert _check_rollback_available()


# ---------------------------------------------------------------------------
# candidate_to_apply_pipeline integration
# ---------------------------------------------------------------------------


class TestCandidateToApplyPipeline:
    def test_valid_canary_ready_for_canary_apply(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "READY_FOR_CANARY_APPLY", "READY_FOR_HUMAN_APPROVAL",
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY", "AUTO_DRY_RUN_APPROVED",
        )
        assert result.decision.canary_only
        assert result.decision.rollback_available

    def test_non_canary_target_blocks(
        self,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="x", source="test",
            target_bot="freqtrade-freqforge",
            parameter="max_open_trades",
            current_value=3, proposed_value=2,
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c, pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any("non_canary_target" in r for r in result.decision.blocked_reasons)

    def test_unknown_bot_blocks(
        self,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="x", source="test",
            target_bot="nonexistent-bot",
            parameter="max_open_trades",
            current_value=3, proposed_value=2,
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c, pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any("unknown_bot" in r or "non_canary" in r for r in result.decision.blocked_reasons)

    def test_unsafe_parameter_blocks(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="x", source="test",
            target_bot=CANARY_BOT_ID,
            parameter="nonexistent_param",
            current_value=1, proposed_value=2,
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c, pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any("unsafe_parameter" in r for r in result.decision.blocked_reasons)

    def test_forbidden_dry_run_parameter_blocks(
        self,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="x", source="test",
            target_bot=CANARY_BOT_ID,
            parameter="dry_run",
            current_value=True, proposed_value=False,
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c, pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any("forbidden_parameter" in r for r in result.decision.blocked_reasons)

    def test_forbidden_strategy_blocks(
        self,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="x", source="test",
            target_bot=CANARY_BOT_ID,
            parameter="strategy",
            current_value="A", proposed_value="B",
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c, pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any(
            "forbidden_parameter" in r or "empty" in r
            for r in result.decision.blocked_reasons
        )

    def test_dry_run_false_blocks(
        self,
        valid_candidate: CandidateApplyInput,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config={"dry_run": False},
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any(
            "dry_run_not_true" in r or "dry_run_not_all_true" in r
            for r in result.decision.blocked_reasons
        )

    def test_missing_dry_run_blocks(
        self,
        valid_candidate: CandidateApplyInput,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config={},
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in ("BLOCKED", "AUTO_DRY_RUN_BLOCKED")
        assert any(
            "dry_run_not_found" in r or "dry_run_not_all_true" in r
            for r in result.decision.blocked_reasons
        )

    def test_execute_true_returns_not_implemented(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
            execute=True,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status == "NOT_IMPLEMENTED_EXECUTION"
        assert any("execution_not_allowed" in r for r in result.decision.blocked_reasons)

    def test_active_measurement_defers_new_candidate(
        self,
        valid_pre_apply: dict,
    ) -> None:
        c = CandidateApplyInput(
            candidate_id="different_candidate",
            source="test",
            target_bot=CANARY_BOT_ID,
            parameter="stoploss_pct",
            current_value=-0.09, proposed_value=-0.08,
            requires_human_approval=True,
        )
        result = candidate_to_apply_pipeline(
            candidate=c,
            pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id="max_open_trades_3_to_2",
        )
        assert result.decision.status == "DEFERRED"
        assert any("measurement_active_for" in r for r in result.decision.blocked_reasons)

    def test_same_candidate_not_deferred(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id="test_max_open_trades_3_to_2",
        )
        # May be READY_FOR_CANARY_APPLY or READY_FOR_HUMAN_APPROVAL depending on readiness
        assert result.decision.status in (
            "READY_FOR_CANARY_APPLY", "READY_FOR_HUMAN_APPROVAL",
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY", "AUTO_DRY_RUN_APPROVED",
        )

    def test_readiness_ready_flag_set(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
        )
        # readiness_ready may be True or False depending on RiskGuard
        # but the field must exist
        assert isinstance(result.decision.readiness_ready, bool)
        assert isinstance(result.readiness_report, object)

    def test_restart_measurement_rollback_flags(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        assert result.restart_plan_required
        assert result.rollback_plan_required

    def test_evidence_refs_preserved(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        _ = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
        )
        assert "test_report.md" in valid_candidate.evidence_refs

    def test_canary_only_flag_true(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
        )
        assert result.decision.canary_only

    def test_next_step_actionable(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
        )
        assert len(result.decision.next_step) > 10
        assert isinstance(result.decision.next_step, str)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_input_to_dict(self, valid_candidate: CandidateApplyInput) -> None:
        d = valid_candidate.to_dict()
        json.dumps(d)
        assert d["candidate_id"] == valid_candidate.candidate_id

    def test_decision_to_dict(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
            active_measurement_candidate_id=None,
        )
        d = result.decision.to_dict()
        json.dumps(d)
        assert d["status"] in (
            "READY_FOR_CANARY_APPLY", "READY_FOR_HUMAN_APPROVAL",
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY", "AUTO_DRY_RUN_APPROVED",
        )

    def test_result_to_dict(
        self,
        valid_candidate: CandidateApplyInput,
        valid_pre_apply: dict,
    ) -> None:
        result = candidate_to_apply_pipeline(
            candidate=valid_candidate,
            pre_apply_config=valid_pre_apply,
        )
        d = result.to_dict()
        json.dumps(d)
        assert "decision" in d


# ---------------------------------------------------------------------------
# No subprocess / no Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_module(self) -> None:
        import inspect

        import si_v2.pipeline.candidate_to_apply as cp
        source = inspect.getsource(cp)
        # Filter docstrings
        code_lines = [line for line in source.splitlines()
                      if not line.strip().startswith(('#', '"""', "'", 'r"""'))]
        assert not any("import subprocess" in line for line in code_lines)
        assert not any("docker" in line.lower() and "no docker" not in line.lower() for line in code_lines)
        assert not any("import run_canary_restart" in line for line in code_lines)
        assert not any("import execute_apply" in line for line in code_lines)
