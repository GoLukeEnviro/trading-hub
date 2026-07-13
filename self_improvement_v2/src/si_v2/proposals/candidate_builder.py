"""SI v2 Proposal Candidate Builder.

This module takes fleet-level evidence from the multi-bot SI v2 cycle and
turns actionable hypotheses into concrete, safe, human-review-only
proposal candidates.

The implementation is intentionally pure: no I/O, no network calls, no
config writes, and no runtime mutation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median
from typing import Final

# ------------------------------------------------------------------
# JSON-safe type aliases
# ------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

# ------------------------------------------------------------------
# Safe overlay allowlist — candidate keys only (never real Freqtrade keys)
# ------------------------------------------------------------------
SAFE_OVERLAY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "max_open_trades_candidate",
        "cooldown_candles_candidate",
        "stop_duration_candles_candidate",
        "entry_threshold_candidate",
        "exit_threshold_candidate",
        "pair_cluster_action",
    }
)

# ------------------------------------------------------------------
# Actionable hypothesis constants
# ------------------------------------------------------------------
HYPOTHESIS_UNDERPERFORMING: Final[str] = "observe_underperforming_pair_cluster_v1"
HYPOTHESIS_PROFIT_DISPERSION: Final[str] = "review_fleet_profitability_dispersion_v1"
HYPOTHESIS_TRADE_DURATION: Final[str] = "review_trade_duration_outlier_v1"
HYPOTHESIS_SIGNAL_QUALITY: Final[str] = "review_entry_signal_quality_v1"
HYPOTHESIS_REINFORCE_PROFITABLE: Final[str] = "reinforce_profitable_pair_cluster_v1"

SUPPORTED_HYPOTHESES: Final[tuple[str, ...]] = (
    HYPOTHESIS_UNDERPERFORMING,
    HYPOTHESIS_PROFIT_DISPERSION,
    HYPOTHESIS_TRADE_DURATION,
    HYPOTHESIS_SIGNAL_QUALITY,
    HYPOTHESIS_REINFORCE_PROFITABLE,
)

_ACTIONABLE_HYPOTHESES: Final[frozenset[str]] = frozenset(SUPPORTED_HYPOTHESES)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BotMetrics:
    """Per-bot metrics extracted from the cycle evidence."""

    bot_id: str
    profit_pct: float
    open_trades: int
    signal_depth: float
    anomaly_flags: tuple[str, ...]
    approval_status: str
    approval_eligible: bool
    walk_forward_net_metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class FleetMetrics:
    """Fleet-wide metrics aggregated across all processed bots."""

    cycle_id: str
    bots: tuple[BotMetrics, ...]
    fleet_verdict: str
    fleet_median_profit_pct: float
    fleet_profit_range_pct: float
    total_open_trades: int
    bots_with_anomalies: int
    bots_approval_eligible: int


# Backwards-compatible alias used by older tests / docs.
FleetBotMetrics = BotMetrics


@dataclass(frozen=True)
class ProposalCandidate:
    """A concrete candidate proposal generated from actionable evidence."""

    candidate_id: str
    cycle_id: str
    proposal_type: str
    target_bot_ids: tuple[str, ...]
    hypothesis: str
    candidate_overlay: JsonObject
    expected_effect: str
    risk_notes: tuple[str, ...]
    validation_plan: JsonObject
    rollback_condition: str
    source_evidence_refs: tuple[str, ...]
    requires_human_approval: bool = True
    mutation_policy: str = "proposal_only"

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe payload for evidence-bundle persistence."""
        return {
            "candidate_id": self.candidate_id,
            "cycle_id": self.cycle_id,
            "proposal_type": self.proposal_type,
            "target_bot_ids": list(self.target_bot_ids),
            "hypothesis": self.hypothesis,
            "candidate_overlay": self.candidate_overlay,
            "expected_effect": self.expected_effect,
            "risk_notes": list(self.risk_notes),
            "validation_plan": self.validation_plan,
            "rollback_condition": self.rollback_condition,
            "source_evidence_refs": list(self.source_evidence_refs),
            "requires_human_approval": self.requires_human_approval,
            "mutation_policy": self.mutation_policy,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _candidate_id(
    cycle_id: str,
    proposal_type: str,
    target_bot_ids: tuple[str, ...],
    candidate_overlay: JsonObject,
) -> str:
    """Deterministic short SHA256 for a proposal candidate."""
    payload = {
        "cycle_id": cycle_id,
        "proposal_type": proposal_type,
        "target_bot_ids": sorted(target_bot_ids),
        "candidate_overlay": candidate_overlay,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _validate_overlay(overlay: JsonObject) -> None:
    """Raise ValueError if any overlay key is not in SAFE_OVERLAY_KEYS."""
    for key in overlay:
        if key not in SAFE_OVERLAY_KEYS:
            raise ValueError(
                f"Unsafe overlay key '{key}' — not in SAFE_OVERLAY_KEYS. "
                f"Allowed: {sorted(SAFE_OVERLAY_KEYS)}"
            )


def validate_candidate_overlay(overlay: JsonObject) -> tuple[bool, tuple[str, ...]]:
    """Compatibility wrapper that returns a boolean plus reason strings."""
    try:
        _validate_overlay(overlay)
    except ValueError as exc:
        return False, (str(exc),)
    return True, ()


def _build_validation_plan(
    proposal_type: str,
    target_bot_ids: tuple[str, ...],
) -> JsonObject:
    """Build a standard validation plan for a proposal type."""
    plan: JsonObject = {
        "backtest_required": True,
        "backtest_command": (
            "freqtrade backtesting --strategy <strategy> "
            "--timerange <timerange> --config <config>"
        ),
        "walk_forward_required": True,
        "walk_forward_min_windows": 3,
        "lookahead_analysis_required": True,
        "lookahead_command": "freqtrade lookahead-analysis --strategy <strategy>",
        "recursive_analysis_required": True,
        "recursive_command": "freqtrade recursive-analysis --strategy <strategy>",
        "profitability_gate": {
            "min_sharpe": 0.5,
            "min_win_rate_pct": 40.0,
            "min_trade_count": 20,
            "max_drawdown_pct": 25.0,
        },
        "out_of_sample_required": True,
        "out_of_sample_timerange": "most recent 30 days",
        "target_bot_count": len(target_bot_ids),
    }

    if proposal_type == HYPOTHESIS_UNDERPERFORMING:
        plan["focus"] = "pair-level profitability before/after cooldown adjustment"
        plan["pair_filter"] = "underperforming pairs only"
    elif proposal_type == HYPOTHESIS_PROFIT_DISPERSION:
        plan["focus"] = "fleet profitability dispersion reduction"
        plan["comparison_baseline"] = "fleet median metrics"
    elif proposal_type == HYPOTHESIS_TRADE_DURATION:
        plan["focus"] = "trade duration distribution before/after exit threshold change"
    elif proposal_type == HYPOTHESIS_SIGNAL_QUALITY:
        plan["focus"] = "entry signal quality metrics before/after threshold adjustment"
    elif proposal_type == HYPOTHESIS_REINFORCE_PROFITABLE:
        plan["focus"] = "profitable pair cluster reinforcement — maintain or tighten parameters"

    return plan


def _build_candidate(
    *,
    cycle_id: str,
    proposal_type: str,
    bot: BotMetrics,
    fleet: FleetMetrics,
    overlay: JsonObject,
    expected_effect: str,
    risk_notes: tuple[str, ...],
    rollback_condition: str,
    source_evidence_refs: tuple[str, ...],
) -> ProposalCandidate:
    _validate_overlay(overlay)
    target = (bot.bot_id,)
    candidate_id = _candidate_id(cycle_id, proposal_type, target, overlay)
    return ProposalCandidate(
        candidate_id=candidate_id,
        cycle_id=cycle_id,
        proposal_type=proposal_type,
        target_bot_ids=target,
        hypothesis=proposal_type,
        candidate_overlay=overlay,
        expected_effect=expected_effect,
        risk_notes=risk_notes,
        validation_plan=_build_validation_plan(proposal_type, target),
        rollback_condition=rollback_condition,
        source_evidence_refs=source_evidence_refs,
    )


def _build_underperforming_candidate(cycle_id: str, bot: BotMetrics, fleet: FleetMetrics) -> ProposalCandidate:
    return _build_candidate(
        cycle_id=cycle_id,
        proposal_type=HYPOTHESIS_UNDERPERFORMING,
        bot=bot,
        fleet=fleet,
        overlay={
            "cooldown_candles_candidate": 12,
            "max_open_trades_candidate": 2,
            "pair_cluster_action": "reduce_exposure",
        },
        expected_effect=(
            f"Reduce exposure for {bot.bot_id} (profit={bot.profit_pct:.1f}%) by increasing "
            f"cooldown and capping open trades. Expected: reduced drawdown from underperforming pairs."
        ),
        risk_notes=(
            "May reduce overall trade frequency and total profit if underperforming pairs recover.",
            "Cooldown increase could delay re-entry on recovering pairs.",
            "Fleet-level impact must be measured — single-bot optimization may degrade correlation benefits.",
        ),
        rollback_condition=(
            "If walk-forward Sharpe drops below 0.3 OR win rate drops below 35% OR drawdown increases by >5% "
            "vs baseline, revert immediately."
        ),
        source_evidence_refs=(
            f"fleet_analyzer:{cycle_id}:{bot.bot_id}:underperforming",
            f"fleet_metrics:{cycle_id}:profit_pct={bot.profit_pct}",
        ),
    )


def _build_dispersion_candidate(cycle_id: str, bot: BotMetrics, fleet: FleetMetrics) -> ProposalCandidate:
    return _build_candidate(
        cycle_id=cycle_id,
        proposal_type=HYPOTHESIS_PROFIT_DISPERSION,
        bot=bot,
        fleet=fleet,
        overlay={
            "max_open_trades_candidate": 3,
            "cooldown_candles_candidate": 6,
            "pair_cluster_action": "align_to_fleet_median",
        },
        expected_effect=(
            f"Align {bot.bot_id} parameters toward fleet median "
            f"(fleet_median_profit={fleet.fleet_median_profit_pct:.1f}%, "
            f"bot_profit={bot.profit_pct:.1f}%). Expected: reduced fleet profitability dispersion."
        ),
        risk_notes=(
            "Alignment toward median may not address root cause of dispersion.",
            "If the bot's strategy is fundamentally different, parameter alignment alone may not close the gap.",
            "Fleet median may shift after alignment — re-measure after 2 cycles.",
        ),
        rollback_condition=(
            "If fleet profit range increases after 2 cycles OR aligned bot's Sharpe drops below 0.3, revert."
        ),
        source_evidence_refs=(
            f"fleet_analyzer:{cycle_id}:{bot.bot_id}:dispersion",
            f"fleet_metrics:{cycle_id}:median={fleet.fleet_median_profit_pct}",
        ),
    )


def _build_duration_candidate(cycle_id: str, bot: BotMetrics, fleet: FleetMetrics) -> ProposalCandidate:
    return _build_candidate(
        cycle_id=cycle_id,
        proposal_type=HYPOTHESIS_TRADE_DURATION,
        bot=bot,
        fleet=fleet,
        overlay={
            "exit_threshold_candidate": -0.02,
            "stop_duration_candles_candidate": 48,
        },
        expected_effect=(
            f"Tighten exit threshold for {bot.bot_id} to reduce trade duration outliers. Expected: shorter average "
            f"trade duration and less exposure to stale positions."
        ),
        risk_notes=(
            "Tighter exit may cut winning trades short — monitor win rate closely.",
            "Stop duration cap may force exits during temporary drawdowns.",
            "Trade count may increase significantly — verify fee impact.",
        ),
        rollback_condition=(
            "If win rate drops below 35% OR average profit per trade drops by >20%, revert immediately."
        ),
        source_evidence_refs=(f"fleet_analyzer:{cycle_id}:{bot.bot_id}:duration_outlier",),
    )


def _build_signal_quality_candidate(cycle_id: str, bot: BotMetrics, fleet: FleetMetrics) -> ProposalCandidate:
    return _build_candidate(
        cycle_id=cycle_id,
        proposal_type=HYPOTHESIS_SIGNAL_QUALITY,
        bot=bot,
        fleet=fleet,
        overlay={
            "entry_threshold_candidate": 0.6,
            "cooldown_candles_candidate": 8,
        },
        expected_effect=(
            f"Raise entry threshold for {bot.bot_id} to filter low-quality signals. Expected: higher win rate and "
            f"fewer but better entries."
        ),
        risk_notes=(
            "Higher threshold may reduce trade frequency significantly.",
            "May miss profitable opportunities during high-volatility regimes.",
            f"Signal depth is currently {bot.signal_depth:.1f} — verify threshold is appropriate.",
        ),
        rollback_condition=(
            "If trade count drops below 10 per week OR win rate does not improve by >5%, revert."
        ),
        source_evidence_refs=(f"fleet_analyzer:{cycle_id}:{bot.bot_id}:signal_quality",),
    )


def _build_reinforce_candidate(cycle_id: str, bot: BotMetrics, fleet: FleetMetrics) -> ProposalCandidate:
    return _build_candidate(
        cycle_id=cycle_id,
        proposal_type=HYPOTHESIS_REINFORCE_PROFITABLE,
        bot=bot,
        fleet=fleet,
        overlay={
            "max_open_trades_candidate": 3,
            "cooldown_candles_candidate": 4,
            "pair_cluster_action": "maintain_profitable",
        },
        expected_effect=(
            f"Reinforce profitable behavior for {bot.bot_id} (profit={bot.profit_pct:.1f}%). Maintain the current "
            f"parameter regime with slight tightening. Expected: sustained profitability, reduced drift risk."
        ),
        risk_notes=(
            "Tightening may reduce adaptability to regime changes.",
            "Profitable behavior may be regime-specific — validate across multiple market conditions.",
            "Over-tightening could create fragility.",
        ),
        rollback_condition=(
            "If profit drops below 0.5% OR Sharpe drops below 0.3 in walk-forward, "
            "revert to pre-reinforcement parameters."
        ),
        source_evidence_refs=(
            f"fleet_analyzer:{cycle_id}:{bot.bot_id}:reinforce",
            f"fleet_metrics:{cycle_id}:profit_pct={bot.profit_pct}",
        ),
    )


_HYPOTHESIS_BUILDERS: Final[dict[str, Callable[[str, BotMetrics, FleetMetrics], ProposalCandidate]]] = {
    HYPOTHESIS_UNDERPERFORMING: _build_underperforming_candidate,
    HYPOTHESIS_PROFIT_DISPERSION: _build_dispersion_candidate,
    HYPOTHESIS_TRADE_DURATION: _build_duration_candidate,
    HYPOTHESIS_SIGNAL_QUALITY: _build_signal_quality_candidate,
    HYPOTHESIS_REINFORCE_PROFITABLE: _build_reinforce_candidate,
}


# ------------------------------------------------------------------
# Fleet metrics builder
# ------------------------------------------------------------------


def build_fleet_metrics_from_cycle(
    *,
    cycle_id: str,
    fleet_decision: object,  # FleetDecision from fleet_analyzer
    safety_results: list[dict[str, object]],
) -> FleetMetrics:
    """Build FleetMetrics from cycle-level data."""
    bots: list[BotMetrics] = []

    safety_by_bot: dict[str, dict[str, object]] = {}
    for sr in safety_results:
        bid = str(sr.get("bot_id", ""))
        if bid:
            safety_by_bot[bid] = dict(sr)

    per_bot = getattr(fleet_decision, "per_bot", [])
    for decision in per_bot:
        bot_id = getattr(decision, "bot_id", "")
        if not bot_id:
            continue

        evidence = getattr(decision, "evidence_summary", {}) or {}
        proposal_evidence = evidence.get("proposal_evidence", {}) or {}
        if not isinstance(proposal_evidence, dict):
            proposal_evidence = {}

        profit_pct = float(proposal_evidence.get("profit_all_percent", 0.0))
        anomalies_raw = proposal_evidence.get("anomaly_flags", [])
        anomalies: tuple[str, ...] = tuple(str(a) for a in anomalies_raw) if isinstance(anomalies_raw, list) else ()
        signal_depth = float(evidence.get("signal_depth", 0.0))
        status = evidence.get("status", {}) or {}
        if not isinstance(status, dict):
            status = {}
        open_trades = int(status.get("open_trades", 0))

        safety = safety_by_bot.get(bot_id, {})
        approval_status = str(safety.get("approval_status", "UNKNOWN"))
        approval_eligible = bool(safety.get("approval_eligible", False))
        wf_metrics = safety.get("walk_forward_net_metrics", {})
        if not isinstance(wf_metrics, dict):
            wf_metrics = {}

        bots.append(
            BotMetrics(
                bot_id=bot_id,
                profit_pct=profit_pct,
                open_trades=open_trades,
                signal_depth=signal_depth,
                anomaly_flags=anomalies,
                approval_status=approval_status,
                approval_eligible=approval_eligible,
                walk_forward_net_metrics=wf_metrics,
            )
        )

    profits = [b.profit_pct for b in bots]
    fleet_median_profit_pct = median(profits) if profits else 0.0
    fleet_profit_range_pct = (max(profits) - min(profits)) if len(profits) >= 2 else 0.0
    total_open_trades = sum(b.open_trades for b in bots)
    bots_with_anomalies = sum(1 for b in bots if b.anomaly_flags)
    bots_approval_eligible = sum(1 for b in bots if b.approval_eligible)

    fleet_summary = getattr(fleet_decision, "fleet_summary", None)
    fleet_verdict = str(getattr(fleet_summary, "fleet_verdict", "UNKNOWN"))

    return FleetMetrics(
        cycle_id=cycle_id,
        bots=tuple(bots),
        fleet_verdict=fleet_verdict,
        fleet_median_profit_pct=fleet_median_profit_pct,
        fleet_profit_range_pct=fleet_profit_range_pct,
        total_open_trades=total_open_trades,
        bots_with_anomalies=bots_with_anomalies,
        bots_approval_eligible=bots_approval_eligible,
    )


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def build_candidate_proposals(
    *,
    cycle_id: str,
    fleet_decision: object,  # FleetDecision from fleet_analyzer
    fleet_metrics: FleetMetrics,
) -> list[ProposalCandidate]:
    """Build concrete proposal candidates from fleet-level evidence."""
    candidates: list[ProposalCandidate] = []
    bot_lookup: dict[str, BotMetrics] = {bot.bot_id: bot for bot in fleet_metrics.bots}

    for decision in getattr(fleet_decision, "per_bot", []):
        if getattr(decision, "decision_type", "") != "SHADOW_PROPOSAL":
            continue

        hypothesis = getattr(decision, "hypothesis", "")
        if hypothesis not in _ACTIONABLE_HYPOTHESES:
            continue

        bot_id = getattr(decision, "bot_id", "")
        bot = bot_lookup.get(bot_id)
        if bot is None:
            continue

        builder = _HYPOTHESIS_BUILDERS.get(hypothesis)
        if builder is None:
            continue

        try:
            candidate = builder(cycle_id, bot, fleet_metrics)
        except ValueError:
            continue
        candidates.append(candidate)

    return candidates


__all__ = [
    "HYPOTHESIS_PROFIT_DISPERSION",
    "HYPOTHESIS_REINFORCE_PROFITABLE",
    "HYPOTHESIS_SIGNAL_QUALITY",
    "HYPOTHESIS_TRADE_DURATION",
    "HYPOTHESIS_UNDERPERFORMING",
    "SAFE_OVERLAY_KEYS",
    "SUPPORTED_HYPOTHESES",
    "BotMetrics",
    "FleetBotMetrics",
    "FleetMetrics",
    "ProposalCandidate",
    "build_candidate_proposals",
    "build_fleet_metrics_from_cycle",
    "validate_candidate_overlay",
]
