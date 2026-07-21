"""Versioned, deterministic edge-evidence contract for Phase 0A.

The module consumes one canonical candle/trade bundle, derives all temporal
views from manifest boundaries, applies the shared ``backtests.cost_model``
engine, and emits research evidence only.  It cannot start Freqtrade, Docker,
or any trading/runtime process.
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
from enum import Enum, StrEnum
from typing import cast

from backtests.cost_model import (
    CostConfig,
    TradeInput,
    calc_mark_to_market_pnl,
    compute_trade_result,
)

from .edge_evidence_harness import Gate0Outcome


class InvalidEvaluationError(ValueError):
    """Stable fail-closed error raised at a typed input boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class BoundaryPolicy(StrEnum):
    """Authoritative trade-to-partition assignment policy."""

    STRICT_CONTAINED = "STRICT_CONTAINED"


class ContinuationPolicy(StrEnum):
    """Treatment of trades crossing a manifest partition boundary."""

    REPORT_ONLY = "CONTINUATION_REPORT_ONLY"
    FORBID = "FORBID"


class ProfitFactorState(StrEnum):
    """Finite JSON representation of profit-factor edge cases."""

    FINITE = "FINITE"
    NO_LOSSES = "NO_LOSSES"
    NO_TRADES = "NO_TRADES"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be UTC-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")


def _require_finite(value: float, field_name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")


def _require_hash(value: str, length: int, field_name: str) -> None:
    if len(value) != length or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field_name} must be a lowercase {length}-character hex digest")


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_utc(parsed, field_name)
    return parsed


def _normalise(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidEvaluationError("NON_FINITE_ARTIFACT", "NaN/Infinity is forbidden")
        rounded = round(value, 12)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, Mapping):
        return {
            str(key): _normalise(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_normalise(item) for item in value]
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        _normalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _timeframe_delta(timeframe: str) -> timedelta:
    if len(timeframe) < 2 or not timeframe[:-1].isdigit():
        raise ValueError(f"unsupported timeframe {timeframe!r}")
    amount = int(timeframe[:-1])
    unit = timeframe[-1]
    if amount <= 0:
        raise ValueError("timeframe amount must be positive")
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise ValueError(f"unsupported timeframe unit {unit!r}")


@dataclass(frozen=True)
class PartitionWindowV1:
    """Half-open manifest partition ``[start, end)``."""

    label: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("partition label must not be empty")
        _require_utc(self.start, "partition.start")
        _require_utc(self.end, "partition.end")
        if self.end <= self.start:
            raise ValueError("partition end must be after start")

    def contains(self, trade: RawTradeV1) -> bool:
        return self.start <= trade.entry_time and trade.exit_time < self.end

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "start": _iso(self.start), "end": _iso(self.end)}


