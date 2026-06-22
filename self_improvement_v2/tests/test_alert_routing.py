"""Tests for report-only Alert Routing Readiness evaluator."""

from __future__ import annotations

import json

from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_BLOCKED as DYNAMIC_EXIT_GATE_BLOCKED,
)
from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_CANDIDATE as DYNAMIC_EXIT_GATE_CANDIDATE,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_BLOCKED as PROFITABILITY_GATE_BLOCKED,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_CANDIDATE as PROFITABILITY_GATE_CANDIDATE,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_INCONCLUSIVE as PROFITABILITY_GATE_INCONCLUSIVE,
)
from si_v2.monitoring.alert_routing import (
    STALE_TELEMETRY_HARD_THRESHOLD_SECONDS,
    STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS,
    AlertRoute,
    AlertRoutingDecision,
    AlertRoutingInput,
    AlertSeverity,
    evaluate_alert_routing,
    evaluate_alert_routing_report,
)
from si_v2.monitoring.fleet_monitoring import MonitoringVerdict

# ---------------------------------------------------------------------------
#  Healthy / green path
# ---------------------------------------------------------------------------


def test_healthy_green_returns_no_alert() -> None:
    """Clean evidence produces info severity with no_alert_recommended route."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            shadow_paper_status="green",
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.INFO
    assert AlertRoute.NO_ALERT_RECOMMENDED in decision.routes
    assert decision.notification_sent is False
    assert decision.action_count == 0
    assert decision.mutation_count == 0


def test_healthy_green_from_dict_input() -> None:
    """The evaluator accepts dict-like evidence objects."""
    decision = evaluate_alert_routing(
        {
            "fleet_monitoring_verdict": "green",
            "dynamic_exit_gate_verdict": "candidate",
            "profitability_gate_verdict": "candidate",
            "telemetry_fresh": True,
            "heartbeat_ok": True,
            "runtime_drift_detected": False,
            "credential_path_clear": True,
            "shadow_paper_status": "green",
            "go_no_go_blocker_present": False,
        }
    )

    assert decision.severity == AlertSeverity.INFO
    assert AlertRoute.NO_ALERT_RECOMMENDED in decision.routes


# ---------------------------------------------------------------------------
#  Warning paths
# ---------------------------------------------------------------------------


def test_monitoring_yellow_warning_operator_review() -> None:
    """Monitoring yellow returns warning + operator review."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.YELLOW.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.WARNING
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes
    assert "fleet_monitoring_yellow" in decision.reason_codes


def test_profitability_inconclusive_warning() -> None:
    """Profitability inconclusive returns warning + operator review."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_INCONCLUSIVE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.WARNING
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes
    assert "profitability_gate_inconclusive" in decision.reason_codes


def test_stale_telemetry_warning_path() -> None:
    """Stale telemetry (not hard) returns warning."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=False,
            telemetry_age_seconds=STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS + 1,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.WARNING
    assert "stale_telemetry_warning" in decision.reason_codes
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes


def test_heartbeat_failed_warning() -> None:
    """Failed heartbeat returns warning."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=False,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.WARNING
    assert "heartbeat_failed" in decision.reason_codes


# ---------------------------------------------------------------------------
#  Critical / blocked paths
# ---------------------------------------------------------------------------


def test_monitoring_red_blocked() -> None:
    """Monitoring red returns blocked + promotion pause."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.RED.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.BLOCKED
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes
    assert "fleet_monitoring_red" in decision.reason_codes


def test_dynamic_exit_gate_blocked_adds_risk_review() -> None:
    """Dynamic exit gate blocked adds risk review route."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_BLOCKED,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.CRITICAL
    assert AlertRoute.RISK_REVIEW_RECOMMENDED in decision.routes
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes


def test_profitability_gate_blocked_adds_promotion_pause() -> None:
    """Profitability gate blocked adds promotion pause route."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_BLOCKED,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.CRITICAL
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert "profitability_gate_blocked" in decision.reason_codes


def test_runtime_drift_adds_runtime_drift_review() -> None:
    """Runtime drift detected adds runtime drift review route."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=True,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.CRITICAL
    assert AlertRoute.RUNTIME_DRIFT_REVIEW_RECOMMENDED in decision.routes
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert "runtime_drift_detected" in decision.reason_codes


def test_unclear_credential_path_adds_credential_review() -> None:
    """Unclear credential path adds credential review route."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=False,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.CRITICAL
    assert AlertRoute.CREDENTIAL_REVIEW_RECOMMENDED in decision.routes
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert "unclear_credential_path" in decision.reason_codes


