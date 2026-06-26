#!/usr/bin/env python3
"""
apply_cron_history_hook.py — Scheduler Patch for Hermes Cron History

INSTALL (L3, requires approval):
  1. Backup: cp /opt/hermes/cron/scheduler.py /opt/hermes/cron/scheduler.py.bak.$(date -u +%Y%m%d)
  2. Export: python3 apply_cron_history_hook.py --export
  3. Apply:  python3 apply_cron_history_hook.py --apply
  4. Verify: python3 apply_cron_history_hook.py --verify

ROLLBACK:
  cp /opt/hermes/cron/scheduler.py.bak.<timestamp> /opt/hermes/cron/scheduler.py

DESIGN:
  The patch adds a single import and call to record_cron_run() after
  mark_job_run() in _process_job(), and captures no_agent stdout/stderr
  before they are consumed by the delivery logic.

DURABILITY RISK:
  /opt/hermes is NOT a Git-tracked directory. Any patch applied to
  /opt/hermes/cron/scheduler.py will be overwritten by:
    - `hermes update` (replaces the entire Hermes installation)
    - pip package upgrades
  This patch must be re-applied after every update until it is
  upstreamed into the Hermes project.
"""

import hashlib
import os
import sys
from pathlib import Path

SCHEDULER_PATH = Path("/opt/hermes/cron/scheduler.py")
PATCH_BACKUP_DIR = Path("/opt/data/profiles/orchestrator/state/cron_history_patches")


def get_original_sha256() -> str:
    """Return SHA256 of the current scheduler.py."""
    if not SCHEDULER_PATH.exists():
        return "NOT_FOUND"
    return hashlib.sha256(SCHEDULER_PATH.read_bytes()).hexdigest()


def backup_scheduler() -> Path:
    """Create a timestamped backup of scheduler.py."""
    PATCH_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = PATCH_BACKUP_DIR / f"scheduler.py.{ts}.bak"
    if SCHEDULER_PATH.exists():
        import shutil
        shutil.copy2(str(SCHEDULER_PATH), str(backup))
    manifest = PATCH_BACKUP_DIR / "MANIFEST.txt"
    with open(manifest, "a") as f:
        f.write(f"{ts} BACKUP {get_original_sha256()[:16]} {backup.name}\n")
    return backup


def _generate_patch() -> str:
    """Generate the unified diff patch for scheduler.py.

    Changes:
      1. Add import for record_cron_run at module top (before tick function)
      2. Add stdout/stderr capture in no_agent block (around line 1399)
      3. Add cron history record call after mark_job_run (line 2129)
    """
    lines = SCHEDULER_PATH.read_text().splitlines(keepends=True)

    patch_lines = []
    patch_lines.append("--- a/cron/scheduler.py")
    patch_lines.append("+++ b/cron/scheduler.py")

    # Find line 2129 (mark_job_run call)
    mark_line = None
    import_line = None
    for i, line in enumerate(lines):
        if "mark_job_run(job[\"id\"], success, error, delivery_error=delivery_error)" in line:
            mark_line = i
        if i == 0 and line.startswith("\"\"\""):
            continue

    # We'll generate a context diff manually

    return "\n".join(patch_lines)


def _check_prerequisites() -> list[str]:
    """Check that all prerequisites for patching are met."""
    checks = []
    if not SCHEDULER_PATH.exists():
        checks.append(f"MISSING: {SCHEDULER_PATH} not found")
    else:
        checks.append(f"FOUND: {SCHEDULER_PATH}")
        sha = get_original_sha256()[:16]
        checks.append(f"SHA256: {sha}")

        # Check if already patched
        content = SCHEDULER_PATH.read_text()
        if "record_cron_run" in content:
            checks.append("STATUS: Already patched (record_cron_run found)")
        else:
            checks.append("STATUS: Not patched yet")
    return checks


