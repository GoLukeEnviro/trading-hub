#!/usr/bin/env python3
"""SI v2 Scoring Proof — validates that the Rainbow producer advances
the scoring gate from 0/10.

This reads the measurement ledger to check scoring eligibility progress.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path("/home/hermes/projects/trading")
LEDGER_DIR = REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "measurement"
LEDGER_PATH = LEDGER_DIR / "measurement_ledger.jsonl"
STATE_DIR = REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "cycle_state"


def main() -> int:
    scoring_eligible_cycles = 0
    total_rainbow_cycles = 0

    print("=" * 60)
    print("SI v2 Scoring Gate Proof — Rainbow Freshness")
    print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"  Ledger:    {LEDGER_PATH}")
    print("=" * 60)

    # Read candidate files from cycle_state dir
    state_files = sorted(STATE_DIR.glob("active_cycle_*.state.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    if not state_files:
        print("No cycle state files found. Run a cycle first.")
        return 1

    latest = state_files[0]
    print(f"\nLatest state file: {latest.name}")
    print(f"  Modified: {datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat()}")

    try:
        with open(latest) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  Error reading: {e}")
        return 1

    rainbow = state.get("external_signals", {}).get("rainbow", {})
    if not rainbow:
        print("  No Rainbow data in latest state file")
        return 1

    print("\n--- Rainbow Observation ---")
    print(f"  Status:            {rainbow.get('status', 'N/A')}")
    print(f"  Source:            {rainbow.get('source', 'N/A')}")
    print(f"  Signal count:      {rainbow.get('count', 'N/A')}")
    print(f"  Errors:            {rainbow.get('errors_count', 'N/A')}")
    print(f"  Fresh:             {rainbow.get('fresh', 'N/A')}")
    print(f"  Freshness age:     {rainbow.get('freshness_seconds', 'N/A')}s")
    print(f"  Freshness max:     {rainbow.get('freshness_max_seconds', 'N/A')}s")

    fresh = rainbow.get("fresh", False)
    source = rainbow.get("source", "")
    count = rainbow.get("count", 0)
    errors = rainbow.get("errors_count", 0)
    status = rainbow.get("status", "")

    scoring_eligible = (
        status == "SUCCESS"
        and source in ("read_only", "live")
        and count >= 1
        and errors == 0
        and fresh
    )
    print(f"\n  Scoring eligible:   {'✅ YES' if scoring_eligible else '❌ NO'}")

    if not scoring_eligible:
        print(f"    - status == SUCCESS:        {status == 'SUCCESS'} (={status})")
        print(f"    - source in read_only/live:  {source in ('read_only', 'live')} (={source})")
        print(f"    - count >= 1:                {count >= 1} (={count})")
        print(f"    - errors == 0:               {errors == 0} (={errors})")
        print(f"    - fresh:                     {fresh} (age={rainbow.get('freshness_seconds', '?')}s)")

    # Read measurement ledger for scoring history
    print("\n--- Measurement Ledger (Rainbow cycles) ---")
    try:
        with open(LEDGER_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("_type") != "fleet":
                    continue
                if "rainbow" not in str(entry.get("cycle_id", "")):
                    # Count all fleet observations
                    pass
                total_rainbow_cycles += 1
                r = entry.get("rainbow_status")
                src = entry.get("rainbow_source")
                cnt = entry.get("rainbow_signal_count", 0)
                err = entry.get("rainbow_errors_count", 0)
                # Check scoring eligibility from historical data
                # (We can't check freshness from ledger alone, but we can
                # track source and errors)
                if r == "SUCCESS" and src in ("read_only", "live") and cnt >= 1 and err == 0:
                    scoring_eligible_cycles += 1
    except FileNotFoundError:
        print("  No measurement ledger found")

    print(f"\n  Total fleet observations: {total_rainbow_cycles}")
    print(f"  Scoring-eligible cycles (by source): {scoring_eligible_cycles}")

    # Controller status
    print("\n--- Safety State ---")
    print(f"  Controller state:      {state.get('controller_state', 'PAUSED / L3_REPOSITORY_ONLY')}")
    print(f"  Config mutations:      {state.get('config_mutations', 0)}")
    print(f"  Docker mutations:      {state.get('docker_mutations', 0)}")
    print(f"  Live trading muts:     {state.get('live_trading_mutations', 0)}")
    print(f"  Strategy mutations:    {state.get('strategy_mutations', 0)}")
    print(f"  Runtime mutations:     {state.get('runtime_mutations', 0)}")

    # Actionability check
    print("\n--- Safety Invariants ---")
    signals = state.get("external_signals", {}).get("rainbow", {}).get("signals", [])
    safety_ok = 0
    for sig in signals:
        meta = sig.get("metadata", {})
        can_exec = meta.get("actionability", {}).get("can_execute", True)
        dry_only = meta.get("actionability", {}).get("dry_run_only", False)
        if not can_exec and dry_only:
            safety_ok += 1
    print(f"  can_execute=False + dry_run_only=True: {safety_ok}/{len(signals)}")

    print(f"\n{'=' * 60}")
    if scoring_eligible and safety_ok == len(signals):
        print("VERDICT: GREEN ✅ — Scoring gate can advance")
    elif scoring_eligible:
        print("VERDICT: YELLOW 🟡 — Scoring eligible but safety check incomplete")
    else:
        print("VERDICT: RED ❌ — Not scoring eligible")
    print(f"{'=' * 60}\n")

    return 0 if scoring_eligible else 1


if __name__ == "__main__":
    sys.exit(main())
