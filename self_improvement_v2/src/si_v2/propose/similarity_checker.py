"""Similarity checker using normalized Euclidean distance.

Prevents proposing mutations that are too similar to previous candidates,
avoiding redundant or oscillating parameter changes.
"""

from __future__ import annotations

import math

# Normalization ranges for each parameter (used to scale to [0, 1])
_PARAM_RANGES: dict[str, tuple[float, float]] = {
    "rsi_period": (2.0, 50.0),
    "stoploss_pct": (-0.5, -0.001),
    "take_profit_pct": (0.001, 0.5),
    "stake_factor": (0.1, 5.0),
    "max_open_trades": (1.0, 20.0),
    "cooldown_candles": (0.0, 100.0),
}


class SimilarityChecker:
    """Checks parameter similarity using normalized Euclidean distance."""

    def compute_distance(
        self,
        params_a: dict[str, float | int],
        params_b: dict[str, float | int],
    ) -> float:
        """Compute normalized Euclidean distance between two parameter sets.

        Args:
            params_a: First parameter set.
            params_b: Second parameter set.

        Returns:
            Distance value (0.0 for identical, higher for more different).
        """
        if not params_a and not params_b:
            return 0.0
        if not params_a or not params_b:
            return 1.0

        all_keys = set(params_a.keys()) | set(params_b.keys())
        if not all_keys:
            return 0.0

        sum_squared = 0.0
        for key in all_keys:
            val_a = float(params_a.get(key, 0))
            val_b = float(params_b.get(key, 0))
            low, high = _PARAM_RANGES.get(key, (0.0, 1.0))
            span = high - low
            if span == 0:
                norm_diff = 0.0
            else:
                norm_a = (val_a - low) / span
                norm_b = (val_b - low) / span
                norm_diff = norm_a - norm_b
            sum_squared += norm_diff**2

        return math.sqrt(sum_squared / len(all_keys))

    def is_too_similar(
        self,
        candidate: dict[str, float | int],
        history: list[dict[str, float | int]],
        threshold: float = 0.05,
    ) -> bool:
        """Check if a candidate is too similar to any entry in history.

        Args:
            candidate: Proposed parameter set.
            history: List of previous parameter sets.
            threshold: Maximum distance below which candidates are considered similar.

        Returns:
            True if candidate is within threshold of any history entry.
        """
        for past_params in history:
            distance = self.compute_distance(candidate, past_params)
            if distance < threshold:
                return True
        return False
