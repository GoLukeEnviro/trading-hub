"""SI v2 Attribution Logic v1.

Passive attribution window computation. In v1, no proposals have been
applied, so all attribution attempts return PENDING_APPLICATION.
"""

from __future__ import annotations

from si_v2.measurement.models import (
    AttributionWindow,
    BotMeasurementPoint,
    ProposalTrackingRecord,
)


def compute_attribution_window(
    proposal: ProposalTrackingRecord,
    bot_points: tuple[BotMeasurementPoint, ...],
) -> AttributionWindow:
    """Compute a pre/post window for a single proposal.

    In v1, no apply path exists. Always returns PENDING_APPLICATION.

    Args:
        proposal: The proposal record to compute attribution for.
        bot_points: All bot measurement points (used in future versions).

    Returns:
        An AttributionWindow with PENDING_APPLICATION status.
    """
    return AttributionWindow(
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        hypothesis=proposal.hypothesis,
        pre_cycle_count=0,
        post_cycle_count=0,
        pre_mean_signal_depth=None,
        post_mean_signal_depth=None,
        pre_mean_profit_pct=None,
        post_mean_profit_pct=None,
        pre_trade_count_avg=None,
        post_trade_count_avg=None,
        pre_cycles=(),
        post_cycles=(),
        attribution_status="PENDING_APPLICATION",
    )
