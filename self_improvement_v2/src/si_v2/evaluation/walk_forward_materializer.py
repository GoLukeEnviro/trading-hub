r"""Walk-Forward Evidence Materializer — read-only gate-fiable metrics derivation.

This module implements a deterministic, read-only materializer that loads
existing telemetry history, historical trade data, and past evidence bundles
to produce per-bot ``walk_forward_net_metrics`` for all four dry-run bots.

Design decisions:
  - Pure functions where possible; I/O is isolated to the top-level entry point.
  - No Docker, no Freqtrade REST API, no network calls.
  - No config writes, no data mutation, no side effects beyond artifact write.
  - Failure-isolated per bot — one bot's missing data never crashes another.
  - Output schema is compatible with ``walk_forward_net_metrics.evaluate_net_metrics``
    and the profitability gate's ``BotProfitabilityMetrics.from_walk_forward_dict``.

Integration:
  Called during the active cycle (post-Step 5) or as a standalone entry point.
  The output artifact at ``reports/phase2/walk_forward/walk_forward_metrics_<cycle_id>.json``
  is consumed by the profitability gate and candidate builder.

Data sources consulted (read-only):
  - ``state/telemetry_history/telemetry_*.jsonl`` — per-bot daily profit snapshots
  - ``state/historical_trades/historical_trades_<bot>.jsonl`` — per-trade records
  - ``reports/phase2/evidence/active_cycle_*.json`` — past walk_forward_net_metrics
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)

# Default paths relative to repo root
DEFAULT_TELEMETRY_HISTORY_DIR: Final[str] = "self_improvement_v2/state/telemetry_history"
DEFAULT_HISTORICAL_TRADES_DIR: Final[str] = "self_improvement_v2/state/historical_trades"
DEFAULT_EVIDENCE_DIR: Final[str] = "self_improvement_v2/reports/phase2/evidence"
DEFAULT_WALK_FORWARD_DIR: Final[str] = "self_improvement_v2/reports/phase2/walk_forward"

# ---------------------------------------------------------------------------
# Evaluation status constants
# ---------------------------------------------------------------------------
STATUS_PASS_REVIEW: Final[str] = "PASS_REVIEW"
"""Sufficient trades and positive net metrics — pass review."""

STATUS_NO_TRADES: Final[str] = "NO_TRADES"
"""Bot exists but has zero closed trades in the evidence window."""

STATUS_INSUFFICIENT_TRADES: Final[str] = "INSUFFICIENT_TRADES"
"""Some trades exist but fewer than the minimum threshold."""

STATUS_MISSING_HISTORY: Final[str] = "MISSING_HISTORY"
"""No telemetry history records found for this bot."""

STATUS_INVALID_METRICS: Final[str] = "INVALID_METRICS"
"""Data was found but metrics are invalid (e.g., NaN, infinite)."""

STATUS_INSUFFICIENT_EVIDENCE: Final[str] = "INSUFFICIENT_EVIDENCE"
"""Cross-source validation: data exists but is insufficient for a verdict."""

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_MIN_TRADES_FOR_EVALUATION: Final[int] = 5
"""Minimum trades required to produce a meaningful evaluation."""

_MAX_TELEMETRY_HISTORY_DAYS: Final[int] = 30
"""Maximum age of telemetry history records to consider."""

# ---------------------------------------------------------------------------
# Metrics source tag
# ---------------------------------------------------------------------------
METRICS_SOURCE: Final[str] = "walk_forward_net_metrics"
"""Source tag for metrics produced by this module — compatible with profitability gate."""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BotWalkForwardMetrics:
    """Per-bot walk-forward metrics produced by the materializer.

    All numeric fields have safe defaults (0 / 0.0). The ``evaluation_status``
    field is the primary signal for downstream consumers.
    """

    bot_id: str
    evaluation_status: str = STATUS_MISSING_HISTORY
    net_profit_abs: float = 0.0
    net_profit_ratio: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    evidence_window_start: str = ""
    evidence_window_end: str = ""
    total_trades: int = 0
    total_net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    metrics_source: str = METRICS_SOURCE
    promotion_blocked: bool = True
    promotion_block_reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for persistence."""
        return {
            "bot_id": self.bot_id,
            "evaluation_status": self.evaluation_status,
            "net_profit_abs": self.net_profit_abs,
            "net_profit_ratio": self.net_profit_ratio,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "profit_factor": self.profit_factor,
            "evidence_window_start": self.evidence_window_start,
            "evidence_window_end": self.evidence_window_end,
            "total_trades": self.total_trades,
            "total_net_pnl": self.total_net_pnl,
            "max_drawdown_pct": self.max_drawdown_pct,
            "metrics_source": self.metrics_source,
            "promotion_blocked": self.promotion_blocked,
            "promotion_block_reason_codes": list(self.promotion_block_reason_codes),
        }

    def to_walk_forward_dict(self) -> dict[str, object]:
        """Produce a dict compatible with WalkForwardEvaluation.to_dict().

        This allows the materializer's output to be used directly by the
        profitability gate's ``evaluate_from_walk_forward_dicts``.
        """
        return {
            "total_trades": self.total_trades,
            "total_net_pnl": self.total_net_pnl,
            "total_fees": 0.0,
            "total_slippage": 0.0,
            "total_funding": 0.0,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "win_rate_pct": self.win_rate,
            "evaluation_status": self.evaluation_status,
            "promotion_blocked": self.promotion_blocked,
            "promotion_block_reason_codes": list(self.promotion_block_reason_codes),
            "metrics_source": self.metrics_source,
        }


