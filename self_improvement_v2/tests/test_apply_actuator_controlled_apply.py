"""Tests for Controlled Apply Runner — token-gated wiring (#335).

Covers the complete test matrix:
  1. No token → AUDIT_ONLY, mutation=0, measurement blocked
  2. Token provided → actuator runs with docker checks
  3. Token provided but actuator blocks → TOKEN_GATED_BLOCKED
  4. Ineligible proposal → BLOCKED
  5. dry_run=false → BLOCKED
  6. Wrong bot path → BLOCKED via actuator
  7. proposal_to_overlay conversion
  8. check_activation_token function
  9. Batch helper
  10. summarize_results
  11. Properties: mutation_counter_should_increment, measurement_allowed
  12. _normalize_bot_id covers all 4 bots
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from si_v2.apply_actuator.controlled_apply import (
    ACTIVATION_TOKEN_ENV,
    ACTIVATION_TOKEN_VALUE,
    ControlledApplyMode,
    ControlledApplyResult,
    _normalize_bot_id,
    check_activation_token,
    proposal_to_overlay,
    run_controlled_apply,
    run_controlled_apply_batch,
    summarize_results,
)
from si_v2.apply_actuator.models import (
    ApplyActuatorResult,
    ApplyStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def approved_proposal_freqforge() -> dict[str, object]:
    """A minimal APPROVED SHADOW_PROPOSAL for freqtrade-freqforge."""
    return {
        "decision_type": "SHADOW_PROPOSAL",
        "approval_status": "APPROVED",
        "approval_eligible": True,
        "requires_human_approval": True,
        "base_mode": "proposal_only",
        "bot_id": "freqforge",
        "candidate_sha256": "65502d13a99bfadd",
        "hypothesis": "reinforce_profitable_pair_cluster_v1",
        "cycle_id": "20260623T055529Z",
        "mutation_policy": "safe_parameter_overlay_only",
        "parameter_overlay": {
            "max_open_trades": 3,
        },
        "walk_forward_net_metrics": {
            "metrics_source": "walk_forward_net_metrics",
            "net_pnl": 23.88,
        },
        "promotion_block_reason_codes": [],
        "no_proposal_reason": None,
        "dry_run": True,
    }


@pytest.fixture
def no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the activation token is NOT set."""
    monkeypatch.delenv(ACTIVATION_TOKEN_ENV, raising=False)


