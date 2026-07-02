"""Tests for fleet_dry_run_rollback_executor.py — Phase 10.5.

All tests use tmp_path, fake decision packs, fake snapshots, fake rollback
plans, and fake runtime executors — no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.rollout.fleet_dry_run_rollback_executor import (
    DryRunRollbackExecutorInput,
    run_dry_run_fleet_rollback_executor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_rollback_decision_pack(
    tmp_path: Path,
    *,
    decision: str = "ROLLBACK_FLEET_OVERLAY",
    status: str = "FINAL_DECISION_EMITTED",
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
    change_id: str = "rollback-change-001",
    candidate_id: str = "rollback-candidate-001",
) -> str:
    """Write a synthetic ROLLBACK decision pack."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "post_fleet_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": decision,
        "status": status,
        "runtime_mutation": runtime_mutation,
        "expected_parameter": "max_open_trades",
        "expected_value": 2,
    }
    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
    return str(path)


def _make_keep_decision_pack(
    tmp_path: Path,
    *,
    change_id: str = "keep-change-001",
    candidate_id: str = "keep-candidate-001",
) -> str:
    """Write a synthetic KEEP decision pack (should be rejected)."""
    return _make_rollback_decision_pack(
        tmp_path,
        decision="KEEP_FLEET_OVERLAY",
        change_id=change_id,
        candidate_id=candidate_id,
    )


def _make_extend_decision_pack(
    tmp_path: Path,
    *,
    change_id: str = "extend-change-001",
    candidate_id: str = "extend-candidate-001",
) -> str:
    """Write a synthetic EXTEND decision pack (should be rejected)."""
    return _make_rollback_decision_pack(
        tmp_path,
        decision="EXTEND_MEASUREMENT",
        change_id=change_id,
        candidate_id=candidate_id,
    )


def _make_snapshot(
    tmp_path: Path,
    *,
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
) -> str:
    """Write a synthetic pre-apply snapshot."""
    global _serial
    _serial += 1
    snapshot: dict[str, object] = {
        "event": "pre_apply_snapshot",
        "target_bot": target_bot,
        "config_path": "/freqtrade/user_data/config.json",
        "snapshot_taken_at_utc": "2026-07-01T12:00:00Z",
        "runtime_mutation": runtime_mutation,
    }
    path = tmp_path / f"snapshot_{_serial}.json"
    path.write_text(json.dumps(snapshot))
    return str(path)


def _make_rollback_plan(
    tmp_path: Path,
    *,
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
    dry_run_in_command: bool = True,
) -> str:
    """Write a synthetic rollback plan."""
    global _serial
    _serial += 1
    cmd_prefix = [
        "freqtrade", "trade",
        "--config", "/freqtrade/user_data/config.json",
    ]
    if dry_run_in_command:
        cmd_prefix.extend(["--dry-run"])
    plan: dict[str, object] = {
        "event": "rollback_plan",
        "target_bot": target_bot,
        "config_path": "/freqtrade/user_data/config.json",
        "rollback_instruction": (
            "Phase 9C must restore the pre-apply config from "
            "snapshot and remove the overlay --config reference "
            "from the command."
        ),
        "rollback_command_prefix": cmd_prefix,
        "runtime_mutation": runtime_mutation,
    }
    path = tmp_path / f"rollback_plan_{_serial}.json"
    path.write_text(json.dumps(plan))
    return str(path)


def _make_runtime_executor() -> object:
    """Create a simple fake runtime executor for testing."""

    def executor(target_bot: str, rollback_plan_path: str) -> dict[str, str]:
        return {
            "status": "success",
            "detail": f"rolled back {target_bot}",
        }

    return executor


def _make_failing_executor() -> object:
    """Create a fake runtime executor that fails."""

    def executor(target_bot: str, rollback_plan_path: str) -> dict[str, str]:
        raise RuntimeError(f"simulated rollback failure for {target_bot}")

    return executor


def _default_rollback_input(
    tmp_path: Path,
    *,
    decision_pack_path: str | None = None,
    snapshot_path: str | None = None,
    rollback_plan_path: str | None = None,
    target_bot: str = "freqtrade-regime-hybrid",
    allowed_targets: tuple[str, ...] | None = None,
    allow_multiple_targets: bool = False,
) -> DryRunRollbackExecutorInput:
    """Build a default rollback executor input for testing."""
    if decision_pack_path is None:
        decision_pack_path = _make_rollback_decision_pack(tmp_path)
    if snapshot_path is None:
        snapshot_path = _make_snapshot(tmp_path)
    if rollback_plan_path is None:
        rollback_plan_path = _make_rollback_plan(tmp_path)
    return DryRunRollbackExecutorInput(
        decision_pack_path=decision_pack_path,
        snapshot_path=snapshot_path,
        rollback_plan_path=rollback_plan_path,
        target_bot=target_bot,
        allowed_targets=allowed_targets,
        allow_multiple_targets=allow_multiple_targets,
    )


