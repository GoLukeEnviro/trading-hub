"""Unit tests for the ShadowModeManager."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

from si_v2.deploy.shadow_mode import ShadowModeManager, ShadowSession, ShadowStatus


def _clock_at(times: list[datetime]):
    """Return a callable that yields successive times, then sticks at the last."""
    it = iter(times)
    current: list[datetime] = []

    def _clock() -> datetime:
        with contextlib.suppress(StopIteration):
            current.append(next(it))
        return current[-1] if current else times[0]

    return _clock


class TestShadowModeStart:
    """start_shadow records a session."""

    def test_start_shadow_creates_session(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        mgr = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        session = mgr.start_shadow(
            bot_id="bot_a",
            candidate_sha="sha-1",
            baseline_metrics={"profit_pct": 3.5},
        )
        assert isinstance(session, ShadowSession)
        assert session.bot_id == "bot_a"
        assert session.candidate_sha == "sha-1"
        assert session.duration_hours == 72
        assert session.status == ShadowStatus.PENDING
        assert session.start_utc == start.isoformat()
        expected_end = start + timedelta(hours=72)
        assert session.expected_end_utc == expected_end.isoformat()

    def test_get_shadow_status_unknown_for_missing_bot(self) -> None:
        mgr = ShadowModeManager(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
        assert mgr.get_shadow_status("nonexistent") == ShadowStatus.UNKNOWN

    def test_start_shadow_copies_metrics(self) -> None:
        mgr = ShadowModeManager(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
        baseline: dict[str, float | int | str] = {"profit_pct": 3.5, "drawdown_pct": 0.05}
        mgr.start_shadow("bot_a", "sha", baseline)
        baseline["profit_pct"] = 99.0
        session = mgr.get_session("bot_a")
        assert session is not None
        assert session.baseline_metrics["profit_pct"] == 3.5


class TestShadowModePendingToComplete:
    """Status transitions from pending to complete as the clock advances."""

    def test_status_pending_within_window(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        times = [
            start,
            start + timedelta(hours=24),
            start + timedelta(hours=71),
        ]
        mgr = ShadowModeManager(clock=_clock_at(times), default_duration_hours=72)
        mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5})
        # Within window: pending
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.PENDING
        assert mgr.is_shadow_complete("bot_a") is False

    def test_status_complete_after_window(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        times = [
            start,
            start + timedelta(hours=72),
            start + timedelta(hours=100),
        ]
        mgr = ShadowModeManager(clock=_clock_at(times), default_duration_hours=72)
        mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5})
        # Past end: complete
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.COMPLETE
        assert mgr.is_shadow_complete("bot_a") is True

    def test_status_complete_at_exact_end(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        # Clock advances during start_shadow, so expected_end = start + 72h
        # Then we advance clock past the expected end to trigger complete
        current = {"t": 0}

        def advancing_clock() -> datetime:
            return start + timedelta(hours=current["t"])

        mgr = ShadowModeManager(clock=advancing_clock, default_duration_hours=72)
        current["t"] = 0  # during start_shadow, clock = start
        mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5})
        current["t"] = 73  # past expected_end (start + 72h)
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.COMPLETE


class TestShadowModeFailure:
    """A shadow session fails if current metrics drop below baseline."""

    def test_failed_when_profit_drops(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        mgr = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        mgr.start_shadow(
            "bot_a",
            "sha-1",
            {"profit_pct": 3.5, "sharpe": 1.5, "win_rate_pct": 60.0},
        )
        mgr.update_metrics("bot_a", {"profit_pct": 1.0})
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.FAILED

    def test_failed_when_sharpe_drops(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        mgr = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5, "sharpe": 1.5})
        mgr.update_metrics("bot_a", {"sharpe": 0.5})
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.FAILED

    def test_not_failed_when_metric_improves(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        mgr = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5})
        mgr.update_metrics("bot_a", {"profit_pct": 4.0})
        assert mgr.get_shadow_status("bot_a") == ShadowStatus.PENDING

    def test_update_metrics_is_safe_for_unknown_bot(self) -> None:
        mgr = ShadowModeManager(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
        # Should not raise
        mgr.update_metrics("nonexistent", {"x": 1})


class TestShadowModeCustomDuration:
    """Default duration is configurable."""

    def test_custom_default_duration(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        mgr = ShadowModeManager(clock=lambda: start, default_duration_hours=24)
        session = mgr.start_shadow("bot_a", "sha-1", {"profit_pct": 1.0})
        assert session.duration_hours == 24
        expected_end = start + timedelta(hours=24)
        assert session.expected_end_utc == expected_end.isoformat()


class TestShadowModeNoBackground:
    """The manager must not spawn background processes."""

    def test_no_threads_or_timers(self) -> None:
        mgr = ShadowModeManager(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
        # No thread / timer attributes should be exposed
        assert not hasattr(mgr, "_thread")
        assert not hasattr(mgr, "_timer")
        assert not hasattr(mgr, "start")
        assert not hasattr(mgr, "run")
