"""Evidence Input Pipeline — Phase 2, issue #62.

Reads trade attribution data from the source_regime_stats SQLite cache
and produces typed evidence records with quality gating for downstream
proposal/weight engines.

Safety guarantees:
- Full typed contracts with zero Any types
- SQLite URI mode=ro (never creates missing databases)
- 10+ quality gates (schema, integrity, age, sparsity, numerics, conflicts, etc.)
- Deterministic output under explicit as_of timestamp
- Source DB remains byte-for-byte unchanged
- Canonical schema utilities from source_regime_stats.db
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from si_v2.source_regime_stats.db import (
    SCHEMA_VERSION as CANONICAL_SCHEMA_VERSION,
)
from si_v2.source_regime_stats.db import (
    foreign_key_check as run_foreign_key_check,
)
from si_v2.source_regime_stats.db import (
    integrity_check as run_integrity_check,
)

# ---------------------------------------------------------------------------
# Typed enums
# ---------------------------------------------------------------------------


class RejectionReason(Enum):
    """Typed reason for evidence rejection."""

    SPARSE_DATA = "sparse_data"
    STALE_EVIDENCE = "stale_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    INTEGRITY_FAILURE = "integrity_failure"
    MISSING_METADATA = "missing_metadata"
    MISSING_FINGERPRINT = "missing_fingerprint"
    INVALID_NUMERICS = "invalid_numerics"
    INVALID_CONFIDENCE = "invalid_confidence"
    UNKNOWN_REGIME = "unknown_regime"
    UNKNOWN_CONFIDENCE_BUCKET = "unknown_confidence_bucket"
    INVALID_COUNTS = "invalid_counts"
    INVALID_TIMESTAMP = "invalid_timestamp"
    MALFORMED_REQUEST = "malformed_request"


class QualityVerdict(Enum):
    """Quality verdict for an evidence record."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEDUPLICATED = "deduplicated"


# ---------------------------------------------------------------------------
# Typed contracts — zero Any usage
# ---------------------------------------------------------------------------

KNOWN_REGIMES: frozenset[str] = frozenset({
    "bullish", "bearish", "neutral", "unknown",
})

KNOWN_CONFIDENCE_BUCKETS: frozenset[str] = frozenset({
    "high", "medium", "low",
})

# Canonical confidence range [0.0, 1.0]
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0


