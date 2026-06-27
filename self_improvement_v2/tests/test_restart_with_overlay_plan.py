r"""Tests for the canary restart-with-overlay planner.

All tests use ``tmp_path`` for overlay files. No Docker, no subprocess,
no runtime mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_BOT_ID,
    CANARY_CONTAINER_NAME,
    CANARY_SERVICE_NAME,
    RESTART_FORBIDDEN_KEYS,
    RestartExecutionResult,
    _build_proposed_command,
    _build_rollback_command,
    _check_canary_only,
    _check_current_command,
    _check_dry_run,
    _check_overlay_content,
    _check_overlay_path,
    execute_canary_restart_with_overlay,
    plan_canary_restart_with_overlay,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def canary_user_data(tmp_path: Path) -> Path:
    """Create a temporary canary user_data directory."""
    d = tmp_path / "freqforge-canary" / "user_data"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def valid_overlay_path(canary_user_data: Path) -> Path:
    """Create a valid overlay file with max_open_trades=2."""
    path = canary_user_data / "overlay_max_open_trades_3_to_2.json"
    path.write_text(json.dumps({"max_open_trades": 2, "_meta": {"source": "test"}}))
    return path


@pytest.fixture
def pre_apply_config() -> dict[str, object]:
    return {"max_open_trades": 3, "dry_run": True}


@pytest.fixture
def current_command() -> tuple[str, ...]:
    return (
        "freqtrade",
        "trade",
        "--config",
        "/freqtrade/user_data/config.json",
        "--strategy",
        "FreqForge_Override",
    )


# ---------------------------------------------------------------------------
# _check_canary_only
# ---------------------------------------------------------------------------


class TestCheckCanaryOnly:
    def test_canary_accepted(self) -> None:
        ok, reason = _check_canary_only(CANARY_BOT_ID)
        assert ok
        assert reason == ""

    def test_wrong_bot_blocked(self) -> None:
        ok, reason = _check_canary_only("freqtrade-freqforge")
        assert not ok
        assert "not_canary" in reason

    def test_empty_bot_blocked(self) -> None:
        ok, reason = _check_canary_only("")
        assert not ok
        assert "not_canary" in reason


# ---------------------------------------------------------------------------
# _check_overlay_path
# ---------------------------------------------------------------------------


class TestCheckOverlayPath:
    def test_valid_path(self, valid_overlay_path: Path, canary_user_data: Path) -> None:
        ok, reason = _check_overlay_path(valid_overlay_path, canary_user_data)
        assert ok
        assert reason == ""

    def test_missing_file(self, canary_user_data: Path) -> None:
        missing = canary_user_data / "overlay_nonexistent.json"
        ok, reason = _check_overlay_path(missing, canary_user_data)
        assert not ok
        assert "overlay_file_missing" in reason

    def test_outside_canary(self, tmp_path: Path, canary_user_data: Path) -> None:
        outside = tmp_path / "other" / "overlay.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}")
        ok, reason = _check_overlay_path(outside, canary_user_data)
        assert not ok
        assert "overlay_outside_canary" in reason

    def test_other_bot_user_data_blocked(
        self, tmp_path: Path, canary_user_data: Path
    ) -> None:
        other = tmp_path / "freqforge" / "user_data" / "overlay.json"
        other.parent.mkdir(parents=True)
        other.write_text("{}")
        ok, reason = _check_overlay_path(other, canary_user_data)
        assert not ok
        assert "overlay_outside_canary" in reason


# ---------------------------------------------------------------------------
# _check_overlay_content
# ---------------------------------------------------------------------------


class TestCheckOverlayContent:
    def test_valid_content(self, valid_overlay_path: Path) -> None:
        data, blocked = _check_overlay_content(valid_overlay_path)
        assert data is not None
        assert data.get("max_open_trades") == 2
        assert len(blocked) == 0

    def test_invalid_json(self, canary_user_data: Path) -> None:
        bad = canary_user_data / "bad.json"
        bad.write_text("not json")
        data, blocked = _check_overlay_content(bad)
        assert data is None
        assert any("overlay_parse_error" in b for b in blocked)

    def test_dry_run_forbidden(self, canary_user_data: Path) -> None:
        path = canary_user_data / "overlay_dry_run.json"
        path.write_text(json.dumps({"dry_run": False}))
        data, blocked = _check_overlay_content(path)
        assert data is not None
        assert any("forbidden_key_in_overlay" in b and "dry_run" in b for b in blocked)

    def test_strategy_forbidden(self, canary_user_data: Path) -> None:
        path = canary_user_data / "overlay_strategy.json"
        path.write_text(json.dumps({"strategy": "OtherStrategy"}))
        _data, blocked = _check_overlay_content(path)
        assert any("forbidden_key_in_overlay" in b and "strategy" in b for b in blocked)

    def test_pair_whitelist_forbidden(self, canary_user_data: Path) -> None:
        path = canary_user_data / "overlay_pairs.json"
        path.write_text(json.dumps({"pair_whitelist": ["BTC/USDT"]}))
        _data, blocked = _check_overlay_content(path)
        assert any("forbidden_key_in_overlay" in b and "pair_whitelist" in b for b in blocked)

    def test_exchange_forbidden(self, canary_user_data: Path) -> None:
        path = canary_user_data / "overlay_exchange.json"
        path.write_text(json.dumps({"exchange": {"name": "binance"}}))
        _data, blocked = _check_overlay_content(path)
        assert any("forbidden_key_in_overlay" in b and "exchange" in b for b in blocked)

    def test_api_server_forbidden(self, canary_user_data: Path) -> None:
        path = canary_user_data / "overlay_api.json"
        path.write_text(json.dumps({"api_server": {"enabled": False}}))
        _data, blocked = _check_overlay_content(path)
        assert any("forbidden_key_in_overlay" in b and "api_server" in b for b in blocked)

    def test_all_forbidden_keys_covered(self) -> None:
        """Ensure every key in RESTART_FORBIDDEN_KEYS is tested."""
        expected = {
            "dry_run", "strategy", "pair_whitelist", "exchange",
            "api_server", "db_url", "user_data_dir", "telegram",
            "external_message_consumer",
        }
        assert expected == RESTART_FORBIDDEN_KEYS


# ---------------------------------------------------------------------------
# _check_dry_run
# ---------------------------------------------------------------------------


class TestCheckDryRun:
    def test_dry_run_true(self, pre_apply_config: dict) -> None:
        ok, reason = _check_dry_run(pre_apply_config)
        assert ok
        assert reason == ""

    def test_dry_run_false(self) -> None:
        ok, reason = _check_dry_run({"dry_run": False})
        assert not ok
        assert "dry_run_not_true" in reason

    def test_dry_run_missing(self) -> None:
        ok, reason = _check_dry_run({})
        assert not ok
        assert "dry_run_not_found" in reason

    def test_dry_run_none(self) -> None:
        ok, reason = _check_dry_run({"dry_run": None})
        assert not ok
        assert "dry_run_not_found" in reason


# ---------------------------------------------------------------------------
# _check_current_command
# ---------------------------------------------------------------------------


class TestCheckCurrentCommand:
    def test_has_config(self, current_command: tuple) -> None:
        ok, reason = _check_current_command(current_command)
        assert ok
        assert reason == ""

    def test_no_config(self) -> None:
        ok, reason = _check_current_command(("freqtrade", "trade"))
        assert not ok
        assert "current_command_no_config" in reason

    def test_empty_command(self) -> None:
        ok, reason = _check_current_command(())
        assert not ok
        assert "current_command_no_config" in reason


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------


class TestBuildProposedCommand:
    def test_appends_overlay_after_last_config(
        self, current_command: tuple
    ) -> None:
        proposed = _build_proposed_command(
            current_command,
            "/freqtrade/user_data/overlay_max_open.json",
        )
        assert "--config" in proposed
        assert "/freqtrade/user_data/overlay_max_open.json" in proposed
        # Overlay should come after the base config
        base_idx = proposed.index("/freqtrade/user_data/config.json")
        overlay_idx = proposed.index("/freqtrade/user_data/overlay_max_open.json")
        assert overlay_idx > base_idx

    def test_no_duplicate_overlay(self, current_command: tuple) -> None:
        """If overlay path already present, return unchanged."""
        already = (*current_command, "--config", "/freqtrade/user_data/overlay_existing.json")
        proposed = _build_proposed_command(
            already,
            "/freqtrade/user_data/overlay_existing.json",
        )
        # Count occurrences
        count = sum(
            1 for i, arg in enumerate(proposed)
            if arg == "--config" and i + 1 < len(proposed)
            and proposed[i + 1] == "/freqtrade/user_data/overlay_existing.json"
        )
        assert count == 1

    def test_no_config_in_command(self) -> None:
        cmd = ("freqtrade", "trade")
        proposed = _build_proposed_command(
            cmd, "/freqtrade/user_data/overlay.json"
        )
        assert proposed == ("freqtrade", "trade", "--config", "/freqtrade/user_data/overlay.json")


class TestBuildRollbackCommand:
    def test_removes_overlay(self, current_command: tuple) -> None:
        with_overlay = (*current_command, "--config", "/freqtrade/user_data/overlay_max_open.json")
        rollback = _build_rollback_command(with_overlay)
        assert rollback == current_command
        assert "overlay_" not in " ".join(rollback)

    def test_preserves_base_config(self, current_command: tuple) -> None:
        rollback = _build_rollback_command(current_command)
        assert rollback == current_command

    def test_removes_multiple_overlays(self, current_command: tuple) -> None:
        extras = ("--config", "/freqtrade/user_data/overlay_1.json",
                  "--config", "/freqtrade/user_data/overlay_2.json")
        with_overlays = (*current_command, *extras)
        rollback = _build_rollback_command(with_overlays)
        assert rollback == current_command
        assert "overlay_" not in " ".join(rollback)


# ---------------------------------------------------------------------------
# Integration: plan_canary_restart_with_overlay
# ---------------------------------------------------------------------------


class TestPlanCanaryRestart:
    def test_valid_plan(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        assert result.blocked_reasons == ()
        assert result.plan.bot_id == CANARY_BOT_ID
        assert result.plan.container_name == CANARY_CONTAINER_NAME
        assert result.plan.service_name == CANARY_SERVICE_NAME
        assert result.plan.expected_parameter == "max_open_trades"
        assert result.plan.expected_value == 2
        assert result.plan.overlay_sha256 != ""
        assert result.plan.proposed_command != result.plan.current_command
        assert result.plan.rollback_command == result.plan.current_command
        assert all(result.plan.safety_checks.values())

    def test_wrong_bot_blocked(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id="freqtrade-freqforge",
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert result.plan is None
        assert any("not_canary" in r for r in result.blocked_reasons)

    def test_missing_overlay_blocked(
        self,
        canary_user_data: Path,
        pre_apply_config: dict,
        current_command: tuple,
    ) -> None:
        missing = canary_user_data / "overlay_missing.json"
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=missing,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("overlay_file_missing" in r for r in result.blocked_reasons)

    def test_overlay_outside_canary_blocked(
        self,
        tmp_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        outside = tmp_path / "other" / "overlay.json"
        outside.parent.mkdir(parents=True)
        outside.write_text(json.dumps({"max_open_trades": 2}))
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=outside,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("overlay_outside_canary" in r for r in result.blocked_reasons)

    def test_dry_run_false_blocked(
        self,
        valid_overlay_path: Path,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config={"dry_run": False},
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("dry_run_not_true" in r for r in result.blocked_reasons)

    def test_dry_run_missing_blocked(
        self,
        valid_overlay_path: Path,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config={},
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("dry_run_not_found" in r for r in result.blocked_reasons)

    def test_no_config_in_command_blocked(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=("freqtrade", "trade"),
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("current_command_no_config" in r for r in result.blocked_reasons)

    def test_forbidden_key_in_overlay_blocked(
        self,
        canary_user_data: Path,
        pre_apply_config: dict,
        current_command: tuple,
    ) -> None:
        path = canary_user_data / "overlay_with_dry_run.json"
        path.write_text(json.dumps({"max_open_trades": 2, "dry_run": False}))
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert not result.ready
        assert any("forbidden_key_in_overlay" in r for r in result.blocked_reasons)

    def test_plan_includes_overlay_sha256(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        assert len(result.plan.overlay_sha256) == 64  # SHA-256 hex

    def test_plan_to_dict_serializable(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        d = result.plan.to_dict()
        # Verify JSON serialisable
        json.dumps(d)
        assert d["plan_id"] == result.plan.plan_id
        assert d["bot_id"] == CANARY_BOT_ID
        assert d["expected_parameter"] == "max_open_trades"
        assert d["expected_value"] == 2
        from typing import cast
        proposed = cast("list[str]", d["proposed_command"])
        current = cast("list[str]", d["current_command"])
        rollback = cast("list[str]", d["rollback_command"])
        assert len(proposed) > len(current)
        assert rollback == list(current_command)

    def test_execute_hard_blocked(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        exec_result = execute_canary_restart_with_overlay(result.plan)
        assert exec_result.status == "NOT_IMPLEMENTED"
        assert "not implemented" in exec_result.reason.lower()
        assert exec_result.plan_id == result.plan.plan_id

    def test_no_subprocess_in_planner(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        """Verify planner is pure Python — no subprocess, no Docker."""
        import subprocess

        original_run = subprocess.run
        calls: list = []

        def _capture(*args, **kwargs):
            calls.append(args)
            return original_run(*args, **kwargs)

        subprocess.run = _capture  # type: ignore[assignment]
        try:
            result = plan_canary_restart_with_overlay(
                bot_id=CANARY_BOT_ID,
                overlay_path=valid_overlay_path,
                current_command=current_command,
                expected_parameter="max_open_trades",
                expected_value=2,
                pre_apply_config=pre_apply_config,
                canary_user_data=canary_user_data,
            )
            assert result.ready
            assert len(calls) == 0, f"subprocess.run was called {len(calls)} times"
        finally:
            subprocess.run = original_run  # type: ignore[assignment]

    def test_non_canary_overlay_anomaly_rejected(
        self,
        tmp_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
    ) -> None:
        """Overlay in non-canary user_data (e.g. freqforge/) is rejected."""
        non_canary = tmp_path / "freqforge" / "user_data" / "overlay_65502d13.json"
        non_canary.parent.mkdir(parents=True)
        non_canary.write_text(json.dumps({"max_open_trades": 3}))
        canary_ud = tmp_path / "freqforge-canary" / "user_data"
        canary_ud.mkdir(parents=True)
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=non_canary,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=3,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_ud,
        )
        assert not result.ready
        assert any("overlay_outside_canary" in r for r in result.blocked_reasons)

    def test_expected_parameter_and_value_in_plan(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        assert result.plan.expected_parameter == "max_open_trades"
        assert result.plan.expected_value == 2

    def test_rollback_command_equals_base_command(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        assert result.plan.rollback_command == current_command
        assert "overlay_" not in " ".join(result.plan.rollback_command)

    def test_proposed_command_has_overlay(
        self,
        valid_overlay_path: Path,
        pre_apply_config: dict,
        current_command: tuple,
        canary_user_data: Path,
    ) -> None:
        result = plan_canary_restart_with_overlay(
            bot_id=CANARY_BOT_ID,
            overlay_path=valid_overlay_path,
            current_command=current_command,
            expected_parameter="max_open_trades",
            expected_value=2,
            pre_apply_config=pre_apply_config,
            canary_user_data=canary_user_data,
        )
        assert result.ready
        assert result.plan is not None
        proposed = " ".join(result.plan.proposed_command)
        assert "--config" in proposed
        assert "overlay_" in proposed
        # Overlay should be after base config
        base_idx = proposed.index("config.json")
        overlay_idx = proposed.index("overlay_")
        assert overlay_idx > base_idx


# ---------------------------------------------------------------------------
# RestartExecutionResult
# ---------------------------------------------------------------------------


class TestRestartExecutionResult:
    def test_to_dict(self) -> None:
        r = RestartExecutionResult(
            status="NOT_IMPLEMENTED",
            reason="test reason",
            plan_id="test_plan",
        )
        d = r.to_dict()
        assert d["status"] == "NOT_IMPLEMENTED"
        assert d["reason"] == "test reason"
        assert d["plan_id"] == "test_plan"
        json.dumps(d)  # verify serialisable
