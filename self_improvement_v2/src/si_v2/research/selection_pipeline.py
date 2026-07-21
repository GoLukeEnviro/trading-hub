"""Selection-only evaluation pipeline (C5.4 corrective).

This module implements a **real, executable** selection evaluation that
operates on calibration + walk-forward windows only, with no holdout
dependency. It replaces the C5.3 stub that returned ``EvaluationManifestV1``
from ``build_manifest_v3()`` and used ``EvaluationRunnerV1.evaluate()``
(which includes holdout in its full partition set).

Key types:

- :class:`EvaluationManifestV3` — real manifest v3 with full provenance,
  canonical JSON serialization, and detached ``.sha256`` sidecar support.
- :class:`SelectionBundleV1` — selection-only candle/trade bundle with
  separate selection candle hash and benchmark hash.
- :class:`SelectionOutcomeV1` — outcome tokens: ``PASS_SELECTION``,
  ``EXTEND``, ``REJECT``, ``INVALID``.
- :class:`SelectionArtifactV1` — canonical output with metrics, hashes,
  and a deterministic fingerprint.
- :class:`SelectionRunnerV1` — runs selection evaluation only, rejects
  any holdout data.

Guardrails:

- :func:`evaluate_guardrails` — one shared outcome function for Selection
  and Full/C6 paths. Selection maps success to ``PASS_SELECTION``; Full
  authorized Holdout evaluation maps success to ``PASS_CANDIDATE``.

Pair and regime isolation:

- :func:`normalize_futures_pair` — versioned mapping between raw snapshot
  pairs and canonical futures identifiers (``BTC/USDT`` → ``BTC/USDT:USDT``).
- :func:`classify_regime_at_entry_v2` — pair-isolated, pre-entry-only
  regime classification.

This module is pure research: it cannot start Freqtrade, Docker, or any
trading/runtime process.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import cast

from backtests.cost_model import (
    CostConfig,
    TradeInput,
    calc_mark_to_market_pnl,
    compute_trade_result,
)

from .evaluation_bundle_v1 import (
    BoundaryPolicy,
    CandleV1,
    ContinuationPolicy,
    DataQualityV1,
    PartitionMetricsV1,
    PartitionWindowV1,
    ProfitFactorState,
    RawTradeV1,
    _block_bootstrap,
    _canonical_json,
    _correlation,
    _iso,
    _parse_datetime,
    _quantile,
    _regular_returns,
    _require_finite,
    _require_hash,
    _require_utc,
    _sha256,
    _timeframe_delta,
)
from .gate0_strategy_provenance import StrategyProvenance


# ---------------------------------------------------------------------------
# Futures pair normalization (Check H resolution)
# ---------------------------------------------------------------------------

# Versioned mapping between raw snapshot pair labels and canonical futures
# identifiers. Per Luke's signed #604 manifest, the canonical futures pairs
# for Gate-0 are BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT.
#
# The ``:USDT`` suffix denotes the settlement currency on linear futures.
# Raw snapshot data may use bare ``BTC/USDT`` without the settlement suffix.
# This mapping ensures adapter and candles resolve to one canonical pair
# identity, and that foreign-pair contamination is impossible.

_FUTURES_PAIR_MAPPING_VERSION = "futures-pair-normalization/v1"
_FUTURES_PAIR_MAPPING: dict[str, str] = {
    "BTC/USDT": "BTC/USDT:USDT",
    "ETH/USDT": "ETH/USDT:USDT",
    "SOL/USDT": "SOL/USDT:USDT",
    # Idempotent: already-canonical pairs pass through
    "BTC/USDT:USDT": "BTC/USDT:USDT",
    "ETH/USDT:USDT": "ETH/USDT:USDT",
    "SOL/USDT:USDT": "SOL/USDT:USDT",
}

CANONICAL_FUTURES_PAIRS: tuple[str, ...] = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
)


def normalize_futures_pair(raw_pair: str) -> str:
    """Map a raw snapshot pair to its canonical futures identifier.

    This does NOT silently strip ``:USDT``. It adds the settlement suffix
    when missing, using an explicit versioned mapping table. If the pair
    is not in the mapping, it raises ``ValueError`` to fail closed.

    Examples::

        normalize_futures_pair("BTC/USDT")      -> "BTC/USDT:USDT"
        normalize_futures_pair("BTC/USDT:USDT") -> "BTC/USDT:USDT"
        normalize_futures_pair("UNKNOWN/USDT")  -> ValueError
    """
    if not raw_pair:
        raise ValueError("pair must not be empty")
    if raw_pair in _FUTURES_PAIR_MAPPING:
        return _FUTURES_PAIR_MAPPING[raw_pair]
    raise ValueError(
        f"unknown pair {raw_pair!r}: no futures normalization mapping "
        f"(mapping version {_FUTURES_PAIR_MAPPING_VERSION})"
    )


def pairs_equivalent(pair_a: str, pair_b: str) -> bool:
    """Check whether two pair labels resolve to the same canonical identity."""
    try:
        return normalize_futures_pair(pair_a) == normalize_futures_pair(pair_b)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Selection outcome tokens
# ---------------------------------------------------------------------------


class SelectionOutcomeV1(StrEnum):
    """Outcome of a selection-only evaluation.

    These are distinct from :class:`Gate0Outcome` because selection success
    must never return ``PASS_CANDIDATE`` (that token is reserved for
    post-holdout evaluation). Selection success returns ``PASS_SELECTION``.
    """

    PASS_SELECTION = "PASS_SELECTION"
    """Selection thresholds met. Candidate may proceed to holdout ceremony."""

    EXTEND = "EXTEND"
    """Insufficient trades, duration, regimes, or precision."""

    REJECT = "REJECT"
    """Material guardrail failure or negative edge."""

    INVALID = "INVALID"
    """Data, leakage, or reproducibility defect."""


# ---------------------------------------------------------------------------
# Unified guardrails (one shared implementation for Selection + Full/C6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardrailResult:
    """Result of applying unified guardrails to a set of partition metrics."""

    outcome: SelectionOutcomeV1 | str
    reasons: tuple[str, ...]


def evaluate_guardrails(
    thresholds: EvaluationThresholdsV3,
    authoritative_metrics: Sequence[PartitionMetricsV1],
    *,
    selection_mode: bool,
) -> GuardrailResult:
    """Apply unified strict guardrails to authoritative partition metrics.

    This is the **single** implementation used by both Selection and
    Full/C6 evaluation paths. The only difference is the success token:

    - ``selection_mode=True`` → success maps to ``PASS_SELECTION``
    - ``selection_mode=False`` → success maps to ``PASS_CANDIDATE``

    Guardrail semantics (identical for both paths):

    - ``trades <= 100`` → ``EXTEND``
    - ``duration < 90 days`` → ``EXTEND``
    - ``regimes < 2`` → ``EXTEND``
    - ``drawdown >= 25%`` → ``REJECT``
    - ``finite profit factor <= 1.3`` → ``REJECT``
    - ``bootstrap precision > max CI width`` → ``EXTEND``
    - ``bootstrap mean < min_edge_mean`` → ``REJECT``
    - ``bootstrap lower <= min_edge_lower_bound`` → ``REJECT``
    - Data gaps > 5% → ``INVALID`` (checked at bundle validation level)
    """
    if not authoritative_metrics:
        return GuardrailResult(SelectionOutcomeV1.INVALID, ("NO_AUTHORITATIVE_METRICS",))

    insufficient: set[str] = set()
    for metric in authoritative_metrics:
        if metric.trade_count <= thresholds.min_trades:
            insufficient.add("INSUFFICIENT_TRADES")
        if metric.duration_days < thresholds.min_duration_days:
            insufficient.add("INSUFFICIENT_DURATION")
        if len(metric.regime_trade_counts) < thresholds.min_regimes:
            insufficient.add("INSUFFICIENT_REGIMES")
        if metric.bootstrap.width > thresholds.max_confidence_interval_width:
            insufficient.add("INSUFFICIENT_PRECISION")

    if insufficient:
        return GuardrailResult(SelectionOutcomeV1.EXTEND, tuple(sorted(insufficient)))

    rejected: set[str] = set()
    for metric in authoritative_metrics:
        if metric.max_drawdown_pct >= thresholds.max_drawdown_pct:
            rejected.add("MAX_DRAWDOWN_GUARDRAIL")
        if (
            metric.profit_factor_state is ProfitFactorState.FINITE
            and cast("float", metric.profit_factor) <= thresholds.min_profit_factor
        ):
            rejected.add("PROFIT_FACTOR_GUARDRAIL")
        if (
            metric.bootstrap.mean < thresholds.min_edge_mean
            or metric.bootstrap.lower <= thresholds.min_edge_lower_bound
        ):
            rejected.add("EDGE_THRESHOLD_NOT_MET")

    if rejected:
        return GuardrailResult(SelectionOutcomeV1.REJECT, tuple(sorted(rejected)))

    if selection_mode:
        return GuardrailResult(
            SelectionOutcomeV1.PASS_SELECTION, ("ALL_PREDECLARED_RULES_MET",)
        )
    return GuardrailResult(
        "PASS_CANDIDATE", ("ALL_PREDECLARED_RULES_MET",)
    )


# ---------------------------------------------------------------------------
# EvaluationManifestV3 — real manifest v3 with full provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationManifestV3:
    """Frozen evaluation manifest v3 with complete provenance.

    Key differences from :class:`EvaluationManifestV1`:

    - ``manifest_version`` is always ``"evaluation-manifest/v3"``
    - ``provenance`` includes ``exporter_version`` and ``data_format_version``
    - ``image_digest`` field for Docker image pinning
    - ``pair_mapping_version`` for futures pair normalization provenance
    - Canonical JSON serialization with deterministic roundtrip
    - Detached ``.sha256`` sidecar support
    - No circular/self-referential hash
    """

    manifest_version: str
    manifest_id: str
    approval_reference: str
    strategy_identifier: str
    provenance: FreqtradeProvenanceV3
    data_source: str
    data_snapshot_id: str
    candle_snapshot_sha256: str
    benchmark_snapshot_sha256: str
    exchange: str
    trading_mode: str
    market_type: str
    pairs: tuple[str, ...]
    pair_mapping_version: str
    timeframe: str
    timerange_start: datetime
    timerange_end: datetime
    calibration: PartitionWindowV1
    walk_forward_windows: tuple[PartitionWindowV1, ...]
    holdout: PartitionWindowV1
    cost_config: CostConfig
    thresholds: EvaluationThresholdsV3
    boundary_policy: BoundaryPolicy
    continuation_policy: ContinuationPolicy
    mark_to_market_price_field: str
    image_digest: str

    def __post_init__(self) -> None:
        if self.manifest_version != "evaluation-manifest/v3":
            raise ValueError("V3 manifest_version must be 'evaluation-manifest/v3'")
        for name in (
            "manifest_id",
            "approval_reference",
            "strategy_identifier",
            "data_source",
            "data_snapshot_id",
            "exchange",
            "trading_mode",
            "market_type",
            "image_digest",
        ):
            if not cast("str", getattr(self, name)):
                raise ValueError(f"{name} must not be empty")
        _require_hash(self.candle_snapshot_sha256, 64, "candle_snapshot_sha256")
        _require_hash(self.benchmark_snapshot_sha256, 64, "benchmark_snapshot_sha256")
        if not self.pairs or len(set(self.pairs)) != len(self.pairs):
            raise ValueError("pairs must be a non-empty unique tuple")
        if tuple(sorted(self.pairs)) != self.pairs:
            raise ValueError("pairs must be lexicographically sorted")
        _timeframe_delta(self.timeframe)
        _require_utc(self.timerange_start, "timerange_start")
        _require_utc(self.timerange_end, "timerange_end")
        if self.timerange_end <= self.timerange_start:
            raise ValueError("timerange_end must be after timerange_start")
        if self.boundary_policy is not BoundaryPolicy.STRICT_CONTAINED:
            raise ValueError("boundary_policy must be STRICT_CONTAINED")
        if self.mark_to_market_price_field != "close":
            raise ValueError("V3 mark_to_market_price_field must be 'close'")
        windows = self.partitions
        if not self.walk_forward_windows:
            raise ValueError("at least one walk-forward window is required")
        if windows[0].label != "calibration" or windows[-1].label != "holdout":
            raise ValueError("calibration and holdout labels are reserved")
        if windows[0].start != self.timerange_start:
            raise ValueError("calibration must start at timerange_start")
        if windows[-1].end != self.timerange_end:
            raise ValueError("holdout must end at timerange_end")
        for previous, current in itertools.pairwise(windows):
            if previous.end != current.start:
                raise ValueError("manifest partitions must be contiguous and non-overlapping")
        labels = [window.label for window in windows]
        if len(labels) != len(set(labels)):
            raise ValueError("partition labels must be unique")

    @property
    def partitions(self) -> tuple[PartitionWindowV1, ...]:
        return (self.calibration, *self.walk_forward_windows, self.holdout)

    @property
    def selection_partitions(self) -> tuple[PartitionWindowV1, ...]:
        """Calibration + walk-forward windows only (no holdout)."""
        return (self.calibration, *self.walk_forward_windows)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "manifest_id": self.manifest_id,
            "approval_reference": self.approval_reference,
            "strategy_identifier": self.strategy_identifier,
            "provenance": self.provenance.to_dict(),
            "data_source": self.data_source,
            "data_snapshot_id": self.data_snapshot_id,
            "candle_snapshot_sha256": self.candle_snapshot_sha256,
            "benchmark_snapshot_sha256": self.benchmark_snapshot_sha256,
            "exchange": self.exchange,
            "trading_mode": self.trading_mode,
            "market_type": self.market_type,
            "pairs": list(self.pairs),
            "pair_mapping_version": self.pair_mapping_version,
            "timeframe": self.timeframe,
            "timerange_start": _iso(self.timerange_start),
            "timerange_end": _iso(self.timerange_end),
            "calibration": self.calibration.to_dict(),
            "walk_forward_windows": [row.to_dict() for row in self.walk_forward_windows],
            "holdout": self.holdout.to_dict(),
            "cost_config": asdict(self.cost_config),
            "thresholds": self.thresholds.to_dict(),
            "boundary_policy": self.boundary_policy.value,
            "continuation_policy": self.continuation_policy.value,
            "mark_to_market_price_field": self.mark_to_market_price_field,
            "image_digest": self.image_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EvaluationManifestV3:
        """Parse a complete v3 manifest or fail with ValueError."""
        try:
            provenance_payload = cast("Mapping[str, object]", payload["provenance"])
            cost_payload = cast("Mapping[str, object]", payload["cost_config"])
            threshold_payload = cast("Mapping[str, object]", payload["thresholds"])

            def window(value: object) -> PartitionWindowV1:
                row = cast("Mapping[str, object]", value)
                return PartitionWindowV1(
                    label=cast("str", row["label"]),
                    start=_parse_datetime(row["start"], "partition.start"),
                    end=_parse_datetime(row["end"], "partition.end"),
                )

            return cls(
                manifest_version=cast("str", payload["manifest_version"]),
                manifest_id=cast("str", payload["manifest_id"]),
                approval_reference=cast("str", payload["approval_reference"]),
                strategy_identifier=cast("str", payload["strategy_identifier"]),
                provenance=FreqtradeProvenanceV3(**provenance_payload),
                data_source=cast("str", payload["data_source"]),
                data_snapshot_id=cast("str", payload["data_snapshot_id"]),
                candle_snapshot_sha256=cast("str", payload["candle_snapshot_sha256"]),
                benchmark_snapshot_sha256=cast("str", payload["benchmark_snapshot_sha256"]),
                exchange=cast("str", payload["exchange"]),
                trading_mode=cast("str", payload["trading_mode"]),
                market_type=cast("str", payload["market_type"]),
                pairs=tuple(cast("Sequence[str]", payload["pairs"])),
                pair_mapping_version=cast("str", payload["pair_mapping_version"]),
                timeframe=cast("str", payload["timeframe"]),
                timerange_start=_parse_datetime(payload["timerange_start"], "timerange_start"),
                timerange_end=_parse_datetime(payload["timerange_end"], "timerange_end"),
                calibration=window(payload["calibration"]),
                walk_forward_windows=tuple(
                    window(row)
                    for row in cast("Sequence[object]", payload["walk_forward_windows"])
                ),
                holdout=window(payload["holdout"]),
                cost_config=CostConfig(**cost_payload),
                thresholds=EvaluationThresholdsV3(**threshold_payload),
                boundary_policy=BoundaryPolicy(cast("str", payload["boundary_policy"])),
                continuation_policy=ContinuationPolicy(
                    cast("str", payload["continuation_policy"])
                ),
                mark_to_market_price_field=cast(
                    "str", payload["mark_to_market_price_field"]
                ),
                image_digest=cast("str", payload["image_digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"INVALID_MANIFEST_V3: {exc}") from exc

    def to_canonical_json(self) -> str:
        """Deterministic canonical JSON serialization (no hash field)."""
        return _canonical_json(self.to_dict())

    @property
    def manifest_hash(self) -> str:
        """SHA-256 of the canonical JSON. No circular reference (hash not in payload)."""
        return _sha256(self.to_dict())

    def compute_detached_sha256(self) -> str:
        """Compute the detached SHA-256 sidecar content.

        Format: ``<manifest_hash>  <manifest_id>.json``
        """
        return f"{self.manifest_hash}  {self.manifest_id}.json"

    def verify_detached_sha256(self, sidecar_content: str) -> bool:
        """Verify a detached .sha256 sidecar matches this manifest."""
        expected = self.compute_detached_sha256()
        return sidecar_content.strip() == expected.strip()


@dataclass(frozen=True)
class FreqtradeProvenanceV3:
    """Pinned Freqtrade exporter and strategy provenance (v3).

    Extends v1 with ``image_digest`` (kept at manifest level in v3),
    and explicitly requires all fields that v1 omitted.
    """

    freqtrade_version: str
    strategy_class: str
    strategy_file_sha256: str
    strategy_commit_sha: str
    config_sha256: str
    exporter_version: str
    data_format_version: str

    def __post_init__(self) -> None:
        for name in (
            "freqtrade_version",
            "strategy_class",
            "exporter_version",
            "data_format_version",
        ):
            if not cast("str", getattr(self, name)):
                raise ValueError(f"{name} must not be empty")
        _require_hash(self.strategy_file_sha256, 64, "strategy_file_sha256")
        _require_hash(self.strategy_commit_sha, 40, "strategy_commit_sha")
        _require_hash(self.config_sha256, 64, "config_sha256")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationThresholdsV3:
    """Versioned decision thresholds for v3 manifest.

    Same fields as :class:`EvaluationThresholdsV1` but with v3 identifier.
    All boundaries use unified strict semantics (``<=``, ``>=``).
    """

    threshold_set_id: str
    min_trades: int
    min_duration_days: float
    min_regimes: int
    max_drawdown_pct: float
    min_profit_factor: float
    min_edge_mean: float
    min_edge_lower_bound: float
    max_confidence_interval_width: float
    bootstrap_samples: int
    bootstrap_block_size: int
    confidence_level: float
    bootstrap_seed: int
    initial_equity: float
    max_missing_candles: int
    tail_quantile: float

    def __post_init__(self) -> None:
        if not self.threshold_set_id:
            raise ValueError("threshold_set_id must not be empty")
        if self.min_trades < 1:
            raise ValueError("min_trades must be >= 1")
        if self.min_duration_days < 0:
            raise ValueError("min_duration_days must be >= 0")
        if self.min_regimes < 1:
            raise ValueError("min_regimes must be >= 1")
        if self.bootstrap_samples < 32:
            raise ValueError("bootstrap_samples must be >= 32")
        if self.bootstrap_block_size < 1:
            raise ValueError("bootstrap_block_size must be >= 1")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between 0 and 1")
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be > 0")
        if self.max_missing_candles < 0:
            raise ValueError("max_missing_candles must be >= 0")
        if not 0 < self.tail_quantile <= 0.5:
            raise ValueError("tail_quantile must be in (0, 0.5]")
        for name in (
            "min_duration_days",
            "max_drawdown_pct",
            "min_profit_factor",
            "min_edge_mean",
            "min_edge_lower_bound",
            "max_confidence_interval_width",
            "confidence_level",
            "initial_equity",
            "tail_quantile",
        ):
            _require_finite(cast("float", getattr(self, name)), name)
        if self.max_drawdown_pct < 0:
            raise ValueError("max_drawdown_pct must be >= 0")
        if self.min_profit_factor < 0:
            raise ValueError("min_profit_factor must be >= 0")
        if self.max_confidence_interval_width <= 0:
            raise ValueError("max_confidence_interval_width must be > 0")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# SelectionBundleV1 — selection-only candles/trades with separate hashes
# ---------------------------------------------------------------------------


def _selection_candle_hash(candles: Sequence[CandleV1]) -> str:
    """Hash selection candles (deterministic pair/time order)."""
    rows = sorted(candles, key=lambda row: (row.pair, row.timestamp))
    return _sha256([row.to_dict() for row in rows])


def _selection_data_quality(
    candles: Sequence[CandleV1],
    manifest_pairs: Sequence[str],
    timeframe: str,
    selection_start: datetime,
    selection_end: datetime,
    max_missing_candles: int,
) -> tuple[DataQualityV1, list[str]]:
    """Compute data quality only over the selection time range.

    Returns (DataQualityV1, list_of_error_codes).
    """
    delta = _timeframe_delta(timeframe)
    by_pair: dict[str, list[CandleV1]] = {pair: [] for pair in manifest_pairs}
    seen: set[tuple[str, datetime]] = set()
    duplicates = 0
    for row in candles:
        key = (row.pair, row.timestamp)
        if key in seen:
            duplicates += 1
        seen.add(key)
        if row.pair in by_pair:
            by_pair[row.pair].append(row)
    missing = 0
    gaps: list[tuple[str, str]] = []
    unsupported: list[str] = []
    for pair in manifest_pairs:
        rows = sorted(by_pair.get(pair, []), key=lambda r: r.timestamp)
        if not rows:
            unsupported.append(pair)
            continue
        if rows[0].timestamp > selection_start:
            units = int((rows[0].timestamp - selection_start) / delta)
            missing += units
            gaps.append((_iso(selection_start), _iso(rows[0].timestamp)))
        if rows[-1].timestamp < selection_end:
            units = int((selection_end - rows[-1].timestamp) / delta)
            missing += units
            gaps.append((_iso(rows[-1].timestamp), _iso(selection_end)))
        for previous, current in itertools.pairwise(rows):
            interval_count = int((current.timestamp - previous.timestamp) / delta)
            if interval_count > 1:
                missing += interval_count - 1
                gaps.append((_iso(previous.timestamp), _iso(current.timestamp)))
    quality = DataQualityV1(
        missing_candles=missing,
        duplicate_timestamps=duplicates,
        timestamp_gaps=tuple(sorted(gaps)),
        unsupported_pairs=tuple(sorted(unsupported)),
    )
    errors: list[str] = []
    if quality.duplicate_timestamps:
        errors.append("DUPLICATE_CANDLES")
    if quality.unsupported_pairs:
        errors.append("UNSUPPORTED_PAIR_HISTORY")
    if quality.missing_candles > max_missing_candles:
        errors.append("MISSING_CANDLES")
    return quality, errors


@dataclass(frozen=True)
class SelectionBundleV1:
    """Selection-only candle/trade bundle.

    Contains ONLY calibration + walk-forward candles/trades. No holdout.

    - ``selection_candle_hash`` is computed over selection candles only.
    - ``selection_benchmark_hash`` is computed over selection benchmark only.
    - Data quality is calculated only through ``holdout.start``.
    - Any holdout candle, holdout trade, or trade crossing into holdout
      → validation fails with INVALID.
    """

    manifest: EvaluationManifestV3
    candles: tuple[CandleV1, ...]
    benchmark_candles: tuple[CandleV1, ...]
    raw_trades: tuple[RawTradeV1, ...]
    source_metadata: tuple[tuple[str, str], ...] = ()

    def validate(self) -> tuple[str, ...]:
        """Validate the selection bundle. Returns error codes (empty = valid)."""
        holdout = self.manifest.holdout
        selection_end = holdout.start

        errors: list[str] = []

        # Check: no holdout candles
        holdout_candle_count = sum(
            1 for c in self.candles if holdout.start <= c.timestamp < holdout.end
        )
        if holdout_candle_count > 0:
            errors.append("HOLDOUT_CANDLES_IN_SELECTION_BUNDLE")

        # Check: no holdout trades
        holdout_trade_count = sum(
            1 for t in self.raw_trades if holdout.start <= t.entry_time < holdout.end
        )
        if holdout_trade_count > 0:
            errors.append("HOLDOUT_TRADES_IN_SELECTION_BUNDLE")

        # Check: no trades crossing into holdout
        cross_holdout_count = sum(
            1
            for t in self.raw_trades
            if t.entry_time < selection_end and t.exit_time >= holdout.start
        )
        if cross_holdout_count > 0:
            errors.append("TRADE_CROSSING_INTO_HOLDOUT")

        # Check: all trades within selection timerange
        for trade in self.raw_trades:
            if trade.pair not in self.manifest.pairs:
                errors.append("INVALID_TRADE_PAIR")
                break
            if not (
                self.manifest.timerange_start <= trade.entry_time
                and trade.exit_time <= selection_end
            ):
                errors.append("TRADE_OUTSIDE_SELECTION_TIMERANGE")
                break

        # Check: unique trade IDs
        if len({t.trade_id for t in self.raw_trades}) != len(self.raw_trades):
            errors.append("DUPLICATE_TRADE_ID")

        # Check: chronological trades
        if tuple(sorted(self.raw_trades, key=lambda r: (r.entry_time, r.trade_id))) != self.raw_trades:
            errors.append("NON_CHRONOLOGICAL_TRADES")

        # Data quality over selection range only
        _, dq_errors = _selection_data_quality(
            self.candles,
            self.manifest.pairs,
            self.manifest.timeframe,
            self.manifest.timerange_start,
            selection_end,
            self.manifest.thresholds.max_missing_candles,
        )
        errors.extend(dq_errors)

        return tuple(sorted(set(errors)))

    @property
    def selection_candle_hash(self) -> str:
        return _selection_candle_hash(self.candles)

    @property
    def selection_benchmark_hash(self) -> str:
        return _selection_candle_hash(self.benchmark_candles)


# ---------------------------------------------------------------------------
# SelectionArtifactV1 — canonical output
# ---------------------------------------------------------------------------


@dataclass
class SelectionArtifactV1:
    """Deterministic selection evidence artifact.

    Contains selection-only metrics, hashes, and fingerprint.
    No holdout metrics, hashes, or counts.
    """

    manifest_id: str
    manifest_hash: str
    outcome: SelectionOutcomeV1
    outcome_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    data_quality: DataQualityV1
    partition_metrics: dict[str, PartitionMetricsV1]
    partition_hashes: dict[str, str]
    continuation_trade_ids: tuple[str, ...]
    selection_fingerprint: str
    selection_candle_hash: str
    selection_benchmark_hash: str
    live_authorization: bool = field(default=False, init=False)

    def _hash_payload(self) -> dict[str, object]:
        return {
            "artifact_version": "selection-artifact/v1",
            "manifest_id": self.manifest_id,
            "manifest_hash": self.manifest_hash,
            "outcome": self.outcome.value,
            "outcome_reasons": list(self.outcome_reasons),
            "invalid_reasons": list(self.invalid_reasons),
            "data_quality": self.data_quality.to_dict(),
            "partition_metrics": {
                label: metric.to_dict()
                for label, metric in sorted(self.partition_metrics.items())
            },
            "partition_hashes": dict(sorted(self.partition_hashes.items())),
            "continuation_trade_ids": list(self.continuation_trade_ids),
            "selection_fingerprint": self.selection_fingerprint,
            "selection_candle_hash": self.selection_candle_hash,
            "selection_benchmark_hash": self.selection_benchmark_hash,
            "live_authorization": False,
        }

    @property
    def artifact_hash(self) -> str:
        return _sha256(self._hash_payload())

    def to_dict(self) -> dict[str, object]:
        payload = self._hash_payload()
        payload["artifact_hash"] = self.artifact_hash
        return payload

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


# ---------------------------------------------------------------------------
# SelectionRunnerV1 — runs selection evaluation only
# ---------------------------------------------------------------------------


class SelectionRunnerV1:
    """Evaluate a selection bundle without holdout dependency.

    This is the canonical selection evaluator. It processes calibration
    and walk-forward windows only, rejects holdout data, and uses the
    unified guardrails function with ``selection_mode=True``.
    """

    def evaluate(self, bundle: SelectionBundleV1) -> SelectionArtifactV1:
        """Run selection evaluation on the bundle."""
        manifest = bundle.manifest
        holdout = manifest.holdout
        selection_windows = list(manifest.selection_partitions)
        selection_labels = [w.label for w in selection_windows]

        # Validate
        try:
            invalid = list(bundle.validate())
        except Exception as exc:
            invalid = [f"VALIDATION_ERROR: {exc}"]

        if invalid:
            _, dq_errors = _selection_data_quality(
                bundle.candles,
                manifest.pairs,
                manifest.timeframe,
                manifest.timerange_start,
                holdout.start,
                manifest.thresholds.max_missing_candles,
            )
            quality = DataQualityV1()  # minimal quality for invalid
            return SelectionArtifactV1(
                manifest_id=manifest.manifest_id,
                manifest_hash=manifest.manifest_hash,
                outcome=SelectionOutcomeV1.INVALID,
                outcome_reasons=(),
                invalid_reasons=tuple(sorted(set(invalid))),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=(),
                selection_fingerprint=_sha256(manifest.to_dict()),
                selection_candle_hash=bundle.selection_candle_hash,
                selection_benchmark_hash=bundle.selection_benchmark_hash,
            )

        # Partition trades for selection windows only
        partition_trades: dict[str, list[RawTradeV1]] = {
            label: [] for label in selection_labels
        }
        continuations: list[str] = []
        for trade in bundle.raw_trades:
            labels = [w.label for w in selection_windows if w.contains(trade)]
            if len(labels) == 1:
                partition_trades[labels[0]].append(trade)
            elif manifest.continuation_policy is ContinuationPolicy.REPORT_ONLY:
                continuations.append(trade.trade_id)
            else:
                invalid.append("CROSS_PARTITION_TRADE")

        if invalid:
            quality = DataQualityV1()
            return SelectionArtifactV1(
                manifest_id=manifest.manifest_id,
                manifest_hash=manifest.manifest_hash,
                outcome=SelectionOutcomeV1.INVALID,
                outcome_reasons=(),
                invalid_reasons=tuple(sorted(set(invalid))),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=tuple(sorted(continuations)),
                selection_fingerprint=_sha256(manifest.to_dict()),
                selection_candle_hash=bundle.selection_candle_hash,
                selection_benchmark_hash=bundle.selection_benchmark_hash,
            )

        # Compute metrics for selection windows only
        metrics: dict[str, PartitionMetricsV1] = {}
        hashes: dict[str, str] = {}
        for window in selection_windows:
            rows = tuple(partition_trades[window.label])
            metrics[window.label] = _partition_metrics(bundle, window, rows)
            hashes[window.label] = _partition_view_hash(bundle, window, rows)

        # Compute data quality for the artifact
        quality, _ = _selection_data_quality(
            bundle.candles,
            manifest.pairs,
            manifest.timeframe,
            manifest.timerange_start,
            holdout.start,
            manifest.thresholds.max_missing_candles,
        )

        # Selection fingerprint
        selection_fingerprint = _sha256(
            {
                "manifest": manifest.to_dict(),
                "selection_partition_hashes": {
                    label: hashes[label] for label in selection_labels
                },
                "selection_candle_hash": bundle.selection_candle_hash,
                "selection_benchmark_hash": bundle.selection_benchmark_hash,
            }
        )

        # Outcome from walk-forward windows only (calibration is descriptive)
        wf_metrics = [
            metrics[w.label]
            for w in manifest.walk_forward_windows
            if w.label in metrics
        ]
        result = evaluate_guardrails(
            manifest.thresholds,
            wf_metrics,
            selection_mode=True,
        )

        return SelectionArtifactV1(
            manifest_id=manifest.manifest_id,
            manifest_hash=manifest.manifest_hash,
            outcome=cast("SelectionOutcomeV1", result.outcome),
            outcome_reasons=result.reasons,
            invalid_reasons=(),
            data_quality=quality,
            partition_metrics=dict(sorted(metrics.items())),
            partition_hashes=dict(sorted(hashes.items())),
            continuation_trade_ids=tuple(sorted(continuations)),
            selection_fingerprint=selection_fingerprint,
            selection_candle_hash=bundle.selection_candle_hash,
            selection_benchmark_hash=bundle.selection_benchmark_hash,
        )


def _partition_metrics(
    bundle: SelectionBundleV1,
    window: PartitionWindowV1,
    trades: Sequence[RawTradeV1],
) -> PartitionMetricsV1:
    """Compute partition metrics for a selection window.

    Delegates to the shared metrics engine from evaluation_bundle_v1.
    Uses a temporary EvaluationBundleV1-like interface via duck typing.
    """
    source_rows = sorted(
        (
            row
            for row in bundle.candles
            if window.start <= row.timestamp <= window.end
            and row.pair in bundle.manifest.pairs
        ),
        key=lambda row: (row.timestamp, row.pair),
    )
    benchmark_rows = sorted(
        (
            row
            for row in bundle.benchmark_candles
            if window.start <= row.timestamp <= window.end
        ),
        key=lambda row: (row.timestamp, row.pair),
    )
    timestamps = sorted({row.timestamp for row in source_rows})
    marks = {(row.pair, row.timestamp): row.close for row in source_rows}
    closed_results = {
        trade.trade_id: compute_trade_result(
            trade.to_cost_input(), bundle.manifest.cost_config
        )
        for trade in trades
    }
    equity_values: list[float] = []
    exposed = 0
    for timestamp in timestamps:
        realised = sum(
            closed_results[trade.trade_id].net_pnl
            for trade in trades
            if trade.exit_time <= timestamp
        )
        open_pnl = 0.0
        is_exposed = False
        for trade in trades:
            if trade.entry_time <= timestamp < trade.exit_time:
                is_exposed = True
                elapsed = (timestamp - trade.entry_time).total_seconds() / 3600.0
                open_pnl += calc_mark_to_market_pnl(
                    trade.to_cost_input(),
                    mark_price=marks[(trade.pair, timestamp)],
                    elapsed_hours=elapsed,
                    config=bundle.manifest.cost_config,
                )
        exposed += int(is_exposed)
        equity_values.append(bundle.manifest.thresholds.initial_equity + realised + open_pnl)
    if not equity_values:
        equity_values = [bundle.manifest.thresholds.initial_equity]
    peak = equity_values[0]
    max_drawdown = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    regular_returns = _regular_returns(equity_values)
    mean_return = statistics.fmean(regular_returns) if regular_returns else 0.0
    return_std = statistics.stdev(regular_returns) if len(regular_returns) > 1 else 0.0
    intervals_per_year = timedelta(days=365) / _timeframe_delta(bundle.manifest.timeframe)
    sharpe = mean_return / return_std * math.sqrt(intervals_per_year) if return_std else 0.0
    downside = [value for value in regular_returns if value < 0]
    downside_deviation = (
        math.sqrt(statistics.fmean([value * value for value in downside]))
        if downside
        else 0.0
    )
    results = list(closed_results.values())
    total_gross = sum(result.gross_pnl for result in results)
    total_net = sum(result.net_pnl for result in results)
    total_fees = sum(result.costs.entry_fee + result.costs.exit_fee for result in results)
    total_slippage = sum(result.costs.slippage_cost for result in results)
    total_funding = sum(result.costs.funding_cost for result in results)
    gross_profit = sum(result.net_pnl for result in results if result.net_pnl > 0)
    gross_loss = abs(sum(result.net_pnl for result in results if result.net_pnl < 0))
    if not results:
        profit_factor = None
        profit_factor_state = ProfitFactorState.NO_TRADES
    elif gross_loss == 0:
        profit_factor = None
        profit_factor_state = ProfitFactorState.NO_LOSSES
    else:
        profit_factor = gross_profit / gross_loss
        profit_factor_state = ProfitFactorState.FINITE
    average_equity = statistics.fmean(equity_values)
    traded_notional = sum(
        (trade.entry_price + trade.exit_price) * trade.quantity for trade in trades
    )
    turnover = traded_notional / average_equity if average_equity > 0 else 0.0
    losses = sorted(result.net_pnl for result in results if result.net_pnl < 0)
    tail_count = max(1, math.ceil(len(results) * bundle.manifest.thresholds.tail_quantile))
    tail_loss = abs(sum(losses[:tail_count])) if losses else 0.0
    regime_counts: dict[str, int] = {}
    regime_pnl: dict[str, float] = {}
    for trade in trades:
        regime_counts[trade.regime] = regime_counts.get(trade.regime, 0) + 1
        regime_pnl[trade.regime] = (
            regime_pnl.get(trade.regime, 0.0) + closed_results[trade.trade_id].net_pnl
        )
    benchmark_returns = _regular_returns([row.close for row in benchmark_rows])
    duration_days = (window.end - window.start).total_seconds() / 86400.0
    return_pct = total_net / bundle.manifest.thresholds.initial_equity * 100.0
    annual_return_pct = return_pct * (365.0 / duration_days) if duration_days else 0.0
    calmar = annual_return_pct / (max_drawdown * 100.0) if max_drawdown else 0.0
    return PartitionMetricsV1(
        label=window.label,
        trade_count=len(trades),
        duration_days=duration_days,
        total_gross_pnl=total_gross,
        total_net_pnl=total_net,
        total_fees=total_fees,
        total_slippage=total_slippage,
        total_funding=total_funding,
        return_pct=return_pct,
        profit_factor=profit_factor,
        profit_factor_state=profit_factor_state,
        max_drawdown_pct=max_drawdown * 100.0,
        sharpe_ratio=sharpe,
        calmar_ratio=calmar,
        downside_deviation=downside_deviation,
        exposure_pct=exposed / len(timestamps) * 100.0 if timestamps else 0.0,
        turnover=turnover,
        tail_loss_pct=tail_loss / bundle.manifest.thresholds.initial_equity * 100.0,
        regime_trade_counts=regime_counts,
        regime_net_pnl=regime_pnl,
        benchmark_correlation=_correlation(regular_returns, benchmark_returns),
        bootstrap=_block_bootstrap(regular_returns, bundle.manifest.thresholds),
    )


def _partition_view_hash(
    bundle: SelectionBundleV1,
    window: PartitionWindowV1,
    trades: Sequence[RawTradeV1],
) -> str:
    """Hash a partition view within the selection bundle."""
    return _sha256(
        {
            "window": window.to_dict(),
            "candles": [
                row.to_dict()
                for row in sorted(bundle.candles, key=lambda item: (item.pair, item.timestamp))
                if window.start <= row.timestamp <= window.end
            ],
            "benchmark_candles": [
                row.to_dict()
                for row in sorted(
                    bundle.benchmark_candles,
                    key=lambda item: (item.pair, item.timestamp),
                )
                if window.start <= row.timestamp <= window.end
            ],
            "trades": [row.to_dict() for row in trades],
        }
    )
