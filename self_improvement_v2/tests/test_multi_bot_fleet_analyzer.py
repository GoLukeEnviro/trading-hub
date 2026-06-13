"""Tests for the SI v2 multi-bot fleet analyzer.

These tests are pure unit tests — no network, no Freqtrade, no Docker.
They exercise the decision matrix and the fleet-summary logic with
synthetic evidence, and assert that no secret value can ever leak
through the analyzer output.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from si_v2.loop.fleet_analyzer import (
    DECISION_NO_PROPOSAL,
    DECISION_SHADOW_PROPOSAL,
    NO_PROPOSAL_REASON_AUTH_FAILED,
    NO_PROPOSAL_REASON_INVALID_EVIDENCE,
    NO_PROPOSAL_REASON_MISSING_BOT_ID,
    NO_PROPOSAL_REASON_PING_FAILED,
    PROPOSAL_HYPOTHESIS_REACHABILITY,
    PROPOSAL_HYPOTHESIS_STATUS_OBSERVABLE,
    BotEvidence,
    analyze_fleet,
    fleet_decision_to_dict,
)

# ------------------------------------------------------------------
# Test fixtures
# ------------------------------------------------------------------


def _ev(
    bot_id: str = "freqtrade-freqforge",
    ping_ok: bool = True,
    status_auth_outcome: str = "YELLOW_MISSING_ENV_VARS",
    status_open_trades: int = 0,
    missing_env_vars: tuple[str, ...] = (),
) -> BotEvidence:
    """Build a BotEvidence for tests. Defaults reproduce the YELLOW cycle."""
    now = datetime.now(UTC).isoformat()
    return BotEvidence(
        bot_id=bot_id,
        base_url=f"http://trading-{bot_id}-1:8080",
        auth_type="env_basic_jwt",
        username_env=f"SII_V2_{bot_id.upper().replace('-','_')}_USERNAME",
        password_env=f"SII_V2_{bot_id.upper().replace('-','_')}_PASSWORD",
        ping_endpoint="/api/v1/ping",
        ping_status_code=200 if ping_ok else 0,
        ping_ok=ping_ok,
        ping_response_summary='{"status":"pong"}' if ping_ok else "connection_error",
        status_endpoint="/api/v1/status",
        status_status_code=200 if status_auth_outcome == "AUTHENTICATED" else 0,
        status_ok=status_auth_outcome == "AUTHENTICATED",
        status_response_summary="[redacted]"
        if status_auth_outcome == "AUTHENTICATED"
        else "YELLOW: missing env vars",
        status_auth_outcome=status_auth_outcome,
        status_open_trades=status_open_trades,
        missing_env_vars=missing_env_vars,
        auth_error_summary="",
        fetched_at_utc=now,
    )


# ------------------------------------------------------------------
# Per-bot decision rules
# ------------------------------------------------------------------


def test_ping_failed_emits_no_proposal() -> None:
    """Rule D: when /ping fails, there is no telemetry -> NO_PROPOSAL."""
    decision = analyze_fleet([_ev(ping_ok=False)], cycle_id="t1")
    assert len(decision.per_bot) == 1
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_NO_PROPOSAL
    assert d.no_proposal_reason == NO_PROPOSAL_REASON_PING_FAILED
    assert d.hypothesis == ""
    assert d.parameters == {}


def test_ping_ok_with_yellow_missing_env_emits_reachability_proposal() -> None:
    """Rule A: ping ok + status_auth unavailable -> reachability proposal."""
    decision = analyze_fleet(
        [_ev(ping_ok=True, status_auth_outcome="YELLOW_MISSING_ENV_VARS")],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_SHADOW_PROPOSAL
    assert d.hypothesis == PROPOSAL_HYPOTHESIS_REACHABILITY
    assert d.requires_human_approval is True
    assert d.base_mode == "proposal_only"
    assert d.mutation_policy == "safe_parameter_overlay_only"
    assert d.parameters == {}  # metadata-only, no executable parameters
    assert d.metadata_only_candidates.get("ping_reachable") == 1


def test_ping_ok_with_not_attempted_emits_reachability_proposal() -> None:
    """Rule A: auth config absent in registry -> still a reachability proposal."""
    decision = analyze_fleet(
        [_ev(ping_ok=True, status_auth_outcome="NOT_ATTEMPTED")],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_SHADOW_PROPOSAL
    assert d.hypothesis == PROPOSAL_HYPOTHESIS_REACHABILITY


def test_ping_ok_with_authenticated_emits_status_observable_proposal() -> None:
    """Rule B: full auth success -> status-observable proposal with open_trades."""
    decision = analyze_fleet(
        [_ev(ping_ok=True, status_auth_outcome="AUTHENTICATED", status_open_trades=3)],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_SHADOW_PROPOSAL
    assert d.hypothesis == PROPOSAL_HYPOTHESIS_STATUS_OBSERVABLE
    assert d.metadata_only_candidates.get("open_trades_observed") == 3


def test_ping_ok_with_auth_failed_emits_no_proposal() -> None:
    """Rule C: auth attempted but failed -> NO_PROPOSAL (ambiguous evidence)."""
    decision = analyze_fleet(
        [_ev(ping_ok=True, status_auth_outcome="FAILED")],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_NO_PROPOSAL
    assert d.no_proposal_reason == NO_PROPOSAL_REASON_AUTH_FAILED


def test_ping_ok_with_unknown_outcome_emits_no_proposal() -> None:
    """Unknown outcome is treated as invalid evidence -> NO_PROPOSAL."""
    decision = analyze_fleet(
        [_ev(ping_ok=True, status_auth_outcome="WAT")],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_NO_PROPOSAL
    assert d.no_proposal_reason == NO_PROPOSAL_REASON_INVALID_EVIDENCE


def test_missing_bot_id_emits_no_proposal() -> None:
    """Rule: empty bot_id -> NO_PROPOSAL with missing_bot_id reason."""
    decision = analyze_fleet(
        [BotEvidence(
            bot_id="",
            base_url="http://x:8080",
            auth_type="env_basic_jwt",
            username_env="U", password_env="P",
            ping_endpoint="/api/v1/ping",
            ping_status_code=200, ping_ok=True,
            ping_response_summary="ok",
            status_endpoint="/api/v1/status",
            status_status_code=0, status_ok=False,
            status_response_summary="n/a",
            status_auth_outcome="YELLOW_MISSING_ENV_VARS",
            status_open_trades=0,
            missing_env_vars=("U","P"),
            auth_error_summary="",
            fetched_at_utc="2026-01-01T00:00:00+00:00",
        )],
        cycle_id="t1",
    )
    d = decision.per_bot[0]
    assert d.decision_type == DECISION_NO_PROPOSAL
    assert d.no_proposal_reason == NO_PROPOSAL_REASON_MISSING_BOT_ID


# ------------------------------------------------------------------
# Fleet-level summary
# ------------------------------------------------------------------


def test_fleet_summary_keeps_mutation_counters_at_zero() -> None:
    """Hard invariant: analyze_fleet must never report mutations."""
    decision = analyze_fleet(
        [_ev(), _ev(bot_id="b2")],
        cycle_id="t1",
    )
    assert decision.fleet_summary is not None
    s = decision.fleet_summary
    assert s.runtime_mutations == 0
    assert s.config_mutations == 0
    assert s.live_trading_mutations == 0


def test_fleet_verdict_yellow_when_all_bots_missing_env() -> None:
    """All 4 bots reachable but env missing -> YELLOW."""
    decision = analyze_fleet(
        [
            _ev(bot_id="b1"),
            _ev(bot_id="b2"),
            _ev(bot_id="b3"),
            _ev(bot_id="b4"),
        ],
        cycle_id="t1",
    )
    s = decision.fleet_summary
    assert s is not None
    assert s.total_bots == 4
    assert s.ping_ok_count == 4
    assert s.status_yellow_missing_env_count == 4
    assert s.fleet_verdict == "YELLOW"


def test_fleet_verdict_green_when_all_authenticated() -> None:
    """All 4 bots authenticated -> GREEN."""
    decision = analyze_fleet(
        [
            _ev(bot_id="b1", status_auth_outcome="AUTHENTICATED"),
            _ev(bot_id="b2", status_auth_outcome="AUTHENTICATED"),
            _ev(bot_id="b3", status_auth_outcome="AUTHENTICATED"),
            _ev(bot_id="b4", status_auth_outcome="AUTHENTICATED"),
        ],
        cycle_id="t1",
    )
    s = decision.fleet_summary
    assert s is not None
    assert s.fleet_verdict == "GREEN"
    assert s.status_authenticated_count == 4


def test_fleet_verdict_red_when_all_ping_failed() -> None:
    """All 4 bots unreachable -> RED."""
    decision = analyze_fleet(
        [
            _ev(bot_id="b1", ping_ok=False),
            _ev(bot_id="b2", ping_ok=False),
        ],
        cycle_id="t1",
    )
    s = decision.fleet_summary
    assert s is not None
    assert s.fleet_verdict == "RED"


def test_fleet_verdict_red_when_empty() -> None:
    """Empty fleet -> RED (loop cannot proceed)."""
    decision = analyze_fleet([], cycle_id="t1")
    s = decision.fleet_summary
    assert s is not None
    assert s.fleet_verdict == "RED"


def test_shadow_proposal_count_matches_decision_type() -> None:
    """shadow_proposal_count + no_proposal_count == total_bots."""
    decision = analyze_fleet(
        [
            _ev(bot_id="b1", status_auth_outcome="AUTHENTICATED"),
            _ev(bot_id="b2", status_auth_outcome="YELLOW_MISSING_ENV_VARS"),
            _ev(bot_id="b3", ping_ok=False),
            _ev(bot_id="b4", status_auth_outcome="FAILED"),
        ],
        cycle_id="t1",
    )
    s = decision.fleet_summary
    assert s is not None
    assert s.shadow_proposal_count + s.no_proposal_count == s.total_bots == 4
    assert s.shadow_proposal_count == 2  # b1 + b2
    assert s.no_proposal_count == 2  # b3 + b4


# ------------------------------------------------------------------
# Safety properties: no secret leakage, no executable parameters
# ------------------------------------------------------------------


def test_decisions_never_carry_executable_parameters() -> None:
    """All ShadowProposals must have empty parameters (metadata-only)."""
    decision = analyze_fleet(
        [
            _ev(bot_id="b1", status_auth_outcome="AUTHENTICATED"),
            _ev(bot_id="b2", status_auth_outcome="YELLOW_MISSING_ENV_VARS"),
            _ev(bot_id="b3", status_auth_outcome="NOT_ATTEMPTED"),
        ],
        cycle_id="t1",
    )
    for d in decision.per_bot:
        if d.decision_type == DECISION_SHADOW_PROPOSAL:
            assert d.parameters == {}
            # Never propose executable Freqtrade parameters from a read cycle
            for forbidden in ("max_open_trades", "stake_amount", "stoploss", "minimal_roi", "dry_run"):
                assert forbidden not in d.parameters


def test_all_decisions_require_human_approval() -> None:
    """Every ShadowProposal must require human approval."""
    decision = analyze_fleet(
        [_ev(bot_id="b1", status_auth_outcome="AUTHENTICATED")],
        cycle_id="t1",
    )
    for d in decision.per_bot:
        if d.decision_type == DECISION_SHADOW_PROPOSAL:
            assert d.requires_human_approval is True


def test_analyzer_output_does_not_leak_secret_value(monkeypatch) -> None:
    """If a real secret value is set in the env, the analyzer output must
    never contain it. This guards against a future regression that
    accidentally embeds env values in evidence."""
    secret = "supersecret-PASSWORD-DO-NOT-LEAK-12345"
    monkeypatch.setenv("SII_V2_FREQTRADE_FREQFORGE_USERNAME", secret)
    monkeypatch.setenv("SII_V2_FREQTRADE_FREQFORGE_PASSWORD", secret)

    ev = _ev(
        bot_id="freqtrade-freqforge",
        status_auth_outcome="AUTHENTICATED",
        missing_env_vars=(),
    )
    decision = analyze_fleet([ev], cycle_id="t1")
    payload = json.dumps(fleet_decision_to_dict(decision))
    assert secret not in payload, "secret value leaked through analyzer output"


def test_analyzer_output_contains_env_var_names_but_not_values(
    monkeypatch,
) -> None:
    """The evidence must reference the env-var NAMES (for traceability)
    but never the VALUES (for safety)."""
    monkeypatch.setenv("SII_V2_FREQTRADE_FREQFORGE_USERNAME", "alice")
    monkeypatch.setenv("SII_V2_FREQTRADE_FREQFORGE_PASSWORD", "hunter2")

    ev = _ev(
        bot_id="freqtrade-freqforge",
        status_auth_outcome="AUTHENTICATED",
    )
    decision = analyze_fleet([ev], cycle_id="t1")
    payload = json.dumps(fleet_decision_to_dict(decision))
    assert "SII_V2_FREQTRADE_FREQFORGE_USERNAME" in payload  # name is fine
    assert "alice" not in payload  # value must never appear
    assert "hunter2" not in payload


def test_fleet_decision_to_dict_is_json_safe() -> None:
    """The serializer must produce JSON-safe output (no dataclass leaks)."""
    decision = analyze_fleet(
        [_ev(bot_id="b1"), _ev(bot_id="b2", status_auth_outcome="AUTHENTICATED")],
        cycle_id="t1",
    )
    out: dict[str, Any] = fleet_decision_to_dict(decision)
    # Must round-trip through json.dumps without TypeError
    json.dumps(out)
    assert "cycle_id" in out
    assert "per_bot" in out
    assert "fleet_summary" in out
    assert isinstance(out["per_bot"], list)
    assert len(out["per_bot"]) == 2


# ------------------------------------------------------------------
# Registry-loading shape (sanity)
# ------------------------------------------------------------------


def test_registry_has_four_enabled_bots() -> None:
    """Sanity check on the readonly registry consumed by the proof."""
    from pathlib import Path

    # tests/test_multi_bot_fleet_analyzer.py lives at
    # self_improvement_v2/tests/ — go up two levels to the repo root.
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
    with open(registry_path) as f:
        registry = json.load(f)
    bots = [b for b in registry.get("bots", []) if b.get("enabled", True)]
    ids = sorted(b.get("bot_id") for b in bots)
    assert ids == [
        "freqai-rebel",
        "freqtrade-freqforge",
        "freqtrade-freqforge-canary",
        "freqtrade-regime-hybrid",
    ]
    for b in bots:
        auth = b.get("auth", {})
        assert auth.get("type") == "env_basic_jwt"
        assert auth.get("username_env", "").startswith("SI_V2_")
        assert auth.get("password_env", "").startswith("SI_V2_")
        assert b.get("dry_run_expected") is True
