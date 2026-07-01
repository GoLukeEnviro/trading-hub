"""Tests for fleet_runtime_ceremony.py — Phase 9C.

All tests use tmp_path and synthetic fleet rollout plan / overlay files —
no real runtime access, no Docker, no API calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from si_v2.rollout.fleet_runtime_ceremony import (
    FleetRuntimeCeremonyInput,
    run_fleet_runtime_ceremony,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_fleet_rollout_plan(
    tmp_path: Path,
    *,
    event: str = "fleet_rollout_artifact_plan",
    status: str = "ROLLOUT_PLAN_READY",
    runtime_mutation: str = "NONE",
    next_required_component: str = "fleet_rollout_runtime_ceremony",
    selected_targets: list[str] | None = None,
    target_plans: list[dict[str, object]] | None = None,
    change_id: str = "change-9c-001",
    candidate_id: str = "candidate-9c-001",
    source_bot: str = "freqtrade-freqforge-canary",
) -> str:
    """Write a synthetic fleet rollout plan JSON and return its path."""
    global _serial
    _serial += 1
    if selected_targets is None:
        selected_targets = ["freqtrade-regime-hybrid"]
    if target_plans is None:
        target_plans = []
    plan: dict[str, object] = {
        "event": event,
        "change_id": change_id,
        "candidate_id": candidate_id,
        "source_bot": source_bot,
        "status": status,
        "selected_targets": selected_targets,
        "target_plans": target_plans,
        "runtime_mutation": runtime_mutation,
        "next_required_component": next_required_component,
        "created_at_utc": "2026-07-01T12:00:00+00:00",
    }
    path = tmp_path / f"fleet_rollout_plan_{_serial}.json"
    path.write_text(json.dumps(plan))
    return str(path)


def _make_overlay(
    tmp_path: Path,
    *,
    parameter: str = "max_open_trades",
    value: int = 2,
) -> tuple[str, str]:
    """Write a synthetic overlay JSON and return (path, sha256)."""
    global _serial
    _serial += 1
    overlay = {
        parameter: value,
        "dry_run": True,
        "stake_currency": "USDT",
    }
    content = json.dumps(overlay, indent=2, sort_keys=True)
    path = tmp_path / f"overlay_{_serial}.json"
    path.write_text(content)
    sha = hashlib.sha256(content.encode()).hexdigest()
    return str(path), sha


def _make_target_plan(
    tmp_path: Path,
    *,
    target_bot: str = "freqtrade-regime-hybrid",
    overlay_path: str | None = None,
    overlay_sha256: str = "",
    rollback_plan_path: str = "/tmp/rollback_plan.json",
    pre_apply_snapshot_path: str = "/tmp/snapshot_plan.json",
    config_path: str = "/etc/freqtrade/config.json",
    user_data_dir: str = "/freqtrade/user_data",
    expected_parameter: str = "max_open_trades",
    expected_value: int = 2,
    validation_checks: list[str] | None = None,
) -> dict[str, object]:
    """Create a synthetic target plan dict."""
    if validation_checks is None:
        validation_checks = [
            "dry_run_true_required",
            "overlay_hash_match_required",
            "config_path_required",
            "rollback_plan_required",
        ]
    if overlay_path is None:
        overlay_path, overlay_sha256 = _make_overlay(tmp_path)
    return {
        "target_bot": target_bot,
        "role": "experimental",
        "config_path": config_path,
        "user_data_dir": user_data_dir,
        "overlay_path": overlay_path,
        "overlay_sha256": overlay_sha256,
        "expected_parameter": expected_parameter,
        "expected_value": expected_value,
        "pre_apply_snapshot_path": pre_apply_snapshot_path,
        "rollback_plan_path": rollback_plan_path,
        "validation_checks": validation_checks,
    }


def _make_runtime_executor() -> object:
    """Create a simple fake runtime executor for testing."""

    def executor(target_bot: str, overlay_path: str) -> dict[str, str]:
        return {"status": "success", "detail": f"applied overlay to {target_bot}"}

    return executor


def _make_failing_executor() -> object:
    """Create a fake runtime executor that fails."""

    def executor(target_bot: str, overlay_path: str) -> dict[str, str]:
        raise RuntimeError(f"simulated failure for {target_bot}")

    return executor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_blocks_missing_fleet_rollout_plan(tmp_path: Path) -> None:
    """Block when the fleet rollout plan file does not exist."""
    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("not_readable" in r for r in result.blocked_reasons)


def test_blocks_plan_not_ready(tmp_path: Path) -> None:
    """Block when plan status is not ROLLOUT_PLAN_READY."""
    plan_path = _make_fleet_rollout_plan(tmp_path, status="ROLLOUT_PLAN_BLOCKED")
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("plan_not_ready" in r for r in result.blocked_reasons)


def test_blocks_runtime_mutation_not_none(tmp_path: Path) -> None:
    """Block when runtime_mutation is not NONE."""
    plan_path = _make_fleet_rollout_plan(
        tmp_path, runtime_mutation="CANARY_RESTART"
    )
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("runtime_mutation_not_none" in r for r in result.blocked_reasons)


def test_blocks_wrong_next_component(tmp_path: Path) -> None:
    """Block when next_required_component is wrong."""
    plan_path = _make_fleet_rollout_plan(
        tmp_path, next_required_component="fleet_rollout_artifact_planner"
    )
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("wrong_next_component" in r for r in result.blocked_reasons)


def test_blocks_empty_target_plans(tmp_path: Path) -> None:
    """Block when target_plans is empty."""
    plan_path = _make_fleet_rollout_plan(tmp_path, target_plans=[])
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("empty_target_plans" in r for r in result.blocked_reasons)


def test_blocks_canary_target(tmp_path: Path) -> None:
    """Block when a target plan references a canary bot."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        target_bot="freqtrade-freqforge-canary",
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        selected_targets=["freqtrade-freqforge-canary"],
        target_plans=[target_plan],
    )
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("canary_target" in r for r in result.blocked_reasons)


