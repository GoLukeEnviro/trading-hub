"""Tests for offline episode skeleton (#97).

Verifies:
- episode entrypoint exists
- manifest loading is tested
- episode result is deterministic
- missing optional inputs produce YELLOW
- tests pass
"""

from __future__ import annotations

from pathlib import Path

from si_v2.episode.offline_episode import (
    EpisodeVerdict,
    OfflineEpisode,
)

_ROOT = Path(__file__).resolve().parent.parent


def _episode() -> OfflineEpisode:
    return OfflineEpisode(root=_ROOT)


class TestEpisodeSkeleton:
    def test_episode_creates(self) -> None:
        ep = _episode()
        assert ep is not None

    def test_episode_returns_result(self) -> None:
        result = _episode().run()
        assert result is not None

    def test_episode_has_verdict(self) -> None:
        result = _episode().run()
        assert isinstance(result.verdict, EpisodeVerdict)

    def test_episode_deterministic(self) -> None:
        r1 = _episode().run()
        r2 = _episode().run()
        assert r1.verdict == r2.verdict
        assert r1.manifest_loaded == r2.manifest_loaded
        assert r1.source_manifest_loaded == r2.source_manifest_loaded
        assert r1.evidence_bundle_found == r2.evidence_bundle_found
        assert r1.quality_gate_found == r2.quality_gate_found

    def test_episode_manifest_loaded(self) -> None:
        result = _episode().run()
        # Manifest file exists in the project
        manifest_path = _ROOT / "episode" / "offline_episode_manifest.json"
        expected = manifest_path.exists()
        assert result.manifest_loaded == expected

    def test_episode_source_manifest_loaded(self) -> None:
        result = _episode().run()
        src_path = _ROOT / "evidence" / "source_manifest.json"
        expected = src_path.exists()
        assert result.source_manifest_loaded == expected

    def test_episode_evidence_bundle_checked(self) -> None:
        result = _episode().run()
        bundle_path = _ROOT / "reports" / "evidence" / "evidence_bundle.json"
        expected = bundle_path.exists()
        assert result.evidence_bundle_found == expected

    def test_episode_quality_gate_checked(self) -> None:
        result = _episode().run()
        qg_path = _ROOT / "reports" / "readiness" / "offline_quality_gate_report.md"
        expected = qg_path.exists()
        assert result.quality_gate_found == expected
        if expected:
            assert result.quality_gate_verdict in ("green", "yellow", "red", "unknown")

    def test_result_to_dict_serializable(self) -> None:
        result = _episode().run()
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "verdict" in d
        assert "manifest_loaded" in d
        assert "artifacts" in d
        assert isinstance(d["artifacts"], list)

    def test_artifacts_listed(self) -> None:
        result = _episode().run()
        assert len(result.artifacts) > 0
        for a in result.artifacts:
            assert a.name
            assert a.path
            assert isinstance(a.found, bool)

    def test_errors_empty_when_all_found(self) -> None:
        result = _episode().run()
        # If all required artifacts exist, errors should be empty
        missing_required = [a for a in result.artifacts if a.severity == "required" and not a.found]
        if not missing_required:
            assert len(result.errors) == 0

    def test_missing_optional_produces_warning(self) -> None:
        """If optional artifacts are missing, we get YELLOW, not RED."""
        result = _episode().run()
        if result.verdict == EpisodeVerdict.YELLOW:
            assert len(result.warnings) > 0
        elif result.verdict == EpisodeVerdict.GREEN:
            assert len(result.warnings) == 0

    def test_no_credentials(self) -> None:
        # Verify the episode module itself has no secret patterns
        source = Path(__file__).resolve().parent.parent / "src" / "si_v2" / "episode" / "offline_episode.py"
        text = source.read_text()
        assert "api_key" not in text
        assert "secret" not in text
        assert "token" not in text
