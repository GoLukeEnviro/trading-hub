"""SI v2 historical window analyzer.

Pure read-only analysis of the historical trade store produced by the
backfill importer (PR #339).  Produces per-bot and fleet-level
performance windows suitable for evidence bundles.

Window types supported:

- ``full``         — every record in the store
- ``last_7d``      — closed trades with ``close_date`` in the last 7 days
- ``last_14d``     — closed trades with ``close_date`` in the last 14 days
- ``pre_apply``    — closed trades with ``close_date < activation_timestamp_utc``
- ``post_apply``   — closed trades with ``close_date >= activation_timestamp_utc``

When the post-apply window has zero closed trades, the verdict is forced to
``WAITING_FOR_POST_APPLY_DATA`` so callers cannot mistake an empty window
for a successful intervention.

Hard rules:
- No runtime imports (no ``docker``, ``freqtrade``, ``exchange`` in import lines).
- No live trading.  Dry-run mode must remain enabled.
- No secrets in output.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from si_v2.backfill.historical_trade_reader import (
    TradeRecord,
    load_store,
)

# Verdict constants.  Kept as module-level strings so callers can switch on
# them without depending on a specific enum class.
VERDICT_GREEN = "GREEN"
VERDICT_YELLOW = "YELLOW"
VERDICT_RED = "RED"
VERDICT_WAITING = "WAITING_FOR_POST_APPLY_DATA"

# Minimum number of closed trades required to score a post-apply window as
# statistically meaningful.  Below this threshold the verdict is
# ``WAITING_FOR_POST_APPLY_DATA`` regardless of PnL.
MIN_POST_APPLY_CLOSED_TRADES = 1

# Built-in window kinds.  ``custom`` is reserved for callers that supply
# explicit start/end timestamps.
WINDOW_FULL = "full"
WINDOW_LAST_7D = "last_7d"
WINDOW_LAST_14D = "last_14d"
WINDOW_PRE_APPLY = "pre_apply"
WINDOW_POST_APPLY = "post_apply"


def _format_pf(pf: float | None) -> float | str | None:
    """Format profit factor for JSON output. ``float('inf')`` becomes the string ``"inf"``."""
    if pf is None:
        return None
    if pf == float("inf"):
        return "inf"
    return round(pf, 6)


@dataclass
class PairStats:
    """Per-pair aggregate across closed trades."""

    pair: str
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    pnl_abs: float = 0.0
    pnl_ratio_sum: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "pair": self.pair,
            "trade_count": self.trade_count,
            "wins": self.wins,
            "losses": self.losses,
            "pnl_abs": round(self.pnl_abs, 8),
            "avg_pnl_ratio": (
                round(self.pnl_ratio_sum / self.trade_count, 6) if self.trade_count else 0.0
            ),
        }


@dataclass
class WindowMetrics:
    """Per-bot metrics for a single time window."""

    bot_id: str
    window_kind: str
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    sum_close_profit_abs: float = 0.0
    sum_close_profit_ratio: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    best_trade_abs: float | None = None
    worst_trade_abs: float | None = None
    oldest_open_date: str | None = None
    newest_close_date: str | None = None
    top_pairs: list[PairStats] = field(default_factory=list)
    worst_pairs: list[PairStats] = field(default_factory=list)

    @property
    def winrate(self) -> float:
        return (self.wins / self.closed_trades) if self.closed_trades else 0.0

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss == 0:
            if self.gross_profit > 0:
                return float("inf")
            return None
        return self.gross_profit / abs(self.gross_loss)

    @property
    def average_close_profit_abs(self) -> float:
        return self.sum_close_profit_abs / self.closed_trades if self.closed_trades else 0.0

    def to_dict(self) -> dict[str, object]:
        pf = self.profit_factor
        return {
            "bot_id": self.bot_id,
            "window_kind": self.window_kind,
            "total_trades": self.total_trades,
            "closed_trades": self.closed_trades,
            "open_trades": self.open_trades,
            "wins": self.wins,
            "losses": self.losses,
            "winrate": round(self.winrate, 6),
            "sum_close_profit_abs": round(self.sum_close_profit_abs, 8),
            "average_close_profit_abs": round(self.average_close_profit_abs, 8),
            "sum_close_profit_ratio": round(self.sum_close_profit_ratio, 6),
            "gross_profit": round(self.gross_profit, 8),
            "gross_loss": round(self.gross_loss, 8),
            "profit_factor": _format_pf(pf),
            "best_trade_abs": (None if self.best_trade_abs is None else round(self.best_trade_abs, 8)),
            "worst_trade_abs": (None if self.worst_trade_abs is None else round(self.worst_trade_abs, 8)),
            "oldest_open_date": self.oldest_open_date,
            "newest_close_date": self.newest_close_date,
            "top_pairs": [p.to_dict() for p in self.top_pairs],
            "worst_pairs": [p.to_dict() for p in self.worst_pairs],
        }


@dataclass
class FleetSummary:
    """Fleet-level metrics across all bots for a single window."""

    window_kind: str
    bots_covered: list[str] = field(default_factory=list)
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    sum_close_profit_abs: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    strongest_bot: str | None = None
    weakest_bot: str | None = None
    coverage_start: str | None = None
    coverage_end: str | None = None
    data_completeness: str = "unknown"  # "complete" | "partial" | "empty" | "unknown"

    @property
    def fleet_profit_factor(self) -> float | None:
        if self.gross_loss == 0:
            if self.gross_profit > 0:
                return float("inf")
            return None
        return self.gross_profit / abs(self.gross_loss)

    def to_dict(self) -> dict[str, object]:
        return {
            "window_kind": self.window_kind,
            "bots_covered": list(self.bots_covered),
            "total_trades": self.total_trades,
            "closed_trades": self.closed_trades,
            "open_trades": self.open_trades,
            "wins": self.wins,
            "losses": self.losses,
            "winrate": round(self.wins / self.closed_trades, 6) if self.closed_trades else 0.0,
            "sum_close_profit_abs": round(self.sum_close_profit_abs, 8),
            "fleet_profit_factor": _format_pf(self.fleet_profit_factor),
            "strongest_bot": self.strongest_bot,
            "weakest_bot": self.weakest_bot,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "data_completeness": self.data_completeness,
        }


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    cleaned = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _window_bounds(
    window: str, activation_utc: str | None, now: datetime | None = None
) -> tuple[str | None, str | None]:
    """Return ``(start_utc, end_utc)`` for a named window.

    ``end_utc`` is inclusive.  An open bound is returned as ``None`` so
    :func:`load_store` treats it as "no limit on this side".
    """
    now = now or _now_utc()
    if window == WINDOW_FULL:
        return (None, None)
    if window == WINDOW_LAST_7D:
        start = (now - timedelta(days=7)).isoformat()
        return (start, now.isoformat())
    if window == WINDOW_LAST_14D:
        start = (now - timedelta(days=14)).isoformat()
        return (start, now.isoformat())
    if window == WINDOW_PRE_APPLY:
        if activation_utc is None:
            raise ValueError("activation_utc is required for pre_apply window")
        # Inclusive: every close strictly before the activation timestamp
        # belongs to pre-apply; the activation moment itself is post-apply.
        # Use a single-microsecond "before" bound.
        act = _parse_utc(activation_utc)
        if act is None:
            raise ValueError(f"activation_utc could not be parsed: {activation_utc!r}")
        return (None, (act - timedelta(microseconds=1)).isoformat())
    if window == WINDOW_POST_APPLY:
        if activation_utc is None:
            raise ValueError("activation_utc is required for post_apply window")
        return (activation_utc, now.isoformat())
    raise ValueError(f"unknown window kind: {window!r}")


def compute_window_metrics(records: Iterable[TradeRecord], *, bot_id: str, window_kind: str) -> WindowMetrics:
    """Aggregate per-bot metrics for a single window."""
    metrics = WindowMetrics(bot_id=bot_id, window_kind=window_kind)
    pair_map: dict[str, PairStats] = {}
    for rec in records:
        if rec.bot_id != bot_id:
            continue
        metrics.total_trades += 1
        if rec.is_closed:
            metrics.closed_trades += 1
        else:
            metrics.open_trades += 1
        if rec.is_closed and rec.close_profit_abs is not None:
            pnl_abs = float(rec.close_profit_abs)
            pnl_ratio = float(rec.close_profit) if rec.close_profit is not None else 0.0
            metrics.sum_close_profit_abs += pnl_abs
            metrics.sum_close_profit_ratio += pnl_ratio
            if pnl_abs > 0:
                metrics.wins += 1
                metrics.gross_profit += pnl_abs
            else:
                metrics.losses += 1
                metrics.gross_loss += abs(pnl_abs)
            if metrics.best_trade_abs is None or pnl_abs > metrics.best_trade_abs:
                metrics.best_trade_abs = pnl_abs
            if metrics.worst_trade_abs is None or pnl_abs < metrics.worst_trade_abs:
                metrics.worst_trade_abs = pnl_abs
            ps = pair_map.setdefault(rec.pair, PairStats(pair=rec.pair))
            ps.trade_count += 1
            ps.pnl_abs += pnl_abs
            ps.pnl_ratio_sum += pnl_ratio
            if pnl_abs > 0:
                ps.wins += 1
            else:
                ps.losses += 1
        # Date coverage (open + close)
        if rec.open_date and (metrics.oldest_open_date is None or rec.open_date < metrics.oldest_open_date):
            metrics.oldest_open_date = rec.open_date
        if rec.close_date and rec.is_closed and (
            metrics.newest_close_date is None or rec.close_date > metrics.newest_close_date
        ):
            metrics.newest_close_date = rec.close_date
    if pair_map:
        sorted_by_pnl = sorted(pair_map.values(), key=lambda p: p.pnl_abs, reverse=True)
        metrics.top_pairs = sorted_by_pnl[:5]
        metrics.worst_pairs = sorted_by_pnl[-5:][::-1]
    return metrics


def _classify_completeness(window: str, metrics_by_bot: dict[str, WindowMetrics]) -> str:
    """Tag a window's data completeness for fleet reporting."""
    if not metrics_by_bot:
        return "empty"
    closed = sum(m.closed_trades for m in metrics_by_bot.values())
    if closed == 0:
        if window in (WINDOW_PRE_APPLY, WINDOW_POST_APPLY):
            # Empty apply windows are expected, not "partial".
            return "empty"
        return "empty"
    return "complete"


