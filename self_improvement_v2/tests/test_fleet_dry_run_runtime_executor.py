"""Tests for fleet_dry_run_runtime_executor.py — Phase 10.3.

All tests use tmp_path, fake decision packs, fake overlays, fake target
runtime specs, and fake runtime executors — no real runtime, no API, no Docker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from si_v2.rollout.fleet_dry_run_runtime_executor import (
    DryRunRuntimeExecutorInput,
    run_dry_run_fleet_runtime_executor,
)
from si_v2.rollout.fleet_rollout_artifact_planner import (
    TargetBotRuntimeSpec,
)
from si_v2.rollout.fleet_rollout_chain_runner import (
    FleetRolloutChainInput,
)
from si_v2.rollout.fleet_rollout_policy import (
    CANARY_BOT,
    CONTROL_BOT,
    FREQAI_REBEL_BOT,
    REGIME_HYBRID_BOT,
    FleetBot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_decision_pack(
    tmp_path: Path,
    *,
    decision: str = "KEEP_CANARY_OVERLAY",
    status: str = "FINAL_DECISION_EMITTED",
    target_bot: str = CANARY_BOT,
    runtime_mutation: str = "NONE",
    change_id: str = "change-10-003",
    candidate_id: str = "candidate-10-003",
    stat_rec: str | None = "STAT_KEEP",
    stat_grade: str | None = "MODERATE",
    stat_conflict_severity: str = "NONE",
    stat_conflict_has: bool = False,
    stat_ready: bool = True,
) -> str:
    """Write a synthetic decision pack with a unique filename."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "autonomous_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": decision,
        "status": status,
        "runtime_mutation": runtime_mutation,
    }

    stat_conflict: dict[str, object] = {
        "has_conflict": stat_conflict_has,
        "severity": stat_conflict_severity,
        "simple_decision": decision,
        "stat_recommendation": stat_rec,
        "reason": "",
    }
    pack["statistical_conflict"] = stat_conflict

    if stat_rec is not None:
        stat_ev: dict[str, object] = {
            "status": "STAT_READY" if stat_ready else "STAT_INSUFFICIENT",
            "recommendation": stat_rec,
            "evidence_grade": stat_grade or "MODERATE",
            "canary_mean_profit": 0.3,
            "control_mean_profit": 0.1,
            "mean_profit_diff": 0.2,
        }
        pack["statistical_evidence"] = stat_ev
    else:
        pack["statistical_evidence"] = None

    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
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


def _make_default_fleet() -> tuple[FleetBot, ...]:
    """Return the standard 4-bot fleet config (all dry-run)."""
    return (
        FleetBot(bot_id=CANARY_BOT, role="canary",
                 dry_run=True, allow_rollout_target=False),
        FleetBot(bot_id=CONTROL_BOT, role="control",
                 dry_run=True, allow_rollout_target=True),
        FleetBot(bot_id=REGIME_HYBRID_BOT, role="experimental",
                 dry_run=True, allow_rollout_target=True),
        FleetBot(bot_id=FREQAI_REBEL_BOT, role="freqai",
                 dry_run=True, allow_rollout_target=True),
    )


def _make_fleet_with_live_bot() -> tuple[FleetBot, ...]:
    """Return a fleet with one live (non-dry-run) bot."""
    return (
        FleetBot(bot_id=CANARY_BOT, role="canary",
                 dry_run=True, allow_rollout_target=False),
        FleetBot(bot_id=CONTROL_BOT, role="control",
                 dry_run=True, allow_rollout_target=True),
        FleetBot(bot_id=REGIME_HYBRID_BOT, role="experimental",
                 dry_run=False, allow_rollout_target=True),
        FleetBot(bot_id=FREQAI_REBEL_BOT, role="freqai",
                 dry_run=True, allow_rollout_target=True),
    )


def _make_runtime_specs() -> tuple[TargetBotRuntimeSpec, ...]:
    """Return default target runtime specs."""
    return (
        TargetBotRuntimeSpec(
            bot_id=REGIME_HYBRID_BOT,
            role="experimental",
            dry_run=True,
            config_path="/freqtrade/user_data/config.json",
            user_data_dir="/freqtrade/user_data",
            current_command=(
                "freqtrade", "trade",
                "--config", "/freqtrade/user_data/config.json",
            ),
        ),
        TargetBotRuntimeSpec(
            bot_id=FREQAI_REBEL_BOT,
            role="freqai",
            dry_run=True,
            config_path="/freqai/user_data/config.json",
            user_data_dir="/freqai/user_data",
            current_command=(
                "freqtrade", "trade",
                "--config", "/freqai/user_data/config.json",
            ),
        ),
    )


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


