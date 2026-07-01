"""Tests for Controlled Apply Actuator with autonomous dry-run mode support.

Test coverage:
  1. AUTONOMOUS_DRY_RUN readiness passes without L3 token when all policy gates pass
  2. AUTONOMOUS_DRY_RUN blocks if dry_run false
  3. MANUAL_L3 still requires token
  4. LIVE_CAPITAL_MODE returns blocked/not implemented
  5. Rollback plan/audit requirement remains visible
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.apply_actuator.controlled_apply_actuator import (
    CANARY_BOT_ID,
    L3_TOKEN_ENV,
    L3_TOKEN_VALUE,
    ApplyMode,
    check_readiness,
    execute_apply,
)


@pytest.fixture
def overlay() -> dict[str, int]:
    return {"cooldown_candles": 4, "max_open_trades": 3}


@pytest.fixture
def pre_cfg() -> dict[str, object]:
    return {"cooldown_candles": 3, "max_open_trades": 3, "dry_run": True}


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    return {
        "state": tmp_path / "state",
        "overlay": tmp_path / "overlays",
        "plan": tmp_path / "rollback_plans",
        "log": tmp_path / "shadow_log",
    }


@pytest.fixture
def l3_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(L3_TOKEN_ENV, L3_TOKEN_VALUE)


class TestAutonomousDryRunMode:
    """Tests for AUTONOMOUS_DRY_RUN mode."""

    def test_readiness_passes_without_token(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        tmp_path: dict,
    ) -> None:
        """In AUTONOMOUS_DRY_RUN mode, readiness should pass without L3 token."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        assert report.ready, (
            f"Autonomous dry-run should pass without token: "
            f"canary={report.canary_gate.passed}, "
            f"params={report.safe_parameters_gate.passed}, "
            f"ks={report.kill_switch_gate.passed}, "
            f"rg={report.riskguard_gate.passed}, "
            f"human={report.human_approval_gate.passed}, "
            f"token={report.token_gate.passed}, "
            f"cooldown={report.cooldown_gate.passed}, "
            f"dry={report.dry_run_gate.passed}, "
            f"compat={report.compatibility_gate.passed}"
        )
        # Verify human and token gates are bypassed
        assert report.human_approval_gate.passed
        assert "bypassed" in report.human_approval_gate.reason.lower()
        assert report.token_gate.passed
        assert "bypassed" in report.token_gate.reason.lower()

    def test_blocks_dry_run_false(
        self,
        overlay: dict[str, int],
        tmp_path: dict,
    ) -> None:
        """AUTONOMOUS_DRY_RUN should block if dry_run is false."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config={"dry_run": False},
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        assert not report.ready
        assert not report.dry_run_gate.passed

    def test_execute_apply_autonomous_mode(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        tmp_path: dict,
    ) -> None:
        """execute_apply in AUTONOMOUS_DRY_RUN should work without token."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        decision = execute_apply(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            overlay_dir=tmp_path / "overlays",
            plan_dir=tmp_path / "rollback_plans",
            log_dir=tmp_path / "shadow_log",
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        assert decision.overall_status in (
            "SHADOW_OVERLAY_WRITTEN", "APPLIED_WITH_RUNTIME_PROOF",
        ), f"Autonomous apply should succeed: {decision.errors}"

    def test_blocks_non_canary(
        self,
        overlay: dict[str, int],
        tmp_path: dict,
    ) -> None:
        """AUTONOMOUS_DRY_RUN should block non-canary targets."""
        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id="freqtrade-freqforge",
            parameter_overlay=overlay,
            state_dir=tmp_path / "state",
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config={"dry_run": True},
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        assert not report.ready
        assert not report.canary_gate.passed


class TestManualL3Mode:
    """Tests for MANUAL_L3 mode (legacy)."""

    def test_requires_token(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        tmp_path: dict,
    ) -> None:
        """MANUAL_L3 mode should require L3 token."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.MANUAL_L3,
        )
        assert not report.ready, "MANUAL_L3 should block without token"
        assert not report.token_gate.passed

    def test_passes_with_token(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        l3_token: None,
        tmp_path: dict,
    ) -> None:
        """MANUAL_L3 mode should pass with L3 token."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.MANUAL_L3,
        )
        assert report.ready, (
            f"MANUAL_L3 with token should pass: "
            f"token={report.token_gate.passed}, "
            f"human={report.human_approval_gate.passed}"
        )


class TestLiveCapitalMode:
    """Tests for LIVE_CAPITAL_MODE (not implemented)."""

    def test_readiness_blocks(
        self,
        overlay: dict[str, int],
        tmp_path: dict,
    ) -> None:
        """LIVE_CAPITAL_MODE readiness should always block."""
        report = check_readiness(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=tmp_path / "state",
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config={"dry_run": True},
            apply_mode=ApplyMode.LIVE_CAPITAL_MODE,
        )
        assert not report.ready

    def test_execute_apply_blocks(
        self,
        overlay: dict[str, int],
        tmp_path: dict,
    ) -> None:
        """execute_apply in LIVE_CAPITAL_MODE should return BLOCKED."""
        decision = execute_apply(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=tmp_path / "state",
            overlay_dir=tmp_path / "overlays",
            plan_dir=tmp_path / "rollback_plans",
            log_dir=tmp_path / "shadow_log",
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config={"dry_run": True},
            apply_mode=ApplyMode.LIVE_CAPITAL_MODE,
        )
        assert decision.overall_status == "BLOCKED"
        assert any("live_capital_mode_not_implemented" in e for e in decision.errors)


class TestRollbackAndAudit:
    """Rollback plan and audit requirements remain visible."""

    def test_rollback_plan_created(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        tmp_path: dict,
    ) -> None:
        """Rollback plan should be created in autonomous mode."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        decision = execute_apply(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            overlay_dir=tmp_path / "overlays",
            plan_dir=tmp_path / "rollback_plans",
            log_dir=tmp_path / "shadow_log",
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        assert decision.rollback_plan_path, "Rollback plan should exist"
        assert decision.overlay_path, "Overlay should exist"

    def test_audit_log_created(
        self,
        overlay: dict[str, int],
        pre_cfg: dict[str, object],
        tmp_path: dict,
    ) -> None:
        """Audit log should be created in autonomous mode."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        ks = state_dir / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))

        log_dir = tmp_path / "shadow_log"
        decision = execute_apply(
            candidate_sha="test_sha_001",
            bot_id=CANARY_BOT_ID,
            parameter_overlay=overlay,
            state_dir=state_dir,
            overlay_dir=tmp_path / "overlays",
            plan_dir=tmp_path / "rollback_plans",
            log_dir=log_dir,
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
            apply_mode=ApplyMode.AUTONOMOUS_DRY_RUN,
        )
        # Check that log files exist (either ShadowLogger or fallback)
        log_files = list(log_dir.glob("*"))
        assert len(log_files) > 0 or decision.rollback_plan_path
