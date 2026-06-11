"""IncrementalUpdater — add new facts to an existing source_regime_stats cache.

Inserts only fact_ids not already present, detects conflicts,
recomputes only affected summary groups, and verifies equivalence
with a clean full rebuild.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .db import integrity_check, open_db
from .rebuild import FullRebuilder, _validate_fact


class IncrementalUpdater:
    """Incremental updater for the source_regime_stats cache."""

    def __init__(self) -> None:
        self._temp_dir: tempfile.TemporaryDirectory | None = None

    def update(
        self,
        db_path: str | Path,
        facts: Iterable[dict],
    ) -> Path:
        """Incrementally add new facts to an existing cache database.

        Args:
            db_path: Path to existing source_regime_stats.db.
            facts: Iterable of new fact dicts to add.

        Returns:
            Path to the updated database.

        Raises:
            ValueError: On validation or conflict errors.
            RuntimeError: If incremental result differs from full rebuild.
        """
        db_path = Path(db_path)
        if not db_path.exists():
            msg = f"Existing database not found: {db_path}"
            raise FileNotFoundError(msg)

        fact_list = list(facts)

        # Validate all new facts before writing
        for fact in fact_list:
            _validate_fact(fact)

        # Open existing db and determine which fact_ids are new
        conn = open_db(str(db_path))
        try:
            # Get existing fact_ids
            existing_ids = {
                row[0]
                for row in conn.execute("SELECT fact_id FROM attribution_facts").fetchall()
            }

            # Filter to only new facts
            new_facts: list[dict] = []
            for fact in fact_list:
                fact_id = fact["fact_id"]
                if fact_id in existing_ids:
                    # Check for conflict
                    cursor = conn.execute(
                        "SELECT * FROM attribution_facts WHERE fact_id = ?",
                        (fact_id,),
                    )
                    existing = cursor.fetchone()
                    columns = [desc[0] for desc in cursor.description]
                    existing_dict = dict(zip(columns, existing, strict=False))

                    if not _fact_dicts_equal(fact, existing_dict):
                        msg = (
                            f"Conflict on fact_id={fact_id}: "
                            f"existing row differs from new row"
                        )
                        raise ValueError(msg)
                    # Identical -> skip
                else:
                    new_facts.append(fact)

            if not new_facts:
                conn.close()
                return db_path

            # Determine which summary groups are affected by new facts
            affected_keys: set[tuple[str, str, str, str, str, str]] = set()
            for fact in new_facts:
                key = _make_group_key(fact)
                affected_keys.add(key)

            # Insert new facts within a transaction
            try:
                conn.execute("BEGIN TRANSACTION;")

                for fact in new_facts:
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

                # Recompute only affected summary groups
                _recompute_affected_groups(conn, affected_keys)

                # Update metadata
                now_iso = datetime.now(UTC).isoformat()
                conn.execute("DELETE FROM cache_metadata;")
                conn.execute(
                    "INSERT INTO cache_metadata (schema_version, last_incremental_time, build_mode) "
                    "VALUES (?, ?, 'incremental')",
                    ("1.0", now_iso),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

            # Integrity check
            issues = integrity_check(conn)
            if issues:
                msg = f"SQLite integrity_check failed after incremental update: {issues}"
                raise RuntimeError(msg)

            # Verify incremental result == clean full rebuild from combined set
            self._verify_equivalence(db_path, new_facts, existing_ids, conn)

        finally:
            conn.close()

        return db_path

    def _verify_equivalence(
        self,
        db_path: Path,
        new_facts: list[dict],
        existing_ids: set[str],
        incremental_conn: sqlite3.Connection,
    ) -> None:
        """Verify that incremental update produces same result as full rebuild."""
        # Build the complete set of facts (existing + new)
        all_facts_cursor = incremental_conn.execute(
            "SELECT * FROM attribution_facts ORDER BY fact_id",
        )
        columns = [desc[0] for desc in all_facts_cursor.description]
        all_facts: list[dict] = []
        for row in all_facts_cursor.fetchall():
            all_facts.append(dict(zip(columns, row, strict=False)))

        if not all_facts:
            return  # Empty cache, nothing to compare

        # Do a clean full rebuild to a temp database
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="src_regime_verify_",
            dir=db_path.parent,
        )
        temp_db = os.path.join(self._temp_dir.name, "verify.db")

        rebuilder = FullRebuilder()
        rebuilder.build(all_facts, temp_db)

        # Compare source_regime_stats between incremental and full rebuild
        verify_conn = open_db(temp_db)
        try:
            inc_rows = incremental_conn.execute(
                "SELECT * FROM source_regime_stats ORDER BY source_id, strategy_or_model_id, "
                "pair, timeframe, regime, confidence_bucket"
            ).fetchall()

            full_rows = verify_conn.execute(
                "SELECT * FROM source_regime_stats ORDER BY source_id, strategy_or_model_id, "
                "pair, timeframe, regime, confidence_bucket"
            ).fetchall()

            if len(inc_rows) != len(full_rows):
                msg = (
                    f"Incremental update produced {len(inc_rows)} summary rows, "
                    f"full rebuild produced {len(full_rows)}"
                )
                raise RuntimeError(msg)

            inc_columns = [
                desc[0]
                for desc in incremental_conn.execute(
                    "SELECT * FROM source_regime_stats"
                ).description
            ]

            for inc_row, full_row in zip(inc_rows, full_rows, strict=False):
                for i, (a, b) in enumerate(zip(inc_row, full_row, strict=False)):
                    if isinstance(a, float) and isinstance(b, float):
                        if abs(a - b) > 1e-9:
                            msg = (
                                f"Summary mismatch at column {inc_columns[i]}: "
                                f"incremental={a}, full={b}"
                            )
                            raise RuntimeError(msg)
                    elif a != b:
                        msg = (
                            f"Summary mismatch at column {inc_columns[i]}: "
                            f"incremental={a!r}, full={b!r}"
                        )
                        raise RuntimeError(msg)
        finally:
            verify_conn.close()

    def cleanup(self) -> None:
        """Clean up temp directory if it exists."""
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()


def _fact_dicts_equal(a: dict, b: dict) -> bool:
    """Check two fact dicts for semantic equality (ignoring ordering)."""
    return dict(sorted(a.items())) == dict(sorted(b.items()))


def _make_group_key(fact: dict) -> tuple[str, str, str, str, str, str]:
    """Create a dimension group key tuple from a fact dict."""
    return (
        str(fact["source_id"]),
        str(fact.get("strategy_or_model_id") or ""),
        str(fact["pair"]),
        str(fact["timeframe"]),
        str(fact["regime"]),
        str(fact["confidence_bucket"]),
    )


def _recompute_affected_groups(
    conn: sqlite3.Connection,
    affected_keys: set[tuple[str, str, str, str, str, str]],
) -> None:
    """Recompute summary stats only for affected dimension groups."""
    for key in affected_keys:
        source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket = key

        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT trade_id),
                COUNT(*),
                SUM(CASE WHEN outcome_classification = 'WIN' THEN 1 ELSE 0 END),
                SUM(CASE WHEN outcome_classification = 'LOSS' THEN 1 ELSE 0 END),
                SUM(CASE WHEN outcome_classification = 'BREAKEVEN' THEN 1 ELSE 0 END),
                AVG(raw_trade_return),
                AVG(weighted_return),
                AVG(weighted_return),
                SUM(weighted_return)
            FROM attribution_facts
            WHERE source_id = ? AND COALESCE(strategy_or_model_id, '') = ?
                AND pair = ? AND timeframe = ? AND regime = ? AND confidence_bucket = ?
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
        ) = row

        decisive = win_count + loss_count
        win_rate = win_count / decisive if decisive > 0 else 0.0

        # Upsert the summary row
        conn.execute(
            """
            INSERT OR REPLACE INTO source_regime_stats (
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