def test_blocks_missing_overlay(tmp_path: Path) -> None:
    """Block when a target plan has no overlay_path."""
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path="",
        overlay_sha256="",
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("missing_overlay" in r for r in result.blocked_reasons)


def test_blocks_overlay_hash_mismatch(tmp_path: Path) -> None:
    """Block when overlay hash does not match."""
    overlay_path, _ = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256="0000000000000000000000000000000000000000000000000000000000000000",
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )
    input_ = FleetRuntimeCeremonyInput(fleet_rollout_plan_path=plan_path)
    result = run_fleet_runtime_ceremony(input_, ceremony_output_dir=tmp_path)
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("overlay_hash_mismatch" in r for r in result.blocked_reasons)


def test_ready_mode_does_not_call_runtime_executor(tmp_path: Path) -> None:
    """Preflight mode must not call the runtime executor."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    call_count = 0

    def tracking_executor(target_bot: str, overlay_path: str) -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return {"status": "success", "detail": "called"}

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=False,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=tracking_executor,
    )
    assert result.status == "FLEET_CEREMONY_READY"
    assert call_count == 0


def test_ready_mode_writes_preflight_artifacts(tmp_path: Path) -> None:
    """Preflight mode writes preflight ceremony artifacts."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=False,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
    )
    assert result.status == "FLEET_CEREMONY_READY"
    assert len(result.target_results) == 1
    assert result.target_results[0].status == "PREFLIGHT_READY"

    # Check preflight artifact was written
    preflight_path = (
        tmp_path / "change-9c-001" / "targets" / "freqtrade-regime-hybrid"
        / "preflight_ceremony_artifact.json"
    )
    assert preflight_path.exists()
    preflight = json.loads(preflight_path.read_text())
    assert preflight["event"] == "preflight_ceremony_artifact"
    assert preflight["target_bot"] == "freqtrade-regime-hybrid"
    assert preflight["runtime_mutation"] == "NONE"


def test_execute_blocks_without_runtime_executor(tmp_path: Path) -> None:
    """Block execute_runtime=True when runtime_executor is None."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=None,
    )
    assert result.status == "FLEET_CEREMONY_BLOCKED"
    assert any("runtime_executor_required" in r for r in result.blocked_reasons)


def test_execute_green_single_target(tmp_path: Path) -> None:
    """Execute ceremony with a single target — green path."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"
    assert len(result.target_results) == 1
    assert result.target_results[0].status == "EXECUTED_GREEN"
    assert result.target_results[0].target_bot == "freqtrade-regime-hybrid"


def test_execute_green_multiple_targets(tmp_path: Path) -> None:
    """Execute ceremony with multiple targets — all green."""
    overlay_path1, overlay_sha1 = _make_overlay(tmp_path)
    overlay_path2, overlay_sha2 = _make_overlay(tmp_path)

    target_plan1 = _make_target_plan(
        tmp_path,
        target_bot="freqtrade-regime-hybrid",
        overlay_path=overlay_path1,
        overlay_sha256=overlay_sha1,
    )
    target_plan2 = _make_target_plan(
        tmp_path,
        target_bot="freqai-rebel",
        overlay_path=overlay_path2,
        overlay_sha256=overlay_sha2,
    )

    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        selected_targets=["freqtrade-regime-hybrid", "freqai-rebel"],
        target_plans=[target_plan1, target_plan2],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"
    assert len(result.target_results) == 2
    assert all(r.status == "EXECUTED_GREEN" for r in result.target_results)


