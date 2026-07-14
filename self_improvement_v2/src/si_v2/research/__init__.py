"""Research evaluation package for edge-evidence analysis.

This package provides a reproducible, repository-only evaluation harness
for testing Freqtrade strategies against historical data. It supports
out-of-sample, walk-forward, and untouched-holdout evaluation with
explicit cost and data-quality assumptions.

**Safety boundary:** This is a research tool only. It never mutates
strategies, runtime configuration, or live state. Output is advisory
evidence, never a trading signal or live authorization.
"""

from __future__ import annotations

from .edge_evidence_harness import (
    DEFAULT_EVALUATION_CONFIG,
    EvaluationConfig,
    EvaluationResult,
    Gate0Outcome,
    HarnessProvenance,
    StrategyEvaluationHarness,
)

__all__ = [
    "DEFAULT_EVALUATION_CONFIG",
    "EvaluationConfig",
    "EvaluationResult",
    "Gate0Outcome",
    "HarnessProvenance",
    "StrategyEvaluationHarness",
]
