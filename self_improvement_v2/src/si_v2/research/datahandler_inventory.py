"""Freqtrade DataHandler inventory producer (runs inside pinned container).

Usage (inside container)::

    python3 /freqtrade/datahandler_inventory.py /freqtrade/user_data/data

Outputs canonical JSON to stdout — one object per pair/timeframe/candle_type
with first, last, count, relative_path, and sha256. No network, no config
needed beyond the datadir path.

This is the single source of truth for the structured inventory; the
``freqtrade_native_data_contract`` module parses this output.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from freqtrade.data.history.datahandlers import get_datahandlerclass
from freqtrade.enums import TradingMode


def inventory(datadir: Path) -> list[dict]:
    """Return structured inventory of all OHLCV files in *datadir*."""
    handler = get_datahandlerclass(datadir)
    available = handler.ohlcv_get_available_data(datadir, TradingMode.FUTURES)
    results: list[dict] = []
    for pair, timeframe, candle_type in sorted(available):
        try:
            first, last, count = handler.ohlcv_data_min_max(
                datadir, pair, timeframe, candle_type
            )
        except Exception:
            first = last = None
            count = 0
        filename = handler._pair_data_filename(
            datadir, pair, timeframe, candle_type
        )
        rel = filename.relative_to(datadir)
        try:
            digest = hashlib.sha256(filename.read_bytes()).hexdigest()
        except Exception:
            digest = None
        results.append(
            {
                "pair": pair,
                "timeframe": timeframe,
                "candle_type": candle_type.value,
                "first": first.isoformat() if first else None,
                "last": last.isoformat() if last else None,
                "count": count,
                "relative_path": str(rel),
                "sha256": digest,
            }
        )
    return results


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: datahandler_inventory.py <datadir>", file=sys.stderr)
        sys.exit(2)
    datadir = Path(sys.argv[1])
    if not datadir.is_dir():
        print(f"datadir not found: {datadir}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(inventory(datadir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