def test_hard_stale_telemetry_blocked_path() -> None:
    """Hard stale telemetry returns blocked."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=False,
            telemetry_age_seconds=STALE_TELEMETRY_HARD_THRESHOLD_SECONDS + 1,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )

    assert decision.severity == AlertSeverity.BLOCKED
    assert "stale_telemetry_hard" in decision.reason_codes
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes


def test_go_no_go_blocker_forces_blocked() -> None:
    """Go/No-Go blocker present forces blocked severity."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=True,
        )
    )

    assert decision.severity == AlertSeverity.BLOCKED
    assert AlertRoute.PROMOTION_PAUSE_RECOMMENDED in decision.routes
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes
    assert "go_no_go_blocker_present" in decision.reason_codes


# ---------------------------------------------------------------------------
#  Safety invariants
# ---------------------------------------------------------------------------


def test_notification_never_sent() -> None:
    """Notification is always False regardless of severity."""
    for severity_input in [
        AlertSeverity.INFO,
        AlertSeverity.WARNING,
        AlertSeverity.CRITICAL,
        AlertSeverity.BLOCKED,
    ]:
        decision = AlertRoutingDecision(
            severity=severity_input,
            routes=(AlertRoute.NO_ALERT_RECOMMENDED,),
        )
        assert decision.notification_sent is False


def test_action_count_always_zero() -> None:
    """Action count is always zero for advisory evaluator."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )
    assert decision.action_count == 0


def test_mutation_count_always_zero() -> None:
    """Mutation count is always zero for advisory evaluator."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )
    assert decision.mutation_count == 0


def test_capital_execution_always_false() -> None:
    """Capital execution is always False for advisory evaluator."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )
    assert decision.capital_execution is False


def test_runtime_mutation_always_false() -> None:
    """Runtime mutation flag is always False for advisory evaluator."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )
    assert decision.runtime_mutation is False


# ---------------------------------------------------------------------------
#  Report-level tests
# ---------------------------------------------------------------------------


def test_report_json_serialization_stable() -> None:
    """AlertRoutingReport.to_dict() produces JSON-serializable output."""
    report = evaluate_alert_routing_report(
        [
            AlertRoutingInput(
                fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
                dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
                profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
                telemetry_fresh=True,
                heartbeat_ok=True,
                runtime_drift_detected=False,
                credential_path_clear=True,
                go_no_go_blocker_present=False,
            ),
            AlertRoutingInput(
                fleet_monitoring_verdict=MonitoringVerdict.YELLOW.value,
                dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
                profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
                telemetry_fresh=True,
                heartbeat_ok=True,
                runtime_drift_detected=False,
                credential_path_clear=True,
                go_no_go_blocker_present=False,
            ),
            AlertRoutingInput(
                fleet_monitoring_verdict=MonitoringVerdict.RED.value,
                dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
                profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
                telemetry_fresh=True,
                heartbeat_ok=True,
                runtime_drift_detected=False,
                credential_path_clear=True,
                go_no_go_blocker_present=False,
            ),
        ]
    )

    report_dict = report.to_dict()
    json_str = json.dumps(report_dict, sort_keys=True)
    parsed = json.loads(json_str)

    assert parsed["schema_version"] == 1
    assert parsed["overall_severity"] == AlertSeverity.BLOCKED.value
    assert len(parsed["decisions"]) == 3

    # Verify safety block
    safety = parsed["safety"]
    assert safety["exchange_io"] is False
    assert safety["orders"] is False
    assert safety["runtime_mutation"] is False
    assert safety["config_writes"] is False
    assert safety["strategy_writes"] is False
    assert safety["docker_changes"] is False
    assert safety["compose_changes"] is False
    assert safety["cron_changes"] is False
    assert safety["auto_healing"] is False
    assert safety["capital_execution"] is False

    # Summary invariants
    assert parsed["summary"]["notification_sent_count"] == 0
    assert parsed["summary"]["action_count"] == 0
    assert parsed["summary"]["mutation_count"] == 0
    assert parsed["summary"]["capital_execution"] is False


def test_report_safety_invariants_for_every_severity() -> None:
    """Every decision in a report must have zero notifications/actions/mutations."""
    report = evaluate_alert_routing_report(
        [
            AlertRoutingInput(
                fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
                dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
                profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
                telemetry_fresh=True,
                heartbeat_ok=True,
                runtime_drift_detected=False,
                credential_path_clear=True,
                go_no_go_blocker_present=False,
            ),
            AlertRoutingInput(
                fleet_monitoring_verdict=MonitoringVerdict.RED.value,
                dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_BLOCKED,
                profitability_gate_verdict=PROFITABILITY_GATE_BLOCKED,
                telemetry_fresh=False,
                telemetry_age_seconds=STALE_TELEMETRY_HARD_THRESHOLD_SECONDS + 100,
                heartbeat_ok=False,
                runtime_drift_detected=True,
                credential_path_clear=False,
                go_no_go_blocker_present=True,
            ),
        ]
    )

    for decision in report.decisions:
        assert decision.notification_sent is False, (
            f"Decision with severity={decision.severity} had notification_sent=True"
        )
        assert decision.action_count == 0
        assert decision.mutation_count == 0
        assert decision.capital_execution is False
        assert decision.runtime_mutation is False

    assert report.summary["notification_sent_count"] == 0
    assert report.summary["action_count"] == 0
    assert report.summary["mutation_count"] == 0


