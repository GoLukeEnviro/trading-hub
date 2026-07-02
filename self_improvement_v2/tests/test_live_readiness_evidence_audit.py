"""Tests for live_readiness_evidence_audit.py — B1.

All tests use tmp_path, fake repo structures, and fake artifact paths —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.readiness.live_readiness_evidence_audit import (
    run_live_readiness_evidence_audit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create rollout modules
    rollout_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "rollout"
    )
    rollout_dir.mkdir(parents=True)
    for mod in [
        "fleet_rollout_input_resolver.py",
        "fleet_rollout_ready_evidence_runner.py",
        "fleet_dry_run_runtime_executor.py",
        "fleet_post_fleet_measurement_watcher.py",
        "fleet_dry_run_rollback_executor.py",
        "next_iteration_selector.py",
    ]:
        (rollout_dir / mod).write_text("# module\n")

    # Create apply_actuator modules
    actuator_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "apply_actuator"
    )
    actuator_dir.mkdir(parents=True)
    (actuator_dir / "rollback_rehearsal.py").write_text("# module\n")
    (actuator_dir / "rollback_executor.py").write_text("# module\n")

    # Create measurement module
    measurement_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "measurement"
    )
    measurement_dir.mkdir(parents=True)
    (measurement_dir / "autonomous_measurement_watcher.py").write_text(
        "# module\n"
    )

    # Create dry-run artifact paths
    for rel_path in [
        "var/si_v2/fleet_rollout_chain/rollout_policy",
        "var/si_v2/fleet_rollout_plans",
        "var/si_v2/fleet_ceremony",
        "var/si_v2/fleet_dry_run_runtime_executor",
        "var/si_v2/post_fleet_measurement/decision_packs",
        "var/si_v2/fleet_dry_run_rollback_executor",
        "var/si_v2/next_iteration_selector",
    ]:
        p = repo / rel_path
        p.mkdir(parents=True)

    # Create JSON files inside those directories
    (repo / "var/si_v2/fleet_dry_run_runtime_executor/executor_audit.json").write_text("{}")
    (repo / "var/si_v2/fleet_dry_run_rollback_executor/rollback_executor_audit.json").write_text("{}")

    # Create a config with dry_run=true
    config_dir = repo / "freqtrade" / "user_data"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps({"dry_run": True, "max_open_trades": 3})
    )

    return repo


def _make_repo_with_live_config(tmp_path: Path) -> Path:
    """Create a repo with a live (dry_run disabled) config."""
    repo = _make_minimal_repo(tmp_path)
    config_path = repo / "freqtrade" / "user_data" / "config.json"
    config_path.write_text(
        json.dumps({"dry_run": False, "max_open_trades": 3})
    )
    return repo


def _make_repo_without_rollback(tmp_path: Path) -> Path:
    """Create a repo missing rollback modules."""
    repo = _make_minimal_repo(tmp_path)
    actuator_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "apply_actuator"
    )
    (actuator_dir / "rollback_rehearsal.py").unlink()
    return repo


def _make_repo_without_measurement(tmp_path: Path) -> Path:
    """Create a repo missing measurement modules."""
    repo = _make_minimal_repo(tmp_path)
    measurement_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "measurement"
    )
    (measurement_dir / "autonomous_measurement_watcher.py").unlink()
    return repo


def _make_repo_without_artifacts(tmp_path: Path) -> Path:
    """Create a repo missing dry-run artifacts."""
    repo = _make_minimal_repo(tmp_path)
    import shutil
    var_dir = repo / "var"
    if var_dir.exists():
        shutil.rmtree(str(var_dir))
    return repo


# ---------------------------------------------------------------------------
# Tests: All checks pass
# ---------------------------------------------------------------------------


def test_all_checks_pass(tmp_path: Path) -> None:
    """All readiness checks pass with a complete repo."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_PREP_READY"
    # Soft checks (alerting, risk limits) are informational and expected
    # to be missing at this stage — they don't block readiness
    assert len(result.checks) == 7
    # Hard checks should all pass
    hard_passed = all(
        c.passed for c in result.checks
        if c.check_name in (
            "track_a_modules_exist",
            "dry_run_artifacts_exist",
            "no_live_activation",
            "rollback_proof",
            "measurement_proof",
        )
    )
    assert hard_passed


