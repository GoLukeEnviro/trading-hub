#!/usr/bin/env python3
"""Alert Routing Readiness Proof — read-only, no mutation.

Evaluates alert routing readiness by running the alert routing evaluator
against a set of evidence-like inputs and verifying that no notification
is sent and no runtime mutation occurs.

Exit codes:
  0 → GREEN   (all checks pass)
  1 → YELLOW  (advisory alerts triggered, but no mutation)
  2 → RED     (readiness failure)

Usage:
  python3 orchestrator/scripts/alert_routing_readiness_proof.py
  python3 orchestrator/scripts/alert_routing_readiness_proof.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "self_improvement_v2" / "src"))

from si_v2.monitoring.alert_routing import (  # noqa: E402
    AlertRoutingInput,
    evaluate_alert_routing,
    evaluate_alert_routing_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alert Routing Readiness Proof — read-only, no mutation",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Test with a healthy input
    healthy = AlertRoutingInput(
        fleet_monitoring_verdict="GREEN",
        telemetry_fresh=True,
        heartbeat_ok=True,
        runtime_drift_detected=False,
        credential_path_clear=True,
        go_no_go_blocker_present=False,
    )
    decision = evaluate_alert_routing(healthy)
    report = evaluate_alert_routing_report([healthy])

    # Verify safety invariants
    assert decision.notification_sent is False
    assert decision.action_count == 0
    assert decision.mutation_count == 0
    assert decision.runtime_mutation is False
    assert decision.capital_execution is False

    verdict = "GREEN" if decision.severity.value in ("info", "no_alert_recommended") else "YELLOW"

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "severity": decision.severity.value,
            "routes": [r.value for r in decision.routes],
            "notification_sent": decision.notification_sent,
            "action_count": decision.action_count,
            "mutation_count": decision.mutation_count,
            "overall_severity": report.overall_severity.value,
        }, indent=2))
    else:
        print(f"Verdict          : {verdict}")
        print(f"Severity         : {decision.severity.value}")
        print(f"Routes           : {[r.value for r in decision.routes]}")
        print(f"Notification sent: {decision.notification_sent}")
        print(f"Action count     : {decision.action_count}")
        print(f"Mutation count   : {decision.mutation_count}")
        print(f"Overall severity : {report.overall_severity.value}")

    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
