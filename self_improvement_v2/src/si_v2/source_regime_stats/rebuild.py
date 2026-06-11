"""FullRebuilder — create a fresh source_regime_stats SQLite cache from scratch.

Validates all facts, runs integrity checks, and performs atomic promotion
with a rename-first backup strategy.
"""

from __future__ import annotations

import contextlib
import copy
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .db import create_schema, integrity_check, open_db

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
    """Validate a single fact dict. Raises ValueError on any issue."""
    missing = FACT_REQUIRED_FIELDS - set(fact.keys())
    if missing:
        msg = f"Fact missing required fields: {sorted(missing)}"
        raise ValueError(msg)

    fact_id = fact.get("fact_id", "")
    if not isinstance(fact_id, str) or not fact_id:
        msg = f"Invalid or missing fact_id: {fact_id!r}"
        raise ValueError(msg)

    outcome = fact.get("outcome_classification", "")
    if outcome not in VALID_OUTCOMES:
        msg = f"Invalid outcome_classification: {outcome!r} in fact {fact_id}"
        raise ValueError(msg)

    regime = fact.get("regime", "")
    if regime not in VALID_REGIMES:
        msg = f"Invalid regime: {regime!r} in fact {fact_id}"
        raise ValueError(msg)

    for field in ("weighted_return", "raw_trade_return", "contribution_weight"):
        val = fact.get(field)
        if val is None or not isinstance(val, (int, float)):
            msg = f"Field {field!r} must be numeric in fact {fact_id}"
            raise ValueError(msg)

    for field in ("trade_id", "source_id", "pair", "timeframe", "provenance_hash"):
        val = fact.get(field)
        if not isinstance(val, str) or not val:
            msg = f"Field {field!r} must be a non-empty string in fact {fact_id}"
            raise ValueError(msg)


def _fact_dicts_equal(a: dict, b: dict) -> bool:
    """Check two fact dicts for semantic equality (ignoring ordering)."""
    return dict(sorted(a.items())) == dict(sorted(b.items()))


def _compute_stats(conn: sqlite3.Connection) -> None:
    """Recompute source_regime_stats from attribution_facts."""
    conn.execute("DELETE FROM source_regime_stats;")

    query = """
        SELECT
            source_id,
            COALESCE(strategy_or_model_id, '') AS strategy_or_model_id,
            pair,
            timeframe,
            regime,
            confidence_bucket,
            COUNT(DISTINCT trade_id) AS unique_trade_count,
            COUNT(*) AS source_contribution_count,
            SUM(CASE WHEN outcome_classification = 'WIN' THEN 1 ELSE 0 END) AS win_count,
            SUM(CASE WHEN outcome_classification = 'LOSS' THEN 1 ELSE 0 END) AS loss_count,
            SUM(CASE WHEN outcome_classification = 'BREAKEVEN' THEN 1 ELSE 0 END) AS breakeven_count,
            AVG(raw_trade_return) AS average_raw_return,
            AVG(weighted_return) AS average_weighted_return,
            AVG(weighted_return) AS expectancy,
            SUM(weighted_return) AS cumulative_weighted_return
        FROM attribution_facts
        GROUP BY source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket
        ORDER BY source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket
    """

    for row in conn.execute(query).fetchall():
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
            average_raw_return,
            average_weighted_return,
            expectancy,
            cumulative_weighted_return,
        ) = row

        decisive = win_count + loss_count
        win_rate = win_count / decisive if decisive > 0 else 0.0

        conn.execute(
            """
            INSERT INTO source_regime_stats (
                source_id, strategy_or_model_id, pair, timeframe, regime,
                confidence_bucket, unique_trade_count, source_contribution_count,
                win_count, loss_count, breakeven_count, win_rate,
                average_raw_return, average_weighted_return, expectancy,
                cumulative_weighted_return, drawdown_proxy,
                average_source_confidence, average_regime_confidence
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0
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
            ),
        )

    conn.commit()


class FullRebuilder:
    """Factory for creating a fresh source_regime_stats cache from facts."""

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
        2. Create temporary SQLite DB.
        3. Validate and insert all facts.
        4. Compute summary stats.
        5. Run integrity_check.
        6. Atomic promote (backup first, then rename temp -> target).

        Returns the final target path.
        """
        # Snapshot input so we can verify it's unchanged later
        fact_list = list(facts)
        input_snapshot = copy.deepcopy(fact_list)

        output_path = Path(output_path)
        output_parent = output_path.resolve().parent
        output_parent.mkdir(parents=True, exist_ok=True)

        # Create temp directory and db path
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="src_regime_rebuild_",
            dir=output_parent,
        )
        self._temp_path = os.path.join(self._temp_dir.name, "source_regime_stats.db")

        conn = open_db(self._temp_path)
        try:
            create_schema(conn)

            # Validate all facts before writing
            for fact in fact_list:
                _validate_fact(fact)

            # Insert all facts with conflict detection
            for fact in fact_list:
                self._insert_fact(conn, fact)

            # Compute summary stats
            _compute_stats(conn)

            # Integrity check
            issues = integrity_check(conn)
            if issues:
                msg = f"SQLite integrity_check failed: {issues}"
                raise RuntimeError(msg)

            # Insert metadata
            now_iso = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO cache_metadata (schema_version, last_rebuild_time, build_mode) "
                "VALUES (?, ?, 'full')",
                ("1.0", now_iso),
            )
            conn.commit()
        finally:
            conn.close()

        # Verify input is byte-for-byte unchanged
        self._verify_input_unchanged(input_snapshot, fact_list)

        # Atomic promote with backup
        self._promote(self._temp_path, output_path)

        return output_path

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
        """Atomically promote temp to target with rename-first backup.

        If target exists, rename it to *.bak first, then rename temp to target.
        """
        target_str = str(target_path)
        if target_path.exists():
            backup = target_path.with_suffix(".db.bak")
            if backup.exists():
                backup.unlink()
            shutil.move(target_str, str(backup))
            self._backup_path = str(backup)

        shutil.move(temp_path, target_str)

    def cleanup(self) -> None:
        """Clean up temp directory if it exists."""
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
