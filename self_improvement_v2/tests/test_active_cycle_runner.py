"""Tests for the SI v2 active cycle runner.

These are pure unit tests — no network, no Freqtrade, no Docker.
They test the cycle runner's components in isolation and verify:

    1. All four bots are processed
    2. Missing env vars fail closed
    3. One bot failing status does not silently mark fleet GREEN
    4. Secret redaction is thorough
    5. Proposal vs NO_PROPOSAL decision logic
    6. Mutation counters remain zero
    7. Output schema stability
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from si_v2.loop.cycle_state import (
    build_cycle_state,
    persist_cycle_state,
    print_cycle_state,
)
from si_v2.loop.fleet_analyzer import (
    DECISION_NO_PROPOSAL,
    DECISION_SHADOW_PROPOSAL,
    BotEvidence,
    analyze_fleet,
    fleet_decision_to_dict,
)

if TYPE_CHECKING:
    pass

# ======================================================================
# Helpers: build synthetic evidence for tests
# ======================================================================


def _build_evidence(
    bot_id: str,
    ping_ok: bool = True,
    ping_status_code: int = 200,
    status_auth_outcome: str = "AUTHENTICATED",
    status_status_code: int = 200,
    status_ok: bool = True,
    status_open_trades: int = 0,
    missing_env_vars: list[str] | None = None,
) -> BotEvidence:
    """Build a BotEvidence with default green values."""
    now_iso = datetime.now(UTC).isoformat()
    return BotEvidence(
        bot_id=bot_id,
        base_url=f"http://trading-{bot_id}-1:8080",
        auth_type="env_basic_jwt",
        username_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_USERNAME",
        password_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_PASSWORD",
        ping_endpoint="/api/v1/ping",
        ping_status_code=ping_status_code,
        ping_ok=ping_ok,
        ping_response_summary='{"status":"ok"}',
        status_endpoint="/api/v1/status",
        status_status_code=status_status_code,
        status_ok=status_ok,
        status_response_summary='[{"trade_id":1}]',
        status_auth_outcome=status_auth_outcome,
        status_open_trades=status_open_trades,
        missing_env_vars=tuple(missing_env_vars or []),
        auth_error_summary="",
        fetched_at_utc=now_iso,
    )


ALL_BOT_IDS = [
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
]


def _all_green_evidence() -> list[BotEvidence]:
    """Produce evidence where all 4 bots are healthy and authenticated."""
    return [_build_evidence(bot_id) for bot_id in ALL_BOT_IDS]


# ======================================================================
# Test: All four bots processed
# ======================================================================


class TestAllBotsProcessed:
    """Verify the fleet analyzer processes all four bots."""

    def test_all_four_bots_processed(self) -> None:
        """All 4 bots appear in the fleet summary."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-001")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.total_bots == 4

    def test_all_bots_ping_ok(self) -> None:
        """All 4 bots ping successfully."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-002")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.ping_ok_count == 4
        assert decision.fleet_summary.ping_failed_count == 0

    def test_all_bots_authenticated(self) -> None:
        """All 4 bots have authenticated status."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-003")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.status_authenticated_count == 4
        assert decision.fleet_summary.status_failed_count == 0

    def test_fleet_verdict_green(self) -> None:
        """Fleet verdict is GREEN when all bots are healthy."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-004")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.fleet_verdict == "GREEN"

    def test_all_bots_have_decisions(self) -> None:
        """Each bot has a per-bot decision."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-005")
        assert len(decision.per_bot) == 4

    def test_all_decisions_are_shadow_proposal(self) -> None:
        """All 4 bots get SHADOW_PROPOSAL when evidence is green."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-006")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_SHADOW_PROPOSAL

    def test_all_candidates_have_sha256(self) -> None:
        """Every SHADOW_PROPOSAL has a non-empty candidate_sha256."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-007")
        for d in decision.per_bot:
            assert d.candidate_sha256, f"bot {d.bot_id} has empty candidate_sha256"

    def test_all_candidates_have_hypothesis(self) -> None:
        """Every SHADOW_PROPOSAL has a non-empty hypothesis."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-008")
        for d in decision.per_bot:
            assert d.hypothesis, f"bot {d.bot_id} has empty hypothesis"

    def test_all_candidates_have_parameters(self) -> None:
        """Every SHADOW_PROPOSAL has a parameters dict."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-009")
        for d in decision.per_bot:
            assert isinstance(d.parameters, dict)

    def test_all_candidates_have_evidence_summary(self) -> None:
        """Every SHADOW_PROPOSAL has an evidence_summary dict."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-010")
        for d in decision.per_bot:
            assert isinstance(d.evidence_summary, dict)
            assert "ping" in d.evidence_summary
            assert "status" in d.evidence_summary

    def test_all_candidates_have_safe_mutation_policy(self) -> None:
        """Every SHADOW_PROPOSAL has safe_parameter_overlay_only policy."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-011")
        for d in decision.per_bot:
            assert d.mutation_policy == "safe_parameter_overlay_only"

    def test_all_candidates_require_human_approval(self) -> None:
        """Every SHADOW_PROPOSAL requires human approval."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-012")
        for d in decision.per_bot:
            assert d.requires_human_approval is True

    def test_all_candidates_have_base_mode_proposal_only(self) -> None:
        """Every SHADOW_PROPOSAL has base_mode=proposal_only."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-013")
        for d in decision.per_bot:
            assert d.base_mode == "proposal_only"


