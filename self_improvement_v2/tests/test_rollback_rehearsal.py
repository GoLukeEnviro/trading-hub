r"""Tests for the rollback rehearsal gate (Phase 5A).

Pure Python — no subprocess, no Docker, no runtime mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.apply_actuator.rollback_rehearsal import (
    CANARY_BOT_ID,
    CANARY_CONTAINER_NAME,
    CANARY_SERVICE_NAME,
    RollbackExecutionResult,
    RollbackPlan,
    RollbackPreview,
    build_rollback_preview,
    check_rollback_gate,
    execute_canary_rollback,
    plan_canary_rollback_from_overlay,
    render_rollback_compose_preview,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def overlay_command() -> tuple[str, ...]:
    return (
        "freqtrade", "trade",
        "--config", "/freqtrade/user_data/config.json",
        "--config", "/freqtrade/user_data/overlay_max_open_trades_.json",
        "--strategy", "FreqForge_Override",
    )


@pytest.fixture
def base_command() -> tuple[str, ...]:
    return (
        "freqtrade", "trade",
        "--config", "/freqtrade/user_data/config.json",
        "--strategy", "FreqForge_Override",
    )


@pytest.fixture
def pre_apply_config() -> dict[str, object]:
    return {"max_open_trades": 2, "dry_run": True}


@pytest.fixture
def overlay_path(tmp_path: Path) -> Path:
    p = tmp_path / "overlay_max_open_trades_.json"
    p.write_text(json.dumps({"max_open_trades": 2}))
    return p


# ---------------------------------------------------------------------------
# plan_canary_rollback_from_overlay
# ---------------------------------------------------------------------------


class TestPlanCanaryRollback:
    def test_valid_plan_created(
        self,
        overlay_command: tuple,
        base_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID,
            candidate_id="max_open_trades_3_to_2",
            current_command=overlay_command,
            base_config_container_path="/freqtrade/user_data/config.json",
            current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2,
            expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="T3 measurement RED: max_open_trades=2 performance degraded",
        )
        assert plan.bot_id == CANARY_BOT_ID
        assert plan.container_name == CANARY_CONTAINER_NAME
        assert plan.service_name == CANARY_SERVICE_NAME
        assert plan.candidate_id == "max_open_trades_3_to_2"
        assert "overlay_" not in " ".join(plan.rollback_command)
        assert plan.dry_run_required is True
        assert plan.rollback_reason != ""
        assert plan.blocked_reasons == ()

    def test_wrong_bot_blocked(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id="freqtrade-freqforge",
            candidate_id="x", current_command=overlay_command,
            base_config_container_path="", current_overlay_path=None,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        assert "not_canary" in str(plan.blocked_reasons)

    def test_dry_run_false_blocked(
        self,
        overlay_command: tuple,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=None,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config={"dry_run": False},
            rollback_reason="test",
        )
        assert any("dry_run_not_true" in r for r in plan.blocked_reasons)

    def test_missing_dry_run_blocked(
        self,
        overlay_command: tuple,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=None,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config={},
            rollback_reason="test",
        )
        assert any("dry_run_not_found" in r for r in plan.blocked_reasons)

    def test_missing_overlay_in_command_blocked(
        self,
        base_command: tuple,
        pre_apply_config: dict,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=base_command,
            base_config_container_path="", current_overlay_path=None,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        assert any("current_command_no_overlay" in r for r in plan.blocked_reasons)

    def test_rollback_removes_overlay(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        assert "overlay_" not in " ".join(plan.rollback_command)

    def test_rollback_keeps_base_config(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        assert "--config" in plan.rollback_command
        assert "/freqtrade/user_data/config.json" in " ".join(plan.rollback_command)

    def test_rollback_keeps_strategy(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        assert "FreqForge_Override" in " ".join(plan.rollback_command)

    def test_missing_reason_blocked(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=None,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="",
        )
        assert any("rollback_reason_missing" in r for r in plan.blocked_reasons)


# ---------------------------------------------------------------------------
# check_rollback_gate
# ---------------------------------------------------------------------------


class TestCheckRollbackGate:
    def test_valid_plan_passes_gate(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="measurement ended",
        )
        result = check_rollback_gate(
            plan,
            pre_apply_config=pre_apply_config,
            current_runtime_value=2,
        )
        assert result.ready
        assert all(result.gate_results.values())

    def test_current_runtime_mismatch_blocks(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        result = check_rollback_gate(
            plan,
            pre_apply_config=pre_apply_config,
            current_runtime_value=99,  # mismatch
        )
        assert not result.ready
        assert any("G7" in r for r in result.blocked_reasons)

    def test_expected_after_baseline_mismatch_blocks(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=99,  # not 3
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        result = check_rollback_gate(
            plan,
            pre_apply_config=pre_apply_config,
            current_runtime_value=2,
        )
        assert not result.ready
        assert any("G8" in r for r in result.blocked_reasons)

    def test_execution_enabled_blocks(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        result = check_rollback_gate(
            plan,
            pre_apply_config=pre_apply_config,
            current_runtime_value=2,
            execution_enabled=True,
        )
        assert not result.ready
        assert any("G10" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# build_rollback_preview
# ---------------------------------------------------------------------------


class TestBuildRollbackPreview:
    def test_preview_preserves_current_command(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        preview = build_rollback_preview(plan, gate)
        assert preview.current_command == plan.current_command

    def test_preview_contains_rollback_command(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        preview = build_rollback_preview(plan, gate)
        assert preview.rollback_command == plan.rollback_command
        assert "overlay_" not in " ".join(preview.rollback_command)


# ---------------------------------------------------------------------------
# render_rollback_compose_preview
# ---------------------------------------------------------------------------


class TestRenderRollbackComposePreview:
    def test_contains_only_canary_service(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        preview = build_rollback_preview(plan, gate)
        yaml = render_rollback_compose_preview(preview)
        assert "services:" in yaml
        assert CANARY_SERVICE_NAME in yaml
        assert "freqtrade-freqforge:" not in yaml
        assert "freqai-rebel:" not in yaml

    def test_does_not_contain_overlay_in_command(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        preview = build_rollback_preview(plan, gate)
        yaml = render_rollback_compose_preview(preview)
        # Extract command section (after 'command:')
        cmd_section = yaml.split("command:", 1)[1] if "command:" in yaml else ""
        assert "overlay_" not in cmd_section

    def test_contains_base_config(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        preview = build_rollback_preview(plan, gate)
        yaml = render_rollback_compose_preview(preview)
        assert "config.json" in yaml

    def test_contains_no_secrets_in_preview(
        self,
    ) -> None:
        """Build a rollback preview without tmp_path to avoid name collision."""
        plan = RollbackPlan(
            plan_id="test", bot_id=CANARY_BOT_ID,
            container_name="c", service_name=CANARY_SERVICE_NAME,
            candidate_id="x", current_overlay_path=None,
            current_overlay_sha256=None,
            base_config_container_path="/cfg",
            current_command=("--config", "/cfg/base.json", "--config", "/cfg/overlay.json"),
            rollback_command=("--config", "/cfg/base.json"),
            expected_before_parameter="", expected_before_value=None,
            expected_after_parameter="", expected_after_value=None,
            dry_run_required=True, rollback_reason="test",
            safety_checks={}, blocked_reasons=(), created_at_utc="",
        )
        preview = RollbackPreview(
            plan_id=plan.plan_id, bot_id=plan.bot_id,
            service_name=plan.service_name,
            current_command=plan.current_command,
            rollback_command=plan.rollback_command,
            current_overlay_path=plan.current_overlay_path,
            dry_run_confirmed=True,
            rollback_gate_ready=True,
            blocked_reasons=(),
        )
        yaml = render_rollback_compose_preview(preview)
        assert "password" not in yaml.lower()
        assert "secret" not in yaml.lower()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_plan_to_dict(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        d = plan.to_dict()
        json.dumps(d)
        assert d["bot_id"] == CANARY_BOT_ID

    def test_gate_result_to_dict(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        gate = check_rollback_gate(
            plan, pre_apply_config=pre_apply_config, current_runtime_value=2,
        )
        d = gate.to_dict()
        json.dumps(d)
        assert "ready" in d

    def test_execution_result_to_dict(self) -> None:
        r = RollbackExecutionResult(
            status="NOT_IMPLEMENTED",
            reason="phase 5a",
            plan_id="test",
        )
        d = r.to_dict()
        json.dumps(d)
        assert d["status"] == "NOT_IMPLEMENTED"


# ---------------------------------------------------------------------------
# Execute stub
# ---------------------------------------------------------------------------


class TestExecuteStub:
    def test_execute_is_hard_blocked(
        self,
        overlay_command: tuple,
        pre_apply_config: dict,
        overlay_path: Path,
    ) -> None:
        plan = plan_canary_rollback_from_overlay(
            bot_id=CANARY_BOT_ID, candidate_id="x",
            current_command=overlay_command,
            base_config_container_path="", current_overlay_path=overlay_path,
            expected_before_parameter="max_open_trades",
            expected_before_value=2, expected_after_parameter="max_open_trades",
            expected_after_value=3,
            pre_apply_config=pre_apply_config,
            rollback_reason="test",
        )
        result = execute_canary_rollback(plan, token="ANY", execute=True)
        assert result.status == "NOT_IMPLEMENTED"


# ---------------------------------------------------------------------------
# No subprocess / no Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_module(self) -> None:
        import inspect

        import si_v2.apply_actuator.rollback_rehearsal as rb
        source = inspect.getsource(rb)
        # Filter out docstrings and comments
        code_lines = [line for line in source.splitlines()
                      if not line.strip().startswith(('#', '"""', "'", 'r"""'))]
        assert not any("import subprocess" in line for line in code_lines)
        assert not any("run_canary_restart" in line for line in code_lines)
        assert not any("execute_apply" in line for line in code_lines)
