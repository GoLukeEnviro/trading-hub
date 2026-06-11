"""CLI entry point for regime detection and Shadowlock enrichment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from si_v2.regime.detection_request import RegimeDetectionRequest
from si_v2.regime.detector import ThresholdRegimeDetector
from si_v2.regime.shadowlock_enrichment import (
    DuplicateConflictError,
    ShadowlockEnrichmentWriter,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Regime detector run and Shadowlock enrichment boundary",
    )
    parser.add_argument(
        "input_file",
        type=str,
        help="Path to input JSONL file (market observations or Shadowlock ledger).",
    )
    parser.add_argument(
        "output_file",
        type=str,
        help="Path to output JSONL file (derived enrichment records).",
    )
    parser.add_argument(
        "--mode",
        choices={"detect", "enrich", "enrich-only"},
        default="detect",
        help=(
            "detect: run detector on observations → write enrichment. "
            "enrich: read ledger and enrich (same as enrich-only). "
            "enrich-only: read ledger and write enrichment without detection."
        ),
    )
    parser.add_argument(
        "--threshold-rsi-bullish",
        type=float,
        default=70.0,
        help="RSI threshold for BULLISH regime (default: 70).",
    )
    parser.add_argument(
        "--threshold-rsi-bearish",
        type=float,
        default=30.0,
        help="RSI threshold for BEARISH regime (default: 30).",
    )
    return parser.parse_args(argv)


def _validate_paths(input_file: str, output_file: str) -> None:
    """H10: Validate that input and output resolve to different paths."""
    real_input = os.path.realpath(input_file)
    real_output = os.path.realpath(output_file)
    if real_input == real_output:
        print(
            f"ERROR: input_file and output_file must be different paths; "
            f"both resolve to {real_input!r}",
            file=sys.stderr,
        )
        sys.exit(1)


def _read_jsonl(path: str) -> list[dict[str, object]]:
    """Read a JSONL file, yielding dicts per line."""
    records: list[dict[str, object]] = []
    p = Path(path)
    if not p.exists():
        print(f"ERROR: input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p) as fp:
        for line_no, line in enumerate(fp, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                print(
                    f"ERROR: invalid JSON on line {line_no}: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
    return records


def _run_detect_mode(
    input_path: str,
    output_path: str,
    rsi_bullish: float,
    rsi_bearish: float,
) -> dict[str, object]:
    """Run detection mode: read observations, detect, write enrichment."""
    records = _read_jsonl(input_path)
    detector = ThresholdRegimeDetector(
        rsi_bullish_threshold=rsi_bullish,
        rsi_bearish_threshold=rsi_bearish,
    )
    writer = ShadowlockEnrichmentWriter()

    # Build synthetic ledger records with detection results
    ledger_records: list[dict[str, object]] = []
    for i, obs in enumerate(records):
        request = RegimeDetectionRequest(
            observations=obs,
            timeframe=str(obs.get("timeframe", "1h")),
            data_source=detector.data_source,
            detected_at=datetime.now(UTC),
        )
        event = detector.detect(request)
        ledger_records.append(
            {
                "source_event_id": f"detect_{i}",
                "regime_label": str(event.regime),
                "confidence": event.confidence,
                "detected_at": event.detected_at.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
        )

    enrichments = writer.process_ledger(
        ledger_records,
        output_path,
        enrichment_created_at=datetime.now(UTC),
    )

    return {
        "mode": "detect",
        "input_file": input_path,
        "output_file": output_path,
        "records_processed": len(records),
        "enrichments_written": len(enrichments),
    }


def _run_enrich_mode(input_path: str, output_path: str) -> dict[str, object]:
    """Run enrichment mode: read ledger, write enrichment."""
    records = _read_jsonl(input_path)
    writer = ShadowlockEnrichmentWriter()

    try:
        enrichments = writer.process_ledger(
            records, output_path, enrichment_created_at=datetime.now(UTC)
        )
    except DuplicateConflictError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    return {
        "mode": "enrich",
        "input_file": input_path,
        "output_file": output_path,
        "records_processed": len(records),
        "enrichments_written": len(enrichments),
    }


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = _parse_args(argv)

    # H10: Validate paths before doing any work
    _validate_paths(args.input_file, args.output_file)

    if args.mode in ("enrich", "enrich-only"):
        summary = _run_enrich_mode(args.input_file, args.output_file)
    else:
        summary = _run_detect_mode(
            args.input_file,
            args.output_file,
            args.threshold_rsi_bullish,
            args.threshold_rsi_bearish,
        )

    # Output JSON summary to stdout
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
