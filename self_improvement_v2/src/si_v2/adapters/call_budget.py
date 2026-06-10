"""Call budget contract — sliding-window rate limiter for real adapters.

Each real adapter can hold an optional :class:`CallBudgetChecker` that
limits invocations to *max_calls* per *window_seconds* sliding window.
When exhausted, the adapter records a denied audit event and returns a
fallback / error.

The checker uses an in-memory sliding window of timestamps. It never
sleeps, never starts threads, and never touches the filesystem. A
deterministic clock (``Callable[[], float]``) is injected so tests can
control time without monkey-patching ``time.time``.
"""

from __future__ import annotations

from collections.abc import Callable
from time import time

from pydantic import BaseModel, Field


class CallBudgetConfig(BaseModel):
    """Configuration for a sliding-window call budget.

    Defaults to **60 calls per 60 seconds** (one call per second on
    average).
    """

    max_calls: int = Field(
        default=60,
        ge=1,
        description="Maximum calls allowed within the sliding window.",
    )
    window_seconds: float = Field(
        default=60.0,
        gt=0.0,
        description="Width of the sliding window in seconds.",
    )
    component_name: str = Field(
        default="",
        description="Human-readable component identifier for error messages.",
    )


class CallBudgetChecker:
    """Sliding-window rate limiter for real adapter invocations.

    Args:
        config: Budget configuration (max_calls, window_seconds, name).
        clock: A callable returning seconds since epoch (for
               deterministic testing). Defaults to :func:`time.time`.
    """

    def __init__(
        self,
        config: CallBudgetConfig,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or time
        self._timestamps: list[float] = []

    def check_call(self) -> bool:
        """Check whether a call is within budget.

        The check is a two-step process:

        1. Prune timestamps older than ``now - window_seconds``.
        2. If the remaining count is below *max_calls*, record ``now`` and
           return ``True``. Otherwise return ``False``.

            Returns:
                ``True`` if the call is allowed, ``False`` if exhausted.
        """
        now = self._clock()
        cutoff = now - self._config.window_seconds
        # Prune expired timestamps
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) < self._config.max_calls:
            self._timestamps.append(now)
            return True
        return False

    def reset(self) -> None:
        """Clear the call window, allowing a fresh budget."""
        self._timestamps.clear()

    def remaining(self) -> int:
        """Return the number of calls still allowed in the current window.

        Returns:
            Calls remaining (may be 0).
        """
        now = self._clock()
        cutoff = now - self._config.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return max(0, self._config.max_calls - len(self._timestamps))
