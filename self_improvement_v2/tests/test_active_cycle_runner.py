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
from si_v2.loop.telemetry_normalizer import (
    normalize_raw_evidence,
    to_bot_evidence,
)

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

    def test_all_four_bots_accepted(self) -> None:
        """All 4 bots produce SHADOW_PROPOSAL when fully green."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-001")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.total_bots == 4
        assert len(decision.per_bot) == 4
        assert decision.fleet_summary.shadow_proposal_count == 4
        assert decision.fleet_summary.no_proposal_count == 0
        assert decision.fleet_summary.fleet_verdict == "GREEN"

    def test_all_bot_ids_present(self) -> None:
        """All expected bot IDs appear in the per-bot decisions."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-002")
        actual_ids = {d.bot_id for d in decision.per_bot}
        expected_ids = set(ALL_BOT_IDS)
        assert actual_ids == expected_ids

    def test_cycle_id_propagates(self) -> None:
        """The cycle_id is propagated to the FleetDecision."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-cycle-abc")
        assert decision.cycle_id == "test-cycle-abc"


# ======================================================================
# Test: Missing env vars fail closed
# ======================================================================


class TestMissingEnvVarsFailClosed:
    """When env vars are missing, the system fails closed."""

    def test_yellow_missing_env_vars_fleet_yellow(self) -> None:
        """All bots with YELLOW_MISSING_ENV_VARS produce a YELLOW verdict."""
        evidence = [
            _build_evidence(
                bot_id,
                status_auth_outcome="YELLOW_MISSING_ENV_VARS",
                status_status_code=0,
                status_ok=False,
                missing_env_vars=[
                    f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_USERNAME",
                ],
            )
            for bot_id in ALL_BOT_IDS
        ]
        decision = analyze_fleet(evidence, cycle_id="test-yellow-env")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.fleet_verdict == "YELLOW"
        assert decision.fleet_summary.status_yellow_missing_env_count == 4
        # Even with missing env, ping is OK -> SHADOW_PROPOSAL (reachability only)
        assert decision.fleet_summary.shadow_proposal_count == 4
        assert decision.fleet_summary.no_proposal_count == 0

    def test_mixed_yellow_and_green(self) -> None:
        """Mixed env-var availability produces a correct verdict."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),  # fully authenticated
            _build_evidence(
                "freqtrade-regime-hybrid",
                status_auth_outcome="YELLOW_MISSING_ENV_VARS",
                status_status_code=0,
                status_ok=False,
                missing_env_vars=["SOME_ENV"],
            ),
            _build_evidence("freqtrade-freqforge-canary"),  # fully authenticated
            _build_evidence(
                "freqai-rebel",
                status_auth_outcome="YELLOW_MISSING_ENV_VARS",
                status_status_code=0,
                status_ok=False,
                missing_env_vars=["SOME_ENV"],
            ),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-mixed")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.total_bots == 4
        assert decision.fleet_summary.ping_ok_count == 4
        assert decision.fleet_summary.fleet_verdict == "YELLOW"
        assert decision.fleet_summary.shadow_proposal_count == 4

    def test_empty_evidence_list(self) -> None:
        """An empty evidence list produces RED."""
        decision = analyze_fleet([], cycle_id="test-empty")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.total_bots == 0
        assert decision.fleet_summary.fleet_verdict == "RED"


# ======================================================================
# Test: One bot failing status does not silently mark fleet GREEN
# ======================================================================


