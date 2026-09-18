#!/usr/bin/env python3
"""CLI for the SI-v2 apply-chain evaluation stage (AUTONOMOUS_DRY_RUN).

Runs one canary-only, fail-closed evaluation of the newest real cycle
candidate and records the outcome. Writes records and (for a qualified
canary candidate) prepared artifacts; never executes a runtime action.

Usage:
    python3 si_v2_apply_chain_evaluator.py [--repo-root PATH] [--state-dir PATH]

Output: structured key=value lines. A line prefixed with
``SI-V2 APPLY-CHAIN ALERT`` is emitted for BLOCKER and PREPARED events;
NO_APPLY stays silent (healthy alert channel).

Safety: no live trading, no dry_run change, no Docker call, no runtime
execution. Runtime execution is deliberately not wired in this stage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SI_V2_DIR = _SCRIPTS_DIR.parent
_SRC_DIR = _SI_V2_DIR / "src"
_REPO_ROOT = _SI_V2_DIR.parent
sys.path.insert(0, str(_SRC_DIR))

from si_v2.pipeline.apply_chain_evaluation import (  # noqa: E402
    DEFAULT_STATE_DIR,
    ApplyChainEvaluationInput,
    evaluate_apply_chain,
    write_evaluation_record,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SI-v2 apply-chain evaluation stage (canary-only, fail-closed)."
    )
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--bundle", default=None)
    parser.add_argument("--marker", default=None)
    parser.add_argument("--kill-switch", default=None)
    parser.add_argument("--riskguard", default=None)
    parser.add_argument("--canary-config", default=None)
    parser.add_argument("--cycle-log-dir", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_ = ApplyChainEvaluationInput(
        repo_root=Path(args.repo_root),
        state_dir=Path(args.state_dir),
        bundle_path=Path(args.bundle) if args.bundle else None,
        marker_path=Path(args.marker) if args.marker else None,
        kill_switch_path=Path(args.kill_switch) if args.kill_switch else None,
        riskguard_state_path=Path(args.riskguard) if args.riskguard else None,
        canary_config_path=Path(args.canary_config) if args.canary_config else None,
        cycle_log_dir=Path(args.cycle_log_dir) if args.cycle_log_dir else None,
    )
    result = evaluate_apply_chain(input_)
    paths = write_evaluation_record(result, input_.state_dir)

    print(f"apply_chain_status={result.status}")
    print(f"apply_chain_event={result.event}")
    print(f"apply_chain_reason={result.reason}")
    print(f"apply_chain_cycle={result.cycle_id or 'none'}")
    print(f"apply_chain_record={paths['record_path']}")
    if result.is_alert():
        print(
            "SI-V2 APPLY-CHAIN ALERT: "
            f"status={result.status} event={result.event} reason={result.reason}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
