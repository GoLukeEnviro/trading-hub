"""Tests for the multi-bot telemetry analyzer.

Tests cover:
- INSUFFICIENT_EVIDENCE when profit/count/status data is missing
- Weakest bot detection with comparable profit metrics
- No division by zero or crash on empty endpoints
- Conservative proposal rules
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANALYZER_PATH = _REPO_ROOT / "self_improvement_v2/src/si_v2/analysis/multi_bot_telemetry_analyzer.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def analyzer_module():
    import importlib.util as iu
    spec = iu.spec_from_file_location("multi_bot_telemetry_analyzer", _ANALYZER_PATH)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
class TestAnalyzerStructure:
    def test_has_analyze_fleet(self, analyzer_module):
        assert callable(analyzer_module.analyze_fleet)

    def test_has_build_bot_summaries(self, analyzer_module):
        assert callable(analyzer_module.build_bot_summaries)

    def test_has_constants(self, analyzer_module):
        assert analyzer_module.ANALYSIS_ONLY_RISK_REVIEW == "ANALYSIS_ONLY_RISK_REVIEW"
        assert analyzer_module.INSUFFICIENT_EVIDENCE == "INSUFFICIENT_EVIDENCE"
        assert analyzer_module.PARAMETER_REVIEW_CANDIDATE == "PARAMETER_REVIEW_CANDIDATE"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_bot_list(self, analyzer_module):
        result = analyzer_module.analyze_fleet([])
        assert result.error == "No bot summaries provided"
        assert result.bots_total == 0

    def test_no_profit_data(self, analyzer_module):
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="bot1", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_telemetry_available=False,
                profit_value=None,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot2", classification="YELLOW",
                endpoints_ok=3, endpoints_total=5,
                profit_telemetry_available=False,
                profit_value=None,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.weakest_bot is None
        assert result.confidence == "LOW"
        assert any("Insufficient profit data" in c for c in result.caveats)

    def test_single_bot_no_comparison(self, analyzer_module):
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="only_bot", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.05,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.weakest_bot is None
        assert result.confidence == "LOW"


# ---------------------------------------------------------------------------
# Weakest bot detection
# ---------------------------------------------------------------------------
class TestWeakestBotDetection:
    def test_identifies_weakest_bot(self, analyzer_module):
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="bot_a", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.10,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot_b", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.12,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot_c", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.02,  # well below median of 0.10
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.weakest_bot == "bot_c"
        assert result.confidence == "MEDIUM"
        assert result.recommendation_type == analyzer_module.PARAMETER_REVIEW_CANDIDATE

    def test_no_weakest_when_similar(self, analyzer_module):
        """When all bots have similar profit, no weakest should be identified."""
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="bot_a", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.10,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot_b", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.11,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.weakest_bot is None
        assert result.confidence == "MEDIUM"

    def test_fleet_summary_counts(self, analyzer_module):
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="green1", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.10,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="yellow1", classification="YELLOW",
                endpoints_ok=2, endpoints_total=5,
                profit_value=0.08,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="red1", classification="RED",
                endpoints_ok=0, endpoints_total=5,
                profit_value=0.0,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.bots_total == 3
        assert result.bots_green == 1
        assert result.bots_yellow == 1
        assert result.bots_red == 1
        assert result.endpoints_ok == 7
        assert result.endpoints_failed == 8


# ---------------------------------------------------------------------------
# Conservative proposal rules
# ---------------------------------------------------------------------------
class TestProposalRules:
    def test_build_bot_summaries_empty(self, analyzer_module):
        results = analyzer_module.build_bot_summaries([])
        assert results == []

    def test_build_bot_summaries_dummy_object(self, analyzer_module):
        """Test with simple objects using response_json."""
        class DummyBot:
            def __init__(self):
                self.bot_id = "test_bot"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/ping": {"ok": True, "status_code": 200},
                    "/api/v1/profit": {"ok": True, "status_code": 200,
                                        "response_json": {"profit_all_ratio": 0.05}},
                }

        results = analyzer_module.build_bot_summaries([DummyBot()])
        assert len(results) == 1
        assert results[0].bot_id == "test_bot"
        assert results[0].endpoints_ok == 2
        assert results[0].endpoints_total == 2
        assert results[0].profit_value == 0.05
        assert results[0].profit_telemetry_available is True

    def test_build_bot_summaries_negative_profit(self, analyzer_module):
        """Negative profit values must be preserved."""
        class DummyBot:
            def __init__(self):
                self.bot_id = "neg_bot"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/profit": {"ok": True, "response_json": {"profit_all_ratio": -0.05}},
                }

        results = analyzer_module.build_bot_summaries([DummyBot()])
        assert results[0].profit_value == -0.05

    def test_build_bot_summaries_missing_profit_field(self, analyzer_module):
        """When profit JSON lacks known fields, profit_value must be None."""
        class DummyBot:
            def __init__(self):
                self.bot_id = "no_profit"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/profit": {"ok": True, "response_json": {"other_field": 42}},
                }

        results = analyzer_module.build_bot_summaries([DummyBot()])
        assert results[0].profit_value is None
        assert results[0].profit_telemetry_available is False

    def test_build_bot_summaries_no_response_json(self, analyzer_module):
        """When response_json is None, profit_value must be None."""
        class DummyBot:
            def __init__(self):
                self.bot_id = "no_json"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/profit": {"ok": True, "response_json": None},
                }

        results = analyzer_module.build_bot_summaries([DummyBot()])
        assert results[0].profit_value is None

    def test_build_bot_summaries_count_from_json(self, analyzer_module):
        """Count must be parsed from response_json."""
        class DummyBot:
            def __init__(self):
                self.bot_id = "count_bot"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/count": {"ok": True, "response_json": {"current": 7}},
                }

        results = analyzer_module.build_bot_summaries([DummyBot()])
        assert results[0].count_open_trades == 7

    def test_weakest_bot_via_build_bot_summaries(self, analyzer_module):
        """Test weakest-bot detection using build_bot_summaries output."""
        class BotA:
            def __init__(self):
                self.bot_id = "bot_a"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/ping": {"ok": True},
                    "/api/v1/profit": {"ok": True, "response_json": {"profit_all_ratio": 0.10}},
                    "/api/v1/count": {"ok": True, "response_json": {"current": 3}},
                    "/api/v1/status": {"ok": True},
                    "/api/v1/version": {"ok": True},
                }

        class BotB:
            def __init__(self):
                self.bot_id = "bot_b"
                self.classification = "GREEN"
                self.endpoints = {
                    "/api/v1/ping": {"ok": True},
                    "/api/v1/profit": {"ok": True, "response_json": {"profit_all_ratio": 0.02}},
                    "/api/v1/count": {"ok": True, "response_json": {"current": 1}},
                    "/api/v1/status": {"ok": True},
                    "/api/v1/version": {"ok": True},
                }

        summaries = analyzer_module.build_bot_summaries([BotA(), BotB()])
        assert len(summaries) == 2
        assert summaries[0].profit_value == 0.10
        assert summaries[1].profit_value == 0.02

        result = analyzer_module.analyze_fleet(summaries)
        assert result.weakest_bot == "bot_b"
        assert result.confidence == "MEDIUM"
        assert result.recommendation_type == analyzer_module.PARAMETER_REVIEW_CANDIDATE

    def test_analysis_is_analysis_only(self, analyzer_module):
        """Analysis type must never be an execute/apply type."""
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="bot", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.05,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot2", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.15,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert result.analysis_type == "ANALYSIS_ONLY_RISK_REVIEW"
        assert result.recommendation_type in ("ANALYSIS_ONLY", "PARAMETER_REVIEW_CANDIDATE")

    def test_validation_required_present(self, analyzer_module):
        """Analysis must include validation requirements."""
        summaries = [
            analyzer_module.BotEndpointSummary(
                bot_id="bot_a", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.05,
            ),
            analyzer_module.BotEndpointSummary(
                bot_id="bot_b", classification="GREEN",
                endpoints_ok=5, endpoints_total=5,
                profit_value=0.15,
            ),
        ]
        result = analyzer_module.analyze_fleet(summaries)
        assert len(result.validation_required) >= 1


# ---------------------------------------------------------------------------
# Forbidden patterns
# ---------------------------------------------------------------------------
class TestForbiddenPatterns:
    def test_no_any_in_analyzer(self, analyzer_module):
        src = _ANALYZER_PATH.read_text()
        _any_str = "ty" + "ping"
        assert "from " + _any_str + " import Any" not in src

    def test_no_forbidden_endpoints(self, analyzer_module):
        src = _ANALYZER_PATH.read_text()
        assert "PUT" not in src
        assert "PATCH" not in src
        assert "DELETE" not in src