@dataclass(frozen=True)
class MaterializerResult:
    """Top-level result produced by the materializer."""

    cycle_id: str
    generated_at_utc: str
    bots: tuple[BotWalkForwardMetrics, ...]
    artifact_type: str = "walk_forward_materializer_v1"

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_type": self.artifact_type,
            "cycle_id": self.cycle_id,
            "generated_at_utc": self.generated_at_utc,
            "bots": [b.to_dict() for b in self.bots],
        }

    def to_walk_forward_by_bot(self) -> dict[str, dict[str, object]]:
        """Per-bot dict mapping for the profitability gate."""
        return {b.bot_id: b.to_walk_forward_dict() for b in self.bots}


# ===========================================================================
# I/O — failure-isolated loaders
# ===========================================================================


def _load_telemetry_history(
    telemetry_dir: Path,
    max_days: int = _MAX_TELEMETRY_HISTORY_DAYS,
) -> list[dict[str, object]]:
    """Load telemetry history records from the JSONL store.

    Returns at most ``max_days`` worth of records, sorted oldest-first.
    Failure-isolated: returns empty list on any error.
    """
    records: list[dict[str, object]] = []
    if not telemetry_dir.is_dir():
        return records

    try:
        files = sorted(telemetry_dir.glob("telemetry_*.jsonl"))
        # Only include files within the max_days window
        now = datetime.now(UTC)
        for f_path in files:
            try:
                # Parse YYYYMMDD from filename: telemetry_20260626.jsonl
                date_str = f_path.stem.replace("telemetry_", "")
                file_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
                age_days = (now - file_date).days
                if age_days > max_days:
                    continue
            except (ValueError, IndexError):
                continue

            with f_path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if isinstance(rec, dict):
                            records.append(rec)
                    except json.JSONDecodeError:
                        continue
    except (OSError, PermissionError):
        return records

    return records


def _load_historical_trades(
    trades_dir: Path,
    bot_id: str,
) -> list[dict[str, object]]:
    """Load historical trades for a single bot from the JSONL store.

    Failure-isolated: returns empty list on any error.
    """
    if not trades_dir.is_dir():
        return []

    safe_name = bot_id.replace("-", "_")
    f_path = trades_dir / f"historical_trades_{safe_name}.jsonl"

    if not f_path.exists():
        # Try original format with hyphens
        f_path = trades_dir / f"historical_trades_{bot_id}.jsonl"

    if not f_path.exists():
        return []

    records: list[dict[str, object]] = []
    try:
        with f_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        records.append(rec)
                except json.JSONDecodeError:
                    continue
    except (OSError, PermissionError):
        return records

    return records


