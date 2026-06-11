"""Evidence Input Pipeline — Phase 2, issue #62.

Reads trade attribution data from the source_regime_stats SQLite cache
and produces typed evidence records with quality gating for downstream
proposal/weight engines.

Safety guarantees:
- Full typed contracts with no Any types
- SQLite URI mode=ro (never creates missing databases)
- 10 quality gates (schema, integrity, age, sparsity, conflicts, etc.)
- Deterministic output under explicit as_of timestamp
- Source DB remains byte-for-byte unchanged
- Canonical schema utilities from source_regime_stats.db
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

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


class QualityVerdict(Enum):
    """Quality verdict for an evidence record."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEDUPLICATED = "deduplicated"


# ---------------------------------------------------------------------------
# Typed contracts
# ---------------------------------------------------------------------------

KNOWN_REGIMES: frozenset[str] = frozenset({
    "bullish", "bearish", "neutral", "unknown",
})

KNOWN_CONFIDENCE_BUCKETS: frozenset[str] = frozenset({
    "high", "medium", "low",
})


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
# Quality gates
# ---------------------------------------------------------------------------


def _check_quality(
    row: dict[str, Any],
    request: EvidencePipelineRequest,
    seen_ids: dict[str, dict[str, Any]],
) -> EvidenceQualityVerdict:
    """Run all quality gates on a single row candidate.

    Returns ACCEPTED, REJECTED, or DEDUPLICATED with typed reasons.
    """
    evidence_id = _make_evidence_id(
        str(row.get("source_id", "")),
        str(row.get("strategy_or_model_id")) if row.get("strategy_or_model_id") else None,
        str(row.get("pair", "")),
        str(row.get("timeframe", "")),
        str(row.get("regime", "")),
        str(row.get("confidence_bucket", "")),
    )

    # --- Gate: Known regime ---
    regime = str(row.get("regime", ""))
    if regime not in KNOWN_REGIMES:
        return EvidenceQualityVerdict(
            verdict=QualityVerdict.REJECTED,
            record=None,
            rejection=EvidenceRejection(
                evidence_id=evidence_id,
                reason=RejectionReason.UNKNOWN_REGIME,
                detail=f"Unknown regime: {regime!r}",
            ),
        )

    # --- Gate: Known confidence bucket ---
    bucket = str(row.get("confidence_bucket", ""))
    if bucket not in KNOWN_CONFIDENCE_BUCKETS:
        return EvidenceQualityVerdict(
            verdict=QualityVerdict.REJECTED,
            record=None,
            rejection=EvidenceRejection(
                evidence_id=evidence_id,
                reason=RejectionReason.UNKNOWN_CONFIDENCE_BUCKET,
                detail=f"Unknown confidence bucket: {bucket!r}",
            ),
        )

    # --- Gate: Minimum unique trade count ---
    trade_count = int(row.get("unique_trade_count", 0))
    if trade_count < request.minimum_unique_trade_count:
        return EvidenceQualityVerdict(
            verdict=QualityVerdict.REJECTED,
            record=None,
            rejection=EvidenceRejection(
                evidence_id=evidence_id,
                reason=RejectionReason.SPARSE_DATA,
                detail=f"Trade count {trade_count} < minimum {request.minimum_unique_trade_count}",
            ),
        )

    # --- Gate: Maximum evidence age ---
    if request.maximum_evidence_age_days is not None:
        closed_at_str = row.get("evidence_max_closed_at")
        if closed_at_str:
            try:
                closed_at = datetime.fromisoformat(str(closed_at_str))
                age_days = (request.as_of - closed_at).total_seconds() / 86400.0
                if age_days > request.maximum_evidence_age_days:
                    return EvidenceQualityVerdict(
                        verdict=QualityVerdict.REJECTED,
                        record=None,
                        rejection=EvidenceRejection(
                            evidence_id=evidence_id,
                            reason=RejectionReason.STALE_EVIDENCE,
                            detail=f"Evidence age {age_days:.1f}d > max {request.maximum_evidence_age_days}d",
                        ),
                    )
            except (ValueError, TypeError):
                pass

    # --- Gate: Finite numeric metrics ---
    numeric_fields = [
        ("win_rate", "win_rate"),
        ("expectancy", "expectancy"),
        ("average_raw_return", "average_raw_return"),
        ("average_weighted_return", "average_weighted_return"),
        ("cumulative_weighted_return", "cumulative_weighted_return"),
        ("drawdown_proxy", "drawdown_proxy"),
    ]
    for display_name, field_name in numeric_fields:
        val = row.get(field_name)
        if val is not None:
            try:
                fval = float(val)
                if fval != fval:  # NaN check
                    return EvidenceQualityVerdict(
                        verdict=QualityVerdict.REJECTED,
                        record=None,
                        rejection=EvidenceRejection(
                            evidence_id=evidence_id,
                            reason=RejectionReason.INVALID_NUMERICS,
                            detail=f"{display_name} is NaN",
                        ),
                    )
                if fval == float("inf") or fval == float("-inf"):
                    return EvidenceQualityVerdict(
                        verdict=QualityVerdict.REJECTED,
                        record=None,
                        rejection=EvidenceRejection(
                            evidence_id=evidence_id,
                            reason=RejectionReason.INVALID_NUMERICS,
                            detail=f"{display_name} is infinite",
                        ),
                    )
            except (ValueError, TypeError):
                pass

    # --- Gate: Duplicate detection ---
    if evidence_id in seen_ids:
        existing = seen_ids[evidence_id]
        # Compare content — if identical, deduplicate silently
        if _rows_equal(row, existing):
            return EvidenceQualityVerdict(
                verdict=QualityVerdict.DEDUPLICATED,
                record=None,
                rejection=EvidenceRejection(
                    evidence_id=evidence_id,
                    reason=RejectionReason.CONFLICTING_EVIDENCE,
                    detail="Duplicate with identical content — deduplicated",
                ),
            )
        # If different, hard conflict
        return EvidenceQualityVerdict(
            verdict=QualityVerdict.REJECTED,
            record=None,
            rejection=EvidenceRejection(
                evidence_id=evidence_id,
                reason=RejectionReason.CONFLICTING_EVIDENCE,
                detail="Duplicate evidence_id with different content — hard conflict",
            ),
        )

    seen_ids[evidence_id] = row

    # --- Build accepted record ---
    record = ProposalEvidenceRecord(
        evidence_id=evidence_id,
        source_id=str(row.get("source_id", "")),
        strategy_or_model_id=str(row["strategy_or_model_id"]) if row.get("strategy_or_model_id") else None,
        pair=str(row.get("pair", "")),
        timeframe=str(row.get("timeframe", "")),
        regime=regime,
        confidence_bucket=bucket,
        unique_trade_count=trade_count,
        source_contribution_count=int(row.get("source_contribution_count", 0)),
        win_count=int(row.get("win_count", 0)),
        loss_count=int(row.get("loss_count", 0)),
        breakeven_count=int(row.get("breakeven_count", 0)),
        win_rate=_safe_float(row.get("win_rate", 0.0)),
        expectancy=_safe_float(row.get("expectancy", 0.0)),
        average_raw_return=_safe_float(row.get("average_raw_return", 0.0)),
        average_weighted_return=_safe_float(row.get("average_weighted_return", 0.0)),
        cumulative_weighted_return=_safe_float(row.get("cumulative_weighted_return", 0.0)),
        drawdown_proxy=_safe_float(row.get("drawdown_proxy", 0.0)),
        average_source_confidence=_safe_float_opt(row.get("average_source_confidence")),
        average_regime_confidence=_safe_float_opt(row.get("average_regime_confidence")),
        evidence_max_closed_at=str(row["evidence_max_closed_at"]) if row.get("evidence_max_closed_at") else None,
        input_fingerprint=str(row.get("input_fingerprint", "")),
        cache_schema_version=str(row.get("cache_schema_version")) if row.get("cache_schema_version") else None,
        fact_schema_version=str(row.get("fact_schema_version")) if row.get("fact_schema_version") else None,
        source_fingerprint=str(row.get("source_fingerprint")) if row.get("source_fingerprint") else None,
    )

    return EvidenceQualityVerdict(
        verdict=QualityVerdict.ACCEPTED,
        record=record,
        rejection=None,
    )


