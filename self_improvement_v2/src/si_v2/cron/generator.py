"""Cron job generator for scheduled SI v2 tasks.

Reads bot schedule definitions from jobs.yaml and generates Hermes cron
job specification dicts. This is a pure function with no side effects —
it does NOT install or activate cron jobs.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# Path to the cron definitions relative to this package
_CRON_DEFS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "cron_defs"


def generate_cron_specs(jobs_path: str | Path | None = None) -> list[dict[str, str]]:
    """Generate Hermes cron job specification dicts from jobs.yaml.

    Args:
        jobs_path: Path to jobs.yaml file. Defaults to cron_defs/jobs.yaml
                   relative to the package root.

    Returns:
        List of cron job specification dicts with keys:
        schedule, script, deliver, workdir.
    """
    jobs_path = _CRON_DEFS_DIR / "jobs.yaml" if jobs_path is None else Path(jobs_path)

    if not jobs_path.exists():
        return []

    with open(jobs_path) as f:
        data = yaml.safe_load(f)

    if not data or "bots" not in data:
        return []

    specs: list[dict[str, str]] = []
    workdir = str(jobs_path.parent.parent.resolve())

    for bot in data["bots"]:
        bot_id = bot["bot_id"]
        schedules = bot.get("schedules", {})

        for schedule_name, schedule_cron in schedules.items():
            script_name = f"si_v2_{schedule_name}"
            spec: dict[str, str] = {
                "schedule": str(schedule_cron),
                "script": script_name,
                "deliver": f"si-v2-{schedule_name}-{bot_id}",
                "workdir": workdir,
                "bot_id": bot_id,
                "task": schedule_name,
            }
            specs.append(spec)

    return specs
