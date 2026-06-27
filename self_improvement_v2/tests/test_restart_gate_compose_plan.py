r"""Tests for the restart gate checker and compose plan preview (Phase 3B-B).

All tests are pure Python — no Docker, no subprocess, no filesystem mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.apply_actuator.restart_gate import (
    CANARY_BOT_ID,
    CANARY_COMPOSE_SERVICE,
    CANARY_CONTAINER_NAME,
    CanaryRecreatePlan,
    RestartGateResult,
    _g7_proposed_command_contains_base_config,
    _g8_proposed_command_contains_overlay_config,
    _g9_rollback_command_available,
    build_canary_recreate_plan,
    check_restart_gate,
    render_compose_override_preview,
)
from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_SERVICE_NAME,
    RestartPlan,
    plan_canary_restart_with_overlay,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_restart_plan(tmp_path: Path) -> RestartPlan:
    """Build a valid RestartPlan with a real overlay file."""
    canary_ud = tmp_path / "freqforge-canary" / "user_data"
    canary_ud.mkdir(parents=True)
    overlay = canary_ud / "overlay_max_open_trades_3_to_2.json"
    overlay.write_text(json.dumps({"max_open_trades": 2}))
    result = plan_canary_restart_with_overlay(
        bot_id=CANARY_BOT_ID,
        overlay_path=overlay,
        current_command=(
            "freqtrade", "trade",
            "--config", "/freqtrade/user_data/config.json",
            "--strategy", "FreqForge_Override",
        ),
        expected_parameter="max_open_trades",
        expected_value=2,
        pre_apply_config={"max_open_trades": 3, "dry_run": True},
        canary_user_data=canary_ud,
    )
    assert result.ready
    assert result.plan is not None
    return result.plan


@pytest.fixture
def valid_overlay_payload() -> dict[str, object]:
    return {"max_open_trades": 2}


@pytest.fixture
def valid_pre_apply_config() -> dict[str, object]:
    return {"max_open_trades": 3, "dry_run": True}


# ---------------------------------------------------------------------------
# check_restart_gate
# ---------------------------------------------------------------------------


class TestCheckRestartGate:
    def test_valid_plan_passes_gate(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        assert result.ready
        assert result.blocked_reasons == ()
        assert all(result.gate_results.values())

    def test_wrong_bot_fails_at_planner_level(
        self,
        tmp_path: Path,
    ) -> None:
        """Wrong bot is caught by planner, so the gate doesn't even run."""
        canary_ud = tmp_path / "freqforge-canary" / "user_data"
        canary_ud.mkdir(parents=True)
        overlay = canary_ud / "overlay_test.json"
        overlay.write_text(json.dumps({"max_open_trades": 2}))
        result = plan_canary_restart_with_overlay(
            bot_id="freqtrade-freqforge",
            overlay_path=overlay,
            current_command=("freqtrade", "trade", "--config",
                             "/freqtrade/user_data/config.json"),
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config={"dry_run": True},
            canary_user_data=canary_ud,
        )
        assert not result.ready
        assert result.plan is None

    def test_dry_run_false_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config={"dry_run": False},
        )
        assert not result.ready
        assert any("G5" in r for r in result.blocked_reasons)

    def test_missing_dry_run_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config={},
        )
        assert not result.ready
        assert any("G5" in r for r in result.blocked_reasons)

    def test_forbidden_dry_run_key_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload={"dry_run": False},
            pre_apply_config=valid_pre_apply_config,
        )
        assert not result.ready
        assert any("G6" in r for r in result.blocked_reasons)

    def test_forbidden_strategy_key_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload={"strategy": "OtherStrategy"},
            pre_apply_config=valid_pre_apply_config,
        )
        assert not result.ready
        assert any("G6" in r for r in result.blocked_reasons)

    def test_forbidden_pair_whitelist_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload={"pair_whitelist": ["BTC/USDT"]},
            pre_apply_config=valid_pre_apply_config,
        )
        assert not result.ready
        assert any("G6" in r for r in result.blocked_reasons)

    def test_proposed_command_without_base_config_fails(self) -> None:
        """G7: proposed command must contain base --config."""
        class _Dummy:
            proposed_command = ("freqtrade", "trade", "--strategy", "Test")
        ok, reason = _g7_proposed_command_contains_base_config(_Dummy())  # type: ignore[arg-type]
        assert not ok
        assert "G7" in reason

    def test_proposed_command_without_overlay_fails(self) -> None:
        """G8: proposed command must contain overlay --config."""
        class _Dummy:
            proposed_command = ("freqtrade", "trade", "--config",
                                "/freqtrade/user_data/config.json")
        ok, reason = _g8_proposed_command_contains_overlay_config(_Dummy())  # type: ignore[arg-type]
        assert not ok
        assert "G8" in reason

    def test_missing_rollback_command_fails(self) -> None:
        """G9: rollback command must not be empty."""
        class _Dummy:
            rollback_command = ()
        ok, reason = _g9_rollback_command_available(_Dummy())  # type: ignore[arg-type]
        assert not ok
        assert "G9" in reason

    def test_execution_enabled_true_fails(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
            execution_enabled=True,
        )
        assert not result.ready
        assert any("G10" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# build_canary_recreate_plan
# ---------------------------------------------------------------------------


class TestBuildCanaryRecreatePlan:
    def test_preserves_proposed_command(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        gate = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        recreate = build_canary_recreate_plan(valid_restart_plan, gate)
        assert recreate.proposed_command == valid_restart_plan.proposed_command
        assert "overlay_" in " ".join(recreate.proposed_command)

    def test_preserves_rollback_command(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        gate = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        recreate = build_canary_recreate_plan(valid_restart_plan, gate)
        assert recreate.rollback_command == valid_restart_plan.rollback_command
        assert "overlay_" not in " ".join(recreate.rollback_command)

    def test_recreate_plan_has_canary_ids(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        gate = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        recreate = build_canary_recreate_plan(valid_restart_plan, gate)
        assert recreate.bot_id == CANARY_BOT_ID
        assert recreate.container_name == CANARY_CONTAINER_NAME
        assert recreate.service_name == CANARY_SERVICE_NAME
        assert recreate.compose_service == CANARY_COMPOSE_SERVICE


# ---------------------------------------------------------------------------
# render_compose_override_preview
# ---------------------------------------------------------------------------


class TestRenderComposeOverridePreview:
    @pytest.fixture
    def recreate_plan(self, valid_restart_plan: RestartPlan) -> CanaryRecreatePlan:
        gate = RestartGateResult(
            ready=True,
            gate_results={"dry_run_true": True},
            blocked_reasons=(),
        )
        return build_canary_recreate_plan(valid_restart_plan, gate)

    def test_contains_only_canary_service(self, recreate_plan: CanaryRecreatePlan) -> None:
        preview = render_compose_override_preview(recreate_plan)
        assert "services:" in preview
        assert "freqtrade-freqforge-canary:" in preview
        assert "freqtrade-freqforge:" not in preview
        assert "freqai-rebel:" not in preview

    def test_contains_overlay_config_path(self, recreate_plan: CanaryRecreatePlan) -> None:
        preview = render_compose_override_preview(recreate_plan)
        assert "overlay_" in preview
        assert "--config" in preview
        assert "/freqtrade/user_data/overlay_" in preview

    def test_contains_no_other_services(self, recreate_plan: CanaryRecreatePlan) -> None:
        preview = render_compose_override_preview(recreate_plan)
        for svc in ["freqai", "hybrid", "webserver", "hermes", "caddy"]:
            assert f"  {svc}:" not in preview, f"Unexpected service {svc}"

    def test_contains_no_secrets(self, recreate_plan: CanaryRecreatePlan) -> None:
        preview = render_compose_override_preview(recreate_plan)
        assert "password" not in preview.lower()
        assert "secret" not in preview.lower()
        assert "jwt" not in preview.lower()

    def test_contains_rollback_instructions(self, recreate_plan: CanaryRecreatePlan) -> None:
        preview = render_compose_override_preview(recreate_plan)
        assert "Rollback" in preview
        assert "docker compose" in preview


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_gate_result_to_dict(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        result = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        d = result.to_dict()
        json.dumps(d)  # verify JSON serialisable
        assert d["ready"] is True
        assert d["blocked_reasons"] == []

    def test_recreate_plan_to_dict(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        gate = check_restart_gate(
            valid_restart_plan,
            overlay_payload=valid_overlay_payload,
            pre_apply_config=valid_pre_apply_config,
        )
        recreate = build_canary_recreate_plan(valid_restart_plan, gate)
        d = recreate.to_dict()
        json.dumps(d)
        assert d["plan_id"] == valid_restart_plan.plan_id
        assert d["bot_id"] == CANARY_BOT_ID
        assert d["compose_service"] == CANARY_COMPOSE_SERVICE


# ---------------------------------------------------------------------------
# No subprocess / no Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_gate_checker(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        import subprocess
        original_run = subprocess.run
        calls: list = []

        def _capture(*args: object, **kwargs: object) -> object:
            calls.append(args)
            return original_run(*args, **kwargs)

        subprocess.run = _capture  # type: ignore[assignment]
        try:
            result = check_restart_gate(
                valid_restart_plan,
                overlay_payload=valid_overlay_payload,
                pre_apply_config=valid_pre_apply_config,
            )
            assert result.ready
            assert len(calls) == 0, f"subprocess.run called {len(calls)} times"
        finally:
            subprocess.run = original_run  # type: ignore[assignment]

    def test_no_subprocess_in_plan_builder(
        self,
        valid_restart_plan: RestartPlan,
        valid_overlay_payload: dict,
        valid_pre_apply_config: dict,
    ) -> None:
        import subprocess
        original_run = subprocess.run
        calls: list = []

        def _capture(*args: object, **kwargs: object) -> object:
            calls.append(args)
            return original_run(*args, **kwargs)

        subprocess.run = _capture  # type: ignore[assignment]
        try:
            gate = check_restart_gate(
                valid_restart_plan,
                overlay_payload=valid_overlay_payload,
                pre_apply_config=valid_pre_apply_config,
            )
            _ = build_canary_recreate_plan(valid_restart_plan, gate)
            assert len(calls) == 0, f"subprocess.run called {len(calls)} times"
        finally:
            subprocess.run = original_run  # type: ignore[assignment]
