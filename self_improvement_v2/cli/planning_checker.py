#!/usr/bin/env python3
"""Planning package checker CLI (#150).

Usage::

    python -m cli.planning_checker check-package PATH
    python -m cli.planning_checker check-artifacts PATH
    python -m cli.planning_checker render-report PATH [--format json|md] [--output FILE]
    python -m cli.planning_checker explain-finding REASON_CODE

Stable return codes (from ``planning_models.ReturnCode`` mapped to ints)::

    PASS=0, WARNING=2, BLOCKED=10, INVALID_SCHEMA=11,
    MISSING_ARTIFACT=12, INCONSISTENT_REFERENCE=13,
    POLICY_VIOLATION=14, USAGE_ERROR=20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rehearsal.planning_models import ReasonCode
from rehearsal.planning_pipeline_validator import validate_planning_package

# ---------------------------------------------------------------------------
# Stable return codes
# ---------------------------------------------------------------------------

# Map Verdict values to exit codes
VERDICT_EXIT_CODES: dict[str, int] = {
    "PASS": 0,
    "WARNING": 2,
    "BLOCKED": 10,
}

ERROR_EXIT_CODES: dict[str, int] = {
    "INVALID_SCHEMA": 11,
    "MISSING_ARTIFACT": 12,
    "INCONSISTENT_REFERENCE": 13,
    "POLICY_VIOLATION": 14,
    "USAGE_ERROR": 20,
}

# ---------------------------------------------------------------------------
# Enum-like lookup for ReasonCode descriptions
# ---------------------------------------------------------------------------

REASON_CODE_EXPLANATIONS: dict[str, str] = {
    "SCHEMA_INVALID": (
        "The proposal package schema is not valid JSON or does not conform "
        "to the expected structure."
    ),
    "MISSING_REQUIRED_FIELD": (
        "A required field is missing from the proposal package or governance document."
    ),
    "FIELD_PATTERN_MISMATCH": (
        "A field value does not match the required pattern (e.g. proposal_id format)."
    ),
    "INVALID_ENUM_VALUE": (
        "A field contains a value that is not in the allowed set of enum values."
    ),
    "ARTIFACT_MISSING": (
        "A required artifact file is missing from the expected location on disk."
    ),
    "ARTIFACT_EMPTY": (
        "An artifact file exists but is empty or contains no meaningful content."
    ),
    "ARTIFACT_UNREADABLE": (
        "An artifact file cannot be read (permissions, encoding, or corruption issue)."
    ),
    "REFERENCE_MISSING": (
        "A cross-reference between artifacts is missing. For example, the planning "
        "gate doc should reference all prerequisite artifacts."
    ),
    "REFERENCE_STALE": (
        "A cross-reference points to content that is outdated or no longer valid."
    ),
    "REFERENCE_ORPHAN": (
        "A cross-reference points to an issue number or artifact that does not exist "
        "in the current set."
    ),
    "ID_DUPLICATE": (
        "A duplicate identifier (e.g. condition ID, finding ID) was found within "
        "an artifact."
    ),
    "ID_MISMATCH": (
        "An identifier referenced in one artifact does not match the definition "
        "in another artifact."
    ),
    "CONTRADICTORY_VERDICT": (
        "Two artifacts define contradictory verdict semantics. For example, the "
        "planning gate says RED means 'proceed' while policy requires RED to block."
    ),
    "MISSING_FINAL_APPROVAL": (
        "A FINAL-stage proposal package is missing the required operator approval "
        "token or approval packet reference."
    ),
    "NON_PRODUCTION_NOT_CONFIRMED": (
        "The non-production confirmation field is missing or false."
    ),
    "NON_RUNTIME_NOT_CONFIRMED": (
        "The non-runtime confirmation field is missing or false."
    ),
    "STOP_MATRIX_NOT_BLOCKED": (
        "The stop-condition matrix default_verdict is not 'BLOCKED'. "
        "This violates the fail-closed safety policy."
    ),
    "HARD_BLOCKER_NOT_RED": (
        "A condition categorised as a hard_blocker does not have a RED verdict."
    ),
    "UNSAFE_PATH": (
        "An absolute path (e.g. /home/..., /opt/data/...) was found in an artifact. "
        "All paths should be relative or redacted."
    ),
    "UNSAFE_CONTENT": (
        "Sensitive content (e.g. API key, secret, wallet address, private key, "
        "bot token, internal IP) was found without proper redaction."
    ),
    "MISSING_REDACTION": (
        "Expected redaction markers ([REDACTED_*]) are missing from content "
        "that should be redacted."
    ),
    "GOLDEN_MISMATCH": (
        "The validation result differs from the golden snapshot. This may indicate "
        "a regression or an intentional change that needs a snapshot update."
    ),
    "UNEXPECTED_PASS": (
        "The validator returned PASS but the golden snapshot expected a different result."
    ),
    "UNEXPECTED_FAIL": (
        "The validator returned a non-PASS result but the golden snapshot expected PASS."
    ),
    "INTERNAL_ERROR": (
        "An unexpected internal error occurred during validation."
    ),
}


def _resolve_reason_code(name: str) -> ReasonCode | None:
    """Resolve a reason-code name (case-insensitive) to a ``ReasonCode`` member."""
    upper = name.upper()
    for rc in ReasonCode:
        if rc.value == upper or rc.name == upper:
            return rc
    return None


# ---------------------------------------------------------------------------
# Subcommand: check-package
# ---------------------------------------------------------------------------


def cmd_check_package(args: argparse.Namespace) -> int:
    """Validate a planning package JSON file."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    if path.is_dir():
        # Treat as project root
        project_root = path
    elif path.suffix == ".json":
        # It's a package JSON — resolve the project root from the file location
        project_root = path.parent.parent
    else:
        project_root = path

    try:
        result = validate_planning_package(
            project_root=project_root,
            output_json=args.output_json,
            output_md=args.output_md,
        )
    except Exception as exc:
        print(f"Error during validation: {exc}", file=sys.stderr)
        return ERROR_EXIT_CODES["INTERNAL_ERROR"]

    _print_result_summary(result)
    return VERDICT_EXIT_CODES.get(str(result.verdict), 1)


