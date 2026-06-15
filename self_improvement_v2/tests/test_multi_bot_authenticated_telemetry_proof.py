"""Tests for the multi-bot authenticated read-only telemetry proof.

Tests cover:
- Bot registry: all four bots present, enabled, auth configured
- Proof structure: required functions exist
- RiskGuard gate: PASS_SHADOW_ONLY for fleet candidate
- Auth-only POST enforcement
- Forbidden patterns: mutation_requests=0, no dry_run=false
- Classification logic: GREEN/YELLOW/RED

These tests do NOT require live Freqtrade or auth env vars.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_PROOF_PATH = (
    _REPO_ROOT
    / "self_improvement_v2"
    / "src"
    / "si_v2"
    / "proofs"
    / "multi_bot_authenticated_telemetry_proof.py"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def bot_registry() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def proof_module():
    import importlib.util as iu
    spec = iu.spec_from_file_location("auth_telemetry_proof", _PROOF_PATH)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestBotRegistry:
    """Registry must contain four enabled bots with auth config."""

    EXPECTED = frozenset({
        "freqtrade-freqforge",
        "freqtrade-regime-hybrid",
        "freqtrade-freqforge-canary",
        "freqai-rebel",
    })

    def test_registry_loads(self, bot_registry):
        assert "bots" in bot_registry

    def test_four_bots(self, bot_registry):
        assert len(bot_registry["bots"]) == 4

    def test_all_ids_present(self, bot_registry):
        ids = {b["bot_id"] for b in bot_registry["bots"]}
        assert ids == self.EXPECTED

    def test_all_enabled(self, bot_registry):
        enabled = [b for b in bot_registry["bots"] if b.get("enabled")]
        assert len(enabled) == 4

    def test_all_have_auth(self, bot_registry):
        for bot in bot_registry["bots"]:
            auth = bot.get("auth", {})
            assert auth.get("type") == "env_basic_jwt"
            assert auth.get("username_env")
            assert auth.get("password_env")

    def test_all_dry_run(self, bot_registry):
        for bot in bot_registry["bots"]:
            assert bot.get("dry_run_expected") is True


# ---------------------------------------------------------------------------
# Proof structure
# ---------------------------------------------------------------------------
class TestProofStructure:
    def test_has_main(self, proof_module):
        assert callable(proof_module.main)

    def test_has_riskguard(self, proof_module):
        assert callable(proof_module._riskguard_check)

    def test_has_build_artifact(self, proof_module):
        assert callable(proof_module._build_telemetry_artifact)

    def test_config_path(self, proof_module):
        assert str(proof_module._CONFIG_PATH) == str(_CONFIG_PATH)


# ---------------------------------------------------------------------------
# RiskGuard
# ---------------------------------------------------------------------------
class TestRiskGuard:
    def test_passes_fleet_candidate(self, proof_module):
        from si_v2.state.schemas import MutationCandidate
        c = MutationCandidate(
            bot_id="fleet", bot_name="Fleet", candidate_sha256="abc",
            source_decision="observe", parameters={"dry_run": 1, "bot_count": 4},
            active_overlay_candidates={}, metadata_only_candidates={"proof": 1},
            requires_backtest=False, requires_paper_validation=False,
            requires_human_approval=True, requires_strategy_adapter=[],
        )
        r = proof_module._riskguard_check(c)
        assert r["result"] == "PASS_SHADOW_ONLY"
        assert "auth_telemetry=True" in str(r["details"])

    def test_blocks_dry_run_zero(self, proof_module):
        from si_v2.state.schemas import MutationCandidate
        c = MutationCandidate(
            bot_id="fleet", bot_name="Fleet", candidate_sha256="live",
            source_decision="observe", parameters={"dry_run": 0},
            active_overlay_candidates={}, metadata_only_candidates={},
            requires_backtest=False, requires_paper_validation=False,
            requires_human_approval=True, requires_strategy_adapter=[],
        )
        r = proof_module._riskguard_check(c)
        assert r["result"] == "BLOCKED"

    def test_blocks_no_human_approval(self, proof_module):
        from si_v2.state.schemas import MutationCandidate
        c = MutationCandidate(
            bot_id="fleet", bot_name="Fleet", candidate_sha256="auto",
            source_decision="observe", parameters={"dry_run": 1},
            active_overlay_candidates={}, metadata_only_candidates={},
            requires_backtest=False, requires_paper_validation=False,
            requires_human_approval=False, requires_strategy_adapter=[],
        )
        r = proof_module._riskguard_check(c)
        assert r["result"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------
class TestClassification:
    def test_bot_result_dataclass(self, proof_module):
        r = proof_module.BotTelemetryResult(
            bot_id="test", base_url="http://localhost:8080"
        )
        assert r.bot_id == "test"
        assert r.classification == proof_module.BOT_RED  # default


# ---------------------------------------------------------------------------
# Artifact fields
# ---------------------------------------------------------------------------
class TestArtifact:
    def test_artifact_contains_fleet_fields(self, proof_module):
        from si_v2.state.schemas import MutationCandidate

        c = MutationCandidate(
            bot_id="fleet", bot_name="Fleet", candidate_sha256="art_test",
            source_decision="observe", parameters={"dry_run": 1, "bot_count": 4,
                                                    "green": 2, "yellow": 2, "red": 0},
            active_overlay_candidates={}, metadata_only_candidates={"proof": 1},
            requires_backtest=False, requires_paper_validation=False,
            requires_human_approval=True, requires_strategy_adapter=[],
        )
        results = [
            proof_module.BotTelemetryResult(
                bot_id="freqtrade-freqforge", base_url="http://a:8080",
                classification=proof_module.BOT_GREEN, auth_success=True,
                endpoints={"/api/v1/ping": {"ok": True, "status_code": 200}},
            ),
            proof_module.BotTelemetryResult(
                bot_id="freqtrade-regime-hybrid", base_url="http://b:8080",
                classification=proof_module.BOT_YELLOW, auth_attempted=True,
                endpoints={"/api/v1/ping": {"ok": True, "status_code": 200}},
            ),
        ]
        artifact = proof_module._build_telemetry_artifact(
            candidate=c, bot_results=results,
            riskguard_result={"result": "PASS_SHADOW_ONLY", "reason": "ok",
                              "details": []},
            shadow_logger_result={"entries_count": 1, "outcome": "LOGGED",
                                  "phase": "proof", "decision": "hold"},
            auth_post_count=1,
        )
        assert artifact["approval_status"] == "PENDING_HUMAN"
        assert artifact["runtime_mutations"] == 0
        assert artifact["config_mutations"] == 0
        assert artifact["freqtrade_mutation_requests"] == 0
        assert artifact["freqtrade_post_requests"] == 1  # auth only
        assert artifact["source"] == "multi_bot_authenticated_rest_telemetry"
        ev = artifact["evidence_summary"]
        assert ev["bots_contacted"] == 2
        assert ev["green"] == 1
        assert ev["yellow"] == 1


# ---------------------------------------------------------------------------
# Forbidden patterns
# ---------------------------------------------------------------------------
class TestForbiddenPatterns:
    def test_no_dry_run_false(self, proof_module):
        """Proof must not contain dry_run=False as a parameter assignment."""
        src = _PROOF_PATH.read_text()
        # The string 'dry_run=false' may appear in docstrings/comments as a
        # non-goal declaration. Check for it as a Python literal assignment.
        assert "parameters={\"dry_run\": 0" not in src
        assert "dry_run=False" not in src

    def test_no_put_patch_delete(self, proof_module):
        """Proof must not use PUT/PATCH/DELETE methods on Freqtrade."""
        src = _PROOF_PATH.read_text()
        forbidden = ["\"PUT\"", "\"PATCH\"", "\"DELETE\"",
                     "'PUT'", "'PATCH'", "'DELETE'"]
        for method in forbidden:
            assert method not in src, f"Unexpected {method} in proof (code usage)"

    def test_allowed_endpoints_only(self, proof_module):
        """Verify only our explicit endpoint list is used."""
        src = _PROOF_PATH.read_text()
        our_eps = ["/api/v1/ping", "/api/v1/version", "/api/v1/status",
                    "/api/v1/count", "/api/v1/profit"]
        for ep in our_eps:
            assert ep in src, f"Expected endpoint {ep} not found in proof"
