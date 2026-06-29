"""Tests for multi-bot proof modules — pure functions only.

Tests cover:
- multi_bot_rest_shadowproposal_proof.py: _riskguard_check, _build_pending_human_artifact
- multi_bot_authenticated_telemetry_proof.py: _riskguard_check, _build_telemetry_artifact, BotTelemetryResult
- multi_bot_read_analyze_shadow_proposal.py: _riskguard_check, asdict_shadow_proposal, _build_report_markdown
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


# ======================================================================
# multi_bot_rest_shadowproposal_proof.py
# ======================================================================

class TestRestShadowproposalRiskguard:
    """_riskguard_check from the REST shadowproposal proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_rest_shadowproposal_proof as m
        return m

    def _make_candidate(self, **overrides: Any) -> Any:
        from si_v2.state.schemas import MutationCandidate
        base = dict(
            candidate_sha256="abc123",
            bot_id="freqforge",
            bot_name="freqforge",
            source_decision="SHADOW_PROPOSAL",
            active_overlay_candidates={},
            base_mode="proposal_only",
            requires_human_approval=True,
            mutation_policy="safe_parameter_overlay_only",
            parameters={},
        )
        base.update(overrides)
        return MutationCandidate(**base)

    def test_passes_safe_candidate(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate())
        assert result["result"] == m.RISKGUARD_RESULT_PASS_SHADOW_ONLY

    def test_blocks_wrong_base_mode(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate(base_mode="apply"))
        assert result["result"] == "BLOCKED"

    def test_blocks_no_human_approval(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate(requires_human_approval=False))
        assert result["result"] == "BLOCKED"

    def test_blocks_wrong_mutation_policy(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate(mutation_policy="full_apply"))
        assert result["result"] == "BLOCKED"

    def test_blocks_dry_run_false(self) -> None:
        m = self._import()
        # MutationCandidate parameters are dict[str, float | int], so use 0
        result = m._riskguard_check(self._make_candidate(parameters={"dry_run": 0}))
        assert result["result"] == "BLOCKED"
        assert "dry_run" in result["reason"]


class TestRestShadowproposalBuildArtifact:
    """_build_pending_human_artifact from the REST shadowproposal proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_rest_shadowproposal_proof as m
        return m

    def _make_candidate(self) -> Any:
        from si_v2.state.schemas import MutationCandidate
        return MutationCandidate(
            candidate_sha256="abc123",
            bot_id="freqforge",
            bot_name="freqforge",
            source_decision="SHADOW_PROPOSAL",
            active_overlay_candidates={},
            base_mode="proposal_only",
            requires_human_approval=True,
            mutation_policy="safe_parameter_overlay_only",
            parameters={},
        )

    def test_builds_artifact(self) -> None:
        m = self._import()
        candidate = self._make_candidate()
        fleet_snapshots = [
            {"bot_id": "freqforge", "ok": True, "response_summary": "pong"},
            {"bot_id": "freqforge-canary", "ok": True, "response_summary": "pong"},
        ]
        riskguard = {"result": "PASS_SHADOW_ONLY"}
        shadow_logger = {"outcome": "LOGGED"}
        artifact = m._build_pending_human_artifact(candidate, fleet_snapshots, riskguard, shadow_logger)
        assert artifact["artifact_type"] == "shadow_proposal_pending_human"
        assert artifact["proposal_id"] == "abc123"
        assert artifact["approval_status"] == "PENDING_HUMAN"
        assert artifact["runtime_mutations"] == 0
        assert artifact["config_mutations"] == 0
        assert artifact["freqtrade_post_requests"] == 0
        assert artifact["evidence_summary"]["bots_contacted"] == 2
        assert artifact["evidence_summary"]["all_ok"] is True

    def test_artifact_with_failures(self) -> None:
        m = self._import()
        candidate = self._make_candidate()
        fleet_snapshots = [
            {"bot_id": "freqforge", "ok": True, "response_summary": "pong"},
            {"bot_id": "freqforge-canary", "ok": False, "response_summary": "timeout"},
        ]
        riskguard = {"result": "PASS_SHADOW_ONLY"}
        shadow_logger = {"outcome": "LOGGED"}
        artifact = m._build_pending_human_artifact(candidate, fleet_snapshots, riskguard, shadow_logger)
        assert artifact["evidence_summary"]["all_ok"] is False

    def test_artifact_json_serializable(self) -> None:
        m = self._import()
        candidate = self._make_candidate()
        artifact = m._build_pending_human_artifact(candidate, [], {"result": "PASS"}, {"outcome": "LOGGED"})
        json.dumps(artifact)  # must not raise


# ======================================================================
# multi_bot_authenticated_telemetry_proof.py
# ======================================================================

class TestAuthTelemetryRiskguard:
    """_riskguard_check from the authenticated telemetry proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_authenticated_telemetry_proof as m
        return m

    def _make_candidate(self, **overrides: Any) -> Any:
        from si_v2.state.schemas import MutationCandidate
        base = dict(
            candidate_sha256="abc123",
            bot_id="freqforge",
            bot_name="freqforge",
            source_decision="SHADOW_PROPOSAL",
            active_overlay_candidates={},
            base_mode="proposal_only",
            requires_human_approval=True,
            mutation_policy="safe_parameter_overlay_only",
            parameters={},
        )
        base.update(overrides)
        return MutationCandidate(**base)

    def test_passes_safe(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate())
        assert result["result"] == m.RISKGUARD_RESULT_PASS_SHADOW_ONLY

    def test_blocks_live_trading(self) -> None:
        m = self._import()
        result = m._riskguard_check(self._make_candidate(parameters={"dry_run": 0}))
        assert result["result"] == "BLOCKED"


