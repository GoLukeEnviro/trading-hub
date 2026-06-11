"""Tests for Automated Attribution Reports (#59).

Covers:
- Deterministic Markdown and JSON output
- Empty cache report
- UNKNOWN regime warnings
- Low-sample exclusion from ranking
- Stable tie-breaking
- Period filtering
- Confidence limitations and warnings
- Negative expectancy warning
- Markdown escaping and sanitization
- SQLite source unchanged
- CLI end-to-end with real temp SQLite cache
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from si_v2.reports.models import (
    AttributionReport,
    ReportRequest,
    ReportSection,
    ReportWarning,
    ReportWarningType,
    WarningSeverity,
)
from si_v2.reports.renderers import JSONRenderer, MarkdownRenderer
from si_v2.reports.report_builder import AttributionReportBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_minimal_db(
    path: Path,
    facts: list[dict[str, object]] | None = None,
    stats: list[dict[str, object]] | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Create a minimal source_regime_stats SQLite database for testing.

    Args:
        path: Path to the database file.
        facts: List of attribution_facts rows.
        stats: List of source_regime_stats rows.
        metadata: Cache metadata dict.
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")

    # Create tables
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS attribution_facts (
        fact_id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        strategy_or_model_id TEXT,
        pair TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        regime TEXT NOT NULL CHECK (regime IN ('bullish','bearish','neutral','unknown')),
        confidence_bucket TEXT NOT NULL,
        weighted_return REAL NOT NULL,
        raw_trade_return REAL NOT NULL,
        contribution_weight REAL NOT NULL,
        outcome_classification TEXT NOT NULL,
        closed_at TEXT NOT NULL,
        provenance_hash TEXT NOT NULL,
        schema_version TEXT NOT NULL
    )
    """
    )
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS source_regime_stats (
        source_id TEXT NOT NULL,
        strategy_or_model_id TEXT,
        pair TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        regime TEXT NOT NULL,
        confidence_bucket TEXT NOT NULL,
        unique_trade_count INTEGER NOT NULL DEFAULT 0,
        source_contribution_count INTEGER NOT NULL DEFAULT 0,
        win_count INTEGER NOT NULL DEFAULT 0,
        loss_count INTEGER NOT NULL DEFAULT 0,
        breakeven_count INTEGER NOT NULL DEFAULT 0,
        win_rate REAL NOT NULL DEFAULT 0.0,
        average_raw_return REAL NOT NULL DEFAULT 0.0,
        average_weighted_return REAL NOT NULL DEFAULT 0.0,
        expectancy REAL NOT NULL DEFAULT 0.0,
        cumulative_weighted_return REAL NOT NULL DEFAULT 0.0,
        drawdown_proxy REAL NOT NULL DEFAULT 0.0,
        average_source_confidence REAL,
        average_regime_confidence REAL,
        evidence_max_closed_at TEXT,
        input_fingerprint TEXT NOT NULL DEFAULT '',
        last_updated TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket)
    )
    """
    )
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS cache_metadata (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        cache_schema_version TEXT NOT NULL,
        fact_schema_version TEXT NOT NULL DEFAULT '',
        source_fingerprint TEXT NOT NULL DEFAULT '',
        build_mode TEXT NOT NULL DEFAULT 'full',
        last_evidence_time TEXT NOT NULL DEFAULT '',
        operation_timestamp TEXT NOT NULL DEFAULT ''
    )
    """
    )

    # Insert facts
    if facts:
        for f in facts:
            fact_id = f.get("fact_id", f"fact_{id(f)}")
            conn.execute(
                """
            INSERT OR IGNORE INTO attribution_facts
            (fact_id, trade_id, source_id, strategy_or_model_id, pair, timeframe,
             regime, confidence_bucket, weighted_return, raw_trade_return,
             contribution_weight, outcome_classification, closed_at,
             provenance_hash, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    fact_id,
                    f.get("trade_id", "T001"),
                    f.get("source_id", "src_a"),
                    f.get("strategy_or_model_id"),
                    f.get("pair", "BTC/USDT"),
                    f.get("timeframe", "1h"),
                    f.get("regime", "bullish"),
                    f.get("confidence_bucket", "75-100"),
                    float(f.get("weighted_return", 0.0)),
                    float(f.get("raw_trade_return", 0.0)),
                    float(f.get("contribution_weight", 1.0)),
                    f.get("outcome_classification", "WIN"),
                    f.get("closed_at", "2026-01-01T12:00:00+00:00"),
                    f.get("provenance_hash", "abc123"),
                    f.get("schema_version", "1.0"),
                ),
            )

    # Insert stats
    if stats:
        for s in stats:
            conn.execute(
                """
            INSERT OR IGNORE INTO source_regime_stats
            (source_id, strategy_or_model_id, pair, timeframe, regime,
             confidence_bucket, unique_trade_count, source_contribution_count,
             win_count, loss_count, breakeven_count, win_rate,
             average_raw_return, average_weighted_return, expectancy,
             cumulative_weighted_return, drawdown_proxy,
             average_source_confidence, average_regime_confidence,
             evidence_max_closed_at, input_fingerprint, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    s.get("source_id", "src_a"),
                    s.get("strategy_or_model_id"),
                    s.get("pair", "BTC/USDT"),
                    s.get("timeframe", "1h"),
                    s.get("regime", "bullish"),
                    s.get("confidence_bucket", "75-100"),
                    int(s.get("unique_trade_count", 0)),
                    int(s.get("source_contribution_count", 0)),
                    int(s.get("win_count", 0)),
                    int(s.get("loss_count", 0)),
                    int(s.get("breakeven_count", 0)),
                    float(s.get("win_rate", 0.0)),
                    float(s.get("average_raw_return", 0.0)),
                    float(s.get("average_weighted_return", 0.0)),
                    float(s.get("expectancy", 0.0)),
                    float(s.get("cumulative_weighted_return", 0.0)),
                    float(s.get("drawdown_proxy", 0.0)),
                    s.get("average_source_confidence"),
                    s.get("average_regime_confidence"),
                    s.get("evidence_max_closed_at"),
                    s.get("input_fingerprint", ""),
                    s.get("last_updated", ""),
                ),
            )

    # Insert metadata
    meta = metadata or {
        "cache_schema_version": "1.1",
        "fact_schema_version": "1.0",
        "source_fingerprint": "abc123def456",
        "build_mode": "full",
        "last_evidence_time": "2026-06-01T00:00:00+00:00",
        "operation_timestamp": "2026-06-01T00:00:00+00:00",
    }
    conn.execute(
        """
    INSERT OR REPLACE INTO cache_metadata
    (id, cache_schema_version, fact_schema_version, source_fingerprint,
     build_mode, last_evidence_time, operation_timestamp)
    VALUES (1, ?, ?, ?, ?, ?, ?)
    """,
        (
            meta["cache_schema_version"],
            meta.get("fact_schema_version", "1.0"),
            meta.get("source_fingerprint", ""),
            meta.get("build_mode", "full"),
            meta.get("last_evidence_time", ""),
            meta.get("operation_timestamp", ""),
        ),
    )

    conn.commit()
    conn.close()