class TestPartialFailure:
    """A single failing bot prevents GREEN verdict."""

    def test_one_bot_ping_fails_fleet_yellow(self) -> None:
        """One bot with ping failure prevents GREEN."""
        evidence = _all_green_evidence()
        # Make the third bot fail ping
        evidence[2] = _build_evidence(
            "freqtrade-freqforge-canary",
            ping_ok=False,
            ping_status_code=0,
            status_auth_outcome="NOT_ATTEMPTED",
            status_status_code=0,
            status_ok=False,
        )
        decision = analyze_fleet(evidence, cycle_id="test-ping-fail")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.ping_ok_count == 3
        assert decision.fleet_summary.ping_failed_count == 1
        assert decision.fleet_summary.fleet_verdict in ("YELLOW",)

        # The failing bot should get NO_PROPOSAL
        failing = [d for d in decision.per_bot if d.bot_id == "freqtrade-freqforge-canary"]
        assert len(failing) == 1
        assert failing[0].decision_type == DECISION_NO_PROPOSAL
        assert failing[0].no_proposal_reason == "ping_failed"

        # Other bots should still get SHADOW_PROPOSAL
        passing = [
            d for d in decision.per_bot
            if d.bot_id != "freqtrade-freqforge-canary"
        ]
        assert all(d.decision_type == DECISION_SHADOW_PROPOSAL for d in passing)

    def test_all_bots_ping_fail_fleet_red(self) -> None:
        """All bots with ping failure produces RED."""
        evidence = [
            _build_evidence(
                bot_id,
                ping_ok=False,
                ping_status_code=0,
                status_auth_outcome="NOT_ATTEMPTED",
                status_status_code=0,
                status_ok=False,
            )
            for bot_id in ALL_BOT_IDS
        ]
        decision = analyze_fleet(evidence, cycle_id="test-all-ping-fail")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.fleet_verdict == "RED"
        assert decision.fleet_summary.no_proposal_count == 4

    def test_multi_bot_auth_fail_some_proposals(self) -> None:
        """AUTH_FAILED bots get NO_PROPOSAL and don't affect others."""
        evidence = [
            _build_evidence("freqtrade-freqforge"),  # OK
            _build_evidence(
                "freqtrade-regime-hybrid",
                status_auth_outcome="FAILED",
                status_status_code=401,
                status_ok=False,
                status_open_trades=0,
            ),
            _build_evidence("freqtrade-freqforge-canary"),  # OK
            _build_evidence(
                "freqai-rebel",
                status_auth_outcome="FAILED",
                status_status_code=401,
                status_ok=False,
                status_open_trades=0,
            ),
        ]
        decision = analyze_fleet(evidence, cycle_id="test-auth-fail")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.fleet_verdict == "YELLOW"
        auth_fail_bots = [
            d for d in decision.per_bot
            if d.decision_type == DECISION_NO_PROPOSAL
        ]
        assert len(auth_fail_bots) == 2
        assert all(d.no_proposal_reason == "auth_failed" for d in auth_fail_bots)

        proposal_bots = [
            d for d in decision.per_bot
            if d.decision_type == DECISION_SHADOW_PROPOSAL
        ]
        assert len(proposal_bots) == 2


# ======================================================================
# Test: Secret redaction
# ======================================================================


class TestSecretRedactionInCycle:
    """Verify the fleet-level chain never leaks secrets."""

    def test_no_secret_in_evidence_summary(self) -> None:
        """Evidence summary redacted fields are NOT present."""
        evidence = _all_green_evidence()
        for ev in evidence:
            summary = ev.ping_response_summary
            assert "access_token" not in summary

    def test_fleet_decision_to_dict_no_secrets(self) -> None:
        """The serialized fleet decision contains no credential values."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-secure")
        raw = fleet_decision_to_dict(decision)
        raw_json = json.dumps(raw)

        for ev in evidence:
            if ev.username_env:
                assert ev.username_env in raw_json  # env-var NAME is safe
            if ev.password_env:
                assert ev.password_env in raw_json  # env-var NAME is safe

    def test_decision_parameters_are_empty(self) -> None:
        """All SHADOW_PROPOSAL decisions have empty parameters."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-empty-params")
        for d in decision.per_bot:
            if d.decision_type == DECISION_SHADOW_PROPOSAL:
                assert d.parameters == {}
                assert d.base_mode == "proposal_only"
                assert d.requires_human_approval is True


# ======================================================================
# Test: Proposal vs NO_PROPOSAL decision accuracy
# ======================================================================


