"""Tests for the SI v2 report-only fleet monitoring evaluator."""

from __future__ import annotations

import json
from dataclasses import fields

from si_v2.monitoring.fleet_monitoring import (
    DEFAULT_EXPECTED_BOT_IDS,
    BotMonitoringStatus,
    FleetMonitoringReport,
    MonitoringRecommendation,
    MonitoringVerdict,
    evaluate_bot_monitoring,
    evaluate_fleet_monitoring,
)

GREEN_BOT_INPUTS: tuple[dict[str, object], ...] = (
    {
        "bot_id": "freqtrade-freqforge",
        "heartbeat_ok": True,
        "heartbeat_age_seconds": 30,
        "telemetry_age_seconds": 120,
        "proposal_generation_ok": True,
        "profitability_gate_verdict": "candidate",
        "dynamic_exit_evidence_gate_verdict": "candidate",
        "error_flags": (),
    },
    {
        "bot_id": "freqtrade-regime-hybrid",
        "heartbeat_ok": True,
        "heartbeat_age_seconds": 45,
        "telemetry_age_seconds": 180,
        "proposal_generation_ok": True,
        "profitability_gate_verdict": "candidate",
        "dynamic_exit_evidence_gate_verdict": "candidate",
        "error_flags": (),
    },
    {
        "bot_id": "freqtrade-freqforge-canary",
        "heartbeat_ok": True,
        "heartbeat_age_seconds": 60,
        "telemetry_age_seconds": 90,
        "proposal_generation_ok": True,
        "profitability_gate_verdict": "candidate",
        "dynamic_exit_evidence_gate_verdict": "candidate",
        "error_flags": (),
    },
    {
        "bot_id": "freqai-rebel",
        "heartbeat_ok": True,
        "heartbeat_age_seconds": 15,
        "telemetry_age_seconds": 240,
        "proposal_generation_ok": True,
        "profitability_gate_verdict": "candidate",
        "dynamic_exit_evidence_gate_verdict": "candidate",
        "error_flags": (),
    },
)


def test_all_four_bots_green() -> None:
    report = evaluate_fleet_monitoring(GREEN_BOT_INPUTS)

    assert isinstance(report, FleetMonitoringReport)
    assert report.verdict == MonitoringVerdict.GREEN
    assert report.bot_count == 4
    assert report.green_bot_count == 4
    assert report.yellow_bot_count == 0
    assert report.red_bot_count == 0
    assert report.bot_ids == DEFAULT_EXPECTED_BOT_IDS
    assert report.recommendations == (MonitoringRecommendation.NO_ACTION_RECOMMENDED,)


def test_one_stale_bot_is_yellow() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[1] = {
        **bot_inputs[1],
        "telemetry_age_seconds": 5400,
    }

    report = evaluate_fleet_monitoring(bot_inputs)

    assert report.verdict == MonitoringVerdict.YELLOW
    assert report.yellow_bot_count == 1
    assert any(bot.bot_id == "freqtrade-regime-hybrid" for bot in report.per_bot_statuses)
    assert any(
        MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED in bot.recommendations
        for bot in report.per_bot_statuses
        if bot.bot_id == "freqtrade-regime-hybrid"
    )


def test_hard_stale_bot_is_red() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[2] = {
        **bot_inputs[2],
        "telemetry_age_seconds": 9000,
    }

    report = evaluate_fleet_monitoring(bot_inputs, stale_threshold_seconds=3600, hard_stale_threshold_seconds=7200)

    assert report.verdict == MonitoringVerdict.RED
    assert report.red_bot_count == 1
    assert any("stale_telemetry_hard" in reason for reason in report.reasons)


def test_missing_heartbeat_is_yellow() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[0] = {
        k: v for k, v in bot_inputs[0].items() if k != "heartbeat_ok"
    }

    report = evaluate_fleet_monitoring(bot_inputs)
    bot = report.get_bot("freqtrade-freqforge")

    assert bot.verdict == MonitoringVerdict.YELLOW
    assert "missing_heartbeat" in bot.reasons
    assert MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED in bot.recommendations


def test_missing_gate_evidence_is_yellow() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[3] = {
        k: v for k, v in bot_inputs[3].items() if k != "dynamic_exit_evidence_gate_verdict"
    }

    report = evaluate_fleet_monitoring(bot_inputs)
    bot = report.get_bot("freqai-rebel")

    assert bot.verdict == MonitoringVerdict.YELLOW
    assert "missing_dynamic_exit_evidence_gate" in bot.reasons
    assert report.verdict == MonitoringVerdict.YELLOW


