"""Tests for the SI v2 Approval-Gated Dry-Run Apply Path (#277).

Covers eligibility checks, safety gates, proposal validation, and
apply plan artifact creation for all four bots.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from si_v2.apply.dry_run_apply_path import (
    APPLY_STATUS_CREATED,
    _is_hard_block,
    _is_real_source,
    check_apply_eligibility,
    create_apply_plan,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

APPROVED_PROPOSAL: dict[str, object] = {
    "bot_id": "freqtrade-freqforge",
    "decision_type": "SHADOW_PROPOSAL",
    "approval_status": "APPROVED",
    "approval_eligible": True,
    "requires_human_approval": True,
    "base_mode": "proposal_only",
    "candidate_sha256": "abcd1234",
    "hypothesis": "reinforce_profitable_pair_cluster_v1",
    "no_proposal_reason": None,
    "dry_run": True,
    "parameters": {},
    "cycle_id": "20260622T050051Z",
    "promotion_block_reason_codes": [],
    "walk_forward_net_metrics": {
        "metrics_source": "walk_forward_net_metrics",
        "evaluation_status": "PASS_REVIEW",
        "total_net_pnl": 10.5,
        "profit_factor": 2.1,
        "total_trades": 15,
        "max_drawdown_pct": 5.0,
    },
}

NOT_APPROVED_PROPOSAL: dict[str, object] = {
    "bot_id": "freqtrade-regime-hybrid",
    "decision_type": "SHADOW_PROPOSAL",
    "approval_status": "PENDING_HUMAN",
    "approval_eligible": True,
    "requires_human_approval": True,
    "base_mode": "proposal_only",
    "candidate_sha256": "dcba5678",
    "hypothesis": "observe_underperforming_pair_cluster_v1",
    "no_proposal_reason": None,
    "dry_run": True,
    "parameters": {},
    "cycle_id": "20260622T050051Z",
    "promotion_block_reason_codes": [],
    "walk_forward_net_metrics": {
        "metrics_source": "walk_forward_net_metrics",
        "evaluation_status": "NEGATIVE_NET_METRICS",
        "total_net_pnl": -7.0,
        "profit_factor": 0.5,
        "total_trades": 10,
        "max_drawdown_pct": 8.0,
    },
}

NO_PROPOSAL_DICT: dict[str, object] = {
    "bot_id": "freqtrade-freqforge-canary",
    "decision_type": "NO_PROPOSAL",
    "approval_status": "NOT_APPLICABLE",
    "approval_eligible": False,
    "requires_human_approval": True,
    "base_mode": "proposal_only",
    "candidate_sha256": "00000000",
    "hypothesis": "",
    "no_proposal_reason": "insufficient_signal_depth",
    "dry_run": True,
    "parameters": {},
    "cycle_id": "20260622T050051Z",
    "promotion_block_reason_codes": ["no_proposal"],
    "walk_forward_net_metrics": {
        "metrics_source": "not_applicable",
        "evaluation_status": "NOT_APPLICABLE",
        "total_net_pnl": 0.0,
        "profit_factor": 0.0,
        "total_trades": 0,
        "max_drawdown_pct": 0.0,
    },
}

HIGH_DRAWDOWN_PROPOSAL: dict[str, object] = {
    **APPROVED_PROPOSAL,
    "bot_id": "freqai-rebel",
    "hypothesis": "reinforce_profitable_pair_cluster_v1",
    "promotion_block_reason_codes": ["high_drawdown"],
    "walk_forward_net_metrics": {
        **APPROVED_PROPOSAL["walk_forward_net_metrics"],  # type: ignore[arg-type]
        "max_drawdown_pct": 25.0,
    },
}

POSITIVE_PROFIT_PROPOSAL: dict[str, object] = {
    **APPROVED_PROPOSAL,
    "bot_id": "freqtrade-freqforge-canary",
    "hypothesis": "reinforce_profitable_pair_cluster_v1",
    "promotion_block_reason_codes": ["positive_profit_hypothesis"],
    "walk_forward_net_metrics": {
        **APPROVED_PROPOSAL["walk_forward_net_metrics"],  # type: ignore[arg-type]
        "total_net_pnl": 3.2,
        "profit_factor": 1.5,
    },
}


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------


class TestSourceValidation:
    def test_real_sources(self) -> None:
        assert _is_real_source("walk_forward_net_metrics") is True
        assert _is_real_source("freqtrade_rest") is True
        assert _is_real_source("real") is True

    def test_fake_sources(self) -> None:
        assert _is_real_source("not_applicable") is False
        assert _is_real_source("synthetic") is False
        assert _is_real_source("unknown") is False


# ---------------------------------------------------------------------------
# Hard block detection
# ---------------------------------------------------------------------------


class TestHardBlock:
    def test_non_blocking_codes(self) -> None:
        assert _is_hard_block("positive_profit_hypothesis") is False
        assert _is_hard_block("watchlist_promoted_to_shadow_proposal") is False
        assert _is_hard_block("multi_cycle_candidate") is False

    def test_hard_block_codes(self) -> None:
        assert _is_hard_block("high_drawdown") is True
        assert _is_hard_block("negative_net_pnl") is True
        assert _is_hard_block("low_profit_factor") is True
        assert _is_hard_block("no_proposal") is True
        assert _is_hard_block("") is True


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------


class TestEligibility:
    def test_approved_proposal_passes(self) -> None:
        eligible, reasons = check_apply_eligibility(APPROVED_PROPOSAL)
        assert eligible is True
        assert reasons == []

    def test_not_approved_fails(self) -> None:
        eligible, reasons = check_apply_eligibility(NOT_APPROVED_PROPOSAL)
        assert eligible is False
        assert any("APPROVED" in r for r in reasons)

    def test_no_proposal_fails(self) -> None:
        eligible, reasons = check_apply_eligibility(NO_PROPOSAL_DICT)
        assert eligible is False
        assert any("SHADOW_PROPOSAL" in r for r in reasons)

    def test_high_drawdown_fails(self) -> None:
        eligible, reasons = check_apply_eligibility(HIGH_DRAWDOWN_PROPOSAL)
        assert eligible is False
        assert any("hard_block" in r for r in reasons)

    def test_positive_profit_hypothesis_is_not_hard_block(self) -> None:
        """positive_profit_hypothesis is a soft code, not a hard block."""
        eligible, reasons = check_apply_eligibility(POSITIVE_PROFIT_PROPOSAL)
        assert eligible is True
        assert reasons == []

    def test_synthetic_source_fails(self) -> None:
        bad = dict(APPROVED_PROPOSAL)
        wf = dict(bad["walk_forward_net_metrics"])  # type: ignore[arg-type]
        wf["metrics_source"] = "synthetic"
        bad["walk_forward_net_metrics"] = wf
        eligible, reasons = check_apply_eligibility(bad)
        assert eligible is False
        assert any("metrics_source" in r for r in reasons)

    def test_dry_run_false_fails(self) -> None:
        bad = dict(APPROVED_PROPOSAL)
        bad["dry_run"] = False
        eligible, reasons = check_apply_eligibility(bad)
        assert eligible is False
        assert any("dry_run" in r for r in reasons)

    def test_approval_eligible_false_fails(self) -> None:
        bad = dict(APPROVED_PROPOSAL)
        bad["approval_eligible"] = False
        eligible, reasons = check_apply_eligibility(bad)
        assert eligible is False
        assert any("approval_eligible" in r for r in reasons)


# ---------------------------------------------------------------------------
# Apply plan creation
# ---------------------------------------------------------------------------


class TestCreateApplyPlan:
    def test_creates_artifact_for_approved_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = create_apply_plan(
                APPROVED_PROPOSAL,
                apply_dir=tmp,
                approved_by="test-human",
            )
            assert Path(path).exists()
            with open(path) as f:
                plan = json.load(f)
            assert plan["apply_plan_id"] != ""
            assert plan["bot_id"] == "freqtrade-freqforge"
            assert plan["mutation_performed"] is False
            assert plan["safety_verdict"] == APPLY_STATUS_CREATED

    def test_artifact_contains_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = create_apply_plan(APPROVED_PROPOSAL, apply_dir=tmp)
            with open(path) as f:
                plan = json.load(f)
            required = [
                "apply_plan_id", "bot_id", "candidate_sha256", "hypothesis",
                "source_evidence_cycle", "plan_generated_at_utc",
                "approved_by", "approved_at_utc", "parameter_overlay",
                "safety_verdict", "safety_reasons", "mutation_performed",
                "mutation_type",
            ]
            for key in required:
                assert key in plan, f"Missing field: {key}"

    def test_raises_for_unapproved_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError, match="not eligible"):
            create_apply_plan(NOT_APPROVED_PROPOSAL, apply_dir=tmp)

    def test_raises_for_no_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError, match="not eligible"):
            create_apply_plan(NO_PROPOSAL_DICT, apply_dir=tmp)

    def test_raises_for_high_drawdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError, match="not eligible"):
            create_apply_plan(HIGH_DRAWDOWN_PROPOSAL, apply_dir=tmp)

    def test_positive_profit_hypothesis_allowed(self) -> None:
        """positive_profit_hypothesis is not a hard block → apply allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            path = create_apply_plan(POSITIVE_PROFIT_PROPOSAL, apply_dir=tmp)
            assert Path(path).exists()

    def test_approved_by_field_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = create_apply_plan(
                APPROVED_PROPOSAL,
                apply_dir=tmp,
                approved_by="captain-luke",
            )
            with open(path) as f:
                plan = json.load(f)
            assert plan["approved_by"] == "captain-luke"

    def test_mutation_performed_always_false(self) -> None:
        """In v1, mutation_performed is ALWAYS False."""
        with tempfile.TemporaryDirectory() as tmp:
            path = create_apply_plan(APPROVED_PROPOSAL, apply_dir=tmp)
            with open(path) as f:
                plan = json.load(f)
            assert plan["mutation_performed"] is False
            assert plan["mutation_type"] == "none"


# ---------------------------------------------------------------------------
# Four-bot coverage
# ---------------------------------------------------------------------------


class TestFourBotCoverage:
    def test_all_four_bots_can_be_checked(self) -> None:
        """Verify that representative proposals for all bots are covered."""
        bots = {
            "freqtrade-freqforge": APPROVED_PROPOSAL,
            "freqtrade-regime-hybrid": NOT_APPROVED_PROPOSAL,
            "freqtrade-freqforge-canary": POSITIVE_PROFIT_PROPOSAL,
            "freqai-rebel": HIGH_DRAWDOWN_PROPOSAL,
        }
        with tempfile.TemporaryDirectory() as tmp:
            for _bot_id, prop in bots.items():
                eligible, _ = check_apply_eligibility(prop)
                if eligible:
                    path = create_apply_plan(prop, apply_dir=tmp)
                    assert Path(path).exists()
                # Not-approved and high-drawdown proposals correctly blocked
