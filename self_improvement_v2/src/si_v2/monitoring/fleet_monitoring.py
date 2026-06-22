"""SI v2 report-only fleet monitoring evaluator.

This module reads existing evidence-like inputs and produces a deterministic
operational monitoring report. It is intentionally pure and advisory-only:
no restarts, no runtime mutation, no config writes, and no live-trading
side effects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_BLOCKED as DYNAMIC_EXIT_GATE_BLOCKED,
)
from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_CANDIDATE as DYNAMIC_EXIT_GATE_CANDIDATE,
)
from si_v2.evaluation.dynamic_exit_evidence import (
    GATE_VERDICT_INCONCLUSIVE as DYNAMIC_EXIT_GATE_INCONCLUSIVE,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_BLOCKED as PROFITABILITY_GATE_BLOCKED,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_CANDIDATE as PROFITABILITY_GATE_CANDIDATE,
)
from si_v2.evaluation.profitability_gate import (
    VERDICT_INCONCLUSIVE as PROFITABILITY_GATE_INCONCLUSIVE,
)

DEFAULT_EXPECTED_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)

DEFAULT_HEARTBEAT_STALE_THRESHOLD_SECONDS: Final[int] = 600
DEFAULT_HEARTBEAT_HARD_STALE_THRESHOLD_SECONDS: Final[int] = 1800
DEFAULT_TELEMETRY_STALE_THRESHOLD_SECONDS: Final[int] = 3600
DEFAULT_TELEMETRY_HARD_STALE_THRESHOLD_SECONDS: Final[int] = 7200


class MonitoringVerdict(StrEnum):
    """Fleet or bot monitoring verdict."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class MonitoringRecommendation(StrEnum):
    """Advisory-only operational recommendation labels."""

    RESTART_COLLECTOR_RECOMMENDED = "restart_collector_recommended"
    PAUSE_PROMOTION_RECOMMENDED = "pause_promotion_recommended"
    MARK_BOT_BLOCKED_RECOMMENDED = "mark_bot_blocked_recommended"
    MANUAL_REVIEW_RECOMMENDED = "manual_review_recommended"
    NO_ACTION_RECOMMENDED = "no_action_recommended"


@dataclass(frozen=True, slots=True)
class BotMonitoringInput:
    """Normalized per-bot monitoring input.

    The evaluator accepts raw dict-like evidence objects or instances of
    this dataclass.
    """

    bot_id: str
    heartbeat_ok: bool | None = None
    heartbeat_age_seconds: int | None = None
    telemetry_age_seconds: int | None = None
    proposal_generation_ok: bool | None = None
    profitability_gate_verdict: str | None = None
    dynamic_exit_evidence_gate_verdict: str | None = None
    error_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BotMonitoringStatus:
    """Per-bot monitoring status produced by the evaluator."""

    bot_id: str
    is_expected_bot: bool
    heartbeat_ok: bool | None
    heartbeat_age_seconds: int | None
    telemetry_fresh: bool | None
    telemetry_age_seconds: int | None
    proposal_generation_ok: bool | None
    profitability_gate_verdict: str
    dynamic_exit_evidence_gate_verdict: str
    error_flags: tuple[str, ...] = ()
    verdict: MonitoringVerdict = MonitoringVerdict.YELLOW
    reasons: tuple[str, ...] = ()
    recommendations: tuple[MonitoringRecommendation, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dictionary representation."""
        return {
            "bot_id": self.bot_id,
            "is_expected_bot": self.is_expected_bot,
            "heartbeat_ok": self.heartbeat_ok,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "telemetry_fresh": self.telemetry_fresh,
            "telemetry_age_seconds": self.telemetry_age_seconds,
            "proposal_generation_ok": self.proposal_generation_ok,
            "profitability_gate_verdict": self.profitability_gate_verdict,
            "dynamic_exit_evidence_gate_verdict": self.dynamic_exit_evidence_gate_verdict,
            "error_flags": list(self.error_flags),
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "recommendations": [recommendation.value for recommendation in self.recommendations],
        }


@dataclass(frozen=True, slots=True)
class FleetMonitoringReport:
    """Fleet-level report-only monitoring evaluation."""

    verdict: MonitoringVerdict
    per_bot_statuses: tuple[BotMonitoringStatus, ...] = ()
    reasons: tuple[str, ...] = ()
    recommendations: tuple[MonitoringRecommendation, ...] = ()
    expected_bot_ids: tuple[str, ...] = DEFAULT_EXPECTED_BOT_IDS
    bot_ids: tuple[str, ...] = ()
    missing_expected_bot_ids: tuple[str, ...] = ()
    unknown_bot_ids: tuple[str, ...] = ()
    bot_count: int = 0
    expected_bot_count: int = 0
    green_bot_count: int = 0
    yellow_bot_count: int = 0
    red_bot_count: int = 0

    def get_bot(self, bot_id: str) -> BotMonitoringStatus:
        """Return the status for a bot_id or raise KeyError."""
        for bot in self.per_bot_statuses:
            if bot.bot_id == bot_id:
                return bot
        raise KeyError(bot_id)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dictionary representation."""
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "recommendations": [recommendation.value for recommendation in self.recommendations],
            "expected_bot_ids": list(self.expected_bot_ids),
            "bot_ids": list(self.bot_ids),
            "missing_expected_bot_ids": list(self.missing_expected_bot_ids),
            "unknown_bot_ids": list(self.unknown_bot_ids),
            "bot_count": self.bot_count,
            "expected_bot_count": self.expected_bot_count,
            "green_bot_count": self.green_bot_count,
            "yellow_bot_count": self.yellow_bot_count,
            "red_bot_count": self.red_bot_count,
            "per_bot_statuses": [bot.to_dict() for bot in self.per_bot_statuses],
        }