class TestBotTelemetryResult:
    """BotTelemetryResult dataclass-like."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_authenticated_telemetry_proof as m
        return m

    def test_creates_with_defaults(self) -> None:
        m = self._import()
        r = m.BotTelemetryResult(bot_id="freqforge", base_url="http://example.com")
        assert r.bot_id == "freqforge"
        assert r.classification == m.BOT_RED
        assert r.endpoints == {}
        assert r.auth_attempted is False
        assert r.auth_success is False

    def test_creates_with_values(self) -> None:
        m = self._import()
        r = m.BotTelemetryResult(
            bot_id="freqforge", base_url="http://example.com",
            classification=m.BOT_GREEN, endpoints={"/ping": {"ok": True}},
            auth_attempted=True, auth_success=True,
        )
        assert r.classification == m.BOT_GREEN
        assert r.auth_success is True


class TestAuthTelemetryBuildArtifact:
    """_build_telemetry_artifact from the authenticated telemetry proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_authenticated_telemetry_proof as m
        return m

    def _make_candidate(self) -> Any:
        from si_v2.state.schemas import MutationCandidate
        return MutationCandidate(
            candidate_sha256="abc123",
            bot_id="freqforge",
            bot_name="freqforge",
            source_decision="SHADOW_PROPOSAL",
            active_overlay_candidates={},
            base_mode="proposal_only",
            requires_human_approval=True,
            mutation_policy="safe_parameter_overlay_only",
            parameters={},
        )

    def _make_bot_results(self, m: Any) -> list:
        return [
            m.BotTelemetryResult("freqforge", "http://a", m.BOT_GREEN, {"/ping": {"ok": True, "status_code": 200}}, True, True),
            m.BotTelemetryResult("freqforge-canary", "http://b", m.BOT_YELLOW, {"/ping": {"ok": True, "status_code": 200}}, True, False),
        ]

    def test_builds_artifact(self) -> None:
        m = self._import()
        candidate = self._make_candidate()
        results = self._make_bot_results(m)
        artifact = m._build_telemetry_artifact(candidate, results, {"result": "PASS"}, {"outcome": "LOGGED"}, auth_post_count=2)
        assert artifact["artifact_type"] == "shadow_proposal_pending_human"
        assert artifact["approval_status"] == "PENDING_HUMAN"
        assert artifact["runtime_mutations"] == 0
        assert artifact["freqtrade_post_requests"] == 2
        assert artifact["freqtrade_mutation_requests"] == 0
        assert artifact["evidence_summary"]["green"] == 1
        assert artifact["evidence_summary"]["yellow"] == 1
        assert artifact["evidence_summary"]["red"] == 0

    def test_artifact_json_serializable(self) -> None:
        m = self._import()
        candidate = self._make_candidate()
        results = self._make_bot_results(m)
        artifact = m._build_telemetry_artifact(candidate, results, {"result": "PASS"}, {"outcome": "LOGGED"}, 2)
        json.dumps(artifact)


# ======================================================================
# multi_bot_read_analyze_shadow_proposal.py
# ======================================================================

