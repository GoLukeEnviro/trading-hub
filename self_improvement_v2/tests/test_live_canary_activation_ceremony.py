"""Tests for live_canary_activation_ceremony.py — C3.

All tests use tmp_path, fake repo structures, and fake artifacts —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import pytest

from si_v2.live.live_canary_activation_ceremony import (
    LIVE_CANARY_CEREMONY_BLOCKED,
    LIVE_CANARY_CEREMONY_READY,
    CeremonyCheckResult,
    LiveCanaryActivationCeremonyResult,
    SnapshotArtifact,
    run_live_canary_activation_ceremony,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_c3_approval_doc(
    repo_root: Path,
    *,
    marker: str = "APPROVED_EXECUTE_LIVE_CANARY",
    extra_content: str = "",
) -> Path:
    """Write a synthetic C3 approval marker document."""
    doc_dir = repo_root / "docs" / "decisions"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "APPROVED_EXECUTE_LIVE_CANARY.md"

    lines = [
        "# Live Canary Execution Approval",
        "",
        f"**Marker:** `{marker}`",
        "**Date:** 2026-07-02",
        "**Author:** Luke (GoLukeEnviro)",
        "",
        "---",
        "",
        "I approve the controlled live canary activation ceremony for",
        "freqtrade-freqforge-canary per C2 config plan.",
        "",
    ]
    if extra_content:
        lines.append(extra_content)

    doc_path.write_text("\n".join(lines) + "\n")
    return doc_path


def _make_c2_plan_ready(repo_root: Path) -> None:
    """Write a synthetic C2 config plan JSON with READY status."""
    plan_dir = repo_root / "var" / "si_v2" / "live_canary_config_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "live_canary_config_plan.json"
    plan_data = {
        "event": "live_canary_config_plan_result",
        "status": "LIVE_CANARY_CONFIG_PLAN_READY",
        "canary_target": "freqtrade-freqforge-canary",
        "checks": [],
        "blocked_reasons": [],
        "planned_config_deltas": {},
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    plan_file.write_text(json.dumps(plan_data, indent=2))


def _make_c1_gate_ready(repo_root: Path) -> None:
    """Write a synthetic C1 gate output with READY status."""
    gate_dir = repo_root / "var" / "si_v2" / "live_canary_approval_gate"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_file = gate_dir / "live_canary_approval_gate.json"
    gate_data = {
        "event": "live_canary_approval_gate_result",
        "status": "LIVE_CANARY_APPROVAL_READY",
        "checks": [],
        "blocked_reasons": [],
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    gate_file.write_text(json.dumps(gate_data, indent=2))


def _make_b2_doc(repo_root: Path) -> None:
    """Create a synthetic B2 risk limits document."""
    doc = repo_root / "docs" / "specs" / "production-risk-limits-spec.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Production Risk Limits Spec\n\nMax capital: 500 USDT\n")


def _make_b4_doc(repo_root: Path) -> None:
    """Create a synthetic B4 alerting gate document."""
    doc = repo_root / "docs" / "reports" / "production-alerting-readiness-gate.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Production Alerting Readiness Gate\n\nStatus: READY\n")


def _make_kill_switch_normal(repo_root: Path) -> None:
    """Create a synthetic kill switch file with NORMAL mode."""
    ks_dir = repo_root / "freqtrade" / "shared"
    ks_dir.mkdir(parents=True, exist_ok=True)
    ks_file = ks_dir / "kill_switch.py"
    ks_file.write_text(
        '# Kill switch for trading operations\n'
        'MODE = "NORMAL"\n'
    )


def _make_kill_switch_halt(repo_root: Path) -> None:
    """Create a synthetic kill switch file with HALT_NEW mode."""
    ks_dir = repo_root / "freqtrade" / "shared"
    ks_dir.mkdir(parents=True, exist_ok=True)
    ks_file = ks_dir / "kill_switch.py"
    ks_file.write_text(
        '# Kill switch for trading operations\n'
        'MODE = "HALT_NEW"\n'
    )


def _make_canary_config(repo_root: Path) -> None:
    """Create a synthetic canary config directory with dry-run config."""
    config_dir = repo_root / "freqforge-canary" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config_canary_dryrun.json"
    config_data = {
        "max_open_trades": 3,
        "stake_currency": "USDT",
        "stake_amount": 25.0,
        "dry_run": True,
        "dry_run_wallet": 500,
        "exchange": {
            "name": "bitget",
            "pair_whitelist": [
                "BTC/USDT:USDT",
                "ETH/USDT:USDT",
            ],
        },
        "bot_name": "freqforge_canary_v1",
        "db_url": (
            "sqlite:////freqtrade/user_data/"
            "tradesv3.freqforge_canary.dryrun.sqlite"
        ),
    }
    config_file.write_text(json.dumps(config_data, indent=2))


def _setup_full_ready_repo(repo_root: Path) -> None:
    """Set up a repo structure where all checks pass."""
    _make_c3_approval_doc(repo_root)
    _make_c2_plan_ready(repo_root)
    _make_c1_gate_ready(repo_root)
    _make_b2_doc(repo_root)
    _make_b4_doc(repo_root)
    _make_kill_switch_normal(repo_root)
    _make_canary_config(repo_root)


# ---------------------------------------------------------------------------
# Tests: result types
# ---------------------------------------------------------------------------


class TestDataModels:
    """Test that result data models work correctly."""

    def test_ceremony_check_result_defaults(self) -> None:
        check = CeremonyCheckResult(
            check_name="test_check",
            passed=True,
            detail="All good",
        )
        assert check.check_name == "test_check"
        assert check.passed is True
        assert check.detail == "All good"

    def test_ceremony_check_result_to_dict(self) -> None:
        check = CeremonyCheckResult(
            check_name="test_check",
            passed=True,
            detail="All good",
        )
        d = check.to_dict()
        assert d["check_name"] == "test_check"
        assert d["passed"] is True
        assert d["detail"] == "All good"

    def test_snapshot_artifact_defaults(self) -> None:
        snap = SnapshotArtifact(
            name="test_snap",
            path="/tmp/test.txt",
            content_preview="hello",
        )
        assert snap.name == "test_snap"
        assert snap.path == "/tmp/test.txt"
        assert snap.content_preview == "hello"

    def test_snapshot_artifact_to_dict(self) -> None:
        snap = SnapshotArtifact(
            name="test_snap",
            path="/tmp/test.txt",
            content_preview="hello",
        )
        d = snap.to_dict()
        assert d["name"] == "test_snap"
        assert d["path"] == "/tmp/test.txt"

    def test_ceremony_result_blocked(self) -> None:
        result = LiveCanaryActivationCeremonyResult(
            status=LIVE_CANARY_CEREMONY_BLOCKED,
            checks=(),
            blocked_reasons=("No approval marker",),
            snapshots=(),
            ceremony_path="/dev/null",
            report_path="/dev/null",
            next_step="Review blocked reasons",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert result.runtime_mutation == "NONE"

    def test_ceremony_result_ready(self) -> None:
        result = LiveCanaryActivationCeremonyResult(
            status=LIVE_CANARY_CEREMONY_READY,
            checks=(),
            blocked_reasons=(),
            snapshots=(),
            ceremony_path="/dev/null",
            report_path="/dev/null",
            next_step="Proceed to execution",
        )
        assert result.status == LIVE_CANARY_CEREMONY_READY
        assert result.runtime_mutation == "NONE"

    def test_ceremony_result_to_dict(self) -> None:
        c = CeremonyCheckResult(check_name="c1", passed=True, detail="ok")
        s = SnapshotArtifact(
            name="snap1", path="/p.txt", content_preview="preview"
        )
        result = LiveCanaryActivationCeremonyResult(
            status=LIVE_CANARY_CEREMONY_READY,
            checks=(c,),
            blocked_reasons=(),
            snapshots=(s,),
            ceremony_path="/c.json",
            report_path="/r.md",
            next_step="go",
        )
        d = result.to_dict()
        assert d["status"] == LIVE_CANARY_CEREMONY_READY
        assert d["runtime_mutation"] == "NONE"
        assert len(d["checks"]) == 1
        assert len(d["snapshots"]) == 1


# ---------------------------------------------------------------------------
# Tests: ceremony — full happy path
# ---------------------------------------------------------------------------


class TestCeremonyHappyPath:
    """Test the ceremony with all preconditions met."""

    def test_all_checks_pass(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_READY
        assert len(result.blocked_reasons) == 0
        assert len(result.snapshots) == 3  # config + ks + approval

    def test_ceremony_writes_json(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        out = tmp_path / "ceremony_out"
        _ = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        ceremony_file = out / "live_canary_activation_ceremony.json"
        assert ceremony_file.exists()
        data = json.loads(ceremony_file.read_text())
        assert data["status"] == LIVE_CANARY_CEREMONY_READY
        assert data["runtime_mutation"] == "NONE"
        assert data["canary_target"] == "freqtrade-freqforge-canary"

    def test_ceremony_writes_report(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        out = tmp_path / "ceremony_out"
        _ = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        report_file = out / "live_canary_activation_ceremony.md"
        assert report_file.exists()
        text = report_file.read_text()
        assert LIVE_CANARY_CEREMONY_READY in text
        assert "NONE" in text

    def test_execute_true_raises(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        with pytest.raises(RuntimeError) as exc_info:
            run_live_canary_activation_ceremony(
                repo_root=tmp_path,
                execute=True,
            )
        assert "FAIL_CLOSED" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests: ceremony — blocked states
# ---------------------------------------------------------------------------


class TestCeremonyBlocked:
    """Test the ceremony when preconditions are not met."""

    def test_blocked_missing_c3_marker(self, tmp_path: Path) -> None:
        # Set up everything except C3 marker.
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any(
            "approval" in r.lower() for r in result.blocked_reasons
        )
        assert len(result.snapshots) == 0

    def test_blocked_stale_c3_marker(self, tmp_path: Path) -> None:
        c3_doc = _make_c3_approval_doc(tmp_path)
        # Deterministically age the C3 marker to 2026-07-02 so it is 10 days
        # older than future_now, exceeding the 7-day expiry (wall-clock independent).
        _aged = datetime.datetime(2026, 7, 2, 12, 0, 0, tzinfo=datetime.UTC).timestamp()
        os.utime(c3_doc, (_aged, _aged))
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        # Set a stale "now" timestamp (10 days after marker creation).
        future_now = "2026-07-12T12:00:00+00:00"
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc=future_now,
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("expired" in r.lower() for r in result.blocked_reasons)
        assert len(result.snapshots) == 0

    def test_blocked_wrong_marker_value(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(
            tmp_path, marker="APPROVED_SOMETHING_ELSE"
        )
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED

    def test_blocked_missing_c2_plan(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("C2" in r for r in result.blocked_reasons)

    def test_blocked_c2_not_ready(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        # C2 plan with BLOCKED status.
        plan_dir = tmp_path / "var" / "si_v2" / "live_canary_config_plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / "live_canary_config_plan.json"
        plan_data = {
            "event": "live_canary_config_plan_result",
            "status": "LIVE_CANARY_CONFIG_PLAN_BLOCKED",
            "blocked_reasons": ["No C1 gate"],
        }
        plan_file.write_text(json.dumps(plan_data, indent=2))
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED

    def test_blocked_missing_c1_gate(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("C1" in r for r in result.blocked_reasons)

    def test_blocked_missing_b2_doc(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("B2" in r for r in result.blocked_reasons)

    def test_blocked_missing_b4_doc(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("B4" in r for r in result.blocked_reasons)

    def test_blocked_kill_switch_not_normal(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_halt(tmp_path)
        _make_canary_config(tmp_path)

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("kill" in r.lower() for r in result.blocked_reasons)

    def test_blocked_missing_canary_config(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)
        # No canary config created.

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED
        assert any("config" in r.lower() for r in result.blocked_reasons)

    def test_blocked_canary_dry_run_false(self, tmp_path: Path) -> None:
        _make_c3_approval_doc(tmp_path)
        _make_c2_plan_ready(tmp_path)
        _make_c1_gate_ready(tmp_path)
        _make_b2_doc(tmp_path)
        _make_b4_doc(tmp_path)
        _make_kill_switch_normal(tmp_path)

        # Create config with dry_run=False.
        config_dir = tmp_path / "freqforge-canary" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config_canary_dryrun.json"
        config_data = {
            "max_open_trades": 3,
            "dry_run": False,
            "exchange": {"name": "bitget"},
        }
        config_file.write_text(json.dumps(config_data, indent=2))

        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=tmp_path / "ceremony_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_BLOCKED


# ---------------------------------------------------------------------------
# Tests: ceremony — snapshot artifacts
# ---------------------------------------------------------------------------


class TestCeremonySnapshots:
    """Test that snapshot artifacts are created correctly."""

    def test_snapshot_config_content(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        out = tmp_path / "ceremony_out"
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        snap_names = [s.name for s in result.snapshots]
        assert "pre_activation_config_snapshot" in snap_names
        config_snap = out / "pre_activation_config_snapshot.json"
        assert config_snap.exists()
        data = json.loads(config_snap.read_text())
        assert data["dry_run"] is True
        assert data["bot_name"] == "freqforge_canary_v1"

    def test_snapshot_kill_switch(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        out = tmp_path / "ceremony_out"
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        snap_names = [s.name for s in result.snapshots]
        assert "pre_activation_kill_switch_snapshot" in snap_names
        ks_snap = out / "pre_activation_kill_switch_snapshot.txt"
        assert ks_snap.exists()
        text = ks_snap.read_text()
        assert "NORMAL" in text

    def test_snapshot_approval_marker(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        out = tmp_path / "ceremony_out"
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        snap_names = [s.name for s in result.snapshots]
        assert "c3_approval_marker_snapshot" in snap_names
        marker_snap = out / "c3_approval_marker_snapshot.md"
        assert marker_snap.exists()
        text = marker_snap.read_text()
        assert "APPROVED_EXECUTE_LIVE_CANARY" in text


# ---------------------------------------------------------------------------
# Tests: ceremony — output directory
# ---------------------------------------------------------------------------


class TestCeremonyOutput:
    """Test ceremony output paths and defaults."""

    def test_default_output_dir(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_READY

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        _setup_full_ready_repo(tmp_path)
        custom = tmp_path / "my_ceremony"
        result = run_live_canary_activation_ceremony(
            repo_root=tmp_path,
            ceremony_output_dir=custom,
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_CEREMONY_READY
        assert str(custom / "live_canary_activation_ceremony.json") in (
            result.ceremony_path
        )
