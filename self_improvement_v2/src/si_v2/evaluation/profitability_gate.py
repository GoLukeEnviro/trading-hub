r"""SI v2 Profitability Evidence Gate — fleet-level profitability evaluation.

This module implements a reusable, deterministic, read-only gate that
evaluates whether a four-bot fleet's profitability metrics qualify for
promotion toward pilot readiness.

It answers: "given aggregated profitability evidence across all four bots,
should the fleet be classified as candidate, blocked, or inconclusive?"

Key design decisions:
  - Pure function — no I/O, no external state, no side effects.
  - Accepts per-bot metrics as a mapping compatible with the existing
    WalkForwardEvaluation schema (dict or dataclass).
  - All thresholds are explicit parameters with conservative defaults.
  - Source validation enforces that only real metrics are accepted.
  - Fleet-aware: all four expected bots must be present.
  - Output is a structured ProfitabilityGateResult with verdict, reasons,
    per-bot verdicts, and fleet summary.

Integration:
  Called after walk-forward net metrics evaluation. The active cycle runner
  collects per-bot WalkForwardEvaluation dicts, then calls evaluate_fleet()
  to produce a single gate verdict that can be persisted in the cycle state.

Safety invariants:
  - Never modifies any external state.
  - Never enables live trading or sets dry_run to false.
  - Never changes config, strategy, or Docker state.
  - Never auto-approves or auto-promotes.
  - candidate requires real metrics from ALL four bots.
  - blocked is the default for anything incomplete or negative.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

# ---------------------------------------------------------------------------
# Expected bot IDs — matches freqtrade_bots.readonly.json registry
# ---------------------------------------------------------------------------
DEFAULT_EXPECTED_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)

# ---------------------------------------------------------------------------
# Verdict constants
# ---------------------------------------------------------------------------
VERDICT_CANDIDATE: Final[str] = "candidate"
VERDICT_BLOCKED: Final[str] = "blocked"
VERDICT_INCONCLUSIVE: Final[str] = "inconclusive"

# ---------------------------------------------------------------------------
# Metrics source constants — real sources that are accepted
# ---------------------------------------------------------------------------
REAL_METRICS_SOURCES: Final[tuple[str, ...]] = (
    "real",
    "freqtrade_rest",
    "freqtrade_telemetry",
    "walk_forward_net_metrics",
    "active_cycle",
)

BLOCKED_METRICS_SOURCES: Final[tuple[str, ...]] = (
    "synthetic",
    "stub",
    "mock",
    "fallback",
    "placeholder",
    "example",
    "test_fixture",
    "unknown",
    "none",
    "not_applicable",
)

# ---------------------------------------------------------------------------
# Default thresholds (conservative)
# ---------------------------------------------------------------------------
_MIN_TRADES_FOR_CANDIDATE: Final[int] = 5
"""Minimum trades per bot to consider metrics reliable."""

_MIN_FLEET_TRADES: Final[int] = 20
"""Minimum total trades across all four bots."""

_MIN_NET_PNL: Final[float] = 0.0
"""Fleet net PnL must be strictly above zero."""

_MIN_PROFIT_FACTOR: Final[float] = 1.0
"""Fleet profit factor must be >= 1.0."""

_MAX_DRAWDOWN_PCT: Final[float] = 15.0
"""Max drawdown threshold (%)."""

_MIN_TRADES_INCONCLUSIVE: Final[int] = 3
"""If a bot has at least this many trades but < _MIN_TRADES_FOR_CANDIDATE,
the gate may return inconclusive instead of blocked."""

# ---------------------------------------------------------------------------
# Reason code constants
# ---------------------------------------------------------------------------
REASON_MISSING_BOT: Final[str] = "missing_bot"
REASON_INVALID_SOURCE: Final[str] = "invalid_metrics_source"
REASON_INSUFFICIENT_TRADES: Final[str] = "insufficient_trades"
REASON_NEGATIVE_PNL: Final[str] = "negative_net_pnl"
REASON_LOW_PROFIT_FACTOR: Final[str] = "low_profit_factor"
REASON_HIGH_DRAWDOWN: Final[str] = "high_drawdown"
REASON_MISSING_DRAWDOWN: Final[str] = "missing_drawdown"
REASON_INCONCLUSIVE_TRADES: Final[str] = "inconclusive_trade_count"
REASON_NO_REAL_METRICS: Final[str] = "no_real_metrics"
REASON_PARTIAL_METRICS: Final[str] = "partial_real_metrics"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BotProfitabilityMetrics:
    """Per-bot profitability metrics for gate evaluation.

    These fields mirror the relevant subset of WalkForwardEvaluation /
    aggregate_metrics that the profit gate needs.
    """

    bot_id: str
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    trade_count: int = 0
    max_drawdown_pct: float = 0.0
    max_drawdown_measured: bool = False
    metrics_source: str = "unknown"
    evaluation_status: str = "NOT_APPLICABLE"

    @classmethod
    def from_walk_forward_dict(cls, bot_id: str, wf_dict: dict[str, object]) -> BotProfitabilityMetrics:
        """Build from a WalkForwardEvaluation-style dict (as stored in safety_results).

        Args:
            bot_id: Stable bot identifier.
            wf_dict: Dict with keys like total_net_pnl, profit_factor,
                     total_trades, max_drawdown_pct, evaluation_status,
                     metrics_source (or walk_forward_net_metrics nested dict).

        Returns:
            BotProfitabilityMetrics with safe defaults for missing fields.
        """
        _pnl_raw = wf_dict.get("total_net_pnl", 0.0)
        _pnl = float(_pnl_raw) if isinstance(_pnl_raw, (int, float)) else 0.0

        _pf_raw = wf_dict.get("profit_factor", 0.0)
        _pf = float(_pf_raw) if isinstance(_pf_raw, (int, float)) else 0.0

        _trades_raw = wf_dict.get("total_trades", 0)
        _trades = int(_trades_raw) if isinstance(_trades_raw, (int, float)) else 0

        _dd_raw = wf_dict.get("max_drawdown_pct", 0.0)
        _dd = float(_dd_raw) if isinstance(_dd_raw, (int, float)) else 0.0
        _dd_measured = isinstance(_dd_raw, (int, float))

        _source_raw = wf_dict.get("metrics_source", "unknown")
        _source = str(_source_raw) if isinstance(_source_raw, str) else "unknown"

        _eval_raw = wf_dict.get("evaluation_status", "NOT_APPLICABLE")
        _eval = str(_eval_raw) if isinstance(_eval_raw, str) else "NOT_APPLICABLE"

        return cls(
            bot_id=bot_id,
            net_pnl=_pnl,
            profit_factor=_pf,
            trade_count=_trades,
            max_drawdown_pct=_dd,
            max_drawdown_measured=_dd_measured,
            metrics_source=_source,
            evaluation_status=_eval,
        )


@dataclass(frozen=True)
class ProfitabilityGateResult:
    """Fleet-level profitability gate result.

    Attributes:
        verdict: One of 'candidate', 'blocked', 'inconclusive'.
        reasons: Human-readable reasons explaining the verdict.
        bot_verdicts: Per-bot verdict mapping (bot_id -> 'candidate', 'blocked', or 'inconclusive').
        fleet_summary: Aggregated fleet metrics.
    """

    verdict: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    bot_verdicts: Mapping[str, str] = field(default_factory=dict)
    fleet_summary: Mapping[str, float | int | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for embedding in cycle state / reports."""
        return {
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "bot_verdicts": dict(self.bot_verdicts),
            "fleet_summary": dict(self.fleet_summary),
        }


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------


