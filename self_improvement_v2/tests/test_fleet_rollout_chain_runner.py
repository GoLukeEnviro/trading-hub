"""Tests for fleet_rollout_chain_runner.py — Phase 10.

All tests use tmp_path, fake decision packs, fake overlays, fake target
runtime specs, and fake runtime executors — no real runtime, no API, no Docker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from si_v2.rollout.fleet_rollout_artifact_planner import (
    TargetBotRuntimeSpec,
)
from si_v2.rollout.fleet_rollout_chain_runner import (
    FleetRolloutChainInput,
    maybe_run_fleet_rollout_chain_from_active_cycle,
    run_fleet_rollout_chain,
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
    change_id: str = "change-10-001",
    candidate_id: str = "candidate-10-001",
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
    """Return the standard 4-bot fleet config."""
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
    execute_fleet_runtime: bool = False,
    change_id: str = "change-10-001",
) -> FleetRolloutChainInput:
    """Build a default chain input for testing."""
    if decision_pack_path is None:
        decision_pack_path = _make_decision_pack(tmp_path, change_id=change_id)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    return FleetRolloutChainInput(
        decision_pack_path=decision_pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT, FREQAI_REBEL_BOT),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        execute_fleet_runtime=execute_fleet_runtime,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chain_blocks_missing_decision_pack(tmp_path: Path) -> None:
    """Block when the decision pack file does not exist."""
    input_ = FleetRolloutChainInput(
        decision_pack_path=str(tmp_path / "nonexistent.json"),
        fleet_bots=(),
        allowed_target_bots=(),
        target_runtime_specs=(),
        source_overlay_path="",
        source_overlay_sha256="",
        expected_parameter="",
        expected_value=0,
    )
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_BLOCKED"
    assert any("decision_pack_not_readable" in r for r in result.blocked_reasons)


def test_chain_not_eligible_when_policy_not_eligible(tmp_path: Path) -> None:
    """Chain returns NOT_ELIGIBLE when policy finds no eligible targets."""
    # Use a decision pack with EXTEND_MEASUREMENT
    pack_path = _make_decision_pack(
        tmp_path, decision="EXTEND_MEASUREMENT",
    )
    input_ = _default_chain_input(tmp_path, decision_pack_path=pack_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_NOT_ELIGIBLE"
    assert result.policy_status == "PROMOTION_EXTEND_MEASUREMENT"


def test_chain_blocks_when_policy_blocked(tmp_path: Path) -> None:
    """Chain blocks when policy is blocked."""
    # Use a decision pack with ROLLBACK decision
    pack_path = _make_decision_pack(
        tmp_path, decision="ROLLBACK_CANARY_OVERLAY",
    )
    input_ = _default_chain_input(tmp_path, decision_pack_path=pack_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_BLOCKED"
    assert result.policy_status == "PROMOTION_BLOCKED"


def test_chain_blocks_when_planner_blocked(tmp_path: Path) -> None:
    """Chain blocks when planner cannot generate plans."""
    # Use a valid decision pack but no runtime specs (planner will fail)
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    input_ = FleetRolloutChainInput(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=(),  # Empty — planner will find no matching specs
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
    )
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_BLOCKED"
    assert result.policy_status == "PROMOTION_ELIGIBLE"
    assert result.planner_status != "ROLLOUT_PLAN_READY"


def test_chain_ready_without_runtime_execution(tmp_path: Path) -> None:
    """Default path (execute_fleet_runtime=False) yields READY."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_READY"
    assert result.policy_status == "PROMOTION_ELIGIBLE"
    assert result.planner_status == "ROLLOUT_PLAN_READY"
    assert result.ceremony_status == "FLEET_CEREMONY_READY"


def test_chain_ready_does_not_call_runtime_executor(tmp_path: Path) -> None:
    """Preflight mode must not call the runtime executor."""
    input_ = _default_chain_input(tmp_path)

    call_count = 0

    def tracking_executor(target_bot: str, overlay_path: str) -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return {"status": "success", "detail": "called"}

    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=tracking_executor,
    )
    assert result.status == "FLEET_CHAIN_READY"
    assert call_count == 0


def test_chain_execute_blocks_without_runtime_executor(tmp_path: Path) -> None:
    """Block execute_fleet_runtime=True when runtime_executor is None."""
    input_ = _default_chain_input(tmp_path, execute_fleet_runtime=True)
    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=None,
    )
    assert result.status == "FLEET_CHAIN_BLOCKED"
    assert any("runtime_executor_required" in r for r in result.blocked_reasons)


def test_chain_execute_green_calls_runtime_executor(tmp_path: Path) -> None:
    """Execute mode calls runtime executor and returns GREEN."""
    input_ = _default_chain_input(tmp_path, execute_fleet_runtime=True)
    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CHAIN_EXECUTED_GREEN"
    assert result.policy_status == "PROMOTION_ELIGIBLE"
    assert result.planner_status == "ROLLOUT_PLAN_READY"
    assert result.ceremony_status == "FLEET_CEREMONY_EXECUTED_GREEN"