def _get_value(source: object, key: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _as_bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _as_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        items: list[str] = []
        for item in value:
            if isinstance(item, str):
                items.append(item)
        return tuple(items)
    return ()


def _normalize_input(source: object) -> BotMonitoringInput:
    bot_id_raw = _get_value(source, "bot_id", "")
    bot_id = bot_id_raw if isinstance(bot_id_raw, str) and bot_id_raw else "<missing>"
    return BotMonitoringInput(
        bot_id=bot_id,
        heartbeat_ok=_as_bool_or_none(_get_value(source, "heartbeat_ok")),
        heartbeat_age_seconds=_as_int_or_none(_get_value(source, "heartbeat_age_seconds")),
        telemetry_age_seconds=_as_int_or_none(_get_value(source, "telemetry_age_seconds")),
        proposal_generation_ok=_as_bool_or_none(_get_value(source, "proposal_generation_ok")),
        profitability_gate_verdict=_as_str_or_none(_get_value(source, "profitability_gate_verdict")),
        dynamic_exit_evidence_gate_verdict=_as_str_or_none(
            _get_value(source, "dynamic_exit_evidence_gate_verdict")
        ),
        error_flags=_as_string_tuple(_get_value(source, "error_flags")),
    )


def _append_unique(
    items: list[MonitoringRecommendation],
    recommendation: MonitoringRecommendation,
) -> None:
    if recommendation not in items:
        items.append(recommendation)


def _classify_bot(
    bot_input: BotMonitoringInput,
    *,
    expected_bot_id: str | None,
    heartbeat_stale_threshold_seconds: int,
    heartbeat_hard_stale_threshold_seconds: int,
    telemetry_stale_threshold_seconds: int,
    telemetry_hard_stale_threshold_seconds: int,
) -> BotMonitoringStatus:
    reasons: list[str] = []
    recommendations: list[MonitoringRecommendation] = []
    verdict = MonitoringVerdict.GREEN

    def mark_yellow(reason: str) -> None:
        nonlocal verdict
        reasons.append(reason)
        if verdict == MonitoringVerdict.GREEN:
            verdict = MonitoringVerdict.YELLOW

    def mark_red(reason: str) -> None:
        nonlocal verdict
        reasons.append(reason)
        verdict = MonitoringVerdict.RED

    is_expected_bot = expected_bot_id is not None
    if not is_expected_bot:
        mark_yellow("unknown_bot")
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    heartbeat_ok = bot_input.heartbeat_ok
    if heartbeat_ok is None:
        mark_yellow("missing_heartbeat")
        _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif heartbeat_ok is False:
        mark_yellow("heartbeat_failed")
        _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    heartbeat_age_seconds = bot_input.heartbeat_age_seconds
    if heartbeat_age_seconds is not None:
        if heartbeat_age_seconds > heartbeat_hard_stale_threshold_seconds:
            mark_red("stale_heartbeat_hard")
            _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
            _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
            _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
        elif heartbeat_age_seconds > heartbeat_stale_threshold_seconds:
            mark_yellow("stale_heartbeat")
            _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
            _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    telemetry_age_seconds = bot_input.telemetry_age_seconds
    telemetry_fresh: bool | None
    if telemetry_age_seconds is None:
        telemetry_fresh = None
        mark_yellow("missing_telemetry_freshness")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif telemetry_age_seconds > telemetry_hard_stale_threshold_seconds:
        telemetry_fresh = False
        mark_red("stale_telemetry_hard")
        _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif telemetry_age_seconds > telemetry_stale_threshold_seconds:
        telemetry_fresh = False
        mark_yellow("stale_telemetry")
        _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    else:
        telemetry_fresh = True

    proposal_generation_ok = bot_input.proposal_generation_ok
    if proposal_generation_ok is None:
        mark_yellow("missing_proposal_generation_status")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif proposal_generation_ok is False:
        mark_yellow("proposal_generation_failed")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    profitability_gate_verdict = (
        bot_input.profitability_gate_verdict or "missing_profitability_gate_verdict"
    )
    if bot_input.profitability_gate_verdict is None:
        mark_yellow("missing_profitability_gate_verdict")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif profitability_gate_verdict == PROFITABILITY_GATE_BLOCKED:
        mark_red("profitability_gate_blocked")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MARK_BOT_BLOCKED_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif profitability_gate_verdict == PROFITABILITY_GATE_INCONCLUSIVE:
        mark_yellow("profitability_gate_inconclusive")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif profitability_gate_verdict != PROFITABILITY_GATE_CANDIDATE:
        mark_yellow("profitability_gate_unknown")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    dynamic_exit_gate_verdict = (
        bot_input.dynamic_exit_evidence_gate_verdict or "missing_dynamic_exit_evidence_gate"
    )
    if bot_input.dynamic_exit_evidence_gate_verdict is None:
        mark_yellow("missing_dynamic_exit_evidence_gate")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif dynamic_exit_gate_verdict == DYNAMIC_EXIT_GATE_BLOCKED:
        mark_red("dynamic_exit_evidence_gate_blocked")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MARK_BOT_BLOCKED_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif dynamic_exit_gate_verdict == DYNAMIC_EXIT_GATE_INCONCLUSIVE:
        mark_yellow("dynamic_exit_evidence_gate_inconclusive")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
    elif dynamic_exit_gate_verdict != DYNAMIC_EXIT_GATE_CANDIDATE:
        mark_yellow("dynamic_exit_evidence_gate_unknown")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)

    if bot_input.error_flags:
        mark_yellow(f"error_flags_present:{','.join(bot_input.error_flags)}")
        _append_unique(recommendations, MonitoringRecommendation.PAUSE_PROMOTION_RECOMMENDED)
        _append_unique(recommendations, MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED)
        if len(bot_input.error_flags) > 1:
            _append_unique(recommendations, MonitoringRecommendation.RESTART_COLLECTOR_RECOMMENDED)

    if verdict == MonitoringVerdict.GREEN:
        recommendations = [MonitoringRecommendation.NO_ACTION_RECOMMENDED]
    elif not recommendations:
        recommendations = [MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED]

    return BotMonitoringStatus(
        bot_id=bot_input.bot_id,
        is_expected_bot=is_expected_bot,
        heartbeat_ok=heartbeat_ok,
        heartbeat_age_seconds=heartbeat_age_seconds,
        telemetry_fresh=telemetry_fresh,
        telemetry_age_seconds=telemetry_age_seconds,
        proposal_generation_ok=proposal_generation_ok,
        profitability_gate_verdict=profitability_gate_verdict,
        dynamic_exit_evidence_gate_verdict=dynamic_exit_gate_verdict,
        error_flags=bot_input.error_flags,
        verdict=verdict,
        reasons=tuple(reasons),
        recommendations=tuple(recommendations),
    )


