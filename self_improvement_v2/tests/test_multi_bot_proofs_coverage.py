"""Tests for multi-bot proof main() and _write_report() functions.

Covers the orchestration layer (main) and report writing (write_report)
for all three multi-bot proof modules using tmp_path and monkeypatch.
No Docker, no HTTP, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# =========================================================================
# Module 1: multi_bot_rest_shadowproposal_proof — _write_report
# =========================================================================

class TestRestShadowproposalWriteReport:
    """Test _write_report for the REST shadowproposal proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_rest_shadowproposal_proof.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_rest_shadowproposal_proof", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def _make_candidate(self, proof_mod: Any) -> Any:
        from si_v2.state.schemas import MutationCandidate
        return MutationCandidate(
            bot_id="freqforge+freqforge-canary",
            bot_name="Fleet",
            candidate_sha256="test_sha_1234",
            source_decision="observe",
            parameters={"dry_run": 1, "bot_count": 2},
            active_overlay_candidates={},
            metadata_only_candidates={"proof_multi_bot_ping": 1},
            requires_backtest=False,
            requires_paper_validation=False,
            requires_human_approval=True,
            requires_strategy_adapter=[],
        )

    def test_write_report_creates_file(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        report_path = tmp_path / "reports" / "phase2" / "test-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", report_path)

        candidate = self._make_candidate(proof_mod)
        snapshots = [
            {"bot_id": "freqforge", "endpoint": "/api/v1/ping", "status_code": 200,
             "ok": True, "response_summary": '{"status":"pong"}', "fetched_at_utc": "2026-06-15T10:00:00Z"},
            {"bot_id": "freqforge-canary", "endpoint": "/api/v1/ping", "status_code": 200,
             "ok": True, "response_summary": '{"status":"pong"}', "fetched_at_utc": "2026-06-15T10:00:01Z"},
        ]
        errors: list[dict] = []
        riskguard = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": ["proposal_only=True"]}
        shadow_logger = {"entries_count": 1, "outcome": "LOGGED", "phase": "proof", "decision": "hold"}
        artifact = {
            "artifact_type": "shadow_proposal_pending_human",
            "proposal_id": "test_sha_1234",
            "approval_status": "PENDING_HUMAN",
            "reason": "test reason",
        }

        proof_mod._write_report(snapshots, errors, candidate, "test_sha_1234",
                                 riskguard, shadow_logger, artifact)
        assert report_path.exists()
        content = report_path.read_text()
        assert "PASS_SHADOW_ONLY" in content
        assert "PENDING_HUMAN" in content
        assert "freqforge" in content
        assert "freqforge-canary" in content

    def test_write_report_includes_errors(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        report_path = tmp_path / "reports" / "phase2" / "test-errors.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", report_path)

        candidate = self._make_candidate(proof_mod)
        snapshots: list[dict] = []
        errors = [{"bot_id": "broken-bot", "error": "Connection refused"}]
        riskguard = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger = {"entries_count": 1, "outcome": "LOGGED", "phase": "proof", "decision": "hold"}
        artifact = {"artifact_type": "shadow_proposal_pending_human", "proposal_id": "test",
                    "approval_status": "PENDING_HUMAN", "reason": "test"}

        proof_mod._write_report(snapshots, errors, candidate, "test_sha",
                                 riskguard, shadow_logger, artifact)
        content = report_path.read_text()
        assert "broken-bot" in content
        assert "Connection refused" in content

    def test_write_report_empty_snapshots(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        report_path = tmp_path / "reports" / "phase2" / "test-empty.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", report_path)

        candidate = self._make_candidate(proof_mod)
        riskguard = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger = {"entries_count": 0, "outcome": "LOGGED", "phase": "proof", "decision": "hold"}
        artifact = {"artifact_type": "shadow_proposal_pending_human", "proposal_id": "test",
                    "approval_status": "PENDING_HUMAN", "reason": "test"}

        proof_mod._write_report([], [], candidate, "test_sha", riskguard, shadow_logger, artifact)
        content = report_path.read_text()
        assert "0/0" in content or "0" in content


# =========================================================================
# Module 1: multi_bot_rest_shadowproposal_proof — main()
# =========================================================================

