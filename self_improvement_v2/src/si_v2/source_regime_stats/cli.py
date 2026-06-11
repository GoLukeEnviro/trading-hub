"""CLI for source_regime_stats cache management.

Modes: rebuild, update, verify, inspect-summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import integrity_check, open_db
from .rebuild import FullRebuilder
from .update import IncrementalUpdater


def _load_jsonl(path: str | Path) -> list[dict]:
    """Load JSONL file into a list of dicts."""
    facts: list[dict] = []
    with Path(path).open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                facts.append(json.loads(line))
    return facts


def _cmd_rebuild(args: argparse.Namespace) -> int:
    """Run a full rebuild from a JSONL input file."""
    facts = _load_jsonl(args.input_jsonl)
    rebuilder = FullRebuilder()
    try:
        result = rebuilder.build(facts, args.output_db)
        print(f"Rebuild complete: {result}")
        print(f"  Facts: {len(facts)}")
        return 0
    finally:
        rebuilder.cleanup()


def _cmd_update(args: argparse.Namespace) -> int:
    """Run an incremental update from a JSONL input file."""
    facts = _load_jsonl(args.input_jsonl)
    updater = IncrementalUpdater()
    try:
        result = updater.update(args.existing_db, facts)
        print(f"Update complete: {result}")
        print(f"  New facts: {len(facts)}")
        return 0
    finally:
        updater.cleanup()


def _cmd_verify(args: argparse.Namespace) -> int:
    """Verify an existing cache database."""
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = open_db(str(db_path))
    try:
        issues = integrity_check(conn)
        if issues:
            print(f"Integrity check FAILED ({len(issues)} issues):")
            for issue in issues:
                print(f"  {issue}")
            return 1

        fact_count = conn.execute(
            "SELECT COUNT(*) FROM attribution_facts"
        ).fetchone()[0]

        summary_count = conn.execute(
            "SELECT COUNT(*) FROM source_regime_stats"
        ).fetchone()[0]

        meta_count = conn.execute(
            "SELECT COUNT(*) FROM cache_metadata"
        ).fetchone()[0]

        print("Integrity check: PASSED")
        print(f"  Attribution facts:     {fact_count}")
        print(f"  Source regime stats:   {summary_count}")
        print(f"  Cache metadata:        {meta_count}")

        # Print metadata details
        cursor = conn.execute("SELECT * FROM cache_metadata")
        for row in cursor.fetchall():
            columns = [desc[0] for desc in cursor.description]
            meta = dict(zip(columns, row, strict=False))
            for k, v in meta.items():
                print(f"  meta.{k}: {v}")

        return 0
    finally:
        conn.close()


def _cmd_inspect_summary(args: argparse.Namespace) -> int:
    """Inspect top N rows from source_regime_stats."""
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    n = args.top_n
    conn = open_db(str(db_path))
    try:
        rows = conn.execute(
            "SELECT * FROM source_regime_stats ORDER BY source_contribution_count DESC LIMIT ?",
            (n,),
        ).fetchall()
        cursor = conn.execute(
            "SELECT * FROM source_regime_stats ORDER BY source_contribution_count DESC LIMIT ?",
            (n,),
        )

        columns = [desc[0] for desc in cursor.description]

        if not rows:
            print("No summary rows found.")
            return 0

        # Print header
        header = " | ".join(columns)
        print(f"Top {n} source_regime_stats rows:")
        print(f"  {header}")
        print(f"  {'-' * len(header)}")

        for row in rows:
            vals = []
            for _col, val in zip(columns, row, strict=False):
                if isinstance(val, float):
                    vals.append(f"{val:.6f}")
                else:
                    vals.append(str(val))
            print(f"  {' | '.join(vals)}")

        return 0
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="source_regime_stats SQLite cache management",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # rebuild
    rebuild = sub.add_parser("rebuild", help="Full rebuild from JSONL")
    rebuild.add_argument("input_jsonl", type=str, help="Path to JSONL input file")
    rebuild.add_argument("output_db", type=str, help="Path to output SQLite database")

    # update
    update = sub.add_parser("update", help="Incremental update from JSONL")
    update.add_argument("input_jsonl", type=str, help="Path to JSONL input file with new facts")
    update.add_argument("existing_db", type=str, help="Path to existing SQLite database")

    # verify
    verify = sub.add_parser("verify", help="Verify database integrity")
    verify.add_argument("db_path", type=str, help="Path to SQLite database")

    # inspect-summary
    inspect = sub.add_parser("inspect-summary", help="Inspect summary rows")
    inspect.add_argument("db_path", type=str, help="Path to SQLite database")
    inspect.add_argument(
        "--top-n", type=int, default=10,
        help="Number of rows to display (default: 10)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "rebuild": _cmd_rebuild,
        "update": _cmd_update,
        "verify": _cmd_verify,
        "inspect-summary": _cmd_inspect_summary,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
