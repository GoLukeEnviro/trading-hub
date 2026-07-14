"""Compatibility tests for the retired Phase-0A scaffold API.

Authoritative evaluation behavior is covered by ``test_evaluation_bundle_v1``.
The legacy list-of-dicts entry point must fail closed so callers cannot bypass
the manifest, canonical input bundle, partition, and provenance contracts.
"""

from __future__ import annotations

import pytest

from si_v2.research.edge_evidence_harness import (
    LegacyEvaluationAPIError,
    StrategyEvaluationHarness,
)


@pytest.mark.parametrize("trade_results", [[], [{"net_pnl": 1.0}]])
def test_legacy_evaluate_always_requires_v1_migration(
    trade_results: list[dict[str, object]],
) -> None:
    harness = object.__new__(StrategyEvaluationHarness)

    with pytest.raises(
        LegacyEvaluationAPIError,
        match=r"EvaluationManifestV1 \+ EvaluationBundleV1 \+ EvaluationRunnerV1",
    ):
        harness.evaluate(trade_results)


def test_legacy_regime_argument_cannot_bypass_migration_gate() -> None:
    harness = object.__new__(StrategyEvaluationHarness)

    with pytest.raises(LegacyEvaluationAPIError, match="disabled"):
        harness.evaluate([{"net_pnl": 1.0}], regime_labels={"bull": 1})
