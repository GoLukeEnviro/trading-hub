"""SI v2 report-only alert routing readiness evaluator.

This module determines *what alert would be recommended* based on
evidence-like inputs. It is intentionally pure and advisory-only:
no notification is sent, no external endpoint is called, no runtime
mutation, and no live-trading side effects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_BLOCKED as DYNAMIC_EXIT_GATE_BLOCKED,
)
from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_INCONCLUSIVE as DYNAMIC_EXIT_GATE_INCONCLUSIVE,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_BLOCKED as PROFITABILITY_GATE_BLOCKED,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_INCONCLUSIVE as PROFITABILITY_GATE_INCONCLUSIVE,
)
from si_v2.monitoring.fleet_monitoring import MonitoringVerdict

STALE_TELEMETRY_HARD_THRESHOLD_SECONDS: Final[int] = 7200
STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS: Final[int] = 3600


class AlertSeverity(StrEnum):
    """Severity levels for alert routing recommendations."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKED = "blocked"


class AlertRoute(StrEnum):
    """Advisory-only route labels.

    These are recommendation labels only. No notification is sent,
    no external endpoint is called, no runtime action is performed.
    """

    OPERATOR_REVIEW_RECOMMENDED = "operator_review_recommended"
    PROMOTION_PAUSE_RECOMMENDED = "promotion_pause_recommended"
    RISK_REVIEW_RECOMMENDED = "risk_review_recommended"
    RUNTIME_DRIFT_REVIEW_RECOMMENDED = "runtime_drift_review_recommended"
    CREDENTIAL_REVIEW_RECOMMENDED = "credential_review_recommended"
    NO_ALERT_RECOMMENDED = "no_alert_recommended"


