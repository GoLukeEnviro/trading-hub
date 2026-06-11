"""Tests for the Evidence Input Pipeline (Phase 2, issue #1).

Covers:
- Real SQLite fixture with known data → pipeline reads correctly
- Empty table → graceful handling with zero counts
- Missing/unreachable DB → graceful error
- Source filter works correctly
- Output is deterministic (same DB → same evidence)
- No mutation of the source DB
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from si_v2.evidence.input_pipeline import (
    AttributionCacheConnector,
    EvidencePipeline,
    PipelineConfig,
    PipelineEvidence,
    PipelineResult,
)

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Helpers: build a temporary source_regime_stats cache DB
# ---------------------------------------------------------------------------

STATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_regime_stats (
    source_id                TEXT NOT NULL,
    strategy_or_model_id     TEXT,
    pair                     TEXT NOT NULL,
    timeframe                TEXT NOT NULL,
    regime                   TEXT NOT NULL,
    confidence_bucket        TEXT NOT NULL,
    unique_trade_count       INTEGER NOT NULL DEFAULT 0,
    source_contribution_count INTEGER NOT NULL DEFAULT 0,
    win_count                INTEGER NOT NULL DEFAULT 0,
    loss_count               INTEGER NOT NULL DEFAULT 0,
    breakeven_count          INTEGER NOT NULL DEFAULT 0,
    win_rate                 REAL NOT NULL DEFAULT 0.0,
    average_raw_return       REAL NOT NULL DEFAULT 0.0,
    average_weighted_return  REAL NOT NULL DEFAULT 0.0,
    expectancy               REAL NOT NULL DEFAULT 0.0,
    cumulative_weighted_return REAL NOT NULL DEFAULT 0.0,
    drawdown_proxy           REAL NOT NULL DEFAULT 0.0,
    average_source_confidence REAL,
    average_regime_confidence  REAL,
    evidence_max_closed_at   TEXT,
    input_fingerprint        TEXT NOT NULL DEFAULT '',
    last_updated             TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket)
);
"""


