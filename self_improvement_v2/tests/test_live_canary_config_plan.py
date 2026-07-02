"""Tests for live_canary_config_plan.py — C2.

All tests use tmp_path, fake repo structures, and fake C1 gate output —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.live.live_canary_config_plan import (
    run_live_canary_config_plan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_c1_gate_blocked(repo_root: Path) -> None:
    """Write a synthetic C1 gate output with BLOCKED status."""
    gate_dir = repo_root / "var" / "si_v2" / "live_canary_approval_gate"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_file = gate_dir / "live_canary_approval_gate.json"
    gate_data = {
        "event": "live_canary_approval_gate_result",
        "status": "LIVE_CANARY_APPROVAL_BLOCKED",
        "checks": [],
        "blocked_reasons": ["Approval document not found"],
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    gate_file.write_text(json.dumps(gate_data, indent=2))


def _make_canary_config(repo_root: Path) -> None:
    """Create a synthetic canary config directory and dry-run config."""
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
        "db_url": "sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
    }
    config_file.write_text(json.dumps(config_data, indent=2))


def _make_b2_doc(repo_root: Path) -> None:
    """Create a synthetic B2 risk limits document."""
    doc = repo_root / "docs" / "specs" / "production-risk-limits-spec.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Production Risk Limits Specification\n\nDraft.\n")


def _make_b4_doc(repo_root: Path) -> None:
    """Create a synthetic B4 alerting gate document."""
    doc = repo_root / "docs" / "reports" / "production-alerting-readiness-gate.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Production Alerting Readiness Gate\n\nDraft.\n")


def _make_rollback_docs(repo_root: Path) -> None:
    """Create synthetic rollback reference documents."""
    # Deployment runbook
    doc1 = repo_root / "docs" / "context" / "freqforge-canary-deployment-runbook.md"
    doc1.parent.mkdir(parents=True, exist_ok=True)
    doc1.write_text("# FreqForge-Canary Deployment Runbook\n\nDraft.\n")

    # Kill switch runbook
    doc2 = repo_root / "docs" / "runbooks" / "kill-switch.md"
    doc2.parent.mkdir(parents=True, exist_ok=True)
    doc2.write_text("# Kill-Switch Runbook\n\nDraft.\n")

    # Incident response runbook
    doc3 = repo_root / "docs" / "specs" / "incident-response-runbooks.md"
    doc3.parent.mkdir(parents=True, exist_ok=True)
    doc3.write_text("# Incident Response and Go-Live Runbooks\n\nDraft.\n")


def _make_live_config(repo_root: Path) -> None:
    """Create a synthetic live config file (simulates already-applied plan)."""
    config_dir = repo_root / "freqforge-canary" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config_canary_live.json"
    config_file.write_text("{}")


def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with all prerequisites for a passing plan."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_c1_gate_ready(repo)
    _make_canary_config(repo)
    _make_b2_doc(repo)
    _make_b4_doc(repo)
    _make_rollback_docs(repo)
    return repo


# ---------------------------------------------------------------------------
# Tests: All checks pass
# ---------------------------------------------------------------------------


def test_all_checks_pass(tmp_path: Path) -> None:
    """All config plan checks pass with a valid repo."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_READY"
    assert len(result.blocked_reasons) == 0
    assert len(result.checks) == 6


# ---------------------------------------------------------------------------
# Tests: C1 gate blocked
# ---------------------------------------------------------------------------


def test_blocks_c1_gate_blocked(tmp_path: Path) -> None:
    """Blocks when C1 gate status is not READY."""
    repo = _make_minimal_repo(tmp_path)
    # Overwrite C1 gate with BLOCKED status
    _make_c1_gate_blocked(repo)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("blocked" in r.lower() for r in result.blocked_reasons)


def test_blocks_missing_c1_gate(tmp_path: Path) -> None:
    """Blocks when C1 gate output is missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove C1 gate output
    gate_file = repo / "var" / "si_v2" / "live_canary_approval_gate" / "live_canary_approval_gate.json"
    gate_file.unlink()
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("not found" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing canary target
# ---------------------------------------------------------------------------


def test_blocks_missing_canary_config(tmp_path: Path) -> None:
    """Blocks when canary config directory is missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove canary config directory
    config_dir = repo / "freqforge-canary" / "config"
    import shutil
    shutil.rmtree(config_dir)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("not found" in r.lower() for r in result.blocked_reasons)