@dataclass(frozen=True, slots=True)
class AlertRoutingInput:
    """Normalized alert routing input evidence."""

    fleet_monitoring_verdict: str | None = None
    dynamic_exit_gate_verdict: str | None = None
    profitability_gate_verdict: str | None = None
    telemetry_fresh: bool | None = None
    telemetry_age_seconds: int | None = None
    heartbeat_ok: bool | None = None
    runtime_drift_detected: bool | None = None
    credential_path_clear: bool | None = None
    shadow_paper_status: str | None = None
    go_no_go_blocker_present: bool | None = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertRoutingDecision:
    """Deterministic alert routing decision for a single input.

    All fields are advisory-only. notification_sent is always False
    and action_count/mutation_count are always 0.
    """

    severity: AlertSeverity
    routes: tuple[AlertRoute, ...] = ()
    reason_codes: tuple[str, ...] = ()

    # Safety invariants — always zero/false for advisory evaluator
    notification_sent: bool = False
    action_count: int = 0
    mutation_count: int = 0
    runtime_mutation: bool = False
    capital_execution: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dictionary representation."""
        return {
            "severity": self.severity.value,
            "routes": [route.value for route in self.routes],
            "reason_codes": list(self.reason_codes),
            "notification_sent": self.notification_sent,
            "action_count": self.action_count,
            "mutation_count": self.mutation_count,
            "runtime_mutation": self.runtime_mutation,
            "capital_execution": self.capital_execution,
        }


@dataclass(frozen=True, slots=True)
class AlertRoutingReport:
    """Fleet-level report-only alert routing evaluation.

    Aggregates multiple routing decisions and ensures no notification
    or runtime mutation occurred.
    """

    schema_version: int = 1
    overall_severity: AlertSeverity = AlertSeverity.INFO
    decisions: tuple[AlertRoutingDecision, ...] = ()
    summary: dict[str, object] = field(default_factory=dict)
    safety: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "overall_severity": self.overall_severity.value,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "summary": self.summary,
            "safety": self.safety,
        }


# ---------------------------------------------------------------------------
#  Input normalization helpers
# ---------------------------------------------------------------------------


def _get_value(source: object, key: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _as_bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _as_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        items: list[str] = []
        for item in value:
            if isinstance(item, str):
                items.append(item)
        return tuple(items)
    return ()


def _normalize_input(source: object) -> AlertRoutingInput:
    """Normalize a dict or dataclass-like input into an AlertRoutingInput."""
    return AlertRoutingInput(
        fleet_monitoring_verdict=_as_str_or_none(
            _get_value(source, "fleet_monitoring_verdict")
        ),
        dynamic_exit_gate_verdict=_as_str_or_none(
            _get_value(source, "dynamic_exit_gate_verdict")
        ),
        profitability_gate_verdict=_as_str_or_none(
            _get_value(source, "profitability_gate_verdict")
        ),
        telemetry_fresh=_as_bool_or_none(
            _get_value(source, "telemetry_fresh")
        ),
        telemetry_age_seconds=_as_int_or_none(
            _get_value(source, "telemetry_age_seconds")
        ),
        heartbeat_ok=_as_bool_or_none(
            _get_value(source, "heartbeat_ok")
        ),
        runtime_drift_detected=_as_bool_or_none(
            _get_value(source, "runtime_drift_detected")
        ),
        credential_path_clear=_as_bool_or_none(
            _get_value(source, "credential_path_clear")
        ),
        shadow_paper_status=_as_str_or_none(
            _get_value(source, "shadow_paper_status")
        ),
        go_no_go_blocker_present=_as_bool_or_none(
            _get_value(source, "go_no_go_blocker_present")
        ),
        reason_codes=_as_string_tuple(
            _get_value(source, "reason_codes")
        ),
    )


# ---------------------------------------------------------------------------
#  Route collection
# ---------------------------------------------------------------------------

def _add_route(
    routes: list[AlertRoute],
    route: AlertRoute,
) -> None:
    """Add a route if not already present."""
    if route not in routes:
        routes.append(route)


# ---------------------------------------------------------------------------
#  Decision engine
# ---------------------------------------------------------------------------

def _evaluate_severity(
    input_data: AlertRoutingInput,
    *,
    telemetry_hard_stale_threshold: int = STALE_TELEMETRY_HARD_THRESHOLD_SECONDS,
    telemetry_warning_stale_threshold: int = STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS,
) -> AlertRoutingDecision:
    """Evaluate a single AlertRoutingInput and return an advisory decision.

    Pure function: no I/O, no notifications, no side effects.
    """
    routes: list[AlertRoute] = []
    reason_codes: list[str] = list(input_data.reason_codes)
    severity = AlertSeverity.INFO

    # -- Convenience aliases
    monitoring_verdict = input_data.fleet_monitoring_verdict
    dynamic_exit = input_data.dynamic_exit_gate_verdict
    profitability = input_data.profitability_gate_verdict
    telemetry_fresh = input_data.telemetry_fresh
    telemetry_age = input_data.telemetry_age_seconds
    heartbeat_ok = input_data.heartbeat_ok
    runtime_drift = input_data.runtime_drift_detected
    credential_clear = input_data.credential_path_clear
    go_no_go_blocker = input_data.go_no_go_blocker_present

    # --- Go/No-Go blocker — highest priority ---
    if go_no_go_blocker is True:
        severity = AlertSeverity.BLOCKED
        reason_codes.append("go_no_go_blocker_present")
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- Runtime drift detected ---
    if runtime_drift is True:
        if severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
            severity = AlertSeverity.CRITICAL
        reason_codes.append("runtime_drift_detected")
        _add_route(routes, AlertRoute.RUNTIME_DRIFT_REVIEW_RECOMMENDED)
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- Unclear credential path ---
    if credential_clear is False:
        if severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
            severity = AlertSeverity.CRITICAL
        reason_codes.append("unclear_credential_path")
        _add_route(routes, AlertRoute.CREDENTIAL_REVIEW_RECOMMENDED)
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- Monitoring verdict ---
    if monitoring_verdict == MonitoringVerdict.RED.value:
        severity = AlertSeverity.BLOCKED
        reason_codes.append("fleet_monitoring_red")
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif monitoring_verdict == MonitoringVerdict.YELLOW.value:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("fleet_monitoring_yellow")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif monitoring_verdict is None:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("fleet_monitoring_missing")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- Dynamic exit gate ---
    if dynamic_exit == DYNAMIC_EXIT_GATE_BLOCKED:
        if severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
            severity = AlertSeverity.CRITICAL
        reason_codes.append("dynamic_exit_gate_blocked")
        _add_route(routes, AlertRoute.RISK_REVIEW_RECOMMENDED)
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif dynamic_exit == DYNAMIC_EXIT_GATE_INCONCLUSIVE:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("dynamic_exit_gate_inconclusive")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif dynamic_exit is None:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("dynamic_exit_gate_missing")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    # dynamic_exit == CANDIDATE → no additional route

    # --- Profitability gate ---
    if profitability == PROFITABILITY_GATE_BLOCKED:
        if severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
            severity = AlertSeverity.CRITICAL
        reason_codes.append("profitability_gate_blocked")
        _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif profitability == PROFITABILITY_GATE_INCONCLUSIVE:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("profitability_gate_inconclusive")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif profitability is None:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("profitability_gate_missing")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    # profitability == CANDIDATE → no additional route

    # --- Telemetry staleness ---
    if telemetry_fresh is False or (
        telemetry_age is not None
        and telemetry_age > telemetry_warning_stale_threshold
    ):
        if (
            telemetry_age is not None
            and telemetry_age > telemetry_hard_stale_threshold
        ):
            reason_codes.append("stale_telemetry_hard")
            if severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
                severity = AlertSeverity.BLOCKED
            _add_route(routes, AlertRoute.PROMOTION_PAUSE_RECOMMENDED)
        else:
            reason_codes.append("stale_telemetry_warning")
            if severity == AlertSeverity.INFO:
                severity = AlertSeverity.WARNING
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- Heartbeat ---
    if heartbeat_ok is False:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("heartbeat_failed")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)
    elif heartbeat_ok is None:
        if severity == AlertSeverity.INFO:
            severity = AlertSeverity.WARNING
        reason_codes.append("heartbeat_missing")
        _add_route(routes, AlertRoute.OPERATOR_REVIEW_RECOMMENDED)

    # --- No alert path ---
    if not routes:
        routes = [AlertRoute.NO_ALERT_RECOMMENDED]
        reason_codes.append("all_checks_clean")

    return AlertRoutingDecision(
        severity=severity,
        routes=tuple(routes),
        reason_codes=tuple(reason_codes),
        notification_sent=False,
        action_count=0,
        mutation_count=0,
        runtime_mutation=False,
        capital_execution=False,
    )


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------


def evaluate_alert_routing(
    input_data: object,
    *,
    telemetry_hard_stale_threshold: int = STALE_TELEMETRY_HARD_THRESHOLD_SECONDS,
    telemetry_warning_stale_threshold: int = STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS,
) -> AlertRoutingDecision:
    """Evaluate alert routing for a single evidence input.

    Returns an advisory-only AlertRoutingDecision.
    No notification is sent. No external endpoint is called.
    """
    normalized = _normalize_input(input_data)
    return _evaluate_severity(
        normalized,
        telemetry_hard_stale_threshold=telemetry_hard_stale_threshold,
        telemetry_warning_stale_threshold=telemetry_warning_stale_threshold,
    )


def evaluate_alert_routing_report(
    inputs: Sequence[object],
    *,
    telemetry_hard_stale_threshold: int = STALE_TELEMETRY_HARD_THRESHOLD_SECONDS,
    telemetry_warning_stale_threshold: int = STALE_TELEMETRY_WARNING_THRESHOLD_SECONDS,
) -> AlertRoutingReport:
    """Evaluate alert routing for multiple evidence inputs and return a report.

    Aggregates decisions and ensures no notification or runtime mutation.
    """
    decisions: list[AlertRoutingDecision] = []
    for item in inputs:
        decisions.append(
            evaluate_alert_routing(
                item,
                telemetry_hard_stale_threshold=telemetry_hard_stale_threshold,
                telemetry_warning_stale_threshold=telemetry_warning_stale_threshold,
            )
        )

    # Determine overall severity (worst-case)
    severity_order = {
        AlertSeverity.INFO: 0,
        AlertSeverity.WARNING: 1,
        AlertSeverity.CRITICAL: 2,
        AlertSeverity.BLOCKED: 3,
    }
    overall = AlertSeverity.INFO
    worst_score = 0
    for decision in decisions:
        score = severity_order.get(decision.severity, 0)
        if score > worst_score:
            worst_score = score
            overall = decision.severity

    # Collect unique reason codes across decisions
    reason_code_set: set[str] = set()
    for decision in decisions:
        for code in decision.reason_codes:
            reason_code_set.add(code)

    return AlertRoutingReport(
        schema_version=1,
        overall_severity=overall,
        decisions=tuple(decisions),
        summary={
            "decision_count": len(decisions),
            "notification_sent_count": 0,
            "action_count": 0,
            "mutation_count": 0,
            "capital_execution": False,
            "unique_reason_codes": sorted(reason_code_set),
        },
        safety={
            "exchange_io": False,
            "orders": False,
            "runtime_mutation": False,
            "config_writes": False,
            "strategy_writes": False,
            "docker_changes": False,
            "compose_changes": False,
            "cron_changes": False,
            "auto_healing": False,
            "capital_execution": False,
        },
    )


__all__ = [
    "AlertRoute",
    "AlertRoutingDecision",
    "AlertRoutingInput",
    "AlertRoutingReport",
    "AlertSeverity",
    "evaluate_alert_routing",
    "evaluate_alert_routing_report",
]
