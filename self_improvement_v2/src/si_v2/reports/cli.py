"""CLI entry point for Automated Attribution Reports.

Reads from a source_regime_stats SQLite cache and generates
Markdown and/or JSON attribution reports.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from .models import ReportRequest
from .renderers import JSONRenderer, MarkdownRenderer
from .report_builder import AttributionReportBuilder


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Automated Attribution Report Generator — "
            "read-only performance summaries from source_regime_stats cache."
        ),
    )
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to source_regime_stats SQLite database (required)",
    )
    parser.add_argument(
        "--markdown-output",
        type=str,
        default=None,
        help="Path for Markdown report output (optional)",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        default=None,
        help="Path for JSON report output (optional)",
    )
    parser.add_argument(
        "--period-start",
        type=str,
        default=None,
        help="ISO timestamp for period start (optional, e.g. 2026-01-01T00:00:00+00:00)",
    )
    parser.add_argument(
        "--period-end",
        type=str,
        default=None,
        help="ISO timestamp for period end (optional, e.g. 2026-06-01T00:00:00+00:00)",
    )
    parser.add_argument(
        "--min-sample-count",
        type=int,
        default=5,
        help="Minimum sample count for ranking inclusion (default: 5)",
    )
    parser.add_argument(
        "--generated-at",
        type=str,
        required=True,
        help=(
            "Explicit ISO timestamp for report generation "
            "(required, e.g. 2026-06-11T12:00:00+00:00)"
        ),
    )
    return parser


def _parse_iso_timestamp(raw: str) -> datetime:
    """Parse an ISO timestamp string, assuming UTC if no timezone."""
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 success, 1 input error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    # Parse timestamps
    try:
        generated_at = _parse_iso_timestamp(args.generated_at)
    except (ValueError, TypeError) as exc:
        print(f"Error: invalid --generated-at: {exc}", file=sys.stderr)
        return 1

    period_start: datetime | None = None
    if args.period_start:
        try:
            period_start = _parse_iso_timestamp(args.period_start)
        except (ValueError, TypeError) as exc:
            print(
                f"Error: invalid --period-start: {exc}", file=sys.stderr
            )
            return 1

    period_end: datetime | None = None
    if args.period_end:
        try:
            period_end = _parse_iso_timestamp(args.period_end)
        except (ValueError, TypeError) as exc:
            print(f"Error: invalid --period-end: {exc}", file=sys.stderr)
            return 1

    # Build request
    request = ReportRequest(
        source_regime_stats_db_path=str(db_path.resolve()),
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        min_sample_count=args.min_sample_count,
    )

    # Generate report
    try:
        builder = AttributionReportBuilder(
            min_sample_count=args.min_sample_count
        )
        report = builder.build(request)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: report generation failed: {exc}", file=sys.stderr)
        return 1

    # Render outputs
    md_renderer = MarkdownRenderer()
    json_renderer = JSONRenderer()

    if args.markdown_output:
        md_path = Path(args.markdown_output)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = md_renderer.render(report)
        md_path.write_text(md_content)
        print(f"Markdown report written to: {md_path}")

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_content = json_renderer.render(report)
        json_path.write_text(json_content)
        print(f"JSON report written to: {json_path}")

    if not args.markdown_output and not args.json_output:
        # Print to stdout if no output file specified
        print(md_renderer.render(report))

    return 0


def entry_point() -> NoReturn:
    """Script entry point that calls main and exits."""
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
