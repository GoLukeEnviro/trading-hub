#!/usr/bin/env python3
"""Runtime Drift Gate Proof — read-only, no mutation.

Evaluates runtime drift detection by running the drift guard against
fixture data and verifying that drift is detected correctly.

Exit codes:
  0 → GREEN   (no drift detected)
  1 → YELLOW  (drift detected, advisory only)
  2 → RED     (readiness failure)

Usage:
  python3 orchestrator/scripts/runtime_drift_gate_proof.py
  python3 orchestrator/scripts/runtime_drift_gate_proof.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "self_improvement_v2" / "src"))

from si_v2.rainbow.drift_guard import (  # noqa: E402
    DriftVerdict,
    RainbowContractDriftGuard,
)
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Runtime Drift Gate Proof — read-only, no mutation",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Run drift check against the repo's own contract and fixtures
    guard = RainbowContractDriftGuard(
        schema_path=Path("self_improvement_v2/contracts/rainbow_signal_envelope.schema.json"),
        fixture_dir=Path("self_improvement_v2/fixtures/rainbow-signals"),
    )
    result = guard.run()

    verdict = "GREEN"
    if result.verdict == DriftVerdict.RED:
        verdict = "RED"
    elif result.verdict == DriftVerdict.YELLOW:
        verdict = "YELLOW"

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "overall_verdict": result.verdict.value,
            "summary": result.summary,
            "total_fixtures": result.total_fixtures,
            "passed_fixtures": result.passed_fixtures,
            "unexpected_failures": result.unexpected_failures,
            "fixture_drifts": result.fixture_drifts,
        }, indent=2))
    else:
        print(f"Verdict          : {verdict}")
        print(f"Overall verdict  : {result.verdict.value}")
        print(f"Summary          : {result.summary}")
        print(f"Fixtures         : {result.passed_fixtures}/{result.total_fixtures} passed")
        print(f"Unexpected fails : {result.unexpected_failures}")
        if result.fixture_drifts:
            print(f"Fixture drifts   : {result.fixture_drifts}")

    return 0 if verdict == "GREEN" else (1 if verdict == "YELLOW" else 2)


if __name__ == "__main__":
    sys.exit(main())