def test_chain_execute_yellow_on_partial_failure(tmp_path: Path) -> None:
    """Partial target failure yields YELLOW."""
    input_ = _default_chain_input(tmp_path, execute_fleet_runtime=True)
    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=_make_failing_executor(),
    )
    assert result.status == "FLEET_CHAIN_EXECUTED_YELLOW"
    assert result.ceremony_status == "FLEET_CEREMONY_EXECUTED_YELLOW"


def test_chain_writes_policy_artifact(tmp_path: Path) -> None:
    """Chain writes the rollout policy artifact."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_READY"
    policy_path = Path(result.rollout_policy_path)
    assert policy_path.exists()
    policy = json.loads(policy_path.read_text())
    assert policy["event"] == "fleet_rollout_policy_decision"
    assert policy["status"] == "PROMOTION_ELIGIBLE"


def test_chain_writes_rollout_plan_artifact(tmp_path: Path) -> None:
    """Chain writes the fleet rollout plan artifact."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_READY"
    plan_path = Path(result.rollout_plan_path)
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["event"] == "fleet_rollout_artifact_plan"
    assert plan["status"] == "ROLLOUT_PLAN_READY"


def test_chain_writes_ceremony_artifacts(tmp_path: Path) -> None:
    """Chain writes ceremony artifacts (preflight)."""
    input_ = _default_chain_input(tmp_path, execute_fleet_runtime=True)
    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    assert result.status == "FLEET_CHAIN_EXECUTED_GREEN"

    # Check ceremony artifacts exist
    ceremony_dir = (
        tmp_path / "change-10-001" / "ceremony"
        / "change-10-001" / "targets" / REGIME_HYBRID_BOT
    )
    assert (ceremony_dir / "pre_apply_snapshot.json").exists()
    assert (ceremony_dir / "runtime_apply_audit.json").exists()
    assert (ceremony_dir / "runtime_effect_proof.json").exists()
    assert (ceremony_dir / "measurement_start_record.json").exists()


def test_chain_writes_chain_audit(tmp_path: Path) -> None:
    """Chain writes the chain audit artifact."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    assert result.status == "FLEET_CHAIN_READY"
    audit_path = Path(result.chain_audit_path)
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "fleet_rollout_chain_audit"
    assert audit["status"] == "FLEET_CHAIN_READY"
    assert audit["runtime_mutation"] == "NONE"


def test_chain_audit_runtime_mutation_none(tmp_path: Path) -> None:
    """Chain audit must always have runtime_mutation=NONE."""
    # Preflight mode
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    audit = json.loads(Path(result.chain_audit_path).read_text())
    assert audit["runtime_mutation"] == "NONE"

    # Execute mode
    input_ = _default_chain_input(tmp_path, execute_fleet_runtime=True)
    result = run_fleet_rollout_chain(
        input_,
        chain_output_dir=tmp_path,
        runtime_executor=_make_runtime_executor(),
    )
    audit = json.loads(Path(result.chain_audit_path).read_text())
    assert audit["runtime_mutation"] == "NONE"


def test_chain_result_serializable(tmp_path: Path) -> None:
    """FleetRolloutChainResult must be JSON-serializable."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["status"] == "FLEET_CHAIN_READY"
    assert deserialized["event"] == "fleet_rollout_chain_result"


def test_active_cycle_hook_default_disabled(tmp_path: Path) -> None:
    """Active cycle hook returns None when disabled."""
    result = maybe_run_fleet_rollout_chain_from_active_cycle(
        decision_pack_path="",
        fleet_bots=(),
        allowed_target_bots=(),
        target_runtime_specs=(),
        source_overlay_path="",
        source_overlay_sha256="",
        expected_parameter="",
        expected_value=0,
        fleet_rollout_chain_enabled=False,
    )
    assert result is None


def test_active_cycle_hook_enabled_invokes_chain_runner(tmp_path: Path) -> None:
    """Active cycle hook invokes chain runner when enabled."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)

    result = maybe_run_fleet_rollout_chain_from_active_cycle(
        decision_pack_path=pack_path,
        fleet_bots=_make_default_fleet(),
        allowed_target_bots=(REGIME_HYBRID_BOT,),
        target_runtime_specs=_make_runtime_specs(),
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha,
        expected_parameter="max_open_trades",
        expected_value=2,
        fleet_rollout_chain_enabled=True,
        chain_output_dir=tmp_path,
    )
    assert result is not None
    assert result.status in (
        "FLEET_CHAIN_READY",
        "FLEET_CHAIN_BLOCKED",
        "FLEET_CHAIN_NOT_ELIGIBLE",
    )


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    input_ = _default_chain_input(tmp_path)
    result = run_fleet_rollout_chain(input_, chain_output_dir=tmp_path)
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "LIVE" not in d["status"]