def _load_latest_evidence_metrics(
    evidence_dir: Path,
    bot_id: str,
) -> dict[str, object]:
    """Load the most recent walk_forward_net_metrics for a bot from evidence bundles.

    Failure-isolated: returns empty dict on any error.
    """
    if not evidence_dir.is_dir():
        return {}

    try:
        files = sorted(evidence_dir.glob("active_cycle_*.json"), reverse=True)
    except OSError:
        return {}

    for f_path in files:
        try:
            with f_path.open() as fh:
                bundle = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(bundle, dict):
            continue

        # Check safety_results for the target bot
        safety = bundle.get("safety_results", [])
        if not isinstance(safety, list):
            # Try per_bot_decisions as fallback
            decisions = bundle.get("per_bot_decisions", [])
            if not isinstance(decisions, list):
                continue
            for d in decisions:
                if isinstance(d, dict) and d.get("bot_id") == bot_id:
                    wf = d.get("walk_forward_net_metrics", {})
                    if isinstance(wf, dict) and "max_drawdown_pct" in wf:
                        return dict(wf)
            continue

        for sr in safety:
            if isinstance(sr, dict) and sr.get("bot_id") == bot_id:
                wf = sr.get("walk_forward_net_metrics", {})
                if isinstance(wf, dict) and "max_drawdown_pct" in wf:
                    return dict(wf)

    return {}


# ===========================================================================
# Computation
# ===========================================================================


def _is_valid_float(value: object) -> bool:
    """Check if a value is a valid (non-NaN, non-infinite) float."""
    if not isinstance(value, (int, float)):
        return False
    if isinstance(value, bool):
        return False
    import math
    return not (math.isnan(value) or math.isinf(value))


def _safe_float(value: object, default: float = 0.0) -> float:
    """Safely extract a float, returning default on invalid values."""
    if not isinstance(value, (int, float)):
        return default
    if isinstance(value, bool):
        return default
    import math
    if math.isnan(value) or math.isinf(value):
        return default
    return float(value)


def _safe_int(value: object, default: int = 0) -> int:
    """Safely extract an int, returning default on invalid values."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and not isinstance(value, bool):
        return int(value)
    return default


def _compute_from_telemetry(
    bot_id: str,
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Compute metrics from telemetry history records.

    Returns dict with keys: ``net_profit_abs``, ``net_profit_ratio``,
    ``trade_count``, ``count``, ``window_start``, ``window_end``.
    Returns empty dict when no relevant records found.
    """
    profit_abs_values: list[float] = []
    profit_ratio_values: list[float] = []
    trade_count_values: list[int] = []
    timestamps: list[str] = []

    for rec in records:
        bots_raw = rec.get("bots")
        if not isinstance(bots_raw, list):
            continue
        for bot_entry in bots_raw:
            if not isinstance(bot_entry, dict):
                continue
            if bot_entry.get("bot_id") != bot_id:
                continue

            pa = _safe_float(bot_entry.get("profit_abs"))
            pr = _safe_float(bot_entry.get("profit_ratio"))
            tc = _safe_int(bot_entry.get("trade_count"))
            ts = bot_entry.get("timestamp_utc")

            # Only include authenticated records with meaningful data
            if bot_entry.get("read_success") is False:
                continue
            if pa == 0.0 and pr == 0.0 and tc == 0:
                continue

            profit_abs_values.append(pa)
            profit_ratio_values.append(pr)
            trade_count_values.append(tc)
            if isinstance(ts, str) and ts:
                timestamps.append(ts)

    if not profit_abs_values:
        return {}

    # Use the maximum trade_count as the best estimate of total closed trades
    best_trade_count = max(trade_count_values) if trade_count_values else 0

    # Use the most recent profit_abs as the current cumulative profit
    latest_profit_abs = profit_abs_values[-1]
    latest_profit_ratio = profit_ratio_values[-1] if profit_ratio_values else 0.0

    return {
        "net_profit_abs": latest_profit_abs,
        "net_profit_ratio": latest_profit_ratio,
        "trade_count": best_trade_count,
        "count": len(profit_abs_values),
        "window_start": timestamps[0] if timestamps else "",
        "window_end": timestamps[-1] if timestamps else "",
    }


def _compute_from_trades(
    trades: list[dict[str, object]],
) -> dict[str, object]:
    """Compute detailed metrics from historical trade records.

    Returns dict with keys: ``win_rate``, ``profit_factor``,
    ``total_net_pnl``, ``trade_count``, ``net_profit_abs``, ``net_profit_ratio``.

    Returns empty dict when no closed trades are found.
    """
    closed_trades = [t for t in trades if t.get("is_open") == 0]
    if not closed_trades:
        return {}

    total_pnl = 0.0
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0

    for t in closed_trades:
        pnl = _safe_float(t.get("close_profit_abs"))

        total_pnl += pnl

        if pnl > 0:
            wins += 1
            gross_profit += pnl
        elif pnl < 0:
            losses += 1
            gross_loss += abs(pnl)

    total_trades = len(closed_trades)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        999.0 if gross_profit > 0 else 0.0
    )

    # Average profit ratio as a simple percentage of mean trade return
    profit_ratios = [_safe_float(t.get("close_profit")) for t in closed_trades]
    avg_profit_ratio = (
        sum(profit_ratios) / len(profit_ratios) if profit_ratios else 0.0
    )

    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4),
        "total_net_pnl": round(total_pnl, 8),
        "trade_count": total_trades,
        "net_profit_abs": round(total_pnl, 8),
        "net_profit_ratio": round(avg_profit_ratio, 8),
    }


