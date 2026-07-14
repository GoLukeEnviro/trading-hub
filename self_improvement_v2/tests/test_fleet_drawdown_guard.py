"""Tests for the fleet drawdown guard (HWM + daily loss)."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from si_v2.risk.fleet_drawdown_guard import (
    DEFAULT_STATE_FILE,
    DrawdownEvaluation,
    DrawdownState,
    FleetDrawdownGuard,
)

D = Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_guard(
    hwm_pct: D | None = None,
    daily_pct: D | None = None,
    state_file: str | Path | None = None,
) -> tuple[FleetDrawdownGuard, Path]:
    """Create a guard with a temporary state file."""
    if hwm_pct is None:
        hwm_pct = D("25.0")
    if daily_pct is None:
        daily_pct = D("10.0")
    if state_file is None:
        fd, path = tempfile.mkstemp(suffix=".json", prefix="drawdown_")
        os.close(fd)
        state_file = path
    guard = FleetDrawdownGuard(
        hwm_drawdown_pct=hwm_pct,
        daily_loss_pct=daily_pct,
        state_file=state_file,
    )
    return guard, Path(state_file)


def _cleanup(path: Path) -> None:
    """Remove temp files."""
    from contextlib import suppress

    with suppress(OSError):
        path.unlink(missing_ok=True)
    with suppress(OSError):
        path.with_suffix(".tmp").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DrawdownState tests
# ---------------------------------------------------------------------------


class TestDrawdownState:
    def test_default_state(self) -> None:
        state = DrawdownState()
        assert state.hwm_equity == D("0")
        assert state.hwm_timestamp == ""
        assert state.day_start_equity == D("0")
        assert state.day_date == ""
        assert state.last_equity == D("0")
        assert state.last_update == ""
        assert state.hwm_breach_triggered is False
        assert state.daily_breach_triggered is False

    def test_round_trip(self) -> None:
        state = DrawdownState(
            hwm_equity=D("100000"),
            hwm_timestamp="2026-07-14T12:00:00+00:00",
            day_start_equity=D("95000"),
            day_date="2026-07-14",
            last_equity=D("94000"),
            last_update="2026-07-14T13:00:00+00:00",
            hwm_breach_triggered=True,
            daily_breach_triggered=False,
        )
        d = state.to_dict()
        restored = DrawdownState.from_dict(d)
        assert restored.hwm_equity == state.hwm_equity
        assert restored.hwm_timestamp == state.hwm_timestamp
        assert restored.day_start_equity == state.day_start_equity
        assert restored.day_date == state.day_date
        assert restored.last_equity == state.last_equity
        assert restored.last_update == state.last_update
        assert restored.hwm_breach_triggered == state.hwm_breach_triggered
        assert restored.daily_breach_triggered == state.daily_breach_triggered

    def test_from_dict_missing_keys(self) -> None:
        state = DrawdownState.from_dict({})
        assert state.hwm_equity == D("0")
        assert state.hwm_breach_triggered is False


# ---------------------------------------------------------------------------
# FleetDrawdownGuard tests
# ---------------------------------------------------------------------------


class TestFleetDrawdownGuardInit:
    def test_default_parameters(self) -> None:
        guard, path = _make_guard()
        try:
            assert guard._hwm_drawdown_pct == D("25.0")
            assert guard._daily_loss_pct == D("10.0")
        finally:
            _cleanup(path)

    def test_custom_parameters(self) -> None:
        guard, path = _make_guard(hwm_pct=D("15.0"), daily_pct=D("5.0"))
        try:
            assert guard._hwm_drawdown_pct == D("15.0")
            assert guard._daily_loss_pct == D("5.0")
        finally:
            _cleanup(path)


class TestFleetDrawdownGuardEvaluate:
    def test_first_tick_initializes_hwm(self) -> None:
        guard, path = _make_guard()
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("100000"), timestamp=ts)

            assert result.triggered is False
            assert result.reason == "Initialized"
            assert result.hwm_equity == D("100000")
            assert result.day_start_equity == D("100000")
            assert result.current_equity == D("100000")
            assert result.hwm_drawdown_pct == D("0")
            assert result.daily_drawdown_pct == D("0")
        finally:
            _cleanup(path)

    def test_equity_above_hwm_updates_hwm(self) -> None:
        guard, path = _make_guard()
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("105000"), timestamp=ts2)

            assert result.triggered is False
            assert result.hwm_equity == D("105000")
            assert result.hwm_drawdown_pct == D("0")
        finally:
            _cleanup(path)

    def test_hwm_drawdown_triggers_at_threshold(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Drop to 89,999 — 10.001% drawdown, should trigger
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("89999"), timestamp=ts2)

            assert result.triggered is True
            assert "HWM drawdown" in result.reason
            assert result.hwm_drawdown_pct >= D("10.0")
        finally:
            _cleanup(path)

    def test_hwm_drawdown_below_threshold_no_trigger(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Drop to 91,000 — 9% drawdown, below 10% threshold
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("91000"), timestamp=ts2)

            assert result.triggered is False
            assert result.hwm_drawdown_pct == D("9")
        finally:
            _cleanup(path)

    def test_daily_loss_triggers_at_threshold(self) -> None:
        guard, path = _make_guard(daily_pct=D("5.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Drop to 94,999 — 5.001% daily loss, should trigger
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("94999"), timestamp=ts2)

            assert result.triggered is True
            assert "Daily drawdown" in result.reason
            assert result.daily_drawdown_pct >= D("5.0")
        finally:
            _cleanup(path)

    def test_new_day_resets_daily_but_not_hwm(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"), daily_pct=D("5.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Next day, equity recovered to 100,000
            ts2 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("100000"), timestamp=ts2)

            # HWM should still be 100,000 (not reset)
            assert result.hwm_equity == D("100000")
            # Day start should be the new equity
            assert result.day_start_equity == D("100000")
            # Daily drawdown should be 0 (just started the day)
            assert result.daily_drawdown_pct == D("0")
            assert result.triggered is False
        finally:
            _cleanup(path)

    def test_hwm_breach_persists_across_days(self) -> None:
        """A new day must NOT clear an HWM breach."""
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Trigger HWM breach
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result1 = guard.evaluate(equity=D("89999"), timestamp=ts2)
            assert result1.triggered is True

            # Next day, equity still below HWM
            ts3 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
            result2 = guard.evaluate(equity=D("90000"), timestamp=ts3)

            # HWM breach flag is still set, so no new trigger
            assert result2.triggered is False
            assert result2.hwm_drawdown_pct >= D("10.0")
        finally:
            _cleanup(path)

    def test_new_hwm_clears_breach_flag(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Trigger HWM breach
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("89999"), timestamp=ts2)

            # Recover above HWM — new HWM clears breach flag
            ts3 = datetime(2026, 7, 14, 14, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("110000"), timestamp=ts3)

            assert result.triggered is False
            assert result.hwm_equity == D("110000")
            assert result.hwm_drawdown_pct == D("0")
        finally:
            _cleanup(path)

    def test_non_positive_equity_triggers_immediately(self) -> None:
        guard, path = _make_guard()
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("0"), timestamp=ts)

            assert result.triggered is True
            assert "Non-positive equity" in result.reason
        finally:
            _cleanup(path)

    def test_negative_equity_triggers_immediately(self) -> None:
        guard, path = _make_guard()
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("-5000"), timestamp=ts)

            assert result.triggered is True
            assert "Non-positive equity" in result.reason
        finally:
            _cleanup(path)

    def test_idempotent_trigger_no_second_trigger(self) -> None:
        """Once triggered, subsequent evaluations must not re-trigger."""
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result1 = guard.evaluate(equity=D("89999"), timestamp=ts2)
            assert result1.triggered is True

            # Same equity, same day — should NOT re-trigger
            ts3 = datetime(2026, 7, 14, 14, 0, 0, tzinfo=UTC)
            result2 = guard.evaluate(equity=D("89999"), timestamp=ts3)
            assert result2.triggered is False
        finally:
            _cleanup(path)

    def test_both_hwm_and_daily_trigger_simultaneously(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"), daily_pct=D("5.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Drop to 85,000 — exceeds both 10% HWM and 5% daily
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("85000"), timestamp=ts2)

            assert result.triggered is True
            assert "HWM drawdown" in result.reason
            assert "Daily drawdown" in result.reason
        finally:
            _cleanup(path)

    def test_state_persistence_across_guard_instances(self) -> None:
        guard1, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard1.evaluate(equity=D("100000"), timestamp=ts)

            # Create a new guard instance reading the same state file
            guard2 = FleetDrawdownGuard(
                hwm_drawdown_pct=D("10.0"),
                daily_loss_pct=D("10.0"),
                state_file=path,
            )
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard2.evaluate(equity=D("89999"), timestamp=ts2)

            assert result.triggered is True
            assert result.hwm_equity == D("100000")
        finally:
            _cleanup(path)

    def test_corrupt_state_file_fails_closed(self) -> None:
        guard, path = _make_guard()
        try:
            # Write corrupt data
            path.write_text("not valid json", encoding="utf-8")

            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("100000"), timestamp=ts)

            # Should initialize fresh
            assert result.triggered is False
            assert result.reason == "Initialized"
            assert result.hwm_equity == D("100000")
        finally:
            _cleanup(path)

    def test_empty_state_file_fails_closed(self) -> None:
        guard, path = _make_guard()
        try:
            path.write_text("", encoding="utf-8")

            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("100000"), timestamp=ts)

            assert result.triggered is False
            assert result.hwm_equity == D("100000")
        finally:
            _cleanup(path)

    def test_reset_clears_all_state(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("89999"), timestamp=ts2)

            guard.reset()

            # After reset, should initialize fresh
            ts3 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("100000"), timestamp=ts3)

            assert result.triggered is False
            assert result.reason == "Initialized"
            assert result.hwm_equity == D("100000")
        finally:
            _cleanup(path)

    def test_load_state_returns_current_state(self) -> None:
        guard, path = _make_guard()
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            state = guard.load_state()
            assert state.hwm_equity == D("100000")
            assert state.day_date == "2026-07-14"
        finally:
            _cleanup(path)

    def test_drawdown_calculation_precision(self) -> None:
        """Verify drawdown percentage calculation is correct."""
        guard, path = _make_guard(hwm_pct=D("25.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # 75,000 from 100,000 = 25% drawdown
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("75000"), timestamp=ts2)

            assert result.triggered is True
            assert result.hwm_drawdown_pct == D("25")
        finally:
            _cleanup(path)

    def test_drawdown_exactly_at_threshold_triggers(self) -> None:
        """Drawdown exactly at the threshold should trigger."""
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # 90,000 from 100,000 = exactly 10% drawdown
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("90000"), timestamp=ts2)

            assert result.triggered is True
            assert result.hwm_drawdown_pct == D("10")
        finally:
            _cleanup(path)

    def test_equity_above_hwm_after_drawdown_no_trigger(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Small drop, below threshold
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            result = guard.evaluate(equity=D("95000"), timestamp=ts2)

            assert result.triggered is False
            assert result.hwm_drawdown_pct == D("5")
        finally:
            _cleanup(path)

    def test_multiple_ticks_same_equity_no_trigger(self) -> None:
        guard, path = _make_guard(hwm_pct=D("10.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            for i in range(5):
                ts2 = datetime(2026, 7, 14, 12, i, 0, tzinfo=UTC)
                result = guard.evaluate(equity=D("95000"), timestamp=ts2)
                assert result.triggered is False
        finally:
            _cleanup(path)

    def test_equity_recovery_after_daily_breach(self) -> None:
        """Daily breach flag should prevent re-triggering even if equity recovers and drops again."""
        guard, path = _make_guard(daily_pct=D("5.0"))
        try:
            ts = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("100000"), timestamp=ts)

            # Trigger daily breach
            ts2 = datetime(2026, 7, 14, 13, 0, 0, tzinfo=UTC)
            guard.evaluate(equity=D("94999"), timestamp=ts2)

            # Recover
            ts3 = datetime(2026, 7, 14, 14, 0, 0, tzinfo=UTC)
            result1 = guard.evaluate(equity=D("98000"), timestamp=ts3)
            assert result1.triggered is False

            # Drop again — should NOT re-trigger (flag already set)
            ts4 = datetime(2026, 7, 14, 15, 0, 0, tzinfo=UTC)
            result2 = guard.evaluate(equity=D("94000"), timestamp=ts4)
            assert result2.triggered is False
        finally:
            _cleanup(path)

    def test_default_state_file_path(self) -> None:
        """Verify the default state file path is correct."""
        assert DEFAULT_STATE_FILE == "var/fleet_drawdown_state.json"


# ---------------------------------------------------------------------------
# DrawdownEvaluation tests
# ---------------------------------------------------------------------------


class TestDrawdownEvaluation:
    def test_default_values(self) -> None:
        ev = DrawdownEvaluation()
        assert ev.triggered is False
        assert ev.reason == ""
        assert ev.hwm_drawdown_pct == D("0")
        assert ev.daily_drawdown_pct == D("0")
        assert ev.hwm_equity == D("0")
        assert ev.day_start_equity == D("0")
        assert ev.current_equity == D("0")

    def test_custom_values(self) -> None:
        ev = DrawdownEvaluation(
            triggered=True,
            reason="Test trigger",
            hwm_drawdown_pct=D("15.5"),
            daily_drawdown_pct=D("8.2"),
            hwm_equity=D("100000"),
            day_start_equity=D("95000"),
            current_equity=D("85000"),
        )
        assert ev.triggered is True
        assert ev.reason == "Test trigger"
        assert ev.hwm_drawdown_pct == D("15.5")
        assert ev.daily_drawdown_pct == D("8.2")
        assert ev.hwm_equity == D("100000")
        assert ev.day_start_equity == D("95000")
        assert ev.current_equity == D("85000")
