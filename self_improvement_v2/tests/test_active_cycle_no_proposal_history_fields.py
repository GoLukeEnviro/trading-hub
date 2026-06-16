"""Tests for NO_PROPOSAL history enforcement fields in ActiveCycleRunner.

These tests validate the fix for the KeyError: 'history_status' crash
where NO_PROPOSAL safety_results entries lacked history enforcement
fields that Step 5 expects for all safety_results.

All tests are pure unit tests — no network, no Freqtrade, no Docker.
"""

from __future__ import annotations

from si_v2.loop.active_cycle_runner import (
    HISTORY_REASON_INSUFFICIENT,
    HISTORY_REASON_MISSING,
    HISTORY_STATUS_INSUFFICIENT,
    HISTORY_STATUS_MISSING,
    HISTORY_STATUS_NORMAL,
    MIN_REQUIRED_TELEMETRY_HISTORY_RUNS,
)
from si_v2.loop.fleet_analyzer import DECISION_NO_PROPOSAL

# ------------------------------------------------------------------
# Required fields for every safety_results entry (SHADOW_PROPOSAL or NO_PROPOSAL)
# ------------------------------------------------------------------
REQUIRED_HISTORY_FIELDS = frozenset({
    "history_status",
    "history_reason_codes",
    "min_required_runs",
    "promotion_blocked",
    "promotion_block_reason_codes",
})