def _default_chain_input(
    tmp_path: Path,
    *,
    decision_pack_path: str | None = None,
    change_id: str = "change-10-003",
    allowed_target_bots: tuple[str, ...] | None = None,
) -> FleetRolloutChainInput:
    """Build a default chain input for testing."""
    if decision_pack_path is None:
        decision_pack_path = _make_decision_pack(tmp_path, change_id=change_id)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    if allowed_target_bots is None:
        allowed_target_bots = (REGIME_HYBRID_BOT,)
    return FleetRolloutChainInput(
        decision_pack_path=decision_pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=allowed_target_bots,
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )


def _default_executor_input(
    tmp_path: Path,
    *,
    chain_input: FleetRolloutChainInput | None = None,
    allowed_targets: tuple[str, ...] | None = None,
    allow_multiple_targets: bool = False,
    require_rollback_plan: bool = True,
) -> DryRunRuntimeExecutorInput:
    """Build a default executor input for testing."""
    if chain_input is None:
        chain_input = _default_chain_input(tmp_path)
    return DryRunRuntimeExecutorInput(
        chain_input=chain_input,
        allowed_targets=allowed_targets,
        allow_multiple_targets=allow_multiple_targets,
        require_rollback_plan=require_rollback_plan,
    )


# ---------------------------------------------------------------------------
# Tests: Safety guards
# ---------------------------------------------------------------------------