def _rows_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Compare two row dicts for content equality."""
    # Compare all keys present in either dict
    all_keys = set(a.keys()) | set(b.keys())
    return all(a.get(key) == b.get(key) for key in all_keys)


def _safe_float(val: object) -> float:
    """Convert a value to float, defaulting to 0.0 on failure."""
    try:
        return float(val)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0.0


def _safe_float_opt(val: object) -> float | None:
    """Convert a value to float or None."""
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


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
            "SELECT cache_schema_version, source_fingerprint "
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
            fp = str(row[1]) if row[1] else ""
            if not fp:
                errors.append("Cache metadata missing source_fingerprint")
    except sqlite3.DatabaseError as exc:
        errors.append(f"Cache metadata check failed: {exc}")

    return errors


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_evidence_pipeline(request: EvidencePipelineRequest) -> EvidencePipelineResult:
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
    seen_ids: dict[str, dict[str, Any]] = {}

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
            # Don't return early — continue to collect evidence even if
            # validation has warnings. Hard failures (integrity, FK) are
            # treated as errors that prevent acceptance.
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
            verdict = _check_quality(dict(row), request, seen_ids)
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
    # Build a deterministic pipeline fingerprint from the result
    fp_input = json.dumps(
        {
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "deduplicated_count": deduplicated_count,
            "error_count": len(errors),
            "as_of": request.as_of.isoformat(),
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
