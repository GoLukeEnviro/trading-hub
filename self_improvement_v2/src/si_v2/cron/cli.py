"""Dry-run-only CLI for SI v2 cron planning.

No apply/install/write/delete commands. All operations are purely
analytical — they validate, render, and diff without side effects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from si_v2.cron.planner import CronDiffPlanner, CronPlanner
from si_v2.cron.schema import CronDefsLoader


class CronCLI:
    """Dry-run-only CLI. No apply/install/write/delete commands."""

    @staticmethod
    def cmd_validate(file: Path) -> int:
        """Validate a jobs.yaml file.

        Args:
            file: Path to the YAML file to validate.

        Returns:
            0 if valid, 1 if invalid.
        """
        file_path = Path(file)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            return 1

        try:
            defs = CronDefsLoader.load(file_path)
            print(f"OK: {file_path} is valid ({len(defs.jobs)} job(s) defined)")
            for job in defs.jobs:
                print(f"  - {job.job_id}: {job.phase.value} @ {job.schedule}")
            return 0
        except Exception as e:
            print(f"ERROR: {file_path} is invalid: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def cmd_render_plan(file: Path, output_json: Path | None = None) -> int:
        """Generate a dry-run cron plan from a jobs.yaml file.

        All jobs in the output are marked enabled=False.

        Args:
            file: Path to the YAML file.
            output_json: Optional path to write JSON output. Must be
                inside the self_improvement_v2/ directory.

        Returns:
            0 on success, 1 on error.
        """
        file_path = Path(file)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            return 1

        if output_json is not None:
            output_path = Path(output_json).resolve()
            # Refuse output path outside self_improvement_v2/
            if "self_improvement_v2" not in output_path.parts:
                print(
                    f"ERROR: Output path must be inside self_improvement_v2/ directory. Got: {output_path}",
                    file=sys.stderr,
                )
                return 1

        try:
            defs = CronDefsLoader.load(file_path)
            planner = CronPlanner()
            plan = planner.build_plan(defs)
            plan.source_file = str(file_path)

            output = plan.model_dump(mode="json", exclude_none=True)

            if output_json is not None:
                output_path = Path(output_json)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(output, f, indent=2)
                print(f"Plan written to {output_path}")
            else:
                print(json.dumps(output, indent=2))

            # Print summary to stderr
            total = len(plan.entries)
            blocked = len(plan.blocked_jobs)
            warnings = len(plan.safety_warnings)
            print(
                f"Summary: {total} job(s), {blocked} blocked, {warnings} warning(s)",
                file=sys.stderr,
            )

            return 0
        except Exception as e:
            print(f"ERROR: Failed to render plan: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def cmd_diff_readonly(file: Path, current_jobs: Path | None = None) -> int:
        """Compute a read-only diff between plan and current Hermes jobs.

        Reads jobs.json for comparison but NEVER writes to it.

        Args:
            file: Path to the YAML definitions file.
            current_jobs: Path to current Hermes jobs.json. If not
                provided, defaults to searching common locations.

        Returns:
            0 on success, 1 on error.
        """
        file_path = Path(file)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            return 1

        if current_jobs is None:
            # Try common locations
            candidates = [
                Path.home() / ".hermes" / "cron" / "jobs.json",
                Path.home() / ".hermes" / "jobs.json",
                Path.cwd() / "jobs.json",
            ]
            for candidate in candidates:
                if candidate.exists():
                    current_jobs = candidate
                    break

        try:
            defs = CronDefsLoader.load(file_path)
            planner = CronPlanner()
            plan = planner.build_plan(defs)
            plan.source_file = str(file_path)

            diff_planner = CronDiffPlanner()
            diff_path = current_jobs if current_jobs is not None else Path("jobs.json")
            diff = diff_planner.diff(plan, diff_path)

            output = diff.model_dump(mode="json", exclude_none=True)
            print(json.dumps(output, indent=2))

            # Print warnings
            for w in diff.proposed.safety_warnings:
                print(f"WARNING: {w}", file=sys.stderr)

            return 0
        except Exception as e:
            print(f"ERROR: Failed to compute diff: {e}", file=sys.stderr)
            return 1