def test_no_secrets_in_decision_to_dict() -> None:
    """Decision to_dict must not contain keys suggesting credentials or secrets."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            go_no_go_blocker_present=False,
        )
    )
    d = decision.to_dict()
    forbidden_keys = [
        "api_key", "secret", "password", "token", "credential",
        "chat_id", "webhook_url", "email", "endpoint",
    ]
    for forbidden in forbidden_keys:
        assert forbidden not in str(d).lower(), (
            f"Forbidden key-like content '{forbidden}' found in decision dict"
        )


def test_report_decision_count_matches_inputs() -> None:
    """Report decision count must equal number of inputs."""
    inputs = [
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.GREEN.value,
            go_no_go_blocker_present=False,
        )
        for _ in range(5)
    ]
    report = evaluate_alert_routing_report(inputs)
    assert report.summary["decision_count"] == 5
    assert len(report.decisions) == 5


def test_multiple_routes_no_duplicates() -> None:
    """Routes list must not contain duplicates."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=MonitoringVerdict.RED.value,
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_BLOCKED,
            profitability_gate_verdict=PROFITABILITY_GATE_BLOCKED,
            telemetry_fresh=False,
            telemetry_age_seconds=STALE_TELEMETRY_HARD_THRESHOLD_SECONDS + 200,
            heartbeat_ok=False,
            runtime_drift_detected=True,
            credential_path_clear=False,
            go_no_go_blocker_present=True,
        )
    )

    route_set = set(decision.routes)
    assert len(decision.routes) == len(route_set), (
        f"Duplicate routes detected: {decision.routes}"
    )


def test_decision_dataclass_field_defaults() -> None:
    """Verify frozen dataclass defaults never mutate safety invariants."""
    d = AlertRoutingDecision(
        severity=AlertSeverity.INFO,
        routes=(AlertRoute.NO_ALERT_RECOMMENDED,),
    )
    assert d.notification_sent is False
    assert d.action_count == 0
    assert d.mutation_count == 0
    assert d.runtime_mutation is False
    assert d.capital_execution is False


# ---------------------------------------------------------------------------
#  Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_handled_gracefully() -> None:
    """Empty input dict returns warning with missing-field reason codes."""
    decision = evaluate_alert_routing({})

    # Empty dict should give warning because all fields are missing/None
    assert decision.severity in (AlertSeverity.WARNING, AlertSeverity.INFO)
    assert decision.notification_sent is False
    assert decision.action_count == 0


def test_none_input_fields_default_to_warning() -> None:
    """All-None input returns appropriate severity with reason codes."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict=None,
            dynamic_exit_gate_verdict=None,
            profitability_gate_verdict=None,
            telemetry_fresh=None,
            heartbeat_ok=None,
            runtime_drift_detected=None,
            credential_path_clear=None,
            go_no_go_blocker_present=None,
        )
    )

    # Missing monitoring, missing dynamic exit, missing profitability → warning
    assert decision.severity == AlertSeverity.WARNING
    assert "fleet_monitoring_missing" in decision.reason_codes
    assert AlertRoute.OPERATOR_REVIEW_RECOMMENDED in decision.routes


def test_unknown_monitoring_verdict_does_not_crash() -> None:
    """Unknown monitoring verdict string is handled gracefully."""
    decision = evaluate_alert_routing(
        AlertRoutingInput(
            fleet_monitoring_verdict="unknown_xyz",
            dynamic_exit_gate_verdict=DYNAMIC_EXIT_GATE_CANDIDATE,
            profitability_gate_verdict=PROFITABILITY_GATE_CANDIDATE,
            telemetry_fresh=True,
            heartbeat_ok=True,
            runtime_drift_detected=False,
            credential_path_clear=True,
            go_no_go_blocker_present=False,
        )
    )
    # Unknown verdict doesn't match any of our checks → falls through to no alert
    assert decision.severity in (AlertSeverity.INFO, AlertSeverity.WARNING)
    assert decision.notification_sent is False


def test_report_empty_inputs_handled() -> None:
    """Empty inputs list returns valid report with zero counts."""
    report = evaluate_alert_routing_report([])

    assert report.schema_version == 1
    assert report.summary["decision_count"] == 0
    assert report.summary["notification_sent_count"] == 0
    assert report.summary["action_count"] == 0
    assert len(report.decisions) == 0