# ======================================================================
# Test: Missing env vars fail closed
# ======================================================================


class TestMissingEnvVars:
    """When env vars are missing, the bot should fail closed."""

    def test_missing_env_vars_yellow(self) -> None:
        """Bot with missing env vars gets YELLOW status."""
        evidence = [
            _build_evidence(
                "freqtrade-freqforge",
                missing_env_vars=["SI_V2_FREQTRADE_FREQFORGE_USERNAME"],
            )
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-missing-env")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.status_yellow_missing_env_count == 1

    def test_missing_env_vars_no_proposal(self) -> None:
        """Bot with missing env vars gets NO_PROPOSAL."""
        evidence = [
            _build_evidence(
                "freqtrade-freqforge",
                missing_env_vars=["SI_V2_FREQTRADE_FREQFORGE_USERNAME"],
            )
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-missing-env-2")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_NO_PROPOSAL

    def test_missing_env_vars_reason(self) -> None:
        """Bot with missing env vars has a no_proposal_reason."""
        evidence = [
            _build_evidence(
                "freqtrade-freqforge",
                missing_env_vars=["SI_V2_FREQTRADE_FREQFORGE_USERNAME"],
            )
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-missing-env-3")
        for d in decision.per_bot:
            assert d.no_proposal_reason is not None
            assert "missing" in d.no_proposal_reason.lower()

    def test_missing_env_vars_does_not_affect_other_bots(self) -> None:
        """One bot with missing env vars does not affect other bots."""
        evidence = [
            _build_evidence("freqtrade-freqforge", missing_env_vars=["MISSING_VAR"]),
            _build_evidence("freqtrade-regime-hybrid"),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-missing-env-4")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.status_yellow_missing_env_count == 1
        assert decision.fleet_summary.status_authenticated_count == 1


# ======================================================================
# Test: One bot failing status does not silently mark fleet GREEN
# ======================================================================


class TestOneBotFailing:
    """When one bot fails, the fleet should not be GREEN."""

    def test_one_bot_ping_fails(self) -> None:
        """One bot with ping failure → fleet not GREEN."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),
            _build_evidence("freqtrade-regime-hybrid", ping_ok=False, ping_status_code=0),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-fail-1")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.ping_failed_count == 1
        assert decision.fleet_summary.fleet_verdict != "GREEN"

    def test_one_bot_status_fails(self) -> None:
        """One bot with status failure → fleet not GREEN."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),
            _build_evidence(
                "freqtrade-regime-hybrid",
                status_auth_outcome="FAILED",
                status_status_code=401,
                status_ok=False,
            ),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-fail-2")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.status_failed_count == 1
        assert decision.fleet_summary.fleet_verdict != "GREEN"

    def test_one_bot_fails_other_still_proposal(self) -> None:
        """One bot failing does not prevent other bots from getting proposals."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),
            _build_evidence("freqtrade-regime-hybrid", ping_ok=False, ping_status_code=0),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-fail-3")
        for d in decision.per_bot:
            if d.bot_id == "freqtrade-freqforge":
                assert d.decision_type == DECISION_SHADOW_PROPOSAL
            else:
                assert d.decision_type == DECISION_NO_PROPOSAL


# ======================================================================
# Test: Secret redaction
# ======================================================================


class TestSecretRedaction:
    """Verify that secrets are not leaked into evidence bundles."""

    def test_no_password_in_evidence_summary(self) -> None:
        """Evidence summary does not contain password values."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-secret-1")
        for d in decision.per_bot:
            summary = d.evidence_summary
            summary_text = json.dumps(summary)
            assert "password" not in summary_text.lower()

    def test_no_username_in_evidence_summary(self) -> None:
        """Evidence summary does not contain username values."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-secret-2")
        for d in decision.per_bot:
            summary = d.evidence_summary
            summary_text = json.dumps(summary)
            assert "username" not in summary_text.lower()

    def test_env_var_names_are_safe(self) -> None:
        """Env var NAMES are safe to include (they are identifiers, not secrets)."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-secret-3")
        for d in decision.per_bot:
            summary = d.evidence_summary
            summary_text = json.dumps(summary)
            # Env var names are identifiers, not secrets — they should be present
            assert "SI_V2_FREQTRADE" in summary_text

    def test_no_password_in_debug_output(self) -> None:
        """Debug output does not contain password values."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-secret-4")
        for d in decision.per_bot:
            summary = d.evidence_summary
            summary_text = json.dumps(summary)
            assert "PASSWORD" not in summary_text


# ======================================================================
# Test: Proposal vs NO_PROPOSAL decision logic
# ======================================================================


class TestProposalVsNoProposal:
    """Verify the decision logic for SHADOW_PROPOSAL vs NO_PROPOSAL."""

    def test_green_evidence_proposal(self) -> None:
        """Green evidence → SHADOW_PROPOSAL."""
        evidence = [_build_evidence("freqtrade-freqforge")]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-proposal-1")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_SHADOW_PROPOSAL

    def test_ping_fail_no_proposal(self) -> None:
        """Ping failure → NO_PROPOSAL."""
        evidence = [_build_evidence("freqtrade-freqforge", ping_ok=False, ping_status_code=0)]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-proposal-2")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_NO_PROPOSAL

    def test_status_fail_no_proposal(self) -> None:
        """Status failure → NO_PROPOSAL."""
        evidence = [
            _build_evidence(
                "freqtrade-freqforge",
                status_auth_outcome="FAILED",
                status_status_code=401,
                status_ok=False,
            )
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-proposal-3")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_NO_PROPOSAL

    def test_missing_env_no_proposal(self) -> None:
        """Missing env vars → NO_PROPOSAL."""
        evidence = [
            _build_evidence(
                "freqtrade-freqforge",
                missing_env_vars=["SI_V2_FREQTRADE_FREQFORGE_USERNAME"],
            )
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-proposal-4")
        for d in decision.per_bot:
            assert d.decision_type == DECISION_NO_PROPOSAL

    def test_mixed_evidence_mixed_decisions(self) -> None:
        """Mixed evidence → mixed decisions."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),
            _build_evidence("freqtrade-regime-hybrid", ping_ok=False, ping_status_code=0),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-cycle-proposal-5")
        decisions = {d.bot_id: d.decision_type for d in decision.per_bot}
        assert decisions["freqtrade-freqforge"] == DECISION_SHADOW_PROPOSAL
        assert decisions["freqtrade-regime-hybrid"] == DECISION_NO_PROPOSAL


# ======================================================================
# Test: Mutation counters remain zero
# ======================================================================


class TestMutationCounters:
    """Verify that mutation counters are always zero."""

    def test_runtime_mutations_zero(self) -> None:
        """runtime_mutations is 0."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-mutation-1")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.runtime_mutations == 0

    def test_config_mutations_zero(self) -> None:
        """config_mutations is 0."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-mutation-2")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.config_mutations == 0

    def test_live_trading_mutations_zero(self) -> None:
        """live_trading_mutations is 0."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-mutation-3")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.live_trading_mutations == 0

    def test_docker_mutations_zero(self) -> None:
        """docker_mutations is 0."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-mutation-4")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.docker_mutations == 0

    def test_strategy_mutations_zero(self) -> None:
        """strategy_mutations is 0."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-mutation-5")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.strategy_mutations == 0


# ======================================================================
# Test: Output schema stability
# ======================================================================


class TestOutputSchema:
    """Verify that the output schema is stable and contains expected fields."""

    def test_fleet_summary_has_all_fields(self) -> None:
        """Fleet summary has all expected fields."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-schema-1")
        assert decision.fleet_summary is not None
        expected = [
            "total_bots",
            "ping_ok_count",
            "ping_failed_count",
            "status_authenticated_count",
            "status_yellow_missing_env_count",
            "status_failed_count",
            "shadow_proposal_count",
            "no_proposal_count",
            "fleet_verdict",
            "fleet_verdict_reason",
            "runtime_mutations",
            "config_mutations",
            "live_trading_mutations",
            "docker_mutations",
            "strategy_mutations",
        ]
        for field in expected:
            assert hasattr(decision.fleet_summary, field), f"Missing field: {field}"

    def test_per_bot_decision_has_all_fields(self) -> None:
        """Per-bot decision has all expected fields."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-schema-2")
        for d in decision.per_bot:
            assert d.bot_id
            assert d.decision_type
            assert d.candidate_sha256
            assert d.base_mode
            assert d.mutation_policy
            assert d.requires_human_approval is not None
            assert d.hypothesis
            assert isinstance(d.parameters, dict)
            assert isinstance(d.evidence_summary, dict)

    def test_fleet_decision_to_dict(self) -> None:
        """fleet_decision_to_dict produces a serializable dict."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-schema-3")
        d = fleet_decision_to_dict(decision)
        assert isinstance(d, dict)
        assert "fleet_summary" in d
        assert "per_bot" in d
        assert len(d["per_bot"]) == 4

    def test_fleet_decision_to_dict_json_serializable(self) -> None:
        """fleet_decision_to_dict output is JSON-serializable."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-schema-4")
        d = fleet_decision_to_dict(decision)
        json.dumps(d)  # should not raise


# ======================================================================
# Test: Cycle state
# ======================================================================


class TestCycleState:
    """Verify cycle state building and persistence."""

    def test_build_cycle_state(self) -> None:
        """build_cycle_state returns a CycleState with expected fields."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-1")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-1",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        assert state.cycle_id == "test-cycle-state-1"
        assert state.branch == "main"
        assert state.commit_sha == "abc123"
        assert state.fleet_verdict is not None
        assert len(state.per_bot_decisions) == 4

    def test_persist_cycle_state(self, tmp_path: Path) -> None:
        """persist_cycle_state writes a JSON file."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-2")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-2",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        path = persist_cycle_state(state=state, state_dir=tmp_path)
        assert path.exists()
        content = json.loads(path.read_text())
        assert content["cycle_id"] == "test-cycle-state-2"

    def test_print_cycle_state(self) -> None:
        """print_cycle_state returns a non-empty string."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-3")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-3",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        output = print_cycle_state(state)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_cycle_state_has_mutation_counters(self) -> None:
        """Cycle state includes mutation counters."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-4")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-4",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        assert state.runtime_mutations == 0
        assert state.config_mutations == 0
        assert state.live_trading_mutations == 0
        assert state.docker_mutations == 0
        assert state.strategy_mutations == 0

    def test_cycle_state_has_controller_state(self) -> None:
        """Cycle state includes controller state."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-5")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-5",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        assert state.controller_state == "PAUSED / L3_REPOSITORY_ONLY"

    def test_cycle_state_has_external_signals(self) -> None:
        """Cycle state includes external_signals dict."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-state-6")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]
        state = build_cycle_state(
            cycle_id="test-cycle-state-6",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
            external_signals={"rainbow": {"status": "DISABLED"}},
        )
        assert state.external_signals == {"rainbow": {"status": "DISABLED"}}

    def test_external_signals_default_empty(self) -> None:
        """CycleState defaults external_signals to empty dict if not provided."""
        from si_v2.loop.cycle_state import build_cycle_state

        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-no-rainbow")
        per_bot_raw = [{"bot_id": d.bot_id, "decision_type": d.decision_type} for d in decision.per_bot]

        state = build_cycle_state(
            cycle_id="test-cycle-no-rainbow",
            branch="main",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        assert state.external_signals == {}


# ======================================================================
# Test: Post-cycle evidence bundle validation hook
# ======================================================================


class TestPostCycleValidation:
    """Verify the post-cycle validation hook (_run_post_cycle_validation)."""

    def test_hook_writes_sidecar_for_valid_bundle(self, tmp_path: Path) -> None:
        """Hook writes a validation sidecar for a valid bundle."""
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

        # Create a minimal valid bundle
        bundle = {
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
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

        # Create two bundles — hook must validate the explicit one
        bundle_a = {
            "artifact_type": "active_cycle_runner_v1",
            "schema_version": 1,
            "cycle_id": "cycle_a",
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
        bundle_b = {
            "artifact_type": "active_cycle_runner_v1",
            "schema_version": 1,
            "cycle_id": "cycle_b",
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
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

        bundle = {
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
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

        # Bundle missing required key → RED
        bundle = {
            "artifact_type": "active_cycle_runner_v1",
            "schema_version": 1,
            "cycle_id": "20260626T120000Z",
            # Missing fleet_summary → RED
        }
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
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

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
        from si_v2.loop.active_cycle_runner import _run_post_cycle_validation

        bundle = {
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
        bundle_path = tmp_path / "active_cycle_20260626T120000Z.json"
        bundle_path.write_text(json.dumps(bundle))
        validation_dir = tmp_path / "validation"

        result = _run_post_cycle_validation(
            bundle_path=bundle_path,
            validation_dir=validation_dir,
        )
        sidecar_path = Path(result["sidecar_path"])
        assert sidecar_path.name == "evidence_validation_20260626T120000Z.json"
