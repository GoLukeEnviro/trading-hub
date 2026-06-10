#!/usr/bin/env python3
"""CLI entry point for SI v2 cron planning.

Usage:
    python scripts/cron_planner.py validate <file>
    python scripts/cron_planner.py render-plan <file> [--output <path>]
    python scripts/cron_planner.py diff-readonly <file> [--current-jobs <path>]

All commands are dry-run only — no apply/install/write/delete operations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from si_v2.cron.cli import CronCLI


def main() -> None:
    """Parse arguments and dispatch to the appropriate CLI command."""
    parser = argparse.ArgumentParser(
        description="SI v2 Cron Planner — dry-run only",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate a jobs.yaml file"
    )
    validate_parser.add_argument(
        "file", type=Path, help="Path to jobs.yaml file"
    )

    # render-plan
    render_parser = subparsers.add_parser(
        "render-plan", help="Generate dry-run cron plan"
    )
    render_parser.add_argument(
        "file", type=Path, help="Path to jobs.yaml file"
    )
    render_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON path (must be inside self_improvement_v2/)",
    )

    # diff-readonly
    diff_parser = subparsers.add_parser(
        "diff-readonly", help="Read-only diff between plan and current jobs"
    )
    diff_parser.add_argument(
        "file", type=Path, help="Path to jobs.yaml file"
    )
    diff_parser.add_argument(
        "--current-jobs", "-j",
        type=Path,
        default=None,
        help="Path to current Hermes jobs.json",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        sys.exit(CronCLI.cmd_validate(args.file))
    elif args.command == "render-plan":
        sys.exit(CronCLI.cmd_render_plan(args.file, args.output))
    elif args.command == "diff-readonly":
        sys.exit(CronCLI.cmd_diff_readonly(args.file, args.current_jobs))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