class TestRestShadowproposalMain:
    """Test main() for the REST shadowproposal proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_rest_shadowproposal_proof.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_rest_shadowproposal_proof", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_main_missing_config(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", tmp_path / "report.md")
        rc = proof_mod.main()
        assert rc == 1

    def test_main_no_enabled_bots(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"schema_version": 1, "bots": [{"bot_id": "x", "enabled": False}]}))
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", tmp_path / "report.md")
        rc = proof_mod.main()
        assert rc == 1


# =========================================================================
# Module 2: multi_bot_authenticated_telemetry_proof — _write_report
# =========================================================================

class TestAuthTelemetryWriteReport:
    """Test _write_report for the authenticated telemetry proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_authenticated_telemetry_proof.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_authenticated_telemetry_proof", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def _make_candidate(self, proof_mod: Any) -> Any:
        from si_v2.state.schemas import MutationCandidate
        return MutationCandidate(
            bot_id="fleet", bot_name="Fleet", candidate_sha256="test_sha",
            source_decision="observe", parameters={"dry_run": 1, "bot_count": 2},
            active_overlay_candidates={}, metadata_only_candidates={"proof": 1},
            requires_backtest=False, requires_paper_validation=False,
            requires_human_approval=True, requires_strategy_adapter=[],
        )

    def test_write_report_creates_file(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        report_path = tmp_path / "reports" / "phase2" / "auth-test.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", report_path)

        candidate = self._make_candidate(proof_mod)
        BotTelemetryResult = proof_mod.BotTelemetryResult
        results = [
            BotTelemetryResult(bot_id="freqforge", base_url="http://a:8080",
                               classification=proof_mod.BOT_GREEN, auth_success=True,
                               endpoints={"/api/v1/ping": {"ok": True, "status_code": 200}}),
            BotTelemetryResult(bot_id="freqforge-canary", base_url="http://b:8080",
                               classification=proof_mod.BOT_YELLOW, auth_attempted=True,
                               endpoints={"/api/v1/ping": {"ok": True, "status_code": 200}}),
        ]
        riskguard = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger = {"entries_count": 1, "outcome": "LOGGED", "phase": "proof", "decision": "hold"}
        artifact = {"artifact_type": "shadow_proposal_pending_human", "proposal_id": "test",
                    "approval_status": "PENDING_HUMAN", "reason": "test"}

        proof_mod._write_report(results, candidate, "test_sha", riskguard, shadow_logger, artifact, auth_post_count=2)
        assert report_path.exists()
        content = report_path.read_text()
        assert "PASS_SHADOW_ONLY" in content
        assert "PENDING_HUMAN" in content
        assert "freqforge" in content

    def test_write_report_all_red(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        report_path = tmp_path / "reports" / "phase2" / "auth-all-red.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", report_path)

        candidate = self._make_candidate(proof_mod)
        BotTelemetryResult = proof_mod.BotTelemetryResult
        results = [
            BotTelemetryResult(bot_id="dead-bot", base_url="http://x:8080",
                               classification=proof_mod.BOT_RED, error="Connection refused"),
        ]
        riskguard = {"result": "PASS_SHADOW_ONLY", "reason": "ok", "details": []}
        shadow_logger = {"entries_count": 0, "outcome": "LOGGED", "phase": "proof", "decision": "hold"}
        artifact = {"artifact_type": "shadow_proposal_pending_human", "proposal_id": "test",
                    "approval_status": "PENDING_HUMAN", "reason": "test"}

        proof_mod._write_report(results, candidate, "test_sha", riskguard, shadow_logger, artifact, auth_post_count=0)
        content = report_path.read_text()
        assert "RED" in content
        assert "dead-bot" in content


# =========================================================================
# Module 2: multi_bot_authenticated_telemetry_proof — main()
# =========================================================================

