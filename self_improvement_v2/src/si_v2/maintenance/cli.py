"""CLI for derived SQLite cache maintenance.

Usage::

    python -m si_v2.maintenance.cli inspect /path/to/cache.db
    python -m si_v2.maintenance.cli dry-run /path/to/cache.db
    python -m si_v2.maintenance.cli execute-analyze /path/to/cache.db
    python -m si_v2.maintenance.cli execute-optimize /path/to/cache.db
    python -m si_v2.maintenance.cli execute-vacuum /path/to/cache.db

Output: deterministic JSON evidence to stdout, human-readable summary to stderr.
Default mode: inspect. Mutating modes require --execute flag.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import (
    MaintenanceMode,
    MaintenanceRequest,
    MaintenanceResult,
)
from .operations import MaintenanceRunner

_MODE_MAP: dict[str, MaintenanceMode] = {
    "inspect": MaintenanceMode.INSPECT,
    "dry-run": MaintenanceMode.DRY_RUN,
    "execute-analyze": MaintenanceMode.EXECUTE_ANALYZE,
    "execute-optimize": MaintenanceMode.EXECUTE_OPTIMIZE,
    "execute-vacuum": MaintenanceMode.EXECUTE_VACUUM,
}


def _resolve_path(path_str: str) -> Path:
    """Resolve a path string to an absolute Path, expanding ~."""
    return Path(path_str).expanduser().resolve()


def _result_to_json(result: MaintenanceResult) -> str:
    """Serialize a MaintenanceResult to deterministic JSON."""
    payload: dict[str, object] = {
        "verdict": result.verdict.value,
        "db_path": str(result.request.db_path),
        "mode": result.request.mode.value,
        "force": result.request.force,
        "executed_at": result.executed_at.isoformat(),
        "operation": result.operation.name if result.operation is not None else None,
        "operation_ok": result.operation_ok,
    }

    # Evidence
    ev = result.evidence
    payload["evidence"] = {
        "schema_version": ev.schema_version,
        "page_count": ev.page_count,
        "page_size": ev.page_size,
        "auto_vacuum": ev.auto_vacuum,
        "wal_mode": ev.wal_mode,
        "integrity_ok": ev.integrity_ok,
        "foreign_keys_ok": ev.foreign_keys_ok,
        "quick_check_ok": ev.quick_check_ok,
        "source_fingerprint": ev.source_fingerprint,
        "rebuildable": ev.rebuildable,
        "free_mb": round(ev.free_mb, 2),
        "db_size_mb": round(ev.db_size_mb, 2),
    }

    if result.backup_path is not None:
        payload["backup_path"] = str(result.backup_path)

    if result.promoted_path is not None:
        payload["promoted_path"] = str(result.promoted_path)

    if result.original_backup_path is not None:
        payload["original_backup_path"] = str(result.original_backup_path)

    if result.messages:
        payload["messages"] = result.messages

    return json.dumps(payload, indent=2, default=str)


def _print_summary(result: MaintenanceResult) -> None:
    """Print a human-readable summary to stderr."""
    verdict = result.verdict.value
    db_path = result.request.db_path
    mode_str = result.request.mode.value

    print(f"Cache:         {db_path}", file=sys.stderr)
    print(f"Mode:          {mode_str}", file=sys.stderr)
    print(f"Verdict:       {verdict}", file=sys.stderr)
    print(file=sys.stderr)

    ev = result.evidence
    print(f"  Size:        {ev.db_size_mb:.2f} MB", file=sys.stderr)
    print(f"  Free disk:   {ev.free_mb:.1f} MB", file=sys.stderr)
    print(f"  Pages:       {ev.page_count} ({ev.page_size} B)", file=sys.stderr)
    print(f"  WAL mode:    {ev.wal_mode}", file=sys.stderr)
    print(f"  Auto-vacuum: {ev.auto_vacuum}", file=sys.stderr)
    print(file=sys.stderr)
    print(f"  Schema ver:  {ev.schema_version}", file=sys.stderr)
    print(f"  Fingerprint: {ev.source_fingerprint or 'N/A'}", file=sys.stderr)
    print(f"  Rebuildable: {ev.rebuildable}", file=sys.stderr)
    print(file=sys.stderr)

    def _fmt_bool(val: bool | None) -> str:
        """Format an optional boolean for display."""
        return "OK" if val else "FAIL" if val is False else "N/A"

    print(f"  Integrity:   {_fmt_bool(ev.integrity_ok)}", file=sys.stderr)
    print(f"  FK check:    {_fmt_bool(ev.foreign_keys_ok)}", file=sys.stderr)
    print(f"  Quick check: {_fmt_bool(ev.quick_check_ok)}", file=sys.stderr)

    if result.operation_ok is not None:
        print(file=sys.stderr)
        print(
            f"  Operation:   {result.operation.name if result.operation else 'N/A'}",
            file=sys.stderr,
        )
        print(f"  Status:      {'OK' if result.operation_ok else 'FAILED'}", file=sys.stderr)

    if result.backup_path is not None:
        print(f"  Backup:      {result.backup_path}", file=sys.stderr)

    if result.promoted_path is not None:
        print(f"  Promoted:    {result.promoted_path}", file=sys.stderr)

    if result.messages:
        print(file=sys.stderr)
        for msg in result.messages:
            print(f"  [{verdict[:4]}] {msg}", file=sys.stderr)


def _cmd_maintain(args: argparse.Namespace) -> int:
    """Run cache maintenance according to the given arguments."""
    db_path = _resolve_path(args.db_path)

    # Resolve mode
    mode = _MODE_MAP.get(args.command)
    if mode is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    # Verify --execute flag for mutating modes
    if mode in (
        MaintenanceMode.EXECUTE_ANALYZE,
        MaintenanceMode.EXECUTE_OPTIMIZE,
        MaintenanceMode.EXECUTE_VACUUM,
    ) and not args.execute:
        print(
            f"Error: Mutating mode '{args.command}' requires --execute flag",
            file=sys.stderr,
        )
        return 1

    # Resolve backup dir if provided
    backup_dir: Path | None = None
    if args.backup_dir:
        backup_dir = _resolve_path(args.backup_dir)

    # Check DB exists
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    request = MaintenanceRequest(
        db_path=db_path,
        mode=mode,
        force=getattr(args, "force", False),
        backup_dir=backup_dir,
    )

    try:
        result = MaintenanceRunner.run(request)
    except Exception as exc:
        print(f"Error: Maintenance failed: {exc}", file=sys.stderr)
        return 2

    # Output: JSON to stdout, summary to stderr
    json_out = _result_to_json(result)
    print(json_out)  # stdout

    _print_summary(result)

    # Exit code based on verdict
    if result.verdict.value.startswith("RED"):
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Derived SQLite cache maintenance for SI v2",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # inspect
    inspect_p = sub.add_parser("inspect", help="Inspect cache (read-only)")
    inspect_p.add_argument("db_path", type=str, help="Path to SQLite cache database")
    inspect_p.add_argument("--backup-dir", type=str, default=None, help="Backup directory")

    # dry-run
    dryrun_p = sub.add_parser("dry-run", help="Dry-run maintenance (no mutations)")
    dryrun_p.add_argument("db_path", type=str, help="Path to SQLite cache database")
    dryrun_p.add_argument("--backup-dir", type=str, default=None, help="Backup directory")

    # execute-analyze
    analyze_p = sub.add_parser("execute-analyze", help="Run ANALYZE on cache")
    analyze_p.add_argument("db_path", type=str, help="Path to SQLite cache database")
    analyze_p.add_argument("--execute", action="store_true", help="Actually perform the operation")
    analyze_p.add_argument("--force", action="store_true", help="Bypass confirmations")
    analyze_p.add_argument("--backup-dir", type=str, default=None, help="Backup directory")

    # execute-optimize
    optimize_p = sub.add_parser("execute-optimize", help="Run PRAGMA optimize on cache")
    optimize_p.add_argument("db_path", type=str, help="Path to SQLite cache database")
    optimize_p.add_argument("--execute", action="store_true", help="Actually perform the operation")
    optimize_p.add_argument("--force", action="store_true", help="Bypass confirmations")
    optimize_p.add_argument("--backup-dir", type=str, default=None, help="Backup directory")

    # execute-vacuum
    vacuum_p = sub.add_parser("execute-vacuum", help="Run VACUUM on cache")
    vacuum_p.add_argument("db_path", type=str, help="Path to SQLite cache database")
    vacuum_p.add_argument("--execute", action="store_true", help="Actually perform the operation")
    vacuum_p.add_argument("--force", action="store_true", help="Bypass confirmations")
    vacuum_p.add_argument("--backup-dir", type=str, default=None, help="Backup directory")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    return _cmd_maintain(args)


if __name__ == "__main__":
    sys.exit(main())
