#!/usr/bin/env python3
"""Run a read-only SI v2 historical Freqtrade SQLite trade backfill.

Discovers the four on-disk Freqtrade trade DBs, reads them in ``mode=ro``,
normalises each row, and writes the result to:

    self_improvement_v2/state/historical_trades/

The script performs no runtime mutation.  It does not touch Freqtrade
containers, configs, strategies, or pairlists.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make si_v2 importable when run as a script
_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[2]  # self_improvement_v2/scripts/<this> -> repo root
sys.path.insert(0, str(_REPO / "self_improvement_v2" / "src"))

from si_v2.backfill.freqtrade_sqlite_backfill import (  # noqa: E402
    DEFAULT_BOT_DBS,
    backfill_all,
    load_summary,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO,
        help="Path to the trading-hub repository root (default: auto-detected).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override the historical trade store path (default: <repo>/self_improvement_v2/state/historical_trades).",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Write a structured log to this path inside the store.",
    )
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print the most recent stored summary; do not re-run the import.",
    )
    p.add_argument(
        "--bot-id",
        action="append",
        default=None,
        help="Restrict backfill to the given bot_id.  Repeatable.  Default: all configured bots.",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("si_v2_backfill_cli")

    if args.summary_only:
        store = args.output_dir or (
            args.repo_root / "self_improvement_v2" / "state" / "historical_trades"
        )
        existing = load_summary(store)
        if existing is None:
            print(
                json.dumps(
                    {"error": "no_summary", "store": str(store)}, indent=2
                )
            )
            return 1
        print(json.dumps(existing, indent=2, sort_keys=True, default=str))
        return 0

    bot_dbs = list(DEFAULT_BOT_DBS)
    if args.bot_id:
        wanted = set(args.bot_id)
        bot_dbs = [b for b in bot_dbs if b["bot_id"] in wanted]
        unknown = wanted - {b["bot_id"] for b in bot_dbs}
        if unknown:
            print(
                json.dumps(
                    {
                        "error": "unknown_bot_id",
                        "unknown": sorted(unknown),
                        "known": [b["bot_id"] for b in DEFAULT_BOT_DBS],
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2

    summary = backfill_all(
        bot_dbs=bot_dbs,
        repo_root=args.repo_root,
        output_dir=args.output_dir,
    )

    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        args.log_file.write_text(
            json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
    )

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str))
    if summary.totals["total_errors"] > 0:
        log.error(
            "backfill completed with %d error(s) across %d bot(s); see summary for details.",
            summary.totals["total_errors"],
            summary.totals["bots_configured"],
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
