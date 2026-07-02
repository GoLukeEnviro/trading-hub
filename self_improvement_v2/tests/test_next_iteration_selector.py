"""Tests for next_iteration_selector.py — Phase 10.6.

All tests use tmp_path, fake decision packs, fake rollback results —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.rollout.next_iteration_selector import (
    NextIterationSelectorInput,
    run_next_iteration_selector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_keep_decision_pack(
    tmp_path: Path,
    *,
    change_id: str = "keep-change-001",
    candidate_id: str = "keep-candidate-001",
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
) -> str:
    """Write a synthetic KEEP_FLEET_OVERLAY decision pack."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "post_fleet_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": "KEEP_FLEET_OVERLAY",
        "status": "FINAL_DECISION_EMITTED",
        "runtime_mutation": runtime_mutation,
        "created_at_utc": "2026-07-01T12:00:00Z",
    }
    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
    return str(path)


def _make_rollback_decision_pack(
    tmp_path: Path,
    *,
    change_id: str = "rollback-change-001",
    candidate_id: str = "rollback-candidate-001",
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
) -> str:
    """Write a synthetic ROLLBACK_FLEET_OVERLAY decision pack."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "post_fleet_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": "ROLLBACK_FLEET_OVERLAY",
        "status": "FINAL_DECISION_EMITTED",
        "runtime_mutation": runtime_mutation,
        "created_at_utc": "2026-07-01T12:00:00Z",
    }
    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
    return str(path)


def _make_extend_decision_pack(
    tmp_path: Path,
    *,
    change_id: str = "extend-change-001",
    candidate_id: str = "extend-candidate-001",
    target_bot: str = "freqtrade-regime-hybrid",
) -> str:
    """Write a synthetic EXTEND_MEASUREMENT decision pack."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "post_fleet_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": "EXTEND_MEASUREMENT",
        "status": "FINAL_DECISION_EMITTED",
        "runtime_mutation": "NONE",
        "created_at_utc": "2026-07-01T12:00:00Z",
    }
    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
    return str(path)


def _make_rollback_result(
    tmp_path: Path,
    *,
    status: str = "DRY_RUN_ROLLBACK_GREEN",
    change_id: str = "rollback-change-001",
    candidate_id: str = "rollback-candidate-001",
    target_bot: str = "freqtrade-regime-hybrid",
    runtime_mutation: str = "NONE",
) -> str:
    """Write a synthetic rollback executor result."""
    global _serial
    _serial += 1
    result: dict[str, object] = {
        "event": "dry_run_rollback_executor_result",
        "status": status,
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "rollback_audit_path": "/tmp/audit.json",
        "rollback_effect_proof_path": "/tmp/proof.json",
        "post_rollback_measurement_start_path": "/tmp/measurement.json",
        "runtime_mutation": runtime_mutation,
    }
    path = tmp_path / f"rollback_result_{_serial}.json"
    path.write_text(json.dumps(result))
    return str(path)


def _default_input(
    tmp_path: Path,
    *,
    decision_pack_path: str | None = None,
    rollback_result_path: str | None = None,
    active_measurement_candidate_id: str | None = None,
    previous_candidate_ids: tuple[str, ...] = (),
) -> NextIterationSelectorInput:
    """Build a default selector input for testing."""
    if decision_pack_path is None:
        decision_pack_path = _make_keep_decision_pack(tmp_path)
    return NextIterationSelectorInput(
        decision_pack_path=decision_pack_path,
        rollback_result_path=rollback_result_path,
        active_measurement_candidate_id=active_measurement_candidate_id,
        previous_candidate_ids=previous_candidate_ids,
    )


# ---------------------------------------------------------------------------
# Tests: KEEP path
# ---------------------------------------------------------------------------