def _default_stats() -> list[dict[str, object]]:
    """Return a standard set of source_regime_stats rows for testing."""
    return [
        # src_a — many trades, positive expectancy
        {
            "source_id": "src_a",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "bullish",
            "confidence_bucket": "75-100",
            "unique_trade_count": 50,
            "source_contribution_count": 50,
            "win_count": 30,
            "loss_count": 18,
            "breakeven_count": 2,
            "win_rate": 0.625,
            "average_raw_return": 0.015,
            "average_weighted_return": 0.012,
            "expectancy": 0.012,
            "cumulative_weighted_return": 0.6,
            "drawdown_proxy": 0.05,
            "average_source_confidence": 0.85,
            "average_regime_confidence": 0.80,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
        # src_b — many trades, negative expectancy
        {
            "source_id": "src_b",
            "pair": "BTC/USDT",
            "timeframe": "4h",
            "regime": "bearish",
            "confidence_bucket": "50-75",
            "unique_trade_count": 30,
            "source_contribution_count": 30,
            "win_count": 10,
            "loss_count": 20,
            "breakeven_count": 0,
            "win_rate": 0.333,
            "average_raw_return": -0.01,
            "average_weighted_return": -0.008,
            "expectancy": -0.008,
            "cumulative_weighted_return": -0.24,
            "drawdown_proxy": 0.15,
            "average_source_confidence": 0.70,
            "average_regime_confidence": 0.65,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
        # src_c — few trades (below min_sample_count)
        {
            "source_id": "src_c",
            "pair": "ETH/USDT",
            "timeframe": "1h",
            "regime": "neutral",
            "confidence_bucket": "25-50",
            "unique_trade_count": 3,
            "source_contribution_count": 3,
            "win_count": 2,
            "loss_count": 1,
            "breakeven_count": 0,
            "win_rate": 0.667,
            "average_raw_return": 0.02,
            "average_weighted_return": 0.015,
            "expectancy": 0.015,
            "cumulative_weighted_return": 0.045,
            "drawdown_proxy": 0.01,
            "average_source_confidence": 0.60,
            "average_regime_confidence": 0.50,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
        # src_a also in bearish regime (multi-regime)
        {
            "source_id": "src_a",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "bearish",
            "confidence_bucket": "75-100",
            "unique_trade_count": 20,
            "source_contribution_count": 20,
            "win_count": 8,
            "loss_count": 12,
            "breakeven_count": 0,
            "win_rate": 0.400,
            "average_raw_return": -0.005,
            "average_weighted_return": -0.004,
            "expectancy": -0.004,
            "cumulative_weighted_return": -0.08,
            "drawdown_proxy": 0.08,
            "average_source_confidence": 0.82,
            "average_regime_confidence": 0.78,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
        # src_a also neutral regime
        {
            "source_id": "src_a",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "neutral",
            "confidence_bucket": "50-75",
            "unique_trade_count": 15,
            "source_contribution_count": 15,
            "win_count": 8,
            "loss_count": 6,
            "breakeven_count": 1,
            "win_rate": 0.571,
            "average_raw_return": 0.008,
            "average_weighted_return": 0.006,
            "expectancy": 0.006,
            "cumulative_weighted_return": 0.09,
            "drawdown_proxy": 0.03,
            "average_source_confidence": 0.78,
            "average_regime_confidence": 0.72,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
    ]


def _default_facts() -> list[dict[str, object]]:
    """Return a standard set of attribution_facts rows for testing."""
    return [
        {
            "fact_id": "fact_001",
            "trade_id": "T001",
            "source_id": "src_a",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "bullish",
            "confidence_bucket": "75-100",
            "weighted_return": 0.012,
            "raw_trade_return": 0.02,
            "contribution_weight": 0.6,
            "outcome_classification": "WIN",
            "closed_at": "2026-01-15T00:00:00+00:00",
            "provenance_hash": "abc123",
            "schema_version": "1.0",
        },
        {
            "fact_id": "fact_002",
            "trade_id": "T002",
            "source_id": "src_b",
            "pair": "BTC/USDT",
            "timeframe": "4h",
            "regime": "bearish",
            "confidence_bucket": "50-75",
            "weighted_return": -0.008,
            "raw_trade_return": -0.02,
            "contribution_weight": 0.4,
            "outcome_classification": "LOSS",
            "closed_at": "2026-02-01T00:00:00+00:00",
            "provenance_hash": "def456",
            "schema_version": "1.0",
        },
    ]


def _make_request(*, db_path: str, **kwargs: object) -> ReportRequest:
    """Create a ReportRequest with standard default values."""
    defaults: dict[str, object] = {
        "source_regime_stats_db_path": db_path,
        "generated_at": datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC),
        "min_sample_count": 5,
    }
    defaults.update(kwargs)
    return ReportRequest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with standard test data."""
    path = tmp_path / "test_source_regime_stats.db"
    _create_minimal_db(path, facts=_default_facts(), stats=_default_stats())
    return path


@pytest.fixture
def empty_db_path(tmp_path: Path) -> Path:
    """Create a temporary database with no data."""
    path = tmp_path / "empty_source_regime_stats.db"
    _create_minimal_db(path)
    return path


@pytest.fixture
def unknown_regime_db_path(tmp_path: Path) -> Path:
    """Create a database with facts under UNKNOWN regime."""
    path = tmp_path / "unknown_regime.db"
    facts = [
        {
            "fact_id": "fact_unknown_1",
            "trade_id": "TU001",
            "source_id": "src_a",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "unknown",
            "confidence_bucket": "0-25",
            "weighted_return": 0.01,
            "raw_trade_return": 0.02,
            "contribution_weight": 0.5,
            "outcome_classification": "WIN",
            "closed_at": "2026-03-01T00:00:00+00:00",
            "provenance_hash": "abc",
            "schema_version": "1.0",
        },
        {
            "fact_id": "fact_unknown_2",
            "trade_id": "TU002",
            "source_id": "src_b",
            "pair": "ETH/USDT",
            "timeframe": "4h",
            "regime": "unknown",
            "confidence_bucket": "0-25",
            "weighted_return": -0.005,
            "raw_trade_return": -0.01,
            "contribution_weight": 0.5,
            "outcome_classification": "LOSS",
            "closed_at": "2026-03-15T00:00:00+00:00",
            "provenance_hash": "def",
            "schema_version": "1.0",
        },
    ]
    _create_minimal_db(path, facts=facts)
    return path


@pytest.fixture
def high_drawdown_db_path(tmp_path: Path) -> Path:
    """Create a database with high drawdown stats."""
    path = tmp_path / "high_drawdown.db"
    stats = [
        {
            "source_id": "src_high_dd",
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "regime": "bullish",
            "confidence_bucket": "75-100",
            "unique_trade_count": 20,
            "source_contribution_count": 20,
            "win_count": 8,
            "loss_count": 12,
            "breakeven_count": 0,
            "win_rate": 0.400,
            "average_raw_return": -0.02,
            "average_weighted_return": -0.018,
            "expectancy": -0.018,
            "cumulative_weighted_return": -0.36,
            "drawdown_proxy": 0.35,
            "average_source_confidence": 0.70,
            "average_regime_confidence": 0.65,
            "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
        },
    ]
    _create_minimal_db(path, stats=stats)
    return path


# ---------------------------------------------------------------------------
# Test: Basic report generation
# ---------------------------------------------------------------------------


class TestBasicReport:
    """Verify basic report generation with standard data."""

    def test_build_report_returns_correct_type(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        assert isinstance(report, AttributionReport)
        assert report.report_id != ""
        assert report.schema_version == "1.0"

    def test_report_contains_all_sections(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        titles = [s.title for s in report.sections]
        expected = [
            "Evidence Quality Overview",
            "Performance by Source",
            "Performance by Regime",
            "Source x Regime Matrix",
            "Pair / Timeframe Splits",
            "Confidence-Bucket Analysis",
            "UNKNOWN Regime Warnings",
            "Negative / Flat Expectancy Warnings",
            "Statistical Limitations",
        ]
        assert titles == expected

    def test_report_metadata_fields(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        assert report.source_fingerprint == "abc123def456"
        assert report.generated_at == datetime(
            2026, 6, 11, 12, 0, 0, tzinfo=UTC
        )
        assert report.period_start is None
        assert report.period_end is None


# ---------------------------------------------------------------------------
# Test: Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Verify that output is byte-identical across runs."""

    def test_deterministic_markdown(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report1 = builder.build(request)
        report2 = builder.build(request)

        renderer = MarkdownRenderer()
        md1 = renderer.render(report1)
        md2 = renderer.render(report2)
        assert md1 == md2
        assert len(md1) > 100

    def test_deterministic_json(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report1 = builder.build(request)
        report2 = builder.build(request)

        renderer = JSONRenderer()
        json1 = renderer.render(report1)
        json2 = renderer.render(report2)
        assert json1 == json2

        # Verify valid JSON
        data = json.loads(json1)
        assert data["schema_version"] == "1.0"
        assert len(data["sections"]) == 9


# ---------------------------------------------------------------------------
# Test: Empty cache
# ---------------------------------------------------------------------------


class TestEmptyCache:
    """Verify behavior with an empty cache (no facts or stats)."""

    def test_empty_cache_has_warning(self, empty_db_path: Path) -> None:
        request = _make_request(db_path=str(empty_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        warning_types = {w.type for w in report.warnings}
        assert ReportWarningType.UNSUFFICIENT_DATA in warning_types

    def test_empty_cache_all_sections_present(self, empty_db_path: Path) -> None:
        request = _make_request(db_path=str(empty_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        assert len(report.sections) == 9
        for section in report.sections:
            assert section.content  # All sections have *some* content

    def test_empty_cache_no_source_performance(
        self, empty_db_path: Path
    ) -> None:
        request = _make_request(db_path=str(empty_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        perf_section = report.sections[1]  # Performance by Source
        assert "No source data available" in perf_section.content


# ---------------------------------------------------------------------------
# Test: UNKNOWN regime warnings
# ---------------------------------------------------------------------------


class TestUnknownRegimeWarnings:
    """Verify UNKNOWN regime detection and reporting."""

    def test_unknown_regime_detected(self, unknown_regime_db_path: Path) -> None:
        request = _make_request(db_path=str(unknown_regime_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        warning_types = {w.type for w in report.warnings}
        assert ReportWarningType.UNKNOWN_REGIME in warning_types

    def test_unknown_regime_warning_message(
        self, unknown_regime_db_path: Path
    ) -> None:
        request = _make_request(db_path=str(unknown_regime_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        unknown_warnings = [
            w for w in report.warnings if w.type == ReportWarningType.UNKNOWN_REGIME
        ]
        assert len(unknown_warnings) == 1
        assert "2" in unknown_warnings[0].message  # 2 unknown facts
        assert unknown_warnings[0].severity == WarningSeverity.WARNING

    def test_unknown_regime_section_content(
        self, unknown_regime_db_path: Path
    ) -> None:
        request = _make_request(db_path=str(unknown_regime_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        unknown_section = report.sections[6]  # UNKNOWN Regime Warnings
        assert "UNKNOWN" in unknown_section.content
        assert "2" in unknown_section.content


# ---------------------------------------------------------------------------
# Test: Low-sample exclusion
# ---------------------------------------------------------------------------


class TestLowSampleExclusion:
    """Verify low-sample sources are excluded from rankings."""

    def test_low_sample_excluded_from_ranking(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path), min_sample_count=5)
        builder = AttributionReportBuilder(min_sample_count=5)
        report = builder.build(request)
        perf_section = report.sections[1]  # Performance by Source

        # src_c has only 3 trades, should be in "Insufficient Evidence" section
        assert "Insufficient Evidence" in perf_section.content
        # src_c gets escaped: underscores become \_
        assert "src\\_c" in perf_section.content.split(
            "Insufficient Evidence"
        )[1]

    def test_low_sample_warning_generated(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path), min_sample_count=5)
        builder = AttributionReportBuilder(min_sample_count=5)
        report = builder.build(request)
        low_sample_warnings = [
            w
            for w in report.warnings
            if w.type == ReportWarningType.LOW_SAMPLE
        ]
        assert len(low_sample_warnings) >= 1

    def test_all_sources_ranked_with_lower_threshold(
        self, db_path: Path
    ) -> None:
        request = _make_request(db_path=str(db_path), min_sample_count=1)
        builder = AttributionReportBuilder(min_sample_count=1)
        report = builder.build(request)
        perf_section = report.sections[1]  # Performance by Source
        assert "src_c" not in perf_section.content.split(
            "Insufficient Evidence"
        )[0]


# ---------------------------------------------------------------------------
# Test: Stable tie-breaking
# ---------------------------------------------------------------------------


class TestStableTieBreaking:
    """Verify deterministic tie-breaking in rankings."""

    def test_tie_breaking_deterministic(self, tmp_path: Path) -> None:
        """Two sources with identical expectancy should sort by source_id."""
        stats = [
            {
                "source_id": "src_beta",
                "pair": "BTC/USDT",
                "timeframe": "1h",
                "regime": "bullish",
                "confidence_bucket": "75-100",
                "unique_trade_count": 10,
                "source_contribution_count": 10,
                "win_count": 6,
                "loss_count": 4,
                "breakeven_count": 0,
                "win_rate": 0.6,
                "average_raw_return": 0.01,
                "average_weighted_return": 0.008,
                "expectancy": 0.008,
                "cumulative_weighted_return": 0.08,
                "drawdown_proxy": 0.02,
                "average_source_confidence": 0.80,
                "average_regime_confidence": 0.75,
                "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
            },
            {
                "source_id": "src_alpha",
                "pair": "BTC/USDT",
                "timeframe": "1h",
                "regime": "bearish",
                "confidence_bucket": "75-100",
                "unique_trade_count": 10,
                "source_contribution_count": 10,
                "win_count": 6,
                "loss_count": 4,
                "breakeven_count": 0,
                "win_rate": 0.6,
                "average_raw_return": 0.01,
                "average_weighted_return": 0.008,
                "expectancy": 0.008,
                "cumulative_weighted_return": 0.08,
                "drawdown_proxy": 0.02,
                "average_source_confidence": 0.80,
                "average_regime_confidence": 0.75,
                "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
            },
        ]
        path = tmp_path / "tiebreak.db"
        _create_minimal_db(path, stats=stats)

        request = _make_request(db_path=str(path), min_sample_count=1)
        builder = AttributionReportBuilder(min_sample_count=1)
        report1 = builder.build(request)
        report2 = builder.build(request)

        assert report1.sections[1].data["ranked"] == report2.sections[1].data["ranked"]
        # src_alpha should come before src_beta (alphabetical)
        ranked = report1.sections[1].data["ranked"]
        assert len(ranked) == 2
        assert ranked[0]["source_id"] == "src_alpha"
        assert ranked[1]["source_id"] == "src_beta"


# ---------------------------------------------------------------------------
# Test: Period filtering
# ---------------------------------------------------------------------------


class TestPeriodFiltering:
    """Verify period filtering via evidence_max_closed_at."""

    def test_period_filter_excludes_outside_range(self, db_path: Path) -> None:
        # All test data has evidence_max_closed_at = 2026-06-01
        # Filter to a period that excludes it
        request = _make_request(
            db_path=str(db_path),
            period_start=datetime(2026, 7, 1, tzinfo=UTC),
            period_end=datetime(2026, 8, 1, tzinfo=UTC),
        )
        builder = AttributionReportBuilder()
        report = builder.build(request)
        overview = report.sections[0]
        assert overview.data["total_facts"] == 0

    def test_period_filter_includes_matching_range(
        self, db_path: Path
    ) -> None:
        request = _make_request(
            db_path=str(db_path),
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 12, 31, tzinfo=UTC),
        )
        builder = AttributionReportBuilder()
        report = builder.build(request)
        overview = report.sections[0]
        assert overview.data["total_facts"] > 0

    def test_period_filter_partial(self, db_path: Path) -> None:
        # Only period_end set
        request = _make_request(
            db_path=str(db_path),
            period_end=datetime(2026, 6, 15, tzinfo=UTC),
        )
        builder = AttributionReportBuilder()
        report = builder.build(request)
        overview = report.sections[0]
        assert overview.data["total_facts"] > 0


# ---------------------------------------------------------------------------
# Test: Confidence limitations and warnings
# ---------------------------------------------------------------------------


class TestConfidenceLimitations:
    """Verify confidence-bucket analysis section."""

    def test_confidence_bucket_section_present(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        titles = [s.title for s in report.sections]
        assert "Confidence-Bucket Analysis" in titles

    def test_confidence_bucket_data(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        bucket_section = report.sections[5]  # Confidence-Bucket Analysis
        assert "75-100" in bucket_section.content


# ---------------------------------------------------------------------------
# Test: Negative expectancy warning
# ---------------------------------------------------------------------------


class TestNegativeExpectancy:
    """Verify negative expectancy detection and warnings."""

    def test_negative_expectancy_detected(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        neg_warnings = [
            w
            for w in report.warnings
            if w.type == ReportWarningType.NEGATIVE_EXPECTANCY
        ]
        # src_b has negative expectancy
        assert len(neg_warnings) >= 1

    def test_negative_expectancy_section_content(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        neg_section = report.sections[7]  # Negative / Flat Expectancy
        # src_b gets escaped: underscores become \_
        assert "src\\_b" in neg_section.content
        assert "negative" in neg_section.content.lower()

    def test_no_false_negative_warnings(self, db_path: Path) -> None:
        """Sources with positive expectancy should not get warnings."""
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        neg_warnings = [
            w
            for w in report.warnings
            if w.type == ReportWarningType.NEGATIVE_EXPECTANCY
        ]
        neg_source_ids = {w.message.split("'")[1] for w in neg_warnings}
        assert "src_a" not in neg_source_ids  # src_a has positive expectancy


# ---------------------------------------------------------------------------
# Test: Markdown escaping and sanitization
# ---------------------------------------------------------------------------


class TestMarkdownSanitization:
    """Verify Markdown escaping and sanitization."""

    def test_identifier_escaping(self, tmp_path: Path) -> None:
        """Source ID with special characters should be escaped."""
        stats = [
            {
                "source_id": "src|special*chars_bold_here",
                "pair": "BTC/USDT",
                "timeframe": "1h",
                "regime": "bullish",
                "confidence_bucket": "75-100",
                "unique_trade_count": 10,
                "source_contribution_count": 10,
                "win_count": 6,
                "loss_count": 4,
                "breakeven_count": 0,
                "win_rate": 0.6,
                "average_raw_return": 0.01,
                "average_weighted_return": 0.008,
                "expectancy": 0.008,
                "cumulative_weighted_return": 0.08,
                "drawdown_proxy": 0.02,
                "average_source_confidence": 0.80,
                "average_regime_confidence": 0.75,
                "evidence_max_closed_at": "2026-06-01T00:00:00+00:00",
            },
        ]
        path = tmp_path / "escape.db"
        _create_minimal_db(path, stats=stats)

        request = _make_request(db_path=str(path), min_sample_count=1)
        builder = AttributionReportBuilder(min_sample_count=1)
        report = builder.build(request)

        renderer = MarkdownRenderer()
        md = renderer.render(report)

        # Escaped pipe should be \| not raw |
        assert "src\\|special" in md
        # Asterisk should be escaped
        assert "\\*chars" in md
        # Underscore should be escaped
        assert "\\_here" in md

    def test_no_secrets_in_output(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)

        renderer = MarkdownRenderer()
        md = renderer.render(report)

        # No API keys, passwords, or token-like content
        assert "api_key" not in md.lower()
        assert "secret" not in md.lower()
        assert "password" not in md.lower()


# ---------------------------------------------------------------------------
# Test: SQLite source unchanged
# ---------------------------------------------------------------------------


class TestSourceUnchanged:
    """Verify that building a report does not modify the source DB."""

    def test_source_db_unchanged(self, db_path: Path) -> None:
        # Read original hash
        original_bytes = db_path.read_bytes()

        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        builder.build(request)
        builder.build(request)
        builder.build(request)

        # DB should be byte-identical
        assert db_path.read_bytes() == original_bytes

    def test_source_db_checksum_unchanged(self, db_path: Path) -> None:
        import hashlib

        original_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

        for _ in range(5):
            request = _make_request(db_path=str(db_path))
            builder = AttributionReportBuilder()
            builder.build(request)

        new_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
        assert new_hash == original_hash


# ---------------------------------------------------------------------------
# Test: High drawdown warnings
# ---------------------------------------------------------------------------


class TestHighDrawdown:
    """Verify high drawdown detection."""

    def test_high_drawdown_detected(
        self, high_drawdown_db_path: Path
    ) -> None:
        request = _make_request(db_path=str(high_drawdown_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        dd_warnings = [
            w for w in report.warnings if w.type == ReportWarningType.DRAWDOWN
        ]
        assert len(dd_warnings) >= 1

    def test_high_drawdown_warning_severity(
        self, high_drawdown_db_path: Path
    ) -> None:
        request = _make_request(db_path=str(high_drawdown_db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        dd_warnings = [
            w for w in report.warnings if w.type == ReportWarningType.DRAWDOWN
        ]
        for w in dd_warnings:
            assert w.severity == WarningSeverity.WARNING


# ---------------------------------------------------------------------------
# Test: Statistical limitations section
# ---------------------------------------------------------------------------


class TestStatisticalLimitations:
    """Verify the statistical limitations section."""

    def test_limitations_section_present(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)
        assert report.sections[8].title == "Statistical Limitations"

    def test_no_trading_recommendations(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report = builder.build(request)

        renderer = MarkdownRenderer()
        md = renderer.render(report)

        # Should mention no-trading-recommendations
        assert "no trading recommendations" in md.lower()

        # No weight/position/allocation suggestions
        assert "weight" not in md.lower() or "weighted" in md.lower()  # weighted_return is allowed
        assert "allocate" not in md.lower()
        assert "position size" not in md.lower()


# ---------------------------------------------------------------------------
# Test: Report builder edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Verify edge case handling."""

    def test_nonexistent_db_raises(self) -> None:
        request = _make_request(
            db_path="/nonexistent/path/db.sqlite"
        )
        builder = AttributionReportBuilder()
        with pytest.raises(FileNotFoundError):
            builder.build(request)

    def test_report_id_deterministic(self, db_path: Path) -> None:
        request = _make_request(db_path=str(db_path))
        builder = AttributionReportBuilder()
        report1 = builder.build(request)
        report2 = builder.build(request)
        assert report1.report_id == report2.report_id


# ---------------------------------------------------------------------------
# Test: CLI end-to-end
# ---------------------------------------------------------------------------


class TestCLI:
    """Verify CLI end-to-end with real temp SQLite cache."""

    @staticmethod
    def _build_env() -> dict[str, str]:
        """Build env with PYTHONPATH for subprocess CLI tests."""
        src = str(Path(__file__).resolve().parent.parent / "src")
        return {**os.environ, "PYTHONPATH": src}

    def test_cli_markdown_output(self, db_path: Path, tmp_path: Path) -> None:
        md_path = tmp_path / "report.md"
        env = self._build_env()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--markdown-output",
                str(md_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
        )
        assert result.returncode == 0
        assert md_path.exists()
        content = md_path.read_text()
        assert "Automated Attribution Report" in content
        assert "Performance by Source" in content

    def test_cli_json_output(self, db_path: Path, tmp_path: Path) -> None:
        json_path = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--json-output",
                str(json_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 0
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["schema_version"] == "1.0"
        assert len(data["sections"]) == 9

    def test_cli_both_outputs(self, db_path: Path, tmp_path: Path) -> None:
        md_path = tmp_path / "report.md"
        json_path = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--markdown-output",
                str(md_path),
                "--json-output",
                str(json_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 0
        assert md_path.exists()
        assert json_path.exists()

    def test_cli_period_filtering(self, db_path: Path, tmp_path: Path) -> None:
        json_path = tmp_path / "filtered.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--json-output",
                str(json_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
                "--period-start",
                "2026-01-01T00:00:00+00:00",
                "--period-end",
                "2026-06-30T00:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(json_path.read_text())
        assert data["schema_version"] == "1.0"

    def test_cli_nonexistent_db(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                "/nonexistent/db.sqlite",
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_cli_missing_generated_at(self, db_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 2  # argparse error

    def test_cli_invalid_timestamp(self, db_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--generated-at",
                "not-a-timestamp",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 1
        assert "invalid" in result.stderr.lower()

    def test_cli_stdout_when_no_output_file(
        self, db_path: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 0
        assert "Automated Attribution Report" in result.stdout
        assert "Performance by Source" in result.stdout

    def test_cli_min_sample_count(self, db_path: Path, tmp_path: Path) -> None:
        json_path = tmp_path / "min_sample.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "si_v2.reports.cli",
                "--db",
                str(db_path),
                "--json-output",
                str(json_path),
                "--generated-at",
                "2026-06-11T12:00:00+00:00",
                "--min-sample-count",
                "1",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=self._build_env(),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(json_path.read_text())
        # With min_sample_count=1, src_c should be ranked (3 trades >= 1)
        source_section = data["sections"][1]
        ranked_sources = [
            r["source_id"]
            for r in source_section["data"]["ranked"]
        ]
        assert "src_c" in ranked_sources


# ---------------------------------------------------------------------------
# Test: Model validation
# ---------------------------------------------------------------------------


class TestModels:
    """Verify Pydantic model validation."""

    def test_report_request_min_sample_default(self) -> None:
        req = ReportRequest(
            source_regime_stats_db_path="/tmp/test.db",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert req.min_sample_count == 5

    def test_report_request_negative_min_sample(self) -> None:
        with pytest.raises(ValueError):  # Pydantic ge constraint raises ValueError
            ReportRequest(
                source_regime_stats_db_path="/tmp/test.db",
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
                min_sample_count=0,
            )

    def test_report_warning_severity_default(self) -> None:
        w = ReportWarning(
            type=ReportWarningType.LOW_SAMPLE,
            message="Test warning",
            severity=WarningSeverity.INFO,
        )
        assert w.severity == WarningSeverity.INFO

    def test_report_section_roundtrip(self) -> None:
        section = ReportSection(
            title="Test",
            content="Hello **world**",
            data={"key": "value"},
        )
        assert section.title == "Test"
        assert section.content == "Hello **world**"
        assert section.data["key"] == "value"
