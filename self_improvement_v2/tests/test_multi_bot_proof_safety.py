"""Tests for the multi-bot read/analyze/shadow-proposal proof script's
safety helpers.

These tests focus on the RiskGuard-style local check used inside the
proof script. They do NOT exercise the full proof (which would talk to
the live Freqtrade fleet); the full proof is exercised manually and
captured in
self_improvement_v2/reports/phase2/multi_bot_read_analyze_shadow_proposal.md.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ------------------------------------------------------------------
# Import the proof module by file path (it is not a package import).
# ------------------------------------------------------------------

_PROOF_PATH = (
    Path(__file__).resolve().parent
    / ".."
    / "src"
    / "si_v2"
    / "proofs"
    / "multi_bot_read_analyze_shadow_proposal.py"
)


def _load_proof():
    spec = importlib.util.spec_from_file_location(
        "si_v2.proofs.multi_bot_read_analyze_shadow_proposal",
        _PROOF_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def proof_mod() -> object:
    return _load_proof()


def _good_decision() -> dict:
    return {
        "decision_type": "SHADOW_PROPOSAL",
        "bot_id": "freqtrade-freqforge",
        "candidate_sha256": "deadbeefcafebabe",
        "base_mode": "proposal_only",
        "mutation_policy": "safe_parameter_overlay_only",
        "requires_human_approval": True,
        "hypothesis": "telemetry_reachability_baseline_established",
        "parameters": {},
        "metadata_only_candidates": {"ping_reachable": 1},
        "evidence_summary": {},
        "no_proposal_reason": None,
        "fetched_at_utc": "2026-01-01T00:00:00+00:00",
    }


def test_riskguard_passes_metadata_only_proposal(proof_mod: object) -> None:
    result = proof_mod._riskguard_check(_good_decision())
    assert "runtime_blocked" in "; ".join(result["details"])


def test_riskguard_blocks_non_proposal_mode(proof_mod: object) -> None:
    decision = _good_decision()
    decision["base_mode"] = "runtime_apply"
    result = proof_mod._riskguard_check(decision)
    assert result["result"] == "BLOCKED"


def test_riskguard_blocks_missing_human_approval(proof_mod: object) -> None:
    decision = _good_decision()
    decision["requires_human_approval"] = False
    result = proof_mod._riskguard_check(decision)
    assert result["result"] == "BLOCKED"


def test_riskguard_blocks_dry_run_false(proof_mod: object) -> None:
    decision = _good_decision()
    decision["parameters"] = {"dry_run": False}
    result = proof_mod._riskguard_check(decision)
    assert result["result"] == "BLOCKED"


def test_riskguard_blocks_executable_parameters(proof_mod: object) -> None:
    """The multi-bot read cycle must never propose executable config
    parameters; the riskguard must reject any decision that has them."""
    for forbidden in ("max_open_trades", "stake_amount", "stoploss", "minimal_roi"):
        decision = _good_decision()
        decision["parameters"] = {forbidden: 1}
        result = proof_mod._riskguard_check(decision)
        assert result["result"] == "BLOCKED", f"riskguard failed to block {forbidden}"


def test_riskguard_blocks_unsafe_mutation_policy(proof_mod: object) -> None:
    decision = _good_decision()
    decision["mutation_policy"] = "free_for_all"
    result = proof_mod._riskguard_check(decision)
    assert result["result"] == "BLOCKED"