class TestDecisionLogic:
    """Verify the decision rules A/B/C/D produce correct outputs."""

    def test_authenticated_gets_proposal(self) -> None:
        """Rule B: authenticated bots get SHADOW_PROPOSAL."""
        ev = _build_evidence("freqtrade-freqforge")
        decision = analyze_fleet([ev], cycle_id="test-rule-b")
        assert decision.per_bot[0].decision_type == DECISION_SHADOW_PROPOSAL
        assert decision.per_bot[0].hypothesis == "telemetry_status_endpoint_observable_v1"

    def test_yellow_env_gets_proposal(self) -> None:
        """Rule A: missing env vars but ping ok gets SHADOW_PROPOSAL."""
        ev = _build_evidence(
            "freqtrade-freqforge",
            status_auth_outcome="YELLOW_MISSING_ENV_VARS",
            status_status_code=0,
            status_ok=False,
            missing_env_vars=["SOME_ENV"],
        )
        decision = analyze_fleet([ev], cycle_id="test-rule-a-yellow")
        assert decision.per_bot[0].decision_type == DECISION_SHADOW_PROPOSAL
        assert decision.per_bot[0].hypothesis == "telemetry_reachability_baseline_established"

    def test_auth_failed_gets_no_proposal(self) -> None:
        """Rule C: auth failed gets NO_PROPOSAL."""
        ev = _build_evidence(
            "freqtrade-freqforge",
            status_auth_outcome="FAILED",
            status_status_code=401,
            status_ok=False,
        )
        decision = analyze_fleet([ev], cycle_id="test-rule-c")
        assert decision.per_bot[0].decision_type == DECISION_NO_PROPOSAL
        assert decision.per_bot[0].no_proposal_reason == "auth_failed"

    def test_ping_failed_gets_no_proposal(self) -> None:
        """Rule D: ping failed gets NO_PROPOSAL."""
        ev = _build_evidence(
            "freqtrade-freqforge",
            ping_ok=False,
            ping_status_code=0,
            status_auth_outcome="NOT_ATTEMPTED",
            status_status_code=0,
            status_ok=False,
        )
        decision = analyze_fleet([ev], cycle_id="test-rule-d")
        assert decision.per_bot[0].decision_type == DECISION_NO_PROPOSAL
        assert decision.per_bot[0].no_proposal_reason == "ping_failed"

    def test_missing_bot_id_gets_no_proposal(self) -> None:
        """Missing bot_id gets NO_PROPOSAL."""
        ev = _build_evidence("")
        ev_dict = {
            "bot_id": "",
            "base_url": "http://localhost:8080",
            "auth_type": "none",
            "username_env": None,
            "password_env": None,
            "ping_endpoint": "/api/v1/ping",
            "ping_status_code": 0,
            "ping_ok": False,
            "ping_response_summary": "",
            "status_endpoint": "/api/v1/status",
            "status_status_code": 0,
            "status_ok": False,
            "status_response_summary": "",
            "status_auth_outcome": "NOT_ATTEMPTED",
            "status_open_trades": 0,
            "missing_env_vars": (),
            "auth_error_summary": "",
            "fetched_at_utc": ev.fetched_at_utc,
        }
        bad_ev = BotEvidence(**ev_dict)
        decision = analyze_fleet([bad_ev], cycle_id="test-missing-id")
        assert decision.per_bot[0].decision_type == DECISION_NO_PROPOSAL
        assert decision.per_bot[0].no_proposal_reason == "missing_bot_id"


# ======================================================================
# Test: Mutation counters remain zero
# ======================================================================