def test_execute_yellow_on_partial_target_failure(tmp_path: Path) -> None:
    """Partial target failure yields YELLOW, not silent GREEN."""
    overlay_path1, overlay_sha1 = _make_overlay(tmp_path)
    overlay_path2, overlay_sha2 = _make_overlay(tmp_path)

    target_plan1 = _make_target_plan(
        tmp_path,
        target_bot="freqtrade-regime-hybrid",
        overlay_path=overlay_path1,
        overlay_sha256=overlay_sha1,
    )
    target_plan2 = _make_target_plan(
        tmp_path,
        target_bot="freqai-rebel",
        overlay_path=overlay_path2,
        overlay_sha256=overlay_sha2,
    )

    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        selected_targets=["freqtrade-regime-hybrid", "freqai-rebel"],
        target_plans=[target_plan1, target_plan2],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_failing_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_YELLOW"
    assert len(result.target_results) == 2
    assert all(r.status == "EXECUTED_YELLOW" for r in result.target_results)
    assert any("runtime_executor failed" in r for r in result.blocked_reasons), (
        f"Expected 'runtime_executor failed' in blocked_reasons, got: "
        f"{result.blocked_reasons}"
    )


def test_audit_event_written(tmp_path: Path) -> None:
    """Audit event is written during execution."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"

    audit_path = (
        tmp_path / "change-9c-001" / "targets" / "freqtrade-regime-hybrid"
        / "runtime_apply_audit.json"
    )
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "runtime_apply_audit"
    assert audit["target_bot"] == "freqtrade-regime-hybrid"
    assert audit["runtime_mutation"] == "NONE"


def test_runtime_effect_proof_written(tmp_path: Path) -> None:
    """RuntimeEffectProof is written during execution."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"

    proof_path = (
        tmp_path / "change-9c-001" / "targets" / "freqtrade-regime-hybrid"
        / "runtime_effect_proof.json"
    )
    assert proof_path.exists()
    proof = json.loads(proof_path.read_text())
    assert proof["event"] == "runtime_effect_proof"
    assert proof["target_bot"] == "freqtrade-regime-hybrid"
    assert proof["ceremony_status"] == "EXECUTED"
    assert proof["runtime_mutation"] == "NONE"


def test_measurement_start_record_written(tmp_path: Path) -> None:
    """Measurement start record is written during execution."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"

    ms_path = (
        tmp_path / "change-9c-001" / "targets" / "freqtrade-regime-hybrid"
        / "measurement_start_record.json"
    )
    assert ms_path.exists()
    ms = json.loads(ms_path.read_text())
    assert ms["event"] == "measurement_start_record"
    assert ms["target_bot"] == "freqtrade-regime-hybrid"
    assert ms["ceremony_status"] == "EXECUTED"
    assert ms["runtime_mutation"] == "NONE"


def test_result_serializable(tmp_path: Path) -> None:
    """FleetRuntimeCeremonyResult must be JSON-serializable."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["status"] == "FLEET_CEREMONY_EXECUTED_GREEN"
    assert deserialized["event"] == "fleet_runtime_ceremony_result"


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    d = result.to_dict()
    # Check top-level keys for live-trading indicators
    assert "dry_run" not in str(d.keys())
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    # Check status values — must not reference live trading
    assert "LIVE" not in d["status"]
    # Check target result fields
    for tr in d["target_results"]:
        assert "LIVE" not in tr["status"]
        assert "api_key" not in str(tr.keys())
        assert "secret" not in str(tr.keys())


def test_runtime_mutation_none_until_executor_call(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE until executor is called."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    target_plan = _make_target_plan(
        tmp_path,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
    )
    plan_path = _make_fleet_rollout_plan(
        tmp_path,
        target_plans=[target_plan],
    )

    # Preflight mode
    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=False,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
    )
    assert result.status == "FLEET_CEREMONY_READY"
    for tr in result.target_results:
        assert tr.status == "PREFLIGHT_READY"

    # Execute mode
    input_ = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=plan_path,
        execute_runtime=True,
    )
    result = run_fleet_runtime_ceremony(
        input_,
        ceremony_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CEREMONY_EXECUTED_GREEN"
    for tr in result.target_results:
        assert tr.status == "EXECUTED_GREEN"