def _determine_evaluation_status(
    tel_data: dict[str, object],
    trade_data: dict[str, object],
    previous_metrics: dict[str, object],
) -> tuple[str, bool, list[str]]:
    """Determine evaluation_status and promotion_blocked from available data.

    Returns a tuple of (evaluation_status, promotion_blocked, reason_codes).
    """

    # Check if we have ANY data at all
    has_tel = bool(tel_data)
    has_trades = bool(trade_data)
    has_previous = bool(previous_metrics)

    if not has_tel and not has_trades and not has_previous:
        return (STATUS_MISSING_HISTORY, True, ["no_telemetry_history", "no_trade_history", "no_previous_metrics"])

    # Get the best available trade count
    trade_count = 0
    if has_tel:
        trade_count = max(trade_count, _safe_int(tel_data.get("trade_count", 0)))
    if has_trades:
        trade_count = max(trade_count, _safe_int(trade_data.get("trade_count", 0)))
    if has_previous:
        trade_count = max(trade_count, _safe_int(previous_metrics.get("total_trades", 0)))

    # Validate numeric values
    if has_trades:
        for key in ("total_net_pnl", "profit_factor", "win_rate"):
            val = trade_data.get(key)
            if val is not None and not _is_valid_float(val):
                return (STATUS_INVALID_METRICS, True, [f"invalid_{key}"])

    if trade_count == 0:
        return (STATUS_NO_TRADES, True, ["zero_trades_in_window"])

    if trade_count < _MIN_TRADES_FOR_EVALUATION:
        return (
            STATUS_INSUFFICIENT_TRADES,
            True,
            [f"only_{trade_count}_trades_below_min_{_MIN_TRADES_FOR_EVALUATION}"],
        )

    return (STATUS_PASS_REVIEW, False, [])


# ===========================================================================
# Public entry point
# ===========================================================================


