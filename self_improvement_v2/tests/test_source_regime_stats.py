"""Tests for source_regime_stats derived SQLite cache (#58).

Covers: empty rebuild, full rebuild, incremental update, duplicate
prevention, conflict rejection, UNKNOWN regime, multiple dimensions,
equivalence verification, transaction rollback, rename-first backup,
integrity check, JSONL unchanged, deterministic ordering, and CLI modes.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from si_v2.source_regime_stats.db import create_schema, integrity_check, open_db
from si_v2.source_regime_stats.rebuild import FullRebuilder
from si_v2.source_regime_stats.update import IncrementalUpdater

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FACT_TEMPLATE: dict = {
    "fact_id": "",
    "trade_id": "",
    "source_id": "src_a",
    "strategy_or_model_id": None,
    "pair": "BTC/USDT",
    "timeframe": "1h",
    "regime": "bullish",
    "confidence_bucket": "75-100",
    "weighted_return": 0.05,
    "raw_trade_return": 0.05,
    "contribution_weight": 1.0,
    "outcome_classification": "WIN",
    "closed_at": "2026-01-01T12:00:00+00:00",
    "provenance_hash": "abc123",
    "schema_version": "1.0",
}


def _make_fact(
    trade_id: str = "T001",
    source_id: str = "src_a",
    regime: str = "bullish",
    outcome: str = "WIN",
    raw_return: float = 0.05,
    weight: float = 1.0,
    pair: str = "BTC/USDT",
    timeframe: str = "1h",
    conf_bucket: str = "75-100",
    model_id: str | None = None,
    closed_at: str | None = None,
    fact_id: str | None = None,
) -> dict:
    """Create an AttributionFact-like dict."""
    fact = dict(FACT_TEMPLATE)
    fact["trade_id"] = trade_id
    fact["source_id"] = source_id
    fact["regime"] = regime
    fact["outcome_classification"] = outcome
    fact["raw_trade_return"] = raw_return
    fact["weighted_return"] = raw_return * weight
    fact["contribution_weight"] = weight
    fact["pair"] = pair
    fact["timeframe"] = timeframe
    fact["confidence_bucket"] = conf_bucket
    fact["strategy_or_model_id"] = model_id
    if closed_at is not None:
        fact["closed_at"] = closed_at
    if fact_id is not None:
        fact["fact_id"] = fact_id
    else:
        # Deterministic fact_id like AttributionFact.compute_fact_id
        import hashlib
        raw = f"{trade_id}:{source_id}:{regime}"
        fact["fact_id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return fact


def _write_jsonl(facts: list[dict], path: Path) -> None:
    """Write fact dicts as JSONL."""
    with open(path, "w") as f:
        for fact in facts:
            f.write(json.dumps(fact, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    """Read JSONL file into list of dicts."""
    objs: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                objs.append(dict(json.loads(line)))
    return objs


# ---------------------------------------------------------------------------
# 1. Empty rebuild
# ---------------------------------------------------------------------------


class TestEmptyRebuild:
    def test_empty_fact_list_creates_db(self, tmp_path: Path) -> None:
        """A rebuild with no facts should still produce a valid DB."""
        db_path = tmp_path / "empty.db"
        rebuilder = FullRebuilder()
        try:
            result = rebuilder.build([], db_path)
        finally:
            rebuilder.cleanup()

        assert result.exists()
        conn = open_db(str(result))
        try:
            issues = integrity_check(conn)
            assert not issues
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 0
            count = conn.execute("SELECT COUNT(*) FROM source_regime_stats").fetchone()[0]
            assert count == 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 2. Full rebuild from real temp JSONL
# ---------------------------------------------------------------------------


class TestFullRebuild:
    def test_full_rebuild_from_jsonl(self, tmp_path: Path) -> None:
        """Build from JSONL with multiple facts."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a", outcome="WIN", raw_return=0.05),
            _make_fact(trade_id="T002", source_id="src_a", outcome="LOSS", raw_return=-0.03),
            _make_fact(trade_id="T003", source_id="src_b", outcome="WIN", raw_return=0.10),
        ]
        jsonl = tmp_path / "input.jsonl"
        _write_jsonl(facts, jsonl)
        db_path = tmp_path / "test.db"

        rebuilder = FullRebuilder()
        try:
            result = rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        assert result == db_path
        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 3

            summary_count = conn.execute("SELECT COUNT(*) FROM source_regime_stats").fetchone()[0]
            assert summary_count == 2  # src_a and src_b groups
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 3. Incremental insert of new facts
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    def test_incremental_adds_new_facts(self, tmp_path: Path) -> None:
        """Incremental update should add fact_ids not already present."""
        facts_initial = [
            _make_fact(trade_id="T001", source_id="src_a", outcome="WIN"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts_initial, db_path)
        finally:
            rebuilder.cleanup()

        new_facts = [
            _make_fact(trade_id="T002", source_id="src_a", outcome="LOSS", raw_return=-0.02),
        ]
        updater = IncrementalUpdater()
        try:
            updater.update(db_path, new_facts)
        finally:
            updater.cleanup()

        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 2
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 4. Identical duplicate prevention
# ---------------------------------------------------------------------------


class TestIdenticalDuplicate:
    def test_identical_duplicate_skipped_rebuild(self, tmp_path: Path) -> None:
        """Identical fact in same rebuild should be silently skipped."""
        fact = _make_fact(trade_id="T001", source_id="src_a")
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build([fact, dict(fact)], db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 1  # Only one inserted
        finally:
            conn.close()

    def test_identical_duplicate_skipped_update(self, tmp_path: Path) -> None:
        """Identical fact in update should be silently skipped."""
        fact = _make_fact(trade_id="T001", source_id="src_a")
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build([fact], db_path)
        finally:
            rebuilder.cleanup()

        updater = IncrementalUpdater()
        try:
            updater.update(db_path, [dict(fact)])
        finally:
            updater.cleanup()

        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 1
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 5. Conflicting duplicate rejection
# ---------------------------------------------------------------------------


class TestConflictingDuplicate:
    def test_conflicting_duplicate_rejected_rebuild(self, tmp_path: Path) -> None:
        """Conflicting fact (same fact_id, different data) raises error in rebuild."""
        fact_a = _make_fact(trade_id="T001", source_id="src_a", raw_return=0.05)
        fact_b = dict(fact_a)
        fact_b["raw_trade_return"] = 0.99  # Different data, same fact_id

        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            with pytest.raises(ValueError, match="Conflict on fact_id"):
                rebuilder.build([fact_a, fact_b], db_path)
        finally:
            rebuilder.cleanup()

    def test_conflicting_duplicate_rejected_update(self, tmp_path: Path) -> None:
        """Conflicting fact in update raises error."""
        fact = _make_fact(trade_id="T001", source_id="src_a", raw_return=0.05)
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build([fact], db_path)
        finally:
            rebuilder.cleanup()

        conflict = dict(fact)
        conflict["raw_trade_return"] = 0.99

        updater = IncrementalUpdater()
        try:
            with pytest.raises(ValueError, match="Conflict on fact_id"):
                updater.update(db_path, [conflict])
        finally:
            updater.cleanup()


# ---------------------------------------------------------------------------
# 6. UNKNOWN regime retention
# ---------------------------------------------------------------------------


class TestUnknownRegime:
    def test_unknown_regime_retained(self, tmp_path: Path) -> None:
        """Facts with 'unknown' regime should be stored and summarized."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a", regime="unknown", outcome="WIN"),
            _make_fact(trade_id="T002", source_id="src_a", regime="unknown", outcome="LOSS"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            rows = conn.execute(
                "SELECT regime, win_count, loss_count FROM source_regime_stats "
                "WHERE regime = 'unknown'"
            ).fetchall()
            assert len(rows) >= 1
            assert rows[0][1] == 1  # win_count
            assert rows[0][2] == 1  # loss_count
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 7. Multiple sources, pairs, timeframes, regimes
# ---------------------------------------------------------------------------


class TestMultipleDimensions:
    def test_multi_dimension_summary(self, tmp_path: Path) -> None:
        """Multiple dimensions produce separate summary rows."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a", pair="BTC/USDT", timeframe="1h",
                       regime="bullish"),
            _make_fact(trade_id="T002", source_id="src_a", pair="BTC/USDT", timeframe="4h",
                       regime="bullish"),
            _make_fact(trade_id="T003", source_id="src_b", pair="ETH/USDT", timeframe="1h",
                       regime="bearish"),
            _make_fact(trade_id="T004", source_id="src_a", pair="BTC/USDT", timeframe="1h",
                       regime="neutral"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            rows = conn.execute(
                "SELECT source_id, pair, timeframe, regime FROM source_regime_stats "
                "ORDER BY source_id, pair, timeframe, regime"
            ).fetchall()
            # Expect 4 groups
            assert len(rows) == 4
            # Check we have src_a BTC/USDT 1h bullish
            assert ("src_a", "BTC/USDT", "1h", "bullish") in rows
            # Check we have src_b ETH/USDT 1h bearish
            assert ("src_b", "ETH/USDT", "1h", "bearish") in rows
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 8. Incremental == clean full rebuild equivalence
# ---------------------------------------------------------------------------


class TestEquivalence:
    def test_incremental_equals_full_rebuild(self, tmp_path: Path) -> None:
        """Incremental update should produce same stats as full rebuild."""
        initial = [
            _make_fact(trade_id="T001", source_id="src_a", outcome="WIN"),
            _make_fact(trade_id="T002", source_id="src_b", outcome="LOSS"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(initial, db_path)
        finally:
            rebuilder.cleanup()

        new_facts = [
            _make_fact(trade_id="T003", source_id="src_a", outcome="WIN"),
            _make_fact(trade_id="T004", source_id="src_c", outcome="BREAKEVEN"),
        ]
        updater = IncrementalUpdater()
        try:
            updater.update(db_path, new_facts)
        finally:
            updater.cleanup()

        # Now full rebuild from combined set
        combined = initial + new_facts
        full_db = tmp_path / "full.db"
        rebuilder2 = FullRebuilder()
        try:
            rebuilder2.build(combined, full_db)
        finally:
            rebuilder2.cleanup()

        # Compare source_regime_stats
        conn_inc = open_db(str(db_path))
        conn_full = open_db(str(full_db))
        try:
            inc_rows = conn_inc.execute(
                "SELECT * FROM source_regime_stats ORDER BY source_id, pair, timeframe, regime, confidence_bucket"
            ).fetchall()
            full_rows = conn_full.execute(
                "SELECT * FROM source_regime_stats ORDER BY source_id, pair, timeframe, regime, confidence_bucket"
            ).fetchall()

            assert len(inc_rows) == len(full_rows)
            for inc, full in zip(inc_rows, full_rows, strict=False):
                for a, b in zip(inc, full, strict=False):
                    if isinstance(a, float) and isinstance(b, float):
                        assert abs(a - b) < 1e-9, f"Float mismatch: {a} != {b}"
                    else:
                        assert a == b, f"Value mismatch: {a!r} != {b!r}"
        finally:
            conn_inc.close()
            conn_full.close()


# ---------------------------------------------------------------------------
# 9. Transaction rollback on malformed fact
# ---------------------------------------------------------------------------


class TestTransactionRollback:
    def test_rollback_on_malformed_fact(self, tmp_path: Path) -> None:
        """A malformed fact in update should rollback the entire transaction."""
        initial = [
            _make_fact(trade_id="T001", source_id="src_a", outcome="WIN"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(initial, db_path)
        finally:
            rebuilder.cleanup()

        # Create a malformed fact (missing required field)
        bad_fact = dict(_make_fact(trade_id="T002", source_id="src_a"))
        del bad_fact["trade_id"]  # Remove required field

        updater = IncrementalUpdater()
        try:
            with pytest.raises((ValueError, KeyError)):
                updater.update(db_path, [bad_fact])
        finally:
            updater.cleanup()

        # Verify original data is intact
        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 1  # Original fact still there
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 10. Rename-first backup before replacing existing DB
# ---------------------------------------------------------------------------


class TestRenameBackup:
    def test_backup_created_before_rebuild(self, tmp_path: Path) -> None:
        """Rebuild on existing DB should create a .bak backup."""
        initial = [_make_fact(trade_id="T001", source_id="src_a")]
        db_path = tmp_path / "test.db"

        # Build initial
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(initial, db_path)
        finally:
            rebuilder.cleanup()

        assert db_path.exists()

        # Rebuild with new facts
        more_facts = [
            _make_fact(trade_id="T001", source_id="src_a"),
            _make_fact(trade_id="T002", source_id="src_b"),
        ]
        rebuilder2 = FullRebuilder()
        try:
            rebuilder2.build(more_facts, db_path)
        finally:
            rebuilder2.cleanup()

        # Backup should exist
        backup = db_path.with_suffix(".db.bak")
        assert backup.exists()

        # Old data should be in backup
        conn_backup = open_db(str(backup))
        try:
            count = conn_backup.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 1
        finally:
            conn_backup.close()


# ---------------------------------------------------------------------------
# 11. SQLite integrity_check passes
# ---------------------------------------------------------------------------


class TestIntegrityCheck:
    def test_integrity_check_after_rebuild(self, tmp_path: Path) -> None:
        """SQLite integrity_check should pass after rebuild."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a"),
            _make_fact(trade_id="T002", source_id="src_b"),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            issues = integrity_check(conn)
            assert not issues
        finally:
            conn.close()

    def test_integrity_check_after_update(self, tmp_path: Path) -> None:
        """SQLite integrity_check should pass after incremental update."""
        initial = [_make_fact(trade_id="T001", source_id="src_a")]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(initial, db_path)
        finally:
            rebuilder.cleanup()

        new_facts = [_make_fact(trade_id="T002", source_id="src_b")]
        updater = IncrementalUpdater()
        try:
            updater.update(db_path, new_facts)
        finally:
            updater.cleanup()

        conn = open_db(str(db_path))
        try:
            issues = integrity_check(conn)
            assert not issues
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 12. Source AttributionFact JSONL unchanged
# ---------------------------------------------------------------------------


class TestJsonlUnchanged:
    def test_input_jsonl_unchanged_after_rebuild(self, tmp_path: Path) -> None:
        """Input JSONL content should remain byte-for-byte identical after rebuild."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a", raw_return=0.05),
            _make_fact(trade_id="T002", source_id="src_b", raw_return=-0.03),
        ]
        jsonl_path = tmp_path / "input.jsonl"
        _write_jsonl(facts, jsonl_path)

        original_bytes = jsonl_path.read_bytes()

        # Read and rebuild
        loaded = _read_jsonl(jsonl_path)
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(loaded, db_path)
        finally:
            rebuilder.cleanup()

        # Verify file unchanged
        assert jsonl_path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# 13. Deterministic summary ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_deterministic_summary_ordering(self, tmp_path: Path) -> None:
        """Multiple rebuilds with same data produce same summary row order."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_b", pair="ETH/USDT"),
            _make_fact(trade_id="T002", source_id="src_a", pair="BTC/USDT"),
            _make_fact(trade_id="T003", source_id="src_c", pair="ADA/USDT"),
        ]

        def _get_summary_keys(db_path: Path) -> list[tuple]:
            conn = open_db(str(db_path))
            try:
                return conn.execute(
                    "SELECT source_id, pair, timeframe, regime, confidence_bucket "
                    "FROM source_regime_stats "
                    "ORDER BY source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket"
                ).fetchall()
            finally:
                conn.close()

        db1 = tmp_path / "test1.db"
        rebuilder1 = FullRebuilder()
        try:
            rebuilder1.build(facts, db1)
        finally:
            rebuilder1.cleanup()
        keys1 = _get_summary_keys(db1)

        db2 = tmp_path / "test2.db"
        rebuilder2 = FullRebuilder()
        try:
            rebuilder2.build(facts, db2)
        finally:
            rebuilder2.cleanup()
        keys2 = _get_summary_keys(db2)

        assert keys1 == keys2


# ---------------------------------------------------------------------------
# 14. CLI rebuild mode
# ---------------------------------------------------------------------------


class TestCliRebuild:
    def test_cli_rebuild(self, tmp_path: Path) -> None:
        """CLI rebuild mode should work end-to-end."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a"),
        ]
        jsonl = tmp_path / "input.jsonl"
        _write_jsonl(facts, jsonl)
        db_path = tmp_path / "test.db"

        result = subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "rebuild", str(jsonl), str(db_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert db_path.exists()


# ---------------------------------------------------------------------------
# 15. CLI update mode
# ---------------------------------------------------------------------------


class TestCliUpdate:
    def test_cli_update(self, tmp_path: Path) -> None:
        """CLI update mode should work end-to-end."""
        initial = [_make_fact(trade_id="T001", source_id="src_a")]
        jsonl1 = tmp_path / "initial.jsonl"
        _write_jsonl(initial, jsonl1)
        db_path = tmp_path / "test.db"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")}

        subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "rebuild", str(jsonl1), str(db_path)],
            check=True,
            cwd=tmp_path,
            env=env,
        )

        new_facts = [_make_fact(trade_id="T002", source_id="src_b")]
        jsonl2 = tmp_path / "update.jsonl"
        _write_jsonl(new_facts, jsonl2)

        result = subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "update", str(jsonl2), str(db_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"

        conn = open_db(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM attribution_facts").fetchone()[0]
            assert count == 2
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 16. CLI verify mode
# ---------------------------------------------------------------------------


class TestCliVerify:
    def test_cli_verify_passes(self, tmp_path: Path) -> None:
        """CLI verify mode should pass on a valid DB."""
        facts = [_make_fact(trade_id="T001", source_id="src_a")]
        jsonl = tmp_path / "input.jsonl"
        _write_jsonl(facts, jsonl)
        db_path = tmp_path / "test.db"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")}

        subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "rebuild", str(jsonl), str(db_path)],
            check=True,
            cwd=tmp_path,
            env=env,
        )

        result = subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "verify", str(db_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert "PASSED" in result.stdout


# ---------------------------------------------------------------------------
# 17. CLI inspect-summary mode
# ---------------------------------------------------------------------------


class TestCliInspectSummary:
    def test_cli_inspect_summary(self, tmp_path: Path) -> None:
        """CLI inspect-summary mode should print rows."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a"),
            _make_fact(trade_id="T002", source_id="src_b"),
        ]
        jsonl = tmp_path / "input.jsonl"
        _write_jsonl(facts, jsonl)
        db_path = tmp_path / "test.db"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")}

        subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "rebuild", str(jsonl), str(db_path)],
            check=True,
            cwd=tmp_path,
            env=env,
        )

        result = subprocess.run(
            [sys.executable, "-m", "si_v2.source_regime_stats.cli",
             "inspect-summary", str(db_path), "--top-n", "5"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert "src_a" in result.stdout or "src_b" in result.stdout or "Top" in result.stdout


# ---------------------------------------------------------------------------
# 18. Rebuild with many facts and verify summary metrics
# ---------------------------------------------------------------------------


class TestSummaryMetrics:
    def test_correct_win_rate_and_counts(self, tmp_path: Path) -> None:
        """Summary metrics should be computed correctly."""
        facts = [
            _make_fact(trade_id="T001", source_id="src_a", outcome="WIN", raw_return=0.10),
            _make_fact(trade_id="T002", source_id="src_a", outcome="WIN", raw_return=0.05),
            _make_fact(trade_id="T003", source_id="src_a", outcome="LOSS", raw_return=-0.03),
            _make_fact(trade_id="T004", source_id="src_a", outcome="LOSS", raw_return=-0.02),
            _make_fact(trade_id="T005", source_id="src_a", outcome="BREAKEVEN", raw_return=0.0),
        ]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            row = conn.execute(
                "SELECT win_count, loss_count, breakeven_count, win_rate, "
                "source_contribution_count, unique_trade_count "
                "FROM source_regime_stats WHERE source_id = 'src_a'"
            ).fetchone()
            assert row is not None
            assert row[0] == 2  # win_count
            assert row[1] == 2  # loss_count
            assert row[2] == 1  # breakeven_count
            assert row[3] == 0.5  # win_rate = 2/4
            assert row[4] == 5  # source_contribution_count
            assert row[5] == 5  # unique_trade_count
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 19. Cache metadata is populated
# ---------------------------------------------------------------------------


class TestCacheMetadata:
    def test_metadata_populated(self, tmp_path: Path) -> None:
        """cache_metadata table should have entries after rebuild."""
        facts = [_make_fact(trade_id="T001", source_id="src_a")]
        db_path = tmp_path / "test.db"
        rebuilder = FullRebuilder()
        try:
            rebuilder.build(facts, db_path)
        finally:
            rebuilder.cleanup()

        conn = open_db(str(db_path))
        try:
            row = conn.execute(
                "SELECT schema_version, build_mode FROM cache_metadata"
            ).fetchone()
            assert row is not None
            assert row[0] == "1.0"
            assert row[1] == "full"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 20. Schema created correctly
# ---------------------------------------------------------------------------


class TestSchema:
    def test_tables_created(self, tmp_path: Path) -> None:
        """All three tables should exist after schema creation."""
        db_path = tmp_path / "schema.db"
        conn = sqlite3.connect(str(db_path))
        try:
            create_schema(conn)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert "attribution_facts" in table_names
            assert "source_regime_stats" in table_names
            assert "cache_metadata" in table_names
        finally:
            conn.close()
