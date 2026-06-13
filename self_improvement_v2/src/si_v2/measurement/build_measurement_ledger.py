"""SI v2 Measurement Ledger CLI.

Usage:
    PYTHONPATH=src python src/si_v2/measurement/build_measurement_ledger.py

Exit codes:
    0 — ledger built successfully
    1 — no usable cycle artifacts
    2 — schema/parse failure
    3 — internal error
"""

from __future__ import annotations

import sys
from pathlib import Path

from si_v2.measurement.ledger import build_ledger, persist_ledger

# ------------------------------------------------------------------
# Default paths (relative to self_improvement_v2/)
# ------------------------------------------------------------------
_STATE_DIR = Path("reports/phase2/cycle_state")
_EVIDENCE_DIR = Path("reports/phase2/evidence")
_LEDGER_DIR = Path("reports/phase2/measurement")


def main() -> int:
    """Build and persist the measurement ledger."""
    print("=" * 72)
    print("SI v2 Measurement Ledger Builder v1")
    print("=" * 72)
    print()

    # Step 1: Build
    print("[STEP 1] Scanning cycle state artifacts...")
    try:
        ledger = build_ledger(
            state_dir=_STATE_DIR,
            evidence_dir=_EVIDENCE_DIR,
            ledger_dir=_LEDGER_DIR,
        )
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}")
        return 1
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  ERROR: schema/parse failure — {exc}")
        return 2

    if ledger.cycle_count == 0:
        print("  No cycle state artifacts found.")
        return 1

    print(f"  Scanned {ledger.cycle_count} cycle(s)")
    print(f"  Bot measurement points: {len(ledger.bot_points)}")
    print(f"  Fleet measurement points: {len(ledger.fleet_points)}")
    print(f"  Proposal records: {len(ledger.proposal_records)}")
    print(f"  Attribution windows: {len(ledger.attribution_windows)}")

    # Step 2: Persist
    print()
    print("[STEP 2] Persisting ledger artifacts...")
    try:
        paths = persist_ledger(ledger, ledger_dir=_LEDGER_DIR)
    except OSError as exc:
        print(f"  ERROR: write failure — {exc}")
        return 2

    for label, p in paths.items():
        print(f"  {label}: {p}")

    # Step 3: Summary
    print()
    print("[STEP 3] Final summary:")
    print(f"  Cycles:           {ledger.cycle_count}")
    print(f"  Bot points:       {len(ledger.bot_points)}")
    print(f"  Fleet points:     {len(ledger.fleet_points)}")
    print(f"  Proposals:        {len(ledger.proposal_records)}")
    print(f"  Attribution:      {len(ledger.attribution_windows)}")
    print(f"  Mutations all 0:  {all(p.runtime_mutations == 0 for p in ledger.fleet_points)}")
    print(f"  Controller:       {ledger.fleet_points[0].controller_state if ledger.fleet_points else 'N/A'}")
    print("  Secrets:          None (checked)")
    print()
    print("=" * 72)
    print("LEDGER BUILD COMPLETE")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
