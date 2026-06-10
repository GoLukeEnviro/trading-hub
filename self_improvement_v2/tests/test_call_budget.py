"""Tests for the call budget contract (adapters/call_budget.py).

Uses an injected deterministic clock for all timing-sensitive tests.
"""

from __future__ import annotations

import pytest

from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig


class TestCallBudgetConfig:
    """Tests for :class:`CallBudgetConfig`."""

    def test_default_values(self) -> None:
        config = CallBudgetConfig()
        assert config.max_calls == 60
        assert config.window_seconds == 60.0
        assert config.component_name == ""

    def test_custom_values(self) -> None:
        config = CallBudgetConfig(max_calls=10, window_seconds=5.0, component_name="test")
        assert config.max_calls == 10
        assert config.window_seconds == 5.0
        assert config.component_name == "test"

    def test_max_calls_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            CallBudgetConfig(max_calls=0)

    def test_window_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            CallBudgetConfig(window_seconds=0.0)


class TestCallBudgetCheckerDeterministic:
    """Tests using an injected clock for deterministic timing."""

    def test_allowed_within_budget(self) -> None:
        """check_call returns True when under the limit."""
        clock = iter([1000.0, 1000.1, 1000.2])
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock))
        assert checker.check_call() is True
        assert checker.check_call() is True
        assert checker.check_call() is True

    def test_denied_after_exhausted(self) -> None:
        """check_call returns False when budget consumed."""
        clock = iter([1000.0] * 3 + [1000.5])
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock))
        assert checker.check_call() is True
        assert checker.check_call() is True
        assert checker.check_call() is True
        assert checker.check_call() is False

    def test_remaining_counts(self) -> None:
        """remaining decreases as calls are made."""
        # Need 5 clock values: 3 for check_call + 2 for remaining calls
        clock = iter([1000.0, 1000.1, 1000.2, 1000.3, 1000.4])
        config = CallBudgetConfig(max_calls=5, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock))
        assert checker.remaining() == 5
        checker.check_call()
        assert checker.remaining() == 4
        checker.check_call()
        assert checker.remaining() == 3

    def test_remaining_never_negative(self) -> None:
        """remaining clamps at 0."""
        clock = iter([1000.0] * 10)
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock))
        for _ in range(3):
            checker.check_call()
        assert checker.remaining() == 0
        # Extra check_call should not drive remaining negative
        checker.check_call()
        assert checker.remaining() == 0

    def test_reset_clears_window(self) -> None:
        """After reset, full budget is restored."""
        # 6 values: 4 check_call + 1 remaining + 1 check_call after reset
        clock = iter([1000.0] * 4 + [1000.5, 1000.6])
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock))
        checker.check_call()
        checker.check_call()
        checker.check_call()
        assert checker.check_call() is False  # exhausted
        checker.reset()
        assert checker.remaining() == 3
        assert checker.check_call() is True  # allowed again

    def test_sliding_window_allows_after_window_passes(self) -> None:
        """Old calls expire after window_seconds, freeing budget."""
        # Simulate: call 3 times at t=1000, then try at t=1011 (window is 10s)
        clock_vals = [1000.0, 1000.01, 1000.02, 1011.0]
        clock_iter = iter(clock_vals)
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock_iter))
        assert checker.check_call() is True  # t=1000.0
        assert checker.check_call() is True  # t=1000.01
        assert checker.check_call() is True  # t=1000.02
        assert checker.check_call() is True  # t=1011.0 → old calls expired

    def test_remaining_with_expired_sliding_window(self) -> None:
        """After window passes, remaining recovers."""
        clock_vals = [1000.0, 1000.01, 1000.02, 1011.0]
        clock_iter = iter(clock_vals)
        config = CallBudgetConfig(max_calls=3, window_seconds=10.0)
        checker = CallBudgetChecker(config, clock=lambda: next(clock_iter))
        checker.check_call()
        checker.check_call()
        checker.check_call()
        # At t=1011, old calls from t=1000 have expired — budget is full again
        assert checker.remaining() == 3

    def test_clock_defaults_to_time(self) -> None:
        """Without a custom clock, the checker uses time.time (smoke test)."""
        config = CallBudgetConfig(max_calls=5, window_seconds=60.0)
        checker = CallBudgetChecker(config)
        assert checker.remaining() == 5
        assert checker.check_call() is True
