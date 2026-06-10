"""Dry-run cron planning and diff logic for SI v2.

Produces a CronPlan that is ALWAYS fully dry-run (no enabled jobs, no
write operations). The diff planner compares a proposed plan against an
existing Hermes jobs.json file but NEVER writes to it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from si_v2.cron.schema import CronDefsFile, CronJobDef


class CronPlanEntry(BaseModel):
    """A single entry in a dry-run cron plan.

    All entries are forced to disabled and dry-run-only — this is
    enforced at the plan-building level.
    """

    model_config = ConfigDict(strict=True)

    job_def: CronJobDef
    proposed_schedule: str
    enabled: bool = False
    dry_run_only: bool = True
    safety_warnings: list[str]
    blocked: bool = False
    block_reason: str = ""


class CronPlan(BaseModel):
    """A complete dry-run cron plan."""

    model_config = ConfigDict(strict=True)

    source_file: str
    generated_at: str
    entries: list[CronPlanEntry]
    disabled_by_default: bool = True
    blocked_jobs: list[CronPlanEntry]
    safety_warnings: list[str]


class CronPlanner:
    """Dry-run planner that reads CronDefsFile and produces CronPlan.

    Every generated plan has all jobs marked enabled=False and
    dry_run_only=True — no exceptions.
    """

    def build_plan(self, defs: CronDefsFile) -> CronPlan:
        """Build a dry-run plan from validated cron definitions.

        Args:
            defs: Validated CronDefsFile instance.

        Returns:
            A CronPlan with all jobs disabled and dry-run-only.
        """
        entries: list[CronPlanEntry] = []
        blocked_entries: list[CronPlanEntry] = []
        global_warnings: list[str] = []

        for job in defs.jobs:
            entry_warnings: list[str] = []
            blocked = False
            block_reason = ""

            # Check for too-frequent schedules
            schedule = job.schedule
            parts = schedule.split()
            if parts and parts[0].startswith("*/"):
                try:
                    n = int(parts[0][2:])
                    if n <= 4:
                        blocked = True
                        block_reason = f"Schedule '{schedule}' runs every {n} minute(s) — too frequent for production"
                        entry_warnings.append(block_reason)
                except ValueError:
                    pass
            elif parts and parts[0] == "*":
                blocked = True
                block_reason = f"Schedule '{schedule}' runs every minute — too frequent"
                entry_warnings.append(block_reason)

            entry = CronPlanEntry(
                job_def=job,
                proposed_schedule=schedule,
                enabled=False,
                dry_run_only=True,
                safety_warnings=entry_warnings,
                blocked=blocked,
                block_reason=block_reason,
            )

            if blocked:
                blocked_entries.append(entry)
                global_warnings.append(f"Blocked job '{job.job_id}': {block_reason}")
            else:
                entries.append(entry)

        # Add a global safety warning about dry-run mode
        if entries:
            global_warnings.append("ALL jobs are disabled by default — no cron jobs will be activated by this plan")
            global_warnings.append("ALL jobs are dry-run only — no real execution will occur")

        generated_at = datetime.now(UTC).isoformat()

        return CronPlan(
            source_file="",
            generated_at=generated_at,
            entries=entries,
            disabled_by_default=True,
            blocked_jobs=blocked_entries,
            safety_warnings=global_warnings,
        )


class CronDiff(BaseModel):
    """Read-only diff between a proposed plan and current Hermes jobs."""

    model_config = ConfigDict(strict=True)

    proposed: CronPlan
    current_path: str
    added: list[CronPlanEntry]
    removed: list[CronPlanEntry]
    changed: list[tuple[CronPlanEntry, CronPlanEntry]]
    unchanged: list[CronPlanEntry]


class CronDiffPlanner:
    """Read-only diff between proposed plan and current Hermes jobs.json.

    Reads jobs.json for comparison but NEVER writes to it. If jobs.json
    does not exist, returns an empty diff with a warning.
    """

    def diff(self, plan: CronPlan, current_jobs_path: Path) -> CronDiff:
        """Compute a read-only diff between plan and current jobs.

        Args:
            plan: The proposed cron plan.
            current_jobs_path: Path to the existing Hermes jobs.json file.

        Returns:
            A CronDiff reflecting what would change. All entries in the
            plan are treated as 'added' since none are enabled.
        """
        current_path = str(current_jobs_path)

        if not current_jobs_path.exists():
            warning = f"Current jobs file '{current_jobs_path}' does not exist — returning empty diff"
            modified_plan = plan.model_copy(deep=True)
            modified_plan.safety_warnings = [*list(plan.safety_warnings), warning]
            return CronDiff(
                proposed=modified_plan,
                current_path=current_path,
                added=[],
                removed=[],
                changed=[],
                unchanged=[],
            )

        # Read current jobs (simple JSON read, no write)
        import json  # import locally to avoid top-level side effects

        with open(current_jobs_path) as f:
            current_data = json.load(f)

        def _to_str_dict(d: dict[str, object]) -> dict[str, str]:
            """Convert a dict's values to strings for type safety."""
            return {k: str(v) for k, v in d.items() if isinstance(v, (str, int, float, bool))}

        # Build a lookup of current job IDs
        current_jobs: dict[str, dict[str, str]] = {}
        if isinstance(current_data, list):
            for entry in current_data:
                if isinstance(entry, dict):
                    job_id = str(entry.get("id", entry.get("job_id", "")))
                    current_jobs[job_id] = _to_str_dict(entry)
        elif isinstance(current_data, dict):
            current_jobs_raw = current_data.get("jobs", current_data.get("entries", []))
            if isinstance(current_jobs_raw, list):
                for entry in current_jobs_raw:
                    if isinstance(entry, dict):
                        job_id = str(entry.get("id", entry.get("job_id", "")))
                        current_jobs[job_id] = _to_str_dict(entry)
            elif isinstance(current_jobs_raw, dict):
                current_jobs = {str(k): _to_str_dict(v) for k, v in current_jobs_raw.items() if isinstance(v, dict)}

        added: list[CronPlanEntry] = []
        removed: list[CronPlanEntry] = []
        changed: list[tuple[CronPlanEntry, CronPlanEntry]] = []
        unchanged: list[CronPlanEntry] = []

        for entry in plan.entries:
            job_id = entry.job_def.job_id
            if job_id in current_jobs:
                current_entry = current_jobs[job_id]
                current_schedule = current_entry.get("schedule", "")
                if current_schedule != entry.proposed_schedule:
                    changed.append((entry, entry))
                else:
                    unchanged.append(entry)
            else:
                added.append(entry)

        return CronDiff(
            proposed=plan,
            current_path=current_path,
            added=added,
            removed=removed,
            changed=changed,
            unchanged=unchanged,
        )
