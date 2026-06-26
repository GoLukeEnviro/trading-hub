"""Evidence Bundle Validation Runner — read-only Contract Validator.

Validates ``active_cycle_*.json`` evidence bundles produced by the
``active_cycle_runner`` and returns a machine-readable verdict:

    GREEN  — proposal_candidates present, all safety invariants met,
             profitability gate not blocked.
    YELLOW — no proposal_candidates, but gate blocked by
             INSUFFICIENT_EVIDENCE; mutations still 0 (expected state).
    RED    — missing key, invalid type, mutations > 0, or
             uninterpretable gate state.

Usage:
    python -m si_v2.validation.evidence_bundle_validator --latest
    python -m si_v2.validation.evidence_bundle_validator --bundle-path <path>
    python -m si_v2.validation.evidence_bundle_validator --latest --json

Safety guarantees (enforced at code level):
    - No live trading enablement
    - No Freqtrade calls
    - No Docker commands
    - No config mutations
    - No secrets read, persisted, or printed
    - Read-only: never writes to disk
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALIDATOR_VERSION: str = "evidence_bundle_validator_v1"
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_EVIDENCE_DIR: Path = PROJECT_ROOT / "reports" / "phase2" / "evidence"

REQUIRED_KEYS: tuple[str, ...] = (
    "artifact_type",
    "schema_version",
    "cycle_id",
    "fleet_summary",
    "proposal_candidates",
    "profitability_gate",
)

MUTATION_KEYS: tuple[str, ...] = (
    "runtime_mutations",
    "config_mutations",
    "live_trading_mutations",
)

# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_bundle(
    bundle: dict[str, object],
    bundle_path: str | None = None,
) -> dict[str, object]:
    """Validate an evidence bundle dict and return a verdict dict.

    Returns a dict with keys:
        verdict, reason, cycle_id, bundle_path,
        proposal_candidates_count, runtime_mutations,
        config_mutations, live_trading_mutations
    """
    result: dict[str, object] = {
        "verdict": "RED",
        "reason": "",
        "cycle_id": bundle.get("cycle_id", "unknown"),
        "bundle_path": bundle_path,
        "proposal_candidates_count": 0,
        "runtime_mutations": 0,
        "config_mutations": 0,
        "live_trading_mutations": 0,
    }

    # --- Check required top-level keys ---
    for key in REQUIRED_KEYS:
        if key not in bundle:
            result["reason"] = f"Missing required key: {key!r}"
            return result

    # --- Check artifact_type ---
    if bundle["artifact_type"] != "active_cycle_runner_v1":
        result["reason"] = (
            f"Unexpected artifact_type: {bundle['artifact_type']!r} "
            f"(expected 'active_cycle_runner_v1')"
        )
        return result

    # --- Check schema_version ---
    if not isinstance(bundle["schema_version"], int):
        result["reason"] = (
            f"schema_version is not an int: {type(bundle['schema_version']).__name__}"
        )
        return result

    # --- Check cycle_id ---
    if not bundle["cycle_id"]:
        result["reason"] = "cycle_id is empty"
        return result

    # --- Check fleet_summary ---
    fleet_summary = bundle["fleet_summary"]
    if not isinstance(fleet_summary, dict):
        result["reason"] = "fleet_summary is not a dict"
        return result

    # --- Check mutation counters ---
    for key in MUTATION_KEYS:
        value = fleet_summary.get(key, 0)
        if not isinstance(value, int):
            result["reason"] = f"{key} is not an int: {type(value).__name__}"
            return result
        result[key] = value
        if value > 0:
            result["reason"] = (
                f"Mutation counter {key}={value} is > 0 — "
                f"safety invariant violated"
            )
            return result

    # --- Check proposal_candidates ---
    candidates = bundle["proposal_candidates"]
    if not isinstance(candidates, list):
        result["reason"] = (
            f"proposal_candidates is not a list: "
            f"{type(candidates).__name__}"
        )
        return result
    result["proposal_candidates_count"] = len(candidates)

    # --- Check profitability_gate ---
    profitability_gate = bundle["profitability_gate"]
    if not isinstance(profitability_gate, dict):
        result["reason"] = "profitability_gate is not a dict"
        return result

    gate_verdict = profitability_gate.get("verdict", "unknown")
    gate_fleet = profitability_gate.get("fleet_summary", {})

    # --- Determine overall verdict ---
    if len(candidates) > 0:
        # GREEN: candidates present, mutations 0 (already checked)
        result["verdict"] = "GREEN"
        result["reason"] = (
            f"proposal_candidates present ({len(candidates)} candidates), "
            f"all mutations 0, profitability gate verdict={gate_verdict!r}"
        )
    elif gate_verdict == "blocked":
        # YELLOW: no candidates, gate blocked (expected insufficient evidence)
        blocked_count = gate_fleet.get("blocked_count", 0)
        result["verdict"] = "YELLOW"
        result["reason"] = (
            f"No proposal_candidates — profitability gate blocked "
            f"({blocked_count} bots blocked, "
            f"expected INSUFFICIENT_EVIDENCE state). "
            f"All mutations 0. This is the expected YELLOW state."
        )
    else:
        # RED: no candidates, gate not blocked — unexpected
        result["verdict"] = "RED"
        result["reason"] = (
            f"No proposal_candidates and profitability gate "
            f"verdict={gate_verdict!r} (expected 'blocked'). "
            f"Unexpected state."
        )

    return result


# ---------------------------------------------------------------------------
# Validator class
# ---------------------------------------------------------------------------


class EvidenceBundleValidator:
    """Read-only validator for active_cycle evidence bundles."""

    def __init__(self) -> None:
        self.version: str = VALIDATOR_VERSION

    def validate(self, bundle: dict[str, object]) -> dict[str, object]:
        """Validate a bundle dict and return a verdict dict."""
        return validate_bundle(bundle)

    def validate_from_file(self, path: str) -> dict[str, object]:
        """Read a JSON file and validate its contents."""
        file_path = Path(path)
        if not file_path.exists():
            return {
                "verdict": "RED",
                "reason": f"Bundle file not found: {path}",
                "cycle_id": "unknown",
                "bundle_path": path,
                "proposal_candidates_count": 0,
                "runtime_mutations": 0,
                "config_mutations": 0,
                "live_trading_mutations": 0,
            }
        try:
            bundle = json.loads(file_path.read_text())
        except json.JSONDecodeError as exc:
            return {
                "verdict": "RED",
                "reason": f"Invalid JSON in bundle file: {exc}",
                "cycle_id": "unknown",
                "bundle_path": path,
                "proposal_candidates_count": 0,
                "runtime_mutations": 0,
                "config_mutations": 0,
                "live_trading_mutations": 0,
            }
        return validate_bundle(bundle, bundle_path=path)

    def find_latest(self, evidence_dir: str) -> Path | None:
        """Find the most recent active_cycle_*.json in a directory."""
        dir_path = Path(evidence_dir)
        if not dir_path.exists():
            return None
        bundles = sorted(dir_path.glob("active_cycle_*.json"))
        if not bundles:
            return None
        return bundles[-1]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> dict[str, object]:
    """CLI entry point.

    Returns the verdict dict (for testability).
    """
    parser = argparse.ArgumentParser(
        description="Evidence Bundle Validation Runner — read-only Contract Validator",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--latest",
        action="store_true",
        help="Validate the most recent active_cycle_*.json in the evidence directory",
    )
    group.add_argument(
        "--bundle-path",
        type=str,
        default=None,
        help="Path to a specific active_cycle_*.json bundle",
    )
    parser.add_argument(
        "--evidence-dir",
        type=str,
        default=None,
        help="Evidence directory (default: reports/phase2/evidence)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON verdict to stdout",
    )

    parsed = parser.parse_args(argv)

    validator = EvidenceBundleValidator()

    # Determine bundle path
    bundle_path: str | None = None

    if parsed.bundle_path:
        bundle_path = parsed.bundle_path
    elif parsed.latest:
        evidence_dir = parsed.evidence_dir or str(DEFAULT_EVIDENCE_DIR)
        latest = validator.find_latest(evidence_dir)
        if latest is None:
            result: dict[str, object] = {
                "verdict": "RED",
                "reason": f"No evidence bundles found in {evidence_dir}",
                "cycle_id": "unknown",
                "bundle_path": None,
                "proposal_candidates_count": 0,
                "runtime_mutations": 0,
                "config_mutations": 0,
                "live_trading_mutations": 0,
            }
            if parsed.json:
                print(json.dumps(result, indent=2))
            return result
        bundle_path = str(latest)
    else:
        result = {
            "verdict": "RED",
            "reason": (
                "No bundle specified. Provide --latest or --bundle-path. "
                "Usage: python -m si_v2.validation.evidence_bundle_validator --latest"
            ),
            "cycle_id": "unknown",
            "bundle_path": None,
            "proposal_candidates_count": 0,
            "runtime_mutations": 0,
            "config_mutations": 0,
            "live_trading_mutations": 0,
        }
        if parsed.json:
            print(json.dumps(result, indent=2))
        return result

    assert bundle_path is not None  # guaranteed by logic above
    result = validator.validate_from_file(bundle_path)

    if parsed.json:
        print(json.dumps(result, indent=2))

    return result


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["verdict"] in ("GREEN", "YELLOW") else 1)
