"""Read-only Freqtrade signal collection for SI v2.

Collects summaries from authenticated Freqtrade REST endpoints and produces
typed ``BotSignalSnapshot`` instances. All values are aggregate/redacted;
full trade payloads are never stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from si_v2.adapters.freqtrade_rest_readonly import (
    SIV2FreqtradeTelemetryConnector,
)
from si_v2.signals.models import (
    BotSignalSnapshot,
    SignalAvailability,
    SignalQuality,
)

# ------------------------------------------------------------------
# Endpoint list for signal collection (all in the GET allowlist)
# ------------------------------------------------------------------
_SIGNAL_ENDPOINTS: tuple[str, ...] = (
    "/api/v1/ping",
    "/api/v1/status",
    "/api/v1/count",
    "/api/v1/profit",
    "/api/v1/performance",
    "/api/v1/daily",
    "/api/v1/whitelist",
    "/api/v1/version",
)


def collect_bot_signals(
    connector: SIV2FreqtradeTelemetryConnector,
    bot_id: str,
    cycle_id: str,
) -> BotSignalSnapshot:
    """Collect summarised signals from a single bot.

    Args:
        connector: An authenticated connector instance for the bot.
        bot_id: Bot identifier.
        cycle_id: Current cycle ID for traceability.

    Returns:
        A BotSignalSnapshot with aggregate/redacted data. Missing endpoints
        degrade signal_quality.completeness_score but do not crash.
    """
    avail_list: list[SignalAvailability] = []
    responses: dict[str, object] = {}

    for ep in _SIGNAL_ENDPOINTS:
        try:
            snap = connector.fetch_snapshot(ep)
            avail_list.append(
                SignalAvailability(
                    endpoint=ep,
                    available=snap.ok,
                    http_code=snap.status_code,
                    error_summary="" if snap.ok else snap.response_summary[:100],
                )
            )
            data = _try_parse_json(snap.response_summary) if snap.ok else None
            responses[ep] = data
        except (ValueError, RuntimeError) as exc:
            avail_list.append(
                SignalAvailability(
                    endpoint=ep,
                    available=False,
                    http_code=0,
                    error_summary=str(exc)[:100],
                )
            )
            responses[ep] = None

    # Count available endpoints
    available_count = sum(1 for a in avail_list if a.available)
    total = len(avail_list)
    completeness = available_count / total if total > 0 else 0.0

    quality = SignalQuality(
        total_endpoints=total,
        available_count=available_count,
        completeness_score=round(completeness, 4),
        raw_secrets_detected=False,
    )

    # Extract aggregate values from responses
    status_data: list = responses.get("/api/v1/status") or []  # type: ignore[assignment]
    count_data: dict = responses.get("/api/v1/count") or {}  # type: ignore[assignment]
    profit_data: dict = responses.get("/api/v1/profit") or {}  # type: ignore[assignment]
    perf_data: list = responses.get("/api/v1/performance") or []  # type: ignore[assignment]
    daily_data: dict = responses.get("/api/v1/daily") or {}  # type: ignore[assignment]
    whitelist_data: dict = responses.get("/api/v1/whitelist") or {}  # type: ignore[assignment]
    version_data: dict = responses.get("/api/v1/version") or {}  # type: ignore[assignment]

    # /status — open trades
    status_open_trades = len(status_data) if isinstance(status_data, list) else 0

    # /count
    count_current = _safe_int(count_data.get("current"), 0)
    count_max = _safe_int(count_data.get("max"), 0)
    count_total_stake = _safe_float(count_data.get("total_stake"), 0.0)

    # /profit
    profit_closed_percent = _safe_float(profit_data.get("profit_closed_percent"), 0.0)
    profit_all_percent = _safe_float(profit_data.get("profit_all_percent"), 0.0)
    profit_all_ratio = _safe_float(profit_data.get("profit_all_ratio"), 0.0)
    profit_closed_coin = _safe_float(profit_data.get("profit_closed_coin"), 0.0)
    profit_all_coin = _safe_float(profit_data.get("profit_all_coin"), 0.0)
    num_trades = _safe_int(profit_data.get("num_trades"), 0)
    profit_factor = _safe_float(profit_data.get("profit_factor"), 0.0)
    bot_start_date = str(profit_data.get("bot_start_date", ""))

    # /performance
    perf_pair_count = len(perf_data) if isinstance(perf_data, list) else 0
    perf_top_pair = ""
    perf_top_profit_pct = 0.0
    if isinstance(perf_data, list) and perf_data:
        sorted_perf = sorted(
            perf_data,
            key=lambda x: _safe_float(x.get("profit_pct"), 0.0),  # type: ignore[arg-type]
            reverse=True,
        )
        if sorted_perf:
            best = sorted_perf[0]
            perf_top_pair = str(best.get("pair", ""))
            perf_top_profit_pct = _safe_float(best.get("profit_pct"), 0.0)

    # /daily
    daily_trade_count_total = 0
    daily_abs_profit_sum = 0.0
    daily_abs_profit_latest = 0.0
    daily_raw = daily_data.get("data")
    if isinstance(daily_raw, list):
        daily_trade_count_total = sum(
            _safe_int(entry.get("trade_count"), 0) for entry in daily_raw
        )
        daily_abs_profit_sum = sum(
            _safe_float(entry.get("abs_profit"), 0.0) for entry in daily_raw
        )
        if daily_raw:
            daily_abs_profit_latest = _safe_float(
                daily_raw[0].get("abs_profit"), 0.0
            )

    # /whitelist
    whitelist_pairs = whitelist_data.get("whitelist", [])
    whitelist_pair_count = (
        len(whitelist_pairs) if isinstance(whitelist_pairs, list) else 0
    )
    whitelist_method = str(whitelist_data.get("method", ""))

    # /version
    bot_version = str(version_data.get("version", ""))

    # Determine ping info from first avail entry
    ping_ok = False
    ping_code = 0
    first_ping = next(
        (a for a in avail_list if a.endpoint == "/api/v1/ping"), None
    )
    if first_ping:
        ping_ok = first_ping.available
        ping_code = first_ping.http_code

    # Auth outcome from connector
    auth_outcome: str
    if not connector.auth_enabled:
        auth_outcome = "NOT_ATTEMPTED"
    elif connector.authenticated:
        auth_outcome = "AUTHENTICATED"
    else:
        auth_outcome = "FAILED"

    return BotSignalSnapshot(
        bot_id=bot_id,
        cycle_id=cycle_id,
        ping_ok=ping_ok,
        ping_status_code=ping_code,
        auth_outcome=auth_outcome,
        status_ok=any(
            a.available for a in avail_list if a.endpoint == "/api/v1/status"
        ),
        status_open_trades=status_open_trades,
        status_response_summary=(
            json.dumps(status_data[:2], sort_keys=True)[:200]
            if isinstance(status_data, list)
            else ""
        ),
        count_current=count_current,
        count_max=count_max,
        count_total_stake=count_total_stake,
        profit_closed_coin=profit_closed_coin,
        profit_closed_percent=profit_closed_percent,
        profit_all_coin=profit_all_coin,
        profit_all_percent=profit_all_percent,
        profit_all_ratio=profit_all_ratio,
        num_trades=num_trades,
        profit_factor=profit_factor,
        bot_start_date=bot_start_date,
        performance_pair_count=perf_pair_count,
        performance_top_pair=perf_top_pair,
        performance_top_pair_profit_pct=perf_top_profit_pct,
        daily_trade_count_total=daily_trade_count_total,
        daily_abs_profit_sum=daily_abs_profit_sum,
        daily_abs_profit_latest=daily_abs_profit_latest,
        whitelist_pair_count=whitelist_pair_count,
        whitelist_method=whitelist_method,
        bot_version=bot_version,
        availability=tuple(avail_list),
        signal_quality=quality,
        fetched_at_utc=datetime.now(UTC).isoformat(),
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _try_parse_json(text: str) -> object:
    """Try to parse a response summary string back to JSON."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
