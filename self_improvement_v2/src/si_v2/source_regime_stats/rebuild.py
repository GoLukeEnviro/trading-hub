"""FullRebuilder — create a fresh source_regime_stats SQLite cache from scratch.

Validates all facts using the #57 AttributionFact pydantic model, runs
integrity checks, computes correct drawdown proxy, and performs atomic
promotion with timestamped .bak backup and rollback on failure.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import math
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from si_v2.attribution.models import AttributionFact

from .db import (
    SCHEMA_VERSION,
    create_schema,
    foreign_key_check,
    integrity_check,
    open_db,
)

FACT_REQUIRED_FIELDS = frozenset({
    "fact_id",
    "trade_id",
    "source_id",
    "pair",
    "timeframe",
    "regime",
    "confidence_bucket",
    "weighted_return",
    "raw_trade_return",
    "contribution_weight",
    "outcome_classification",
    "closed_at",
    "provenance_hash",
    "schema_version",
})

VALID_OUTCOMES = frozenset({"WIN", "LOSS", "BREAKEVEN"})
VALID_REGIMES = frozenset({"bullish", "bearish", "neutral", "unknown"})


def _validate_fact(fact: dict) -> None:
    """Validate a single fact dict against the #57 AttributionFact model.

    Uses pydantic model_validate() which rejects bool, NaN, inf, out-of-range,
    and non-canonical timestamp values automatically.
    """
    # First check for required fields
    missing = FACT_REQUIRED_FIELDS - set(fact.keys())
    if missing:
        msg = f"Fact missing required fields: {sorted(missing)}"
        raise ValueError(msg)

    fact_id = fact.get("fact_id", "")
    if not isinstance(fact_id, str) or not fact_id:
        msg = f"Invalid or missing fact_id: {fact_id!r}"
        raise ValueError(msg)

    # --- Extra scalar checks before model_validate ---
    # Reject bool masquerading as numeric
    for field in ("weighted_return", "raw_trade_return", "contribution_weight"):
        val = fact.get(field)
        if isinstance(val, bool):
            msg = f"Field {field!r} must be numeric, got bool in fact {fact_id}"
            raise ValueError(msg)
        if val is None:
            msg = f"Field {field!r} cannot be None in fact {fact_id}"
            raise ValueError(msg)
        if not isinstance(val, (int, float)):
            msg = f"Field {field!r} must be numeric in fact {fact_id}"
            raise ValueError(msg)
        if isinstance(val, float) and not math.isfinite(val):
            msg = f"Field {field!r} must be finite in fact {fact_id}"
            raise ValueError(msg)

    # Reject contribution_weight out of (0, 1]
    cw = fact["contribution_weight"]
    if cw <= 0 or cw > 1.0:
        msg = f"contribution_weight must be in (0, 1], got {cw} in fact {fact_id}"
        raise ValueError(msg)

    # Validate outcome
    outcome = fact.get("outcome_classification", "")
    if outcome not in VALID_OUTCOMES:
        msg = f"Invalid outcome_classification: {outcome!r} in fact {fact_id}"
        raise ValueError(msg)

    # Validate regime
    regime = fact.get("regime", "")
    if regime not in VALID_REGIMES:
        msg = f"Invalid regime: {regime!r} in fact {fact_id}"
        raise ValueError(msg)

    # Validate non-empty identity fields
    for field in ("trade_id", "source_id", "pair", "timeframe", "provenance_hash"):
        val = fact.get(field)
        if not isinstance(val, str) or not val:
            msg = f"Field {field!r} must be a non-empty string in fact {fact_id}"
            raise ValueError(msg)

    # Validate closed_at is a timezone-aware ISO string
    closed_at = fact.get("closed_at", "")
    if not isinstance(closed_at, str) or not closed_at:
        msg = f"closed_at must be a non-empty string in fact {fact_id}"
        raise ValueError(msg)
    _validate_timestamp(closed_at, fact_id)

    # Validate schema_version
    sv = fact.get("schema_version", "")
    if sv not in ("1.0",):
        msg = f"Unsupported schema_version {sv!r} in fact {fact_id}"
        raise ValueError(msg)

    # --- Run pydantic model_validate for full type coercion ---
    try:
        AttributionFact.model_validate(fact)
    except Exception as exc:
        msg = f"AttributionFact model validation failed for fact {fact_id}: {exc}"
        raise ValueError(msg) from exc


def _validate_timestamp(ts: str, fact_id: str) -> None:
    """Validate that a timestamp string is in canonical UTC ISO 8601 format."""
    try:
        # Parse and re-validate it's timezone-aware
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            msg = f"closed_at must be timezone-aware in fact {fact_id}, got naive: {ts!r}"
            raise ValueError(msg)
        # Ensure it's in UTC and in canonical form
        utc_dt = dt.astimezone(UTC)
        canonical = utc_dt.isoformat()
        # Accept both +00:00 and Z forms, canonicalize to +00:00
        if ts != canonical and ts != canonical.replace("+00:00", "Z"):
            msg = (
                f"closed_at must be canonical UTC ISO 8601 in fact {fact_id}: "
                f"got {ts!r}, expected {canonical!r}"
            )
            raise ValueError(msg)
    except ValueError as exc:
        if "must be timezone-aware" in str(exc):
            raise
        msg = f"Invalid closed_at timestamp {ts!r} in fact {fact_id}: {exc}"
        raise ValueError(msg) from exc


def _fact_dicts_equal(a: dict, b: dict) -> bool:
    """Check two fact dicts for semantic equality (ignoring ordering)."""
    return dict(sorted(a.items())) == dict(sorted(b.items()))


def _compute_input_fingerprint(facts: list[dict]) -> str:
    """Compute a deterministic fingerprint of the source data.

    Uses sorted JSON representation to ensure determinism regardless of input order.
    """
    sorted_facts = sorted(facts, key=lambda f: f.get("fact_id", ""))
    raw = "|".join(
        _canonical_json(f) for f in sorted_facts
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _canonical_json(obj: dict) -> str:
    """Produce deterministic JSON for a fact dict."""
    import json
    return json.dumps(obj, sort_keys=True, default=str)


def _compute_drawdown_proxy(
    conn: sqlite3.Connection,
    source_id: str,
    strategy_or_model_id: str | None,
    pair: str,
    timeframe: str,
    regime: str,
    confidence_bucket: str,
) -> float:
    """Compute drawdown proxy from time-ordered cumulative weighted returns.

    Drawdown proxy = max peak-to-trough decline in cumulative weighted returns,
    ordered by closed_at ascending. Returns 0.0 if fewer than 2 facts.
    """
    rows = conn.execute(
        """
        SELECT weighted_return, closed_at
        FROM attribution_facts
        WHERE source_id = ? AND COALESCE(strategy_or_model_id, '') = ?
            AND pair = ? AND timeframe = ? AND regime = ? AND confidence_bucket = ?
        ORDER BY closed_at ASC, fact_id ASC
        """,
        (
            source_id,
            strategy_or_model_id or "",
            pair,
            timeframe,
            regime,
            confidence_bucket,
        ),
    ).fetchall()

    if len(rows) < 2:
        return 0.0

    cumulative = 0.0
    peak = -float("inf")
    max_drawdown = 0.0

    for weighted_return, _closed_at in rows:
        cumulative += weighted_return
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return max_drawdown


def _compute_stats(conn: sqlite3.Connection, input_fingerprint: str) -> None:
    """Recompute source_regime_stats from attribution_facts.

    Computes drawdown proxy from time-ordered cumulative weighted returns
    and stores source/regime confidence only if present.
    """
    conn.execute("DELETE FROM source_regime_stats;")

    # Step 1: Get dimension groups
    dimension_query = """
        SELECT DISTINCT
            source_id,
            COALESCE(strategy_or_model_id, '') AS strategy_or_model_id,
            pair,
            timeframe,
            regime,
            confidence_bucket
        FROM attribution_facts
        ORDER BY source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket
    """

    groups = conn.execute(dimension_query).fetchall()
    now_iso = datetime.now(UTC).isoformat()

    for group in groups:
        (
            source_id,
            strategy_or_model_id,
            pair,
            timeframe,
            regime,
            confidence_bucket,
        ) = group

        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT trade_id) AS unique_trade_count,
                COUNT(*) AS source_contribution_count,
                SUM(CASE WHEN outcome_classification = 'WIN' THEN 1 ELSE 0 END) AS win_count,
                SUM(CASE WHEN outcome_classification = 'LOSS' THEN 1 ELSE 0 END) AS loss_count,
                SUM(CASE WHEN outcome_classification = 'BREAKEVEN' THEN 1 ELSE 0 END) AS breakeven_count,
                AVG(raw_trade_return) AS average_raw_return,
                AVG(weighted_return) AS average_weighted_return,
                AVG(weighted_return) AS expectancy,
                SUM(weighted_return) AS cumulative_weighted_return,
                MAX(closed_at) AS evidence_max_closed_at,
                AVG(average_source_confidence_inner) AS avg_source_conf,
                AVG(average_regime_confidence_inner) AS avg_regime_conf
            FROM (
                SELECT *,
                    NULL AS average_source_confidence_inner,
                    NULL AS average_regime_confidence_inner
                FROM attribution_facts
                WHERE source_id = ? AND COALESCE(strategy_or_model_id, '') = ?
                    AND pair = ? AND timeframe = ? AND regime = ? AND confidence_bucket = ?
            )
            """,
            (
                source_id,
                strategy_or_model_id,
                pair,
                timeframe,
                regime,
                confidence_bucket,
            ),
        ).fetchone()

        (
            unique_trade_count,
            source_contribution_count,
            win_count,
            loss_count,
            breakeven_count,
            average_raw_return,
            average_weighted_return,
            expectancy,
            cumulative_weighted_return,
            evidence_max_closed_at,
            _avg_source_conf,
            _avg_regime_conf,
        ) = row

        # Win rate: decisive = win_count + loss_count (breakevens excluded from denominator)
        decisive = win_count + loss_count
        win_rate = win_count / decisive if decisive > 0 else 0.0

        # Drawdown proxy from time-ordered cumulative weighted returns
        drawdown_proxy = _compute_drawdown_proxy(
            conn,
            source_id,
            strategy_or_model_id,
            pair,
            timeframe,
            regime,
            confidence_bucket,
        )

        conn.execute(
            """
            INSERT INTO source_regime_stats (
                source_id, strategy_or_model_id, pair, timeframe, regime,
                confidence_bucket, unique_trade_count, source_contribution_count,
                win_count, loss_count, breakeven_count, win_rate,
                average_raw_return, average_weighted_return, expectancy,
                cumulative_weighted_return, drawdown_proxy,
                average_source_confidence, average_regime_confidence,
                evidence_max_closed_at, input_fingerprint, last_updated
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                source_id,
                strategy_or_model_id,
                pair,
                timeframe,
                regime,
                confidence_bucket,
                unique_trade_count,
                source_contribution_count,
                win_count,
                loss_count,
                breakeven_count,
                win_rate,
                average_raw_return,
                average_weighted_return,
                expectancy,
                cumulative_weighted_return,
                drawdown_proxy,
                None,  # average_source_confidence — not in #57 fact model
                None,  # average_regime_confidence — not in #57 fact model
                evidence_max_closed_at,
                input_fingerprint,
                now_iso,
            ),
        )

    conn.commit()


class FullRebuilder:
    """Factory for creating a fresh source_regime_stats cache from facts.

    Uses copy-on-write: builds temp DB → validates → integrity_check →
    checkpoint WAL → timestamped .bak backup → os.replace promote.
    On promotion failure: restores original from .bak.
    """

    def __init__(self) -> None:
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._temp_path: str | None = None
        self._backup_path: str | None = None

    def build(
        self,
        facts: Iterable[dict],
        output_path: str | Path,
    ) -> Path:
        """Build a fresh cache at output_path from the given fact dicts.

        Steps:
        1. Snapshot input for byte-for-byte verification.
        2. Detect duplicates within the input batch.
        3. Validate all facts using pydantic model_validate().
        4. Create temporary SQLite DB.
        5. Insert all facts with conflict detection.
        6. Compute summary stats (with real drawdown proxy).
        7. Run integrity_check and foreign_key_check.
        8. Checkpoint WAL.
        9. Create timestamped .bak backup of target.
        10. os.replace promote (atomic on same filesystem).
        11. On failure: restore original from .bak.
        12. Clean temporary WAL/SHM artifacts.
        """
        # Snapshot input so we can verify it's unchanged later
        fact_list = list(facts)
        input_snapshot = copy.deepcopy(fact_list)

        output_path = Path(output_path)
        output_parent = output_path.resolve().parent
        output_parent.mkdir(parents=True, exist_ok=True)

        # Detect intra-batch duplicates before any mutation
        self._detect_intra_batch_duplicates(fact_list)

        # Validate ALL facts using the typed AttributionFact model (rejects bool, NaN, inf, etc.)
        for fact in fact_list:
            _validate_fact(fact)

        # Compute input fingerprint from validated facts
        input_fingerprint = _compute_input_fingerprint(fact_list)

        # Create temp directory and db path
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="src_regime_rebuild_",
            dir=output_parent,
        )
        self._temp_path = os.path.join(self._temp_dir.name, "source_regime_stats.db")

        conn = open_db(self._temp_path)
        try:
            create_schema(conn)

            # Insert all facts with conflict detection
            for fact in fact_list:
                self._insert_fact(conn, fact)

            # Compute summary stats (with real drawdown proxy)
            _compute_stats(conn, input_fingerprint)

            # Insert metadata using single-row pattern
            now_iso = datetime.now(UTC).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_metadata
                    (id, cache_schema_version, fact_schema_version, source_fingerprint,
                     build_mode, last_evidence_time, operation_timestamp)
                VALUES (1, ?, ?, ?, 'full', ?, ?)
                """,
                (SCHEMA_VERSION, "1.0", input_fingerprint, now_iso, now_iso),
            )
            conn.commit()

            # Integrity checks
            issues = integrity_check(conn)
            if issues:
                msg = f"SQLite integrity_check failed: {issues}"
                raise RuntimeError(msg)

            fk_issues = foreign_key_check(conn)
            if fk_issues:
                msg = f"SQLite foreign_key_check failed: {fk_issues}"
                raise RuntimeError(msg)

            # Checkpoint WAL to flush journal
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.commit()
        finally:
            conn.close()

        # Verify input is byte-for-byte unchanged
        self._verify_input_unchanged(input_snapshot, fact_list)

        # Atomic promote with timestamped backup
        self._promote(self._temp_path, output_path)

        # Clean up temp WAL/SHM artifacts
        self._clean_temp_artifacts()

        return output_path

    @staticmethod
    def _detect_intra_batch_duplicates(facts: list[dict]) -> None:
        """Detect duplicate fact_ids within the same input batch.

        Raises ValueError if the same fact_id appears more than once with
        different content. Silently skips identical duplicates.
        """
        seen: dict[str, dict] = {}
        for fact in facts:
            fid: str | None = fact.get("fact_id")  # type: ignore[type-arg]
            if fid is None:
                msg = "Fact missing fact_id in input batch"
                raise ValueError(msg)
            if fid in seen:
                if not _fact_dicts_equal(fact, seen[fid]):
                    msg = (
                        f"Duplicate fact_id={fid} within input batch with "
                        f"different content"
                    )
                    raise ValueError(msg)
                # Identical duplicate — will be deduped on insert
            else:
                seen[fid] = fact

    def _insert_fact(self, conn: sqlite3.Connection, fact: dict) -> None:
        """Insert a single fact with conflict detection.

        ON CONFLICT:
        - Identical row -> silently skip
        - Different row -> raise ValueError
        """
        fact_id = fact["fact_id"]

        existing = conn.execute(
            "SELECT * FROM attribution_facts WHERE fact_id = ?", (fact_id,),
        ).fetchone()

        if existing is not None:
            cursor = conn.execute(
                "SELECT * FROM attribution_facts WHERE fact_id = ?", (fact_id,),
            )
            columns = [desc[0] for desc in cursor.description]
            existing_dict = dict(zip(columns, existing, strict=False))

            if _fact_dicts_equal(fact, existing_dict):
                return  # Identical, skip silently

            msg = (
                f"Conflict on fact_id={fact_id}: "
                f"existing row differs from new row"
            )
            raise ValueError(msg)

        conn.execute(
            """
            INSERT INTO attribution_facts (
                fact_id, trade_id, source_id, strategy_or_model_id,
                pair, timeframe, regime, confidence_bucket,
                weighted_return, raw_trade_return, contribution_weight,
                outcome_classification, closed_at, provenance_hash,
                schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact["fact_id"],
                fact["trade_id"],
                fact["source_id"],
                fact.get("strategy_or_model_id"),
                fact["pair"],
                fact["timeframe"],
                fact["regime"],
                fact["confidence_bucket"],
                fact["weighted_return"],
                fact["raw_trade_return"],
                fact["contribution_weight"],
                fact["outcome_classification"],
                fact["closed_at"],
                fact["provenance_hash"],
                fact.get("schema_version", "1.0"),
            ),
        )
        conn.commit()

    def _verify_input_unchanged(
        self,
        snapshot: list[dict],
        current: list[dict],
    ) -> None:
        """Verify that the input fact list hasn't been mutated during processing."""
        if len(snapshot) != len(current):
            msg = "Input fact list length changed during rebuild"
            raise RuntimeError(msg)
        for i, (s, c) in enumerate(zip(snapshot, current, strict=False)):
            if s != c:
                msg = f"Input fact at index {i} mutated during rebuild"
                raise RuntimeError(msg)

    def _promote(self, temp_path: str, target_path: Path) -> None:
        """Atomically promote temp to target with timestamped backup.

        1. If target exists, copy to timestamped .bak first.
        2. Use os.replace (atomic on same filesystem) to promote temp -> target.
        3. On failure, restore from .bak.
        """
        target_str = str(target_path)
        self._backup_path = None

        if target_path.exists():
            now = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup = target_path.with_name(f"{target_path.name}.{now}.bak")
            # Copy the existing file to backup
            shutil.copy2(target_str, str(backup))
            self._backup_path = str(backup)

        try:
            os.replace(temp_path, target_str)
        except Exception:
            # Promotion failed — restore original from backup if it existed
            if self._backup_path is not None:
                try:
                    shutil.copy2(self._backup_path, target_str)
                except Exception as restore_err:
                    msg = (
                        f"Promotion failed AND restore from backup failed: "
                        f"{restore_err}"
                    )
                    raise RuntimeError(msg) from restore_err
            raise

    def _clean_temp_artifacts(self) -> None:
        """Clean up temporary WAL/SHM and directory artifacts."""
        if self._temp_dir is not None:
            temp_dir_path = self._temp_dir.name
            # Clean up any leftover WAL/SHM files
            for suffix in ("-wal", "-shm"):
                artifact = os.path.join(temp_dir_path, f"source_regime_stats.db{suffix}")
                if os.path.exists(artifact):
                    with contextlib.suppress(Exception):
                        os.unlink(artifact)
            # Cleanup the temp directory
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
                self._temp_dir = None

    def cleanup(self) -> None:
        """Clean up temp directory if it exists."""
        self._clean_temp_artifacts()
