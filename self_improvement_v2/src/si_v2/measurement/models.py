"""Typed measurement models for SI v2 Measurement and Attribution Ledger v1.

No ``Any``. Only explicit dataclasses and JSON-safe aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ------------------------------------------------------------------
# JSON-safe type aliases (no Any)
# ------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


# ------------------------------------------------------------------
# Status enumerations
# ------------------------------------------------------------------


class MeasurementStatus(StrEnum):
    """Status of a measurement point or ledger entry."""

    BASELINE_ONLY = "BASELINE_ONLY"
    PENDING_APPLICATION = "PENDING_APPLICATION"
    APPLIED_AWAITING_POST_WINDOW = "APPLIED_AWAITING_POST_WINDOW"
    ATTRIBUTED = "ATTRIBUTED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AttributionStatus(StrEnum):
    """Status of a proposal attribution attempt."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING_APPLICATION = "PENDING_APPLICATION"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    AWAITING_POST_WINDOW = "AWAITING_POST_WINDOW"
    ATTRIBUTED_POSITIVE = "ATTRIBUTED_POSITIVE"
    ATTRIBUTED_NEUTRAL = "ATTRIBUTED_NEUTRAL"
    ATTRIBUTED_NEGATIVE = "ATTRIBUTED_NEGATIVE"
    ATTRIBUTION_FAILED = "ATTRIBUTION_FAILED"


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BotMeasurementPoint:
    """Stable per-bot measurement for a single active cycle.

    Attributes:
        cycle_id: The cycle this measurement was captured in.
        cycle_timestamp: ISO 8601 timestamp of the cycle.
        bot_id: Bot identifier.
        fleet_verdict: Overall fleet verdict in this cycle.
        decision_type: SHADOW_PROPOSAL or NO_PROPOSAL.
        hypothesis: The hypothesis string or empty string.
        approval_status: PENDING_HUMAN or similar.
        candidate_sha256: Candidate SHA-256 if SHADOW_PROPOSAL, else "".
        signal_depth: Signal depth score (0.0-1.0) or 0.0 if unavailable.
        ping_ok: Whether /api/v1/ping returned 200.
        auth_ok: Whether authentication succeeded.
        status_ok: Whether /api/v1/status returned 200.
        open_trade_count: Number of open trades or None.
        count_current: Current open trades from /count or None.
        count_max: Max allowed trades or None.
        profit_all_percent: Overall profit percentage or None.
        profit_all_ratio: Overall profit ratio or None.
        daily_trade_count: Recent trade count from /daily or None.
        whitelist_pair_count: Number of whitelisted pairs or None.
        runtime_mutations: Runtime mutation counter.
        config_mutations: Config mutation counter.
        live_trading_mutations: Live trading mutation counter.
        docker_mutations: Docker mutation counter.
        strategy_mutations: Strategy mutation counter.
        controller_state: Controller state string.
        measurement_status: Status of this measurement.
        source_artifact: Relative path to the cycle state file.
    """

    cycle_id: str
    cycle_timestamp: str
    bot_id: str
    fleet_verdict: str
    decision_type: str
    hypothesis: str
    approval_status: str
    candidate_sha256: str
    signal_depth: float
    ping_ok: bool
    auth_ok: bool
    status_ok: bool
    open_trade_count: int | None
    count_current: int | None
    count_max: int | None
    profit_all_percent: float | None
    profit_all_ratio: float | None
    daily_trade_count: int | None
    whitelist_pair_count: int | None
    runtime_mutations: int
    config_mutations: int
    live_trading_mutations: int
    docker_mutations: int
    strategy_mutations: int
    controller_state: str
    measurement_status: str  # MeasurementStatus value
    source_artifact: str

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe dict for ledger output."""
        return {
            "cycle_id": self.cycle_id,
            "cycle_timestamp": self.cycle_timestamp,
            "bot_id": self.bot_id,
            "fleet_verdict": self.fleet_verdict,
            "decision_type": self.decision_type,
            "hypothesis": self.hypothesis,
            "approval_status": self.approval_status,
            "candidate_sha256": self.candidate_sha256,
            "signal_depth": round(self.signal_depth, 4),
            "ping_ok": self.ping_ok,
            "auth_ok": self.auth_ok,
            "status_ok": self.status_ok,
            "open_trade_count": self.open_trade_count,
            "count_current": self.count_current,
            "count_max": self.count_max,
            "profit_all_percent": (
                round(self.profit_all_percent, 4) if self.profit_all_percent is not None else None
            ),
            "profit_all_ratio": (
                round(self.profit_all_ratio, 6) if self.profit_all_ratio is not None else None
            ),
            "daily_trade_count": self.daily_trade_count,
            "whitelist_pair_count": self.whitelist_pair_count,
            "runtime_mutations": self.runtime_mutations,
            "config_mutations": self.config_mutations,
            "live_trading_mutations": self.live_trading_mutations,
            "docker_mutations": self.docker_mutations,
            "strategy_mutations": self.strategy_mutations,
            "controller_state": self.controller_state,
            "measurement_status": self.measurement_status,
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class FleetMeasurementPoint:
    """Fleet-level aggregate measurement for a single cycle."""

    cycle_id: str
    cycle_timestamp: str
    fleet_verdict: str
    total_bots: int
    ping_ok_count: int
    ping_failed_count: int
    shadow_proposal_count: int
    no_proposal_count: int
    mean_signal_depth: float
    mean_profit_all_percent: float | None
    total_open_trades: int | None
    runtime_mutations: int
    config_mutations: int
    live_trading_mutations: int
    docker_mutations: int
    strategy_mutations: int
    controller_state: str
    measurement_status: str
    source_artifact: str

    def to_json_safe(self) -> JsonObject:
        return {
            "cycle_id": self.cycle_id,
            "cycle_timestamp": self.cycle_timestamp,
            "fleet_verdict": self.fleet_verdict,
            "total_bots": self.total_bots,
            "ping_ok_count": self.ping_ok_count,
            "ping_failed_count": self.ping_failed_count,
            "shadow_proposal_count": self.shadow_proposal_count,
            "no_proposal_count": self.no_proposal_count,
            "mean_signal_depth": round(self.mean_signal_depth, 4),
            "mean_profit_all_percent": (
                round(self.mean_profit_all_percent, 4)
                if self.mean_profit_all_percent is not None
                else None
            ),
            "total_open_trades": self.total_open_trades,
            "runtime_mutations": self.runtime_mutations,
            "config_mutations": self.config_mutations,
            "live_trading_mutations": self.live_trading_mutations,
            "docker_mutations": self.docker_mutations,
            "strategy_mutations": self.strategy_mutations,
            "controller_state": self.controller_state,
            "measurement_status": self.measurement_status,
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class ProposalTrackingRecord:
    """Tracks a single proposal decision across cycles."""

    proposal_id: str  # candidate_sha256
    bot_id: str
    hypothesis: str
    first_cycle_id: str
    first_cycle_timestamp: str
    latest_cycle_id: str
    latest_cycle_timestamp: str
    decision_count: int  # How many cycles this proposal appeared
    last_decision_type: str
    last_approval_status: str
    applied: bool
    attribution_status: str  # AttributionStatus value
    attribution_cycles: tuple[str, ...]

    def to_json_safe(self) -> JsonObject:
        return {
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "hypothesis": self.hypothesis,
            "first_cycle_id": self.first_cycle_id,
            "first_cycle_timestamp": self.first_cycle_timestamp,
            "latest_cycle_id": self.latest_cycle_id,
            "latest_cycle_timestamp": self.latest_cycle_timestamp,
            "decision_count": self.decision_count,
            "last_decision_type": self.last_decision_type,
            "last_approval_status": self.last_approval_status,
            "applied": self.applied,
            "attribution_status": self.attribution_status,
            "attribution_cycles": list(self.attribution_cycles),
        }


@dataclass(frozen=True)
class AttributionWindow:
    """Describes a pre/post attribution window for a proposal."""

    proposal_id: str
    bot_id: str
    hypothesis: str
    pre_cycle_count: int
    post_cycle_count: int
    pre_mean_signal_depth: float | None
    post_mean_signal_depth: float | None
    pre_mean_profit_pct: float | None
    post_mean_profit_pct: float | None
    pre_trade_count_avg: float | None
    post_trade_count_avg: float | None
    pre_cycles: tuple[str, ...]
    post_cycles: tuple[str, ...]
    attribution_status: str

    def to_json_safe(self) -> JsonObject:
        return {
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "hypothesis": self.hypothesis,
            "pre_cycle_count": self.pre_cycle_count,
            "post_cycle_count": self.post_cycle_count,
            "pre_mean_signal_depth": (
                round(self.pre_mean_signal_depth, 4)
                if self.pre_mean_signal_depth is not None
                else None
            ),
            "post_mean_signal_depth": (
                round(self.post_mean_signal_depth, 4)
                if self.post_mean_signal_depth is not None
                else None
            ),
            "pre_mean_profit_pct": (
                round(self.pre_mean_profit_pct, 4) if self.pre_mean_profit_pct is not None else None
            ),
            "post_mean_profit_pct": (
                round(self.post_mean_profit_pct, 4)
                if self.post_mean_profit_pct is not None
                else None
            ),
            "pre_trade_count_avg": self.pre_trade_count_avg,
            "post_trade_count_avg": self.post_trade_count_avg,
            "pre_cycles": list(self.pre_cycles),
            "post_cycles": list(self.post_cycles),
            "attribution_status": self.attribution_status,
        }


@dataclass(frozen=True)
class MeasurementLedger:
    """Complete measurement ledger for one build run."""

    build_timestamp: str
    cycle_count: int
    bot_count: int
    bot_points: tuple[BotMeasurementPoint, ...]
    fleet_points: tuple[FleetMeasurementPoint, ...]
    proposal_records: tuple[ProposalTrackingRecord, ...]
    attribution_windows: tuple[AttributionWindow, ...]
    source_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class LedgerBuildSummary:
    """Human-readable summary of a ledger build."""

    build_timestamp: str
    total_cycles_scanned: int
    total_bot_points: int
    total_fleet_points: int
    total_proposal_records: int
    total_attribution_windows: int
    measurement_statuses: dict[str, int]
    fleet_verdict_counts: dict[str, int]
    mutations_all_zero: bool
    controller_state: str
    secrets_found: bool
    insufficient_history: bool
