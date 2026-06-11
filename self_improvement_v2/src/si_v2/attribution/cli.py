"""CLI entry point for the Performance Attribution Engine.

Reads JSONL input, processes through the engine, and writes JSONL output
plus optional summary JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from .engine import PerformanceAttributionEngine
from .models import AttributionInput, RegimeLabel, SignalContribution


def _parse_entry(line: str) -> AttributionInput | None:
    """Parse a single JSONL line into an AttributionInput.

    Args:
        line: Raw JSON string.

    Returns:
        Parsed AttributionInput, or None on parse error.
    """
    try:
        data = dict(json.loads(line))
    except (json.JSONDecodeError, ValueError):
        return None

    # Parse regime
    try:
        regime = RegimeLabel(data["regime"])
    except (ValueError, KeyError):
        return None

    # Parse closed_at
    try:
        closed_at = datetime.fromisoformat(data["closed_at"])
    except (ValueError, KeyError):
        return None
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=UTC)

    # Parse signal contributions
    sc_list = data.get("signal_contributions", [])
    signal_contributions = [
        SignalContribution(
            source_id=sc["source_id"],
            contribution_weight=sc["contribution_weight"],
            source_confidence=sc.get("source_confidence"),
            model_or_strategy_id=sc.get("model_or_strategy_id"),
        )
        for sc in sc_list
    ]

    try:
        return AttributionInput(
            trade_id=str(data["trade_id"]),
            source_event_id=str(data["source_event_id"]),
            pair=str(data["pair"]),
            timeframe=str(data["timeframe"]),
            closed_at=closed_at,
            realized_return=float(data["realized_return"]),
            regime=regime,
            regime_confidence=float(data["regime_confidence"]),
            signal_contributions=signal_contributions,
        )
    except (ValueError, KeyError):
        return None


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Performance Attribution Engine — process trade attribution inputs.",
    )
    parser.add_argument(
        "input_file",
        type=str,
        help="Path to input JSONL file (one AttributionInput per line)",
    )
    parser.add_argument(
        "output_file",
        type=str,
        help="Path to output JSONL file (one AttributionFact per line)",
    )
    parser.add_argument(
        "--summary-file",
        type=str,
        default=None,
        help="Optional path to write aggregated summary JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 success, 1 input error, 2 processing error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    # Read and parse entries
    entries: list[AttributionInput] = []
    with open(input_path) as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            entry = _parse_entry(line)
            if entry is None:
                print(
                    f"Error: failed to parse line {line_num}",
                    file=sys.stderr,
                )
                return 1
            entries.append(entry)

    if not entries:
        print("Error: no valid entries found in input file", file=sys.stderr)
        return 1

    # Process through engine
    try:
        engine = PerformanceAttributionEngine()
        result = engine.from_iterable(entries)
    except Exception as e:
        print(f"Error: processing failed: {e}", file=sys.stderr)
        return 2

    # Write output facts as JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for fact in result.facts:
            f.write(fact.model_dump_json() + "\n")

    # Write summary if requested
    if args.summary_file:
        summary_path = Path(args.summary_file)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        metrics = engine.compute_metrics(result, entries)

        summary_dict: dict[str, object] = {
            "accepted_count": result.accepted_count,
            "rejected_count": result.rejected_count,
            "total_facts": len(result.facts),
            "input_fingerprint": result.input_fingerprint,
            "schema_version": result.schema_version,
            "dimension_groups": {},
        }

        groups_dict: dict[str, object] = {}
        for key, m in metrics.items():
            group_name = ":".join(key)
            groups_dict[group_name] = {
                "unique_trade_count": m.unique_trade_count,
                "source_contribution_count": m.source_contribution_count,
                "win_count": m.win_count,
                "loss_count": m.loss_count,
                "breakeven_count": m.breakeven_count,
                "win_rate": round(m.win_rate, 6),
                "average_raw_return": round(m.average_raw_return, 6),
                "average_weighted_return": round(m.average_weighted_return, 6),
                "expectancy": round(m.expectancy, 6),
                "cumulative_weighted_return": round(m.cumulative_weighted_return, 6),
                "drawdown_proxy": round(m.drawdown_proxy, 6),
                "average_source_confidence": round(m.average_source_confidence, 6),
                "average_regime_confidence": round(m.average_regime_confidence, 6),
            }
        summary_dict["dimension_groups"] = groups_dict

        with open(summary_path, "w") as f:
            json.dump(summary_dict, f, indent=2)

    return 0


def entry_point() -> NoReturn:
    """Script entry point that calls main and exits."""
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
