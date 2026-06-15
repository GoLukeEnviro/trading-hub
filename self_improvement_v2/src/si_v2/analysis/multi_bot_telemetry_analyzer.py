"""Multi-bot telemetry analyzer for SI v2.

Compares authenticated telemetry from all four Freqtrade dry-run bots and
generates a conservative, proposal-only analysis result.

Analysis rules (Phase 1, conservative):
1. Check that all four bots provided telemetry endpoints.
2. Compare comparable profit/count/status signals across bots.
3. Identify the weakest-performing bot only if enough data exists.
4. If data is insufficient, return INSUFFICIENT_EVIDENCE.
5. Never mutate, apply, or execute anything.

Output is always ANALYSIS_ONLY_RISK_REVIEW — never an actionable parameter change.
"""

from __future__ import annotations

import json
from typing import Final

# ---------------------------------------------------------------------------
# JSON type aliases (no Any)
# ---------------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INSUFFICIENT_EVIDENCE: Final[str] = "INSUFFICIENT_EVIDENCE"
ANALYSIS_ONLY_RISK_REVIEW: Final[str] = "ANALYSIS_ONLY_RISK_REVIEW"
PARAMETER_REVIEW_CANDIDATE: Final[str] = "PARAMETER_REVIEW_CANDIDATE"

# Minimum number of bots with comparable profit data to trigger fleet comparison
MIN_PROFIT_BOTS_FOR_COMPARISON: Final[int] = 2

# Minimum number of status-like endpoints expected per bot
MIN_ENDPOINTS_FOR_GREEN: Final[int] = 4
MIN_ENDPOINTS_FOR_YELLOW: Final[int] = 1


# ---------------------------------------------------------------------------
# Sanitized input: per-bot endpoint summary
# ---------------------------------------------------------------------------


class BotEndpointSummary:
    """Sanitized summary of one bot's endpoint results.

    Excludes raw response bodies, tokens, and credentials.
    Not a dataclass to avoid Python 3.13 importlib compatibility issues.
    """

    __slots__ = ("bot_id", "classification", "endpoints_ok", "endpoints_total",
                 "profit_telemetry_available", "profit_value",
                 "count_open_trades", "status_healthy")

    def __init__(self, bot_id: str = "", classification: str = "RED",
                 endpoints_ok: int = 0, endpoints_total: int = 0,
                 profit_telemetry_available: bool = False,
                 profit_value: float | None = None,
                 count_open_trades: int | None = None,
                 status_healthy: bool | None = None) -> None:
        self.bot_id = bot_id
        self.classification = classification
        self.endpoints_ok = endpoints_ok
        self.endpoints_total = endpoints_total
        self.profit_telemetry_available = profit_telemetry_available
        self.profit_value = profit_value
        self.count_open_trades = count_open_trades
        self.status_healthy = status_healthy


# ---------------------------------------------------------------------------
# Analysis result
# ---------------------------------------------------------------------------


class FleetAnalysis:
    """Conservative analysis result for the fleet.
    Not a dataclass to avoid Python 3.13 importlib compatibility issues.
    """

    __slots__ = (
        "analysis_type", "bots_total", "bots_green", "bots_yellow",
        "bots_red", "endpoints_ok", "endpoints_failed", "weakest_bot",
        "weakest_bot_reason", "fleet_median_profit", "confidence",
        "recommendation_type", "caveats", "validation_required", "error",
    )

    def __init__(self, analysis_type: str = ANALYSIS_ONLY_RISK_REVIEW,
                 bots_total: int = 0, bots_green: int = 0,
                 bots_yellow: int = 0, bots_red: int = 0,
                 endpoints_ok: int = 0, endpoints_failed: int = 0,
                 weakest_bot: str | None = None,
                 weakest_bot_reason: str = "",
                 fleet_median_profit: float | None = None,
                 confidence: str = "LOW",
                 recommendation_type: str = "ANALYSIS_ONLY",
                 caveats: list[str] | None = None,
                 validation_required: list[str] | None = None,
                 error: str = "") -> None:
        self.analysis_type = analysis_type
        self.bots_total = bots_total
        self.bots_green = bots_green
        self.bots_yellow = bots_yellow
        self.bots_red = bots_red
        self.endpoints_ok = endpoints_ok
        self.endpoints_failed = endpoints_failed
        self.weakest_bot = weakest_bot
        self.weakest_bot_reason = weakest_bot_reason
        self.fleet_median_profit = fleet_median_profit
        self.confidence = confidence
        self.recommendation_type = recommendation_type
        self.caveats = caveats or []
        self.validation_required = validation_required or []
        self.error = error