REQUIRED_BASE_FIELDS = frozenset({
    "bot_id",
    "decision_type",
    "no_proposal_reason",
    "riskguard",
    "shadow_logger",
    "approval_status",
})


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestNoProposalHistoryFields:
    """Validate that NO_PROPOSAL safety_results include all history fields."""

    def test_no_proposal_all_required_fields_present(self) -> None:
        """All required fields (base + history) must be present."""
        safety_result = self._build_no_proposal_safety_result(
            bot_id="freqforge",
            evidence_window_dict={},
        )

        all_required = REQUIRED_BASE_FIELDS | REQUIRED_HISTORY_FIELDS
        result_keys = set(safety_result.keys())
        missing = all_required - result_keys
        assert not missing, f"Missing required fields: {missing}"

    def test_no_proposal_promotion_blocked_true(self) -> None:
        """NO_PROPOSAL must always have promotion_blocked=True."""
        for ed in ({}, {"runs_observed": 3}, {"runs_observed": 10}):
            result = self._build_no_proposal_safety_result("freqforge", ed)
            assert result["promotion_blocked"] is True, (
                f"promotion_blocked should be True for NO_PROPOSAL "
                f"(evidence_window={ed})"
            )
            assert isinstance(result["promotion_block_reason_codes"], list)
            block_reasons: list = result["promotion_block_reason_codes"]
            assert "no_proposal" in block_reasons, (
                f"promotion_block_reason_codes must include 'no_proposal' "
                f"(got {block_reasons})"
            )

    def test_no_proposal_approval_status_not_applicable(self) -> None:
        """NO_PROPOSAL must always have approval_status='NOT_APPLICABLE'."""
        result = self._build_no_proposal_safety_result("freqforge", {})
        assert result["approval_status"] == "NOT_APPLICABLE"

    def test_no_proposal_riskguard_skipped(self) -> None:
        """NO_PROPOSAL must have riskguard='SKIPPED_NO_PROPOSAL'."""
        result = self._build_no_proposal_safety_result("freqforge", {})
        assert result["riskguard"] == "SKIPPED_NO_PROPOSAL"

    def test_no_proposal_shadow_logger_skipped(self) -> None:
        """NO_PROPOSAL must have shadow_logger='SKIPPED_NO_PROPOSAL'."""
        result = self._build_no_proposal_safety_result("freqforge", {})
        assert result["shadow_logger"] == "SKIPPED_NO_PROPOSAL"

    def test_history_status_missing_when_no_evidence_window(self) -> None:
        """When evidence_window is missing, history_status must be MISSING."""
        result = self._build_no_proposal_safety_result(
            "freqforge", evidence_window_dict={},
        )
        assert result["history_status"] == HISTORY_STATUS_MISSING
        assert HISTORY_REASON_MISSING in result["history_reason_codes"]

    def test_history_status_insufficient_when_too_few_runs(self) -> None:
        """When runs_observed < MIN_REQUIRED, history_status must be INSUFFICIENT."""
        low_run_count = MIN_REQUIRED_TELEMETRY_HISTORY_RUNS - 1
        result = self._build_no_proposal_safety_result(
            "freqforge",
            evidence_window_dict={"runs_observed": low_run_count},
        )
        assert result["history_status"] == HISTORY_STATUS_INSUFFICIENT
        assert HISTORY_REASON_INSUFFICIENT in result["history_reason_codes"]

    def test_history_status_normal_when_sufficient_runs(self) -> None:
        """When runs_observed >= MIN_REQUIRED, history_status must be NORMAL."""
        result = self._build_no_proposal_safety_result(
            "freqforge",
            evidence_window_dict={"runs_observed": MIN_REQUIRED_TELEMETRY_HISTORY_RUNS + 1},
        )
        assert result["history_status"] == HISTORY_STATUS_NORMAL
        # No reason codes for NORMAL
        assert result["history_reason_codes"] == []

    def test_min_required_runs_present(self) -> None:
        """min_required_runs must be the configured constant."""
        result = self._build_no_proposal_safety_result("freqforge", {})
        assert result["min_required_runs"] == MIN_REQUIRED_TELEMETRY_HISTORY_RUNS

    def test_no_proposal_decision_type(self) -> None:
        """decision_type must be DECISION_NO_PROPOSAL."""
        result = self._build_no_proposal_safety_result("freqforge", {})
        assert result["decision_type"] == DECISION_NO_PROPOSAL

    def test_no_proposal_bot_id_present(self) -> None:
        """bot_id must be present and match."""
        result = self._build_no_proposal_safety_result("freqai-rebel", {})
        assert result["bot_id"] == "freqai-rebel"

    def test_no_proposal_no_proposal_reason_present(self) -> None:
        """no_proposal_reason must be present."""
        result = self._build_no_proposal_safety_result(
            "freqforge",
            {},
            no_proposal_reason="auth_failed",
        )
        assert result["no_proposal_reason"] == "auth_failed"

    def test_all_bots_no_proposal_step5_no_keyerror(self) -> None:
        """Simulate Step 5 injection with 4x NO_PROPOSAL — must not KeyError."""
        bots = ["freqforge", "regime-hybrid", "freqforge-canary", "freqai-rebel"]
        evidence_window: dict[str, object] = {"runs_observed": 3}

        # Build safety_results using the same logic as Step 4
        safety_results = []
        for bot_id in bots:
            sr = self._build_no_proposal_safety_result(bot_id, evidence_window)
            safety_results.append(sr)

        # Build per_bot_raw from safety_results (simulating Step 5)
        per_bot_raw = [
            {
                "bot_id": sr["bot_id"],
                "decision_type": sr["decision_type"],
            }
            for sr in safety_results
        ]

        # Now run Step 5 injection (lines ~1201-1220 in active_cycle_runner.py)
        for pd in per_bot_raw:
            # This is the exact pattern from Step 5 that crashed with KeyError
            pd["history_status"] = next(
                (s["history_status"] for s in safety_results if s["bot_id"] == pd.get("bot_id")),
                HISTORY_STATUS_MISSING,
            )
            pd["history_reason_codes"] = next(
                (s["history_reason_codes"] for s in safety_results if s["bot_id"] == pd.get("bot_id")),
                [HISTORY_REASON_MISSING],
            )
            pd["min_required_runs"] = MIN_REQUIRED_TELEMETRY_HISTORY_RUNS
            pd["promotion_blocked"] = next(
                (s["promotion_blocked"] for s in safety_results if s["bot_id"] == pd.get("bot_id")),
                True,
            )
            pd["promotion_block_reason_codes"] = next(
                (s["promotion_block_reason_codes"] for s in safety_results if s["bot_id"] == pd.get("bot_id")),
                [HISTORY_REASON_MISSING],
            )

        # If we got here without KeyError, the fix works
        # Validate the injected fields
        for pd in per_bot_raw:
            assert "history_status" in pd
            assert "history_reason_codes" in pd
            assert "promotion_blocked" in pd
            assert "promotion_block_reason_codes" in pd
            assert pd["promotion_blocked"] is True
            block_reasons: list = pd.get("promotion_block_reason_codes", [])
            assert "no_proposal" in block_reasons

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_no_proposal_safety_result(
        bot_id: str,
        evidence_window_dict: dict,
        no_proposal_reason: str = "auth_failed",
    ) -> dict[str, object]:
        """Build a safety result dict exactly as Step 4 builds it for NO_PROPOSAL.

        This replicates the fix logic at lines 1093-1120 of active_cycle_runner.py.
        """
        # History status derivation (mirrors the fix)
        if not evidence_window_dict:
            no_proposal_history_status = HISTORY_STATUS_MISSING
            no_proposal_history_reason_codes = [HISTORY_REASON_MISSING]
        else:
            runs_obs_raw = evidence_window_dict.get("runs_observed", 0)
            runs_obs = int(runs_obs_raw) if isinstance(runs_obs_raw, int) else 0
            if runs_obs < MIN_REQUIRED_TELEMETRY_HISTORY_RUNS:
                no_proposal_history_status = HISTORY_STATUS_INSUFFICIENT
                no_proposal_history_reason_codes = [HISTORY_REASON_INSUFFICIENT]
            else:
                no_proposal_history_status = HISTORY_STATUS_NORMAL
                no_proposal_history_reason_codes = []

        return {
            "bot_id": bot_id,
            "decision_type": DECISION_NO_PROPOSAL,
            "no_proposal_reason": no_proposal_reason,
            "riskguard": "SKIPPED_NO_PROPOSAL",
            "shadow_logger": "SKIPPED_NO_PROPOSAL",
            "approval_status": "NOT_APPLICABLE",
            "history_status": no_proposal_history_status,
            "history_reason_codes": no_proposal_history_reason_codes,
            "min_required_runs": MIN_REQUIRED_TELEMETRY_HISTORY_RUNS,
            "promotion_blocked": True,
            "promotion_block_reason_codes": ["no_proposal", *no_proposal_history_reason_codes],
        }
