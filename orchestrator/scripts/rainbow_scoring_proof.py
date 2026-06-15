#!/usr/bin/env python3
"""SI v2 Scoring Proof — validates scoring eligibility from persisted state.

Reads the latest cycle state JSON and the measurement ledger to confirm:
- Rainbow observation status
- Freshness (fresh=True, age <= threshold)
- Scoring eligibility (all 5 conditions)
- Safety invariants (can_execute=False, dry_run_only=True)

Usage:
    python3 orchestrator/scripts/rainbow_scoring_proof.py
    python3 orchestrator/scripts/rainbow_scoring_proof.py --state-dir <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime as dt_mod
from pathlib import Path

REPO_ROOT = Path("/home/hermes/projects/trading")
LEDGER_DIR = REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "measurement"
STATE_DIR = REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "cycle_state"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "✅" if ok else "❌"
    print(f"  {status} {label}")
    if detail:
        print(f"       {detail}")
    return ok


def _count_scoring_eligible_from_ledger(ledger_path: Path) -> tuple[int, int]:
    """Count scoring-eligible cycles from the measurement ledger.

    Uses the persisted ``rainbow_scoring_eligible`` field.
    Does NOT infer eligibility from source/count alone.
    """
    eligible = 0
    total_rainbow = 0
    if not ledger_path.exists():
        return 0, 0
    with open(ledger_path) as f:
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
            total_rainbow += 1
            # Only count from persisted rainbow_scoring_eligible field
            if entry.get("rainbow_scoring_eligible", False) is True:
                eligible += 1
    return eligible, total_rainbow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SI v2 Scoring Gate Proof")
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    parser.add_argument("--ledger-path", type=Path, default=LEDGER_DIR / "measurement_ledger.jsonl")
    args = parser.parse_args(argv)

    state_dir = args.state_dir
    ledger_path = args.ledger_path
    failures = 0

    print("=" * 60)
    print("SI v2 Scoring Gate Proof — Rainbow Freshness")
    print(f"  Timestamp: {dt_mod.now(UTC).isoformat()}")
    print(f"  State dir: {state_dir}")
    print(f"  Ledger:    {ledger_path}")
    print("=" * 60)

    # ── Latest state file ────────────────────────────────────────────────
    state_files = sorted(
        state_dir.glob("active_cycle_*.state.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not state_files:
        check("No cycle state files found", False)
        return 1

    latest = state_files[0]
    print(f"\nLatest state file: {latest.name}")
    print(f"  Modified: {dt_mod.fromtimestamp(latest.stat().st_mtime, UTC).isoformat()}")

    try:
        with open(latest) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        check(f"Read state file: {e}", False)
        return 1

    rainbow = state.get("external_signals", {}).get("rainbow", {})
    if not rainbow:
        check("Rainbow data in state", False)
        return 1

    # ── Rainbow observation ──────────────────────────────────────────────
    print("\n--- Rainbow Observation ---")
    r_status = rainbow.get("status", "N/A")
    r_source = rainbow.get("source", "N/A")
    r_count = rainbow.get("count", 0)
    r_errors = rainbow.get("errors_count", 0)
    r_fresh = rainbow.get("fresh", False)
    r_age = rainbow.get("freshness_seconds")
    r_max_age = rainbow.get("freshness_max_seconds", 900)
    r_fresh_count = rainbow.get("fresh_signal_count", 0)
    r_stale_count = rainbow.get("stale_signal_count", 0)
    r_fresh_syms = rainbow.get("fresh_symbols", [])
    r_stale_syms = rainbow.get("stale_symbols", [])

    print(f"  Status:            {r_status}")
    print(f"  Source:            {r_source}")
    print(f"  Signal count:      {r_count}")
    print(f"  Errors:            {r_errors}")
    print(f"  Fresh:             {r_fresh}")
    print(f"  Freshness age:     {r_age}s (max: {r_max_age}s)")
    print(f"  Fresh signals:     {r_fresh_count} ({', '.join(r_fresh_syms) if r_fresh_syms else 'none'})")
    print(f"  Stale signals:     {r_stale_count} ({', '.join(r_stale_syms) if r_stale_syms else 'none'})")

    # ── Freshness invariants ─────────────────────────────────────────────
    print("\n--- Freshness Invariants ---")
    age_ok = r_age is not None and 0 <= r_age <= (r_max_age or 900)
    if r_age is not None:
        if r_age < -30:
            # Future timestamp — should not happen with fixed code
            failures += 1  # always counts as failure
            check(
                "Future timestamp rejected", False,
                f"age={r_age}s (future), threshold={r_max_age}s",
            )
        elif not age_ok:
            failures += 1
            check(
                f"Freshness age out of range: {r_age}s not in [0, {r_max_age}s]", False,
            )
        else:
            check(
                f"Freshness age in valid range: {r_age}s <= {r_max_age}s", True,
            )
    else:
        failures += 1
        check("Freshness age is not None", False)

    if r_fresh_count <= 0:
        failures += 1
        check(
            f"At least one fresh signal ({r_fresh_count})", False,
        )
    else:
        check(
            f"At least one fresh signal ({r_fresh_count})", True,
        )

    # ── Scoring eligibility ──────────────────────────────────────────────
    print("\n--- Scoring Eligibility ---")
    scoring = (
        r_status == "SUCCESS"
        and r_source in ("read_only", "live")
        and r_count >= 1
        and r_errors == 0
        and r_fresh is True
        and r_age is not None
        and 0 <= r_age <= (r_max_age or 900)
    )
    failures += 0 if check(
        f"Scoring eligible: {scoring}", scoring,
    ) else 1

    if not scoring:
        print("       Conditions:")
        print(f"         status == SUCCESS:        {r_status == 'SUCCESS'} (={r_status})")
        print(f"         source read_only/live:    {r_source in ('read_only', 'live')} (={r_source})")
        print(f"         count >= 1:               {r_count >= 1} (={r_count})")
        print(f"         errors == 0:              {r_errors == 0} (={r_errors})")
        print(f"         fresh:                    {r_fresh}")
        print(f"         age in [0, threshold]:    {age_ok} (age={r_age}, max={r_max_age})")

    # ── Ledger scoring history ───────────────────────────────────────────
    print("\n--- Measurement Ledger (Persisted Scoring History) ---")
    eligible_count, total_count = _count_scoring_eligible_from_ledger(ledger_path)
    print(f"  Total fleet observations in ledger:  {total_count}")
    print(f"  Scoring-eligible cycles (persisted):  {eligible_count}")
    print(f"  Scoring gate progress:               {eligible_count}/10")

    if eligible_count > 0:
        check("Scoring gate advancing", True, f"{eligible_count}/10")
    elif scoring:
        check("Scoring eligible this cycle — ledger will advance on next persist", True)
    else:
        check("No scoring-eligible cycles yet", False)

    # ── Safety state ─────────────────────────────────────────────────────
    print("\n--- Safety State ---")
    ctrl = state.get("controller_state", "PAUSED / L3_REPOSITORY_ONLY")
    print(f"  Controller:     {ctrl}")
    print(f"  Config muts:    {state.get('config_mutations', 0)}")
    print(f"  Docker muts:    {state.get('docker_mutations', 0)}")
    print(f"  Live trade muts: {state.get('live_trading_mutations', 0)}")
    print(f"  Strategy muts:  {state.get('strategy_mutations', 0)}")

    # ── Safety invariants ────────────────────────────────────────────────
    print("\n--- Safety Invariants ---")
    signals = rainbow.get("signals", state.get("external_signals", {}).get("rainbow", {}).get("signals", []))
    safety_ok = 0
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        meta = sig.get("metadata", {})
        act = meta.get("actionability", {}) if isinstance(meta, dict) else {}
        can_exec = act.get("can_execute", True) if isinstance(act, dict) else True
        dry_only = act.get("dry_run_only", False) if isinstance(act, dict) else False
        if not can_exec and dry_only:
            safety_ok += 1

    n_signals = len(signals)
    failures += 0 if check(
        f"can_execute=False + dry_run_only=True: {safety_ok}/{n_signals}",
        safety_ok == n_signals > 0,
    ) else 1

    # ── Verdict ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if failures == 0 and scoring:
        verdict = "GREEN ✅ — Scoring gate can advance"
    elif failures == 0:
        verdict = "YELLOW 🟡 — No failures but scoring not eligible yet"
    else:
        verdict = f"RED ❌ — {failures} failure(s)"
    print(f"VERDICT: {verdict}")
    print(f"{'=' * 60}\n")

    return 0 if failures == 0 and scoring else 1


if __name__ == "__main__":
    sys.exit(main())
