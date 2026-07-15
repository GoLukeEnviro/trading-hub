"""Phase 1D tests — Kill switch safety state + actions (Issue #598).

Extends existing kill_switch.py tests with v2 schema tests.
All existing tests must continue to pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Path setup — same as test_kill_switch.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_DIR = _REPO_ROOT / "freqtrade" / "shared"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SHARED_DIR))

from freqtrade.shared.kill_switch import (  # noqa: E402
    ACTION_CANCEL_ALL_PENDING,
    ACTION_CANCEL_PENDING_ENTRIES,
    ACTION_REQUEST_CONTROLLED_UNWIND,
    ACTION_STATE_ATTEMPTED,
    ACTION_STATE_CONFIRMED,
    ACTION_STATE_FAILED,
    ACTION_STATE_REQUESTED,
    MODE_EMERGENCY,
    MODE_HALT_NEW,
    MODE_NORMAL,
    SAFETY_EMERGENCY,
    SAFETY_HALT_NEW,
    SAFETY_NORMAL,
    SAFETY_REDUCE_ONLY,
    clear_kill_switch,
    get_actions,
    get_effective_safety_state,
    get_kill_mode,
    get_safety_state,
    is_action_attempted,
    is_action_confirmed,
    is_emergency,
    is_kill_active,
    is_reduce_only,
    load_kill_state,
    record_action,
    set_kill_mode,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_state_file(tmp_path: Path) -> Path:
    return tmp_path / "kill_switch.json"


@pytest.fixture
def normal_v1(tmp_state_file: Path) -> Path:
    tmp_state_file.write_text(
        json.dumps({"mode": "NORMAL", "reason": "", "triggered_at": "", "triggered_by": ""})
    )
    return tmp_state_file


@pytest.fixture
def halt_v1(tmp_state_file: Path) -> Path:
    tmp_state_file.write_text(
        json.dumps({"mode": "HALT_NEW", "reason": "test", "triggered_at": "2026-01-01T00:00:00Z",
                     "triggered_by": "tester"})
    )
    return tmp_state_file


# ---------------------------------------------------------------------------
# V2 schema
# ---------------------------------------------------------------------------


class TestSchemaV2:
    def test_load_v1_file_normal(self, normal_v1: Path) -> None:
        state = load_kill_state(normal_v1)
        assert state["version"] == 2
        assert state["safety_state"] == "NORMAL"
        assert state["mode"] == "NORMAL"  # backward compat
        assert state["actions"] == {}

    def test_load_v1_file_halt(self, halt_v1: Path) -> None:
        state = load_kill_state(halt_v1)
        assert state["version"] == 2
        assert state["safety_state"] == "HALT_NEW"

    def test_set_kill_mode_produces_v2(self, tmp_state_file: Path) -> None:
        set_kill_mode("HALT_NEW", reason="t", triggered_by="t", path=tmp_state_file)
        raw = json.loads(tmp_state_file.read_text())
        assert raw["version"] == 2
        assert raw["safety_state"] == "HALT_NEW"
        assert raw["mode"] == "HALT_NEW"

    def test_unknown_mode_fail_closed(self, tmp_state_file: Path) -> None:
        tmp_state_file.write_text('{"mode": "BOGUS", "reason": ""}')
        state = load_kill_state(tmp_state_file)
        # fail-closed: unknown mode → HALT_NEW
        assert state["safety_state"] in ("HALT_NEW",)
        assert is_kill_active(tmp_state_file)


# ---------------------------------------------------------------------------
# REDUCE_ONLY
# ---------------------------------------------------------------------------


class TestReduceOnly:
    def test_set_reduce_only(self, tmp_state_file: Path) -> None:
        set_kill_mode(SAFETY_REDUCE_ONLY, reason="r", triggered_by="t", path=tmp_state_file)
        assert get_kill_mode(tmp_state_file) == SAFETY_REDUCE_ONLY
        assert is_kill_active(tmp_state_file) is True
        assert is_emergency(tmp_state_file) is False
        assert is_reduce_only(tmp_state_file) is True

    def test_reduce_only_blocks_entries(self, tmp_state_file: Path) -> None:
        set_kill_mode(SAFETY_REDUCE_ONLY, reason="r", triggered_by="t", path=tmp_state_file)
        assert is_kill_active(tmp_state_file) is True

    def test_reduce_only_is_not_emergency(self, tmp_state_file: Path) -> None:
        set_kill_mode(SAFETY_REDUCE_ONLY, reason="r", triggered_by="t", path=tmp_state_file)
        assert is_emergency(tmp_state_file) is False

    def test_clear_from_reduce_only(self, tmp_state_file: Path) -> None:
        set_kill_mode(SAFETY_REDUCE_ONLY, reason="r", triggered_by="t", path=tmp_state_file)
        clear_kill_switch(triggered_by="op", path=tmp_state_file)
        assert get_kill_mode(tmp_state_file) == MODE_NORMAL


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_emergency_wins_over_all(self) -> None:
        assert get_effective_safety_state(SAFETY_NORMAL, SAFETY_EMERGENCY, SAFETY_HALT_NEW) == SAFETY_EMERGENCY

    def test_halt_new_wins_over_reduce_only(self) -> None:
        assert get_effective_safety_state(SAFETY_REDUCE_ONLY, SAFETY_HALT_NEW) == SAFETY_HALT_NEW

    def test_reduce_only_wins_over_normal(self) -> None:
        assert get_effective_safety_state(SAFETY_NORMAL, SAFETY_REDUCE_ONLY) == SAFETY_REDUCE_ONLY

    def test_normal_only_when_all_normal(self) -> None:
        assert get_effective_safety_state(SAFETY_NORMAL, SAFETY_NORMAL) == SAFETY_NORMAL

    def test_unknown_mode_treated_as_halt_new_level(self) -> None:
        # unknown state → HALT_NEW level (fail-closed)
        result = get_effective_safety_state(SAFETY_NORMAL, "BOGUS")
        assert result == "BOGUS"  # returned as-is
        # but the precedence is treated at HALT_NEW level
        result2 = get_effective_safety_state(SAFETY_EMERGENCY, "BOGUS")
        assert result2 == SAFETY_EMERGENCY  # EMERGENCY still wins


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class TestActions:
    def test_record_cancel_pending_requested(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        record_action(ACTION_CANCEL_PENDING_ENTRIES, ACTION_STATE_REQUESTED,
                      triggered_by="guard", reason="drawdown", path=tmp_state_file)
        actions = get_actions(tmp_state_file)
        assert ACTION_CANCEL_PENDING_ENTRIES in actions
        assert actions[ACTION_CANCEL_PENDING_ENTRIES]["state"] == "requested"
        assert actions[ACTION_CANCEL_PENDING_ENTRIES]["requested_by"] == "guard"

    def test_action_lifecycle(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_EMERGENCY, path=tmp_state_file)
        record_action(ACTION_REQUEST_CONTROLLED_UNWIND, ACTION_STATE_REQUESTED,
                      triggered_by="op", path=tmp_state_file)
        assert not is_action_attempted(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)
        record_action(ACTION_REQUEST_CONTROLLED_UNWIND, ACTION_STATE_ATTEMPTED,
                      path=tmp_state_file)
        assert is_action_attempted(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)
        assert not is_action_confirmed(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)
        record_action(ACTION_REQUEST_CONTROLLED_UNWIND, ACTION_STATE_CONFIRMED,
                      path=tmp_state_file)
        assert is_action_confirmed(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)

    def test_action_idempotent_confirmed(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_REQUESTED, path=tmp_state_file)
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_ATTEMPTED, path=tmp_state_file)
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_CONFIRMED, path=tmp_state_file)
        # re-confirm is no-op
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_CONFIRMED, path=tmp_state_file)
        assert is_action_confirmed(ACTION_CANCEL_ALL_PENDING, tmp_state_file)

    def test_action_can_fail(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_REQUESTED, path=tmp_state_file)
        record_action(ACTION_CANCEL_ALL_PENDING, ACTION_STATE_FAILED, reason="timeout",
                      path=tmp_state_file)
        actions = get_actions(tmp_state_file)
        assert actions[ACTION_CANCEL_ALL_PENDING]["state"] == "failed"
        assert "timeout" in actions[ACTION_CANCEL_ALL_PENDING]["reason"]

    def test_exit_intent_not_confirmed_closure(self, tmp_state_file: Path) -> None:
        """REQUEST_CONTROLLED_UNWIND requested is NOT confirmed execution."""
        set_kill_mode(MODE_EMERGENCY, path=tmp_state_file)
        record_action(ACTION_REQUEST_CONTROLLED_UNWIND, ACTION_STATE_REQUESTED,
                      triggered_by="guard", path=tmp_state_file)
        assert not is_action_confirmed(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)
        assert not is_action_attempted(ACTION_REQUEST_CONTROLLED_UNWIND, tmp_state_file)

    def test_invalid_action_raises(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        with pytest.raises(ValueError):
            record_action("LIQUIDATE_ALL", ACTION_STATE_REQUESTED, path=tmp_state_file)

    def test_invalid_action_state_raises(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        with pytest.raises(ValueError):
            record_action(ACTION_CANCEL_PENDING_ENTRIES, "executing", path=tmp_state_file)

    def test_actions_survive_mode_change(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        record_action(ACTION_CANCEL_PENDING_ENTRIES, ACTION_STATE_REQUESTED,
                      triggered_by="g", path=tmp_state_file)
        set_kill_mode(MODE_NORMAL, path=tmp_state_file)
        actions = get_actions(tmp_state_file)
        assert ACTION_CANCEL_PENDING_ENTRIES in actions

    def test_multiple_actions_coexist(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_EMERGENCY, path=tmp_state_file)
        record_action(ACTION_CANCEL_PENDING_ENTRIES, ACTION_STATE_REQUESTED, path=tmp_state_file)
        record_action(ACTION_REQUEST_CONTROLLED_UNWIND, ACTION_STATE_REQUESTED, path=tmp_state_file)
        actions = get_actions(tmp_state_file)
        assert len(actions) == 2


# ---------------------------------------------------------------------------
# Concurrency / atomic
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_action_atomic_write(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_HALT_NEW, path=tmp_state_file)
        record_action(ACTION_CANCEL_PENDING_ENTRIES, ACTION_STATE_REQUESTED,
                      path=tmp_state_file)
        assert not tmp_state_file.with_suffix(".tmp").exists()


# ---------------------------------------------------------------------------
# get_safety_state
# ---------------------------------------------------------------------------


class TestGetSafetyState:
    def test_returns_v2_primary_field(self, tmp_state_file: Path) -> None:
        set_kill_mode(MODE_EMERGENCY, path=tmp_state_file)
        assert get_safety_state(tmp_state_file) == MODE_EMERGENCY

    def test_falls_back_to_mode_for_v1(self, normal_v1: Path) -> None:
        assert get_safety_state(normal_v1) == MODE_NORMAL