def test_keep_selects_next_iteration(tmp_path: Path) -> None:
    """KEEP decision pack selects next iteration."""
    input_ = _default_input(tmp_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    assert result.source_decision == "KEEP_FLEET_OVERLAY"
    assert result.next_candidate_id
    assert result.next_target_bot
    assert len(result.blocked_reasons) == 0


def test_keep_selects_non_current_target(tmp_path: Path) -> None:
    """KEEP selects a different target bot than the current one."""
    pack_path = _make_keep_decision_pack(
        tmp_path, target_bot="freqtrade-regime-hybrid",
    )
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    # Should not select the same target
    assert result.next_target_bot != "freqtrade-regime-hybrid"
    # Should select a valid fleet bot
    assert result.next_target_bot in (
        "freqtrade-freqforge",
        "freqtrade-freqforge-canary",
        "freqtrade-regime-hybrid",
        "freqai-rebel",
    )


# ---------------------------------------------------------------------------
# Tests: ROLLBACK path
# ---------------------------------------------------------------------------


def test_rollback_with_green_result_selects_next(tmp_path: Path) -> None:
    """ROLLBACK with GREEN rollback result selects next iteration."""
    pack_path = _make_rollback_decision_pack(tmp_path)
    rollback_path = _make_rollback_result(tmp_path, status="DRY_RUN_ROLLBACK_GREEN")
    input_ = _default_input(
        tmp_path,
        decision_pack_path=pack_path,
        rollback_result_path=rollback_path,
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    assert result.source_decision == "ROLLBACK_FLEET_OVERLAY"


def test_rollback_without_result_blocks(tmp_path: Path) -> None:
    """ROLLBACK without rollback result blocks selection."""
    pack_path = _make_rollback_decision_pack(tmp_path)
    input_ = _default_input(
        tmp_path, decision_pack_path=pack_path,
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("rollback_required" in r for r in result.blocked_reasons)


def test_rollback_with_yellow_result_blocks(tmp_path: Path) -> None:
    """ROLLBACK with YELLOW rollback result blocks selection."""
    pack_path = _make_rollback_decision_pack(tmp_path)
    rollback_path = _make_rollback_result(
        tmp_path, status="DRY_RUN_ROLLBACK_YELLOW",
    )
    input_ = _default_input(
        tmp_path,
        decision_pack_path=pack_path,
        rollback_result_path=rollback_path,
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("rollback_yellow" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: EXTEND blocks
# ---------------------------------------------------------------------------


def test_extend_blocks_selection(tmp_path: Path) -> None:
    """EXTEND_MEASUREMENT blocks selection."""
    pack_path = _make_extend_decision_pack(tmp_path)
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_DEFERRED"
    assert any("extend_measurement_active" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Active measurement window
# ---------------------------------------------------------------------------


def test_blocks_active_measurement_window(tmp_path: Path) -> None:
    """Active measurement window blocks selection."""
    input_ = _default_input(
        tmp_path,
        active_measurement_candidate_id="some-active-candidate",
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_DEFERRED"
    assert any("active_measurement_window" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Duplicate candidate avoidance
# ---------------------------------------------------------------------------


def test_blocks_duplicate_candidate(tmp_path: Path) -> None:
    """Previously selected candidate blocks selection."""
    input_ = _default_input(
        tmp_path,
        previous_candidate_ids=("keep-candidate-001",),
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("duplicate_candidate" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing/invalid decision pack
# ---------------------------------------------------------------------------


def test_blocks_missing_decision_pack(tmp_path: Path) -> None:
    """Missing decision pack blocks selection."""
    input_ = _default_input(
        tmp_path,
        decision_pack_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("decision_pack_not_readable" in r for r in result.blocked_reasons)


def test_blocks_invalid_decision_pack(tmp_path: Path) -> None:
    """Invalid decision pack blocks selection."""
    path = tmp_path / "bad_pack.json"
    path.write_text(json.dumps({"event": "wrong_event"}))
    input_ = _default_input(
        tmp_path, decision_pack_path=str(path),
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"


def test_blocks_decision_pack_with_runtime_mutation(tmp_path: Path) -> None:
    """Decision pack with runtime_mutation != NONE blocks selection."""
    pack_path = _make_keep_decision_pack(
        tmp_path, runtime_mutation="MUTATED",
    )
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("runtime_mutation_not_none" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing/invalid rollback result
# ---------------------------------------------------------------------------


def test_blocks_missing_rollback_result(tmp_path: Path) -> None:
    """Missing rollback result blocks selection."""
    pack_path = _make_rollback_decision_pack(tmp_path)
    input_ = _default_input(
        tmp_path,
        decision_pack_path=pack_path,
        rollback_result_path=str(tmp_path / "nonexistent.json"),
    )
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_BLOCKED"
    assert any("rollback_result_not_readable" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_selection_plan(tmp_path: Path) -> None:
    """Selector writes a selection plan artifact."""
    input_ = _default_input(tmp_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    assert result.selection_plan_path
    plan_path = Path(result.selection_plan_path)
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["event"] == "next_iteration_selection_plan"
    assert plan["status"] == "NEXT_ITERATION_SELECTED"
    assert plan["runtime_mutation"] == "NONE"


def test_writes_blocked_plan(tmp_path: Path) -> None:
    """Blocked selector still writes a plan artifact."""
    pack_path = _make_extend_decision_pack(tmp_path)
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.selection_plan_path
    plan_path = Path(result.selection_plan_path)
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["event"] == "next_iteration_selection_plan"
    assert plan["status"] == "NEXT_ITERATION_DEFERRED"
    assert plan["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """NextIterationSelectionPlan must be JSON-serializable."""
    input_ = _default_input(tmp_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "next_iteration_selection_plan"
    assert deserialized["status"] == "NEXT_ITERATION_SELECTED"


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    input_ = _default_input(tmp_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
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
    input_ = _default_input(tmp_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"

    plan = json.loads(Path(result.selection_plan_path).read_text())
    assert plan["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Target selection logic
# ---------------------------------------------------------------------------


def test_selects_regime_hybrid_when_current_is_rebel(tmp_path: Path) -> None:
    """Selects regime-hybrid when current target is freqai-rebel."""
    pack_path = _make_keep_decision_pack(
        tmp_path, target_bot="freqai-rebel",
    )
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    assert result.next_target_bot == "freqtrade-regime-hybrid"


def test_selects_rebel_when_current_is_regime_hybrid(tmp_path: Path) -> None:
    """Selects freqai-rebel when current target is regime-hybrid."""
    pack_path = _make_keep_decision_pack(
        tmp_path, target_bot="freqtrade-regime-hybrid",
    )
    input_ = _default_input(tmp_path, decision_pack_path=pack_path)
    result = run_next_iteration_selector(
        input_, selector_output_dir=tmp_path,
    )
    assert result.status == "NEXT_ITERATION_SELECTED"
    assert result.next_target_bot == "freqai-rebel"
