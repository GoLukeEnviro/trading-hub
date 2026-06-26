"""Tests for Phase 1 Controlled Apply Actuator — Canary-First Human Gate (#363).

Test coverage:
  1. Basic gate functions
  2. Readiness check (all gates)
  3. Cooldown fail-closed (BLOCKER-5)
  4. Dry-run unconditional (HIGH-1)
  5. Kill-switch and RiskGuard (BLOCKER-2, BLOCKER-3)
  6. Value validation (BLOCKER-1)
  7. Shadow logger integration
  8. Blocked and success scenarios via execute_apply
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from si_v2.apply_actuator.controlled_apply_actuator import (
    CANARY_BOT_ID,
    COOLDOWN_DAYS,
    L3_TOKEN_ENV,
    L3_TOKEN_VALUE,
    ControlledApplyDecision,
    CooldownState,
    check_canary_bot,
    check_cooldown,
    check_dry_run,
    check_human_approval,
    check_kill_switch,
    check_readiness,
    check_riskguard,
    check_safe_parameters,
    check_token,
    create_rollback_plan,
    execute_apply,
    log_shadow_events,
    summarize_decision,
    write_overlay_file,
)

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def canary() -> str:
    return CANARY_BOT_ID


@pytest.fixture
def overlay() -> dict[str, int]:
    return {"cooldown_candles": 4, "max_open_trades": 3}


@pytest.fixture
def pre_cfg() -> dict[str, object]:
    return {"cooldown_candles": 3, "max_open_trades": 3, "dry_run": True}


@pytest.fixture
def tmp_dir(tmp_path: Path) -> dict[str, Path]:
    return {
        "state": tmp_path / "state",
        "overlay": tmp_path / "overlays",
        "plan": tmp_path / "rollback_plans",
        "log": tmp_path / "shadow_log",
    }


@pytest.fixture
def l3_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(L3_TOKEN_ENV, L3_TOKEN_VALUE)


# -- 1. Basic gate functions --------------------------------------------------


class TestCanaryBotGate:
    def test_accept_canary(self) -> None:
        assert check_canary_bot(CANARY_BOT_ID).passed

    def test_reject_other(self) -> None:
        assert not check_canary_bot("freqtrade-freqforge").passed


class TestSafeParameters:
    def test_accept_valid(self) -> None:
        assert check_safe_parameters({"cooldown_candles": 4}).passed

    def test_reject_bad_key(self) -> None:
        assert not check_safe_parameters({"exchange": "binance"}).passed

    def test_reject_empty(self) -> None:
        assert not check_safe_parameters({}).passed

    def test_reject_value_out_of_range(self) -> None:
        assert not check_safe_parameters({"cooldown_candles": 9999}).passed

    def test_reject_non_numeric(self) -> None:
        assert not check_safe_parameters({"cooldown_candles": "high"}).passed


class TestTokenGate:
    def test_accept_with_token(self, l3_token: None) -> None:
        assert check_token().passed

    def test_reject_without_token(self) -> None:
        assert not check_token().passed


class TestHumanApproval:
    def test_accept_true(self) -> None:
        assert check_human_approval(True).passed

    def test_reject_false(self) -> None:
        assert not check_human_approval(False).passed


class TestKillSwitch:
    def test_accept_normal(self, tmp_path: Path) -> None:
        ks = tmp_path / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))
        assert check_kill_switch(ks).passed

    def test_reject_halt_new(self, tmp_path: Path) -> None:
        ks = tmp_path / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "HALT_NEW"}))
        assert not check_kill_switch(ks).passed

    def test_reject_emergency(self, tmp_path: Path) -> None:
        ks = tmp_path / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "EMERGENCY"}))
        assert not check_kill_switch(ks).passed

    def test_fail_closed_corrupt(self, tmp_path: Path) -> None:
        ks = tmp_path / "kill_switch.json"
        ks.write_text("{bad json}")
        assert not check_kill_switch(ks).passed


class TestRiskGuard:
    def test_accept_pass(self) -> None:
        assert check_riskguard("PASS").passed

    def test_reject_fail(self) -> None:
        assert not check_riskguard("FAIL").passed

    def test_reject_none(self) -> None:
        assert not check_riskguard(None).passed


class TestDryRun:
    def test_accept_true(self, pre_cfg: dict[str, object]) -> None:
        assert check_dry_run(pre_cfg).passed

    def test_reject_false(self, pre_cfg: dict[str, object]) -> None:
        pre_cfg["dry_run"] = False
        assert not check_dry_run(pre_cfg).passed

    def test_block_on_none(self) -> None:
        """Unconditional: no config must block (HIGH-1)."""
        assert not check_dry_run(None).passed


# -- 2. Cooldown fail-closed (BLOCKER-5) --------------------------------------


class TestCooldownFailClosed:
    def test_fresh_no_file(self, tmp_dir: dict[str, Path]) -> None:
        state, result = check_cooldown(tmp_dir["state"])
        assert not state._corrupt
        assert result.passed

    def test_corrupt_file_blocks(self, tmp_dir: dict[str, Path]) -> None:
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        (tmp_dir["state"] / "cooldown_state.json").write_text("corrupt")
        state, result = check_cooldown(tmp_dir["state"])
        assert state._corrupt
        assert not result.passed

    def test_active_cooldown_blocks(self, tmp_dir: dict[str, Path]) -> None:
        s = CooldownState(
            last_apply_utc=datetime.now(UTC).isoformat(),
            candidate_sha="abc", bot_id=CANARY_BOT_ID,
        )
        s.save(tmp_dir["state"])
        state, result = check_cooldown(tmp_dir["state"])
        assert state.is_on_cooldown()
        assert not result.passed

    def test_expired_cooldown_passes(self, tmp_dir: dict[str, Path]) -> None:
        past = datetime.now(UTC) - timedelta(days=COOLDOWN_DAYS + 1)
        s = CooldownState(
            last_apply_utc=past.isoformat(),
            candidate_sha="abc", bot_id=CANARY_BOT_ID,
        )
        s.save(tmp_dir["state"])
        state, result = check_cooldown(tmp_dir["state"])
        assert not state.is_on_cooldown()
        assert result.passed


# -- 3. Readiness runner ------------------------------------------------------


class TestReadinessRunner:
    def test_ready_for_canary_with_all_gates(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            candidate_sha="f68a031923d0",
            bot_id=canary,
            parameter_overlay=overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert report.ready, f"Should be ready: {report.canary_gate.reason}"

    def test_blocks_wrong_bot(
        self, overlay: dict[str, int], tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            "abc", "freqtrade-regime-hybrid", overlay,
            state_dir=tmp_dir["state"],
        )
        assert not report.ready
        assert report.canary_gate.passed is False

    def test_blocks_unsafe_value(
        self, canary: str, l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            "abc", canary, {"cooldown_candles": 9999},
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="PASS",
            pre_apply_config={"dry_run": True},
        )
        assert not report.ready
        assert not report.safe_parameters_gate.passed

    def test_blocks_no_token(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            "abc", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert not report.ready

    def test_blocks_halt_new_kill_switch(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        ks = tmp_dir["state"] / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "HALT_NEW"}))
        report = check_readiness(
            "abc", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=ks, riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert not report.ready

    def test_blocks_riskguard_not_pass(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            "abc", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="FAIL",
            pre_apply_config=pre_cfg,
        )
        assert not report.ready

    def test_blocks_no_dry_run_config(
        self, canary: str, overlay: dict[str, int],
        l3_token: None, tmp_dir: dict[str, Path],
    ) -> None:
        report = check_readiness(
            "abc", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="PASS",
            pre_apply_config=None,
        )
        assert not report.ready


# -- 4. Overlay and rollback helpers ------------------------------------------


class TestOverlayWriter:
    def test_writes_file(self, tmp_dir: dict[str, Path]) -> None:
        path, sha = write_overlay_file(
            "f68a031923d0", {"cooldown_candles": 4},
            overlay_dir=tmp_dir["overlay"],
        )
        assert Path(path).exists()
        assert len(sha) == 64


class TestRollbackPlan:
    def test_creates_plan(self, tmp_dir: dict[str, Path]) -> None:
        path = create_rollback_plan(
            "f68a", CANARY_BOT_ID, "/tmp/o.json",
            {"cooldown_candles": 3},
            plan_dir=tmp_dir["plan"],
        )
        assert Path(path).exists()


class TestShadowLogger:
    def test_logs_and_does_not_block(self, tmp_dir: dict[str, Path]) -> None:
        # log_shadow_events should not raise
        log_shadow_events(
            "abc", CANARY_BOT_ID, {"cooldown_candles": 4},
            "/tmp/o.json", "/tmp/r.json",
            log_dir=tmp_dir["log"],
        )


# -- 5. Execute apply (end-to-end) --------------------------------------------


class TestExecuteApply:
    def test_success(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        decision = execute_apply(
            candidate_sha="f68a031923d0", bot_id=canary,
            parameter_overlay=overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            overlay_dir=tmp_dir["overlay"],
            plan_dir=tmp_dir["plan"],
            log_dir=tmp_dir["log"],
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert decision.overall_status == "SHADOW_OVERLAY_WRITTEN", decision.errors
        assert decision.overlay_path
        assert decision.rollback_plan_path
        assert not decision.mutation_counter_should_increment
        assert not decision.measurement_allowed

    def test_blocked_wrong_bot(
        self, overlay: dict[str, int], tmp_dir: dict[str, Path],
    ) -> None:
        d = execute_apply(
            "abc", "wrong-bot", overlay,
            state_dir=tmp_dir["state"],
        )
        assert d.overall_status == "BLOCKED"

    def test_blocked_unsafe_value(
        self, canary: str, l3_token: None, tmp_dir: dict[str, Path],
    ) -> None:
        d = execute_apply(
            "abc", canary, {"cooldown_candles": 9999},
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="PASS",
            pre_apply_config={"dry_run": True},
        )
        assert d.overall_status == "BLOCKED"

    def test_blocked_no_token(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], tmp_dir: dict[str, Path],
    ) -> None:
        d = execute_apply(
            "abc", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=None, riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert d.overall_status == "BLOCKED"


# -- 6. Summarize_decision ----------------------------------------------------


class TestSummarize:
    def test_summary_includes_safety_fields(self) -> None:
        d = ControlledApplyDecision(
            overall_status="SHADOW_OVERLAY_WRITTEN",
            candidate_sha="f68a", bot_id=CANARY_BOT_ID,
        )
        s = summarize_decision(d)
        assert s["status"] == "SHADOW_OVERLAY_WRITTEN"
        assert s["mutation_counter_should_increment"] is False
        assert s["measurement_allowed"] is False
        assert s["runtime_visible"] is False
        assert s["runtime_proof_status"] == "NOT_RUN"