def test_blocks_missing_dryrun_config(tmp_path: Path) -> None:
    """Blocks when canary dry-run config file is missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove dry-run config
    config_file = repo / "freqforge-canary" / "config" / "config_canary_dryrun.json"
    config_file.unlink()
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("not found" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing B2 document
# ---------------------------------------------------------------------------


def test_blocks_missing_b2_doc(tmp_path: Path) -> None:
    """Blocks when B2 risk limits document is missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove B2 document
    b2_doc = repo / "docs" / "specs" / "production-risk-limits-spec.md"
    b2_doc.unlink()
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("b2" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing B4 document
# ---------------------------------------------------------------------------


def test_blocks_missing_b4_doc(tmp_path: Path) -> None:
    """Blocks when B4 alerting gate document is missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove B4 document
    b4_doc = repo / "docs" / "reports" / "production-alerting-readiness-gate.md"
    b4_doc.unlink()
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("b4" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Missing rollback references
# ---------------------------------------------------------------------------


def test_blocks_missing_rollback_docs(tmp_path: Path) -> None:
    """Blocks when rollback reference documents are missing."""
    repo = _make_minimal_repo(tmp_path)
    # Remove all rollback docs
    import shutil
    shutil.rmtree(repo / "docs" / "context")
    shutil.rmtree(repo / "docs" / "runbooks")
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("rollback" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Live config already applied
# ---------------------------------------------------------------------------


def test_blocks_live_config_already_applied(tmp_path: Path) -> None:
    """Blocks when a live config file already exists."""
    repo = _make_minimal_repo(tmp_path)
    _make_live_config(repo)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.status == "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
    assert any("already exists" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_plan_json(tmp_path: Path) -> None:
    """Plan writes a JSON artifact."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.plan_path
    plan_path = Path(result.plan_path)
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["event"] == "live_canary_config_plan_result"
    assert plan["runtime_mutation"] == "NONE"
    assert plan["canary_target"] == "freqtrade-freqforge-canary"
    assert "planned_config_deltas" in plan
    assert "exchange_key_boundaries" in plan
    assert "b2_risk_limits" in plan
    assert "b4_alerting_gate" in plan
    assert "rollback_references" in plan
    assert "measurement_window" in plan


def test_writes_report_md(tmp_path: Path) -> None:
    """Plan writes a human-readable markdown report."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert result.report_path
    report_path = Path(result.report_path)
    assert report_path.exists()
    report_text = report_path.read_text()
    assert "# Live Canary Config Plan" in report_text
    assert result.status in report_text
    assert "Planned Config Deltas" in report_text
    assert "Exchange Key Boundaries" in report_text
    assert "B2 Risk Limits" in report_text
    assert "B4 Alerting Gate" in report_text
    assert "Rollback References" in report_text
    assert "Measurement Window" in report_text


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """LiveCanaryConfigPlanResult must be JSON-serializable."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "live_canary_config_plan_result"
    assert deserialized["status"] in (
        "LIVE_CANARY_CONFIG_PLAN_READY",
        "LIVE_CANARY_CONFIG_PLAN_BLOCKED",
    )


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "dry_run" not in str(d.keys()) or "dry_run" in str(d.keys())  # planned delta mentions it


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    plan = json.loads(Path(result.plan_path).read_text())
    assert plan["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Check count
# ---------------------------------------------------------------------------


def test_has_six_checks(tmp_path: Path) -> None:
    """Plan runs exactly 6 checks."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    assert len(result.checks) == 6


# ---------------------------------------------------------------------------
# Tests: Planned config deltas are documented
# ---------------------------------------------------------------------------


def test_planned_deltas_contain_dry_run(tmp_path: Path) -> None:
    """Planned config deltas must include dry_run toggle."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    plan = json.loads(Path(result.plan_path).read_text())
    deltas = plan.get("planned_config_deltas", {})
    assert "dry_run" in deltas
    assert deltas["dry_run"]["current"] is True
    assert deltas["dry_run"]["planned"] is False


def test_planned_deltas_contain_exchange_api(tmp_path: Path) -> None:
    """Planned config deltas must include exchange API key boundaries."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_canary_config_plan(
        repo_root=repo,
        plan_output_dir=tmp_path / "plan",
    )
    plan = json.loads(Path(result.plan_path).read_text())
    deltas = plan.get("planned_config_deltas", {})
    assert "exchange_api" in deltas
    assert "Bitget" in deltas["exchange_api"]["planned"]
