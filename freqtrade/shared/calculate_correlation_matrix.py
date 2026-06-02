from __future__ import annotations

"""Compute a fleet-wide pair correlation matrix from Freqtrade OHLCV feathers.

This script is designed to be run inside a Python environment that has pandas and
pyarrow available (for example, via docker exec against a Freqtrade container or
via a one-off helper container with the repository mounted).

Output: JSON file consumed by FleetRiskManager for correlation-aware throttling.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "freqtrade" / "shared" / "fleet_correlation_matrix.json"
DATA_ROOTS = [
    ROOT / "freqforge" / "user_data" / "data" / "bitget" / "futures",
    ROOT / "freqforge-canary" / "user_data" / "data" / "bitget" / "futures",
    ROOT / "freqtrade" / "bots" / "regime-hybrid" / "user_data" / "data" / "bitget" / "futures",
]

PAIR_RE = re.compile(
    r"^(?P<base>[^_]+)_(?P<quote>[^_]+)_(?P<settle>[^-]+)-(?P<timeframe>\d+[mhdw])-futures\.feather$",
    re.IGNORECASE,
)


def parse_pair_from_filename(name: str) -> Optional[Tuple[str, str]]:
    match = PAIR_RE.match(name)
    if not match:
        return None
    base = match.group("base").upper()
    quote = match.group("quote").upper()
    settle = match.group("settle").upper()
    timeframe = match.group("timeframe").lower()
    pair = f"{base}/{quote}:{settle}"
    return pair, timeframe


def discover_latest_pair_files() -> Dict[str, Path]:
    latest: Dict[str, Path] = {}
    for root in DATA_ROOTS:
        if not root.exists():
            continue
        for path in root.glob("*-15m-futures.feather"):
            parsed = parse_pair_from_filename(path.name)
            if not parsed:
                continue
            pair, timeframe = parsed
            if timeframe != "15m":
                continue
            previous = latest.get(pair)
            if previous is None:
                latest[pair] = path
                continue
            try:
                if path.stat().st_mtime > previous.stat().st_mtime:
                    latest[pair] = path
            except OSError:
                continue
    return latest


def load_return_series(path: Path, pair: str, lookback: int) -> pd.Series:
    frame = pd.read_feather(path)
    if frame.empty:
        return pd.Series(dtype=float, name=pair)

    time_col = None
    for candidate in ("date", "timestamp", "date_utc", "time"):
        if candidate in frame.columns:
            time_col = candidate
            break

    if time_col is not None:
        frame[time_col] = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
        frame = frame.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)
    else:
        frame = frame.copy()
        frame.index = pd.RangeIndex(len(frame))

    if lookback > 0 and len(frame) > lookback:
        frame = frame.tail(lookback)

    close_col = None
    for candidate in ("close", "Close", "c"):
        if candidate in frame.columns:
            close_col = candidate
            break
    if close_col is None:
        raise ValueError(f"No close column found in {path}")

    close = pd.to_numeric(frame[close_col], errors="coerce").dropna()
    if close.empty or len(close) < 3:
        return pd.Series(dtype=float, name=pair)

    log_returns = close.astype(float).apply(lambda x: math.log(x) if x > 0 else float("nan")).diff()
    log_returns = log_returns.dropna()
    log_returns.name = pair
    return log_returns


def build_component_clusters(matrix: pd.DataFrame, threshold: float) -> List[List[str]]:
    pairs = list(matrix.index)
    graph = {pair: set() for pair in pairs}
    for i, left in enumerate(pairs):
        for right in pairs[i + 1 :]:
            corr = abs(float(matrix.loc[left, right]))
            if corr >= threshold:
                graph[left].add(right)
                graph[right].add(left)

    seen = set()
    clusters: List[List[str]] = []
    for pair in pairs:
        if pair in seen:
            continue
        stack = [pair]
        component = []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.append(node)
            stack.extend(graph[node] - seen)
        clusters.append(sorted(component))
    clusters.sort(key=lambda items: (-len(items), items[0] if items else ""))
    return clusters


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute fleet pair correlation matrix")
    parser.add_argument("--lookback", type=int, default=1000, help="Tail rows to use per pair")
    parser.add_argument("--threshold", type=float, default=0.80, help="High-correlation threshold")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    files = discover_latest_pair_files()
    if not files:
        print("No 15m futures feather files found.", file=sys.stderr)
        return 1

    series_map: Dict[str, pd.Series] = {}
    source_paths: Dict[str, str] = {}
    for pair, path in sorted(files.items()):
        try:
            series = load_return_series(path, pair, args.lookback)
            if series.empty:
                print(f"SKIP {pair}: not enough data in {path}", file=sys.stderr)
                continue
            series_map[pair] = series
            source_paths[pair] = str(path)
        except Exception as exc:
            print(f"WARN {pair}: failed to load {path} ({exc})", file=sys.stderr)

    if len(series_map) < 2:
        print("Not enough pairs with data to compute correlations.", file=sys.stderr)
        return 1

    combined = pd.concat(series_map.values(), axis=1)
    matrix = combined.corr().fillna(0.0).round(4)

    high_corr_pairs = []
    pairs = list(matrix.index)
    for i, left in enumerate(pairs):
        for right in pairs[i + 1 :]:
            corr = float(matrix.loc[left, right])
            if abs(corr) >= float(args.threshold):
                high_corr_pairs.append(
                    {
                        "pair_a": left,
                        "pair_b": right,
                        "correlation": corr,
                        "abs_correlation": abs(corr),
                    }
                )
    high_corr_pairs.sort(key=lambda item: item["abs_correlation"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_rows": int(args.lookback),
        "threshold": float(args.threshold),
        "pair_count": len(series_map),
        "source_paths": source_paths,
        "matrix": {
            left: {right: float(matrix.loc[left, right]) for right in matrix.columns}
            for left in matrix.index
        },
        "high_corr_pairs": high_corr_pairs,
        "clusters": build_component_clusters(matrix, float(args.threshold)),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"Wrote {args.output} | pairs={len(series_map)} | high_corr={len(high_corr_pairs)} | "
        f"clusters={len(output['clusters'])}",
        file=sys.stderr,
    )
    # Emit JSON to stdout only (for pipe/capture by wrapper)
    sys.stdout.write(json.dumps(output, indent=2, sort_keys=True) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