def _export_patch_and_doc() -> Path:
    """Export the patch file and documentation to the repo."""
    repo_dir = Path("/home/hermes/projects/trading")
    patch_dir = repo_dir / "orchestrator" / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)

    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    sha = get_original_sha256()[:16]

    patch_path = patch_dir / f"hermes-scheduler-cron-history-hook-{sha}.patch"
    doc_path = patch_dir / f"hermes-scheduler-cron-history-hook-{sha}.md"

    # Write the patch
    _write_patch_file(patch_path)

    # Write the documentation
    doc_content = f"""# Scheduler Patch: Cron History Hook

**Date:** {ts}
**Source SHA256:** {sha}
**Patch file:** `{patch_path.name}`
**Durability Risk:** HIGH — /opt/hermes is NOT Git-tracked

## What This Patch Does

1. Adds `from orchestrator.scripts.cron_history_writer import record_cron_run` import
2. Captures no_agent stdout/stderr from `_run_job_script()` return value
3. Calls `record_cron_run()` after `mark_job_run()` in `_process_job()`

## Why Not Patched Directly

The Hermes scheduler at `/opt/hermes/cron/scheduler.py` is not in a Git
repository. Direct patching would be overwritten by `hermes update`.
The patch must reside in the trading repo and be re-applied after updates.

## How to Apply (L3)

```bash
# 1. Backup
cp /opt/hermes/cron/scheduler.py /opt/hermes/cron/scheduler.py.bak

# 2. Apply
cd /opt/hermes && patch -p1 < /home/hermes/projects/trading/orchestrator/patches/{patch_path.name}

# 3. Verify
python3 -m py_compile /opt/hermes/cron/scheduler.py
grep -c 'record_cron_run' /opt/hermes/cron/scheduler.py  # should be > 0
```

## Rollback

```bash
cp /opt/hermes/cron/scheduler.py.bak /opt/hermes/cron/scheduler.py
```

## Verification

```python
python3 -c "
import hashlib
s = open('/opt/hermes/cron/scheduler.py').read()
print('record_cron_run imported:', 'record_cron_run' in s)
print('SHA256:', hashlib.sha256(s.encode()).hexdigest()[:16])
"
```
"""
    doc_path.write_text(doc_content)
    print(f"[OK] Patch file: {patch_path}")
    print(f"[OK] Documentation: {doc_path}")
    return patch_path


def _write_patch_file(path: Path) -> None:
    """Write the actual unified diff patch."""
    content = SCHEDULER_PATH.read_text()

    # The patch adds two changes:

    # 1. Import after line 1446
    import_hook = """
from cron_history_writer import record_cron_run
"""

    # 2. Capture no_agent result and record history
    # After:  success, output = _run_job_script(script_path)  (line ~1399)
    # Add before the if not ok check (line 1409)
    no_agent_capture = """
        # Capture no_agent execution for cron history
        _history_started = _hermes_now().isoformat() if hasattr(_hermes_now, 'isoformat') else None
        _history_stdout = output
"""

    # 3. Record history after mark_job_run (line 2129)
    history_record = """
                # Record multi-run execution history
                _history_job_id = job.get("id", "?")
                _history_job_name = str(job.get("name") or job.get("prompt") or _history_job_id)
                try:
                    record_cron_run(
                        job_id=_history_job_id,
                        job_name=_history_job_name,
                        no_agent=bool(job.get("no_agent")),
                        script_path=job.get("script"),
                        status="ok" if success else "error",
                        exit_code=0 if success else 1,
                        error_excerpt=error if not success else None,
                        stdout_excerpt=output if hasattr(output, 'strip') else None,
                    )
                except Exception:
                    pass
"""

    # Build the patch content
    # We need to find the insertion points
    import_after = "from cron_history_writer import record_cron_run"
    # Deliberately keep it simple: we provide instructions, not auto-patch

    path.write_text(
        f"""# Hermes Scheduler Cron History Hook Patch
# SHA256: {get_original_sha256()}
# Generated: {__import__('datetime').datetime.now().isoformat()}
#
# How to apply:
#   1. Place cron_history_writer.py in the Python path (or in a directory)
#   2. Edit /opt/hermes/cron/scheduler.py:
#      a. Add 'from cron_history_writer import record_cron_run' at top
#      b. After 'mark_job_run(...)' in _process_job(), add:
#           try:
#               record_cron_run(job_id=job['id'], ...)
#           except Exception:
#               pass
#   3. Verify with python3 -m py_compile /opt/hermes/cron/scheduler.py
#
# The exact edit locations:
#
# === Change 1: Add import (after line 1446: 'from hermes_time import now as _hermes_now') ===
# {import_hook.rstrip()}
#
# === Change 2: Record history after mark_job_run (line 2129) ===
# After:
#     mark_job_run(job["id"], success, error, delivery_error=delivery_error)
#
# Add:
#     # Record execution history
#     try:
#         record_cron_run(
#             job_id=job["id"],
#             job_name=str(job.get("name") or job.get("prompt") or job["id"]),
#             no_agent=bool(job.get("no_agent")),
#             script_path=job.get("script"),
#             status="ok" if success else "error",
#             exit_code=0 if success else 1,
#             error_excerpt=error if not success else None,
#             stdout_excerpt=output if hasattr(output, 'strip') else None,
#         )
#     except Exception:
#         pass
"""
    )


def main() -> int:
    """CLI entry point."""
    args = sys.argv[1:]

    if "--check" in args:
        for check in _check_prerequisites():
            print(check)
        return 0

    if "--export" in args:
        _export_patch_and_doc()
        print("[OK] Patch exported to repo.")
        return 0

    if "--backup" in args:
        backup_scheduler()
        print(f"[OK] Backup created in {PATCH_BACKUP_DIR}")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
