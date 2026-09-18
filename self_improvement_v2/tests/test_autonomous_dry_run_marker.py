"""Tests for the owner-authorization marker of the Agent0 dry-run activation.

The marker is a governance artifact: it must name the authorization, the
author, the mode and the host scope, and it must be referenced by the
evaluator's fail-closed marker check. A missing or renamed marker file must
break these tests, so the marker cannot be silently dropped.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER_ID = "APPROVED_AUTONOMOUS_DRY_RUN_AGENT0"
MARKER_PATH = ROOT / "docs" / "decisions" / f"{MARKER_ID}.md"


def test_marker_file_exists() -> None:
    assert MARKER_PATH.is_file(), f"marker missing: {MARKER_PATH}"


def test_marker_contains_required_tokens() -> None:
    text = MARKER_PATH.read_text(encoding="utf-8")
    for token in (MARKER_ID, "Luke", "AUTONOMOUS_DRY_RUN"):
        assert token in text, f"marker missing token: {token}"


def test_marker_names_host_scope_and_mode() -> None:
    text = MARKER_PATH.read_text(encoding="utf-8")
    assert "Agent0" in text
    assert "dry-run" in text.lower()
    assert "no live trading" in text.lower()


def test_marker_references_operator_goal() -> None:
    text = MARKER_PATH.read_text(encoding="utf-8")
    assert "GOAL" in text
    assert "2026-09-18" in text


def test_marker_records_not_authorized_scope() -> None:
    text = MARKER_PATH.read_text(encoding="utf-8")
    assert "dry_run=false" in text
    assert "freqai-rebel" in text


def test_marker_checker_accepts_the_committed_marker() -> None:
    """The evaluator's own fail-closed check must accept this marker."""
    import sys

    src = ROOT / "self_improvement_v2" / "src"
    sys.path.insert(0, str(src))
    from si_v2.pipeline.apply_chain_evaluation import _check_marker

    ok, reason, sha = _check_marker(MARKER_PATH)
    assert ok, reason
    assert len(sha) == 64


def test_marker_has_no_secrets() -> None:
    text = MARKER_PATH.read_text(encoding="utf-8")
    for marker in ("gho_", "-----BEGIN", "api_key", "password"):
        assert marker not in text, f"suspicious token in marker: {marker}"
