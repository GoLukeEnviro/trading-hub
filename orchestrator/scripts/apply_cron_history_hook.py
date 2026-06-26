#!/usr/bin/env python3
"""
apply_cron_history_hook.py — Real Hermes Cron History Hook Patch Manager

Patches /opt/hermes/cron/scheduler.py (or a test fixture via --target) to insert
a best-effort cron-history call after every mark_job_run(...) call inside
_process_job(). The hook is idempotent: re-running --apply does nothing if the
markers are already present.

CLI MODES (all read scheduler.py, none of them edit jobs.json):

    --status                Report current patch state (unpatched / patched / drifted).
                            Performs no writes. Exit 0 always.
    --dry-run               Show exactly what would change. Performs no writes.
    --backup                Create a timestamped backup + MANIFEST.jsonl entry.
                            Performs no patch.
    --apply                 backup -> patch -> verify (no restart, no jobs.json edit).
                            Idempotent: a second --apply is a no-op.
    --verify                Confirm hook markers are present and target compiles.
                            Performs no writes.
    --rollback BACKUP_PATH  Restore exact bytes from BACKUP_PATH (verified by SHA256).
                            Performs no further patch.

OPTIONS:

    --target PATH           Override scheduler.py path (TESTS ONLY).
    --backup-dir PATH       Override backup directory (TESTS ONLY).
    --jobs-json PATH        Reference jobs.json to assert we never mutate it
                            (read-only; used by tests). Never written by this tool.

DURABILITY:

    /opt/hermes is NOT a Git repository. Any patch applied to
    /opt/hermes/cron/scheduler.py is OVERWRITTEN by `hermes update`. The
    markers and idempotency here make the patch re-applicable after every
    update. See docs/runbooks/hermes-cron-history-design.md.

SAFETY:

    - Never writes to jobs.json.
    - Never restarts any service.
    - Never prints secrets, tokens, or credentials.
    - Writes only to:
        * <backup-dir>/scheduler.py.<ts>.bak
        * <backup-dir>/MANIFEST.jsonl
        * <target>  (only via --apply, after backup)

MARKER LAYOUT in patched scheduler.py:

    # HERMES_CRON_HISTORY_HOOK_BEGIN
    <import block>
    # HERMES_CRON_HISTORY_HOOK_END

    ...(original code)...

    mark_job_run(...)
    # HERMES_CRON_HISTORY_HOOK_CALL_BEGIN
    <hook call block>
    # HERMES_CRON_HISTORY_HOOK_CALL_END

EXIT CODES:

    0   OK (status, dry-run summary, successful backup/apply/verify/rollback)
    1   user error (bad args, missing target, missing backup)
    2   state error (patch drifted, sha mismatch on rollback)
    3   compile error (py_compile failed on patched target)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER_IMPORT_BEGIN = "# HERMES_CRON_HISTORY_HOOK_BEGIN"
MARKER_IMPORT_END = "# HERMES_CRON_HISTORY_HOOK_END"
MARKER_CALL_BEGIN = "# HERMES_CRON_HISTORY_HOOK_CALL_BEGIN"
MARKER_CALL_END = "# HERMES_CRON_HISTORY_HOOK_CALL_END"

# Canonical runtime target. Override via --target for tests only.
DEFAULT_TARGET = Path("/opt/hermes/cron/scheduler.py")
DEFAULT_BACKUP_DIR = Path(
    "/opt/data/profiles/orchestrator/state/cron_history_patches"
)
DEFAULT_JOBS_JSON = Path("/opt/data/profiles/orchestrator/cron/jobs.json")

# Where cron_history_writer.py lives at runtime. The scheduler must be able
# to import it. We insert this into sys.path defensively (if not already
# present) so a re-deploy doesn't accidentally break the import.
RUNTIME_WRITER_DIR = "/opt/data/profiles/orchestrator/scripts"


# ---------------------------------------------------------------------------
# Marker block builders
# ---------------------------------------------------------------------------

IMPORT_BLOCK_TEMPLATE = '''{import_begin}
try:
    import sys as _hermes_cron_sys
    _HERMES_CRON_HISTORY_DIR = "{writer_dir}"
    if _HERMES_CRON_HISTORY_DIR not in _hermes_cron_sys.path:
        _hermes_cron_sys.path.insert(0, _HERMES_CRON_HISTORY_DIR)
    from cron_history_writer import run_with_history as _hermes_cron_run_with_history
except Exception:  # pragma: no cover - best-effort fallback
    def _hermes_cron_run_with_history(*_a, **_kw):
        return False
{import_end}
'''


CALL_BLOCK_TEMPLATE = '''{call_begin}
try:
    _hermes_cron_run_with_history(
        {job_expr},
        no_agent=bool({job_expr}.get("no_agent")),
        status="ok" if {success_expr} else "error",
        error_text=({error_expr}) if not {success_expr} else None,
        stdout_text={output_expr},
        finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    )
except Exception:
    pass
{call_end}
'''


def build_import_block() -> str:
    return IMPORT_BLOCK_TEMPLATE.format(
        import_begin=MARKER_IMPORT_BEGIN,
        import_end=MARKER_IMPORT_END,
        writer_dir=RUNTIME_WRITER_DIR,
    )


def _common_call_body(indent: str, job_expr: str, success_expr: str, error_expr: str, output_expr: str) -> str:
    """Return the inner body lines of the hook call block (without markers).
    `indent` is the leading whitespace of the call-site line (e.g. '    '
    for one level inside a function). All body lines are positioned RELATIVE
    to that indent:
      - `try:` line:    indent + ""  (same as call site)
      - inner lines:    indent + "    "
      - `except:` line: indent + ""
      - `pass`:         indent + "    "
    """
    # Build with no template indentation, then prepend the correct indent to
    # each line so the result is exactly right for the call site.
    body = (
        "try:\n"
        "    _hermes_cron_run_with_history(\n"
        "        {job},\n"
        "        no_agent=bool({job}.get(\"no_agent\")),\n"
        "        status=\"ok\" if {success} else \"error\",\n"
        "        error_text=({error}) if not {success} else None,\n"
        "        stdout_text={stdout},\n"
        "        finished_at=__import__(\"datetime\").datetime.now(__import__(\"datetime\").timezone.utc).isoformat(),\n"
        "    )\n"
        "except Exception:\n"
        "    pass\n"
    ).format(job=job_expr, success=success_expr, error=error_expr, stdout=output_expr)
    # Re-indent each line: first `try` and `except` get `indent`, deeper lines
    # keep their existing 4/8-space offset relative to the base.
    out_lines = []
    for line in body.splitlines():
        if not line.strip():
            out_lines.append("")
            continue
        # Count existing leading ws (4 or 8 or 0)
        existing = len(line) - len(line.lstrip())
        if existing == 0:
            out_lines.append(indent + line)
        elif existing == 4:
            out_lines.append(indent + "    " + line.lstrip())
        elif existing == 8:
            out_lines.append(indent + "        " + line.lstrip())
        else:
            out_lines.append(indent + " " * existing + line.lstrip())
    return "\n".join(out_lines) + "\n"


def _build_call_block_with_indent(indent: str, *, happy: bool) -> str:
    """Build a CALL_BLOCK pre-indented to `indent`. The CALL_BLOCK_BEGIN
    marker line itself is emitted at column 0 so it is trivially greppable
    in the target file; subsequent lines of the block are at `indent` or
    deeper. We do NOT indent the markers because:
      - they are pure comment lines, not executable code
      - leaving them at column 0 makes --verify trivial
      - stripping them in --apply (idempotent re-apply) only needs to
        look for the bare marker text
    """
    if happy:
        job_expr = "job"
        success_expr = "success"
        error_expr = "error or delivery_error"
        output_expr = "output if isinstance(output, str) else None"
    else:
        job_expr = "job"
        success_expr = "False"
        error_expr = "str(e)"
        output_expr = "None"
    body = _common_call_body(indent, job_expr, success_expr, error_expr, output_expr)
    return (
        f"{MARKER_CALL_BEGIN}\n"
        f"{body}"
        f"{MARKER_CALL_END}\n"
    )


# ---------------------------------------------------------------------------
# Target / backup helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_utc_compact() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_backup_dir(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)


def _append_manifest(backup_dir: Path, entry: dict) -> None:
    manifest = backup_dir / "MANIFEST.jsonl"
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def backup_target(target: Path, backup_dir: Path) -> Path:
    """Create a timestamped backup of `target` into `backup_dir`.

    Returns the backup path. The MANIFEST.jsonl gets one entry per backup
    so any rollback can be cross-checked.
    """
    if not target.exists():
        raise FileNotFoundError(f"target not found: {target}")
    _ensure_backup_dir(backup_dir)
    ts = _now_utc_compact()
    backup_path = backup_dir / f"{target.name}.{ts}.bak"
    shutil.copy2(str(target), str(backup_path))
    _append_manifest(
        backup_dir,
        {
            "ts_utc": ts,
            "action": "BACKUP",
            "target": str(target),
            "backup": str(backup_path),
            "target_sha256": _sha256(target),
            "backup_sha256": _sha256(backup_path),
        },
    )
    return backup_path


# ---------------------------------------------------------------------------
# Patch core
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def detect_status(target: Path) -> dict:
    """Inspect the target and report patch status. Read-only."""
    if not target.exists():
        return {"state": "missing", "target": str(target)}
    text = _read_text(target)
    has_import_block = (
        MARKER_IMPORT_BEGIN in text and MARKER_IMPORT_END in text
    )
    has_call_block = (
        MARKER_CALL_BEGIN in text and MARKER_CALL_END in text
    )
    # call blocks are inserted after every mark_job_run. Count occurrences.
    call_block_count = text.count(MARKER_CALL_BEGIN)

    if has_import_block and has_call_block and call_block_count >= 2:
        state = "patched"
    elif has_import_block or has_call_block:
        state = "drifted"  # partial markers — needs repair
    else:
        state = "unpatched"

    return {
        "state": state,
        "target": str(target),
        "sha256": _sha256(target),
        "has_import_block": has_import_block,
        "has_call_block": has_call_block,
        "call_block_count": call_block_count,
        "size_bytes": target.stat().st_size,
    }


def _splitlines_keep(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _join(lines: list[str]) -> str:
    if lines and not lines[-1].endswith("\n"):
        # Ensure file ends with newline; cheap and standard.
        lines[-1] = lines[-1] + "\n"
    return "".join(lines)


def _line_indent(line: str) -> str:
    """Return the leading whitespace of `line`."""
    return line[: len(line) - len(line.lstrip())]


def _insert_after_anchor(lines: list[str], anchor: str, insertion: str) -> tuple[list[str], int]:
    """Insert `insertion` (a multi-line str ending with newline) directly
    after the FIRST occurrence of `anchor`. The inserted block is assumed to
    already be pre-indented for the call site (callers must build the
    insertion with the correct indent level).
    Returns (new_lines, count=1). Raises ValueError if anchor is missing.
    """
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if (not inserted) and (anchor in line):
            out.extend(insertion.splitlines(keepends=True))
            inserted = True
    if not inserted:
        raise ValueError(f"anchor not found: {anchor!r}")
    return out, (1 if inserted else 0)


def _insert_after_each_with_indent(lines: list[str], anchor: str, block_factory) -> tuple[list[str], int]:
    """Insert after EVERY occurrence of `anchor`. `block_factory` is a
    callable taking the anchor line's leading indent string and returning
    a pre-indented block to insert. We use a factory because the happy-path
    call block needs different locals than the exception-path call block.
    """
    out: list[str] = []
    count = 0
    for line in lines:
        if anchor in line:
            indent = _line_indent(line)
            block = block_factory(indent)
            out.append(line)
            out.extend(block.splitlines(keepends=True))
            count += 1
        else:
            out.append(line)
    return out, count


def _strip_existing_blocks(lines: list[str]) -> list[str]:
    """Remove any existing import or call blocks bracketed by our markers,
    so we can idempotently re-apply from a clean slate. This also handles
    the 'drifted' case (partial markers).
    """
    out: list[str] = []
    in_block = None  # one of None, 'import', 'call'
    for line in lines:
        if in_block is None:
            if MARKER_IMPORT_BEGIN in line:
                in_block = "import"
                continue
            if MARKER_CALL_BEGIN in line:
                in_block = "call"
                continue
            out.append(line)
        else:
            if in_block == "import" and MARKER_IMPORT_END in line:
                in_block = None
                continue
            if in_block == "call" and MARKER_CALL_END in line:
                in_block = None
                continue
            # Drop everything inside the block (incl. blank lines / partial markers)
    return out


def _has_anchor(lines: list[str], anchor: str) -> bool:
    return any(anchor in line for line in lines)


def plan_patch(target: Path) -> dict:
    """Compute the diff that would be applied. Read-only.

    Returns a dict with planned insertions and counts. No writes.
    """
    if not target.exists():
        raise FileNotFoundError(f"target not found: {target}")
    text = _read_text(target)
    status = detect_status(target)

    if status["state"] == "patched":
        return {
            "would_apply": False,
            "reason": "already patched (markers present, call_block_count >= 2)",
            "status": status,
        }

    # Count mark_job_run occurrences (both happy and exception paths)
    mark_count = text.count("mark_job_run(")
    has_hermes_time_import = "from hermes_time import now as _hermes_now" in text

    return {
        "would_apply": True,
        "reason": "would insert import block + call block(s) after each mark_job_run",
        "status": status,
        "mark_job_run_occurrences": mark_count,
        "has_hermes_time_import_anchor": has_hermes_time_import,
        "planned_insertions": [
            {
                "kind": "import_block",
                "anchor": "from hermes_time import now as _hermes_now",
                "size_lines": build_import_block().count("\n"),
            },
            {
                "kind": "call_block",
                "anchor": "mark_job_run(",
                "occurrences": mark_count,
                "size_lines": _build_call_block_with_indent("    ", happy=True).count("\n"),
                "note": (
                    "first occurrence after happy-path (line ~2129 in scheduler.py); "
                    "subsequent occurrences after exception-path (line ~2134) use "
                    "a different locals() resolution but the same shape."
                ),
            },
        ],
    }


def apply_patch(target: Path, backup_dir: Path) -> dict:
    """Apply the hook patch. Idempotent: returns already_patched=True on second run.

    Steps:
      1. detect status
      2. if patched -> return
      3. backup target
      4. strip any existing marker blocks (handles 'drifted' state)
      5. insert import block after `from hermes_time import now as _hermes_now`
      6. insert call block after every `mark_job_run(`
      7. write file
      8. py_compile (best-effort; failure leaves file but reports error)
      9. detect status again
    """
    status_before = detect_status(target)
    if status_before["state"] == "patched":
        return {
            "ok": True,
            "already_patched": True,
            "status_before": status_before,
            "status_after": status_before,
        }

    if status_before["state"] == "missing":
        raise FileNotFoundError(f"target missing: {target}")

    # Backup first (always, even for 'drifted' — we want a fresh safe baseline)
    backup_path = backup_target(target, backup_dir)

    text = _read_text(target)
    lines = _splitlines_keep(text)

    # 4. Strip any existing partial blocks so we can re-insert cleanly.
    lines = _strip_existing_blocks(lines)

    # 5. Insert import block (always at column 0 — module-level import).
    lines, _ = _insert_after_anchor(
        lines,
        "from hermes_time import now as _hermes_now",
        build_import_block(),
    )

    # 6. Insert call block after each mark_job_run(. The FIRST occurrence
    # is the happy-path (line ~2129 in scheduler.py) — success/error/output
    # are in scope. Subsequent occurrences (typically just the exception
    # path at ~2134) only have `job` and `e` in scope.
    mark_occurrences: list[int] = [
        i for i, ln in enumerate(lines) if "mark_job_run(" in ln
    ]

    def _factory_for_occurrence(occ_idx_in_mark_list: int):
        # First mark_job_run is happy path; later ones are exception paths.
        is_happy = (occ_idx_in_mark_list == 0)
        return lambda indent: _build_call_block_with_indent(indent, happy=is_happy)

    out_lines: list[str] = []
    mark_seen = 0
    call_count = 0
    for line in lines:
        out_lines.append(line)
        if "mark_job_run(" in line:
            indent = _line_indent(line)
            block = _factory_for_occurrence(mark_seen)(indent)
            out_lines.extend(block.splitlines(keepends=True))
            mark_seen += 1
            call_count += 1
    lines = out_lines

    # 7. Write file.
    target.write_text(_join(lines), encoding="utf-8")

    # 8. py_compile
    compile_ok, compile_msg = _safe_py_compile(target)

    # 9. Status after
    status_after = detect_status(target)

    return {
        "ok": True,
        "already_patched": False,
        "backup": str(backup_path),
        "call_blocks_inserted": call_count,
        "compile_ok": compile_ok,
        "compile_msg": compile_msg,
        "status_before": status_before,
        "status_after": status_after,
    }


def verify_patch(target: Path, do_compile: bool = True) -> dict:
    """Verify the patch is present. Optionally run py_compile. Read-only
    except for running py_compile (which is read-only too — just parses)."""
    if not target.exists():
        return {"ok": False, "reason": f"target missing: {target}"}
    status = detect_status(target)
    if status["state"] != "patched":
        return {
            "ok": False,
            "reason": f"target not in 'patched' state: {status['state']}",
            "status": status,
        }
    if do_compile:
        compile_ok, compile_msg = _safe_py_compile(target)
        return {
            "ok": compile_ok,
            "reason": "py_compile passed" if compile_ok else "py_compile failed",
            "compile_msg": compile_msg,
            "status": status,
        }
    return {"ok": True, "reason": "markers present, compile skipped", "status": status}


def rollback(target: Path, backup_path: Path, backup_dir: Path) -> dict:
    """Restore the exact bytes from `backup_path` to `target`. The backup
    is cross-checked against the MANIFEST.jsonl entry (sha256 must match
    the entry's backup_sha256)."""
    if not backup_path.exists():
        raise FileNotFoundError(f"backup not found: {backup_path}")
    if not target.exists():
        raise FileNotFoundError(f"target missing (cannot rollback into nothing): {target}")

    # Verify backup SHA against MANIFEST.jsonl if present.
    manifest_path = backup_dir / "MANIFEST.jsonl"
    expected_sha: Optional[str] = None
    if manifest_path.exists():
        for raw in manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("backup") == str(backup_path):
                expected_sha = entry.get("backup_sha256")
                break

    actual_sha = _sha256(backup_path)
    if expected_sha and expected_sha != actual_sha:
        raise RuntimeError(
            f"backup sha mismatch: manifest={expected_sha} actual={actual_sha}"
        )

    backup_bytes = backup_path.read_bytes()
    target.write_bytes(backup_bytes)
    _append_manifest(
        backup_dir,
        {
            "ts_utc": _now_utc_compact(),
            "action": "ROLLBACK",
            "target": str(target),
            "backup": str(backup_path),
            "backup_sha256": actual_sha,
            "target_sha256_after": _sha256(target),
        },
    )
    return {
        "ok": True,
        "restored_from": str(backup_path),
        "target_sha256_after": _sha256(target),
        "verified_against_manifest": expected_sha is not None,
    }


# ---------------------------------------------------------------------------
# py_compile helper (best-effort)
# ---------------------------------------------------------------------------


def _safe_py_compile(target: Path) -> tuple[bool, str]:
    """Run python3 -m py_compile on target. Return (ok, message).
    Falls back to a no-op message if the python version isn't usable.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, "py_compile ok"
        return False, (proc.stderr or proc.stdout or "py_compile failed").strip()
    except Exception as e:  # pragma: no cover - best-effort
        return False, f"py_compile could not run: {e}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apply_cron_history_hook.py",
        description="Patch manager for the Hermes cron history hook.",
    )
    p.add_argument("--status", action="store_true", help="Report patch state (read-only).")
    p.add_argument("--dry-run", action="store_true", help="Show planned changes, no writes.")
    p.add_argument("--backup", action="store_true", help="Create a backup, no patch.")
    p.add_argument("--apply", action="store_true", help="Apply patch (idempotent).")
    p.add_argument("--verify", action="store_true", help="Verify patch + py_compile.")
    p.add_argument(
        "--rollback",
        metavar="BACKUP_PATH",
        help="Restore exact bytes from BACKUP_PATH into target.",
    )
    p.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Override target path (tests only).")
    p.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Override backup dir (tests only).")
    p.add_argument(
        "--jobs-json",
        type=Path,
        default=DEFAULT_JOBS_JSON,
        help="Reference jobs.json path (read-only sanity).",
    )
    p.add_argument(
        "--no-compile",
        action="store_true",
        help="Skip py_compile during --verify (and after --apply).",
    )
    return p


def _print_mode_header(mode: str, target: Path, backup_dir: Path) -> None:
    print(f"[{mode}]")
    print(f"  target    : {target}")
    print(f"  backup_dir: {backup_dir}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target: Path = args.target
    backup_dir: Path = args.backup_dir

    # Pick exactly one mode. If none, fall through to --status.
    modes = [
        args.status,
        args.dry_run,
        args.backup,
        args.apply,
        args.verify,
        bool(args.rollback),
    ]
    chosen = sum(modes)
    if chosen > 1:
        print("error: choose exactly one of --status / --dry-run / --backup / --apply / --verify / --rollback", file=sys.stderr)
        return 1
    if chosen == 0:
        args.status = True  # default

    # Safety banner: never touches jobs.json
    if args.jobs_json.exists():
        try:
            js_sha = _sha256(args.jobs_json)
        except Exception:
            js_sha = "<unreadable>"
        print(f"  jobs_json : {args.jobs_json}  sha256={js_sha[:16]} (READ-ONLY — this tool never writes it)")

    if args.status:
        _print_mode_header("STATUS", target, backup_dir)
        status = detect_status(target)
        print(f"  state     : {status['state']}")
        if status["state"] != "missing":
            print(f"  sha256    : {status['sha256'][:16]}")
            print(f"  import    : {'present' if status['has_import_block'] else 'absent'}")
            print(f"  call      : {'present' if status['has_call_block'] else 'absent'} (count={status['call_block_count']})")
        return 0

    if args.dry_run:
        _print_mode_header("DRY-RUN", target, backup_dir)
        plan = plan_patch(target)
        print(f"  would_apply         : {plan['would_apply']}")
        print(f"  reason              : {plan['reason']}")
        print(f"  current state       : {plan['status']['state']}")
        if plan["would_apply"]:
            print(f"  mark_job_run anchors: {plan['mark_job_run_occurrences']}")
            for ins in plan["planned_insertions"]:
                print(f"  -> {ins['kind']}: anchor={ins.get('anchor', ins.get('occurrences'))!r}, ~{ins['size_lines']} lines")
        return 0

    if args.backup:
        _print_mode_header("BACKUP", target, backup_dir)
        if not target.exists():
            print(f"  error: target missing: {target}", file=sys.stderr)
            return 1
        bp = backup_target(target, backup_dir)
        print(f"  backup   : {bp}")
        print(f"  sha256   : {_sha256(bp)[:16]}")
        return 0

    if args.apply:
        _print_mode_header("APPLY", target, backup_dir)
        result = apply_patch(target, backup_dir)
        if result.get("already_patched"):
            print("  result    : already_patched (no changes)")
        else:
            print(f"  backup    : {result.get('backup')}")
            print(f"  call_blocks_inserted: {result.get('call_blocks_inserted')}")
            print(f"  compile_ok : {result.get('compile_ok')}")
            if not result.get("compile_ok") and not args.no_compile:
                print(f"  compile_msg: {result.get('compile_msg')}")
                print("  state      : APPLIED but py_compile failed — investigate", file=sys.stderr)
                return 3
        st = result.get("status_after", {})
        print(f"  final_state: {st.get('state')} (call_blocks={st.get('call_block_count')})")
        return 0

    if args.verify:
        _print_mode_header("VERIFY", target, backup_dir)
        result = verify_patch(target, do_compile=not args.no_compile)
        print(f"  ok    : {result['ok']}")
        print(f"  reason: {result['reason']}")
        st = result.get("status", {})
        if st:
            print(f"  state : {st.get('state')} (call_blocks={st.get('call_block_count')})")
        return 0 if result["ok"] else 2

    if args.rollback:
        _print_mode_header("ROLLBACK", target, backup_dir)
        backup_path = Path(args.rollback)
        if not backup_path.is_absolute():
            backup_path = (backup_dir / backup_path).resolve()
        result = rollback(target, backup_path, backup_dir)
        print(f"  restored_from : {result['restored_from']}")
        print(f"  verified_against_manifest: {result['verified_against_manifest']}")
        print(f"  target_sha256_after: {result['target_sha256_after'][:16]}")
        return 0

    # Unreachable
    return 1


if __name__ == "__main__":
    sys.exit(main())
