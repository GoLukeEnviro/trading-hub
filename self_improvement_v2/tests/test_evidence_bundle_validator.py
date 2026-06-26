"""Tests for the Evidence Bundle Validation Runner.

These tests are pure unit tests — no network, no Freqtrade, no Docker.
They exercise the evidence bundle validator with synthetic JSON bundles
and assert correct GREEN/YELLOW/RED verdicts.

Coverage:
    - GREEN: candidates present, mutations 0, gate not blocked
    - YELLOW: no candidates, gate blocked by INSUFFICIENT_EVIDENCE, mutations 0
    - RED: missing proposal_candidates key
    - RED: proposal_candidates not a list
    - RED: mutations > 0
    - RED: empty evidence directory with --latest
    - CLI: --latest, --bundle-path, --json flags
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from si_v2.validation.evidence_bundle_validator import (
    VALIDATOR_VERSION,
    EvidenceBundleValidator,
    validate_bundle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_green_bundle() -> dict:
    """Return a minimal GREEN bundle with 2 proposal candidates."""
    return {
        "artifact_type": "active_cycle_runner_v1",
        "schema_version": 1,
        "cycle_id": "20260626T120000Z",
        "branch": "main",
        "commit_sha": "abc123",
        "generated_at_utc": "2026-06-26T12:00:00Z",
        "registry_path": "self_improvement_v2/state/bot_registry.json",
        "bots": [],
        "fleet_summary": {
            "total_bots": 4,
            "fleet_verdict": "GREEN",
            "fleet_verdict_reason": "all bots healthy",
            "ping_ok_count": 4,
            "ping_failed_count": 0,
            "shadow_proposal_count": 2,
            "no_proposal_count": 0,
            "runtime_mutations": 0,
            "config_mutations": 0,
            "live_trading_mutations": 0,
            "docker_mutations": 0,
            "strategy_mutations": 0,
            "status_authenticated_count": 4,
            "status_failed_count": 0,
            "status_yellow_missing_env_count": 0,
        },
        "proposal_candidates": [
            {
                "candidate_id": "candidate-001",
                "bot_id": "freqtrade-freqforge",
                "hypothesis": "telemetry_reachability_baseline_established",
                "parameters": {},
                "mutation_policy": "safe_parameter_overlay_only",
            },
            {
                "candidate_id": "candidate-002",
                "bot_id": "freqtrade-regime-hybrid",
                "hypothesis": "telemetry_reachability_baseline_established",
                "parameters": {},
                "mutation_policy": "safe_parameter_overlay_only",
            },
        ],
        "profitability_gate": {
            "verdict": "passed",
            "fleet_summary": {
                "blocked_count": 0,
                "candidate_count": 2,
                "bot_count": 4,
                "inconclusive_count": 0,
                "fleet_profit_factor": 1.5,
                "max_drawdown_pct": 0.05,
                "total_net_pnl": 100.0,
                "total_trades": 50,
            },
            "reasons": [],
        },
        "per_bot_decisions": [],
        "safety_results": [],
        "historical_trade_window": {},
        "telemetry_history": {},
    }


def _make_yellow_bundle() -> dict:
    """Return a minimal YELLOW bundle with empty proposal_candidates and blocked gate."""
    return {
        "artifact_type": "active_cycle_runner_v1",
        "schema_version": 1,
        "cycle_id": "20260626T120000Z",
        "branch": "main",
        "commit_sha": "abc123",
        "generated_at_utc": "2026-06-26T12:00:00Z",
        "registry_path": "self_improvement_v2/state/bot_registry.json",
        "bots": [],
        "fleet_summary": {
            "total_bots": 4,
            "fleet_verdict": "YELLOW",
            "fleet_verdict_reason": "all 4 bots reachable but JWT env vars not set",
            "ping_ok_count": 4,
            "ping_failed_count": 0,
            "shadow_proposal_count": 4,
            "no_proposal_count": 0,
            "runtime_mutations": 0,
            "config_mutations": 0,
            "live_trading_mutations": 0,
            "docker_mutations": 0,
            "strategy_mutations": 0,
            "status_authenticated_count": 0,
            "status_failed_count": 0,
            "status_yellow_missing_env_count": 4,
        },
        "proposal_candidates": [],
        "profitability_gate": {
            "verdict": "blocked",
            "fleet_summary": {
                "blocked_count": 4,
                "candidate_count": 0,
                "bot_count": 4,
                "inconclusive_count": 0,
                "fleet_profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "total_net_pnl": 0.0,
                "total_trades": 0,
            },
            "reasons": [
                "blocked_bots: freqtrade-freqforge, freqtrade-regime-hybrid, freqtrade-freqforge-canary, freqai-rebel"
            ],
        },
        "per_bot_decisions": [],
        "safety_results": [],
        "historical_trade_window": {},
        "telemetry_history": {},
    }


def _make_red_missing_candidates_bundle() -> dict:
    """Return a bundle missing the proposal_candidates key entirely."""
    d = _make_green_bundle()
    del d["proposal_candidates"]
    return d


def _make_red_candidates_not_list_bundle() -> dict:
    """Return a bundle where proposal_candidates is not a list."""
    d = _make_green_bundle()
    d["proposal_candidates"] = "not-a-list"
    return d


def _make_red_mutations_bundle() -> dict:
    """Return a bundle with runtime_mutations > 0."""
    d = _make_green_bundle()
    d["fleet_summary"]["runtime_mutations"] = 1
    return d


def _make_red_config_mutations_bundle() -> dict:
    """Return a bundle with config_mutations > 0."""
    d = _make_green_bundle()
    d["fleet_summary"]["config_mutations"] = 1
    return d


def _make_red_live_trading_mutations_bundle() -> dict:
    """Return a bundle with live_trading_mutations > 0."""
    d = _make_green_bundle()
    d["fleet_summary"]["live_trading_mutations"] = 1
    return d


# ---------------------------------------------------------------------------
# Tests: GREEN verdict
# ---------------------------------------------------------------------------


class TestGreenVerdict:
    """GREEN: Candidates present, all safety invariants met, gate not blocked."""

    def test_green_with_candidates(self):
        """Bundle with 2 candidates, mutations 0, gate passed → GREEN."""
        bundle = _make_green_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "GREEN"
        assert result["proposal_candidates_count"] == 2
        assert result["runtime_mutations"] == 0
        assert result["config_mutations"] == 0
        assert result["live_trading_mutations"] == 0

    def test_green_with_single_candidate(self):
        """Bundle with 1 candidate → GREEN."""
        bundle = _make_green_bundle()
        bundle["proposal_candidates"] = [bundle["proposal_candidates"][0]]
        bundle["profitability_gate"]["fleet_summary"]["candidate_count"] = 1
        result = validate_bundle(bundle)
        assert result["verdict"] == "GREEN"
        assert result["proposal_candidates_count"] == 1

    def test_green_cycle_id_preserved(self):
        """Cycle ID from bundle is preserved in output."""
        bundle = _make_green_bundle()
        result = validate_bundle(bundle)
        assert result["cycle_id"] == "20260626T120000Z"

    def test_green_bundle_path_in_output(self):
        """Bundle path is included in output when provided."""
        result = validate_bundle(_make_green_bundle(), bundle_path="/tmp/test.json")
        assert result["bundle_path"] == "/tmp/test.json"

    def test_green_bundle_path_none_when_omitted(self):
        """Bundle path is None when not provided."""
        result = validate_bundle(_make_green_bundle())
        assert result["bundle_path"] is None


# ---------------------------------------------------------------------------
# Tests: YELLOW verdict
# ---------------------------------------------------------------------------


class TestYellowVerdict:
    """YELLOW: No candidates, gate blocked by INSUFFICIENT_EVIDENCE, mutations 0."""

    def test_yellow_empty_candidates_blocked_gate(self):
        """Empty candidates + blocked gate + mutations 0 → YELLOW."""
        bundle = _make_yellow_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "YELLOW"
        assert result["proposal_candidates_count"] == 0
        assert result["runtime_mutations"] == 0
        assert result["config_mutations"] == 0
        assert result["live_trading_mutations"] == 0

    def test_yellow_reason_contains_insufficient_evidence(self):
        """YELLOW reason mentions insufficient evidence."""
        bundle = _make_yellow_bundle()
        result = validate_bundle(bundle)
        assert "INSUFFICIENT_EVIDENCE" in result["reason"] or "insufficient" in result["reason"].lower()

    def test_yellow_cycle_id_preserved(self):
        """Cycle ID from bundle is preserved in YELLOW output."""
        bundle = _make_yellow_bundle()
        result = validate_bundle(bundle)
        assert result["cycle_id"] == "20260626T120000Z"


# ---------------------------------------------------------------------------
# Tests: RED verdict
# ---------------------------------------------------------------------------


class TestRedVerdict:
    """RED: Missing key, invalid type, mutations > 0, or uninterpretable gate."""

    def test_red_missing_proposal_candidates_key(self):
        """Missing proposal_candidates key → RED."""
        bundle = _make_red_missing_candidates_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"
        assert "proposal_candidates" in result["reason"]

    def test_red_candidates_not_a_list(self):
        """proposal_candidates not a list → RED."""
        bundle = _make_red_candidates_not_list_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"
        assert "list" in result["reason"].lower()

    def test_red_runtime_mutations_positive(self):
        """runtime_mutations > 0 → RED."""
        bundle = _make_red_mutations_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"
        assert "runtime_mutations" in result["reason"]

    def test_red_config_mutations_positive(self):
        """config_mutations > 0 → RED."""
        bundle = _make_red_config_mutations_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"
        assert "config_mutations" in result["reason"]

    def test_red_live_trading_mutations_positive(self):
        """live_trading_mutations > 0 → RED."""
        bundle = _make_red_live_trading_mutations_bundle()
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"
        assert "live_trading_mutations" in result["reason"]

    def test_red_missing_fleet_summary(self):
        """Missing fleet_summary → RED."""
        bundle = _make_green_bundle()
        del bundle["fleet_summary"]
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"

    def test_red_missing_artifact_type(self):
        """Missing artifact_type → RED."""
        bundle = _make_green_bundle()
        del bundle["artifact_type"]
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"

    def test_red_wrong_artifact_type(self):
        """Wrong artifact_type → RED."""
        bundle = _make_green_bundle()
        bundle["artifact_type"] = "wrong_type"
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"

    def test_red_missing_schema_version(self):
        """Missing schema_version → RED."""
        bundle = _make_green_bundle()
        del bundle["schema_version"]
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"

    def test_red_missing_profitability_gate(self):
        """Missing profitability_gate → RED."""
        bundle = _make_green_bundle()
        del bundle["profitability_gate"]
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"

    def test_red_missing_cycle_id(self):
        """Missing cycle_id → RED."""
        bundle = _make_green_bundle()
        del bundle["cycle_id"]
        result = validate_bundle(bundle)
        assert result["verdict"] == "RED"


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------


class TestCli:
    """CLI interface: --latest, --bundle-path, --json."""

    def test_cli_with_bundle_path(self, tmp_path: Path):
        """--bundle-path reads a file and returns valid JSON output."""
        bundle = _make_green_bundle()
        bundle_path = tmp_path / "test_bundle.json"
        bundle_path.write_text(json.dumps(bundle))
        from si_v2.validation.evidence_bundle_validator import main

        result = main(["--bundle-path", str(bundle_path)])
        assert result["verdict"] == "GREEN"
        assert result["proposal_candidates_count"] == 2

    def test_cli_with_json_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """--json flag prints JSON to stdout."""
        bundle = _make_green_bundle()
        bundle_path = tmp_path / "test_bundle.json"
        bundle_path.write_text(json.dumps(bundle))
        from si_v2.validation.evidence_bundle_validator import main

        main(["--bundle-path", str(bundle_path), "--json"])
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["verdict"] == "GREEN"

    def test_cli_with_latest_no_evidence_dir(self, tmp_path: Path):
        """--latest with empty evidence directory → RED."""
        from si_v2.validation.evidence_bundle_validator import main

        result = main(["--latest", "--evidence-dir", str(tmp_path)])
        assert result["verdict"] == "RED"
        assert "No evidence bundles found" in result["reason"]

    def test_cli_with_latest_finds_bundle(self, tmp_path: Path):
        """--latest finds the most recent bundle in evidence dir."""
        bundle = _make_green_bundle()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        bundle_path = evidence_dir / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        from si_v2.validation.evidence_bundle_validator import main

        result = main(["--latest", "--evidence-dir", str(evidence_dir)])
        assert result["verdict"] == "GREEN"

    def test_cli_with_latest_default_dir(self, tmp_path: Path):
        """--latest with --evidence-dir finds the most recent bundle."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        bundle = _make_green_bundle()
        bundle_path = evidence_dir / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        from si_v2.validation.evidence_bundle_validator import main

        result = main(["--latest", "--evidence-dir", str(evidence_dir)])
        assert result["verdict"] == "GREEN"

    def test_cli_no_args_shows_help(self, capsys: pytest.CaptureFixture[str]):
        """No args prints usage and returns RED."""
        from si_v2.validation.evidence_bundle_validator import main

        result = main([])
        assert result["verdict"] == "RED"
        assert "usage" in result["reason"].lower() or "provide" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Tests: Validator class