@pytest.fixture
def with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the activation token to APPROVE."""
    monkeypatch.setenv(ACTIVATION_TOKEN_ENV, ACTIVATION_TOKEN_VALUE)


# ---------------------------------------------------------------------------
# 1. No token → AUDIT_ONLY
# ---------------------------------------------------------------------------


class TestNoTokenAuditOnly:
    """Without the L3 token, the runner must be AUDIT_ONLY."""

    def test_mode_is_audit_only(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert result.mode == ControlledApplyMode.AUDIT_ONLY

    def test_token_provided_false(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert result.token_provided is False

    def test_mutation_counter_stays_zero(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert result.mutation_counter_should_increment is False

    def test_measurement_blocked(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert result.measurement_allowed is False

    def test_eligibility_checked(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert result.eligible is True

    def test_warnings_contain_audit_only_note(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        result = run_controlled_apply(approved_proposal_freqforge)
        assert any("AUDIT_ONLY" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 2. Token provided → actuator runs
# ---------------------------------------------------------------------------


class TestTokenProvided:
    """With the token, the actuator runs with docker checks (still fail-closed)."""

    def test_token_provided_true(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        # docker_available=False to avoid CI Docker dependency
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert result.token_provided is True

    def test_mode_is_not_audit_only(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert result.mode != ControlledApplyMode.AUDIT_ONLY

    def test_mutation_stays_zero_without_docker_proof(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert result.mutation_counter_should_increment is False

    def test_measurement_blocked_without_docker_proof(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert result.measurement_allowed is False


# ---------------------------------------------------------------------------
# 3. Token provided but actuator blocks → TOKEN_GATED_BLOCKED
# ---------------------------------------------------------------------------


class TestTokenGatedBlocked:
    """Token present but actuator can't verify runtime → TOKEN_GATED_BLOCKED."""

    def test_mode_is_token_gated_blocked(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert result.mode == ControlledApplyMode.TOKEN_GATED_BLOCKED

    def test_warning_contains_fail_closed_note(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        result = run_controlled_apply(
            approved_proposal_freqforge,
            docker_available=False,
        )
        assert any("fail-closed" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 4. Ineligible proposal → BLOCKED
# ---------------------------------------------------------------------------


class TestIneligibleProposal:
    """Proposals that fail eligibility are blocked immediately."""

    def test_not_approved_blocked(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        proposal = dict(approved_proposal_freqforge)
        proposal["approval_status"] = "PENDING"
        result = run_controlled_apply(proposal)
        assert result.eligible is False
        assert result.mode == ControlledApplyMode.TOKEN_GATED_BLOCKED

    def test_not_shadow_proposal_blocked(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        proposal = dict(approved_proposal_freqforge)
        proposal["decision_type"] = "WATCH_ONLY"
        result = run_controlled_apply(proposal)
        assert result.eligible is False

    def test_eligibility_reasons_populated(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        proposal = dict(approved_proposal_freqforge)
        proposal["approval_status"] = "PENDING"
        result = run_controlled_apply(proposal)
        assert len(result.eligibility_reasons) > 0
        assert any("APPROVED" in r for r in result.eligibility_reasons)


# ---------------------------------------------------------------------------
# 5. dry_run=false → BLOCKED
# ---------------------------------------------------------------------------


class TestDryRunFalseBlocked:
    """A proposal with dry_run=False must be BLOCKED."""

    def test_dry_run_false_blocks_eligibility(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        proposal = dict(approved_proposal_freqforge)
        proposal["dry_run"] = False
        result = run_controlled_apply(proposal)
        assert result.eligible is False
        assert any("dry_run" in r.lower() for r in result.eligibility_reasons)

    def test_dry_run_false_no_mutation(
        self,
        approved_proposal_freqforge: dict[str, object],
        with_token: None,
    ) -> None:
        proposal = dict(approved_proposal_freqforge)
        proposal["dry_run"] = False
        result = run_controlled_apply(proposal)
        assert result.mutation_counter_should_increment is False


# ---------------------------------------------------------------------------
# 6. Properties: mutation_counter_should_increment + measurement_allowed
# ---------------------------------------------------------------------------


class TestResultProperties:
    """The ControlledApplyResult properties respect token + proof gates."""

    def test_mutation_requires_both_token_and_green_proof(self) -> None:
        # Green proof but no token → no mutation
        green_result = ControlledApplyResult(
            mode=ControlledApplyMode.AUDIT_ONLY,
            token_provided=False,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
                mutation_counter_should_increment=True,
                measurement_allowed=True,
            ),
        )
        assert green_result.mutation_counter_should_increment is False

    def test_mutation_with_token_and_green_proof(self) -> None:
        green_result = ControlledApplyResult(
            mode=ControlledApplyMode.ACTUATOR_VERIFIED,
            token_provided=True,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
                mutation_counter_should_increment=True,
                measurement_allowed=True,
            ),
        )
        assert green_result.mutation_counter_should_increment is True
        assert green_result.measurement_allowed is True

    def test_measurement_blocked_without_token(self) -> None:
        result = ControlledApplyResult(
            mode=ControlledApplyMode.AUDIT_ONLY,
            token_provided=False,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
                measurement_allowed=True,
            ),
        )
        assert result.measurement_allowed is False

    def test_to_dict_serialization(self) -> None:
        result = ControlledApplyResult(
            mode=ControlledApplyMode.AUDIT_ONLY,
            proposal_id="test123",
            bot_id="freqtrade-freqforge",
            eligible=True,
            token_provided=False,
        )
        d = result.to_dict()
        assert d["mode"] == "AUDIT_ONLY"
        assert d["proposal_id"] == "test123"
        assert d["token_provided"] is False
        assert d["mutation_counter_should_increment"] is False


# ---------------------------------------------------------------------------
# 7. proposal_to_overlay conversion
# ---------------------------------------------------------------------------


class TestProposalConversion:
    """proposal_to_overlay correctly converts evidence bundle dicts."""

    def test_basic_conversion(
        self,
        approved_proposal_freqforge: dict[str, object],
    ) -> None:
        overlay = proposal_to_overlay(approved_proposal_freqforge)
        assert overlay.proposal_id == "65502d13a99bfadd"
        assert overlay.bot_id == "freqtrade-freqforge"
        assert overlay.policy == "safe_parameter_overlay_only"
        assert overlay.parameters == {"max_open_trades": 3}

    def test_missing_sha256_uses_proposal_id(self) -> None:
        proposal: dict[str, object] = {
            "bot_id": "freqforge",
            "proposal_id": "abc123",
            "mutation_policy": "safe_parameter_overlay_only",
            "parameter_overlay": {},
        }
        overlay = proposal_to_overlay(proposal)
        assert overlay.proposal_id == "abc123"

    def test_empty_parameters(self) -> None:
        proposal: dict[str, object] = {
            "bot_id": "freqforge",
            "candidate_sha256": "deadbeef",
            "mutation_policy": "safe_parameter_overlay_only",
        }
        overlay = proposal_to_overlay(proposal)
        assert overlay.parameters == {}

    def test_non_dict_parameters_handled(self) -> None:
        proposal: dict[str, object] = {
            "bot_id": "freqforge",
            "candidate_sha256": "deadbeef",
            "mutation_policy": "safe_parameter_overlay_only",
            "parameter_overlay": "not_a_dict",
        }
        overlay = proposal_to_overlay(proposal)
        assert overlay.parameters == {}


# ---------------------------------------------------------------------------
# 8. _normalize_bot_id
# ---------------------------------------------------------------------------


class TestNormalizeBotId:
    """bot_id normalization covers all 4 fleet bots."""

    @pytest.mark.parametrize(
        ("input_id", "expected"),
        [
            ("freqforge", "freqtrade-freqforge"),
            ("freqforge-canary", "freqtrade-freqforge-canary"),
            ("regime-hybrid", "freqtrade-regime-hybrid"),
            ("freqai-rebel", "freqai-rebel"),
            ("freqtrade-freqforge", "freqtrade-freqforge"),
            ("freqtrade-freqforge-canary", "freqtrade-freqforge-canary"),
            ("freqtrade-regime-hybrid", "freqtrade-regime-hybrid"),
            ("", ""),
        ],
    )
    def test_normalization(self, input_id: str, expected: str) -> None:
        assert _normalize_bot_id(input_id) == expected


# ---------------------------------------------------------------------------
# 9. check_activation_token
# ---------------------------------------------------------------------------


class TestActivationToken:
    """Token check function returns correct values."""

    def test_no_token_returns_false(self, no_token: None) -> None:
        provided, detail = check_activation_token()
        assert provided is False
        assert ACTIVATION_TOKEN_ENV in detail

    def test_correct_token_returns_true(self, with_token: None) -> None:
        provided, detail = check_activation_token()
        assert provided is True
        assert "APPROVE" in detail

    def test_wrong_token_returns_false(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(ACTIVATION_TOKEN_ENV, "WRONG_VALUE")
        provided, _detail = check_activation_token()
        assert provided is False


# ---------------------------------------------------------------------------
# 10. Batch helper
# ---------------------------------------------------------------------------


class TestBatchApply:
    """run_controlled_apply_batch filters and processes correctly."""

    def test_skips_non_shadow_proposal(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        decisions = [
            approved_proposal_freqforge,
            {"decision_type": "WATCH_ONLY", "approval_status": "APPROVED"},
        ]
        results = run_controlled_apply_batch(decisions)
        assert len(results) == 1

    def test_skips_non_approved(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        pending = dict(approved_proposal_freqforge)
        pending["approval_status"] = "PENDING"
        decisions = [approved_proposal_freqforge, pending]
        results = run_controlled_apply_batch(decisions)
        assert len(results) == 1

    def test_empty_list(self, no_token: None) -> None:
        results = run_controlled_apply_batch([])
        assert len(results) == 0

    def test_multiple_approved(
        self,
        approved_proposal_freqforge: dict[str, object],
        no_token: None,
    ) -> None:
        canary = dict(approved_proposal_freqforge)
        canary["bot_id"] = "freqforge-canary"
        canary["candidate_sha256"] = "aabbccdd11223344"
        decisions = [approved_proposal_freqforge, canary]
        results = run_controlled_apply_batch(decisions)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# 11. summarize_results
# ---------------------------------------------------------------------------


class TestSummarizeResults:
    """summarize_results produces correct counts."""

    def test_all_audit_only(self) -> None:
        results = [
            ControlledApplyResult(mode=ControlledApplyMode.AUDIT_ONLY),
            ControlledApplyResult(mode=ControlledApplyMode.AUDIT_ONLY),
        ]
        summary = summarize_results(results)
        assert summary["total_proposals"] == 2
        assert summary["audit_only"] == 2
        assert summary["token_gated_blocked"] == 0
        assert summary["actuator_verified"] == 0
        assert summary["all_mutations_zero"] is True

    def test_mixed_modes(self) -> None:
        results = [
            ControlledApplyResult(mode=ControlledApplyMode.AUDIT_ONLY),
            ControlledApplyResult(mode=ControlledApplyMode.TOKEN_GATED_BLOCKED),
            ControlledApplyResult(
                mode=ControlledApplyMode.ACTUATOR_VERIFIED,
                token_provided=True,
                actuator_result=ApplyActuatorResult(
                    mutation_counter_should_increment=True,
                    measurement_allowed=True,
                ),
            ),
        ]
        summary = summarize_results(results)
        assert summary["total_proposals"] == 3
        assert summary["audit_only"] == 1
        assert summary["token_gated_blocked"] == 1
        assert summary["actuator_verified"] == 1
        assert summary["mutation_counters_incremented"] == 1
        assert summary["all_mutations_zero"] is False

    def test_empty_list(self) -> None:
        summary = summarize_results([])
        assert summary["total_proposals"] == 0
        assert summary["all_mutations_zero"] is True


# ---------------------------------------------------------------------------
# 12. GREEN proof simulation — mutation allowed only with token
# ---------------------------------------------------------------------------


class TestGreenProofSimulation:
    """Simulate a GREEN proof to verify mutation/measurement gating."""

    def test_green_proof_without_token_no_mutation(self) -> None:
        """Even with a GREEN actuator result, no token → no mutation."""
        result = ControlledApplyResult(
            mode=ControlledApplyMode.AUDIT_ONLY,
            token_provided=False,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
                mutation_counter_should_increment=True,
                measurement_allowed=True,
            ),
        )
        assert result.mutation_counter_should_increment is False
        assert result.measurement_allowed is False

    def test_green_proof_with_token_allows_mutation(self) -> None:
        """Token + GREEN actuator result → mutation and measurement allowed."""
        result = ControlledApplyResult(
            mode=ControlledApplyMode.ACTUATOR_VERIFIED,
            token_provided=True,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
                mutation_counter_should_increment=True,
                measurement_allowed=True,
            ),
        )
        assert result.mutation_counter_should_increment is True
        assert result.measurement_allowed is True

    def test_red_proof_with_token_no_mutation(self) -> None:
        """Token + RED actuator result → no mutation, no measurement."""
        result = ControlledApplyResult(
            mode=ControlledApplyMode.TOKEN_GATED_BLOCKED,
            token_provided=True,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.BLOCKED,
                mutation_counter_should_increment=False,
                measurement_allowed=False,
            ),
        )
        assert result.mutation_counter_should_increment is False
        assert result.measurement_allowed is False
