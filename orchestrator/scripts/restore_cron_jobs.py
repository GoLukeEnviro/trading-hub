#!/usr/bin/env python3
"""restore_cron_jobs.py — Merge-safe, SI-v2-safe cron registry restore.

Replaces the old wholesale ``cp backup -> live`` logic which could shrink the
live 58-job registry down to a stale 11-job backup and thereby DELETE the
SI-v2 active-cycle job (id ``64866012641a``).

Guarantees (enforced here and covered by unit tests):

* **Backup validity gate** — a backup that does NOT contain the protected job
  id ``64866012641a`` is treated as INVALID and is never used for merge, add or
  recovery. This prevents stale backup-only jobs from leaking into the live
  registry.
* **Add-only / merge-safe** — restore only ADDS jobs that are missing from live
  (matched by ``id``). It never removes or overwrites an existing live job.
* **No-shrink guard** — the planned result is never smaller than the current
  live registry.
* **SI-v2 invariant** — the planned result must contain ``64866012641a``,
  otherwise the write is refused.
* **--dry-run never writes.**

Environment overrides (defaults match the runtime layout inside hermes-green):

    CRON_JOBS_DB      default /opt/data/profiles/orchestrator/cron/jobs.json
    CRON_JOBS_BACKUP  default <repo>/orchestrator/config/cron_jobs_backup.json
    CRON_RESTORE_LOG  default <repo>/orchestrator/logs/cron_restore.log

Exit codes: ``0`` for all safe outcomes (no-op, refuse, dry-run, successful
restore); ``1`` only for hard errors (unreadable files, write failure). A refuse
is logged loudly but does not flap the cron job.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Job id that must never be removed by a restore (SI-v2 active cycle).
PROTECTED_IDS: tuple[str, ...] = ("64866012641a",)
SI_V2_NAME = "si-v2-active-cycle"

REPO = "/home/hermes/projects/trading"
DEFAULT_DB = "/opt/data/profiles/orchestrator/cron/jobs.json"
DEFAULT_BACKUP = f"{REPO}/orchestrator/config/cron_jobs_backup.json"
DEFAULT_LOG = f"{REPO}/orchestrator/logs/cron_restore.log"


# ── small self-contained JSON helpers (no external runtime import) ──────────

def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def write_json_atomic(path: str | Path, data: Any) -> None:
    """Write JSON to a temp file in the same dir, then atomically replace."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── registry helpers ───────────────────────────────────────────────────────

def extract_jobs(container: Any) -> list[dict]:
    if isinstance(container, list):
        return [j for j in container if isinstance(j, dict)]
    if isinstance(container, dict):
        return [j for j in container.get("jobs", []) if isinstance(j, dict)]
    return []


def job_ids(jobs: list[dict]) -> set[str]:
    return {j.get("id") for j in jobs if j.get("id") is not None}


def backup_is_valid(backup_jobs: list[dict], protected: tuple[str, ...] = PROTECTED_IDS) -> bool:
    """A backup is valid only if it contains every protected job id."""
    ids = job_ids(backup_jobs)
    return all(pid in ids for pid in protected)


# ── core: pure, unit-testable merge plan ───────────────────────────────────

