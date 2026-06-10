"""Shadow-mode manager — simulation only.

Provides a ShadowModeManager that records a ShadowSession per bot and
reports a ShadowStatus (pending / complete / failed / unknown) based
on the injected clock and the current metrics.

The manager does NOT start any background processes, does NOT install
cron jobs, does NOT use threading or asyncio timers, and does NOT
perform any network I/O. Time-dependent behaviour is computed only
when explicitly queried.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ShadowStatus(StrEnum):
    """Possible status values for a shadow session."""

    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ShadowSession(BaseModel):
    """The state of a single shadow-mode session for a bot."""

    model_config = ConfigDict(strict=False)

    bot_id: str
    candidate_sha: str
    start_utc: str
    expected_end_utc: str
    duration_hours: int = Field(default=72, ge=1)
    baseline_metrics: dict[str, float | int | str] = Field(default_factory=dict)
    current_metrics: dict[str, float | int | str] = Field(default_factory=dict)
    status: ShadowStatus = ShadowStatus.PENDING


# Metrics that are interpreted as "higher is better" when comparing
# current to baseline. If the current value is less than the baseline,
# the session is considered failed.
_HIGHER_IS_BETTER: tuple[str, ...] = (
    "profit_pct",
    "profit_total_pct",
    "expected_profit_pct",
    "sharpe",
    "win_rate_pct",
    "profit_factor",
)


class ShadowModeManager:
    """Manages in-memory shadow sessions for bots.

    All time arithmetic uses the injected clock. No timers, no
    background processes, no cron.
    """

    def __init__(
        self,
        clock: Callable[[], datetime],
        default_duration_hours: int = 72,
    ) -> None:
        """Initialise the manager with a clock and default duration.

        Args:
            clock: Callable returning the current UTC datetime.
            default_duration_hours: Default shadow window length.
        """
        self._clock = clock
        self._default_duration_hours = default_duration_hours
        self._sessions: dict[str, ShadowSession] = {}

    def start_shadow(
        self,
        bot_id: str,
        candidate_sha: str,
        baseline_metrics: dict[str, float | int | str],
    ) -> ShadowSession:
        """Start a new shadow session for a bot.

        Args:
            bot_id: Bot identifier.
            candidate_sha: SHA256 hash of the candidate being shadowed.
            baseline_metrics: Metrics recorded at session start.

        Returns:
            The new ShadowSession.
        """
        now = self._clock()
        end = now + timedelta(hours=self._default_duration_hours)
        session = ShadowSession(
            bot_id=bot_id,
            candidate_sha=candidate_sha,
            start_utc=now.isoformat(),
            expected_end_utc=end.isoformat(),
            duration_hours=self._default_duration_hours,
            baseline_metrics=dict(baseline_metrics),
            current_metrics=dict(baseline_metrics),
            status=ShadowStatus.PENDING,
        )
        self._sessions[bot_id] = session
        return session

    def update_metrics(
        self,
        bot_id: str,
        current_metrics: dict[str, float | int | str],
    ) -> None:
        """Update the current metrics for an active shadow session.

        Args:
            bot_id: Bot identifier.
            current_metrics: New metric values to record.
        """
        if bot_id not in self._sessions:
            return
        session = self._sessions[bot_id]
        merged: dict[str, float | int | str] = dict(session.current_metrics)
        for key, value in current_metrics.items():
            merged[key] = value
        session.current_metrics = merged
        # Re-evaluate status in case current metrics are below baseline
        if self._metrics_below_baseline(session):
            session.status = ShadowStatus.FAILED
        elif self._clock() >= datetime.fromisoformat(session.expected_end_utc):
            session.status = ShadowStatus.COMPLETE
        else:
            session.status = ShadowStatus.PENDING

    def is_shadow_complete(self, bot_id: str) -> bool:
        """Check whether the shadow session for a bot has completed.

        Returns True if the current clock is at or past the session's
        expected_end_utc AND the session has not been marked failed.

        Args:
            bot_id: Bot identifier.

        Returns:
            True if the session is complete; False otherwise.
        """
        if bot_id not in self._sessions:
            return False
        session = self._sessions[bot_id]
        end = datetime.fromisoformat(session.expected_end_utc)
        now = self._clock()
        return now >= end and session.status != ShadowStatus.FAILED

    def get_shadow_status(self, bot_id: str) -> ShadowStatus:
        """Compute the current status for a bot's shadow session.

        Returns:
            * "unknown"  — no session recorded for the bot.
            * "failed"   — current metrics are below baseline on a
                            higher-is-better metric.
            * "complete" — clock is at or past expected end and the
                            session is not failed.
            * "pending"  — clock is before expected end and the
                            session is not failed.
        """
        if bot_id not in self._sessions:
            return ShadowStatus.UNKNOWN

        session = self._sessions[bot_id]
        if self._metrics_below_baseline(session):
            return ShadowStatus.FAILED

        end = datetime.fromisoformat(session.expected_end_utc)
        now = self._clock()
        if now >= end:
            return ShadowStatus.COMPLETE
        return ShadowStatus.PENDING

    def get_session(self, bot_id: str) -> ShadowSession | None:
        """Return the stored session for a bot (or None if absent)."""
        return self._sessions.get(bot_id)

    def _metrics_below_baseline(self, session: ShadowSession) -> bool:
        """Return True if any higher-is-better metric has dropped.

        Args:
            session: The session to evaluate.

        Returns:
            True when the session's current_metrics contain a
            higher-is-better key whose value is below the baseline.
        """
        for key, current in session.current_metrics.items():
            if key not in _HIGHER_IS_BETTER:
                continue
            baseline = session.baseline_metrics.get(key)
            if baseline is None:
                continue
            try:
                cur_f = float(current)
                base_f = float(baseline)
            except (TypeError, ValueError):
                continue
            if cur_f < base_f:
                return True
        return False