# ---------------------------------------------------------------------------
# Tests: Track A check
# ---------------------------------------------------------------------------


def test_blocks_missing_track_a_module(tmp_path: Path) -> None:
    """Blocks when a Track A module is missing."""
    repo = _make_minimal_repo(tmp_path)
    rollout_dir = (
        repo / "self_improvement_v2" / "src" / "si_v2" / "rollout"
    )
    (rollout_dir / "next_iteration_selector.py").unlink()
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_BLOCKED"
    assert any("Missing modules" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Live activation check
# ---------------------------------------------------------------------------


def test_blocks_live_config(tmp_path: Path) -> None:
    """Blocks when a config has dry_run disabled."""
    repo = _make_repo_with_live_config(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_BLOCKED"
    assert any("dry_run" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Rollback proof check
# ---------------------------------------------------------------------------


def test_blocks_missing_rollback(tmp_path: Path) -> None:
    """Blocks when rollback modules are missing."""
    repo = _make_repo_without_rollback(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_BLOCKED"
    assert any("rollback" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Measurement proof check
# ---------------------------------------------------------------------------


def test_blocks_missing_measurement(tmp_path: Path) -> None:
    """Blocks when measurement modules are missing."""
    repo = _make_repo_without_measurement(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_BLOCKED"
    assert any("measurement" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Artifact check
# ---------------------------------------------------------------------------


def test_blocks_missing_artifacts(tmp_path: Path) -> None:
    """Blocks when dry-run artifacts are missing."""
    repo = _make_repo_without_artifacts(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.status == "LIVE_READINESS_BLOCKED"
    assert any("artifact" in r.lower() for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: Alerting check
# ---------------------------------------------------------------------------


def test_notes_missing_alerting(tmp_path: Path) -> None:
    """Notes missing alerting docs but does not block on them alone."""
    repo = _make_minimal_repo(tmp_path)
    # Remove any alerting docs
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    # Alerting is a soft check — it reports missing but doesn't block
    # if other checks pass
    alerting_check = [c for c in result.checks if "alerting" in c.check_name]
    assert len(alerting_check) == 1
    assert not alerting_check[0].passed


# ---------------------------------------------------------------------------
# Tests: Risk limit check
# ---------------------------------------------------------------------------


def test_notes_missing_risk_limits(tmp_path: Path) -> None:
    """Notes missing risk limit docs but does not block on them alone."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    risk_check = [c for c in result.checks if "risk_limit" in c.check_name]
    assert len(risk_check) == 1
    assert not risk_check[0].passed


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_audit_json(tmp_path: Path) -> None:
    """Audit writes a JSON artifact."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.audit_path
    audit_path = Path(result.audit_path)
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "live_readiness_evidence_audit"
    assert audit["runtime_mutation"] == "NONE"


def test_writes_report_md(tmp_path: Path) -> None:
    """Audit writes a human-readable markdown report."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert result.report_path
    report_path = Path(result.report_path)
    assert report_path.exists()
    report_text = report_path.read_text()
    assert "# Live Readiness Evidence Audit" in report_text
    assert result.status in report_text


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """LiveReadinessAuditResult must be JSON-serializable."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "live_readiness_evidence_audit"
    assert deserialized["status"] in (
        "LIVE_READINESS_PREP_READY",
        "LIVE_READINESS_BLOCKED",
    )


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    # LIVE_READINESS_PREP_READY is a valid audit status, not a live trading field
    assert "exchange" not in str(d.keys())


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """All artifacts must have runtime_mutation=NONE."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    audit = json.loads(Path(result.audit_path).read_text())
    assert audit["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Check count
# ---------------------------------------------------------------------------


def test_has_seven_checks(tmp_path: Path) -> None:
    """Audit runs exactly 7 checks."""
    repo = _make_minimal_repo(tmp_path)
    result = run_live_readiness_evidence_audit(
        repo_root=repo,
        audit_output_dir=tmp_path / "audit",
    )
    assert len(result.checks) == 7
