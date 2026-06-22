r"""SI v2 Dynamic Exit Evidence — read-only risk enrichment for gate evaluation.

This module bridges the Dynamic Exit Engine (#300) and Strategy Codex (#301)
into the SI v2 evidence/gate pipeline.

It provides:
- ``DynamicExitEvidence`` — per-bot structured exit evidence block
- ``ExitEvidenceGateResult`` — fleet-level gate verdict
- ``enrich_bot_exit_evidence()`` — compute exit evidence for one bot
- ``enrich_fleet_exit_evidence()`` — compute for all four expected bots
- ``evaluate_exit_evidence_gate()`` — gate evaluation with promotion rules

Design:
  - Pure read-only enrichment — no exchange I/O, no config mutation.
  - Accepts bot metrics dicts with optional indicator fields.
  - Consults the Strategy Codex for strategy ↔ bot mapping.
  - Missing strategy mapping → ``strategy_mapping_missing`` (soft block).
  - Missing indicator data → ``insufficient_indicator_data`` (hard block).
  - Invalid exit levels → ``exit_levels_invalid`` (hard block).
  - Low risk/reward ratio → ``risk_reward_below_minimum`` (hard block).
  - Valid exit evidence enriches the bot's evidence block without side effects.

Safety invariants:
  - Never activates capital execution. Dry-run mode remains required.
  - Never writes Freqtrade strategy files.
  - Never mutates config, Docker, Compose, or cron state.
  - Never auto-approves or auto-promotes.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from si_v2.risk.dynamic_exits import (
    DIRECTION_LONG,
    MODE_ATR,
    STATUS_BLOCKED,
    STATUS_VALID,
    DynamicExitResult,
    calculate_dynamic_exit,
)

# -- Strategy Codex types (avoid circular import) ---------------------------
# Imported lazily in enrich_bot_exit_evidence to keep the module importable
# even if the codex module isn't on the path.

# ---------------------------------------------------------------------------
# Expected bot IDs — consistent with profitability_gate.py
# ---------------------------------------------------------------------------
DEFAULT_FLEET_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)

# -- Strategy ↔ Bot mappings (explicit registry for Phase 3) ----------------
#
# Maps bot IDs to strategy IDs from the Strategy Codex.
# If a bot is not in this mapping, enrichment will produce
# reason_code="strategy_mapping_missing".
#
# Initial mapping (conservative — all draft strategies):
#   freqtrade-freqforge        → strat_btc_01 (BTC Pullback Bounce)
#   freqtrade-regime-hybrid    → strat_eth_01 (ETH Momentum Break)
#   freqtrade-freqforge-canary → strat_btc_01 (mirrors FreqForge)
#   freqai-rebel               → strat_sol_01 (SOL Volume Spike Reversal)
# ---------------------------------------------------------------------------

DEFAULT_STRATEGY_BOT_MAPPING: Final[dict[str, str]] = {
    "freqtrade-freqforge": "strat_btc_01",
    "freqtrade-regime-hybrid": "strat_eth_01",
    "freqtrade-freqforge-canary": "strat_btc_01",
    "freqai-rebel": "strat_sol_01",
}

# ---------------------------------------------------------------------------
# Reason code constants
# ---------------------------------------------------------------------------
REASON_STRATEGY_MAPPING_MISSING: Final[str] = "strategy_mapping_missing"
REASON_INSUFFICIENT_INDICATOR_DATA: Final[str] = "insufficient_indicator_data"
REASON_EXIT_LEVELS_INVALID: Final[str] = "exit_levels_invalid"
REASON_RISK_REWARD_BELOW_MINIMUM: Final[str] = "risk_reward_below_minimum"
REASON_MISSING_EXIT_EVIDENCE: Final[str] = "missing_exit_evidence"

# ---------------------------------------------------------------------------
# Default gate thresholds
# ---------------------------------------------------------------------------


def _decimal_from(value: object) -> Decimal | None:
    """Coerce a value to Decimal, returning None on failure."""
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            return Decimal(value)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DynamicExitEvidence:
    """Per-bot dynamic exit evidence enrichment.

    Mirrors the DynamicExitResult.to_dict() shape but adds bot-level
    metadata (bot_id, strategy_id) for fleet-level aggregation.
    """

    bot_id: str
    strategy_id: str | None
    status: str  # "valid" | "blocked"
    mode: str
    direction: str
    stop_loss: str | None
    take_profit: str | None
    risk_distance: str | None
    reward_distance: str | None
    risk_reward_ratio: str | None
    reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_exit_result(
        cls,
        *,
        bot_id: str,
        strategy_id: str | None,
        result: DynamicExitResult,
    ) -> DynamicExitEvidence:
        """Build from a DynamicExitResult.

        Uses the result's to_dict() to ensure Decimal stringification
        is consistent with the exit engine.
        """
        d = result.to_dict()
        return cls(
            bot_id=bot_id,
            strategy_id=strategy_id,
            status=d["status"],  # type: ignore[arg-type]
            mode=d["mode"],  # type: ignore[arg-type]
            direction=d["direction"],  # type: ignore[arg-type]
            stop_loss=d["stop_loss"],  # type: ignore[arg-type]
            take_profit=d["take_profit"],  # type: ignore[arg-type]
            risk_distance=d["risk_distance"],  # type: ignore[arg-type]
            reward_distance=d["reward_distance"],  # type: ignore[arg-type]
            risk_reward_ratio=d["risk_reward_ratio"],  # type: ignore[arg-type]
            reason_codes=tuple(result.reason_codes),
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for embedding in evidence bundles."""
        return {
            "bot_id": self.bot_id,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "mode": self.mode,
            "direction": self.direction,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_distance": self.risk_distance,
            "reward_distance": self.reward_distance,
            "risk_reward_ratio": self.risk_reward_ratio,
            "reason_codes": list(self.reason_codes),
        }

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED


@dataclass(frozen=True, slots=True)
class ExitEvidenceGateResult:
    """Fleet-level exit evidence gate verdict.

    Attributes:
        verdict: One of "candidate", "blocked", "inconclusive".
        per_bot_evidence: Exit evidence for each evaluated bot.
        reasons: Human-readable reasons.
    """

    verdict: str
    per_bot_evidence: tuple[DynamicExitEvidence, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "per_bot_evidence": [e.to_dict() for e in self.per_bot_evidence],
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Verdict constants
# ---------------------------------------------------------------------------
GATE_VERDICT_CANDIDATE: Final[str] = "candidate"
GATE_VERDICT_BLOCKED: Final[str] = "blocked"
GATE_VERDICT_INCONCLUSIVE: Final[str] = "inconclusive"

# ---------------------------------------------------------------------------
# Default exit parameters per strategy (safe defaults)
# ---------------------------------------------------------------------------
_DEFAULT_EXIT_PARAMS: dict[str, object] = {
    "mode": MODE_ATR,
    "direction": DIRECTION_LONG,
    "stop_multiplier": Decimal("1.5"),
    "take_profit_multiplier": Decimal("2.0"),
    "minimum_risk_distance": Decimal("0.001"),
    "minimum_candles": 20,
}


def _build_bot_metrics_row(
    bot_id: str,
    bot_metrics: Mapping[str, object] | None,
    strategy_id: str | None,
) -> dict[str, object] | None:
    """Build a row dict suitable for calculate_dynamic_exit from bot metrics.

    Returns None if the bot lacks a strategy mapping.
    Returns a row with safe defaults if indicator data is unavailable.
    """
    if not strategy_id:
        return None

    metrics = bot_metrics or {}
    row: dict[str, object] = dict(_DEFAULT_EXIT_PARAMS)

    # Entry price: try to get from metrics, fall back to a safe default
    entry_raw = metrics.get("entry_price") or metrics.get("current_price") or metrics.get("last_price")
    if entry_raw is not None:
        try:
            row["entry_price"] = Decimal(str(entry_raw))
        except Exception:
            row["entry_price"] = Decimal("100")
    else:
        row["entry_price"] = Decimal("100")

    # Direction from strategy context
    row["direction"] = str(metrics.get("direction", DIRECTION_LONG))

    # Mode preference
    row["mode"] = str(metrics.get("exit_mode", MODE_ATR))

    # Indicator values (optional — missing = blocked for non-fixed modes)
    for key in ("atr", "bollinger_upper", "bollinger_mid", "bollinger_lower"):
        val = metrics.get(key)
        if val is not None:
            with contextlib.suppress(Exception):
                row[key] = Decimal(str(val))

    # Candle count
    candle_count = metrics.get("candle_count", 50)
    if isinstance(candle_count, (int, float)):
        row["candle_count"] = int(candle_count)

    # Multipliers
    for key in ("stop_multiplier", "take_profit_multiplier", "minimum_risk_distance"):
        val = metrics.get(key)
        if val is not None:
            with contextlib.suppress(Exception):
                row[key] = Decimal(str(val))

    # Maximum stop distance (optional)
    msd = metrics.get("maximum_stop_distance")
    if msd is not None:
        with contextlib.suppress(Exception):
            row["maximum_stop_distance"] = Decimal(str(msd))

    return row


# ---------------------------------------------------------------------------
# Enrichment functions
# ---------------------------------------------------------------------------


def enrich_bot_exit_evidence(
    bot_id: str,
    *,
    bot_metrics: Mapping[str, object] | None = None,
    strategy_id: str | None = None,
    strategy_bot_mapping: Mapping[str, str] | None = None,
) -> DynamicExitEvidence:
    """Compute dynamic exit evidence for a single bot.

    Args:
        bot_id: Bot identifier (e.g. "freqtrade-freqforge").
        bot_metrics: Optional dict of bot-specific metrics/indicators.
        strategy_id: Explicit strategy ID for this bot. If None, consults
            strategy_bot_mapping.
        strategy_bot_mapping: Optional bot_id → strategy_id mapping. Used
            as fallback when strategy_id is None.

    Returns:
        DynamicExitEvidence with status, levels, and reason codes.

    The function is pure: no I/O, no side effects, no config mutation.
    """
    # Resolve strategy
    resolved_strategy: str | None = strategy_id
    if resolved_strategy is None and strategy_bot_mapping:
        resolved_strategy = strategy_bot_mapping.get(bot_id)

    if resolved_strategy is None:
        return DynamicExitEvidence(
            bot_id=bot_id,
            strategy_id=None,
            status=STATUS_BLOCKED,
            mode="fixed",
            direction=DIRECTION_LONG,
            stop_loss=None,
            take_profit=None,
            risk_distance=None,
            reward_distance=None,
            risk_reward_ratio=None,
            reason_codes=(REASON_STRATEGY_MAPPING_MISSING,),
        )

    # Build row for calculate_dynamic_exit
    row = _build_bot_metrics_row(bot_id, bot_metrics, resolved_strategy)
    if row is None:
        return DynamicExitEvidence(
            bot_id=bot_id,
            strategy_id=resolved_strategy,
            status=STATUS_BLOCKED,
            mode="fixed",
            direction=DIRECTION_LONG,
            stop_loss=None,
            take_profit=None,
            risk_distance=None,
            reward_distance=None,
            risk_reward_ratio=None,
            reason_codes=(REASON_STRATEGY_MAPPING_MISSING,),
        )

    # Compute exit levels
    result = calculate_dynamic_exit(
        entry_price=row["entry_price"],
        direction=row["direction"],
        mode=row["mode"],
        atr=row.get("atr"),
        bollinger_upper=row.get("bollinger_upper"),
        bollinger_mid=row.get("bollinger_mid"),
        bollinger_lower=row.get("bollinger_lower"),
        stop_multiplier=row["stop_multiplier"],
        take_profit_multiplier=row["take_profit_multiplier"],
        minimum_risk_distance=row["minimum_risk_distance"],
        maximum_stop_distance=row.get("maximum_stop_distance"),
        candle_count=row["candle_count"],
        minimum_candles=row["minimum_candles"],
    )

    return DynamicExitEvidence.from_exit_result(
        bot_id=bot_id,
        strategy_id=resolved_strategy,
        result=result,
    )


def enrich_fleet_exit_evidence(
    *,
    bot_metrics_map: Mapping[str, Mapping[str, object] | None] | None = None,
    strategy_bot_mapping: Mapping[str, str] | None = None,
    fleet_bot_ids: tuple[str, ...] = DEFAULT_FLEET_BOT_IDS,
) -> tuple[DynamicExitEvidence, ...]:
    """Compute dynamic exit evidence for all expected bots.

    Args:
        bot_metrics_map: Optional mapping of bot_id → metrics dict.
        strategy_bot_mapping: Optional bot_id → strategy_id mapping.
            Defaults to DEFAULT_STRATEGY_BOT_MAPPING.
        fleet_bot_ids: Expected bot IDs to evaluate.

    Returns:
        Tuple of DynamicExitEvidence, one per bot.
    """
    mapping = strategy_bot_mapping if strategy_bot_mapping is not None else DEFAULT_STRATEGY_BOT_MAPPING
    metrics_map = bot_metrics_map or {}

    results: list[DynamicExitEvidence] = []
    for bot_id in fleet_bot_ids:
        evidence = enrich_bot_exit_evidence(
            bot_id=bot_id,
            bot_metrics=metrics_map.get(bot_id),
            strategy_bot_mapping=mapping,
        )
        results.append(evidence)

    return tuple(results)


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def evaluate_exit_evidence_gate(
    per_bot_evidence: Sequence[DynamicExitEvidence],
    *,
    min_risk_reward_ratio: Decimal | None = None,
) -> ExitEvidenceGateResult:
    """Evaluate whether fleet exit evidence supports promotion.

    Gate rules (deterministic):
      1. If ANY bot has status=blocked with a hard reason (not just
         strategy_mapping_missing), the fleet verdict is BLOCKED.
      2. If ALL bots have strategy_mapping_missing or are missing exit
         evidence entirely, the verdict is INCONCLUSIVE.
      3. If any bot has valid exit evidence but risk_reward_ratio is below
         the configured minimum, the fleet verdict is BLOCKED.
      4. If at least one bot has valid exit evidence, all strategy-mapped
         bots produce valid exits, and risk/reward is acceptable, the
         verdict is CANDIDATE.
      5. Mixed evidence (some valid, some soft-blocked via
         strategy_mapping_missing) → INCONCLUSIVE.

    Args:
        per_bot_evidence: Exit evidence for each bot.
        min_risk_reward_ratio: Minimum acceptable risk/reward ratio.
            Defaults to Decimal("1.0").

    Returns:
        ExitEvidenceGateResult with verdict and reasons.
    """
    if min_risk_reward_ratio is None:
        min_risk_reward_ratio = Decimal("1.0")

    reasons: list[str] = []
    hard_blocked: list[str] = []
    soft_blocked: list[str] = []
    valid_bots: list[str] = []
    rr_failures: list[str] = []

    for e in per_bot_evidence:
        if e.status == STATUS_VALID:
            # Check risk/reward ratio
            rr = _decimal_from(e.risk_reward_ratio)
            if rr is not None and rr < min_risk_reward_ratio:
                rr_failures.append(
                    f"{e.bot_id}:rr={e.risk_reward_ratio} < {min_risk_reward_ratio}"
                )
                continue
            valid_bots.append(e.bot_id)
        elif e.is_blocked:
            # Classify: hard block vs soft block
            is_strategy_missing_only = (
                len(e.reason_codes) == 1
                and REASON_STRATEGY_MAPPING_MISSING in e.reason_codes
            )
            if is_strategy_missing_only:
                soft_blocked.append(e.bot_id)
            else:
                hard_blocked.append(e.bot_id)

    # Rule 1: A hard block means → BLOCKED
    if hard_blocked:
        reasons.append(f"hard_blocked_bots: {', '.join(hard_blocked)}")
        return ExitEvidenceGateResult(
            verdict=GATE_VERDICT_BLOCKED,
            per_bot_evidence=tuple(per_bot_evidence),
            reasons=tuple(reasons),
        )

    # Risk/reward failures
    if rr_failures:
        reasons.append(f"risk_reward_failures: {'; '.join(rr_failures)}")
        return ExitEvidenceGateResult(
            verdict=GATE_VERDICT_BLOCKED,
            per_bot_evidence=tuple(per_bot_evidence),
            reasons=tuple(reasons),
        )

    # Rule 2: All soft blocked or none found → INCONCLUSIVE
    if not valid_bots:
        reasons.append(
            f"no_valid_exit_evidence — soft_blocked: {', '.join(soft_blocked)}"
            if soft_blocked
            else "no_exit_evidence_computed"
        )
        return ExitEvidenceGateResult(
            verdict=GATE_VERDICT_INCONCLUSIVE,
            per_bot_evidence=tuple(per_bot_evidence),
            reasons=tuple(reasons),
        )

    # Rule 5: Mixed — some valid, some soft-blocked → INCONCLUSIVE
    if soft_blocked:
        reasons.append(
            f"mixed_evidence: valid={valid_bots}, soft_blocked={soft_blocked}"
        )
        return ExitEvidenceGateResult(
            verdict=GATE_VERDICT_INCONCLUSIVE,
            per_bot_evidence=tuple(per_bot_evidence),
            reasons=tuple(reasons),
        )

    # Rule 4: All valid → CANDIDATE
    return ExitEvidenceGateResult(
        verdict=GATE_VERDICT_CANDIDATE,
        per_bot_evidence=tuple(per_bot_evidence),
        reasons=(),
    )
