"""Tests for production_alerting_gate.py — B4.

All tests use tmp_path, fake repo structures, and fake artifact paths —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.readiness.production_alerting_gate import (
    run_production_alerting_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create alert config paths
    kill_switch_dir = repo / "freqtrade" / "shared"
    kill_switch_dir.mkdir(parents=True)
    (kill_switch_dir / "kill_switch.py").write_text("# kill switch\n")

    runbooks_dir = repo / "docs" / "runbooks"
    runbooks_dir.mkdir(parents=True)
    (runbooks_dir / "kill-switch.md").write_text("# kill switch runbook\n")
    (runbooks_dir / "riskguard-pair-universe.md").write_text(
        "# riskguard runbook\n"
    )

    specs_dir = repo / "docs" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "incident-response-runbooks.md").write_text(
        "# incident response\n"
    )
    (specs_dir / "production-risk-limits-spec.md").write_text(
        "# risk limits\n"
    )

    # Create delivery proof paths
    adapters_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "adapters"
    )
    adapters_dir.mkdir(parents=True)
    (adapters_dir / "telegram_adapter.py").write_text("# telegram adapter\n")

    tests_dir = repo / "self_improvement_v2" / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_telegram_adapter.py").write_text(
        "# telegram adapter test\n"
    )

    # Create drawdown alert paths
    refs_dir = repo / "docs" / "references"
    refs_dir.mkdir(parents=True)
    (refs_dir / "freqtrade-kill-switch-procedure.md").write_text(
        "# kill switch procedure\n"
    )

    # Create runtime failure alert paths
    cron_dir = repo / "orchestrator" / "cron"
    cron_dir.mkdir(parents=True)
    (cron_dir / ".gitkeep").write_text("")

    scripts_dir = repo / "orchestrator" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "si-v2-active-cycle-runner.sh").write_text(
        "#!/bin/bash\n"
    )

    return repo


def _make_repo_missing_telegram(tmp_path: Path) -> Path:
    """Create a repo missing Telegram adapter."""
    repo = _make_minimal_repo(tmp_path)
    adapter = (
        repo
        / "self_improvement_v2"
        / "src"
        / "si_v2"
        / "adapters"
        / "telegram_adapter.py"
    )
    adapter.unlink()
    return repo


def _make_repo_missing_kill_switch(tmp_path: Path) -> Path:
    """Create a repo missing kill switch module."""
    repo = _make_minimal_repo(tmp_path)
    ks = repo / "freqtrade" / "shared" / "kill_switch.py"
    ks.unlink()
    return repo


def _make_repo_missing_scheduler(tmp_path: Path) -> Path:
    """Create a repo missing scheduler scripts."""
    repo = _make_minimal_repo(tmp_path)
    runner = (
        repo / "orchestrator" / "scripts" / "si-v2-active-cycle-runner.sh"
    )
    runner.unlink()
    return repo


# ---------------------------------------------------------------------------
# Tests: All checks pass
# ---------------------------------------------------------------------------


def test_all_checks_pass(tmp_path: Path) -> None:
    """All alerting gate checks pass with a complete repo."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "PRODUCTION_ALERTING_READY"
    assert len(result.blocked_reasons) == 0
    assert len(result.checks) == 4


# ---------------------------------------------------------------------------
# Tests: Individual check failures
# ---------------------------------------------------------------------------


def test_blocks_missing_telegram(tmp_path: Path) -> None:
    """Blocks when Telegram adapter is missing."""
    repo = _make_repo_missing_telegram(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "PRODUCTION_ALERTING_BLOCKED"
    assert any("telegram_adapter_module" in r for r in result.blocked_reasons)


def test_blocks_missing_kill_switch(tmp_path: Path) -> None:
    """Blocks when kill switch module is missing."""
    repo = _make_repo_missing_kill_switch(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "PRODUCTION_ALERTING_BLOCKED"
    assert any("kill_switch_file" in r for r in result.blocked_reasons)


def test_blocks_missing_scheduler(tmp_path: Path) -> None:
    """Blocks when scheduler scripts are missing."""
    repo = _make_repo_missing_scheduler(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.status == "PRODUCTION_ALERTING_BLOCKED"
    assert any("active_cycle_runner" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_gate_json(tmp_path: Path) -> None:
    """Gate writes a JSON artifact."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.gate_path
    gate_path = Path(result.gate_path)
    assert gate_path.exists()
    gate = json.loads(gate_path.read_text())
    assert gate["event"] == "production_alerting_gate_result"
    assert gate["runtime_mutation"] == "NONE"


def test_writes_report_md(tmp_path: Path) -> None:
    """Gate writes a human-readable markdown report."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert result.report_path
    report_path = Path(result.report_path)
    assert report_path.exists()
    report_text = report_path.read_text()
    assert "# Production Alerting Readiness Gate" in report_text
    assert result.status in report_text


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """ProductionAlertingGateResult must be JSON-serializable."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "production_alerting_gate_result"
    assert deserialized["status"] in (
        "PRODUCTION_ALERTING_READY",
        "PRODUCTION_ALERTING_BLOCKED",
    )


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
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
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    gate = json.loads(Path(result.gate_path).read_text())
    assert gate["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Check count
# ---------------------------------------------------------------------------


def test_has_four_checks(tmp_path: Path) -> None:
    """Gate runs exactly 4 checks."""
    repo = _make_minimal_repo(tmp_path)
    result = run_production_alerting_gate(
        repo_root=repo,
        gate_output_dir=tmp_path / "gate",
    )
    assert len(result.checks) == 4