def plan_merge(
    live_jobs: list[dict],
    backup_jobs: list[dict],
    protected: tuple[str, ...] = PROTECTED_IDS,
) -> dict:
    """Compute a non-destructive restore plan.

    Returns ``{valid_backup, refuse_reason, add, planned, planned_ids}``.

    * ``valid_backup`` — False if the backup lacks a protected id (INVALID).
    * ``refuse_reason`` — set whenever NO write must happen; None means "ok to apply".
    * ``add`` — backup jobs (by id) not present in live (may be empty).
    * ``planned`` — live + add (the would-be new registry).
    """
    if not backup_is_valid(backup_jobs, protected):
        return {
            "valid_backup": False,
            "refuse_reason": "INVALID_BACKUP_NO_PROTECTED_JOB",
            "add": [],
            "planned": list(live_jobs),
            "planned_ids": job_ids(live_jobs),
        }

    live_ids = job_ids(live_jobs)
    add = [j for j in backup_jobs if j.get("id") not in live_ids]
    planned = list(live_jobs) + add
    planned_ids = job_ids(planned)

    if len(planned) < len(live_jobs):  # defensive: add-only can never shrink
        return {
            "valid_backup": True,
            "refuse_reason": "NO_SHRINK_VIOLATION",
            "add": [],
            "planned": list(live_jobs),
            "planned_ids": job_ids(live_jobs),
        }
    if not all(pid in planned_ids for pid in protected):
        return {
            "valid_backup": True,
            "refuse_reason": "PROTECTED_JOB_MISSING_AFTER_MERGE",
            "add": [],
            "planned": list(live_jobs),
            "planned_ids": job_ids(live_jobs),
        }

    return {
        "valid_backup": True,
        "refuse_reason": None,
        "add": add,
        "planned": planned,
        "planned_ids": planned_ids,
    }


# ── entrypoint ─────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(log_path: str, message: str) -> None:
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{_ts()}] {message}\n")
    except OSError:
        # Logging must never break the restore path.
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv

    db_path = os.environ.get("CRON_JOBS_DB", DEFAULT_DB)
    backup_path = os.environ.get("CRON_JOBS_BACKUP", DEFAULT_BACKUP)
    log_path = os.environ.get("CRON_RESTORE_LOG", DEFAULT_LOG)

    _log(log_path, "restore_cron_jobs.sh started (merge-safe)")

    try:
        live_raw = read_json(db_path)
        backup_raw = read_json(backup_path)
    except (OSError, ValueError) as exc:
        _log(log_path, f"FATAL: cannot read db/backup: {exc}")
        return 1

    live_jobs = extract_jobs(live_raw)
    backup_jobs = extract_jobs(backup_raw)
    live_is_list = isinstance(live_raw, list)

    plan = plan_merge(live_jobs, backup_jobs)

    if not plan["valid_backup"]:
        # INVALID backup (no protected/SI-v2 job) — refuse completely, never add.
        _log(
            log_path,
            "CRITICAL: backup invalid (no protected job "
            f"{'/'.join(PROTECTED_IDS)}) — refusing restore, no write",
        )
        print("REFUSE: invalid backup (no protected job); no write")
        return 0

    if plan["refuse_reason"]:
        _log(log_path, f"REFUSE: {plan['refuse_reason']} — no write")
        print(f"REFUSE: {plan['refuse_reason']}; no write")
        return 0

    add_ids = [j.get("id") for j in plan["add"]]
    if not add_ids:
        _log(log_path, f"Already {len(live_jobs)} jobs registered. Skip.")
        print(f"OK: already complete ({len(live_jobs)} jobs); skip")
        return 0

    if dry_run:
        _log(log_path, f"DRY-RUN: would add {len(add_ids)} job(s): {add_ids}")
        print(f"DRY-RUN: would add {len(add_ids)} job(s): {add_ids}")
        return 0

    # Apply: preserve the live container shape, replace only the jobs list.
    new_raw = plan["planned"] if live_is_list else {**live_raw, "jobs": plan["planned"]}
    try:
        write_json_atomic(db_path, new_raw)
    except OSError as exc:
        _log(log_path, f"FATAL: write failed: {exc}")
        return 1

    # Re-assert the SI-v2 invariant on the freshly written file.
    try:
        after = read_json(db_path)
        after_ids = job_ids(extract_jobs(after))
    except (OSError, ValueError) as exc:
        _log(log_path, f"FATAL: post-write verify failed: {exc}")
        return 1
    if not all(pid in after_ids for pid in PROTECTED_IDS):
        _log(log_path, "CRITICAL: protected job missing after write — manual review required")
        return 1

    _log(
        log_path,
        f"RESTORED: added {len(add_ids)} job(s) {add_ids}; "
        f"registry now {len(extract_jobs(after))} jobs; protected job present",
    )
    print(f"OK: restored {len(add_ids)} job(s); protected job present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
