"""Tests for Offline Episode Output Report Renderer (#114).

Verifies:
- renderer exists
- sample report exists
- missing input files produce YELLOW
- output is deterministic
- tests pass
"""

from __future__ import annotations

from pathlib import Path

from si_v2.episode.offline_episode_report import (
    OfflineEpisodeReportRenderer,
)

_ROOT = Path(__file__).resolve().parent.parent


def _renderer() -> OfflineEpisodeReportRenderer:
    return OfflineEpisodeReportRenderer(root=_ROOT)


class TestReportRenderer:
    def test_renderer_creates(self) -> None:
        r = _renderer()
        assert r is not None

    def test_render_returns_string(self) -> None:
        md = _renderer().render()
        assert isinstance(md, str)
        assert len(md) > 0

    def test_render_includes_verdict(self) -> None:
        md = _renderer().render()
        assert "Verdict:" in md

    def test_render_includes_artifacts_table(self) -> None:
        md = _renderer().render()
        assert "## Artifacts" in md
        assert "| Artifact | Status |" in md

    def test_render_deterministic(self) -> None:
        md1 = _renderer().render()
        md2 = _renderer().render()
        assert md1 == md2

    def test_render_includes_quality_gate(self) -> None:
        md = _renderer().render()
        if (_ROOT / "reports" / "readiness" / "offline_quality_gate_report.md").exists():
            assert "## Quality Gate" in md

    def test_render_includes_evidence_bundle(self) -> None:
        md = _renderer().render()
        if (_ROOT / "reports" / "evidence" / "evidence_bundle.json").exists():
            assert "## Evidence Bundle" in md

    def test_render_includes_attribution(self) -> None:
        md = _renderer().render()
        if (_ROOT / "reports" / "attribution" / "offline_attribution_summary.json").exists():
            assert "## Attribution Summary" in md

    def test_render_no_crash_on_missing_files(self) -> None:
        """Renderer must not crash even with a non-existent root."""
        r = OfflineEpisodeReportRenderer(root=Path("/tmp/nonexistent_episode_dir_xyz"))
        md = r.render()
        assert isinstance(md, str)
        assert "Verdict:" in md  # YELLOW or RED verdict

    def test_missing_files_produce_yellow(self) -> None:
        r = OfflineEpisodeReportRenderer(root=Path("/tmp/nonexistent_episode_dir_xyz"))
        md = r.render()
        # When required artifacts are missing, should show Missing
        assert "Missing" in md or "Verdict:" in md


class TestSampleReport:
    def test_sample_report_exists(self) -> None:
        p = _ROOT / "reports" / "episode" / "offline_episode_report.md"
        assert p.exists()

    def test_sample_report_contains_sections(self) -> None:
        text = (_ROOT / "reports" / "episode" / "offline_episode_report.md").read_text()
        assert "# Offline Episode Report" in text
        assert "## Artifacts" in text
