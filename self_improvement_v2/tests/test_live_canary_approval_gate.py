"""Tests for live_canary_approval_gate.py — C1.

All tests use tmp_path, fake repo structures, and fake approval documents —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from si_v2.live.live_canary_approval_gate import (
    run_live_canary_approval_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval_doc(
    repo_root: Path,
    *,
    marker: str = "APPROVED_LIVE_CANARY_TRANSITION",
    include_track_b: bool = True,
    extra_content: str = "",
) -> str:
    """Write a synthetic approval marker document."""
    doc_dir = repo_root / "docs" / "decisions"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "APPROVED_LIVE_CANARY_TRANSITION.md"

    lines = [
        "# Live Canary Transition Approval",
        "",
        f"**Marker:** `{marker}`",
        "**Date:** 2026-07-02",
        "**Author:** Luke (GoLukeEnviro)",
        "",
        "---",
        "",
        "## Approval",
        "",
        f"I hereby approve the transition to live canary mode: {marker}",
        "",
    ]

    if include_track_b:
        lines.extend([
            "## Track B Evidence",
            "",
            "The following Track B phases are complete:",
            "",
            "- B1 — Live Readiness Evidence Audit",
            "- B2 — Production Risk Limits Spec",
            "- B3 — Incident Response and Go-Live Runbooks",
            "- B4 — Production Alerting Readiness Gate",
            "",
        ])

    if extra_content:
        lines.append(extra_content)
        lines.append("")

    doc_path.write_text("\n".join(lines))
    return str(doc_path)


def _make_conflicting_approval(
    repo_root: Path,
    *,
    marker: str = "APPROVED_EXECUTE_LIVE_CANARY",
) -> None:
    """Write a conflicting approval marker document."""
    doc_dir = repo_root / "docs" / "decisions"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "APPROVED_EXECUTE_LIVE_CANARY.md"
    doc_path.write_text(
        f"# Execute Live Canary\n\n**Marker:** `{marker}`\n"
    )


def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with a valid approval document."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_approval_doc(repo)
    return repo


def _make_repo_without_approval(tmp_path: Path) -> Path:
    """Create a repo without an approval document."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _make_repo_with_stale_approval(tmp_path: Path) -> Path:
    """Create a repo with a stale approval document."""
    repo = tmp_path / "repo"
    repo.mkdir()
    doc_path = _make_approval_doc(repo)
    # Set the file's mtime to 8 days ago
    old_time = (datetime.now(UTC) - timedelta(days=8)).timestamp()
    os_import = __import__("os")
    os_import.utime(doc_path, (old_time, old_time))
    return repo


def _make_repo_with_wrong_marker(tmp_path: Path) -> Path:
    """Create a repo with a wrong approval marker."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_approval_doc(repo, marker="APPROVED_WRONG_MARKER")
    return repo


def _make_repo_without_track_b(tmp_path: Path) -> Path:
    """Create a repo with an approval doc missing Track B refs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_approval_doc(repo, include_track_b=False)
    return repo


def _make_repo_with_conflicting_approval(tmp_path: Path) -> Path:
    """Create a repo with a conflicting approval marker."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_approval_doc(repo)
    _make_conflicting_approval(repo)
    return repo


# ---------------------------------------------------------------------------
# Tests: All checks pass
# ---------------------------------------------------------------------------


def test_all_checks_pass(tmp_path: Path) -> None:
    """All approval gate checks pass with a valid repo."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_READY"
    assert len(result.blocked_reasons) == 0
    assert len(result.checks) == 5


# ---------------------------------------------------------------------------
# Tests: Missing approval document
# ---------------------------------------------------------------------------


def test_blocks_missing_approval(tmp_path: Path) -> None:
    """Blocks when approval document is missing."""
    repo = _make_repo_without_approval(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_BLOCKED"
    assert any("not found" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Wrong marker value
# ---------------------------------------------------------------------------


def test_blocks_wrong_marker(tmp_path: Path) -> None:
    """Blocks when approval marker value is wrong."""
    repo = _make_repo_with_wrong_marker(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_BLOCKED"
    assert any("not found" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Stale approval
# ---------------------------------------------------------------------------


def test_blocks_stale_approval(tmp_path: Path) -> None:
    """Blocks when approval is older than 7 days."""
    repo = _make_repo_with_stale_approval(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_BLOCKED"
    assert any("expired" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing Track B evidence
# ---------------------------------------------------------------------------


def test_blocks_missing_track_b(tmp_path: Path) -> None:
    """Blocks when Track B evidence references are missing."""
    repo = _make_repo_without_track_b(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_BLOCKED"
    assert any("track b" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Conflicting approval
# ---------------------------------------------------------------------------


def test_blocks_conflicting_approval(tmp_path: Path) -> None:
    """Blocks when a conflicting approval marker exists."""
    repo = _make_repo_with_conflicting_approval(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "LIVE_CANARY_APPROVAL_BLOCKED"
    assert any("conflicting" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_gate_json(tmp_path: Path) -> None:
    """Gate writes a JSON artifact."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.gate_path
    gate_path = Path(result.gate_path)
    assert gate_path.exists()
    gate = json.loads(gate_path.read_text())
    assert gate["event"] == "live_canary_approval_gate_result"
    assert gate["runtime_mutation"] == "NONE"


def test_writes_report_md(tmp_path: Path) -> None:
    """Gate writes a human-readable markdown report."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.report_path
    report_path = Path(result.report_path)
    assert report_path.exists()
    report_text = report_path.read_text()
    assert "# Live Canary Approval Gate" in report_text
    assert result.status in report_text


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """LiveCanaryApprovalGateResult must be JSON-serializable."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "live_canary_approval_gate_result"
    assert deserialized["status"] in (
        "LIVE_CANARY_APPROVAL_READY",
        "LIVE_CANARY_APPROVAL_BLOCKED",
    )


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "exchange" not in str(d.keys())


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    gate = json.loads(Path(result.gate_path).read_text())
    assert gate["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Check count
# ---------------------------------------------------------------------------


def test_has_five_checks(tmp_path: Path) -> None:
    """Gate runs exactly 5 checks."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_approval_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert len(result.checks) == 5