def test_refuses_dry_run_false(tmp_path: Path) -> None:
    """Executor refuses when a fleet bot has dry_run=False."""
    fleet = _make_fleet_with_live_bot()
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    pack_path = _make_decision_pack(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=fleet,
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTOR_BLOCKED"
    assert any("dry_run_required" in r for r in result.blocked_reasons)
    assert result.chain_result is None


def test_refuses_non_allowlisted_target(tmp_path: Path) -> None:
    """Executor refuses a target not in the allowlist."""
    # Use a target that is NOT in DEFAULT_ALLOWED_DRY_RUN_TARGETS
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=("non-allowlisted-bot",),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTOR_BLOCKED"
    assert any("target_not_allowlisted" in r for r in result.blocked_reasons)
    assert result.chain_result is None


def test_refuses_multiple_targets_by_default(tmp_path: Path) -> None:
    """Executor refuses multiple targets unless allow_multiple_targets=True."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT, FREQAI_REBEL_BOT),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTOR_BLOCKED"
    assert any("multiple_targets" in r for r in result.blocked_reasons)
    assert result.chain_result is None


def test_allows_multiple_targets_when_configured(tmp_path: Path) -> None:
    """Executor allows multiple targets when allow_multiple_targets=True."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT, FREQAI_REBEL_BOT),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path,
        chain_input=chain_input,
        allow_multiple_targets=True,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"
    assert result.chain_result is not None
    assert result.chain_result.status == "FLEET_CHAIN_EXECUTED_GREEN"


def test_blocks_without_rollback_plan(tmp_path: Path) -> None:
    """Executor blocks when require_rollback_plan=True and no decision pack."""
    # Create a chain input with empty decision_pack_path
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path="",
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTOR_BLOCKED"
    assert any("rollback_plan_required" in r for r in result.blocked_reasons)
    assert result.chain_result is None


def test_blocks_without_rollback_plan_when_disabled(tmp_path: Path) -> None:
    """Executor does NOT block when require_rollback_plan=False."""
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path="",
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path,
        chain_input=chain_input,
        require_rollback_plan=False,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    # Should pass rollback guard but may fail at ceremony level
    # (empty decision_pack_path causes chain to block)
    assert result.status == "DRY_RUN_EXECUTOR_BLOCKED"
    # The block should come from the chain, not the rollback guard
    assert not any("rollback_plan_required" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Successful execution
# ---------------------------------------------------------------------------


def test_executor_green_with_single_target(tmp_path: Path) -> None:
    """Executor returns GREEN for a single allowlisted target."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"
    assert result.chain_result is not None
    assert result.chain_result.status == "FLEET_CHAIN_EXECUTED_GREEN"
    assert result.chain_result.policy_status == "PROMOTION_ELIGIBLE"
    assert result.chain_result.planner_status == "ROLLOUT_PLAN_READY"
    assert result.chain_result.ceremony_status == "FLEET_CEREMONY_EXECUTED_GREEN"


def test_executor_green_with_allowlisted_target(tmp_path: Path) -> None:
    """Executor succeeds with a target in DEFAULT_ALLOWED_DRY_RUN_TARGETS."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(FREQAI_REBEL_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"
    assert result.chain_result is not None
    assert result.chain_result.status == "FLEET_CHAIN_EXECUTED_GREEN"


def test_executor_green_with_custom_allowlist(tmp_path: Path) -> None:
    """Executor succeeds with a custom allowlist."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path,
        chain_input=chain_input,
        allowed_targets=(REGIME_HYBRID_BOT,),
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_executor_writes_pre_apply_snapshot(tmp_path: Path) -> None:
    """Executor writes pre-apply snapshot artifact."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"
    assert result.chain_result is not None

    # Find the ceremony target directory
    chain_dir = tmp_path / "chain"
    ceremony_dir = chain_dir / "change-10-003" / "ceremony"
    target_dir = ceremony_dir / "change-10-003" / "targets" / REGIME_HYBRID_BOT
    snapshot_path = target_dir / "pre_apply_snapshot.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot["event"] == "pre_apply_snapshot"
    assert snapshot["target_bot"] == REGIME_HYBRID_BOT
    assert snapshot["runtime_mutation"] == "NONE"


def test_executor_writes_runtime_apply_audit(tmp_path: Path) -> None:
    """Executor writes runtime apply audit artifact."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"

    chain_dir = tmp_path / "chain"
    ceremony_dir = chain_dir / "change-10-003" / "ceremony"
    target_dir = ceremony_dir / "change-10-003" / "targets" / REGIME_HYBRID_BOT
    audit_path = target_dir / "runtime_apply_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "runtime_apply_audit"
    assert audit["target_bot"] == REGIME_HYBRID_BOT
    assert audit["runtime_mutation"] == "NONE"


def test_executor_writes_runtime_effect_proof(tmp_path: Path) -> None:
    """Executor writes RuntimeEffectProof artifact."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"

    chain_dir = tmp_path / "chain"
    ceremony_dir = chain_dir / "change-10-003" / "ceremony"
    target_dir = ceremony_dir / "change-10-003" / "targets" / REGIME_HYBRID_BOT
    effect_proof_path = target_dir / "runtime_effect_proof.json"
    assert effect_proof_path.exists()
    effect_proof = json.loads(effect_proof_path.read_text())
    assert effect_proof["event"] == "runtime_effect_proof"
    assert effect_proof["target_bot"] == REGIME_HYBRID_BOT
    assert effect_proof["runtime_mutation"] == "NONE"


def test_executor_writes_measurement_start_record(tmp_path: Path) -> None:
    """Executor writes measurement start record artifact."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"

    chain_dir = tmp_path / "chain"
    ceremony_dir = chain_dir / "change-10-003" / "ceremony"
    target_dir = ceremony_dir / "change-10-003" / "targets" / REGIME_HYBRID_BOT
    measurement_path = target_dir / "measurement_start_record.json"
    assert measurement_path.exists()
    measurement = json.loads(measurement_path.read_text())
    assert measurement["event"] == "measurement_start_record"
    assert measurement["target_bot"] == REGIME_HYBRID_BOT
    assert measurement["runtime_mutation"] == "NONE"


def test_executor_writes_executor_audit(tmp_path: Path) -> None:
    """Executor writes its own audit artifact."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"

    audit_path = Path(result.executor_audit_path)
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "dry_run_runtime_executor_audit"
    assert audit["status"] == "DRY_RUN_EXECUTED_GREEN"
    assert audit["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Partial failure
# ---------------------------------------------------------------------------


def test_partial_failure_yields_yellow(tmp_path: Path) -> None:
    """Partial target failure yields YELLOW, not silent GREEN."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    chain_input = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=False,
    )
    executor_input = _default_executor_input(
        tmp_path, chain_input=chain_input,
    )
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_failing_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_YELLOW"
    assert result.chain_result is not None
    assert result.chain_result.status == "FLEET_CHAIN_EXECUTED_YELLOW"
    assert result.chain_result.ceremony_status == "FLEET_CEREMONY_EXECUTED_YELLOW"


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """DryRunRuntimeExecutorResult must be JSON-serializable."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "dry_run_runtime_executor_result"
    assert deserialized["status"] == "DRY_RUN_EXECUTED_GREEN"


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "LIVE" not in d["status"]
    assert result.chain_result is not None
    assert "LIVE" not in result.chain_result.status


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE."""
    executor_input = _default_executor_input(tmp_path)
    result = run_dry_run_fleet_runtime_executor(
        executor_input,
        executor_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "DRY_RUN_EXECUTED_GREEN"

    # Check executor audit
    audit = json.loads(Path(result.executor_audit_path).read_text())
    assert audit["runtime_mutation"] == "NONE"

    # Check chain audit
    assert result.chain_result is not None
    chain_audit = json.loads(Path(result.chain_result.chain_audit_path).read_text())
    assert chain_audit["runtime_mutation"] == "NONE"
