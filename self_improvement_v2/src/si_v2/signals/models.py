"""Typed signal models for SI v2 signal fusion.

No ``Any``. Only JSON-safe types and explicit dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# ------------------------------------------------------------------
# JSON-safe type aliases (no Any)
# ------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


# ------------------------------------------------------------------
# Signal availability and quality
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SignalAvailability:
    """Whether a read-only endpoint was available in the current cycle.

    Attributes:
        endpoint: The REST API path.
        available: True if HTTP 200 was returned.
        http_code: Actual HTTP status code (0 for connection error).
        error_summary: Short error description if not available.
    """

    endpoint: str
    available: bool
    http_code: int = 0
    error_summary: str = ""


@dataclass(frozen=True)
class SignalQuality:
    """Overall quality assessment of collected signals for one bot.

    Attributes:
        total_endpoints: Number of endpoints probed.
        available_count: Number of endpoints that returned HTTP 200.
        completeness_score: Ratio of available to total (0.0 to 1.0).
        raw_secrets_detected: True if any endpoint response contained
            secret-like keys (should always be False in production).
    """

    total_endpoints: int
    available_count: int
    completeness_score: float
    raw_secrets_detected: bool = False


# ------------------------------------------------------------------
# Per-bot signal snapshot
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BotSignalSnapshot:
    """Summarised signal snapshot for a single bot in a cycle.

    Only aggregate / redacted data. Full trade payloads are never stored.
    """

    bot_id: str
    cycle_id: str

    # Ping / basic connectivity
    ping_ok: bool
    ping_status_code: int

    # Auth outcome
    auth_outcome: str  # AUTHENTICATED | FAILED | YELLOW_MISSING_ENV_VARS | NOT_ATTEMPTED

    # Status / open trade context
    status_ok: bool
    status_open_trades: int
    status_response_summary: str

    # /api/v1/count summary
    count_current: int = 0
    count_max: int = 0
    count_total_stake: float = 0.0

    # /api/v1/profit summary (safe aggregate values only)
    profit_closed_coin: float = 0.0
    profit_closed_percent: float = 0.0
    profit_all_coin: float = 0.0
    profit_all_percent: float = 0.0
    profit_all_ratio: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0
    max_drawdown_pct: float | None = None
    bot_start_date: str = ""

    # /api/v1/performance (per-pair aggregate)
    performance_pair_count: int = 0
    performance_top_pair: str = ""
    performance_top_pair_profit_pct: float = 0.0

    # /api/v1/daily summary
    daily_trade_count_total: int = 0
    daily_abs_profit_sum: float = 0.0
    daily_abs_profit_latest: float = 0.0

    # /api/v1/whitelist
    whitelist_pair_count: int = 0
    whitelist_method: str = ""

    # /api/v1/version
    bot_version: str = ""

    # Availability tracking
    availability: tuple[SignalAvailability, ...] = ()

    # Quality
    signal_quality: SignalQuality | None = None

    # Timing
    fetched_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def signal_depth(self) -> float:
        """Overall signal depth (0.0 = none, 1.0 = all endpoints available)."""
        q = self.signal_quality
        return q.completeness_score if q else 0.0

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe dict without dataclass internals."""
        avail_list: list[JsonObject] = []
        for a in self.availability:
            avail_list.append({
                "endpoint": a.endpoint,
                "available": a.available,
                "http_code": a.http_code,
                "error": a.error_summary[:100] if a.error_summary else "",
            })

        return {
            "bot_id": self.bot_id,
            "cycle_id": self.cycle_id,
            "ping_ok": self.ping_ok,
            "ping_status_code": self.ping_status_code,
            "auth_outcome": self.auth_outcome,
            "status_ok": self.status_ok,
            "status_open_trades": self.status_open_trades,
            "count_current": self.count_current,
            "count_max": self.count_max,
            "count_total_stake": self.count_total_stake,
            "profit_closed_percent": self.profit_closed_percent,
            "profit_all_percent": self.profit_all_percent,
            "profit_all_ratio": self.profit_all_ratio,
            "num_trades": self.num_trades,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "performance_pair_count": self.performance_pair_count,
            "performance_top_pair": self.performance_top_pair,
            "performance_top_pair_profit_pct": self.performance_top_pair_profit_pct,
            "daily_trade_count_total": self.daily_trade_count_total,
            "daily_abs_profit_sum": self.daily_abs_profit_sum,
            "daily_abs_profit_latest": self.daily_abs_profit_latest,
            "whitelist_pair_count": self.whitelist_pair_count,
            "whitelist_method": self.whitelist_method,
            "bot_version": self.bot_version,
            "availability": avail_list,
            "signal_depth": self.signal_depth,
            "fetched_at_utc": self.fetched_at_utc,
        }