# ---------------------------------------------------------------------------
# Subcommand: check-artifacts
# ---------------------------------------------------------------------------


def cmd_check_artifacts(args: argparse.Namespace) -> int:
    """Validate all artifacts in a directory."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    try:
        result = validate_planning_package(
            project_root=path,
            output_json=args.output_json,
            output_md=args.output_md,
        )
    except Exception as exc:
        print(f"Error during validation: {exc}", file=sys.stderr)
        return ERROR_EXIT_CODES["INTERNAL_ERROR"]

    _print_result_summary(result)
    return VERDICT_EXIT_CODES.get(str(result.verdict), 1)


# ---------------------------------------------------------------------------
# Subcommand: render-report
# ---------------------------------------------------------------------------


def cmd_render_report(args: argparse.Namespace) -> int:
    """Render a validation report from an existing JSON result."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading report: {exc}", file=sys.stderr)
        return ERROR_EXIT_CODES["INVALID_SCHEMA"]

    fmt = args.format.lower()
    output = args.output

    if fmt == "json":
        content = json.dumps(data, indent=2, sort_keys=False)
    elif fmt == "md":
        content = _render_markdown(data)
    else:
        print(f"Error: unsupported format '{fmt}' (use 'json' or 'md')", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    if output:
        Path(output).write_text(content, encoding="utf-8")
        print(f"Report written to {output}")
    else:
        print(content)

    return 0


def _render_markdown(data: dict[str, object]) -> str:
    """Render a validation result dict as Markdown."""
    verdict = data.get("verdict", "UNKNOWN")
    icon = {"PASS": "✅", "WARNING": "⚠️", "BLOCKED": "❌"}.get(verdict, "❓")

    lines = [
        "# Planning Package Validation Report",
        "",
        f"**Verdict:** {icon} **{verdict}**",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Checks | {data.get('total_checks', 0)} |",
        f"| Passed | {data.get('passed', 0)} |",
        f"| Warnings | {data.get('warnings', 0)} |",
        f"| Blocked | {data.get('blocked', 0)} |",
        "",
    ]

    findings = data.get("findings", [])
    if findings:
        lines.extend([
            "## Findings",
            "",
            "| Check ID | Reason Code | Severity | Verdict | Message |",
            "|----------|-------------|----------|---------|---------|",
        ])
        for f in sorted(findings, key=lambda x: (x.get("reason_code", ""), x.get("check_id", ""))):
            lines.append(
                f"| {f.get('check_id', '')} | {f.get('reason_code', '')} "
                f"| {f.get('severity', '')} | {f.get('verdict', '')} "
                f"| {f.get('message', '')} |"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommand: explain-finding
# ---------------------------------------------------------------------------


def cmd_explain_finding(args: argparse.Namespace) -> int:
    """Print a human-readable explanation for a reason code."""
    rc = _resolve_reason_code(args.reason_code)
    if rc is None:
        print(
            f"Error: unknown reason code '{args.reason_code}'. "
            f"Valid codes: {', '.join(sorted(rc.value for rc in ReasonCode))}",
            file=sys.stderr,
        )
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    explanation = REASON_CODE_EXPLANATIONS.get(rc.value, "No explanation available.")
    print(f"Reason Code: {rc.value}")
    print(f"Explanation: {explanation}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_result_summary(result: object) -> None:
    """Print a human-readable summary of validation results."""
    verdict = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
    print(f"Verdict: {verdict}")
    print(f"Total Checks: {result.total_checks}")
    print(f"  Passed:   {result.passed}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Blocked:  {result.blocked}")
    if result.findings:
        print("\nFindings:")
        for f in sorted(result.findings, key=lambda x: (x.reason_code.value, x.check_id)):
            print(f"  [{f.verdict.value}] {f.reason_code.value}: {f.message}")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="planning-checker",
        description="SI v2 Planning Package Checker",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check-package
    pkg = subparsers.add_parser("check-package", help="Validate a planning package (JSON)")
    pkg.add_argument("path", type=str, help="Path to planning package JSON or project root")
    pkg.add_argument("--output-json", type=str, default=None, help="Write JSON report to file")
    pkg.add_argument("--output-md", type=str, default=None, help="Write Markdown report to file")

    # check-artifacts
    art = subparsers.add_parser("check-artifacts", help="Validate all artifacts in a directory")
    art.add_argument("path", type=str, help="Path to directory containing artifacts")
    art.add_argument("--output-json", type=str, default=None, help="Write JSON report to file")
    art.add_argument("--output-md", type=str, default=None, help="Write Markdown report to file")

    # render-report
    rep = subparsers.add_parser("render-report", help="Render a validation report")
    rep.add_argument("path", type=str, help="Path to JSON report file")
    rep.add_argument("--format", type=str, default="md", choices=["json", "md"],
                     help="Output format")
    rep.add_argument("--output", type=str, default=None, help="Write report to file")

    # explain-finding
    exp = subparsers.add_parser("explain-finding", help="Explain a reason code")
    exp.add_argument("reason_code", type=str, help="Reason code to explain")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    command_handlers = {
        "check-package": cmd_check_package,
        "check-artifacts": cmd_check_artifacts,
        "render-report": cmd_render_report,
        "explain-finding": cmd_explain_finding,
    }

    handler = command_handlers.get(args.command)
    if handler is None:
        print(f"Error: unknown command '{args.command}'", file=sys.stderr)
        return ERROR_EXIT_CODES["USAGE_ERROR"]

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