def _is_real_source(metrics_source: str) -> bool:
    """Check whether a metrics source string is considered real.

    Returns True for known real sources. Returns False for blocked,
    unknown, or empty sources.
    """
    source_lower = metrics_source.strip().lower()
    if not source_lower:
        return False
    if source_lower in BLOCKED_METRICS_SOURCES:
        return False
    # Unknown sources are treated as non-real (safe default)
    return source_lower in REAL_METRICS_SOURCES


# ---------------------------------------------------------------------------
# Per-bot verdict helper
# ---------------------------------------------------------------------------


def _classify_bot(metrics: BotProfitabilityMetrics) -> tuple[str, list[str]]:
    """Classify a single bot's profitability as candidate/blocked/inconclusive.

    Returns:
        Tuple of (verdict, reason_codes).
    """
    reasons: list[str] = []

    # Source check — must be real
    if not _is_real_source(metrics.metrics_source):
        return (VERDICT_BLOCKED, [REASON_INVALID_SOURCE])

    # Drawdown must be measured
    if not metrics.max_drawdown_measured:
        reasons.append(REASON_MISSING_DRAWDOWN)
        return (VERDICT_BLOCKED, reasons)

    # Drawdown threshold
    if metrics.max_drawdown_pct >= _MAX_DRAWDOWN_PCT:
        reasons.append(REASON_HIGH_DRAWDOWN)

    # Trade count check
    if metrics.trade_count < _MIN_TRADES_FOR_CANDIDATE:
        if metrics.trade_count >= _MIN_TRADES_INCONCLUSIVE and not reasons:
            # Partial evidence — inconclusive rather than blocked
            return (VERDICT_INCONCLUSIVE, [REASON_INCONCLUSIVE_TRADES])
        reasons.append(REASON_INSUFFICIENT_TRADES)

    # Net PnL
    if metrics.net_pnl <= _MIN_NET_PNL:
        reasons.append(REASON_NEGATIVE_PNL)

    # Profit factor
    if metrics.profit_factor < _MIN_PROFIT_FACTOR:
        reasons.append(REASON_LOW_PROFIT_FACTOR)

    if reasons:
        return (VERDICT_BLOCKED, reasons)

    return (VERDICT_CANDIDATE, [])