# ---------------------------------------------------------------------------


class TestValidatorClass:
    """EvidenceBundleValidator class interface."""

    def test_validator_instantiation(self):
        """Validator can be instantiated."""
        v = EvidenceBundleValidator()
        assert v.version == VALIDATOR_VERSION

    def test_validator_validate_green(self):
        """Validator.validate returns GREEN for a valid bundle."""
        v = EvidenceBundleValidator()
        result = v.validate(_make_green_bundle())
        assert result["verdict"] == "GREEN"

    def test_validator_validate_yellow(self):
        """Validator.validate returns YELLOW for insufficient evidence."""
        v = EvidenceBundleValidator()
        result = v.validate(_make_yellow_bundle())
        assert result["verdict"] == "YELLOW"

    def test_validator_validate_red(self):
        """Validator.validate returns RED for missing key."""
        v = EvidenceBundleValidator()
        result = v.validate(_make_red_missing_candidates_bundle())
        assert result["verdict"] == "RED"

    def test_validator_validate_from_file(self, tmp_path: Path):
        """Validator.validate_from_file reads and validates a JSON file."""
        bundle = _make_green_bundle()
        bundle_path = tmp_path / "test_bundle.json"
        bundle_path.write_text(json.dumps(bundle))
        v = EvidenceBundleValidator()
        result = v.validate_from_file(str(bundle_path))
        assert result["verdict"] == "GREEN"

    def test_validator_validate_from_file_not_found(self):
        """Validator.validate_from_file returns RED for missing file."""
        v = EvidenceBundleValidator()
        result = v.validate_from_file("/tmp/nonexistent_bundle.json")
        assert result["verdict"] == "RED"
        assert "not found" in result["reason"].lower()

    def test_validator_validate_from_file_invalid_json(self, tmp_path: Path):
        """Validator.validate_from_file returns RED for invalid JSON."""
        bundle_path = tmp_path / "invalid.json"
        bundle_path.write_text("not json")
        v = EvidenceBundleValidator()
        result = v.validate_from_file(str(bundle_path))
        assert result["verdict"] == "RED"
        assert "JSON" in result["reason"]

    def test_validator_find_latest_empty_dir(self, tmp_path: Path):
        """Validator.find_latest returns None for empty directory."""
        v = EvidenceBundleValidator()
        result = v.find_latest(str(tmp_path))
        assert result is None

    def test_validator_find_latest_finds_file(self, tmp_path: Path):
        """Validator.find_latest finds the most recent bundle."""
        bundle = _make_green_bundle()
        bundle_path = tmp_path / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        v = EvidenceBundleValidator()
        result = v.find_latest(str(tmp_path))
        assert result is not None
        assert result.name == "active_cycle_20260626T120000Z.json"
