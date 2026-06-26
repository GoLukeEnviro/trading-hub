"""Tests for the SI v2 post-cycle evidence validation hook.

These are pure unit tests — no network, no Freqtrade, no Docker.
They test the ``_run_post_cycle_validation`` function in isolation.

Coverage:
    - Sidecar written for valid bundle
    - Explicit bundle_path used (not --latest)
    - YELLOW does not crash cycle
    - RED stored in sidecar
    - Validator error captured as FAILED
    - Sidecar naming convention
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.loop.active_cycle_runner import _run_post_cycle_validation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_yellow_bundle() -> dict[str, object]:
    """Return a minimal YELLOW bundle (empty candidates, blocked gate)."""
    return {
        "artifact_type": "active_cycle_runner_v1",
        "schema_version": 1,
        "cycle_id": "20260626T120000Z",
        "fleet_summary": {
            "runtime_mutations": 0,
            "config_mutations": 0,
            "live_trading_mutations": 0,
        },
        "proposal_candidates": [],
        "profitability_gate": {
            "verdict": "blocked",
            "fleet_summary": {"blocked_count": 4},
        },
    }


def _make_red_bundle() -> dict[str, object]:
    """Return a minimal RED bundle (missing required key)."""
    return {
        "artifact_type": "active_cycle_runner_v1",
        "schema_version": 1,
        "cycle_id": "20260626T120000Z",
        # Missing fleet_summary → RED
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPostCycleValidation:
    """Verify the post-cycle validation hook (_run_post_cycle_validation)."""

    def test_hook_writes_sidecar_for_valid_bundle(self, tmp_path: Path) -> None:
        """Hook writes a validation sidecar for a valid bundle."""
        bundle = _make_yellow_bundle()
        bundle_path = tmp_path / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )

        assert result["status"] == "SUCCESS"
        assert result["verdict"] == "YELLOW"
        assert result["cycle_id"] == "20260626T120000Z"
        assert result["sidecar_path"] != ""
        sidecar = Path(result["sidecar_path"])
        assert sidecar.exists()
        sidecar_content = json.loads(sidecar.read_text())
        assert sidecar_content["verdict"] == "YELLOW"

    def test_hook_uses_explicit_bundle_path(self, tmp_path: Path) -> None:
        """Hook validates the explicit bundle_path, not --latest."""
        # Create two bundles — hook must validate the explicit one
        bundle_a = _make_yellow_bundle()
        bundle_a["cycle_id"] = "cycle_a"
        bundle_b = _make_yellow_bundle()
        bundle_b["cycle_id"] = "cycle_b"
        path_a = tmp_path / "active_cycle_cycle_a.json"
        path_b = tmp_path / "active_cycle_cycle_b.json"
        path_a.write_text(json.dumps(bundle_a))
        path_b.write_text(json.dumps(bundle_b))
        validation_dir = tmp_path / "validation"

        # Validate bundle_a explicitly
        result = _run_post_cycle_validation(
            bundle_path=path_a,
            validation_dir=validation_dir,
        )
        assert result["cycle_id"] == "cycle_a"
        sidecar = Path(result["sidecar_path"])
        sidecar_content = json.loads(sidecar.read_text())
        assert sidecar_content["cycle_id"] == "cycle_a"

    def test_yellow_does_not_crash_cycle(self, tmp_path: Path) -> None:
        """YELLOW verdict returns SUCCESS status (non-blocking)."""
        bundle = _make_yellow_bundle()
        bundle_path = tmp_path / "active_cycle_yellow.json"
        bundle_path.write_text(json.dumps(bundle))
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )
        # YELLOW must not be treated as failure
        assert result["status"] == "SUCCESS"
        assert result["verdict"] == "YELLOW"

    def test_red_is_stored_in_sidecar(self, tmp_path: Path) -> None:
        """RED verdict is stored in sidecar, does not crash cycle."""
        bundle = _make_red_bundle()
        bundle_path = tmp_path / "active_cycle_red.json"
        bundle_path.write_text(json.dumps(bundle))
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )
        # RED must not crash — status is WARNING, sidecar is written
        assert result["status"] == "WARNING"
        assert result["verdict"] == "RED"
        sidecar = Path(result["sidecar_path"])
        assert sidecar.exists()
        sidecar_content = json.loads(sidecar.read_text())
        assert sidecar_content["verdict"] == "RED"

    def test_validator_error_does_not_crash_cycle(self, tmp_path: Path) -> None:
        """Validator import/run error is captured as FAILED, does not crash."""
        # Non-existent bundle path
        bundle_path = tmp_path / "nonexistent.json"
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )
        assert result["status"] == "FAILED"
        assert "not found" in result["error"].lower()

    def test_sidecar_naming_convention(self, tmp_path: Path) -> None:
        """Sidecar file is named evidence_validation_<cycle_id>.json."""
        bundle = _make_yellow_bundle()
        bundle_path = tmp_path / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )
        sidecar_path = Path(result["sidecar_path"])
        assert sidecar_path.name == "evidence_validation_20260626T120000Z.json"