@dataclass(frozen=True)
class CandleV1:
    """One canonical UTC OHLCV candle."""

    pair: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not self.pair:
            raise ValueError("pair must not be empty")
        _require_utc(self.timestamp, "timestamp")
        for name in ("open", "high", "low", "close"):
            value = cast("float", getattr(self, name))
            _require_finite(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be > 0")
        _require_finite(self.volume, "volume")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is inconsistent with OHLC values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is inconsistent with OHLC values")

    def to_dict(self) -> dict[str, object]:
        return {
            "pair": self.pair,
            "timestamp": _iso(self.timestamp),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class RawTradeV1:
    """Chronological raw trade input; PnL is intentionally not accepted."""

    trade_id: str
    pair: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: str
    regime: str

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("trade_id must not be empty")
        if not self.pair:
            raise ValueError("pair must not be empty")
        _require_utc(self.entry_time, "entry_time")
        _require_utc(self.exit_time, "exit_time")
        if self.exit_time <= self.entry_time:
            raise ValueError("exit_time must be after entry_time")
        TradeInput(
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            quantity=self.quantity,
            side=self.side,
            hold_hours=self.hold_hours,
        )
        if not self.regime:
            raise ValueError("regime must not be empty")

    @property
    def hold_hours(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds() / 3600.0

    def to_cost_input(self) -> TradeInput:
        return TradeInput(
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            quantity=self.quantity,
            side=self.side,
            hold_hours=self.hold_hours,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "pair": self.pair,
            "entry_time": _iso(self.entry_time),
            "exit_time": _iso(self.exit_time),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "side": self.side,
            "regime": self.regime,
        }


def canonical_candle_hash(candles: Sequence[CandleV1]) -> str:
    """Hash canonical candle bytes in deterministic pair/time order."""

    rows = sorted(candles, key=lambda row: (row.pair, row.timestamp))
    return _sha256([row.to_dict() for row in rows])


@dataclass(frozen=True)
class FreqtradeProvenanceV1:
    """Pinned Freqtrade exporter and strategy provenance."""

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
class EvaluationThresholdsV1:
    """Complete, versioned decision set with no default decision values."""

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


@dataclass(frozen=True)
class EvaluationManifestV1:
    """Frozen evaluation contract approved before holdout inspection."""

    manifest_version: str
    manifest_id: str
    approval_reference: str
    strategy_identifier: str
    provenance: FreqtradeProvenanceV1
    data_source: str
    data_snapshot_id: str
    candle_snapshot_sha256: str
    benchmark_snapshot_sha256: str
    exchange: str
    trading_mode: str
    market_type: str
    pairs: tuple[str, ...]
    timeframe: str
    timerange_start: datetime
    timerange_end: datetime
    calibration: PartitionWindowV1
    walk_forward_windows: tuple[PartitionWindowV1, ...]
    holdout: PartitionWindowV1
    cost_config: CostConfig
    thresholds: EvaluationThresholdsV1
    boundary_policy: BoundaryPolicy
    continuation_policy: ContinuationPolicy
    mark_to_market_price_field: str

    def __post_init__(self) -> None:
        if self.manifest_version != "evaluation-manifest/v1":
            raise ValueError("unsupported manifest_version")
        for name in (
            "manifest_id",
            "approval_reference",
            "strategy_identifier",
            "data_source",
            "data_snapshot_id",
            "exchange",
            "trading_mode",
            "market_type",
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
            raise ValueError("V1 mark_to_market_price_field must be 'close'")
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
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EvaluationManifestV1:
        """Parse a complete manifest or fail with ``INVALID_MANIFEST``."""

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
                provenance=FreqtradeProvenanceV1(**provenance_payload),
                data_source=cast("str", payload["data_source"]),
                data_snapshot_id=cast("str", payload["data_snapshot_id"]),
                candle_snapshot_sha256=cast("str", payload["candle_snapshot_sha256"]),
                benchmark_snapshot_sha256=cast("str", payload["benchmark_snapshot_sha256"]),
                exchange=cast("str", payload["exchange"]),
                trading_mode=cast("str", payload["trading_mode"]),
                market_type=cast("str", payload["market_type"]),
                pairs=tuple(cast("Sequence[str]", payload["pairs"])),
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
                thresholds=EvaluationThresholdsV1(**threshold_payload),
                boundary_policy=BoundaryPolicy(cast("str", payload["boundary_policy"])),
                continuation_policy=ContinuationPolicy(
                    cast("str", payload["continuation_policy"])
                ),
                mark_to_market_price_field=cast(
                    "str", payload["mark_to_market_price_field"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidEvaluationError("INVALID_MANIFEST", str(exc)) from exc


@dataclass(frozen=True)
class DataQualityV1:
    """Deterministic candle quality evidence."""

    missing_candles: int = 0
    duplicate_timestamps: int = 0
    timestamp_gaps: tuple[tuple[str, str], ...] = ()
    unsupported_pairs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "missing_candles": self.missing_candles,
            "duplicate_timestamps": self.duplicate_timestamps,
            "timestamp_gaps": [list(gap) for gap in self.timestamp_gaps],
            "unsupported_pairs": list(self.unsupported_pairs),
        }


def _data_quality(bundle: EvaluationBundleV1) -> DataQualityV1:
    delta = _timeframe_delta(bundle.manifest.timeframe)
    by_pair: dict[str, list[CandleV1]] = {pair: [] for pair in bundle.manifest.pairs}
    seen: set[tuple[str, datetime]] = set()
    duplicates = 0
    for row in bundle.candles:
        key = (row.pair, row.timestamp)
        if key in seen:
            duplicates += 1
        seen.add(key)
        if row.pair in by_pair:
            by_pair[row.pair].append(row)
    missing = 0
    gaps: list[tuple[str, str]] = []
    unsupported: list[str] = []
    for pair in bundle.manifest.pairs:
        rows = sorted(by_pair[pair], key=lambda row: row.timestamp)
        if not rows:
            unsupported.append(pair)
            continue
        if rows[0].timestamp > bundle.manifest.timerange_start:
            units = int((rows[0].timestamp - bundle.manifest.timerange_start) / delta)
            missing += units
            gaps.append((_iso(bundle.manifest.timerange_start), _iso(rows[0].timestamp)))
        if rows[-1].timestamp < bundle.manifest.timerange_end:
            units = int((bundle.manifest.timerange_end - rows[-1].timestamp) / delta)
            missing += units
            gaps.append((_iso(rows[-1].timestamp), _iso(bundle.manifest.timerange_end)))
        for previous, current in itertools.pairwise(rows):
            interval_count = int((current.timestamp - previous.timestamp) / delta)
            if interval_count > 1:
                missing += interval_count - 1
                gaps.append((_iso(previous.timestamp), _iso(current.timestamp)))
    return DataQualityV1(
        missing_candles=missing,
        duplicate_timestamps=duplicates,
        timestamp_gaps=tuple(sorted(gaps)),
        unsupported_pairs=tuple(sorted(unsupported)),
    )


@dataclass(frozen=True)
class EvaluationBundleV1:
    """One canonical input source; all partitions are derived views."""

    manifest: EvaluationManifestV1
    candles: tuple[CandleV1, ...]
    benchmark_candles: tuple[CandleV1, ...]
    raw_trades: tuple[RawTradeV1, ...]
    source_metadata: tuple[tuple[str, str], ...] = ()

    def validate(self) -> tuple[str, ...]:
        if tuple(sorted(self.source_metadata)) != self.source_metadata:
            raise InvalidEvaluationError(
                "INVALID_SOURCE_METADATA", "source_metadata must be sorted"
            )
        if len({trade.trade_id for trade in self.raw_trades}) != len(self.raw_trades):
            raise InvalidEvaluationError("DUPLICATE_TRADE_ID", "trade ids must be unique")
        if tuple(sorted(self.raw_trades, key=lambda row: (row.entry_time, row.trade_id))) != self.raw_trades:
            raise InvalidEvaluationError(
                "NON_CHRONOLOGICAL_TRADES", "raw trades must be chronological"
            )
        for trade in self.raw_trades:
            if trade.pair not in self.manifest.pairs:
                raise InvalidEvaluationError(
                    "INVALID_TRADE_PAIR", f"{trade.pair} is outside manifest pairs"
                )
            if not (
                self.manifest.timerange_start <= trade.entry_time
                and trade.exit_time <= self.manifest.timerange_end
            ):
                raise InvalidEvaluationError(
                    "TRADE_OUTSIDE_TIMERANGE", f"trade {trade.trade_id} is out of range"
                )
        errors: list[str] = []
        if canonical_candle_hash(self.candles) != self.manifest.candle_snapshot_sha256:
            errors.append("CANDLE_SNAPSHOT_HASH_MISMATCH")
        if (
            canonical_candle_hash(self.benchmark_candles)
            != self.manifest.benchmark_snapshot_sha256
        ):
            errors.append("BENCHMARK_SNAPSHOT_HASH_MISMATCH")
        quality = _data_quality(self)
        if quality.duplicate_timestamps:
            errors.append("DUPLICATE_CANDLES")
        if quality.unsupported_pairs:
            errors.append("UNSUPPORTED_PAIR_HISTORY")
        if quality.missing_candles > self.manifest.thresholds.max_missing_candles:
            errors.append("MISSING_CANDLES")
        return tuple(sorted(set(errors)))


@dataclass(frozen=True)
class BootstrapIntervalV1:
    mean: float
    lower: float
    upper: float

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def to_dict(self) -> dict[str, object]:
        return {
            "mean": self.mean,
            "lower": self.lower,
            "upper": self.upper,
            "width": self.width,
        }


@dataclass(frozen=True)
class PartitionMetricsV1:
    label: str
    trade_count: int
    duration_days: float
    total_gross_pnl: float
    total_net_pnl: float
    total_fees: float
    total_slippage: float
    total_funding: float
    return_pct: float
    profit_factor: float | None
    profit_factor_state: ProfitFactorState
    max_drawdown_pct: float
    sharpe_ratio: float
    calmar_ratio: float
    downside_deviation: float
    exposure_pct: float
    turnover: float
    tail_loss_pct: float
    regime_trade_counts: dict[str, int]
    regime_net_pnl: dict[str, float]
    benchmark_correlation: float | None
    bootstrap: BootstrapIntervalV1

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "trade_count": self.trade_count,
            "duration_days": self.duration_days,
            "total_gross_pnl": self.total_gross_pnl,
            "total_net_pnl": self.total_net_pnl,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_funding": self.total_funding,
            "return_pct": self.return_pct,
            "profit_factor": self.profit_factor,
            "profit_factor_state": self.profit_factor_state.value,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "calmar_ratio": self.calmar_ratio,
            "downside_deviation": self.downside_deviation,
            "exposure_pct": self.exposure_pct,
            "turnover": self.turnover,
            "tail_loss_pct": self.tail_loss_pct,
            "regime_trade_counts": dict(sorted(self.regime_trade_counts.items())),
            "regime_net_pnl": dict(sorted(self.regime_net_pnl.items())),
            "benchmark_correlation": self.benchmark_correlation,
            "bootstrap": self.bootstrap.to_dict(),
        }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def _block_bootstrap(
    returns: Sequence[float], thresholds: EvaluationThresholdsV1
) -> BootstrapIntervalV1:
    if not returns:
        return BootstrapIntervalV1(0.0, 0.0, 0.0)
    sample_size = len(returns)
    block_size = min(thresholds.bootstrap_block_size, sample_size)
    rng = random.Random(thresholds.bootstrap_seed)
    sample_means: list[float] = []
    for _ in range(thresholds.bootstrap_samples):
        sampled: list[float] = []
        while len(sampled) < sample_size:
            start = rng.randrange(sample_size)
            sampled.extend(
                returns[(start + offset) % sample_size]
                for offset in range(block_size)
            )
        sample_means.append(statistics.fmean(sampled[:sample_size]))
    alpha = (1.0 - thresholds.confidence_level) / 2.0
    return BootstrapIntervalV1(
        mean=statistics.fmean(returns),
        lower=_quantile(sample_means, alpha),
        upper=_quantile(sample_means, 1.0 - alpha),
    )


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    count = min(len(left), len(right))
    if count < 2:
        return None
    a = list(left[-count:])
    b = list(right[-count:])
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    denominator = math.sqrt(
        sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b)
    )
    return numerator / denominator if denominator else None


def _regular_returns(values: Sequence[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in itertools.pairwise(values):
        returns.append((current / previous - 1.0) if previous else 0.0)
    return returns


def _partition_metrics(
    bundle: EvaluationBundleV1,
    window: PartitionWindowV1,
    trades: Sequence[RawTradeV1],
) -> PartitionMetricsV1:
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


@dataclass
class EvaluationArtifactV1:
    """Deterministic machine and human evidence artifact."""

    manifest_id: str
    outcome: Gate0Outcome
    outcome_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    data_quality: DataQualityV1
    partition_metrics: dict[str, PartitionMetricsV1]
    partition_hashes: dict[str, str]
    continuation_trade_ids: tuple[str, ...]
    selection_fingerprint: str
    live_authorization: bool = field(default=False, init=False)

    def _hash_payload(self) -> dict[str, object]:
        return {
            "artifact_version": "evaluation-artifact/v1",
            "manifest_id": self.manifest_id,
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

    def to_markdown(self) -> str:
        lines = [
            "# Evaluation Artifact V1",
            "",
            f"- Manifest: `{self.manifest_id}`",
            f"- Outcome: `{self.outcome.value}`",
            f"- Artifact SHA-256: `{self.artifact_hash}`",
            "- Live authorization: `false`",
            "",
            "| Partition | Trades | Net PnL | Max DD % | CI lower | CI upper |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for label, metric in sorted(self.partition_metrics.items()):
            lines.append(
                f"| {label} | {metric.trade_count} | {metric.total_net_pnl:.12g} "
                f"| {metric.max_drawdown_pct:.12g} | {metric.bootstrap.lower:.12g} "
                f"| {metric.bootstrap.upper:.12g} |"
            )
        if self.outcome_reasons:
            lines.extend(("", "Reasons: " + ", ".join(self.outcome_reasons)))
        if self.invalid_reasons:
            lines.extend(("", "Invalid: " + ", ".join(self.invalid_reasons)))
        return "\n".join(lines) + "\n"


def _partition_view_hash(
    bundle: EvaluationBundleV1,
    window: PartitionWindowV1,
    trades: Sequence[RawTradeV1],
) -> str:
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


class EvaluationRunnerV1:
    """Evaluate a typed bundle without mutating strategies or runtime."""

    def evaluate(self, bundle: EvaluationBundleV1) -> EvaluationArtifactV1:
        quality = _data_quality(bundle)
        try:
            invalid = list(bundle.validate())
        except InvalidEvaluationError as exc:
            invalid = [exc.code]
        partition_trades: dict[str, list[RawTradeV1]] = {
            window.label: [] for window in bundle.manifest.partitions
        }
        continuations: list[str] = []
        for trade in bundle.raw_trades:
            labels = [
                window.label
                for window in bundle.manifest.partitions
                if window.contains(trade)
            ]
            if len(labels) == 1:
                partition_trades[labels[0]].append(trade)
            elif bundle.manifest.continuation_policy is ContinuationPolicy.REPORT_ONLY:
                continuations.append(trade.trade_id)
            else:
                invalid.append("CROSS_PARTITION_TRADE")
        if invalid:
            return EvaluationArtifactV1(
                manifest_id=bundle.manifest.manifest_id,
                outcome=Gate0Outcome.INVALID,
                outcome_reasons=(),
                invalid_reasons=tuple(sorted(set(invalid))),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=tuple(sorted(continuations)),
                selection_fingerprint=_sha256(bundle.manifest.to_dict()),
            )
        metrics: dict[str, PartitionMetricsV1] = {}
        hashes: dict[str, str] = {}
        for window in bundle.manifest.partitions:
            rows = tuple(partition_trades[window.label])
            metrics[window.label] = _partition_metrics(bundle, window, rows)
            hashes[window.label] = _partition_view_hash(bundle, window, rows)
        selection_labels = [
            bundle.manifest.calibration.label,
            *(window.label for window in bundle.manifest.walk_forward_windows),
        ]
        selection_fingerprint = _sha256(
            {
                "manifest": bundle.manifest.to_dict(),
                "selection_partition_hashes": {
                    label: hashes[label] for label in selection_labels
                },
            }
        )
        outcome, reasons = self._outcome(bundle.manifest, metrics)
        return EvaluationArtifactV1(
            manifest_id=bundle.manifest.manifest_id,
            outcome=outcome,
            outcome_reasons=reasons,
            invalid_reasons=(),
            data_quality=quality,
            partition_metrics=dict(sorted(metrics.items())),
            partition_hashes=dict(sorted(hashes.items())),
            continuation_trade_ids=tuple(sorted(continuations)),
            selection_fingerprint=selection_fingerprint,
        )

    @staticmethod
    def _outcome(
        manifest: EvaluationManifestV1,
        metrics: Mapping[str, PartitionMetricsV1],
    ) -> tuple[Gate0Outcome, tuple[str, ...]]:
        """Full evaluation outcome using unified guardrails (C5.4 corrective).

        Uses the shared ``evaluate_guardrails`` function so Selection and Full
        runners enforce the exact same strict boundaries:
        ``<=100 trades -> EXTEND``, ``>=25% DD -> REJECT``,
        ``finite <=1.3 PF -> REJECT``.  Success maps to ``PASS_CANDIDATE``
        for the C6 holdout ceremony.
        """
        from si_v2.research.selection_pipeline import (
            GuardrailResult,
            SelectionOutcomeV1,
            evaluate_guardrails,
        )

        authoritative = [
            metrics[window.label]
            for window in (*manifest.walk_forward_windows, manifest.holdout)
            if window.label in metrics
        ]
        result: GuardrailResult = evaluate_guardrails(
            manifest.thresholds, authoritative, selection_mode=False
        )
        if result.outcome == SelectionOutcomeV1.PASS_SELECTION:
            return Gate0Outcome.PASS_CANDIDATE, result.reasons
        if result.outcome == SelectionOutcomeV1.EXTEND:
            return Gate0Outcome.EXTEND, result.reasons
        if result.outcome == SelectionOutcomeV1.REJECT:
            return Gate0Outcome.REJECT, result.reasons
        return Gate0Outcome.INVALID, result.reasons

    def evaluate_selection(
        self, bundle: EvaluationBundleV1
    ) -> EvaluationArtifactV1:
        """Selection-only evaluation: calibration + walk-forward windows only.

        This method:
        - Processes calibration, walk-forward 1, and walk-forward 2.
        - Calibration is treated as descriptive only.
        - Walk-forward partitions are authoritative for the outcome.
        - Rejects any holdout candles or holdout trades in the bundle
          (fail-closed INVALID).
        - Never materializes holdout metrics or holdout hashes.

        The full :meth:`evaluate` method is reserved for the later C6
        holdout ceremony.
        """
        holdout = bundle.manifest.holdout

        # Fail-closed: reject any holdout candles in the bundle
        holdout_candle_count = sum(
            1
            for c in bundle.candles
            if holdout.start <= c.timestamp < holdout.end
        )
        if holdout_candle_count > 0:
            quality = _data_quality(bundle)
            return EvaluationArtifactV1(
                manifest_id=bundle.manifest.manifest_id,
                outcome=Gate0Outcome.INVALID,
                outcome_reasons=(),
                invalid_reasons=("HOLDOUT_CANDLES_IN_SELECTION_BUNDLE",),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=(),
                selection_fingerprint=_sha256(bundle.manifest.to_dict()),
            )

        # Fail-closed: reject any holdout trades in the bundle
        holdout_trade_count = sum(
            1
            for t in bundle.raw_trades
            if holdout.start <= t.entry_time < holdout.end
        )
        if holdout_trade_count > 0:
            quality = _data_quality(bundle)
            return EvaluationArtifactV1(
                manifest_id=bundle.manifest.manifest_id,
                outcome=Gate0Outcome.INVALID,
                outcome_reasons=(),
                invalid_reasons=("HOLDOUT_TRADES_IN_SELECTION_BUNDLE",),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=(),
                selection_fingerprint=_sha256(bundle.manifest.to_dict()),
            )

        # Standard validation
        quality = _data_quality(bundle)
        try:
            invalid = list(bundle.validate())
        except InvalidEvaluationError as exc:
            invalid = [exc.code]

        if invalid:
            return EvaluationArtifactV1(
                manifest_id=bundle.manifest.manifest_id,
                outcome=Gate0Outcome.INVALID,
                outcome_reasons=(),
                invalid_reasons=tuple(sorted(set(invalid))),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=(),
                selection_fingerprint=_sha256(bundle.manifest.to_dict()),
            )

        # Partition trades for selection windows only
        selection_windows = [
            bundle.manifest.calibration,
            *bundle.manifest.walk_forward_windows,
        ]
        selection_labels = [w.label for w in selection_windows]
        partition_trades: dict[str, list[RawTradeV1]] = {
            label: [] for label in selection_labels
        }
        continuations: list[str] = []
        for trade in bundle.raw_trades:
            labels = [
                w.label for w in selection_windows if w.contains(trade)
            ]
            if len(labels) == 1:
                partition_trades[labels[0]].append(trade)
            elif bundle.manifest.continuation_policy is ContinuationPolicy.REPORT_ONLY:
                continuations.append(trade.trade_id)
            else:
                invalid.append("CROSS_PARTITION_TRADE")

        if invalid:
            return EvaluationArtifactV1(
                manifest_id=bundle.manifest.manifest_id,
                outcome=Gate0Outcome.INVALID,
                outcome_reasons=(),
                invalid_reasons=tuple(sorted(set(invalid))),
                data_quality=quality,
                partition_metrics={},
                partition_hashes={},
                continuation_trade_ids=tuple(sorted(continuations)),
                selection_fingerprint=_sha256(bundle.manifest.to_dict()),
            )

        # Compute metrics for selection windows only (no holdout)
        metrics: dict[str, PartitionMetricsV1] = {}
        hashes: dict[str, str] = {}
        for window in selection_windows:
            rows = tuple(partition_trades[window.label])
            metrics[window.label] = _partition_metrics(bundle, window, rows)
            hashes[window.label] = _partition_view_hash(bundle, window, rows)

        selection_fingerprint = _sha256(
            {
                "manifest": bundle.manifest.to_dict(),
                "selection_partition_hashes": {
                    label: hashes[label] for label in selection_labels
                },
            }
        )

        # Outcome from walk-forward windows only (calibration is descriptive)
        outcome, reasons = self._selection_outcome(bundle.manifest, metrics)

        return EvaluationArtifactV1(
            manifest_id=bundle.manifest.manifest_id,
            outcome=outcome,
            outcome_reasons=reasons,
            invalid_reasons=(),
            data_quality=quality,
            partition_metrics=dict(sorted(metrics.items())),
            partition_hashes=dict(sorted(hashes.items())),
            continuation_trade_ids=tuple(sorted(continuations)),
            selection_fingerprint=selection_fingerprint,
        )

    @staticmethod
    def _selection_outcome(
        manifest: EvaluationManifestV1,
        metrics: Mapping[str, PartitionMetricsV1],
    ) -> tuple[Gate0Outcome, tuple[str, ...]]:
        """Selection outcome: walk-forward windows are authoritative.

        Calibration metrics are descriptive only — they do not gate the
        outcome. Only walk-forward partitions decide EXTEND/REJECT/PASS.
        """
        authoritative = [
            metrics[window.label]
            for window in manifest.walk_forward_windows
            if window.label in metrics
        ]
        if not authoritative:
            return Gate0Outcome.INVALID, ("NO_WALK_FORWARD_METRICS",)

        insufficient: set[str] = set()
        for metric in authoritative:
            if metric.trade_count <= manifest.thresholds.min_trades:
                insufficient.add("INSUFFICIENT_TRADES")
            if metric.duration_days < manifest.thresholds.min_duration_days:
                insufficient.add("INSUFFICIENT_DURATION")
            if len(metric.regime_trade_counts) < manifest.thresholds.min_regimes:
                insufficient.add("INSUFFICIENT_REGIMES")
            if (
                metric.bootstrap.width
                > manifest.thresholds.max_confidence_interval_width
            ):
                insufficient.add("INSUFFICIENT_PRECISION")
        if insufficient:
            return Gate0Outcome.EXTEND, tuple(sorted(insufficient))

        rejected: set[str] = set()
        for metric in authoritative:
            if metric.max_drawdown_pct >= manifest.thresholds.max_drawdown_pct:
                rejected.add("MAX_DRAWDOWN_GUARDRAIL")
            if (
                metric.profit_factor_state is ProfitFactorState.FINITE
                and cast("float", metric.profit_factor)
                <= manifest.thresholds.min_profit_factor
            ):
                rejected.add("PROFIT_FACTOR_GUARDRAIL")
            if (
                metric.bootstrap.mean < manifest.thresholds.min_edge_mean
                or metric.bootstrap.lower
                <= manifest.thresholds.min_edge_lower_bound
            ):
                rejected.add("EDGE_THRESHOLD_NOT_MET")
        if rejected:
            return Gate0Outcome.REJECT, tuple(sorted(rejected))
        return Gate0Outcome.PASS_CANDIDATE, ("ALL_PREDECLARED_RULES_MET",)


class FreqtradeExportAdapterV1:
    """Pure importer for already-exported Freqtrade trade artifacts."""

    def import_trades(
        self,
        export: Mapping[str, object],
        manifest: EvaluationManifestV1,
    ) -> tuple[RawTradeV1, ...]:
        try:
            actual = cast("Mapping[str, object]", export["provenance"])
            expected: dict[str, object] = {
                **manifest.provenance.to_dict(),
                "exchange": manifest.exchange,
                "trading_mode": manifest.trading_mode,
                "pairs": list(manifest.pairs),
                "timeframe": manifest.timeframe,
                "timerange": [
                    manifest.timerange_start.isoformat(),
                    manifest.timerange_end.isoformat(),
                ],
            }
            mismatches = [
                key for key, value in expected.items() if actual.get(key) != value
            ]
            if mismatches:
                raise InvalidEvaluationError(
                    "FREQTRADE_PROVENANCE_MISMATCH",
                    "mismatched fields: " + ", ".join(sorted(mismatches)),
                )
            rows: list[RawTradeV1] = []
            for raw in cast("Sequence[object]", export["trades"]):
                trade = cast("Mapping[str, object]", raw)
                rows.append(
                    RawTradeV1(
                        trade_id=cast("str", trade["trade_id"]),
                        pair=cast("str", trade["pair"]),
                        entry_time=_parse_datetime(trade["open_date"], "open_date"),
                        exit_time=_parse_datetime(trade["close_date"], "close_date"),
                        entry_price=float(cast("float", trade["open_rate"])),
                        exit_price=float(cast("float", trade["close_rate"])),
                        quantity=float(cast("float", trade["amount"])),
                        side="short" if trade["is_short"] is True else "long",
                        regime=cast("str", trade["regime"]),
                    )
                )
            return tuple(sorted(rows, key=lambda row: (row.entry_time, row.trade_id)))
        except InvalidEvaluationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidEvaluationError("INVALID_FREQTRADE_EXPORT", str(exc)) from exc
