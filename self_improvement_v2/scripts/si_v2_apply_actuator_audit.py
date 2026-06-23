#!/usr/bin/env python3
r"""SI v2 Apply Actuator Audit — read-only fleet runtime binding validation.

Usage:
    python3 si_v2_apply_actuator_audit.py
    python3 si_v2_apply_actuator_audit.py --mode audit
    python3 si_v2_apply_actuator_audit.py --proposal-id 65502d13 --bot-id freqtrade-freqforge --mode audit
    python3 si_v2_apply_actuator_audit.py --mode report --output /path/to/report.json

Modes:
    audit   — read-only fleet binding validation + overlay candidate check
    report  — generate proof report as JSON

Safety: read-only. No runtime mutation, no config changes, no Docker Compose,
no bot restart, no live trading, no dry_run=false.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for module imports
_REPO_ROOT = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_REPO_ROOT))

from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    build_host_overlay_path,
    resolve_binding,
    validate_fleet_bindings,
)
from si_v2.apply_actuator.models import (
    OverlayProposal,
    ProofStatus,
)
from si_v2.apply_actuator.overlay_merge import validate_overlay_safety
from si_v2.apply_actuator.policy import compute_apply_result


def cmd_audit(args: argparse.Namespace) -> int:
    """Run read-only fleet binding audit."""
    print("=" * 60)
    print("SI-v2 Apply Actuator — Fleet Runtime Binding Audit")
    print("=" * 60)

    # Fleet validation
    valid, issues = validate_fleet_bindings()
    if not valid:
        print(f"\n🔴 Fleet validation FAILED ({len(issues)} issues):")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ Fleet validation PASSED — all 4 bindings VERIFIED")

    # Per-bot audit
    print("\n--- Bot Bindings ---")
    for bot_id, binding in BOT_RUNTIME_BINDINGS.items():
        status = "✅" if binding.runtime_visible else "❌"
        print(f"\n{status} {bot_id}")
        print(f"   Container:  {binding.container_name}")
        print(f"   Host path:  {binding.host_user_data_path}")
        print(f"   Container:  {binding.container_user_data_path}")
        print(f"   Config:     {binding.host_config_path}")
        print(f"   Confidence: {binding.confidence}")

        # Check overlay file visibility on host
        overlay_candidates = []
        host_dir = Path(binding.host_user_data_path)
        if host_dir.exists():
            for f in host_dir.glob("overlay_*.json"):
                overlay_candidates.append(f.name)

        if overlay_candidates:
            print(f"   Overlays:   {', '.join(overlay_candidates)}")
        else:
            print(f"   Overlays:   (none)")

    # Specific proposal check if provided
    if args.proposal_id and args.bot_id:
        print(f"\n--- Proposal Check: {args.proposal_id} → {args.bot_id} ---")
        binding = resolve_binding(args.bot_id)
        if binding is None:
            print(f"❌ Unknown bot: {args.bot_id}")
        else:
            correct_path = build_host_overlay_path(args.bot_id, args.proposal_id)
            print(f"   Correct host path: {correct_path}")

            # Check if overlay exists at correct path
            if correct_path and Path(correct_path).exists():
                print(f"   ✅ Overlay exists at correct path")
            else:
                print(f"   ❌ Overlay NOT at correct path")

            # Check if overlay exists at wrong path (the dead path)
            wrong_path = Path(
                f"/home/hermes/projects/trading/freqtrade/bots/{args.bot_id.replace('freqtrade-', '')}/user_data/overlay_{args.proposal_id[:8]}.json"
            )
            if wrong_path.exists():
                print(f"   ⚠️  Overlay exists at WRONG (repo-inert) path: {wrong_path}")

    print("\n" + "=" * 60)
    return 0 if valid else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Generate proof report as JSON."""
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = {
        "generated_at_utc": now_utc,
        "mode": "read_only_audit",
        "fleet": {
            "bot_count": len(BOT_RUNTIME_BINDINGS),
            "bindings": {},
            "validation": {},
        },
        "proposal_check": None,
    }

    # Fleet validation
    valid, issues = validate_fleet_bindings()
    report["fleet"]["validation"] = {
        "valid": valid,
        "issues": issues,
    }

    # Per-bot bindings
    for bot_id, binding in BOT_RUNTIME_BINDINGS.items():
        report["fleet"]["bindings"][bot_id] = binding.to_dict()

    # Specific proposal check
    if args.proposal_id and args.bot_id:
        proposal = OverlayProposal(
            proposal_id=args.proposal_id,
            bot_id=args.bot_id,
        )
        result = compute_apply_result(proposal, docker_available=False)
        report["proposal_check"] = result.to_dict()

    # Write output
    output_path = args.output or (
        f"/opt/data/reports/si-v2-apply-actuator-audit-{now_utc.replace(':', '')}.json"
    )
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"Report written: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SI v2 Apply Actuator Audit — read-only fleet validation",
    )
    parser.add_argument(
        "--mode",
        choices=["audit", "report"],
        default="audit",
        help="Operation mode (default: audit)",
    )
    parser.add_argument(
        "--proposal-id",
        type=str,
        default="",
        help="Proposal ID to check (e.g., 65502d13a99bfadd)",
    )
    parser.add_argument(
        "--bot-id",
        type=str,
        default="",
        help="Target bot ID (e.g., freqtrade-freqforge)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output path for report JSON",
    )
    args = parser.parse_args()

    if args.mode == "report":
        return cmd_report(args)
    return cmd_audit(args)


if __name__ == "__main__":
    sys.exit(main())