# ------------------------------------------------------------------
# Fleet-level snapshot
# ------------------------------------------------------------------


@dataclass(frozen=True)
class FleetSignalSnapshot:
    """Aggregate fleet-level signal snapshot from all bots.

    Attributes:
        cycle_id: Active cycle identifier.
        total_bots: Number of bots processed.
        bot_snapshots: Per-bot signal snapshots, one per bot.
        fleet_signal_depth: Mean signal depth across all bots (0.0-1.0).
        all_bots_reachable: True if every bot had ping_ok.
        all_bots_authenticated: True if every bot achieved AUTHENTICATED.
        any_profit_anomaly: True if fleet-level cross-bot profit
            dispersion exceeds the configured threshold.
        generated_at_utc: ISO 8601 timestamp.
    """

    cycle_id: str
    total_bots: int
    bot_snapshots: tuple[BotSignalSnapshot, ...] = ()
    fleet_signal_depth: float = 0.0
    all_bots_reachable: bool = False
    all_bots_authenticated: bool = False
    any_profit_anomaly: bool = False
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def has_rich_signals(self) -> bool:
        """True if at least one bot has signal_depth >= 0.5."""
        return any(snap.signal_depth >= 0.5 for snap in self.bot_snapshots)


# ------------------------------------------------------------------
# Proposal evidence summary
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ProposalEvidenceSummary:
    """Evidence summary for a single ShadowProposal.

    This replaces the generic ``JsonObject evidence_summary`` with a
    structured, typed summary that the Fleet Analyzer can inspect.

    Attributes:
        bot_id: Bot identifier.
        ping_ok: Whether ping succeeded.
        auth_outcome: Auth outcome string.
        status_open_trades: Number of open trades from /status.
        open_trade_pairs: Tuple of pair symbols with open trades.
        signal_count_available: Number of signal endpoints that responded.
        signal_count_total: Number of signal endpoints probed.
        signal_depth: Ratio signal_count_available / signal_count_total.
        profit_closed_percent: Profit percentage on closed trades.
        profit_all_percent: Overall profit percentage.
        profit_all_ratio: Overall profit ratio.
        performance_top_pairs: Up to 3 top-performing pair symbols.
        daily_trade_count_recent: Number of trades in the latest day.
        anomaly_flags: Tuple of anomaly description strings, if any.
        signal_notes: Tuple of human-readable notes about the signal data.
    """

    bot_id: str
    ping_ok: bool
    auth_outcome: str
    status_open_trades: int
    open_trade_pairs: tuple[str, ...] = ()
    signal_count_available: int = 0
    signal_count_total: int = 0
    signal_depth: float = 0.0
    profit_closed_percent: float = 0.0
    profit_all_percent: float = 0.0
    profit_all_ratio: float = 0.0
    performance_top_pairs: tuple[str, ...] = ()
    daily_trade_count_recent: int = 0
    anomaly_flags: tuple[str, ...] = ()
    signal_notes: tuple[str, ...] = ()

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe dict representation."""
        return {
            "bot_id": self.bot_id,
            "ping_ok": self.ping_ok,
            "auth_outcome": self.auth_outcome,
            "status_open_trades": self.status_open_trades,
            "open_trade_pairs": list(self.open_trade_pairs),
            "signal_count_available": self.signal_count_available,
            "signal_count_total": self.signal_count_total,
            "signal_depth": round(self.signal_depth, 4),
            "profit_closed_percent": round(self.profit_closed_percent, 4),
            "profit_all_percent": round(self.profit_all_percent, 4),
            "profit_all_ratio": round(self.profit_all_ratio, 6),
            "performance_top_pairs": list(self.performance_top_pairs),
            "daily_trade_count_recent": self.daily_trade_count_recent,
            "anomaly_flags": list(self.anomaly_flags),
            "signal_notes": list(self.signal_notes),
        }

    def is_sufficient(self) -> bool:
        """Return True if signal depth is high enough for actionable proposals.

        Requires at least ping + status + one additional endpoint.
        """
        return self.signal_count_available >= 2 and self.ping_ok