def test_hard_dynamic_exit_gate_block_is_red() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[0] = {
        **bot_inputs[0],
        "dynamic_exit_evidence_gate_verdict": "blocked",
    }

    report = evaluate_fleet_monitoring(bot_inputs)
    bot = report.get_bot("freqtrade-freqforge")

    assert bot.verdict == MonitoringVerdict.RED
    assert "dynamic_exit_evidence_gate_blocked" in bot.reasons
    assert MonitoringRecommendation.MARK_BOT_BLOCKED_RECOMMENDED in bot.recommendations
    assert report.verdict == MonitoringVerdict.RED


def test_hard_profitability_gate_block_is_red() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[1] = {
        **bot_inputs[1],
        "profitability_gate_verdict": "blocked",
    }

    report = evaluate_fleet_monitoring(bot_inputs)
    bot = report.get_bot("freqtrade-regime-hybrid")

    assert bot.verdict == MonitoringVerdict.RED
    assert "profitability_gate_blocked" in bot.reasons
    assert report.verdict == MonitoringVerdict.RED


def test_multiple_stale_or_error_bots_is_red() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs[0] = {
        **bot_inputs[0],
        "telemetry_age_seconds": 5400,
    }
    bot_inputs[1] = {
        **bot_inputs[1],
        "error_flags": ("proposal_generation_failed",),
    }

    report = evaluate_fleet_monitoring(bot_inputs)

    assert report.verdict == MonitoringVerdict.RED
    assert report.yellow_bot_count + report.red_bot_count >= 2


def test_recommendations_are_advisory_only() -> None:
    report = evaluate_fleet_monitoring(GREEN_BOT_INPUTS)

    assert report.recommendations == (MonitoringRecommendation.NO_ACTION_RECOMMENDED,)
    assert all(bot.recommendations for bot in report.per_bot_statuses)
    assert all(isinstance(rec.value, str) for rec in report.recommendations)


def test_no_mutation_counters_exist() -> None:
    report_fields = {field.name for field in fields(FleetMonitoringReport)}
    bot_fields = {field.name for field in fields(BotMonitoringStatus)}

    assert all("mutation" not in name for name in report_fields)
    assert all("mutation" not in name for name in bot_fields)


def test_json_serialization_is_stable() -> None:
    report = evaluate_fleet_monitoring(GREEN_BOT_INPUTS)
    payload = report.to_dict()
    text = json.dumps(payload, sort_keys=True)
    loaded = json.loads(text)

    assert loaded["verdict"] == "green"
    assert len(loaded["per_bot_statuses"]) == 4
    assert loaded["per_bot_statuses"][0]["bot_id"] == "freqtrade-freqforge"


def test_all_expected_bots_are_represented() -> None:
    report = evaluate_fleet_monitoring(GREEN_BOT_INPUTS)
    bot_ids = {bot.bot_id for bot in report.per_bot_statuses}

    assert bot_ids == set(DEFAULT_EXPECTED_BOT_IDS)


def test_unknown_bot_does_not_crash() -> None:
    bot_inputs = list(GREEN_BOT_INPUTS)
    bot_inputs.append(
        {
            "bot_id": "unknown-bot-x",
            "heartbeat_ok": True,
            "telemetry_age_seconds": 90,
            "proposal_generation_ok": True,
            "profitability_gate_verdict": "candidate",
            "dynamic_exit_evidence_gate_verdict": "candidate",
            "error_flags": (),
        }
    )

    report = evaluate_fleet_monitoring(bot_inputs)
    bot = report.get_bot("unknown-bot-x")

    assert bot.bot_id == "unknown-bot-x"
    assert bot.verdict == MonitoringVerdict.YELLOW
    assert "unknown_bot" in bot.reasons


def test_evaluate_bot_monitoring_directly() -> None:
    bot = evaluate_bot_monitoring(
        {
            "bot_id": "freqtrade-freqforge",
            "heartbeat_ok": True,
            "telemetry_age_seconds": 30,
            "proposal_generation_ok": True,
            "profitability_gate_verdict": "candidate",
            "dynamic_exit_evidence_gate_verdict": "candidate",
            "error_flags": (),
        }
    )

    assert bot.verdict == MonitoringVerdict.GREEN
    assert bot.heartbeat_ok is True
    assert bot.telemetry_age_seconds == 30
