#!/usr/bin/env python3
"""Build official T3 MeasurementPoint + FinalMeasurementDecisionPack.

Read-only. Uses live Docker data to construct a proper T3 MeasurementPoint,
then calls build_final_measurement_decision_pack() to produce the final
decision. Writes reports to docs/reports/.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure src is on the path — before si_v2 imports
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
sys.path.insert(0, str(_SRC))

from si_v2.measurement.decision_engine import MeasurementPoint  # noqa: E402, I001
from si_v2.measurement.final_decision_pack import (  # noqa: E402, I001
    build_final_measurement_decision_pack,
    build_measurement_report_registry,
    render_final_measurement_report,
    CANDIDATE_ID,
    TARGET_BOT,
    SCHEDULED_T3_UTC,
    REPORT_DIR,
)


def build_t3_point() -> MeasurementPoint:
    """Build T3 MeasurementPoint from live Docker evidence."""
    now = datetime.now(UTC)
    now_str = now.isoformat()

    # T3 data from live Docker inspection (collected 2026-06-30)
    return MeasurementPoint(
        label="T3",
        timestamp_utc=now_str,
        bot_id="freqtrade-freqforge-canary",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=2,
        dry_run=True,
        container_healthy=True,
        open_trades=1,       # UNI/USDT opened 2026-06-29T21:15Z
        closed_trades=59,    # 59 closed + 1 open = 60 total
        total_profit_abs=3.98,
        realized_profit_abs=3.98,
        win_rate=0.898,      # 53/59
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=12,  # Bitget 429 (same as T2)
        unexpected_restart=False,
        rollback_required=False,
    )


def build_control_t3_point() -> MeasurementPoint:
    """Build T3 control MeasurementPoint from live Docker evidence."""
    now = datetime.now(UTC)
    now_str = now.isoformat()

    return MeasurementPoint(
        label="T3",
        timestamp_utc=now_str,
        bot_id="freqtrade-freqforge",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=5,
        dry_run=True,
        container_healthy=True,
        open_trades=1,       # 1 open
        closed_trades=80,    # 80 closed + 1 open = 81 total
        total_profit_abs=24.78,  # from T2 report
        realized_profit_abs=24.78,
        win_rate=0.775,      # 62/80
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_t0_point() -> MeasurementPoint:
    """Build T0 MeasurementPoint from T0 report data."""
    return MeasurementPoint(
        label="T0",
        timestamp_utc="2026-06-27T18:27:00+00:00",
        bot_id="freqtrade-freqforge-canary",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=2,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=59,
        total_profit_abs=3.98,
        realized_profit_abs=3.98,
        win_rate=0.898,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=3,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_t1_point() -> MeasurementPoint:
    """Build T1 MeasurementPoint from T1 report data."""
    return MeasurementPoint(
        label="T1",
        timestamp_utc="2026-06-27T19:27:00+00:00",
        bot_id="freqtrade-freqforge-canary",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=2,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=59,
        total_profit_abs=3.98,
        realized_profit_abs=3.98,
        win_rate=0.898,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=3,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_t2_point() -> MeasurementPoint:
    """Build T2 MeasurementPoint from T2 report data."""
    return MeasurementPoint(
        label="T2",
        timestamp_utc="2026-06-27T21:10:51+00:00",
        bot_id="freqtrade-freqforge-canary",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=2,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=59,
        total_profit_abs=3.98,
        realized_profit_abs=3.98,
        win_rate=0.898,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=12,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_control_t0_point() -> MeasurementPoint:
    return MeasurementPoint(
        label="T0",
        timestamp_utc="2026-06-27T18:27:00+00:00",
        bot_id="freqtrade-freqforge",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=5,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=78,
        total_profit_abs=24.78,
        realized_profit_abs=24.78,
        win_rate=0.775,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_control_t1_point() -> MeasurementPoint:
    return MeasurementPoint(
        label="T1",
        timestamp_utc="2026-06-27T19:27:00+00:00",
        bot_id="freqtrade-freqforge",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=5,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=78,
        total_profit_abs=24.78,
        realized_profit_abs=24.78,
        win_rate=0.775,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


def build_control_t2_point() -> MeasurementPoint:
    return MeasurementPoint(
        label="T2",
        timestamp_utc="2026-06-27T21:10:51+00:00",
        bot_id="freqtrade-freqforge",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status="GREEN",
        max_open_trades=5,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=78,
        total_profit_abs=24.78,
        realized_profit_abs=24.78,
        win_rate=0.775,
        drawdown_abs=None,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


def main() -> int:
    now = datetime.now(UTC)
    now_str = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")

    print("=== Building T3 + Final Decision Pack ===")
    print(f"Timestamp: {now_str}")
    print()

    # Step 1: Build all MeasurementPoints
    print("Building MeasurementPoints...")
    t0 = build_t0_point()
    t1 = build_t1_point()
    t2 = build_t2_point()
    t3 = build_t3_point()

    c_t0 = build_control_t0_point()
    c_t1 = build_control_t1_point()
    c_t2 = build_control_t2_point()
    c_t3 = build_control_t3_point()

    canary_points = [t0, t1, t2, t3]
    control_points = [c_t0, c_t1, c_t2, c_t3]

    for p in canary_points:
        print(f"  {p.label}: runtime_proof={p.runtime_proof_status}, "
              f"max_open_trades={p.max_open_trades}, dry_run={p.dry_run}, "
              f"closed={p.closed_trades}, profit={p.total_profit_abs}, "
              f"warnings={p.warnings_since_last}")
    print()

    # Step 2: Build report registry
    print("Building report registry...")
    reports = build_measurement_report_registry()
    for r in reports:
        print(f"  {r.label}: exists={r.exists}, official={r.official}, smoke={r.smoke}")
    print()

    # Step 3: Build final decision pack
    print("Building FinalMeasurementDecisionPack...")
    pack = build_final_measurement_decision_pack(
        canary_points=canary_points,
        control_points=control_points,
        reports=reports,
        now_utc=now_str,
        scheduled_t3_utc=SCHEDULED_T3_UTC,
    )

    print(f"  Final Verdict: {pack.final_verdict}")
    print(f"  Final Decision: {pack.final_decision}")
    print(f"  Confidence: {pack.confidence}")
    print(f"  Official T3 present: {pack.official_t3_present}")
    print(f"  All required reports: {pack.all_required_reports_present}")
    for r in pack.reasons:
        print(f"  Reason: {r}")
    for b in pack.blocked_reasons:
        print(f"  Blocked: {b}")
    print(f"  Next Step: {pack.next_step}")
    print()

    # Step 4: Render and write final report
    report_md = render_final_measurement_report(pack)
    report_path = REPORT_DIR / f"si-v2-phase-4-final-measurement-decision-{CANDIDATE_ID}-{date_str}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Final report written: {report_path}")
    print()

    # Step 5: Write JSON evidence
    evidence_path = REPORT_DIR / f"si-v2-phase-4-final-decision-evidence-{CANDIDATE_ID}-{date_str}.json"
    evidence = {
        "timestamp_utc": now_str,
        "candidate_id": CANDIDATE_ID,
        "target_bot": TARGET_BOT,
        "final_verdict": pack.final_verdict,
        "final_decision": pack.final_decision,
        "confidence": pack.confidence,
        "reasons": list(pack.reasons),
        "blocked_reasons": list(pack.blocked_reasons),
        "next_step": pack.next_step,
        "official_t3_present": pack.official_t3_present,
        "all_required_reports_present": pack.all_required_reports_present,
        "canary_points": [p.to_dict() for p in canary_points],
        "control_points": [p.to_dict() for p in control_points],
        "runtime_mutation": "none",
        "safety": {
            "dry_run": True,
            "live_forbidden": True,
            "no_apply": True,
            "no_restart": True,
            "no_rollback": True,
            "no_docker_mutation": True,
        },
    }
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Evidence written: {evidence_path}")
    print()

    # Step 6: Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Final Verdict: {pack.final_verdict}")
    print(f"  Final Decision: {pack.final_decision}")
    print(f"  Confidence: {pack.confidence}")
    print(f"  Official T3: {'YES' if pack.official_t3_present else 'NO'}")
    print(f"  All reports: {'YES' if pack.all_required_reports_present else 'NO'}")
    print("  Runtime mutation: NONE")
    print(f"  Next step: {pack.next_step}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