# ---------------------------------------------------------------------------
# JSON parsing helpers (safe, no Any, no type: ignore)
# ---------------------------------------------------------------------------


def _parse_profit_value(summary: str) -> float | None:
    """Safely parse a profit metric from a Freqtrade /profit response summary.

    Tries fields in order: profit_all_ratio, profit_closed_ratio,
    profit_all_abs, profit_closed_coin (as float).

    Args:
        summary: The response_summary string from the connector snapshot.

    Returns:
        A float profit value, or None if parsing fails or no field matches.
    """
    if not summary or not isinstance(summary, str):
        return None
    try:
        data = json.loads(summary)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    for key in ("profit_all_ratio", "profit_closed_ratio",
                "profit_all_abs", "profit_closed_coin"):
        val = data.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _parse_count_value(summary: str) -> int | None:
    """Safely parse a count value from a Freqtrade /count response summary.

    Tries fields: current, count, open_trades. Falls back to parsing the
    entire response as a plain integer.

    Args:
        summary: The response_summary string from the connector snapshot.

    Returns:
        An integer count, or None if parsing fails.
    """
    if not summary or not isinstance(summary, str):
        return None
    try:
        data = json.loads(summary)
    except (json.JSONDecodeError, ValueError):
        # Try plain integer parsing
        try:
            return int(summary.strip())
        except (ValueError, TypeError):
            return None
    if isinstance(data, dict):
        for key in ("current", "count", "open_trades"):
            val = data.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
    if isinstance(data, (int, float)):
        return int(data)
    return None


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def analyze_fleet(
    bot_summaries: list[BotEndpointSummary],
) -> FleetAnalysis:
    """Analyze fleet telemetry and produce a conservative analysis result.

    Args:
        bot_summaries: Sanitized per-bot endpoint summaries.

    Returns:
        FleetAnalysis with deterministic result. Never raises.
    """
    if not bot_summaries:
        return FleetAnalysis(
            analysis_type=ANALYSIS_ONLY_RISK_REVIEW,
            error="No bot summaries provided",
            confidence="LOW",
        )

    total = len(bot_summaries)
    green = sum(1 for b in bot_summaries if b.classification == "GREEN")
    yellow = sum(1 for b in bot_summaries if b.classification == "YELLOW")
    red = sum(1 for b in bot_summaries if b.classification == "RED")
    endpoints_ok = sum(b.endpoints_ok for b in bot_summaries)
    endpoints_failed = sum(b.endpoints_total - b.endpoints_ok for b in bot_summaries)

    caveats: list[str] = []
    validation: list[str] = []

    # Collect profit telemetry across bots
    bots_with_profit = [b for b in bot_summaries if b.profit_value is not None]

    fleet_median_profit: float | None = None
    weakest_bot: str | None = None
    weakest_reason = ""
    confidence = "LOW"

    if len(bots_with_profit) >= MIN_PROFIT_BOTS_FOR_COMPARISON:
        # Compute median profit
        profit_values = sorted(
            b.profit_value for b in bots_with_profit
            if b.profit_value is not None
        )
        n = len(profit_values)
        if n % 2 == 1:
            fleet_median_profit = profit_values[n // 2]
        else:
            fleet_median_profit = (profit_values[n // 2 - 1] + profit_values[n // 2]) / 2.0

        # Find weakest: bot with lowest profit, by some margin
        worst = min(
            bots_with_profit,
            key=lambda b: b.profit_value if b.profit_value is not None else 0.0,
        )
        if worst.profit_value is not None and fleet_median_profit is not None:
            if worst.profit_value < fleet_median_profit * 0.8:
                weakest_bot = worst.bot_id
                weakest_reason = (
                    f"profit ratio {worst.profit_value:.4f} is "
                    f"below 80% of fleet median {fleet_median_profit:.4f}"
                )

        confidence = "MEDIUM"
    else:
        caveats.append(
            f"Insufficient profit data: {len(bots_with_profit)}/"
            f"{total} bots have profit telemetry. "
            f"Fleet comparison deferred."
        )

    # Validation requirements
    if weakest_bot:
        validation.append(
            f"Apply requires: 3+ historical runs, backtest for "
            f"{weakest_bot}, walk-forward validation, and operator review."
        )
    else:
        validation.append("No weakest bot detected. Fleet is performing within bounds.")

    if not weakest_bot and not caveats:
        caveats.append("No significant anomaly detected in this snapshot.")

    # Build deterministic analysis
    analysis = FleetAnalysis(
        analysis_type=ANALYSIS_ONLY_RISK_REVIEW,
        bots_total=total,
        bots_green=green,
        bots_yellow=yellow,
        bots_red=red,
        endpoints_ok=endpoints_ok,
        endpoints_failed=endpoints_failed,
        weakest_bot=weakest_bot,
        weakest_bot_reason=weakest_reason,
        fleet_median_profit=fleet_median_profit,
        confidence=confidence,
        recommendation_type=PARAMETER_REVIEW_CANDIDATE if weakest_bot else "ANALYSIS_ONLY",
        caveats=caveats,
        validation_required=validation,
    )

    return analysis


# ---------------------------------------------------------------------------
# Helper: build bot summaries from proof telemetry results
# ---------------------------------------------------------------------------


def build_bot_summaries(
    bot_results: list[object],
) -> list[BotEndpointSummary]:
    """Convert proof-level bot results to sanitized analysis summaries.

    Args:
        bot_results: List of BotTelemetryResult objects from the proof.

    Returns:
        List of BotEndpointSummary with only safe numeric/profiling fields.
    """
    summaries: list[BotEndpointSummary] = []

    for bot in bot_results:
        # Duck-type access to avoid coupling to proof module
        bot_id = getattr(bot, "bot_id", "unknown")
        classification = getattr(bot, "classification", "RED")
        endpoints = getattr(bot, "endpoints", {})

        if not isinstance(endpoints, dict):
            summaries.append(
                BotEndpointSummary(
                    bot_id=str(bot_id), classification=str(classification),
                    endpoints_ok=0, endpoints_total=0,
                )
            )
            continue

        total_eps = len(endpoints)
        ok_eps = sum(
            1 for e in endpoints.values()
            if isinstance(e, dict) and e.get("ok")
        )

        # Extract /profit value if available
        profit_result = endpoints.get("/api/v1/profit", {})
        profit_value: float | None = None
        profit_available = False
        if isinstance(profit_result, dict) and profit_result.get("ok"):
            summary = profit_result.get("response_summary", "")
            if isinstance(summary, str) and summary:
                profit_available = True
                profit_value = _parse_profit_value(summary)

        # Extract /count if available
        count_open: int | None = None
        count_result = endpoints.get("/api/v1/count", {})
        if isinstance(count_result, dict) and count_result.get("ok"):
            summary = count_result.get("response_summary", "")
            if isinstance(summary, str) and summary:
                count_open = _parse_count_value(summary)

        # Extract /status if available
        status_healthy: bool | None = None
        status_result = endpoints.get("/api/v1/status", {})
        if isinstance(status_result, dict) and status_result.get("ok"):
            status_healthy = True

        summaries.append(
            BotEndpointSummary(
                bot_id=str(bot_id),
                classification=str(classification),
                endpoints_ok=ok_eps,
                endpoints_total=total_eps,
                profit_telemetry_available=profit_available,
                profit_value=profit_value,
                count_open_trades=count_open,
                status_healthy=status_healthy,
            )
        )

    return summaries