# ---------------------------------------------------------------------------
# Fleet-level evaluation
# ---------------------------------------------------------------------------


def evaluate_fleet(
    bot_metrics: Sequence[BotProfitabilityMetrics],
    *,
    expected_bot_ids: tuple[str, ...] = DEFAULT_EXPECTED_BOT_IDS,
) -> ProfitabilityGateResult:
    """Evaluate fleet-level profitability evidence.

    Args:
        bot_metrics: Per-bot metrics for all bots in the fleet.
        expected_bot_ids: Tuple of bot IDs expected in the fleet. Defaults to
            the four production dry-run bots.

    Returns:
        ProfitabilityGateResult with fleet-level verdict.

    The gate is fleet-aware:
      - All expected bots must be present.
      - Each bot is classified individually.
      - Fleet-level aggregates are computed from all bots.
      - The fleet verdict is the most restrictive per-bot verdict unless
        fleet-level thresholds are also breached.

    Verdict logic:
      - BLOCKED if any bot is blocked (hard fail).
      - INCONCLUSIVE if any bot is inconclusive and none are blocked.
      - CANDIDATE only if ALL bots are candidate AND fleet aggregates pass.
    """
    fleet_reasons: list[str] = []

    # ── Check bot coverage ─────────────────────────────────────────────
    seen_bot_ids = {m.bot_id for m in bot_metrics}
    missing = [bid for bid in expected_bot_ids if bid not in seen_bot_ids]
    if missing:
        return ProfitabilityGateResult(
            verdict=VERDICT_BLOCKED,
            reasons=(f"{REASON_MISSING_BOT}: {', '.join(missing)}",),
            bot_verdicts={bid: VERDICT_BLOCKED for bid in expected_bot_ids},
            fleet_summary={"bots_found": len(seen_bot_ids), "bots_expected": len(expected_bot_ids)},
        )

    # ── Per-bot classification ─────────────────────────────────────────
    bot_verdicts: dict[str, str] = {}
    for bm in bot_metrics:
        v, _ = _classify_bot(bm)
        bot_verdicts[bm.bot_id] = v

    # ── Fleet aggregate metrics ────────────────────────────────────────
    total_trades = sum(bm.trade_count for bm in bot_metrics)
    total_pnl = sum(bm.net_pnl for bm in bot_metrics)
    max_fleet_drawdown = max(bm.max_drawdown_pct for bm in bot_metrics)

    # Compute fleet profit factor as weighted aggregate
    # (sum of profits / sum of losses where profit_factor = profit/loss)
    # For simplicity: treat profit_factor < 1 as contributing negatively
    fleet_profit_factor = _compute_fleet_profit_factor(bot_metrics)

    fleet_summary: dict[str, float | int | str] = {
        "total_trades": total_trades,
        "total_net_pnl": round(total_pnl, 8),
        "max_drawdown_pct": round(max_fleet_drawdown, 4),
        "fleet_profit_factor": round(fleet_profit_factor, 4),
        "bot_count": len(bot_metrics),
        "candidate_count": sum(1 for v in bot_verdicts.values() if v == VERDICT_CANDIDATE),
        "blocked_count": sum(1 for v in bot_verdicts.values() if v == VERDICT_BLOCKED),
        "inconclusive_count": sum(1 for v in bot_verdicts.values() if v == VERDICT_INCONCLUSIVE),
    }

    # ── Fleet verdict ──────────────────────────────────────────────────
    # BLOCKED verdict: at least one bot is blocked
    blocked_bots = [bid for bid, v in bot_verdicts.items() if v == VERDICT_BLOCKED]
    if blocked_bots:
        fleet_reasons.append(f"blocked_bots: {', '.join(blocked_bots)}")

    # INCONCLUSIVE verdict: at least one bot inconclusive (none blocked)
    inconclusive_bots = [bid for bid, v in bot_verdicts.items() if v == VERDICT_INCONCLUSIVE]
    if inconclusive_bots and not blocked_bots:
        fleet_reasons.append(f"inconclusive_bots: {', '.join(inconclusive_bots)}")

    # Fleet-level threshold checks (only when not already blocked)
    if not blocked_bots:
        if total_trades < _MIN_FLEET_TRADES:
            fleet_reasons.append(f"fleet_trades_{total_trades}_below_{_MIN_FLEET_TRADES}")

        if total_pnl <= _MIN_NET_PNL:
            fleet_reasons.append(f"fleet_net_pnl_{total_pnl}_not_positive")

        if fleet_profit_factor < _MIN_PROFIT_FACTOR:
            fleet_reasons.append(f"fleet_profit_factor_{fleet_profit_factor}_below_{_MIN_PROFIT_FACTOR}")

        if max_fleet_drawdown >= _MAX_DRAWDOWN_PCT:
            fleet_reasons.append(f"fleet_drawdown_{max_fleet_drawdown}_above_{_MAX_DRAWDOWN_PCT}")

    # ── Determine final verdict ────────────────────────────────────────
    if blocked_bots or fleet_reasons:
        # Check if we should downgrade to inconclusive instead of blocked
        # Only when no bot has hard failures and fleet issues are trade-count based
        if not blocked_bots and all(
            r.startswith("inconclusive") or r.startswith("fleet_trades")
            for r in fleet_reasons
        ):
            return ProfitabilityGateResult(
                verdict=VERDICT_INCONCLUSIVE,
                reasons=tuple(fleet_reasons),
                bot_verdicts=bot_verdicts,
                fleet_summary=fleet_summary,
            )
        return ProfitabilityGateResult(
            verdict=VERDICT_BLOCKED,
            reasons=tuple(fleet_reasons) if fleet_reasons else ("unknown_fleet_block",),
            bot_verdicts=bot_verdicts,
            fleet_summary=fleet_summary,
        )

    # All bots candidate + fleet thresholds pass
    if inconclusive_bots:
        return ProfitabilityGateResult(
            verdict=VERDICT_INCONCLUSIVE,
            reasons=tuple(fleet_reasons) if fleet_reasons else ("inconclusive_bots_present",),
            bot_verdicts=bot_verdicts,
            fleet_summary=fleet_summary,
        )

    return ProfitabilityGateResult(
        verdict=VERDICT_CANDIDATE,
        reasons=(),
        bot_verdicts=bot_verdicts,
        fleet_summary=fleet_summary,
    )


