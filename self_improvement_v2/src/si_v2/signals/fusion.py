"""Signal fusion for SI v2.

Combines per-bot signal snapshots into a fleet-level assessment and
produces proposal evidence summaries for the Fleet Analyzer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from si_v2.signals.models import (
    BotSignalSnapshot,
    FleetSignalSnapshot,
    ProposalEvidenceSummary,
)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

# Signal endpoints required for minimum viability (must always be probed)
_MIN_ENDPOINTS_MANDATORY: tuple[str, ...] = (
    "/api/v1/ping",
    "/api/v1/status",
)

# Additional endpoints that enrich proposal quality
_RICH_ENDPOINTS: tuple[str, ...] = (
    "/api/v1/count",
    "/api/v1/profit",
    "/api/v1/performance",
    "/api/v1/daily",
    "/api/v1/whitelist",
    "/api/v1/version",
)

# Profit dispersion threshold (percentage): if max - min > this, flag anomaly
_PROFIT_DISPERSION_THRESHOLD_PCT: float = 5.0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def fuse_signals(
    snapshots: list[BotSignalSnapshot],
    cycle_id: str,
) -> FleetSignalSnapshot:
    """Combine per-bot signal snapshots into a fleet-level assessment.

    Args:
        snapshots: List of BotSignalSnapshot, one per bot.
        cycle_id: Active cycle identifier.

    Returns:
        A FleetSignalSnapshot with aggregate stats.
    """
    total = len(snapshots)
    all_reachable = all(s.ping_ok for s in snapshots)
    all_authed = all(s.auth_outcome == "AUTHENTICATED" for s in snapshots)
    depths = [s.signal_depth for s in snapshots]
    fleet_depth = sum(depths) / len(depths) if depths else 0.0

    # Check profit dispersion
    profit_pcts = [
        s.profit_all_percent
        for s in snapshots
        if s.profit_all_percent != 0.0
    ]
    profit_anomaly = False
    if len(profit_pcts) >= 2:
        spread = max(profit_pcts) - min(profit_pcts)
        profit_anomaly = spread > _PROFIT_DISPERSION_THRESHOLD_PCT

    return FleetSignalSnapshot(
        cycle_id=cycle_id,
        total_bots=total,
        bot_snapshots=tuple(snapshots),
        fleet_signal_depth=round(fleet_depth, 4),
        all_bots_reachable=all_reachable,
        all_bots_authenticated=all_authed,
        any_profit_anomaly=profit_anomaly,
        generated_at_utc=datetime.now(UTC).isoformat(),
    )


def build_proposal_evidence(
    snapshot: BotSignalSnapshot,
) -> ProposalEvidenceSummary:
    """Build a typed evidence summary from a signal snapshot for analysis.

    Args:
        snapshot: A per-bot BotSignalSnapshot.

    Returns:
        A ProposalEvidenceSummary with aggregate signal values.
    """
    # Identify open trade pairs from status response if available
    open_pairs: tuple[str, ...] = ()
    if snapshot.status_response_summary:
        try:
            parsed = json.loads(snapshot.status_response_summary)
            if isinstance(parsed, list):
                open_pairs = tuple(
                    str(t.get("pair", ""))
                    for t in parsed
                    if isinstance(t, dict) and t.get("pair")
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Count available rich endpoints
    avail_count = sum(1 for a in snapshot.availability if a.available)
    total_count = len(snapshot.availability) if snapshot.availability else 0

    # Top pairs from performance
    top_pairs: tuple[str, ...] = ()
    if snapshot.performance_top_pair:
        top_pairs = (snapshot.performance_top_pair,)

    # Anomaly flags
    anomalies: list[str] = []
    if snapshot.profit_all_percent < -10.0:
        anomalies.append("profit_below_-10%")
    if snapshot.profit_closed_percent < 0 and snapshot.profit_closed_percent != 0.0:
        anomalies.append("negative_closed_profit")
    if snapshot.status_open_trades == 0 and snapshot.count_current > 0:
        # Market mismatch: count shows trades but status shows none open
        anomalies.append("trade_count_mismatch")
    if snapshot.profit_all_percent > 20.0:
        anomalies.append("profit_above_20%")

    # Signal notes
    notes: list[str] = []
    if snapshot.signal_quality:
        if snapshot.signal_quality.completeness_score >= 0.8:
            notes.append("high_signal_depth")
        elif snapshot.signal_quality.completeness_score >= 0.5:
            notes.append("moderate_signal_depth")
        else:
            notes.append("low_signal_depth")

    if snapshot.auth_outcome == "AUTHENTICATED":
        notes.append("authenticated_telemetry")

    return ProposalEvidenceSummary(
        bot_id=snapshot.bot_id,
        ping_ok=snapshot.ping_ok,
        auth_outcome=snapshot.auth_outcome,
        status_open_trades=snapshot.status_open_trades,
        open_trade_pairs=open_pairs[:3],  # limit to top 3
        signal_count_available=avail_count,
        signal_count_total=total_count,
        signal_depth=snapshot.signal_depth,
        profit_closed_percent=round(snapshot.profit_closed_percent, 4),
        profit_all_percent=round(snapshot.profit_all_percent, 4),
        profit_all_ratio=round(snapshot.profit_all_ratio, 6),
        performance_top_pairs=top_pairs[:3],
        daily_trade_count_recent=snapshot.daily_trade_count_total,
        anomaly_flags=tuple(anomalies),
        signal_notes=tuple(notes),
    )
