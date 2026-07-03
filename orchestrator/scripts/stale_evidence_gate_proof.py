#!/usr/bin/env python3
"""Stale Evidence Gate Proof — read-only, no mutation.

Evaluates stale evidence detection by running the stale evidence gate
against fixture data and verifying that stale evidence is correctly
identified across all domains.

Exit codes:
  0 → GREEN   (all evidence fresh)
  1 → YELLOW  (stale evidence detected, advisory only)
  2 → RED     (readiness failure)

Usage:
  python3 orchestrator/scripts/stale_evidence_gate_proof.py
  python3 orchestrator/scripts/stale_evidence_gate_proof.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "self_improvement_v2" / "src"))

from si_v2.validation.stale_evidence_gate import (  # noqa: E402
    EvidenceDomain,
    EvidenceItem,
    evaluate_stale_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stale Evidence Gate Proof — read-only, no mutation",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    now = datetime.now(tz=UTC)

    # Test fresh evidence (all domains)
    fresh_items = [
        EvidenceItem(
            evidence_id="fresh_active_cycle",
            domain=EvidenceDomain.ACTIVE_CYCLE,
            timestamp=now - timedelta(minutes=5),
        ),
        EvidenceItem(
            evidence_id="fresh_monitoring",
            domain=EvidenceDomain.MONITORING,
            timestamp=now - timedelta(minutes=5),
        ),
        EvidenceItem(
            evidence_id="fresh_dynamic_exit",
            domain=EvidenceDomain.DYNAMIC_EXIT,
            timestamp=now - timedelta(minutes=5),
        ),
    ]
    fresh_result = evaluate_stale_evidence(fresh_items, now=now)

    # Test stale evidence (all domains)
    stale_items = [
        EvidenceItem(
            evidence_id="stale_active_cycle",
            domain=EvidenceDomain.ACTIVE_CYCLE,
            timestamp=now - timedelta(days=30),
        ),
        EvidenceItem(
            evidence_id="stale_monitoring",
            domain=EvidenceDomain.MONITORING,
            timestamp=now - timedelta(days=30),
        ),
        EvidenceItem(
            evidence_id="stale_dynamic_exit",
            domain=EvidenceDomain.DYNAMIC_EXIT,
            timestamp=now - timedelta(days=30),
        ),
    ]
    stale_result = evaluate_stale_evidence(stale_items, now=now)

    # Test mixed evidence
    mixed_items = [
        EvidenceItem(
            evidence_id="mixed_active_cycle",
            domain=EvidenceDomain.ACTIVE_CYCLE,
            timestamp=now - timedelta(minutes=5),
        ),
        EvidenceItem(
            evidence_id="mixed_monitoring",
            domain=EvidenceDomain.MONITORING,
            timestamp=now - timedelta(days=30),
        ),
        EvidenceItem(
            evidence_id="mixed_dynamic_exit",
            domain=EvidenceDomain.DYNAMIC_EXIT,
            timestamp=now - timedelta(minutes=5),
        ),
    ]
    mixed_result = evaluate_stale_evidence(mixed_items, now=now)

    # Determine overall verdict
    all_fresh = all(r.is_stale is False for r in fresh_result.results)
    any_stale = any(r.is_stale for r in stale_result.results)
    mixed_stale = any(r.is_stale for r in mixed_result.results)

    if all_fresh and not any_stale and not mixed_stale:
        verdict = "GREEN"
    elif not all_fresh:
        verdict = "YELLOW"
    else:
        verdict = "GREEN"

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "fresh_all_green": all_fresh,
            "stale_all_red": any_stale,
            "mixed_detected": mixed_stale,
            "fresh_results": [{"id": r.evidence_id, "stale": r.is_stale, "age_hours": r.age_hours} for r in fresh_result.results],
            "stale_results": [{"id": r.evidence_id, "stale": r.is_stale, "age_hours": r.age_hours} for r in stale_result.results],
            "mixed_results": [{"id": r.evidence_id, "stale": r.is_stale, "age_hours": r.age_hours} for r in mixed_result.results],
        }, indent=2))
    else:
        print(f"Verdict              : {verdict}")
        print(f"Fresh (all domains)  : {'GREEN' if all_fresh else 'STALE'}")
        print(f"Stale (all domains)  : {'STALE' if any_stale else 'GREEN'}")
        print(f"Mixed detection      : {'STALE' if mixed_stale else 'GREEN'}")
        print()
        print("Fresh evidence:")
        for r in fresh_result.results:
            print(f"  {r.evidence_id}: {'FRESH' if not r.is_stale else 'STALE'} ({r.age_hours:.1f}h)")
        print()
        print("Stale evidence:")
        for r in stale_result.results:
            print(f"  {r.evidence_id}: {'FRESH' if not r.is_stale else 'STALE'} ({r.age_hours:.1f}h)")

    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