# ---------------------------------------------------------------------------
# Fleet profit factor helper
# ---------------------------------------------------------------------------


def _compute_fleet_profit_factor(
    bot_metrics: Sequence[BotProfitabilityMetrics],
) -> float:
    """Compute a fleet-level profit factor from per-bot metrics.

    Uses a simplified model: sum of positive net_pnl contributions vs
    sum of absolute negative net_pnl contributions.
    If no negative contributions exist and total is positive, returns 999.
    If total is zero or negative and no positive contributions, returns 0.
    """
    total_positive = sum(bm.net_pnl for bm in bot_metrics if bm.net_pnl > 0)
    total_negative = abs(sum(bm.net_pnl for bm in bot_metrics if bm.net_pnl < 0))

    if total_negative == 0:
        return 999.0 if total_positive > 0 else 0.0

    return round(total_positive / total_negative, 4)


# ---------------------------------------------------------------------------
# Convenience: evaluate from a list of WalkForwardEvaluation dicts
# ---------------------------------------------------------------------------


def evaluate_from_walk_forward_dicts(
    bot_metrics_dicts: Mapping[str, dict[str, object]],
    *,
    expected_bot_ids: tuple[str, ...] = DEFAULT_EXPECTED_BOT_IDS,
) -> ProfitabilityGateResult:
    """Convenience wrapper that builds BotProfitabilityMetrics from dicts.

    Args:
        bot_metrics_dicts: Mapping of bot_id -> WalkForwardEvaluation-style dict.
        expected_bot_ids: Expected bot IDs in the fleet.

    Returns:
        ProfitabilityGateResult.
    """
    metrics_list = [
        BotProfitabilityMetrics.from_walk_forward_dict(bot_id, wf_dict)
        for bot_id, wf_dict in bot_metrics_dicts.items()
    ]
    return evaluate_fleet(metrics_list, expected_bot_ids=expected_bot_ids)