def compute_fleet_summary(
    metrics_by_bot: dict[str, WindowMetrics],
    window_kind: str,
    *,
    activation_utc: str | None = None,
) -> FleetSummary:
    """Aggregate per-bot metrics into a single fleet summary for ``window_kind``."""
    fleet = FleetSummary(window_kind=window_kind)
    if not metrics_by_bot:
        fleet.data_completeness = "empty"
        return fleet
    fleet.bots_covered = sorted(metrics_by_bot.keys())
    for m in metrics_by_bot.values():
        fleet.total_trades += m.total_trades
        fleet.closed_trades += m.closed_trades
        fleet.open_trades += m.open_trades
        fleet.wins += m.wins
        fleet.losses += m.losses
        fleet.sum_close_profit_abs += m.sum_close_profit_abs
        fleet.gross_profit += m.gross_profit
        fleet.gross_loss += m.gross_loss
    # Coverage bounds across all bots for this window
    starts = [m.oldest_open_date for m in metrics_by_bot.values() if m.oldest_open_date]
    ends = [m.newest_close_date for m in metrics_by_bot.values() if m.newest_close_date]
    fleet.coverage_start = min(starts) if starts else None
    fleet.coverage_end = max(ends) if ends else None
    # Strongest/weakest bot by pnl_abs
    ranked = sorted(
        ((bid, m.sum_close_profit_abs) for bid, m in metrics_by_bot.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    if ranked:
        fleet.strongest_bot = ranked[0][0]
        fleet.weakest_bot = ranked[-1][0]
    fleet.data_completeness = _classify_completeness(window_kind, metrics_by_bot)
    return fleet


def _verdict_for_window(
    window: str,
    fleet: FleetSummary,
    post_apply_min_trades: int = MIN_POST_APPLY_CLOSED_TRADES,
) -> str:
    """Return the canonical verdict for a single window."""
    if window == WINDOW_POST_APPLY:
        if fleet.closed_trades < post_apply_min_trades:
            return VERDICT_WAITING
        return VERDICT_YELLOW if fleet.closed_trades < max(5, post_apply_min_trades) else VERDICT_GREEN
    if window in (WINDOW_LAST_7D, WINDOW_LAST_14D):
        return VERDICT_GREEN if fleet.closed_trades > 0 else VERDICT_YELLOW
    if window == WINDOW_PRE_APPLY:
        return VERDICT_GREEN if fleet.closed_trades > 0 else VERDICT_YELLOW
    if window == WINDOW_FULL:
        return VERDICT_GREEN if fleet.closed_trades > 0 else VERDICT_YELLOW
    return VERDICT_YELLOW


def analyze_windows(
    store_dir: str | Path,
    *,
    activation_utc: str | None = None,
    windows: tuple[str, ...] = (WINDOW_FULL, WINDOW_LAST_7D, WINDOW_LAST_14D, WINDOW_PRE_APPLY, WINDOW_POST_APPLY),
    bot_ids: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Run the requested windows over the store and return an evidence-shaped dict.

    The output is JSON-serializable and safe to embed in SI v2 evidence
    bundles.  Callers (e.g. the active cycle) can consume it without
    touching runtime Freqtrade.
    """
    store = Path(store_dir)
    bot_filter = list(bot_ids) if bot_ids else None
    out: dict[str, object] = {
        "store_dir": str(store),
        "activation_utc": activation_utc,
        "windows": {},
    }
    for window in windows:
        start_utc, end_utc = _window_bounds(window, activation_utc, now=now)
        records, stats = load_store(
            store,
            start_utc=start_utc,
            end_utc=end_utc,
            only_closed=(window in (WINDOW_LAST_7D, WINDOW_LAST_14D, WINDOW_PRE_APPLY, WINDOW_POST_APPLY)),
        )
        # Restrict to the requested bot set; load_store does not know about
        # the bot tuple, so filter here.
        if bot_filter is not None:
            records = [r for r in records if r.bot_id in bot_filter]
        per_bot_ids = sorted({r.bot_id for r in records})
        metrics_by_bot: dict[str, WindowMetrics] = {}
        for bid in per_bot_ids:
            metrics_by_bot[bid] = compute_window_metrics(records, bot_id=bid, window_kind=window)
        fleet = compute_fleet_summary(metrics_by_bot, window, activation_utc=activation_utc)
        verdict = _verdict_for_window(window, fleet)
        out["windows"][window] = {
            "start_utc": start_utc,
            "end_utc": end_utc,
            "verdict": verdict,
            "read_stats": stats.to_dict(),
            "per_bot": {bid: m.to_dict() for bid, m in metrics_by_bot.items()},
            "fleet": fleet.to_dict(),
        }
    return out


def build_historical_evidence_window(
    store_dir: Path | str,
    *,
    candidate_id: str | None = None,
    activation_timestamp_utc: str | None = None,
    bot_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Build a JSON-serializable evidence window bundle.

    Convenience wrapper around :func:`analyze_windows` that always
    includes the full / pre-apply / post-apply split.  Designed to be
    called by the SI v2 active cycle once that flow is wired in.  The
    active cycle is intentionally **not** modified in this PR.
    """
    result = analyze_windows(
        store_dir,
        activation_utc=activation_timestamp_utc,
        windows=(WINDOW_FULL, WINDOW_PRE_APPLY, WINDOW_POST_APPLY),
        bot_ids=bot_ids,
    )
    bundle: dict[str, object] = {
        "schema": "si_v2.historical_evidence_window/v1",
        "store_dir": str(Path(store_dir)),
        "candidate_id": candidate_id,
        "activation_timestamp_utc": activation_timestamp_utc,
        "windows": result["windows"],
    }
    windows_map = result["windows"]
    if isinstance(windows_map, Mapping):
        post_apply = windows_map.get(WINDOW_POST_APPLY)
        if isinstance(post_apply, Mapping):
            verdict = post_apply.get("verdict")
            if isinstance(verdict, str):
                bundle["primary_verdict"] = verdict
            else:
                bundle["primary_verdict"] = VERDICT_YELLOW
        else:
            bundle["primary_verdict"] = VERDICT_YELLOW
    else:
        bundle["primary_verdict"] = VERDICT_YELLOW
    return bundle


__all__ = [
    "MIN_POST_APPLY_CLOSED_TRADES",
    "VERDICT_GREEN",
    "VERDICT_RED",
    "VERDICT_WAITING",
    "VERDICT_YELLOW",
    "WINDOW_FULL",
    "WINDOW_LAST_7D",
    "WINDOW_LAST_14D",
    "WINDOW_POST_APPLY",
    "WINDOW_PRE_APPLY",
    "FleetSummary",
    "PairStats",
    "WindowMetrics",
    "analyze_windows",
    "build_historical_evidence_window",
    "compute_fleet_summary",
    "compute_window_metrics",
]
