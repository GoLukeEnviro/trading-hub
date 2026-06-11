"""Performance Attribution Engine.

Processes attribution inputs and produces deterministic attribution facts
with per-dimension-group metrics.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass

from .models import (
    AttributionFact,
    AttributionInput,
    AttributionResult,
    RejectionDiagnostic,
)


@dataclass
class DimensionGroupMetrics:
    """Aggregated metrics for a single dimension group.

    Attributes:
        canonical_key: Sorted tuple of (dimension, value) pairs for stable identity.
        unique_trade_count: Number of unique trades in this group.
        source_contribution_count: Number of signal contributions.
        win_count: Number of winning outcomes.
        loss_count: Number of losing outcomes.
        breakeven_count: Number of breakeven outcomes.
        win_rate: Fraction of non-breakeven outcomes that are wins.
        average_raw_return: Mean raw trade return.
        average_weighted_return: Mean weighted return.
        expectancy: Average weighted return across all contributions.
        cumulative_weighted_return: Sum of weighted returns.
        drawdown_proxy: Maximum peak-to-trough decline in cumulative returns
            from time-ordered cumulative returns.
        average_source_confidence: Mean source confidence (None treated as 0).
        average_regime_confidence: Mean regime confidence.
    """

    unique_trade_count: int = 0
    source_contribution_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    win_rate: float = 0.0
    average_raw_return: float = 0.0
    average_weighted_return: float = 0.0
    expectancy: float = 0.0
    cumulative_weighted_return: float = 0.0
    drawdown_proxy: float = 0.0
    average_source_confidence: float = 0.0
    average_regime_confidence: float = 0.0


class DimensionGroup:
    """Collector for facts and associated metadata sharing the same dimensions."""

    def __init__(self) -> None:
        self.facts: list[AttributionFact] = []
        self._trade_ids: set[str] = set()
        self._source_confidences: list[float] = []
        self._regime_confidences: list[float] = []

    def add(
        self,
        fact: AttributionFact,
        source_confidence: float | None = None,
        regime_confidence: float | None = None,
    ) -> None:
        """Add a fact with associated confidence values."""
        self.facts.append(fact)
        self._trade_ids.add(fact.trade_id)
        self._source_confidences.append(source_confidence if source_confidence is not None else 0.0)
        if regime_confidence is not None:
            self._regime_confidences.append(regime_confidence)

    @property
    def trade_ids(self) -> set[str]:
        return self._trade_ids

    def compute_metrics(self) -> DimensionGroupMetrics:
        """Compute all metrics for this dimension group."""
        m = DimensionGroupMetrics()

        m.unique_trade_count = len(self._trade_ids)
        m.source_contribution_count = len(self.facts)

        # Sort facts by closed_at for time-ordered cumulative return computation
        sorted_facts_with_idx = sorted(
            enumerate(self.facts),
            key=lambda pair: pair[1].closed_at,
        )

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        weighted_returns: list[float] = []
        raw_returns: list[float] = []

        for _idx, fact in sorted_facts_with_idx:
            weighted_returns.append(fact.weighted_return)
            raw_returns.append(fact.raw_trade_return)
            cumulative += fact.weighted_return
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_drawdown:
                max_drawdown = dd

        m.cumulative_weighted_return = cumulative
        m.drawdown_proxy = max_drawdown

        # Outcome counts
        for _, fact in sorted_facts_with_idx:
            if fact.outcome_classification == "WIN":
                m.win_count += 1
            elif fact.outcome_classification == "LOSS":
                m.loss_count += 1
            else:
                m.breakeven_count += 1

        # Win rate: wins / (wins + losses), treat as 0 if no decisive outcomes
        decisive = m.win_count + m.loss_count
        m.win_rate = m.win_count / decisive if decisive > 0 else 0.0

        # Averages
        n = len(sorted_facts_with_idx)
        if n > 0:
            m.average_raw_return = sum(raw_returns) / n
            m.average_weighted_return = sum(weighted_returns) / n
            m.expectancy = sum(weighted_returns) / n

        # Average confidences
        if self._source_confidences:
            m.average_source_confidence = sum(self._source_confidences) / len(
                self._source_confidences
            )
        if self._regime_confidences:
            m.average_regime_confidence = sum(self._regime_confidences) / len(
                self._regime_confidences
            )

        return m


class PerformanceAttributionEngine:
    """Engine for processing attribution inputs and producing metrics.

    Processes AttributionInput records, validates them, produces AttributionFact
    records, and computes per-dimension-group metrics.
    """

    def from_iterable(
        self,
        entries: Iterable[AttributionInput],
    ) -> AttributionResult:
        """Process an iterable of AttributionInput records.

        Args:
            entries: Iterable of attribution input records.

        Returns:
            AttributionResult with accepted facts, rejection diagnostics,
            and aggregate counts.
        """
        facts: list[AttributionFact] = []
        diagnostics: list[RejectionDiagnostic] = []
        seen_fact_ids: set[str] = set()
        accepted = 0
        rejected = 0

        # Build input fingerprint
        input_entries = list(entries)
        input_raw = "|".join(
            f"{e.trade_id}:{e.source_event_id}:{e.regime.value}"
            for e in input_entries
        )
        input_fingerprint = hashlib.sha256(input_raw.encode("utf-8")).hexdigest()

        for entry in input_entries:
            # Validate trade_id
            if not entry.trade_id or not entry.trade_id.strip():
                diagnostics.append(
                    RejectionDiagnostic(
                        trade_id=entry.trade_id or "",
                        reason="missing_trade_id",
                        detail="Trade ID is empty or missing",
                    )
                )
                rejected += 1
                continue

            # Validate signal_contributions (presence check beyond model)
            if not entry.signal_contributions:
                diagnostics.append(
                    RejectionDiagnostic(
                        trade_id=entry.trade_id,
                        reason="missing_signal_contributions",
                        detail="No signal contributions provided",
                    )
                )
                rejected += 1
                continue

            # Reject non-finite returns
            if not math.isfinite(entry.realized_return):
                diagnostics.append(
                    RejectionDiagnostic(
                        trade_id=entry.trade_id,
                        reason="invalid_realized_return",
                        detail=f"Non-finite realized_return: {entry.realized_return}",
                    )
                )
                rejected += 1
                continue

            # Process each signal contribution
            for sc in entry.signal_contributions:
                # Validate source_id
                if not sc.source_id or not sc.source_id.strip():
                    diagnostics.append(
                        RejectionDiagnostic(
                            trade_id=entry.trade_id,
                            reason="missing_source_id",
                            detail="Signal contribution has empty source_id",
                        )
                    )
                    rejected += 1
                    continue

                # Compute weighted return
                weighted_return = entry.realized_return * sc.contribution_weight

                # Compute fact_id
                fact_id = AttributionFact.compute_fact_id(
                    entry.trade_id, sc.source_id, entry.regime
                )

                # Check for conflicting fact (same fact_id from different data)
                if fact_id in seen_fact_ids:
                    diagnostics.append(
                        RejectionDiagnostic(
                            trade_id=entry.trade_id,
                            reason="duplicate_fact_id",
                            detail=f"Conflicting fact detected for fact_id={fact_id}",
                        )
                    )
                    rejected += 1
                    continue

                seen_fact_ids.add(fact_id)

                # Compute outcome classification
                outcome = AttributionFact._classify_outcome(entry.realized_return)

                # Compute confidence bucket
                conf_bucket = AttributionFact._confidence_bucket(entry.regime_confidence)

                # Compute provenance hash
                prov_hash = AttributionFact.compute_provenance_hash(
                    entry.trade_id, entry.source_event_id
                )

                fact = AttributionFact(
                    fact_id=fact_id,
                    trade_id=entry.trade_id,
                    source_id=sc.source_id,
                    strategy_or_model_id=sc.model_or_strategy_id,
                    pair=entry.pair,
                    timeframe=entry.timeframe,
                    regime=entry.regime,
                    confidence_bucket=conf_bucket,
                    weighted_return=weighted_return,
                    raw_trade_return=entry.realized_return,
                    contribution_weight=sc.contribution_weight,
                    outcome_classification=outcome,
                    closed_at=entry.closed_at,
                    provenance_hash=prov_hash,
                )
                facts.append(fact)
                accepted += 1

        # Sort facts deterministically by fact_id
        facts.sort(key=lambda f: f.fact_id)

        return AttributionResult(
            facts=facts,
            accepted_count=accepted,
            rejected_count=rejected,
            rejection_diagnostics=diagnostics,
            input_fingerprint=input_fingerprint,
        )

    def compute_metrics(
        self,
        result: AttributionResult,
        entries: list[AttributionInput] | None = None,
    ) -> dict[tuple, DimensionGroupMetrics]:
        """Compute per-dimension-group metrics from an AttributionResult.

        Dimension groupings: (source_id, strategy_or_model_id, pair,
        timeframe, regime, confidence_bucket).

        Args:
            result: The attribution result to compute metrics for.
            entries: Optional original inputs to extract confidence values from.
                If not provided, source_confidence defaults to 0.0 and
                regime_confidence is not averaged.

        Returns:
            Dict mapping canonical dimension group keys to metrics.
        """
        groups: dict[tuple, DimensionGroup] = {}

        # Build lookup for input-level confidence values if entries provided
        entry_lookup: dict[str, AttributionInput] = {}
        if entries is not None:
            for entry in entries:
                entry_lookup[entry.trade_id] = entry

        for fact in result.facts:
            key = (
                fact.source_id,
                fact.strategy_or_model_id or "",
                fact.pair,
                fact.timeframe,
                fact.regime.value,
                fact.confidence_bucket,
            )
            if key not in groups:
                groups[key] = DimensionGroup()

            # Get source confidence from original signal contributions
            source_conf: float | None = None
            regime_conf: float | None = None

            input_entry = entry_lookup.get(fact.trade_id)
            if input_entry is not None:
                regime_conf = input_entry.regime_confidence
                for sc in input_entry.signal_contributions:
                    if sc.source_id == fact.source_id:
                        source_conf = sc.source_confidence
                        break

            groups[key].add(fact, source_confidence=source_conf, regime_confidence=regime_conf)

        # Compute metrics for each group, sorted deterministically
        metrics_dict: dict[tuple, DimensionGroupMetrics] = {}
        for key in sorted(groups.keys()):
            metrics_dict[key] = groups[key].compute_metrics()

        return metrics_dict
