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
    LegacyEvaluationAPIError,
    StrategyEvaluationHarness,
)
from .evaluation_bundle_v1 import (
    BoundaryPolicy,
    CandleV1,
    ContinuationPolicy,
    EvaluationArtifactV1,
    EvaluationBundleV1,
    EvaluationManifestV1,
    EvaluationRunnerV1,
    EvaluationThresholdsV1,
    FreqtradeExportAdapterV1,
    FreqtradeProvenanceV1,
    InvalidEvaluationError,
    PartitionWindowV1,
    ProfitFactorState,
    RawTradeV1,
    canonical_candle_hash,
)

__all__ = [
    "DEFAULT_EVALUATION_CONFIG",
    "BoundaryPolicy",
    "CandleV1",
    "ContinuationPolicy",
    "EvaluationArtifactV1",
    "EvaluationBundleV1",
    "EvaluationConfig",
    "EvaluationManifestV1",
    "EvaluationResult",
    "EvaluationRunnerV1",
    "EvaluationThresholdsV1",
    "FreqtradeExportAdapterV1",
    "FreqtradeProvenanceV1",
    "Gate0Outcome",
    "HarnessProvenance",
    "InvalidEvaluationError",
    "LegacyEvaluationAPIError",
    "PartitionWindowV1",
    "ProfitFactorState",
    "RawTradeV1",
    "StrategyEvaluationHarness",
    "canonical_candle_hash",
]