@dataclass(frozen=True)
class EvidencePipelineRequest:
    """Full typed request for the evidence input pipeline.

    Attributes:
        cache_db_path: Path to the source_regime_stats SQLite cache.
        as_of: Explicit UTC timestamp for evidence age calculation.
        period_start: Optional start of evidence period (inclusive).
        period_end: Optional end of evidence period (inclusive).
        source_filter: Optional source ID filter.
        regime_filter: Optional regime filter.
        minimum_unique_trade_count: Minimum unique trades for inclusion.
        maximum_evidence_age_days: Max age in days relative to as_of.
        accepted_schema_versions: Set of accepted full version strings.
    """

    cache_db_path: Path
    as_of: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    source_filter: str | None = None
    regime_filter: str | None = None
    minimum_unique_trade_count: int = 1
    maximum_evidence_age_days: float | None = None
    accepted_schema_versions: frozenset[str] = field(
        default_factory=lambda: frozenset({CANONICAL_SCHEMA_VERSION})
    )

    def __post_init__(self: EvidencePipelineRequest) -> None:
        """Validate request invariants at construction time."""
        errors: list[str] = []

        # as_of must be timezone-aware UTC
        if self.as_of.tzinfo is None:
            errors.append("as_of must be timezone-aware (got naive datetime)")
        elif self.as_of.tzinfo != UTC:
            errors.append(f"as_of must be in UTC, got {self.as_of.tzinfo}")

        # period_start/end must be timezone-aware UTC when present
        for label, dt in [("period_start", self.period_start), ("period_end", self.period_end)]:
            if dt is not None:
                if dt.tzinfo is None:
                    errors.append(f"{label} must be timezone-aware (got naive datetime)")
                elif dt.tzinfo != UTC:
                    errors.append(f"{label} must be in UTC, got {dt.tzinfo}")

        # period_start must not exceed period_end
        if self.period_start is not None and self.period_end is not None and self.period_start > self.period_end:
            errors.append(
                f"period_start ({self.period_start.isoformat()}) exceeds "
                f"period_end ({self.period_end.isoformat()})"
            )

        # period_end must not exceed as_of
        if self.period_end is not None and self.period_end > self.as_of:
            errors.append(
                f"period_end ({self.period_end.isoformat()}) exceeds "
                f"as_of ({self.as_of.isoformat()})"
            )

        # minimum_unique_trade_count must be int > 0 and reject bool
        if isinstance(self.minimum_unique_trade_count, bool):
            errors.append("minimum_unique_trade_count must be an integer, not bool")
        elif not isinstance(self.minimum_unique_trade_count, int):
            errors.append(
                f"minimum_unique_trade_count must be an integer, "
                f"got {type(self.minimum_unique_trade_count).__name__}"
            )
        elif self.minimum_unique_trade_count < 1:
            errors.append(
                f"minimum_unique_trade_count must be >= 1, "
                f"got {self.minimum_unique_trade_count}"
            )

        # maximum_evidence_age_days must be finite non-negative when set
        if self.maximum_evidence_age_days is not None:
            if isinstance(self.maximum_evidence_age_days, bool):
                errors.append("maximum_evidence_age_days must be a float, not bool")
            elif not isinstance(self.maximum_evidence_age_days, (int, float)):
                errors.append(
                    f"maximum_evidence_age_days must be a number, "
                    f"got {type(self.maximum_evidence_age_days).__name__}"
                )
            else:
                fval = float(self.maximum_evidence_age_days)
                if fval != fval or fval == float("inf") or fval == float("-inf"):
                    errors.append(
                        f"maximum_evidence_age_days must be finite, got {fval}"
                    )
                if fval < 0:
                    errors.append(
                        f"maximum_evidence_age_days must be non-negative, got {fval}"
                    )

        # source_filter must be non-empty when present
        if self.source_filter is not None and not self.source_filter.strip():
            errors.append("source_filter must be a non-empty string when provided")

        # regime_filter must be non-empty when present
        if self.regime_filter is not None and not self.regime_filter.strip():
            errors.append("regime_filter must be a non-empty string when provided")

        # accepted_schema_versions must be non-empty
        if not self.accepted_schema_versions:
            errors.append("accepted_schema_versions must be a non-empty set")

        if errors:
            raise ValueError(
                "EvidencePipelineRequest validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


@dataclass(frozen=True)
class ProposalEvidenceRecord:
    """A single typed evidence record from the pipeline.

    Every field from the source_regime_stats aggregation is preserved.
    """

    evidence_id: str  # deterministic hash
    source_id: str
    strategy_or_model_id: str | None
    pair: str
    timeframe: str
    regime: str
    confidence_bucket: str
    unique_trade_count: int
    source_contribution_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float
    expectancy: float
    average_raw_return: float
    average_weighted_return: float
    cumulative_weighted_return: float
    drawdown_proxy: float
    average_source_confidence: float | None
    average_regime_confidence: float | None
    evidence_max_closed_at: str | None
    input_fingerprint: str
    cache_schema_version: str | None
    fact_schema_version: str | None
    source_fingerprint: str | None

    def canonical_serialize(self) -> str:
        """Deterministic JSON serialization of all semantic fields."""
        return json.dumps(
            {
                "evidence_id": self.evidence_id,
                "source_id": self.source_id,
                "strategy_or_model_id": self.strategy_or_model_id,
                "pair": self.pair,
                "timeframe": self.timeframe,
                "regime": self.regime,
                "confidence_bucket": self.confidence_bucket,
                "unique_trade_count": self.unique_trade_count,
                "source_contribution_count": self.source_contribution_count,
                "win_count": self.win_count,
                "loss_count": self.loss_count,
                "breakeven_count": self.breakeven_count,
                "win_rate": self.win_rate,
                "expectancy": self.expectancy,
                "average_raw_return": self.average_raw_return,
                "average_weighted_return": self.average_weighted_return,
                "cumulative_weighted_return": self.cumulative_weighted_return,
                "drawdown_proxy": self.drawdown_proxy,
                "average_source_confidence": self.average_source_confidence,
                "average_regime_confidence": self.average_regime_confidence,
                "evidence_max_closed_at": self.evidence_max_closed_at,
                "input_fingerprint": self.input_fingerprint,
                "cache_schema_version": self.cache_schema_version,
                "fact_schema_version": self.fact_schema_version,
                "source_fingerprint": self.source_fingerprint,
            },
            sort_keys=True,
            default=str,
        )


@dataclass(frozen=True)
class EvidenceRejection:
    """A rejection of a single evidence candidate."""

    evidence_id: str | None
    reason: RejectionReason
    detail: str


@dataclass(frozen=True)
class EvidenceQualityVerdict:
    """Quality verdict for a single candidate."""

    verdict: QualityVerdict
    record: ProposalEvidenceRecord | None
    rejection: EvidenceRejection | None


@dataclass(frozen=True)
class EvidencePipelineResult:
    """Result of running the evidence input pipeline."""

    request: EvidencePipelineRequest
    accepted: tuple[ProposalEvidenceRecord, ...]
    rejected: tuple[EvidenceRejection, ...]
    deduplicated: int
    total_candidates: int
    pipeline_fingerprint: str
    errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Evidence ID generation
# ---------------------------------------------------------------------------


def _make_evidence_id(
    source_id: str,
    strategy_or_model_id: str | None,
    pair: str,
    timeframe: str,
    regime: str,
    confidence_bucket: str,
) -> str:
    """Generate a deterministic evidence ID from dimension fields."""
    raw = f"{source_id}|{strategy_or_model_id or ''}|{pair}|{timeframe}|{regime}|{confidence_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Safe typed parsing helpers
# ---------------------------------------------------------------------------


def _reject_non_finite(val: object, field_name: str) -> str | None:
    """Returns an error message if val is non-finite, bool, or non-numeric; None if OK."""
    if isinstance(val, bool):
        return f"{field_name} is bool ({val!r}), not a valid float"
    if not isinstance(val, (int, float)):
        return f"{field_name} has unexpected type {type(val).__name__} ({val!r})"
    fval = float(val)
    if fval != fval:  # NaN
        return f"{field_name} is NaN"
    if fval == float("inf"):
        return f"{field_name} is +infinity"
    if fval == float("-inf"):
        return f"{field_name} is -infinity"
    return None


def _parse_required_float(val: object) -> float:
    """Parse a required float field. Raises ValueError on failure."""
    err = _reject_non_finite(val, "value")
    if err is not None:
        raise ValueError(err)
    # _reject_non_finite ensures val is int | float at this point
    assert isinstance(val, (int, float)), f"expected int/float, got {type(val).__name__}"
    return float(val)


def _parse_optional_float(val: object) -> float | None:
    """Parse an optional float field. Returns None on failure."""
    if val is None:
        return None
    err = _reject_non_finite(val, "value")
    if err is not None:
        return None
    # _reject_non_finite ensures val is int | float at this point
    assert isinstance(val, (int, float)), f"expected int/float, got {type(val).__name__}"
    return float(val)


def _parse_required_int(val: object) -> int:
    """Parse a required integer field. Raises ValueError on failure.

    Rejects bool values explicitly.
    """
    if isinstance(val, bool):
        raise ValueError(f"value is bool ({val!r}), not a valid integer")
    if not isinstance(val, int):
        raise ValueError(f"value has unexpected type {type(val).__name__} ({val!r})")
    if val < 0:
        raise ValueError(f"value is negative ({val})")
    return val


def _parse_required_non_empty_string(val: object) -> str:
    """Parse a required non-empty string. Raises ValueError on failure."""
    if val is None:
        raise ValueError("value is None")
    if isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            raise ValueError("value is empty or whitespace-only")
        return stripped
    raise ValueError(f"value is not a string ({type(val).__name__}): {val!r}")


def _parse_optional_non_empty_string(val: object) -> str | None:
    """Parse an optional non-empty string. Returns None if None or empty."""
    if val is None:
        return None
    if isinstance(val, str):
        stripped = val.strip()
        return stripped if stripped else None
    return None


def _parse_utc_datetime_string(val: object) -> str | None:
    """Parse and validate a UTC datetime string. Returns normalized ISO string or None.

    Returns None when val is None.
    Raises ValueError for malformed, naive, or non-UTC strings.
    """
    if val is None:
        return None
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"must be a non-empty string, got {type(val).__name__}")
    try:
        dt = datetime.fromisoformat(val.strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(f"could not be parsed: {exc}") from exc
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime (no timezone): {val}")
    if dt.tzinfo != UTC:
        dt_utc = dt.astimezone(UTC)
        return dt_utc.isoformat()
    return val.strip()


def _parse_str(val: object) -> str:
    """Convert a DB value to str. Returns '' for None."""
    if val is None:
        return ""
    return str(val)


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------


def _check_quality(
    row: sqlite3.Row,
    request: EvidencePipelineRequest,
    seen_records: dict[str, str],  # evidence_id -> canonical_serialize
) -> EvidenceQualityVerdict:
    """Run all quality gates on a single row candidate.

    Returns ACCEPTED, REJECTED, or DEDUPLICATED with typed reasons.
    No Any types used — row is accessed via typed parsing functions.
    """
    # Extract and validate dimension fields (fail-fast on malformed rows)
    try:
        source_id = _parse_required_non_empty_string(row["source_id"])
    except ValueError as exc:
        return _reject(None, RejectionReason.MALFORMED_REQUEST, f"source_id: {exc}")

    strategy_or_model_id = (
        str(row["strategy_or_model_id"])
        if row["strategy_or_model_id"] is not None
        else None
    )

    try:
        pair = _parse_required_non_empty_string(row["pair"])
        timeframe = _parse_required_non_empty_string(row["timeframe"])
        regime = _parse_required_non_empty_string(row["regime"])
        confidence_bucket = _parse_required_non_empty_string(row["confidence_bucket"])
    except ValueError as exc:
        return _reject(None, RejectionReason.MALFORMED_REQUEST, str(exc))

    evidence_id = _make_evidence_id(
        source_id,
        strategy_or_model_id,
        pair,
        timeframe,
        regime,
        confidence_bucket,
    )

    # --- Gate: Known regime ---
    if regime not in KNOWN_REGIMES:
        return _reject(
            evidence_id,
            RejectionReason.UNKNOWN_REGIME,
            f"Unknown regime: {regime!r}",
        )

    # --- Gate: Known confidence bucket ---
    if confidence_bucket not in KNOWN_CONFIDENCE_BUCKETS:
        return _reject(
            evidence_id,
            RejectionReason.UNKNOWN_CONFIDENCE_BUCKET,
            f"Unknown confidence bucket: {confidence_bucket!r}",
        )

    # --- Gate: Minimum unique trade count ---
    try:
        trade_count = _parse_required_int(row["unique_trade_count"])
    except ValueError as exc:
        return _reject(evidence_id, RejectionReason.SPARSE_DATA, str(exc))

    if trade_count < request.minimum_unique_trade_count:
        return _reject(
            evidence_id,
            RejectionReason.SPARSE_DATA,
            f"Trade count {trade_count} < minimum {request.minimum_unique_trade_count}",
        )

    # --- Gate: Maximum evidence age ---
    if request.maximum_evidence_age_days is not None:
        closed_at_raw = row["evidence_max_closed_at"]
        if closed_at_raw is None:
            return _reject(
                evidence_id,
                RejectionReason.STALE_EVIDENCE,
                "Missing evidence_max_closed_at — cannot validate age",
            )
        if isinstance(closed_at_raw, str) and not closed_at_raw.strip():
            return _reject(
                evidence_id,
                RejectionReason.STALE_EVIDENCE,
                "Empty evidence_max_closed_at — cannot validate age",
            )
        try:
            closed_at_str = _parse_utc_datetime_string(closed_at_raw)
        except ValueError as exc:
            return _reject(evidence_id, RejectionReason.STALE_EVIDENCE, str(exc))

        if closed_at_str is not None:
            closed_dt = datetime.fromisoformat(closed_at_str)
            age_days = (request.as_of - closed_dt).total_seconds() / 86400.0
            if age_days < 0:
                return _reject(
                    evidence_id,
                    RejectionReason.STALE_EVIDENCE,
                    f"Evidence timestamp {closed_at_str} is later than as_of",
                )
            if age_days > request.maximum_evidence_age_days:
                return _reject(
                    evidence_id,
                    RejectionReason.STALE_EVIDENCE,
                    f"Evidence age {age_days:.1f}d > max {request.maximum_evidence_age_days}d",
                )

    # --- Gate: Finite numeric metrics ---
    numeric_fields: list[tuple[str, str]] = [
        ("win_rate", "win_rate"),
        ("expectancy", "expectancy"),
        ("average_raw_return", "average_raw_return"),
        ("average_weighted_return", "average_weighted_return"),
        ("cumulative_weighted_return", "cumulative_weighted_return"),
        ("drawdown_proxy", "drawdown_proxy"),
    ]
    parsed_numerics: dict[str, float] = {}
    for display_name, field_name in numeric_fields:
        val = row[field_name]
        if val is not None:
            try:
                fval = _parse_required_float(val)
                parsed_numerics[field_name] = fval
            except ValueError as exc:
                return _reject(evidence_id, RejectionReason.INVALID_NUMERICS, f"{display_name}: {exc}")

    # --- Gate: Win rate range ---
    wr_val = row["win_rate"]
    if wr_val is not None:
        try:
            win_rate = _parse_required_float(wr_val)
        except ValueError as exc:
            return _reject(evidence_id, RejectionReason.INVALID_NUMERICS, f"win_rate: {exc}")
        if win_rate < 0.0 or win_rate > 1.0:
            return _reject(
                evidence_id,
                RejectionReason.INVALID_NUMERICS,
                f"win_rate {win_rate} outside expected [0.0, 1.0] range",
            )
    else:
        win_rate = 0.0

    # --- Gate: Confidence value ranges ---
    for conf_field in ("average_source_confidence", "average_regime_confidence"):
        conf_val = row[conf_field]
        if conf_val is not None:
            try:
                fconf = _parse_required_float(conf_val)
            except ValueError as exc:
                return _reject(evidence_id, RejectionReason.INVALID_CONFIDENCE, f"{conf_field}: {exc}")
            if fconf < CONFIDENCE_MIN or fconf > CONFIDENCE_MAX:
                return _reject(
                    evidence_id,
                    RejectionReason.INVALID_CONFIDENCE,
                    f"{conf_field} value {fconf} outside [{CONFIDENCE_MIN}, {CONFIDENCE_MAX}]",
                )

    # --- Gate: Count invariants ---
    try:
        win_count = _parse_required_int(row["win_count"])
        loss_count = _parse_required_int(row["loss_count"])
        breakeven_count = _parse_required_int(row["breakeven_count"])
        source_contrib_count = _parse_required_int(row["source_contribution_count"])
    except ValueError as exc:
        return _reject(evidence_id, RejectionReason.INVALID_COUNTS, str(exc))

    total_outcome = win_count + loss_count + breakeven_count
    if total_outcome != trade_count:
        return _reject(
            evidence_id,
            RejectionReason.INVALID_COUNTS,
            f"win_count ({win_count}) + loss_count ({loss_count}) + breakeven_count "
            f"({breakeven_count}) = {total_outcome} != unique_trade_count ({trade_count})",
        )
    if source_contrib_count < 0:
        return _reject(
            evidence_id,
            RejectionReason.INVALID_COUNTS,
            f"source_contribution_count is negative ({source_contrib_count})",
        )

    # --- Gate: Duplicate detection ---
    record = _build_record(
        row, evidence_id, source_id, strategy_or_model_id,
        pair, timeframe, regime, confidence_bucket,
        trade_count, win_count, loss_count, breakeven_count,
        source_contrib_count, win_rate, parsed_numerics,
    )
    if record is None:
        return _reject(
            evidence_id, RejectionReason.MALFORMED_REQUEST,
            "Failed to build evidence record from row data",
        )

    if evidence_id in seen_records:
        candidate_serialized = record.canonical_serialize()
        existing_serialized = seen_records[evidence_id]
        if candidate_serialized == existing_serialized:
            return EvidenceQualityVerdict(
                verdict=QualityVerdict.DEDUPLICATED,
                record=None,
                rejection=EvidenceRejection(
                    evidence_id=evidence_id,
                    reason=RejectionReason.CONFLICTING_EVIDENCE,
                    detail="Duplicate with identical content — deduplicated",
                ),
            )
        return EvidenceQualityVerdict(
            verdict=QualityVerdict.REJECTED,
            record=None,
            rejection=EvidenceRejection(
                evidence_id=evidence_id,
                reason=RejectionReason.CONFLICTING_EVIDENCE,
                detail="Duplicate evidence_id with different content — hard conflict",
            ),
        )

    seen_records[evidence_id] = record.canonical_serialize()

    return EvidenceQualityVerdict(
        verdict=QualityVerdict.ACCEPTED,
        record=record,
        rejection=None,
    )


def _reject(
    evidence_id: str | None,
    reason: RejectionReason,
    detail: str,
) -> EvidenceQualityVerdict:
    """Helper to create a REJECTED verdict."""
    return EvidenceQualityVerdict(
        verdict=QualityVerdict.REJECTED,
        record=None,
        rejection=EvidenceRejection(
            evidence_id=evidence_id,
            reason=reason,
            detail=detail,
        ),
    )


def _build_record(
    row: sqlite3.Row,
    evidence_id: str,
    source_id: str,
    strategy_or_model_id: str | None,
    pair: str,
    timeframe: str,
    regime: str,
    confidence_bucket: str,
    trade_count: int,
    win_count: int,
    loss_count: int,
    breakeven_count: int,
    source_contrib_count: int,
    win_rate: float,
    parsed_numerics: dict[str, float],
) -> ProposalEvidenceRecord | None:
    """Build a ProposalEvidenceRecord from row data. Returns None on parse failure."""
    expectancy = parsed_numerics.get("expectancy")
    avg_raw = parsed_numerics.get("average_raw_return")
    avg_weighted = parsed_numerics.get("average_weighted_return")
    cum_weighted = parsed_numerics.get("cumulative_weighted_return")
    drawdown = parsed_numerics.get("drawdown_proxy")
    if any(v is None for v in [expectancy, avg_raw, avg_weighted, cum_weighted, drawdown]):
        return None

    avg_source_conf = _parse_optional_float(row["average_source_confidence"])
    avg_regime_conf = _parse_optional_float(row["average_regime_confidence"])

    return ProposalEvidenceRecord(
        evidence_id=evidence_id,
        source_id=source_id,
        strategy_or_model_id=strategy_or_model_id,
        pair=pair,
        timeframe=timeframe,
        regime=regime,
        confidence_bucket=confidence_bucket,
        unique_trade_count=trade_count,
        source_contribution_count=source_contrib_count,
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=breakeven_count,
        win_rate=win_rate,
        expectancy=expectancy,
        average_raw_return=avg_raw,
        average_weighted_return=avg_weighted,
        cumulative_weighted_return=cum_weighted,
        drawdown_proxy=drawdown,
        average_source_confidence=avg_source_conf,
        average_regime_confidence=avg_regime_conf,
        evidence_max_closed_at=_parse_optional_non_empty_string(row["evidence_max_closed_at"]),
        input_fingerprint=_parse_str(row["input_fingerprint"]),
        cache_schema_version=_parse_optional_non_empty_string(row["cache_schema_version"]),
        fact_schema_version=_parse_optional_non_empty_string(row["fact_schema_version"]),
        source_fingerprint=_parse_optional_non_empty_string(row["source_fingerprint"]),
    )


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


_EVIDENCE_QUERY = """
    SELECT
        s.source_id,
        s.strategy_or_model_id,
        s.pair,
        s.timeframe,
        s.regime,
        s.confidence_bucket,
        s.unique_trade_count,
        s.source_contribution_count,
        s.win_count,
        s.loss_count,
        s.breakeven_count,
        s.win_rate,
        s.expectancy,
        s.average_raw_return,
        s.average_weighted_return,
        s.cumulative_weighted_return,
        s.drawdown_proxy,
        s.average_source_confidence,
        s.average_regime_confidence,
        s.evidence_max_closed_at,
        s.input_fingerprint,
        m.cache_schema_version,
        m.fact_schema_version,
        m.source_fingerprint
    FROM source_regime_stats s
    LEFT JOIN cache_metadata m ON m.id = 1
    WHERE 1=1
"""


def _build_query(request: EvidencePipelineRequest) -> tuple[str, list[str]]:
    """Build the SQL query with request filters."""
    query = _EVIDENCE_QUERY
    params: list[str] = []

    if request.source_filter is not None:
        query += " AND s.source_id = ?"
        params.append(request.source_filter)

    if request.regime_filter is not None:
        query += " AND s.regime = ?"
        params.append(request.regime_filter)

    if request.period_start is not None:
        query += " AND s.evidence_max_closed_at >= ?"
        params.append(request.period_start.isoformat())

    if request.period_end is not None:
        query += " AND s.evidence_max_closed_at <= ?"
        params.append(request.period_end.isoformat())

    query += " ORDER BY s.source_id, s.regime, s.pair, s.timeframe"
    return query, params


# ---------------------------------------------------------------------------
# Pre-flight cache validation
# ---------------------------------------------------------------------------


def _validate_cache(
    conn: sqlite3.Connection,
    request: EvidencePipelineRequest,
) -> list[str]:
    """Validate the cache database before reading evidence.

    Checks:
    - integrity_check
    - foreign_key_check
    - cache_metadata exists and has source_fingerprint
    - schema version is supported

    Returns a list of error messages. Empty list means validation passed.
    """
    errors: list[str] = []

    # Integrity check
    integrity_issues = run_integrity_check(conn)
    if integrity_issues:
        errors.append(f"Cache integrity check failed: {integrity_issues}")

    # Foreign key check
    fk_issues = run_foreign_key_check(conn)
    if fk_issues:
        errors.append(f"Cache foreign key check failed: {fk_issues}")

    # Schema version and metadata
    try:
        row = conn.execute(
            "SELECT cache_schema_version, fact_schema_version, source_fingerprint "
            "FROM cache_metadata WHERE id = 1 LIMIT 1"
        ).fetchone()
        if row is None:
            errors.append("Cache metadata row not found")
        else:
            ver = str(row[0]) if row[0] else ""
            if ver not in request.accepted_schema_versions:
                errors.append(
                    f"Unsupported cache schema version: {ver!r}. "
                    f"Accepted: {sorted(request.accepted_schema_versions)}"
                )
            fp = str(row[2]) if row[2] else ""
            if not fp:
                errors.append("Cache metadata missing source_fingerprint")
    except sqlite3.DatabaseError as exc:
        errors.append(f"Cache metadata check failed: {exc}")

    return errors


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_evidence_pipeline(
    request: EvidencePipelineRequest,
) -> EvidencePipelineResult:
    """Run the evidence input pipeline.

    This is the primary entry point. It:
    1. Validates the cache database (integrity, FK, metadata, schema)
    2. Opens the cache with mode=ro
    3. Queries source_regime_stats with LEFT JOIN cache_metadata
    4. Applies quality gates (regime, bucket, sparsity, age, numerics, conflicts)
    5. Returns typed accepted/rejected/deduplicated records

    Args:
        request: Full typed request with all parameters.

    Returns:
        EvidencePipelineResult with accepted evidence, rejections, and errors.

    The source database is never modified.
    No datetime.now inside — uses request.as_of.
    """
    errors: list[str] = []
    accepted: list[ProposalEvidenceRecord] = []
    rejected: list[EvidenceRejection] = []
    deduplicated_count = 0
    seen_records: dict[str, str] = {}  # evidence_id -> canonical_serialize

    db_path = request.cache_db_path.resolve()

    if not db_path.exists():
        errors.append(f"Cache database not found: {db_path}")
        return _make_result(request, accepted, rejected, deduplicated_count, errors)

    # Open with mode=ro — never creates a missing database
    uri = f"{db_path.as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.DatabaseError as exc:
        errors.append(f"Cannot open cache database: {exc}")
        return _make_result(request, accepted, rejected, deduplicated_count, errors)

    try:
        # Pre-flight validation
        validation_errors = _validate_cache(conn, request)
        if validation_errors:
            errors.extend(validation_errors)
            has_hard_failure = any(
                "integrity" in e.lower() or "foreign key" in e.lower()
                for e in validation_errors
            )
            if has_hard_failure:
                return _make_result(
                    request, accepted, rejected, deduplicated_count, errors
                )

        # Build and execute query
        query, params = _build_query(request)
        cursor = conn.execute(query, params)

        for row in cursor:
            verdict = _check_quality(row, request, seen_records)
            if verdict.verdict == QualityVerdict.ACCEPTED and verdict.record is not None:
                accepted.append(verdict.record)
            elif verdict.verdict == QualityVerdict.REJECTED and verdict.rejection is not None:
                rejected.append(verdict.rejection)
            elif verdict.verdict == QualityVerdict.DEDUPLICATED:
                deduplicated_count += 1

    except sqlite3.DatabaseError as exc:
        errors.append(f"Database error during query: {exc}")
    finally:
        conn.close()

    return _make_result(request, accepted, rejected, deduplicated_count, errors)


def _make_result(
    request: EvidencePipelineRequest,
    accepted: list[ProposalEvidenceRecord],
    rejected: list[EvidenceRejection],
    deduplicated_count: int,
    errors: list[str],
) -> EvidencePipelineResult:
    """Build the final EvidencePipelineResult with a deterministic fingerprint."""
    # Build a deterministic pipeline fingerprint from full result content
    accepted_serialized = [r.canonical_serialize() for r in accepted]
    rejected_serialized = [
        {
            "evidence_id": r.evidence_id,
            "reason": r.reason.value,
            "detail": r.detail,
        }
        for r in rejected
    ]

    fp_input = json.dumps(
        {
            "accepted": accepted_serialized,
            "rejected": rejected_serialized,
            "deduplicated_count": deduplicated_count,
            "error_count": len(errors),
            "errors": sorted(errors),
            "as_of": request.as_of.isoformat(),
            "period_start": request.period_start.isoformat() if request.period_start else None,
            "period_end": request.period_end.isoformat() if request.period_end else None,
            "source_filter": request.source_filter,
            "regime_filter": request.regime_filter,
            "minimum_unique_trade_count": request.minimum_unique_trade_count,
            "maximum_evidence_age_days": request.maximum_evidence_age_days,
        },
        sort_keys=True,
    )
    pipeline_fingerprint = hashlib.sha256(fp_input.encode()).hexdigest()[:16]

    return EvidencePipelineResult(
        request=request,
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        deduplicated=deduplicated_count,
        total_candidates=len(accepted) + len(rejected) + deduplicated_count,
        pipeline_fingerprint=pipeline_fingerprint,
        errors=tuple(errors),
    )
