"""Tests for the offline attribution aggregator (#111).

Verifies:
- loads stats fixtures
- aggregates by source and regime
- outputs deterministic JSON and Markdown
- handles missing input as degraded
"""

from __future__ import annotations

from pathlib import Path

from si_v2.attribution.offline_aggregator import (
    OfflineAttributionAggregator,
)

_STATS_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "source-regime-stats"
)


def _aggregator() -> OfflineAttributionAggregator:
    return OfflineAttributionAggregator(stats_dir=_STATS_DIR)


class TestAggregator:
    def test_aggregator_creates(self) -> None:
        a = _aggregator()
        assert a is not None

    def test_aggregate_returns_summary(self) -> None:
        s = _aggregator().aggregate()
        assert s is not None
        assert s.status == "ok"

    def test_aggregate_loads_fixtures(self) -> None:
        s = _aggregator().aggregate()
        assert s.source_count == 2  # 2 fixtures

    def test_aggregate_has_samples(self) -> None:
        s = _aggregator().aggregate()
        assert s.total_samples > 0

    def test_aggregate_has_win_rate(self) -> None:
        s = _aggregator().aggregate()
        assert s.overall_win_rate > 0.0

    def test_rows_have_required_fields(self) -> None:
        s = _aggregator().aggregate()
        for r in s.rows:
            assert r.source_id
            assert r.regime_label
            assert r.sample_count > 0

    def test_missing_dir_returns_degraded(self) -> None:
        a = OfflineAttributionAggregator(
            stats_dir=Path("/tmp/nonexistent_stats")
        )
        s = a.aggregate()
        assert s.status == "degraded"
        assert len(s.errors) > 0

    def test_deterministic(self) -> None:
        s1 = _aggregator().aggregate()
        s2 = _aggregator().aggregate()
        assert s1.total_samples == s2.total_samples
        assert s1.overall_win_rate == s2.overall_win_rate
        assert s1.source_count == s2.source_count


class TestMarkdown:
    def test_markdown_generates(self) -> None:
        md = _aggregator().generate_markdown()
        assert "Offline Attribution Summary" in md
        assert "Overall Win Rate" in md

    def test_markdown_deterministic(self) -> None:
        md1 = _aggregator().generate_markdown()
        md2 = _aggregator().generate_markdown()
        assert md1 == md2


class TestDict:
    def test_to_dict_serializable(self) -> None:
        d = _aggregator().to_dict()
        import json
        json.dumps(d)
        assert d["status"] == "ok"
        assert d["source_count"] == 2