# Keep the helper name typo-free in the source; pyright/mypy should catch it.


def evaluate_bot_monitoring(
    bot_input: object,
    *,
    expected_bot_id: str | None = None,
    stale_threshold_seconds: int | None = None,
    hard_stale_threshold_seconds: int | None = None,
    heartbeat_stale_threshold_seconds: int = DEFAULT_HEARTBEAT_STALE_THRESHOLD_SECONDS,
    heartbeat_hard_stale_threshold_seconds: int = DEFAULT_HEARTBEAT_HARD_STALE_THRESHOLD_SECONDS,
    telemetry_stale_threshold_seconds: int = DEFAULT_TELEMETRY_STALE_THRESHOLD_SECONDS,
    telemetry_hard_stale_threshold_seconds: int = DEFAULT_TELEMETRY_HARD_STALE_THRESHOLD_SECONDS,
) -> BotMonitoringStatus:
    """Evaluate a single bot's monitoring evidence."""
    normalized = _normalize_input(bot_input)
    expected = expected_bot_id if expected_bot_id is not None else normalized.bot_id
    telemetry_stale_threshold_seconds = (
        stale_threshold_seconds
        if stale_threshold_seconds is not None
        else telemetry_stale_threshold_seconds
    )
    telemetry_hard_stale_threshold_seconds = (
        hard_stale_threshold_seconds
        if hard_stale_threshold_seconds is not None
        else telemetry_hard_stale_threshold_seconds
    )
    return _classify_bot(
        normalized,
        expected_bot_id=expected,
        heartbeat_stale_threshold_seconds=heartbeat_stale_threshold_seconds,
        heartbeat_hard_stale_threshold_seconds=heartbeat_hard_stale_threshold_seconds,
        telemetry_stale_threshold_seconds=telemetry_stale_threshold_seconds,
        telemetry_hard_stale_threshold_seconds=telemetry_hard_stale_threshold_seconds,
    )