class TestReadAnalyzeRiskguard:
    """_riskguard_check from the read/analyze/shadow-proposal proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_read_analyze_shadow_proposal as m
        return m

    def test_passes_safe_decision(self) -> None:
        m = self._import()
        decision = {
            "base_mode": "proposal_only",
            "requires_human_approval": True,
            "mutation_policy": "safe_parameter_overlay_only",
            "parameters": {},
            "candidate_sha256": "abc",
            "bot_id": "freqforge",
        }
        result = m._riskguard_check(decision)
        assert result["result"] == m.RISKGUARD_RESULT_PASS_SHADOW_ONLY

    def test_blocks_no_human_approval(self) -> None:
        m = self._import()
        decision = {
            "base_mode": "proposal_only",
            "requires_human_approval": False,
            "mutation_policy": "safe_parameter_overlay_only",
            "parameters": {},
            "candidate_sha256": "abc",
            "bot_id": "freqforge",
        }
        result = m._riskguard_check(decision)
        assert result["result"] == "BLOCKED"

    def test_blocks_dry_run_false(self) -> None:
        m = self._import()
        decision = {
            "base_mode": "proposal_only",
            "requires_human_approval": True,
            "mutation_policy": "safe_parameter_overlay_only",
            "parameters": {"dry_run": False},
            "candidate_sha256": "abc",
            "bot_id": "freqforge",
        }
        result = m._riskguard_check(decision)
        assert result["result"] == "BLOCKED"


class TestAsdictShadowProposal:
    """asdict_shadow_proposal from the read/analyze proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_read_analyze_shadow_proposal as m
        return m

    def _make_decision(self) -> Any:
        from si_v2.loop.fleet_analyzer import ShadowProposalDecision, DECISION_SHADOW_PROPOSAL
        return ShadowProposalDecision(
            decision_type=DECISION_SHADOW_PROPOSAL,
            bot_id="freqforge",
            candidate_sha256="abc123",
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis="test_hypothesis",
            parameters={"max_open_trades": 3},
            metadata_only_candidates={},
            evidence_summary={"ping": {"ok": True}},
            no_proposal_reason="",
            fetched_at_utc="2026-06-22T12:00:00Z",
        )

    def test_converts_decision(self) -> None:
        m = self._import()
        d = self._make_decision()
        result = m.asdict_shadow_proposal(d)
        assert result["decision_type"] == "SHADOW_PROPOSAL"
        assert result["bot_id"] == "freqforge"
        assert result["requires_human_approval"] is True
        assert result["parameters"]["max_open_trades"] == 3

    def test_json_serializable(self) -> None:
        m = self._import()
        d = self._make_decision()
        result = m.asdict_shadow_proposal(d)
        json.dumps(result)


class TestBuildReportMarkdown:
    """_build_report_markdown from the read/analyze proof."""

    def _import(self) -> Any:
        import si_v2.proofs.multi_bot_read_analyze_shadow_proposal as m
        return m

    def _make_evidence(self, m: Any, bot_id: str = "freqforge") -> Any:
        from si_v2.loop.fleet_analyzer import BotEvidence
        return BotEvidence(
            bot_id=bot_id,
            base_url=f"http://trading-{bot_id}-1:8080",
            auth_type="env_basic_jwt",
            username_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_USERNAME",
            password_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_PASSWORD",
            ping_endpoint="/api/v1/ping",
            ping_status_code=200,
            ping_ok=True,
            ping_response_summary='{"status":"ok"}',
            status_endpoint="/api/v1/status",
            status_status_code=200,
            status_ok=True,
            status_response_summary='[{"trade_id":1}]',
            status_auth_outcome="AUTHENTICATED",
            status_open_trades=2,
            missing_env_vars=(),
            auth_error_summary="",
            fetched_at_utc="2026-06-22T12:00:00Z",
        )

    def test_renders_report(self) -> None:
        m = self._import()
        from si_v2.loop.fleet_analyzer import analyze_fleet
        evidence = [self._make_evidence(m, "freqforge"), self._make_evidence(m, "freqforge-canary")]
        decision = analyze_fleet(evidence, cycle_id="test-cycle")
        report = m._build_report_markdown(
            cycle_id="test-cycle",
            branch="main",
            commit_sha="abc1234",
            now_iso="2026-06-22T12:00:00Z",
            evidence_list=evidence,
            decision=decision,
            safety_results=[],
        )
        assert "test-cycle" in report
        assert "main" in report
        assert "abc1234" in report
        assert "freqforge" in report
        assert "freqforge-canary" in report

    def test_report_with_safety_results(self) -> None:
        m = self._import()
        from si_v2.loop.fleet_analyzer import analyze_fleet
        evidence = [self._make_evidence(m)]
        decision = analyze_fleet(evidence, cycle_id="test-cycle")
        safety_results = [
            {"bot_id": "freqforge", "decision_type": "SHADOW_PROPOSAL", "shadow_logger": "LOGGED", "approval_status": "PENDING_HUMAN", "riskguard": "PASS_SHADOW_ONLY"},
        ]
        report = m._build_report_markdown(
            cycle_id="test-cycle", branch="main", commit_sha="abc",
            now_iso="2026-06-22T12:00:00Z",
            evidence_list=evidence, decision=decision,
            safety_results=safety_results,
        )
        assert "PENDING_HUMAN" in report
        assert "PASS_SHADOW_ONLY" in report