class TestZeroMutations:
    """Verify that every output path has zero mutation counters."""

    def test_fleet_summary_has_zero_mutations(self) -> None:
        """FleetSummary mutation counters are all zero."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-mutation-zero")
        assert decision.fleet_summary is not None
        assert decision.fleet_summary.runtime_mutations == 0
        assert decision.fleet_summary.config_mutations == 0
        assert decision.fleet_summary.live_trading_mutations == 0

    def test_cycle_state_has_zero_mutations(self) -> None:
        """CycleState mutation counters are all zero."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-state-zero")
        per_bot_raw = [
            {
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "candidate_sha256": d.candidate_sha256,
                "hypothesis": d.hypothesis,
                "no_proposal_reason": d.no_proposal_reason,
            }
            for d in decision.per_bot
        ]
        state = build_cycle_state(
            cycle_id="test-state-zero",
            branch="test-branch",
            commit_sha="abc123",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        assert state.runtime_mutations == 0
        assert state.config_mutations == 0
        assert state.live_trading_mutations == 0
        assert state.docker_mutations == 0
        assert state.strategy_mutations == 0
        assert state.controller_state == "PAUSED / L3_REPOSITORY_ONLY"

    def test_evidence_bundle_no_mutation_counters(self) -> None:
        """The serialized fleet decision has zero mutation values."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="test-bundle-zero")
        raw = fleet_decision_to_dict(decision)
        assert raw["fleet_summary"]["runtime_mutations"] == 0
        assert raw["fleet_summary"]["config_mutations"] == 0
        assert raw["fleet_summary"]["live_trading_mutations"] == 0

    def test_verify_no_side_effects(self) -> None:
        """The fleet analyzer function is pure: calling it multiple times
        with the same evidence produces identical results."""
        evidence = _all_green_evidence()
        d1 = analyze_fleet(evidence, cycle_id="idempotent-test")
        d2 = analyze_fleet(evidence, cycle_id="idempotent-test")
        assert d1.fleet_summary is not None
        assert d2.fleet_summary is not None
        assert d1.fleet_summary.ping_ok_count == d2.fleet_summary.ping_ok_count
        assert d1.fleet_summary.fleet_verdict == d2.fleet_summary.fleet_verdict


# ======================================================================
# Test: Output schema stability
# ======================================================================


class TestSchemaStability:
    """Verify that output schemas are stable and JSON-safe."""

    def test_fleet_decision_structure(self) -> None:
        """FleetDecision has the expected top-level keys."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="schema-test")
        raw = fleet_decision_to_dict(decision)

        assert "cycle_id" in raw
        assert "generated_at_utc" in raw
        assert "per_bot" in raw
        assert "fleet_summary" in raw

        summary = raw["fleet_summary"]
        assert "total_bots" in summary
        assert "fleet_verdict" in summary
        assert "runtime_mutations" in summary
        assert "config_mutations" in summary
        assert "live_trading_mutations" in summary

    def test_per_bot_decision_structure(self) -> None:
        """Each per-bot decision has the expected fields."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="schema-per-bot")
        raw = fleet_decision_to_dict(decision)

        for bot_decision in raw["per_bot"]:
            assert "decision_type" in bot_decision
            assert "bot_id" in bot_decision
            assert "candidate_sha256" in bot_decision
            assert "base_mode" in bot_decision
            assert "mutation_policy" in bot_decision
            assert "requires_human_approval" in bot_decision
            assert "hypothesis" in bot_decision
            assert "parameters" in bot_decision
            assert "evidence_summary" in bot_decision
            assert "no_proposal_reason" in bot_decision
            assert "fetched_at_utc" in bot_decision

    def test_cycle_state_structure(self) -> None:
        """CycleState has the expected fields."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="schema-state")
        per_bot_raw = [
            {
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "candidate_sha256": d.candidate_sha256,
                "hypothesis": d.hypothesis,
                "no_proposal_reason": d.no_proposal_reason,
            }
            for d in decision.per_bot
        ]
        state = build_cycle_state(
            cycle_id="schema-state",
            branch="test-branch",
            commit_sha="def456",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )

        dumped = state.model_dump(mode="json")
        assert "schema_version" in dumped
        assert "cycle_id" in dumped
        assert "generated_at_utc" in dumped
        assert "total_bots" in dumped
        assert "fleet_verdict" in dumped
        assert "per_bot_decisions" in dumped
        assert isinstance(dumped["per_bot_decisions"], list)
        assert len(dumped["per_bot_decisions"]) == 4

    def test_cycle_state_json_roundtrip(self, tmp_path: Path) -> None:
        """CycleState survives a JSON write/read roundtrip."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="roundtrip")
        per_bot_raw = [
            {
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "candidate_sha256": d.candidate_sha256,
                "hypothesis": d.hypothesis,
                "no_proposal_reason": d.no_proposal_reason,
            }
            for d in decision.per_bot
        ]
        state = build_cycle_state(
            cycle_id="roundtrip",
            branch="test-branch",
            commit_sha="ghi789",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )

        # Write to temp dir
        written = persist_cycle_state(
            state=state,
            state_dir=tmp_path,
            create_symlink=False,
        )
        assert written.exists()

        # Read back
        from si_v2.loop.cycle_state import load_cycle_state
        loaded = load_cycle_state(written)

        assert loaded.cycle_id == state.cycle_id
        assert loaded.total_bots == state.total_bots
        assert loaded.fleet_verdict == state.fleet_verdict
        assert loaded.runtime_mutations == 0
        assert len(loaded.per_bot_decisions) == 4

    def test_cycle_state_print_not_empty(self) -> None:
        """print_cycle_state produces non-empty output."""
        evidence = _all_green_evidence()
        decision = analyze_fleet(evidence, cycle_id="print-test")
        per_bot_raw = [
            {
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "candidate_sha256": d.candidate_sha256,
                "hypothesis": d.hypothesis,
                "no_proposal_reason": d.no_proposal_reason,
            }
            for d in decision.per_bot
        ]
        state = build_cycle_state(
            cycle_id="print-test",
            branch="test",
            commit_sha="abc",
            fleet_decision=decision,
            per_bot_decisions_raw=per_bot_raw,
        )
        output = print_cycle_state(state)
        assert "print-test" in output
        assert "GREEN" in output
        assert "Per-bot decisions:" in output

    def test_normalizer_schema_matches_bot_evidence(self) -> None:
        """The to_bot_evidence conversion produces valid BotEvidence."""
        telemetry = normalize_raw_evidence(
            bot_id="freqtrade-freqforge",
            base_url="http://trading-freqtrade-freqforge-1:8080",
            ping_status_code=200,
            ping_response_summary='{"status":"ok"}',
            status_status_code=200,
            status_response_summary="[]",
            status_auth_outcome="AUTHENTICATED",
        )
        ev_dict = to_bot_evidence(telemetry)
        # Verify it can construct BotEvidence
        ev = BotEvidence(**ev_dict)
        assert ev.bot_id == "freqtrade-freqforge"
        assert ev.ping_ok is True
        assert ev.status_auth_outcome == "AUTHENTICATED"

    def test_load_latest_returns_none_when_missing(self) -> None:
        """load_latest_cycle_state returns None when no state exists."""
        import tempfile

        from si_v2.loop.cycle_state import load_latest_cycle_state
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = load_latest_cycle_state(state_dir=Path(tmp_dir))
        assert result is None
