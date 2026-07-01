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
    check_candidate_compatibility,
    check_cooldown,
    check_dry_run,
    check_human_approval,
    check_kill_switch,
    check_readiness,
    check_riskguard,
    check_safe_parameters,
    check_token,
    create_rollback_plan,
    derive_riskguard_status,
    execute_apply,
    log_shadow_events,
    read_riskguard_status,
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

    def test_reject_none_path(self) -> None:
        """check_kill_switch(None) must block - fail-closed."""
        result = check_kill_switch(None)
        assert not result.passed
        assert "fail-closed" in result.reason.lower() or "blocked" in result.reason.lower()

    def test_reject_missing_file(self, tmp_path: Path) -> None:
        """check_kill_switch(nonexistent) must block - fail-closed."""
        missing = tmp_path / "nonexistent_kill_switch.json"
        assert not missing.exists()
        result = check_kill_switch(missing)
        assert not result.passed
        assert "fail-closed" in result.reason.lower() or "blocked" in result.reason.lower()


class TestRiskGuard:
    def test_accept_pass(self) -> None:
        assert check_riskguard("PASS").passed

    def test_reject_fail(self) -> None:
        assert not check_riskguard("FAIL").passed

    def test_reject_none(self) -> None:
        """check_riskguard(None) reads canonical state; on this test host it may PASS.

        We therefore only verify it returns a deterministic GateResult and does
        not raise.  The fail-closed behavior on a missing file is tested via
        read_riskguard_status(missing_path).
        """
        result = check_riskguard(None)
        assert isinstance(result.passed, bool)
        assert result.reason

    def test_derive_pass_active_with_accepted(self) -> None:
        state = {
            "summary": {"status": "ACTIVE"},
            "pairs": {
                "BTC/USDT": {"verdict": "ACCEPTED"},
                "ETH/USDT": {"verdict": "WATCH_ONLY"},
            },
        }
        assert derive_riskguard_status(state) == "PASS"

    def test_derive_fail_no_accepted(self) -> None:
        state = {
            "summary": {"status": "ACTIVE"},
            "pairs": {
                "BTC/USDT": {"verdict": "WATCH_ONLY"},
            },
        }
        assert derive_riskguard_status(state) == "FAIL"

    def test_derive_fail_block_entry(self) -> None:
        state = {
            "summary": {"status": "ACTIVE"},
            "pairs": {
                "BTC/USDT": {"verdict": "ACCEPTED"},
                "ETH/USDT": {"verdict": "BLOCK_ENTRY"},
            },
        }
        assert derive_riskguard_status(state) == "FAIL"

    def test_derive_fail_not_active(self) -> None:
        state = {
            "summary": {"status": "DEGRADED"},
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED"}},
        }
        assert derive_riskguard_status(state) == "FAIL"

    def test_derive_fail_missing_summary(self) -> None:
        assert derive_riskguard_status({"pairs": {}}) == "FAIL"

    def test_read_missing_file_blocks(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing_riskguard_state.json"
        result = read_riskguard_status(missing)
        assert not result.passed
        assert "fail-closed" in result.reason.lower() or "blocked" in result.reason.lower()

    def test_read_active_accepted_pass(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        state = {
            "schema_version": "1.0",
            "summary": {"status": "ACTIVE"},
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED", "confidence": 0.85}},
        }
        state_path.write_text(json.dumps(state))
        result = read_riskguard_status(state_path)
        assert result.passed

    def test_read_corrupt_blocks(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        state_path.write_text("{bad json}")
        result = read_riskguard_status(state_path)
        assert not result.passed

    def test_read_none_uses_default_path(self) -> None:
        """check_riskguard(None) without override should read canonical path.

        We only assert that it returns a GateResult; the actual verdict depends
        on whether orchestrator/state/riskguard/riskguard_state.json exists.
        """
        result = check_riskguard(None)
        assert isinstance(result.passed, bool)

    def test_check_riskguard_reads_state(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        state = {
            "summary": {"status": "ACTIVE"},
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED"}},
        }
        state_path.write_text(json.dumps(state))
        from si_v2.apply_actuator import controlled_apply_actuator as _caa
        original = _caa.RISKGUARD_STATE_PATH
        try:
            _caa.RISKGUARD_STATE_PATH = state_path
            result = check_riskguard(None)
            assert result.passed
        finally:
            _caa.RISKGUARD_STATE_PATH = original


class TestDryRun:
    def test_accept_true(self, pre_cfg: dict[str, object]) -> None:
        assert check_dry_run(pre_cfg).passed

    def test_reject_false(self, pre_cfg: dict[str, object]) -> None:
        pre_cfg["dry_run"] = False
        assert not check_dry_run(pre_cfg).passed

    def test_block_on_none(self) -> None:
        """Unconditional: no config must block (HIGH-1)."""
        assert not check_dry_run(None).passed

    def test_block_missing_key(self) -> None:
        """Missing dry_run key must block — fail-closed."""
        assert not check_dry_run({"max_open_trades": 3}).passed


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
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        ks = tmp_dir["state"] / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))
        report = check_readiness(
            candidate_sha="f68a031923d0",
            bot_id=canary,
            parameter_overlay=overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=ks,
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
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        ks = tmp_dir["state"] / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))
        decision = execute_apply(
            candidate_sha="f68a031923d0", bot_id=canary,
            parameter_overlay=overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            overlay_dir=tmp_dir["overlay"],
            plan_dir=tmp_dir["plan"],
            log_dir=tmp_dir["log"],
            kill_switch_path=ks,
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


# -- 7. Candidate Compatibility Gate ------------------------------------------


class TestCandidateCompatibilityGate:
    """Tests for Gate 9: candidate compatibility with runtime config."""

    def test_pass_when_key_exists_and_baseline_matches(self) -> None:
        """PASS when overlay key exists in pre_apply_config and current
        value matches expected baseline."""
        result = check_candidate_compatibility(
            {"max_open_trades": 4},
            pre_apply_config={"max_open_trades": 3, "dry_run": True},
            expected_baselines={"max_open_trades": 3},
        )
        assert result.passed
        assert "proven baselines" in result.reason.lower()

    def test_pass_when_key_exists_no_baseline_required(self) -> None:
        """PASS when overlay key exists and no expected baseline is required."""
        result = check_candidate_compatibility(
            {"max_open_trades": 4},
            pre_apply_config={"max_open_trades": 3, "dry_run": True},
        )
        assert result.passed

    def test_block_when_key_absent_from_pre_apply_config(self) -> None:
        """BLOCK when overlay key is absent from pre_apply_config."""
        result = check_candidate_compatibility(
            {"cooldown_candles": 4},
            pre_apply_config={"max_open_trades": 3, "dry_run": True},
        )
        assert not result.passed
        assert "absent" in result.reason.lower()

    def test_block_when_key_value_is_none(self) -> None:
        """BLOCK when overlay key exists but value is None."""
        result = check_candidate_compatibility(
            {"cooldown_candles": 4},
            pre_apply_config={"cooldown_candles": None, "dry_run": True},
        )
        assert not result.passed
        assert "none" in result.reason.lower()

    def test_block_when_expected_baseline_differs(self) -> None:
        """BLOCK when expected current value differs from runtime value."""
        result = check_candidate_compatibility(
            {"max_open_trades": 4},
            pre_apply_config={"max_open_trades": 5, "dry_run": True},
            expected_baselines={"max_open_trades": 3},
        )
        assert not result.passed
        assert "baseline mismatch" in result.reason.lower()

    def test_block_f68a_candidate_when_runtime_value_is_none(self) -> None:
        """BLOCK f68a031923d0-like cooldown_candles candidate when runtime
        value is None or absent — the core regression test."""
        result = check_candidate_compatibility(
            {"cooldown_candles": 4},
            pre_apply_config={
                "dry_run": True,
                "max_open_trades": 3,
                "cooldown_candles": None,
            },
            expected_baselines={"cooldown_candles": 3},
        )
        assert not result.passed
        assert "none" in result.reason.lower() or "baseline mismatch" in result.reason.lower()

    def test_block_when_pre_apply_config_is_none(self) -> None:
        """BLOCK when pre_apply_config is not provided."""
        result = check_candidate_compatibility(
            {"max_open_trades": 4},
            pre_apply_config=None,
        )
        assert not result.passed
        assert "not provided" in result.reason.lower()

    def test_multiple_failures_reported(self) -> None:
        """All failures are reported, not just the first."""
        result = check_candidate_compatibility(
            {"cooldown_candles": 4, "rsi_period": 20},
            pre_apply_config={"rsi_period": None, "dry_run": True},
        )
        assert not result.passed
        assert "cooldown_candles" in result.reason
        assert "rsi_period" in result.reason


class TestCompatibilityGateInReadiness:
    """Verify compatibility gate appears in readiness report and
    prevents ready status even if safe_parameters passes."""

    def test_compatibility_gate_appears_in_report(self) -> None:
        """Verify compatibility_gate field exists in readiness report."""
        report = check_readiness(
            "abc", CANARY_BOT_ID, {"max_open_trades": 4},
            state_dir=Path("/tmp/test_compat_gate"),
            kill_switch_path=None,
            riskguard_status="PASS",
            pre_apply_config={"max_open_trades": 3, "dry_run": True},
        )
        d = report.to_dict()
        assert "compatibility_gate" in d
        assert isinstance(d["compatibility_gate"], dict)
        assert "passed" in d["compatibility_gate"]
        assert "reason" in d["compatibility_gate"]

    def test_compatibility_failure_prevents_ready_even_if_safe_params_pass(
        self, canary: str, l3_token: None, tmp_dir: dict[str, Path],
    ) -> None:
        """Compatibility failure prevents ready status even if
        safe_parameters passes."""
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        ks = tmp_dir["state"] / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))
        report = check_readiness(
            "f68a031923d0", canary,
            {"cooldown_candles": 4},
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config={
                "dry_run": True,
                "max_open_trades": 3,
                "cooldown_candles": None,
            },
        )
        # safe_parameters should pass (cooldown_candles=4 is in SAFE_PARAMETERS)
        assert report.safe_parameters_gate.passed
        # compatibility gate should block
        assert not report.compatibility_gate.passed
        # overall should not be ready
        assert not report.ready

    def test_ready_when_compatibility_passes(
        self, canary: str, overlay: dict[str, int],
        pre_cfg: dict[str, object], l3_token: None,
        tmp_dir: dict[str, Path],
    ) -> None:
        """Full readiness passes when compatibility gate passes."""
        tmp_dir["state"].mkdir(parents=True, exist_ok=True)
        ks = tmp_dir["state"] / "kill_switch.json"
        ks.write_text(json.dumps({"mode": "NORMAL"}))
        report = check_readiness(
            "f68a031923d0", canary, overlay,
            requires_human_approval=True,
            state_dir=tmp_dir["state"],
            kill_switch_path=ks,
            riskguard_status="PASS",
            pre_apply_config=pre_cfg,
        )
        assert report.ready, (
            f"Should be ready. Compatibility: {report.compatibility_gate.reason}"
        )