def evaluate_fleet_monitoring(
    bot_inputs: Sequence[object],
    *,
    expected_bot_ids: Sequence[str] = DEFAULT_EXPECTED_BOT_IDS,
    stale_threshold_seconds: int | None = None,
    hard_stale_threshold_seconds: int | None = None,
    heartbeat_stale_threshold_seconds: int = DEFAULT_HEARTBEAT_STALE_THRESHOLD_SECONDS,
    heartbeat_hard_stale_threshold_seconds: int = DEFAULT_HEARTBEAT_HARD_STALE_THRESHOLD_SECONDS,
    telemetry_stale_threshold_seconds: int = DEFAULT_TELEMETRY_STALE_THRESHOLD_SECONDS,
    telemetry_hard_stale_threshold_seconds: int = DEFAULT_TELEMETRY_HARD_STALE_THRESHOLD_SECONDS,
) -> FleetMonitoringReport:
    """Evaluate fleet monitoring inputs and return a report-only verdict."""
    telemetry_stale_threshold_seconds = (
        stale_threshold_seconds
        if stale_threshold_seconds is not None
        else telemetry_stale_threshold_seconds
    )
    telemetry_hard_stale_threshold_seconds = (
        hard_stale_threshold_seconds
        if hard_stale_threshold_seconds is not None
        else telemetry_hard_stale_threshold_seconds
    )
    normalized_inputs: list[BotMonitoringInput] = []
    seen_bot_ids: set[str] = set()
    for item in bot_inputs:
        normalized = _normalize_input(item)
        if normalized.bot_id in seen_bot_ids:
            continue
        normalized_inputs.append(normalized)
        seen_bot_ids.add(normalized.bot_id)

    by_bot_id = {item.bot_id: item for item in normalized_inputs}
    per_bot_statuses: list[BotMonitoringStatus] = []
    missing_expected_bot_ids: list[str] = []
    unknown_bot_ids: list[str] = []

    expected_set = set(expected_bot_ids)
    for expected_bot_id in expected_bot_ids:
        bot_input = by_bot_id.get(expected_bot_id)
        if bot_input is None:
            missing_expected_bot_ids.append(expected_bot_id)
            placeholder = BotMonitoringInput(bot_id=expected_bot_id)
            bot_status = _classify_bot(
                placeholder,
                expected_bot_id=expected_bot_id,
                heartbeat_stale_threshold_seconds=heartbeat_stale_threshold_seconds,
                heartbeat_hard_stale_threshold_seconds=heartbeat_hard_stale_threshold_seconds,
                telemetry_stale_threshold_seconds=telemetry_stale_threshold_seconds,
                telemetry_hard_stale_threshold_seconds=telemetry_hard_stale_threshold_seconds,
            )
        else:
            bot_status = _classify_bot(
                bot_input,
                expected_bot_id=expected_bot_id,
                heartbeat_stale_threshold_seconds=heartbeat_stale_threshold_seconds,
                heartbeat_hard_stale_threshold_seconds=heartbeat_hard_stale_threshold_seconds,
                telemetry_stale_threshold_seconds=telemetry_stale_threshold_seconds,
                telemetry_hard_stale_threshold_seconds=telemetry_hard_stale_threshold_seconds,
            )
        per_bot_statuses.append(bot_status)

    for normalized in normalized_inputs:
        if normalized.bot_id not in expected_set:
            unknown_bot_ids.append(normalized.bot_id)
            per_bot_statuses.append(
                _classify_bot(
                    normalized,
                    expected_bot_id=None,
                    heartbeat_stale_threshold_seconds=heartbeat_stale_threshold_seconds,
                    heartbeat_hard_stale_threshold_seconds=heartbeat_hard_stale_threshold_seconds,
                    telemetry_stale_threshold_seconds=telemetry_stale_threshold_seconds,
                    telemetry_hard_stale_threshold_seconds=telemetry_hard_stale_threshold_seconds,
                )
            )

    bot_ids = tuple(bot.bot_id for bot in per_bot_statuses)
    green_bot_count = sum(1 for bot in per_bot_statuses if bot.verdict == MonitoringVerdict.GREEN)
    yellow_bot_count = sum(1 for bot in per_bot_statuses if bot.verdict == MonitoringVerdict.YELLOW)
    red_bot_count = sum(1 for bot in per_bot_statuses if bot.verdict == MonitoringVerdict.RED)
    non_green_bot_count = yellow_bot_count + red_bot_count

    if red_bot_count > 0 or non_green_bot_count >= 2:
        fleet_verdict = MonitoringVerdict.RED
    elif non_green_bot_count == 1:
        fleet_verdict = MonitoringVerdict.YELLOW
    else:
        fleet_verdict = MonitoringVerdict.GREEN

    reasons: list[str] = []
    for bot in per_bot_statuses:
        for reason in bot.reasons:
            if reason not in reasons:
                reasons.append(f"{bot.bot_id}:{reason}")

    if fleet_verdict == MonitoringVerdict.GREEN:
        recommendations = [MonitoringRecommendation.NO_ACTION_RECOMMENDED]
    else:
        recommendation_order: list[MonitoringRecommendation] = []
        for bot in per_bot_statuses:
            for recommendation in bot.recommendations:
                if recommendation == MonitoringRecommendation.NO_ACTION_RECOMMENDED:
                    continue
                _append_unique(recommendation_order, recommendation)
        recommendations = recommendation_order or [MonitoringRecommendation.MANUAL_REVIEW_RECOMMENDED]

    return FleetMonitoringReport(
        verdict=fleet_verdict,
        per_bot_statuses=tuple(per_bot_statuses),
        reasons=tuple(reasons),
        recommendations=tuple(recommendations),
        expected_bot_ids=tuple(expected_bot_ids),
        bot_ids=bot_ids,
        missing_expected_bot_ids=tuple(missing_expected_bot_ids),
        unknown_bot_ids=tuple(unknown_bot_ids),
        bot_count=len(per_bot_statuses),
        expected_bot_count=len(expected_bot_ids),
        green_bot_count=green_bot_count,
        yellow_bot_count=yellow_bot_count,
        red_bot_count=red_bot_count,
    )


__all__ = [
    "DEFAULT_EXPECTED_BOT_IDS",
    "BotMonitoringInput",
    "BotMonitoringStatus",
    "FleetMonitoringReport",
    "MonitoringRecommendation",
    "MonitoringVerdict",
    "evaluate_bot_monitoring",
    "evaluate_fleet_monitoring",
]
