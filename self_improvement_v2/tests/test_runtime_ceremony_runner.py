"""Tests for SI-v2 Phase 6C Runtime Ceremony Runner.

Test coverage:
  1. test_blocks_missing_overlay
  2. test_blocks_overlay_hash_mismatch
  3. test_blocks_missing_rollback_plan
  4. test_blocks_missing_audit
  5. test_blocks_missing_measurement_plan
  6. test_blocks_non_canary
  7. test_blocks_dry_run_false
  8. test_blocks_kill_switch_not_normal
  9. test_blocks_riskguard_not_pass
  10. test_ready_without_runtime_execution
  11. test_execute_runtime_false_does_not_call_subprocess
  12-13. test_execute_runtime_true with mocked results
  14. test_manual_l3_mode_not_used_for_autonomous_path
  15. test_live_capital_mode_blocks
  16. test_t0_activation_only_after_green_runtime_proof
  17. test_result_serializable
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from si_v2.pipeline.runtime_ceremony_runner import (
    AUTONOMOUS_MODE,
    LIVE_MODE,
    MANUAL_MODE,
    RuntimeCeremonyInput,
    run_runtime_ceremony,
)


def _make_ceremony_input(
    *,
    change_id: str = "change_abc123",
    candidate_id: str = "test_candidate_001",
    target_bot: str = "freqtrade-freqforge-canary",
    pre_apply_config: dict[str, object] | None = None,
    current_command: tuple[str, ...] = (
        "freqtrade", "trade", "--config", "/freqtrade/user_data/config.json",
    ),
    expected_parameter: str = "max_open_trades",
    expected_value: int | float = 2,
    kill_switch_mode: str = "NORMAL",
    riskguard_status: str = "PASS",
    apply_mode: str = AUTONOMOUS_MODE,
    tmp_path: Path | None = None,
) -> tuple[RuntimeCeremonyInput, dict[str, Path]]:
    """Create a ceremony input with real temp files in tmp_path."""
    assert tmp_path is not None, "tmp_path required"

    canary_user_data = tmp_path / "freqforge-canary" / "user_data"
    canary_user_data.mkdir(parents=True, exist_ok=True)

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    overlay_data = {"max_open_trades": 2, "_meta": {"candidate_id": candidate_id}}
    overlay_path = canary_user_data / "overlay_test_candidate.json"
    overlay_path.write_text(json.dumps(overlay_data))
    overlay_sha256 = hashlib.sha256(overlay_path.read_bytes()).hexdigest()

    rollback_path = state_dir / "rollback_test.json"
    rollback_path.write_text(json.dumps({"candidate_id": candidate_id}))

    audit_path = state_dir / "audit.jsonl"
    audit_path.write_text(json.dumps({"event": "test"}) + "\n")

    meas_path = state_dir / "measurement_start_test.json"
    meas_path.write_text(json.dumps({"candidate_id": candidate_id}))

    return RuntimeCeremonyInput(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        overlay_path=str(overlay_path),
        overlay_sha256=overlay_sha256,
        rollback_plan_path=str(rollback_path),
        audit_path=str(audit_path),
        measurement_start_plan_path=str(meas_path),
        pre_apply_config=pre_apply_config or {"dry_run": True, "max_open_trades": 3},
        current_command=current_command,
        expected_parameter=expected_parameter,
        expected_value=expected_value,
        kill_switch_mode=kill_switch_mode,
        riskguard_status=riskguard_status,
        apply_mode=apply_mode,
    ), {"state": state_dir, "canary_user_data": canary_user_data}


class TestCeremonyBlocked:
    """Tests for blocking conditions."""

    def _run(self, input_: RuntimeCeremonyInput) -> Any:
        return run_runtime_ceremony(input_, execute_runtime=False)

    def test_blocks_missing_overlay(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(tmp_path=tmp_path)
        input_ = RuntimeCeremonyInput(
            **{**input_.__dict__, "overlay_path": "/nonexistent/overlay.json"}
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_overlay_hash_mismatch(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(tmp_path=tmp_path)
        input_ = RuntimeCeremonyInput(
            **{**input_.__dict__, "overlay_sha256": "0" * 64}
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_missing_rollback_plan(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(tmp_path=tmp_path)
        input_ = RuntimeCeremonyInput(
            **{**input_.__dict__, "rollback_plan_path": ""}
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_missing_audit(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(tmp_path=tmp_path)
        input_ = RuntimeCeremonyInput(
            **{**input_.__dict__, "audit_path": ""}
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_missing_measurement_plan(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(tmp_path=tmp_path)
        input_ = RuntimeCeremonyInput(
            **{**input_.__dict__, "measurement_start_plan_path": ""}
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_non_canary(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(
            tmp_path=tmp_path, target_bot="freqtrade-freqforge",
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_dry_run_false(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(
            tmp_path=tmp_path,
            pre_apply_config={"dry_run": False, "max_open_trades": 3},
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_kill_switch_not_normal(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(
            tmp_path=tmp_path, kill_switch_mode="HALT_NEW",
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons

    def test_blocks_riskguard_not_pass(self, tmp_path: Path) -> None:
        input_, _ = _make_ceremony_input(
            tmp_path=tmp_path, riskguard_status="FAIL",
        )
        result = self._run(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons


class TestCeremonyReady:
    """Tests for ready state without runtime execution."""

    def test_ready_without_runtime_execution(self, tmp_path: Path) -> None:
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=False,
            canary_user_data=dirs["canary_user_data"],
        )
        assert result.status == "CEREMONY_READY", (
            f"Should be ready: {result.status}: {result.blocked_reasons}"
        )
        assert result.restart_plan_ready
        assert result.runtime_status == "NOT_EXECUTED"
        assert not result.t0_measurement_active
        assert result.restart_plan is not None

    def test_execute_runtime_false_does_not_call_subprocess(
        self, tmp_path: Path,
    ) -> None:
        """execute_runtime=False should not trigger runtime execution."""
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=False,
            canary_user_data=dirs["canary_user_data"],
        )
        assert result.status == "CEREMONY_READY"
        assert result.runtime_result is None


class TestCeremonyRuntimeExecution:
    """Tests for runtime execution."""

    def test_execute_runtime_true_mocked_green(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Mocked runtime success should return GREEN."""
        from si_v2.apply_actuator.models import ProofStatus, RuntimeEffectProof
        from si_v2.apply_actuator.runtime_executor import RuntimeExecutionResult

        def _fake_run(**kwargs: Any) -> RuntimeExecutionResult:
            return RuntimeExecutionResult(
                status="EXECUTED_GREEN",
                reason="mocked_green",
                proof=RuntimeEffectProof(
                    proposal_id="test",
                    bot_id="freqtrade-freqforge-canary",
                    proof_status=ProofStatus.GREEN,
                ),
            )

        # Patch the ceremony runner's module-level import
        import si_v2.pipeline.runtime_ceremony_runner as cr
        monkeypatch.setattr(cr, "run_canary_restart_with_overlay", _fake_run)
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=True,
            canary_user_data=dirs["canary_user_data"],
        )
        assert result.status == "CEREMONY_EXECUTED_GREEN", (
            f"Should be GREEN: {result.status}"
        )
        assert result.runtime_proof_status == "GREEN"
        assert result.t0_measurement_active

    def test_execute_runtime_true_mocked_red(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Mocked runtime failure should return RED."""
        from si_v2.apply_actuator.runtime_executor import RuntimeExecutionResult

        def _fake_run(**kwargs: Any) -> RuntimeExecutionResult:
            return RuntimeExecutionResult(
                status="EXECUTED_RED",
                reason="mocked_red",
            )

        import si_v2.pipeline.runtime_ceremony_runner as cr
        monkeypatch.setattr(cr, "run_canary_restart_with_overlay", _fake_run)
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=True,
            canary_user_data=dirs["canary_user_data"],
        )
        assert result.status == "CEREMONY_EXECUTED_RED", (
            f"Should be RED: {result.status}"
        )
        assert result.runtime_proof_status == "RED"
        assert not result.t0_measurement_active


class TestCeremonyModes:
    """Tests for different apply modes."""

    def test_manual_l3_mode_not_used_for_autonomous_path(
        self, tmp_path: Path,
    ) -> None:
        """MANUAL_L3 mode should still work via runtime_executor."""
        input_, dirs = _make_ceremony_input(
            tmp_path=tmp_path, apply_mode=MANUAL_MODE,
        )
        result = run_runtime_ceremony(
            input_, execute_runtime=False,
            canary_user_data=dirs["canary_user_data"],
        )
        assert result.status == "CEREMONY_READY", (
            f"MANUAL_L3 should be ready: {result.status}"
        )

    def test_live_capital_mode_blocks(self, tmp_path: Path) -> None:
        """LIVE_CAPITAL_MODE should block."""
        input_, _ = _make_ceremony_input(
            tmp_path=tmp_path, apply_mode=LIVE_MODE,
        )
        result = run_runtime_ceremony(input_)
        assert result.status == "CEREMONY_BLOCKED", result.blocked_reasons


class TestCeremonyT0Activation:
    """T0 activation only after GREEN runtime proof."""

    def test_t0_activation_only_after_green_runtime_proof(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """T0 should only activate for GREEN."""
        from si_v2.apply_actuator.models import ProofStatus, RuntimeEffectProof
        from si_v2.apply_actuator.runtime_executor import RuntimeExecutionResult

        def _fake_run_green(**kwargs: Any) -> RuntimeExecutionResult:
            return RuntimeExecutionResult(
                status="EXECUTED_GREEN",
                reason="mocked_green",
                proof=RuntimeEffectProof(
                    proposal_id="test",
                    bot_id="freqtrade-freqforge-canary",
                    proof_status=ProofStatus.GREEN,
                ),
            )

        import si_v2.pipeline.runtime_ceremony_runner as cr
        monkeypatch.setattr(cr, "run_canary_restart_with_overlay", _fake_run_green)
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        t0_dir = dirs["state"] / "t0_records"
        result = run_runtime_ceremony(
            input_, execute_runtime=True,
            canary_user_data=dirs["canary_user_data"],
            t0_dir=t0_dir,
        )
        assert result.status == "CEREMONY_EXECUTED_GREEN"
        assert result.t0_measurement_active
        t0_files = list(t0_dir.glob("t0_active_*"))
        assert len(t0_files) > 0, "T0 activation record should exist"


class TestCeremonyResultShape:
    """Result serialization."""

    def test_result_serializable(self, tmp_path: Path) -> None:
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=False,
            canary_user_data=dirs["canary_user_data"],
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0
        assert d["status"] == "CEREMONY_READY"
        assert d["change_id"] == "change_abc123"
        assert d["t0_measurement_active"] is False

    def test_result_serializable_after_execution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Even executed results should be serializable."""
        from si_v2.apply_actuator.models import ProofStatus, RuntimeEffectProof
        from si_v2.apply_actuator.runtime_executor import RuntimeExecutionResult

        def _fake_run_green(**kwargs: Any) -> RuntimeExecutionResult:
            return RuntimeExecutionResult(
                status="EXECUTED_GREEN",
                reason="mocked_green",
                proof=RuntimeEffectProof(
                    proposal_id="test",
                    bot_id="freqtrade-freqforge-canary",
                    proof_status=ProofStatus.GREEN,
                ),
            )

        import si_v2.pipeline.runtime_ceremony_runner as cr
        monkeypatch.setattr(cr, "run_canary_restart_with_overlay", _fake_run_green)
        input_, dirs = _make_ceremony_input(tmp_path=tmp_path)
        result = run_runtime_ceremony(
            input_, execute_runtime=True,
            canary_user_data=dirs["canary_user_data"],
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0
        assert d["status"] == "CEREMONY_EXECUTED_GREEN"
