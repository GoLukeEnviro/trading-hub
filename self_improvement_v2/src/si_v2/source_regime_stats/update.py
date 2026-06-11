"""IncrementalUpdater — add new facts to an existing source_regime_stats cache.

Uses copy-on-write: backup API → apply to copy → compute groups → verify
integrity → compare with full rebuild logic → promote. On any failure the
copy is discarded and the original is left unchanged.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .db import (
    SCHEMA_VERSION,
    foreign_key_check,
    integrity_check,
    open_db,
)
from .rebuild import (
    FullRebuilder,
    _compute_input_fingerprint,
    _fact_dicts_equal,
    _validate_fact,
)


class IncrementalUpdater:
    """Incremental updater for the source_regime_stats cache.

    Uses copy-on-write: makes a working copy of the DB, applies changes,
    verifies integrity, then atomically promotes. If any step fails, the
    original is preserved and the copy is discarded.
    """

    def __init__(self) -> None:
        self._working_dir: tempfile.TemporaryDirectory | None = None
        self._working_db_path: str | None = None
        self._backup_path: str | None = None

    def update(
        self,
        db_path: str | Path,
        facts: Iterable[dict],
    ) -> Path:
        """Incrementally add new facts to an existing cache database.

        Uses copy-on-write: creates a working copy, applies changes, verifies
        integrity and equivalence, then atomically promotes.

        Args:
            db_path: Path to existing source_regime_stats.db.
            facts: Iterable of new fact dicts to add.

        Returns:
            Path to the updated database.

        Raises:
            ValueError: On validation or conflict errors.
            RuntimeError: If incremental result differs from full rebuild.
            FileNotFoundError: If existing database not found.
        """
        db_path = Path(db_path)
        if not db_path.exists():
            msg = f"Existing database not found: {db_path}"
            raise FileNotFoundError(msg)

        fact_list = list(facts)
        if not fact_list:
            # No-op: still verify integrity of existing DB
            conn = open_db(str(db_path))
            try:
                issues = integrity_check(conn)
                if issues:
                    msg = f"SQLite integrity_check failed: {issues}"
                    raise RuntimeError(msg)
            finally:
                conn.close()
            return db_path

        # Use a lock file in the same directory as the DB to prevent concurrent updates
        lock_path = db_path.with_name(f".{db_path.name}.lock")

        # Try to acquire the lock
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(lock_fd)
        except FileExistsError:
            msg = f"Concurrent update lock held: {lock_path}"
            raise RuntimeError(msg) from None

        try:
            return self._do_update(db_path, fact_list)
        finally:
            # Release the lock
            with contextlib.suppress(FileNotFoundError):
                os.unlink(str(lock_path))

    def _do_update(
        self,
        db_path: Path,
        fact_list: list[dict],
    ) -> Path:
        """Internal update method. Holds no lock — caller manages the file lock."""
        # Detect intra-batch duplicates
        FullRebuilder._detect_intra_batch_duplicates(fact_list)

        # Validate all new facts using the typed AttributionFact model
        for fact in fact_list:
            _validate_fact(fact)

        # Read existing facts from the DB
        read_conn = open_db(str(db_path))
        try:
            existing_cursor = read_conn.execute(
                "SELECT * FROM attribution_facts ORDER BY fact_id",
            )
            columns = [desc[0] for desc in existing_cursor.description]
            existing_facts: list[dict] = []
            for row in existing_cursor.fetchall():
                existing_facts.append(dict(zip(columns, row, strict=False)))
        finally:
            read_conn.close()

        existing_ids = {f["fact_id"] for f in existing_facts}

        # Determine which facts are new vs duplicates/conflicts
        new_facts: list[dict] = []
        conflicts: list[str] = []
        identical_skipped: int = 0

        # Build an index of existing facts by fact_id for quick lookup
        existing_by_id: dict[str, dict] = {f["fact_id"]: f for f in existing_facts}

        for fact in fact_list:
            fid = fact["fact_id"]
            if fid in existing_ids:
                if _fact_dicts_equal(fact, existing_by_id[fid]):
                    identical_skipped += 1  # No-op
                else:
                    conflicts.append(fid)
            else:
                new_facts.append(fact)

        if conflicts:
            msg = (
                f"Conflict on fact_ids: {conflicts}. "
                f"Existing rows differ from new rows"
            )
            raise ValueError(msg)

        if not new_facts and identical_skipped > 0:
            # All facts already present — no-op, still verify integrity
            check_conn = open_db(str(db_path))
            try:
                issues = integrity_check(check_conn)
                if issues:
                    msg = f"SQLite integrity_check failed: {issues}"
                    raise RuntimeError(msg)
            finally:
                check_conn.close()
            return db_path

        # --- Copy-on-write: create working copy ---
        self._working_dir = tempfile.TemporaryDirectory(
            prefix="src_regime_update_",
            dir=db_path.parent,
        )
        working_db = os.path.join(self._working_dir.name, "working.db")

        # Copy the existing DB to the working copy
        shutil.copy2(str(db_path), working_db)

        # Also copy WAL/SHM if they exist
        for suffix in ("-wal", "-shm"):
            src = f"{db_path}{suffix}"
            if os.path.exists(src):
                shutil.copy2(src, f"{working_db}{suffix}")

        # Open working copy
        working_conn = open_db(working_db)
        try:
            # Determine which summary keys are affected
            affected_keys: set[tuple[str, str, str, str, str, str]] = set()
            for fact in new_facts:
                key = _make_group_key(fact)
                affected_keys.add(key)

            # Also refresh groups whose existing facts may have changed
            # (relevant for drawdown proxy recomputation)
            for fact in fact_list:
                key = _make_group_key(fact)
                affected_keys.add(key)

            # Insert new facts in working copy within a transaction
            try:
                working_conn.execute("BEGIN TRANSACTION;")

                for fact in new_facts:
                    working_conn.execute(
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

                # Recompute all affected groups
                _recompute_affected_groups(working_conn, affected_keys)

                # Update metadata
                now_iso = datetime.now(UTC).isoformat()

                # Compute combined fingerprint
                all_facts_cur = working_conn.execute(
                    "SELECT * FROM attribution_facts ORDER BY fact_id",
                )
                all_columns = [desc[0] for desc in all_facts_cur.description]
                all_facts_list: list[dict] = []
                for row in all_facts_cur.fetchall():
                    all_facts_list.append(
                        dict(zip(all_columns, row, strict=False))
                    )
                combined_fingerprint = _compute_input_fingerprint(all_facts_list)

                working_conn.execute("DELETE FROM cache_metadata;")
                working_conn.execute(
                    """
                    INSERT INTO cache_metadata
                        (id, cache_schema_version, fact_schema_version, source_fingerprint,
                         build_mode, last_evidence_time, operation_timestamp)
                    VALUES (1, ?, ?, ?, 'incremental', ?, ?)
                    """,
                    (SCHEMA_VERSION, "1.0", combined_fingerprint, now_iso, now_iso),
                )

                # Recompute evidence_max_closed_at and last_updated for all groups
                working_conn.execute(
                    """
                    UPDATE source_regime_stats
                    SET last_updated = ?
                    """,
                    (now_iso,),
                )

                # Update evidence_max_closed_at per group from facts
                working_conn.execute(
                    """
                    UPDATE source_regime_stats
                    SET evidence_max_closed_at = (
                        SELECT MAX(closed_at)
                        FROM attribution_facts af
                        WHERE af.source_id = source_regime_stats.source_id
                            AND COALESCE(af.strategy_or_model_id, '')
                                = COALESCE(source_regime_stats.strategy_or_model_id, '')
                            AND af.pair = source_regime_stats.pair
                            AND af.timeframe = source_regime_stats.timeframe
                            AND af.regime = source_regime_stats.regime
                            AND af.confidence_bucket = source_regime_stats.confidence_bucket
                    )
                    """,
                )

                working_conn.commit()
            except Exception:
                working_conn.rollback()
                raise

            # Integrity check on working copy
            issues = integrity_check(working_conn)
            if issues:
                msg = f"SQLite integrity_check failed on working copy: {issues}"
                raise RuntimeError(msg)

            fk_issues = foreign_key_check(working_conn)
            if fk_issues:
                msg = f"SQLite foreign_key_check failed on working copy: {fk_issues}"
                raise RuntimeError(msg)

            # Verify incremental result == clean full rebuild from combined set
            self._verify_equivalence(working_conn, all_facts_list)

            # Checkpoint WAL on working copy
            working_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            working_conn.commit()
        finally:
            working_conn.close()

        # --- Promote: backup original, then replace with working copy ---
        self._promote(working_db, db_path)

        # Clean up temp artifacts
        self._clean_temp_artifacts()

        return db_path

    @staticmethod
    def _verify_equivalence(
        incremental_conn: sqlite3.Connection,
        all_facts: list[dict],
    ) -> None:
        """Verify that incremental update produces same result as full rebuild."""
        if not all_facts:
            return  # Empty cache, nothing to compare

        # Do a clean full rebuild to a temp database
        temp_dir = tempfile.TemporaryDirectory(
            prefix="src_regime_verify_",
        )
        try:
            temp_db = os.path.join(temp_dir.name, "verify.db")

            rebuilder = FullRebuilder()
            rebuilder.build(all_facts, temp_db)

            # Compare source_regime_stats between incremental and full rebuild
            verify_conn = open_db(temp_db)
            try:
                inc_rows = incremental_conn.execute(
                    "SELECT * FROM source_regime_stats ORDER BY source_id, "
                    "COALESCE(strategy_or_model_id, ''), pair, timeframe, "
                    "regime, confidence_bucket"
                ).fetchall()

                full_rows = verify_conn.execute(
                    "SELECT * FROM source_regime_stats ORDER BY source_id, "
                    "COALESCE(strategy_or_model_id, ''), pair, timeframe, "
                    "regime, confidence_bucket"
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
                        col = inc_columns[i]

                        # Skip metadata fields that will differ (timestamps, fingerprints)
                        if col in ("last_updated", "operation_timestamp",
                                   "input_fingerprint", "source_fingerprint",
                                   "last_evidence_time", "build_mode",
                                   "cache_schema_version", "fact_schema_version"):
                            continue

                        if isinstance(a, float) and isinstance(b, float):
                            if abs(a - b) > 1e-9:
                                msg = (
                                    f"Summary mismatch at column {col}: "
                                    f"incremental={a}, full={b}"
                                )
                                raise RuntimeError(msg)
                        elif a != b:
                            msg = (
                                f"Summary mismatch at column {col}: "
                                f"incremental={a!r}, full={b!r}"
                            )
                            raise RuntimeError(msg)
            finally:
                verify_conn.close()
        finally:
            with contextlib.suppress(Exception):
                temp_dir.cleanup()

    def _promote(self, working_path: str, target_path: Path) -> None:
        """Atomically promote working copy to target with backup.

        1. Copy existing target to timestamped .bak.
        2. Use os.replace (atomic on same filesystem).
        3. On failure, restore from .bak.
        """
        target_str = str(target_path)
        self._backup_path = None

        if target_path.exists():
            now = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup = target_path.with_name(f"{target_path.name}.{now}.bak")
            shutil.copy2(target_str, str(backup))
            self._backup_path = str(backup)

        try:
            os.replace(working_path, target_str)
        except Exception:
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
        """Clean up temporary working directory and any WAL/SHM artifacts."""
        if self._working_dir is not None:
            temp_dir_path = self._working_dir.name
            # Clean up any leftover WAL/SHM files
            for suffix in ("-wal", "-shm"):
                artifact = os.path.join(temp_dir_path, f"working.db{suffix}")
                if os.path.exists(artifact):
                    with contextlib.suppress(Exception):
                        os.unlink(artifact)
            with contextlib.suppress(Exception):
                self._working_dir.cleanup()
                self._working_dir = None

    def cleanup(self) -> None:
        """Clean up temp directory if it exists."""
        self._clean_temp_artifacts()


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
        source_id, strategy_or_model_id_str, pair, timeframe, regime, confidence_bucket = key

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
                SUM(weighted_return),
                MAX(closed_at)
            FROM attribution_facts
            WHERE source_id = ? AND COALESCE(strategy_or_model_id, '') = ?
                AND pair = ? AND timeframe = ? AND regime = ? AND confidence_bucket = ?
            """,
            (
                source_id,
                strategy_or_model_id_str,
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
        ) = row

        decisive = win_count + loss_count
        win_rate = win_count / decisive if decisive > 0 else 0.0

        # Compute drawdown proxy for this group
        drawdown_proxy = _compute_group_drawdown(
            conn, source_id, strategy_or_model_id_str,
            pair, timeframe, regime, confidence_bucket,
        )

        now_iso = datetime.now(UTC).isoformat()

        # Upsert the summary row
        conn.execute(
            """
            INSERT OR REPLACE INTO source_regime_stats (
                source_id, strategy_or_model_id, pair, timeframe, regime,
                confidence_bucket, unique_trade_count, source_contribution_count,
                win_count, loss_count, breakeven_count, win_rate,
                average_raw_return, average_weighted_return, expectancy,
                cumulative_weighted_return, drawdown_proxy,
                average_source_confidence, average_regime_confidence,
                evidence_max_closed_at, last_updated
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                source_id,
                strategy_or_model_id_str,
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
                None,  # average_source_confidence
                None,  # average_regime_confidence
                evidence_max_closed_at,
                now_iso,
            ),
        )


def _compute_group_drawdown(
    conn: sqlite3.Connection,
    source_id: str,
    strategy_or_model_id: str,
    pair: str,
    timeframe: str,
    regime: str,
    confidence_bucket: str,
) -> float:
    """Compute drawdown proxy from time-ordered cumulative weighted returns."""
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
            strategy_or_model_id,
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

    for weighted_return, _ in rows:
        cumulative += weighted_return
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return max_drawdown