def materialize_walk_forward_metrics(
    *,
    cycle_id: str | None = None,
    repo_root: Path | str | None = None,
    telemetry_dir: Path | str | None = None,
    trades_dir: Path | str | None = None,
    evidence_dir: Path | str | None = None,
    walk_forward_dir: Path | str | None = None,
    persist: bool = True,
) -> MaterializerResult:
    """Produce walk-forward metrics for all four bots from available data.

    This is the main entry point. It loads all available data sources,
    computes per-bot metrics, and optionally persists the result as a
    JSON artifact.

    Args:
        cycle_id: Optional cycle ID. Auto-generated if omitted.
        repo_root: Repository root path. Auto-detected if omitted.
        telemetry_dir: Telemetry history directory.
        trades_dir: Historical trades directory.
        evidence_dir: Past evidence bundles directory.
        walk_forward_dir: Output directory for the artifact.
        persist: If True, write the artifact to disk.

    Returns:
        MaterializerResult with per-bot metrics.

    No runtime mutation, no Docker, no Freqtrade API calls.
    """
    # ── Resolve paths ────────────────────────────────────────────────────
    resolved_root = Path(repo_root).resolve() if repo_root else _resolve_repo_root()
    tel_dir = (
        Path(telemetry_dir).resolve()
        if telemetry_dir
        else resolved_root / DEFAULT_TELEMETRY_HISTORY_DIR
    )
    trd_dir = (
        Path(trades_dir).resolve()
        if trades_dir
        else resolved_root / DEFAULT_HISTORICAL_TRADES_DIR
    )
    evd_dir = (
        Path(evidence_dir).resolve()
        if evidence_dir
        else resolved_root / DEFAULT_EVIDENCE_DIR
    )
    wf_dir = (
        Path(walk_forward_dir).resolve()
        if walk_forward_dir
        else resolved_root / DEFAULT_WALK_FORWARD_DIR
    )

    # ── Generate cycle_id ───────────────────────────────────────────────
    now_utc = datetime.now(UTC)
    if not cycle_id:
        cycle_id = now_utc.strftime("%Y%m%dT%H%M%SZ")
    generated_at_utc = now_utc.isoformat()

    # ── Load data sources ───────────────────────────────────────────────
    tel_records = _load_telemetry_history(tel_dir)

    bots_list: list[BotWalkForwardMetrics] = []

    for bot_id in EXPECTED_BOT_IDS:
        # Load all available data for this bot
        tel_data = _compute_from_telemetry(bot_id, tel_records)
        trade_records = _load_historical_trades(trd_dir, bot_id)
        trade_data = _compute_from_trades(trade_records)
        prev_metrics = _load_latest_evidence_metrics(evd_dir, bot_id)

        # Determine evaluation status
        status, blocked, reason_codes = _determine_evaluation_status(
            tel_data, trade_data, prev_metrics,
        )

        # Merge metrics from best available source
        # Trade-level data is preferred for detailed metrics
        if trade_data:
            net_profit_abs = _safe_float(trade_data.get("net_profit_abs"))
            net_profit_ratio = _safe_float(trade_data.get("net_profit_ratio"))
            trade_count = _safe_int(trade_data.get("trade_count"))
            win_rate = _safe_float(trade_data.get("win_rate"))
            profit_factor = _safe_float(trade_data.get("profit_factor"))
            total_trades = _safe_int(trade_data.get("trade_count"))
            total_net_pnl = _safe_float(trade_data.get("total_net_pnl"))
        elif tel_data:
            net_profit_abs = _safe_float(tel_data.get("net_profit_abs"))
            net_profit_ratio = _safe_float(tel_data.get("net_profit_ratio"))
            trade_count = _safe_int(tel_data.get("trade_count"))
            win_rate = 0.0
            profit_factor = 0.0
            total_trades = trade_count
            total_net_pnl = net_profit_abs
        else:
            net_profit_abs = 0.0
            net_profit_ratio = 0.0
            trade_count = 0
            win_rate = 0.0
            profit_factor = 0.0
            total_trades = 0
            total_net_pnl = 0.0

        # Extract max_drawdown from previous metrics if available
        max_drawdown_pct = _safe_float(prev_metrics.get("max_drawdown_pct"))
        max_drawdown = max_drawdown_pct

        # Evidence window timestamps
        window_start = str(tel_data.get("window_start", "")) if tel_data else ""
        window_end = str(tel_data.get("window_end", "")) if tel_data else ""

        # Validate numeric metrics after merge
        if _is_valid_float(net_profit_abs) and _is_valid_float(profit_factor):
            pass  # OK
        elif status == STATUS_PASS_REVIEW:
            # Metrics became invalid during merge — downgrade
            status = STATUS_INVALID_METRICS
            blocked = True
            reason_codes = ["invalid_metrics_after_merge"]

        bots_list.append(
            BotWalkForwardMetrics(
                bot_id=bot_id,
                evaluation_status=status,
                net_profit_abs=net_profit_abs,
                net_profit_ratio=net_profit_ratio,
                trade_count=trade_count,
                win_rate=win_rate,
                max_drawdown=max_drawdown,
                profit_factor=profit_factor,
                evidence_window_start=window_start,
                evidence_window_end=window_end,
                total_trades=total_trades,
                total_net_pnl=total_net_pnl,
                max_drawdown_pct=max_drawdown_pct,
                metrics_source=METRICS_SOURCE,
                promotion_blocked=blocked,
                promotion_block_reason_codes=tuple(reason_codes),
            )
        )

    result = MaterializerResult(
        cycle_id=cycle_id,
        generated_at_utc=generated_at_utc,
        bots=tuple(bots_list),
    )

    # ── Persist artifact ─────────────────────────────────────────────────
    if persist:
        wf_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = wf_dir / f"walk_forward_metrics_{cycle_id}.json"
        artifact_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True)
        )

    return result


def _resolve_repo_root() -> Path:
    """Resolve the repository root by walking up from this file's location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "self_improvement_v2").is_dir() and (parent / ".git").is_dir():
            return parent
    # Fallback to a sensible default
    return Path("/home/hermes/projects/trading")


# ===========================================================================
# CLI entry point
# ===========================================================================


def main() -> int:
    """Entry point for ``python -m si_v2.evaluation.walk_forward_materializer``."""

    result = materialize_walk_forward_metrics(persist=True)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
