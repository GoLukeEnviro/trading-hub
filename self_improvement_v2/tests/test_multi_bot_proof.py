"""Tests for the multi-bot read-only REST ShadowProposal proof.

Tests cover:
- Bot registry loading with all four enabled bots
- Fleet-level MutationCandidate structure
- RiskGuard gate passes for fleet proposal
- Runtime mutation counters at 0
- Approval status is PENDING_HUMAN
- Only GET endpoints in the allowlist are used

These tests do NOT require live Freqtrade instances.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]  # up to trading-hub/
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_PROOF_PATH = (
    _REPO_ROOT
    / "self_improvement_v2"
    / "src"
    / "si_v2"
    / "proofs"
    / "multi_bot_rest_shadowproposal_proof.py"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def bot_registry() -> dict[str, object]:
    """Load the actual bot registry config."""
    with open(_CONFIG_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def proof_module():
    """Import the proof module (once)."""
    import importlib.util as iu

    spec = iu.spec_from_file_location("multi_bot_proof", _PROOF_PATH)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Test: bot registry has all four bots enabled
# ---------------------------------------------------------------------------
class TestBotRegistry:
    """Verify the registry contains the expected four Freqtrade bots."""

    EXPECTED_BOT_IDS = frozenset({
        "freqtrade-freqforge",
        "freqtrade-regime-hybrid",
        "freqtrade-freqforge-canary",
        "freqai-rebel",
    })

    def test_registry_loads_valid_json(self, bot_registry):
        """Registry file must be valid JSON with a 'bots' key."""
        assert "bots" in bot_registry
        assert "schema_version" in bot_registry

    def test_exactly_four_bots(self, bot_registry):
        """Registry must contain exactly four bot entries."""
        bots = bot_registry["bots"]
        assert isinstance(bots, list)
        assert len(bots) == 4

    def test_all_bot_ids_present(self, bot_registry):
        """All four expected bot IDs must be in the registry."""
        bot_ids = {b.get("bot_id") for b in bot_registry["bots"]}
        assert bot_ids == self.EXPECTED_BOT_IDS

    def test_all_bots_enabled(self, bot_registry):
        """All four bots must be enabled for this proof."""
        enabled = [b for b in bot_registry["bots"] if b.get("enabled", False)]
        assert len(enabled) == 4
        enabled_ids = {b.get("bot_id") for b in enabled}
        assert enabled_ids == self.EXPECTED_BOT_IDS

    def test_all_bots_have_required_fields(self, bot_registry):
        """Each bot must have bot_id, base_url, and auth config."""
        required_fields = {"bot_id", "base_url", "auth"}
        for bot in bot_registry["bots"]:
            assert required_fields.issubset(bot.keys()), f"Bot {bot.get('bot_id')} missing fields"
            auth = bot.get("auth", {})
            assert "type" in auth
            assert auth["type"] == "env_basic_jwt"

    def test_all_bots_dry_run_expected(self, bot_registry):
        """Every bot must be expected to run in dry-run mode."""
        for bot in bot_registry["bots"]:
            assert bot.get("dry_run_expected") is True, (
                f"Bot {bot.get('bot_id')} dry_run_expected is not True"
            )


# ---------------------------------------------------------------------------
# Test: proof script structure
# ---------------------------------------------------------------------------
class TestProofStructure:
    """Verify the proof module has the required functions and structure."""

    def test_proof_has_main(self, proof_module):
        """The proof module must have a main() entry point."""
        assert hasattr(proof_module, "main")
        assert callable(proof_module.main)

    def test_proof_has_riskguard_check(self, proof_module):
        """The proof module must have a RiskGuard-style check."""
        assert hasattr(proof_module, "_riskguard_check")
        assert callable(proof_module._riskguard_check)

    def test_proof_has_build_artifact(self, proof_module):
        """The proof module must have a pending-human artifact builder."""
        assert hasattr(proof_module, "_build_pending_human_artifact")
        assert callable(proof_module._build_pending_human_artifact)

    def test_proof_config_path_points_to_registry(self, proof_module):
        """The proof's config path must match the registry location."""
        assert str(proof_module._CONFIG_PATH) == str(_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Test: RiskGuard gate rejects dangerous candidates
# ---------------------------------------------------------------------------
class TestRiskGuardGate:
    """Verify the RiskGuard-style check blocks inappropriate candidates."""

    def test_passes_fleet_candidate(self, proof_module):
        """A fleet candidate with proposal_only and human approval must pass."""
        from si_v2.state.schemas import MutationCandidate

        candidate = MutationCandidate(
            bot_id="fleet",
            bot_name="Fleet",
            candidate_sha256="test123",
            source_decision="observe",
            parameters={"dry_run": 1, "bot_count": 4},
            active_overlay_candidates={},
            metadata_only_candidates={"proof_multi_bot_ping": 1},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=True,
            requires_strategy_adapter=[],
        )
        result = proof_module._riskguard_check(candidate)
        assert result["result"] == "PASS_SHADOW_ONLY"
        assert "runtime_blocked=True" in str(result["details"])
        assert "fleet_scope=True" in str(result["details"])

    def test_blocks_live_trading_flag(self, proof_module):
        """A candidate with dry_run=0 (implies live) must be blocked."""
        from si_v2.state.schemas import MutationCandidate

        candidate = MutationCandidate(
            bot_id="fleet",
            bot_name="Fleet",
            candidate_sha256="test_live",
            source_decision="observe",
            parameters={"dry_run": 0},  # 0 = live trading per convention
            active_overlay_candidates={},
            metadata_only_candidates={},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=True,
            requires_strategy_adapter=[],
        )
        result = proof_module._riskguard_check(candidate)
        assert result["result"] == "BLOCKED"
        assert "dry_run" in result["reason"]

    def test_blocks_no_human_approval(self, proof_module):
        """A candidate without human approval must be blocked."""
        from si_v2.state.schemas import MutationCandidate

        candidate = MutationCandidate(
            bot_id="fleet",
            bot_name="Fleet",
            candidate_sha256="test_auto",
            source_decision="observe",
            parameters={"dry_run": 1},
            active_overlay_candidates={},
            metadata_only_candidates={},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=False,
            requires_strategy_adapter=[],
        )
        result = proof_module._riskguard_check(candidate)
        assert result["result"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Test: Approval artifact contains multi-bot fields
# ---------------------------------------------------------------------------
class TestApprovalArtifact:
    """Verify the pending-human artifact includes all four bots."""

    def test_artifact_contains_bot_ids(self, proof_module):
        """The artifact must list all four bot IDs."""
        from si_v2.state.schemas import MutationCandidate

        candidate = MutationCandidate(
            bot_id="freqtrade-freqforge+freqtrade-regime-hybrid+freqtrade-freqforge-canary+freqai-rebel",
            bot_name="Fleet",
            candidate_sha256="fleet_test",
            source_decision="observe",
            parameters={"dry_run": 1, "bot_count": 4},
            active_overlay_candidates={},
            metadata_only_candidates={"proof_multi_bot_ping": 1},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=True,
            requires_strategy_adapter=[],
        )
        fleet_snapshots = [
            {"bot_id": "freqtrade-freqforge", "endpoint": "/api/v1/ping",
             "status_code": 200, "ok": True,
             "response_summary": '{"status": "pong"}',
             "fetched_at_utc": "2026-06-15T10:00:00Z"},
            {"bot_id": "freqtrade-regime-hybrid", "endpoint": "/api/v1/ping",
             "status_code": 200, "ok": True,
             "response_summary": '{"status": "pong"}',
             "fetched_at_utc": "2026-06-15T10:00:01Z"},
            {"bot_id": "freqtrade-freqforge-canary", "endpoint": "/api/v1/ping",
             "status_code": 200, "ok": True,
             "response_summary": '{"status": "pong"}',
             "fetched_at_utc": "2026-06-15T10:00:02Z"},
            {"bot_id": "freqai-rebel", "endpoint": "/api/v1/ping",
             "status_code": 200, "ok": True,
             "response_summary": '{"status": "pong"}',
             "fetched_at_utc": "2026-06-15T10:00:03Z"},
        ]
        riskguard_result = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger_result = {"entries_count": 1, "outcome": "LOGGED",
                                "phase": "proof", "decision": "hold"}

        artifact = proof_module._build_pending_human_artifact(
            candidate=candidate,
            fleet_snapshots=fleet_snapshots,
            riskguard_result=riskguard_result,
            shadow_logger_result=shadow_logger_result,
        )

        assert artifact["approval_status"] == "PENDING_HUMAN"
        assert artifact["runtime_mutations"] == 0
        assert artifact["config_mutations"] == 0
        assert artifact["freqtrade_post_requests"] == 0

        # Verify all four bots in evidence
        evidence = artifact["evidence_summary"]
        assert evidence["bots_contacted"] == 4
        assert len(evidence["bot_ids"]) == 4
        assert "freqtrade-freqforge" in evidence["bot_ids"]
        assert "freqtrade-regime-hybrid" in evidence["bot_ids"]
        assert "freqtrade-freqforge-canary" in evidence["bot_ids"]
        assert "freqai-rebel" in evidence["bot_ids"]
        assert evidence["all_ok"] is True

    def test_artifact_shows_errors(self, proof_module):
        """The artifact must capture bot errors and not claim all_ok."""
        from si_v2.state.schemas import MutationCandidate

        candidate = MutationCandidate(
            bot_id="fleet",
            bot_name="Fleet",
            candidate_sha256="err_test",
            source_decision="observe",
            parameters={"dry_run": 1},
            active_overlay_candidates={},
            metadata_only_candidates={},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=True,
            requires_strategy_adapter=[],
        )
        # Empty snapshots + some errors
        snapshots = []
        riskguard_result = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger_result = {"entries_count": 1, "outcome": "LOGGED",
                                "phase": "proof", "decision": "hold"}

        artifact = proof_module._build_pending_human_artifact(
            candidate=candidate,
            fleet_snapshots=snapshots,
            riskguard_result=riskguard_result,
            shadow_logger_result=shadow_logger_result,
        )

        evidence = artifact["evidence_summary"]
        assert evidence["bots_contacted"] == 0
        assert not evidence["all_ok"]


# ---------------------------------------------------------------------------
# Test: Forbidden patterns (dry_run=false, live config)
# ---------------------------------------------------------------------------
class TestForbiddenPatterns:
    """Verify the proof does not introduce forbidden patterns."""

    def test_no_dry_run_false_in_source(self, proof_module):
        """The proof source must not contain 'dry_run=false' as a literal."""
        import re
        src = _PROOF_PATH.read_text()
        # Check for 'dry_run'=False as a literal assignment or parameter
        matches = re.findall(r'dry_run\s*=\s*False', src)
        assert len(matches) == 0, f"Found 'dry_run=False' in proof: {matches}"

    def test_no_live_trading_string(self, proof_module):
        """The proof must not contain 'dry_run=false'."""
        src = _PROOF_PATH.read_text()
        assert "dry_r" + "un=false" not in src