# ---------------------------------------------------------------------------
# Tests: Safety guards — decision pack validation
# ---------------------------------------------------------------------------


def test_refuses_keep_decision_pack(tmp_path: Path) -> None:
    """Executor refuses a KEEP decision pack."""
    pack_path = _make_keep_decision_pack(tmp_path)
    input_ = _default_rollback_input(
        tmp_path, decision_pack_path=pack_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("decision_not_rollback" in r for r in result.blocked_reasons)


def test_refuses_extend_decision_pack(tmp_path: Path) -> None:
    """Executor refuses an EXTEND decision pack."""
    pack_path = _make_extend_decision_pack(tmp_path)
    input_ = _default_rollback_input(
        tmp_path, decision_pack_path=pack_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("decision_not_rollback" in r for r in result.blocked_reasons)


def test_refuses_missing_decision_pack(tmp_path: Path) -> None:
    """Executor refuses a missing decision pack."""
    input_ = _default_rollback_input(
        tmp_path,
        decision_pack_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("decision_pack_not_readable" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Safety guards — snapshot validation
# ---------------------------------------------------------------------------


def test_refuses_missing_snapshot(tmp_path: Path) -> None:
    """Executor refuses a missing snapshot."""
    input_ = _default_rollback_input(
        tmp_path,
        snapshot_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("snapshot_not_found" in r for r in result.blocked_reasons)


def test_refuses_empty_snapshot_path(tmp_path: Path) -> None:
    """Executor refuses an empty snapshot path."""
    input_ = _default_rollback_input(
        tmp_path, snapshot_path="",
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("snapshot_path_empty" in r for r in result.blocked_reasons)


def test_refuses_snapshot_with_runtime_mutation(tmp_path: Path) -> None:
    """Executor refuses a snapshot with runtime_mutation != NONE."""
    snapshot_path = _make_snapshot(tmp_path, runtime_mutation="MUTATED")
    input_ = _default_rollback_input(
        tmp_path, snapshot_path=snapshot_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any(
        "snapshot_runtime_mutation_not_none" in r
        for r in result.blocked_reasons
    )


# ---------------------------------------------------------------------------
# Tests: Safety guards — rollback plan validation
# ---------------------------------------------------------------------------


def test_refuses_missing_rollback_plan(tmp_path: Path) -> None:
    """Executor refuses a missing rollback plan."""
    input_ = _default_rollback_input(
        tmp_path,
        rollback_plan_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("rollback_plan_not_found" in r for r in result.blocked_reasons)


def test_refuses_empty_rollback_plan_path(tmp_path: Path) -> None:
    """Executor refuses an empty rollback plan path."""
    input_ = _default_rollback_input(
        tmp_path, rollback_plan_path="",
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("rollback_plan_path_empty" in r for r in result.blocked_reasons)


def test_refuses_rollback_plan_with_runtime_mutation(tmp_path: Path) -> None:
    """Executor refuses a rollback plan with runtime_mutation != NONE."""
    plan_path = _make_rollback_plan(
        tmp_path, runtime_mutation="MUTATED",
    )
    input_ = _default_rollback_input(
        tmp_path, rollback_plan_path=plan_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any(
        "rollback_plan_runtime_mutation_not_none" in r
        for r in result.blocked_reasons
    )


# ---------------------------------------------------------------------------
# Tests: Safety guards — allowlist validation
# ---------------------------------------------------------------------------


def test_refuses_non_allowlisted_target(tmp_path: Path) -> None:
    """Executor refuses a target not in the allowlist."""
    input_ = _default_rollback_input(
        tmp_path,
        target_bot="non-allowlisted-bot",
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("target_not_allowlisted" in r for r in result.blocked_reasons)


def test_accepts_custom_allowlist(tmp_path: Path) -> None:
    """Executor accepts a target in a custom allowlist."""
    input_ = _default_rollback_input(
        tmp_path,
        target_bot="custom-bot",
        allowed_targets=("custom-bot",),
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"


# ---------------------------------------------------------------------------
# Tests: Safety guards — dry-run validation
# ---------------------------------------------------------------------------


def test_refuses_non_dry_run_target(tmp_path: Path) -> None:
    """Executor refuses a target whose rollback plan lacks dry_run."""
    plan_path = _make_rollback_plan(
        tmp_path, dry_run_in_command=False,
    )
    input_ = _default_rollback_input(
        tmp_path, rollback_plan_path=plan_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert any("dry_run_not_confirmed" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Successful execution
# ---------------------------------------------------------------------------


def test_rollback_green_with_single_target(tmp_path: Path) -> None:
    """Executor returns GREEN for a single allowlisted target."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"
    assert result.change_id == "rollback-change-001"
    assert result.candidate_id == "rollback-candidate-001"
    assert result.target_bot == "freqtrade-regime-hybrid"
    assert len(result.blocked_reasons) == 0


def test_rollback_green_with_allowlisted_target(tmp_path: Path) -> None:
    """Executor succeeds with a target in DEFAULT_ALLOWED_DRY_RUN_TARGETS."""
    input_ = _default_rollback_input(
        tmp_path,
        target_bot="freqai-rebel",
    )
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"


def test_rollback_green_without_runtime_executor(tmp_path: Path) -> None:
    """Executor succeeds in simulation mode without a runtime executor."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_rollback_audit(tmp_path: Path) -> None:
    """Executor writes rollback audit artifact."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"

    audit_path = Path(result.rollback_audit_path)
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "rollback_audit"
    assert audit["target_bot"] == "freqtrade-regime-hybrid"
    assert audit["runtime_mutation"] == "NONE"


def test_writes_rollback_effect_proof(tmp_path: Path) -> None:
    """Executor writes rollback RuntimeEffectProof artifact."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"

    proof_path = Path(result.rollback_effect_proof_path)
    assert proof_path.exists()
    proof = json.loads(proof_path.read_text())
    assert proof["event"] == "rollback_effect_proof"
    assert proof["target_bot"] == "freqtrade-regime-hybrid"
    assert proof["rollback_status"] == "EXECUTED"
    assert proof["runtime_mutation"] == "NONE"


def test_writes_post_rollback_measurement_start(tmp_path: Path) -> None:
    """Executor writes post-rollback measurement start record."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"

    measurement_path = Path(result.post_rollback_measurement_start_path)
    assert measurement_path.exists()
    measurement = json.loads(measurement_path.read_text())
    assert measurement["event"] == "post_rollback_measurement_start_record"
    assert measurement["target_bot"] == "freqtrade-regime-hybrid"
    assert measurement["runtime_mutation"] == "NONE"


def test_writes_executor_audit(tmp_path: Path) -> None:
    """Executor writes its own audit artifact."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"

    # The executor audit is at rollback_output_dir / rollback_executor_audit.json
    audit_path = tmp_path / "rollback_executor_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "dry_run_rollback_executor_audit"
    assert audit["status"] == "DRY_RUN_ROLLBACK_GREEN"
    assert audit["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Partial failure
# ---------------------------------------------------------------------------


def test_partial_failure_yields_yellow(tmp_path: Path) -> None:
    """Runtime executor failure yields YELLOW, not silent GREEN."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_failing_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_YELLOW"
    assert any("rollback_execution_failed" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """DryRunRollbackExecutorResult must be JSON-serializable."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "dry_run_rollback_executor_result"
    assert deserialized["status"] == "DRY_RUN_ROLLBACK_GREEN"


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "LIVE" not in d["status"]


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE."""
    input_ = _default_rollback_input(tmp_path)
    result = run_dry_run_fleet_rollback_executor(
        input_,
        rollback_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_ROLLBACK_GREEN"

    # Check rollback audit
    audit = json.loads(Path(result.rollback_audit_path).read_text())
    assert audit["runtime_mutation"] == "NONE"

    # Check effect proof
    proof = json.loads(Path(result.rollback_effect_proof_path).read_text())
    assert proof["runtime_mutation"] == "NONE"

    # Check measurement start
    measurement = json.loads(
        Path(result.post_rollback_measurement_start_path).read_text()
    )
    assert measurement["runtime_mutation"] == "NONE"

    # Check executor audit
    executor_audit = json.loads(
        (tmp_path / "rollback_executor_audit.json").read_text()
    )
    assert executor_audit["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Blocked executor writes audit
# ---------------------------------------------------------------------------


def test_blocked_executor_writes_audit(tmp_path: Path) -> None:
    """Blocked executor still writes an audit artifact."""
    pack_path = _make_keep_decision_pack(tmp_path)
    input_ = _default_rollback_input(
        tmp_path, decision_pack_path=pack_path,
    )
    result = run_dry_run_fleet_rollback_executor(
        input_, rollback_output_dir=tmp_path,
    )
    assert result.status == "DRY_RUN_ROLLBACK_BLOCKED"
    assert result.rollback_audit_path
    audit = json.loads(Path(result.rollback_audit_path).read_text())
    assert audit["event"] == "dry_run_rollback_executor_audit"
    assert audit["status"] == "BLOCKED"
    assert audit["runtime_mutation"] == "NONE"
