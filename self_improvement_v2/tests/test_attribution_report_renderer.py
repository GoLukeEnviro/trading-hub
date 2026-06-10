"""Tests for Attribution Report Renderer (#116).

Verifies:
- renderer exists
- report output exists
- source/regime table is present
- missing-data cases are handled
- tests pass
"""

from __future__ import annotations

from pathlib import Path

from si_v2.attribution.attribution_report_renderer import (
    AttributionReportRenderer,
)

_ROOT = Path(__file__).resolve().parent.parent


def _renderer() -> AttributionReportRenderer:
    return AttributionReportRenderer(root=_ROOT)


class TestRenderer:
    def test_renderer_creates(self) -> None:
        r = _renderer()
        assert r is not None

    def test_render_returns_string(self) -> None:
        md = _renderer().render()
        assert isinstance(md, str)
        assert len(md) > 0

    def test_render_includes_title(self) -> None:
        md = _renderer().render()
        assert "# Attribution Report" in md

    def test_render_includes_status(self) -> None:
        md = _renderer().render()
        assert "**Status:**" in md

    def test_render_has_table(self) -> None:
        md = _renderer().render()
        assert "| Source | Regime |" in md

    def test_render_has_confidence_buckets(self) -> None:
        md = _renderer().render()
        assert "## Confidence Buckets" in md

    def test_render_deterministic(self) -> None:
        md1 = _renderer().render()
        md2 = _renderer().render()
        assert md1 == md2

    def test_missing_file_returns_degraded(self) -> None:
        r = AttributionReportRenderer(
            root=Path("/tmp/nonexistent_attr_dir_xyz")
        )
        md = r.render()
        assert "degraded" in md or "⚠️" in md

    def test_missing_file_does_not_crash(self) -> None:
        r = AttributionReportRenderer(
            root=Path("/tmp/nonexistent_attr_dir_xyz")
        )
        md = r.render()
        assert isinstance(md, str)
        assert len(md) > 0


class TestSampleReport:
    def test_sample_report_exists(self) -> None:
        p = _ROOT / "reports" / "attribution" / "attribution_report.md"
        assert p.exists()

    def test_sample_report_has_table(self) -> None:
        text = (
            _ROOT / "reports" / "attribution" / "attribution_report.md"
        ).read_text()
        assert "| Source | Regime |" in text
        assert "rainbow:ta" in text or "rainbow:llm" in text