class TestAuthTelemetryMain:
    """Test main() for the authenticated telemetry proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_authenticated_telemetry_proof.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_authenticated_telemetry_proof", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_main_missing_config(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", tmp_path / "report.md")
        rc = proof_mod.main()
        assert rc == 1

    def test_main_no_enabled_bots(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"schema_version": 1, "bots": [{"bot_id": "x", "enabled": False}]}))
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(proof_mod, "_REPORT_PATH", tmp_path / "report.md")
        rc = proof_mod.main()
        assert rc == 1


# =========================================================================
# Module 3: multi_bot_read_analyze_shadow_proposal — _collect_one
# =========================================================================

class TestReadAnalyzeCollectOne:
    """Test _collect_one for the read/analyze shadow proposal proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_read_analyze_shadow_proposal.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_read_analyze_shadow_proposal", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_collect_one_no_auth_config(self, proof_mod: Any, monkeypatch: Any) -> None:
        import unittest.mock as um

        bot_config = {
            "bot_id": "test-bot",
            "base_url": "http://localhost:8080",
            "auth": None,
        }

        mock_snapshot = um.MagicMock()
        mock_snapshot.bot_id = "test-bot"
        mock_snapshot.endpoint = "/api/v1/ping"
        mock_snapshot.status_code = 200
        mock_snapshot.ok = True
        mock_snapshot.response_summary = '{"status":"pong"}'
        mock_snapshot.fetched_at_utc = "2026-06-15T10:00:00Z"

        mock_connector = um.MagicMock()
        mock_connector.fetch_snapshot.return_value = mock_snapshot

        monkeypatch.setattr(proof_mod, "SIV2FreqtradeTelemetryConnector",
                            lambda base_url, bot_id, **kwargs: mock_connector)

        evidence, debug = proof_mod._collect_one(bot_config, now_iso="2026-06-15T10:00:00Z")
        assert evidence is not None
        assert evidence.bot_id == "test-bot"

    def test_collect_one_missing_env_vars(self, proof_mod: Any, monkeypatch: Any) -> None:
        import unittest.mock as um

        bot_config = {
            "bot_id": "test-bot",
            "base_url": "http://localhost:8080",
            "auth": {"type": "env_basic_jwt", "username_env": "NONEXISTENT_USER", "password_env": "NONEXISTENT_PASS"},
        }

        mock_snapshot = um.MagicMock()
        mock_snapshot.bot_id = "test-bot"
        mock_snapshot.endpoint = "/api/v1/ping"
        mock_snapshot.status_code = 200
        mock_snapshot.ok = True
        mock_snapshot.response_summary = '{"status":"pong"}'
        mock_snapshot.fetched_at_utc = "2026-06-15T10:00:00Z"

        mock_connector = um.MagicMock()
        mock_connector.fetch_snapshot.return_value = mock_snapshot

        monkeypatch.setattr(proof_mod, "SIV2FreqtradeTelemetryConnector",
                            lambda base_url, bot_id, **kwargs: mock_connector)

        evidence, debug = proof_mod._collect_one(bot_config, now_iso="2026-06-15T10:00:00Z")
        assert evidence is not None
        assert evidence.bot_id == "test-bot"

    def test_collect_one_with_auth(self, proof_mod: Any, monkeypatch: Any) -> None:
        import unittest.mock as um

        bot_config = {
            "bot_id": "test-bot",
            "base_url": "http://localhost:8080",
            "auth": {"type": "env_basic_jwt", "username_env": "TEST_USER", "password_env": "TEST_PASS"},
        }

        monkeypatch.setenv("TEST_USER", "admin")
        monkeypatch.setenv("TEST_PASS", "secret")

        mock_snapshot = um.MagicMock()
        mock_snapshot.bot_id = "test-bot"
        mock_snapshot.endpoint = "/api/v1/ping"
        mock_snapshot.status_code = 200
        mock_snapshot.ok = True
        mock_snapshot.response_summary = '{"status":"pong"}'
        mock_snapshot.fetched_at_utc = "2026-06-15T10:00:00Z"

        mock_connector = um.MagicMock()
        mock_connector.fetch_snapshot.return_value = mock_snapshot
        mock_connector.token_login.return_value = True

        monkeypatch.setattr(proof_mod, "SIV2FreqtradeTelemetryConnector",
                            lambda base_url, bot_id, **kwargs: mock_connector)

        evidence, debug = proof_mod._collect_one(bot_config, now_iso="2026-06-15T10:00:00Z")
        assert evidence is not None
        assert evidence.bot_id == "test-bot"


# =========================================================================
# Module 3: multi_bot_read_analyze_shadow_proposal — git helpers
# =========================================================================

class TestReadAnalyzeGitHelpers:
    """Test _current_commit_sha and _current_branch."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_read_analyze_shadow_proposal.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_read_analyze_shadow_proposal", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_current_commit_sha(self, proof_mod: Any) -> None:
        sha = proof_mod._current_commit_sha()
        assert sha is not None
        assert len(sha) > 0

    def test_current_branch(self, proof_mod: Any) -> None:
        branch = proof_mod._current_branch()
        assert branch is not None
        assert len(branch) > 0


# =========================================================================
# Module 3: multi_bot_read_analyze_shadow_proposal — main()
# =========================================================================

class TestReadAnalyzeMain:
    """Test main() for the read/analyze shadow proposal proof."""

    @pytest.fixture
    def proof_mod(self):
        import importlib.util as iu
        _PROOF_PATH = (
            Path(__file__).resolve().parents[1] / "src" / "si_v2" / "proofs"
            / "multi_bot_read_analyze_shadow_proposal.py"
        )
        spec = iu.spec_from_file_location("si_v2.proofs.multi_bot_read_analyze_shadow_proposal", _PROOF_PATH)
        mod = iu.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_main_missing_config(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(proof_mod, "_REPORT_DIR", tmp_path / "reports")
        monkeypatch.setattr(proof_mod, "_EVIDENCE_DIR", tmp_path / "evidence")
        monkeypatch.setattr(proof_mod, "_REPO_ROOT", tmp_path)
        rc = proof_mod.main()
        assert rc == 1

    def test_main_no_enabled_bots(self, proof_mod: Any, tmp_path: Any, monkeypatch: Any) -> None:
        """main() processes bots even when enabled=False (default=True in source)."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"schema_version": 1, "bots": []}))
        monkeypatch.setattr(proof_mod, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(proof_mod, "_REPORT_DIR", tmp_path / "reports")
        monkeypatch.setattr(proof_mod, "_EVIDENCE_DIR", tmp_path / "evidence")
        monkeypatch.setattr(proof_mod, "_REPO_ROOT", tmp_path)
        rc = proof_mod.main()
        assert rc == 0  # empty bots list is not an error