def _create_stats_db(path: Path, rows: list[dict[str, object]]) -> None:
    """Create a source_regime_stats DB with the given rows."""
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(STATS_SCHEMA)
        for row in rows:
            conn.execute(
                """INSERT OR REPLACE INTO source_regime_stats
                   (source_id, strategy_or_model_id, pair, timeframe,
                    regime, confidence_bucket, unique_trade_count,
                    win_count, loss_count, breakeven_count, win_rate,
                    average_raw_return, average_weighted_return,
                    expectancy, cumulative_weighted_return,
                    drawdown_proxy, input_fingerprint, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("source_id", "src_a"),
                    row.get("strategy_or_model_id"),
                    row.get("pair", "BTC/USDT"),
                    row.get("timeframe", "1h"),
                    row.get("regime", "bullish"),
                    row.get("confidence_bucket", "75-100"),
                    row.get("unique_trade_count", 0),
                    row.get("win_count", 0),
                    row.get("loss_count", 0),
                    row.get("breakeven_count", 0),
                    row.get("win_rate", 0.0),
                    row.get("average_raw_return", 0.0),
                    row.get("average_weighted_return", 0.0),
                    row.get("expectancy", 0.0),
                    row.get("cumulative_weighted_return", 0.0),
                    row.get("drawdown_proxy", 0.0),
                    row.get("input_fingerprint", ""),
                    row.get("last_updated", ""),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _known_rows() -> list[dict[str, object]]:
    """Return deterministic rows for a known-good test fixture."""
    return [
        {
            "source_id": "ai-hedge-fund-crypto",
            "regime": "bullish",
            "unique_trade_count": 20,
            "win_count": 14,
            "loss_count": 5,
            "breakeven_count": 1,
            "win_rate": 70.0,
            "average_raw_return": 1.25,
            "average_weighted_return": 1.25,
            "cumulative_weighted_return": 25.0,
            "input_fingerprint": "fp_a",
            "last_updated": "2026-06-10T12:00:00+00:00",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "confidence_bucket": "75-100",
        },
        {
            "source_id": "ai-hedge-fund-crypto",
            "regime": "bearish",
            "unique_trade_count": 10,
            "win_count": 4,
            "loss_count": 6,
            "breakeven_count": 0,
            "win_rate": 40.0,
            "average_raw_return": -0.50,
            "average_weighted_return": -0.50,
            "cumulative_weighted_return": -5.0,
            "input_fingerprint": "fp_a",
            "last_updated": "2026-06-10T12:00:00+00:00",
            "pair": "ETH/USDT",
            "timeframe": "4h",
            "confidence_bucket": "50-75",
        },
        {
            "source_id": "freqforge",
            "regime": "bullish",
            "unique_trade_count": 15,
            "win_count": 12,
            "loss_count": 3,
            "breakeven_count": 0,
            "win_rate": 80.0,
            "average_raw_return": 2.00,
            "average_weighted_return": 2.00,
            "cumulative_weighted_return": 30.0,
            "input_fingerprint": "fp_b",
            "last_updated": "2026-06-10T13:00:00+00:00",
            "pair": "SOL/USDT",
            "timeframe": "1h",
            "confidence_bucket": "75-100",
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAttributionCacheConnector:
    """Tests for the lower-level AttributionCacheConnector."""

    def test_read_all_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        rows = _known_rows()
        _create_stats_db(db, rows)

        connector = AttributionCacheConnector(db)
        result = list(connector.read_rows())
        assert len(result) == 3

        # Verify all three rows are present
        sources = {r["source_id"] for r in result}
        assert sources == {"ai-hedge-fund-crypto", "freqforge"}

    def test_read_with_source_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        connector = AttributionCacheConnector(db)
        result = list(connector.read_rows(source_filter="ai-hedge-fund-crypto"))
        assert len(result) == 2
        assert all(r["source_id"] == "ai-hedge-fund-crypto" for r in result)

    def test_read_with_regime_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        connector = AttributionCacheConnector(db)
        result = list(connector.read_rows(regime_filter="bullish"))
        assert len(result) == 2
        assert all(r["regime"] == "bullish" for r in result)

    def test_read_with_both_filters(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        connector = AttributionCacheConnector(db)
        result = list(
            connector.read_rows(
                source_filter="ai-hedge-fund-crypto",
                regime_filter="bullish",
            )
        )
        assert len(result) == 1
        assert result[0]["source_id"] == "ai-hedge-fund-crypto"
        assert result[0]["regime"] == "bullish"

    def test_read_empty_table(self, tmp_path: Path) -> None:
        db = tmp_path / "empty.db"
        _create_stats_db(db, [])  # No rows

        connector = AttributionCacheConnector(db)
        result = list(connector.read_rows())
        assert result == []

    def test_read_non_existent_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        # File does NOT exist

        connector = None
        try:
            connector = AttributionCacheConnector(db)
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass

        assert connector is None


class TestEvidencePipeline:
    """Tests for the EvidencePipeline orchestrator."""

    def test_pipeline_reads_known_data(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert isinstance(result, PipelineResult)
        assert result.errors == []
        assert result.total_sources == 2
        assert len(result.evidence_bundles) == 3

        # Check individual evidence items by source
        crypto_bullish = [
            e for e in result.evidence_bundles
            if e.source == "ai-hedge-fund-crypto" and e.regime == "bullish"
        ]
        assert len(crypto_bullish) == 1
        cb = crypto_bullish[0]
        assert cb.total_trades == 20
        assert cb.winning_trades == 14
        assert cb.win_rate_pct == 70.0
        assert cb.total_profit_pct == 25.0
        assert cb.avg_profit_pct == 1.25

        crypto_bearish = [
            e for e in result.evidence_bundles
            if e.source == "ai-hedge-fund-crypto" and e.regime == "bearish"
        ]
        assert len(crypto_bearish) == 1
        cbe = crypto_bearish[0]
        assert cbe.total_trades == 10
        assert cbe.winning_trades == 4
        assert cbe.win_rate_pct == 40.0
        assert cbe.total_profit_pct == -5.0

        freqforge = [
            e for e in result.evidence_bundles
            if e.source == "freqforge"
        ]
        assert len(freqforge) == 1
        ff = freqforge[0]
        assert ff.total_trades == 15
        assert ff.winning_trades == 12
        assert ff.win_rate_pct == 80.0
        assert ff.total_profit_pct == 30.0

    def test_empty_table_returns_zero_counts(self, tmp_path: Path) -> None:
        db = tmp_path / "empty.db"
        _create_stats_db(db, [])  # No rows

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert isinstance(result, PipelineResult)
        assert result.errors == []
        assert result.total_sources == 0
        assert result.evidence_bundles == []

    def test_missing_db_returns_graceful_error(self, tmp_path: Path) -> None:
        db = tmp_path / "missing.db"
        # Do NOT create the file

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert isinstance(result, PipelineResult)
        assert len(result.errors) == 1
        assert "not found" in result.errors[0].lower()
        assert result.total_sources == 0
        assert result.evidence_bundles == []

    def test_unreachable_db_returns_graceful_error(self, tmp_path: Path) -> None:
        db = tmp_path / "unreachable.db"
        _create_stats_db(db, _known_rows())
        # Make the directory unreadable (if file itself, use a directory path instead)
        # Instead, create a path that is a directory (not a file)
        dir_path = tmp_path / "is_a_directory"
        dir_path.mkdir()

        config = PipelineConfig(db_path=dir_path)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert isinstance(result, PipelineResult)
        assert len(result.errors) >= 1
        assert result.total_sources == 0
        assert result.evidence_bundles == []

    def test_source_filter_works(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(db_path=db, source_filter="freqforge")
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert result.errors == []
        assert result.total_sources == 1
        assert len(result.evidence_bundles) == 1
        assert result.evidence_bundles[0].source == "freqforge"

    def test_regime_filter_works(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(db_path=db, regime_filter="bearish")
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert result.errors == []
        assert result.total_sources == 1
        assert len(result.evidence_bundles) == 1
        assert result.evidence_bundles[0].regime == "bearish"

    def test_combined_filters(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(
            db_path=db,
            source_filter="ai-hedge-fund-crypto",
            regime_filter="bullish",
        )
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        assert result.errors == []
        assert result.total_sources == 1
        assert len(result.evidence_bundles) == 1
        assert result.evidence_bundles[0].source == "ai-hedge-fund-crypto"
        assert result.evidence_bundles[0].regime == "bullish"

    def test_deterministic_output(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result1 = pipeline.run()
        result2 = pipeline.run()

        # Same DB + same config → same evidence bundles
        for e1, e2 in zip(
            result1.evidence_bundles,
            result2.evidence_bundles,
            strict=False,
        ):
            assert e1.source == e2.source
            assert e1.regime == e2.regime
            assert e1.total_trades == e2.total_trades
            assert e1.winning_trades == e2.winning_trades
            assert abs(e1.total_profit_pct - e2.total_profit_pct) < 1e-9
            assert abs(e1.win_rate_pct - e2.win_rate_pct) < 1e-9
            assert abs(e1.avg_profit_pct - e2.avg_profit_pct) < 1e-9

        assert result1.total_sources == result2.total_sources
        assert result1.errors == result2.errors

    def test_no_mutation_of_source_db(self, tmp_path: Path) -> None:
        """Verify the pipeline never modifies the cache database."""
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        # Snapshot the DB before running the pipeline
        conn_before = sqlite3.connect(str(db))
        before_checksum = conn_before.execute(
            "SELECT count(*), sum(unique_trade_count), sum(win_count) FROM source_regime_stats"
        ).fetchone()
        before_pages = conn_before.execute("PRAGMA page_count").fetchone()[0]
        conn_before.close()

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()
        assert result.errors == []

        # Snapshot after
        conn_after = sqlite3.connect(str(db))
        after_checksum = conn_after.execute(
            "SELECT count(*), sum(unique_trade_count), sum(win_count) FROM source_regime_stats"
        ).fetchone()
        after_pages = conn_after.execute("PRAGMA page_count").fetchone()[0]
        conn_after.close()

        assert before_checksum == after_checksum
        # Page count should not have changed (read-only mode)
        assert before_pages == after_pages

    def test_pipeline_config_property(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(
            db_path=db,
            source_filter="freqforge",
            regime_filter="bullish",
        )
        pipeline = EvidencePipeline(config)
        assert pipeline.config is config
        assert pipeline.config.source_filter == "freqforge"
        assert pipeline.config.regime_filter == "bullish"

    def test_collected_at_is_utc(self, tmp_path: Path) -> None:
        db = tmp_path / "stats.db"
        _create_stats_db(db, _known_rows())

        config = PipelineConfig(db_path=db)
        pipeline = EvidencePipeline(config)
        result = pipeline.run()

        for evidence in result.evidence_bundles:
            assert evidence.collected_at.tzinfo is not None
            assert evidence.collected_at.tzinfo.utcoffset(
                evidence.collected_at
            ) == timezone.utc.utcoffset(evidence.collected_at)
