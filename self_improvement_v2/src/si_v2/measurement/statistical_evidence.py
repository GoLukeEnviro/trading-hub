"""SI-v2 Phase 8 — Statistical Evidence Framework.

Read-only statistical evidence layer for autonomous dry-run measurement
decisions. Provides sample adequacy by evidence class, bootstrap confidence
intervals, effect size, winrate, profit factor, and decision recommendations.

This module has NO dependencies beyond the Python standard library.
It does NOT execute runtime actions, apply overlays, or enable schedulers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVIDENCE_CLASS_A: str = "A"
EVIDENCE_CLASS_B: str = "B"
EVIDENCE_CLASS_C: str = "C"

DEFAULT_MIN_SAMPLES: dict[str, int] = {
    "A": 5,
    "B": 15,
    "C": 30,
}

DEFAULT_BOOTSTRAP_ITERATIONS: int = 1000
DEFAULT_CONFIDENCE_LEVEL: float = 0.90
DEFAULT_RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeSample:
    """A single closed trade sample.

    All fields except trade_id, bot_id, and close_timestamp_utc are
    optional to allow partial data from different evidence sources,
    but profit_abs and profit_ratio are required for statistical
    calculations.
    """

    trade_id: str
    bot_id: str
    close_timestamp_utc: str
    profit_abs: float
    profit_ratio: float
    duration_minutes: float | None = None
    pair: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "bot_id": self.bot_id,
            "close_timestamp_utc": self.close_timestamp_utc,
            "profit_abs": self.profit_abs,
            "profit_ratio": self.profit_ratio,
            "duration_minutes": self.duration_minutes,
            "pair": self.pair,
        }


@dataclass(frozen=True)
class ArmTradeEvidence:
    """Trade evidence for one arm (canary or control)."""

    bot_id: str
    trades: tuple[TradeSample, ...]


@dataclass(frozen=True)
class StatisticalEvidenceInput:
    """All inputs for the statistical evidence evaluator."""

    change_id: str
    candidate_id: str
    canary: ArmTradeEvidence
    control: ArmTradeEvidence
    evidence_class: Literal["A", "B", "C"] = "A"
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL
    random_seed: int = DEFAULT_RANDOM_SEED

    @property
    def min_samples(self) -> int:
        """Minimum required samples per arm for this evidence class."""
        return DEFAULT_MIN_SAMPLES.get(self.evidence_class, 5)


@dataclass(frozen=True)
class StatisticalEvidenceResult:
    """Structured result from the statistical evidence evaluator."""

    status: Literal[
        "STAT_READY",
        "STAT_INSUFFICIENT",
        "STAT_BLOCKED",
    ]
    recommendation: Literal[
        "STAT_KEEP",
        "STAT_EXTEND",
        "STAT_ROLLBACK",
        "STAT_INSUFFICIENT",
        "STAT_BLOCKED",
    ]
    change_id: str
    candidate_id: str
    evidence_class: str
    canary_n: int
    control_n: int
    canary_mean_profit: float
    control_mean_profit: float
    mean_profit_diff: float
    bootstrap_ci_low: float
    bootstrap_ci_high: float
    effect_size: float
    canary_winrate: float
    control_winrate: float
    canary_profit_factor: float | None
    control_profit_factor: float | None
    blocked_reasons: tuple[str, ...]
    evidence_grade: Literal[
        "STRONG", "MODERATE", "WEAK", "INSUFFICIENT", "BLOCKED"
    ]
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "statistical_evidence_result",
            "status": self.status,
            "recommendation": self.recommendation,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "evidence_class": self.evidence_class,
            "canary_n": self.canary_n,
            "control_n": self.control_n,
            "canary_mean_profit": round(self.canary_mean_profit, 6),
            "control_mean_profit": round(self.control_mean_profit, 6),
            "mean_profit_diff": round(self.mean_profit_diff, 6),
            "bootstrap_ci_low": round(self.bootstrap_ci_low, 6),
            "bootstrap_ci_high": round(self.bootstrap_ci_high, 6),
            "effect_size": round(self.effect_size, 6),
            "canary_winrate": round(self.canary_winrate, 4),
            "control_winrate": round(self.control_winrate, 4),
            "canary_profit_factor": (
                round(self.canary_profit_factor, 6)
                if self.canary_profit_factor is not None
                else None
            ),
            "control_profit_factor": (
                round(self.control_profit_factor, 6)
                if self.control_profit_factor is not None
                else None
            ),
            "blocked_reasons": list(self.blocked_reasons),
            "evidence_grade": self.evidence_grade,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Profit factor helper
# ---------------------------------------------------------------------------


def calculate_profit_factor(samples: tuple[TradeSample, ...]) -> float | None:
    """Calculate profit factor = gross_profit / abs(gross_loss).

    Rules:
    - If no trades: returns None.
    - If gross_profit > 0 and gross_loss == 0: returns None
      (undefined — no losing trades; profit factor approaches infinity).
    - If gross_profit == 0 and gross_loss > 0: returns 0.0.
    - If both zero: returns None (no real data).
    - No division by zero.
    """
    if not samples:
        return None

    gross_profit = sum(t.profit_abs for t in samples if t.profit_abs > 0)
    gross_loss = abs(sum(t.profit_abs for t in samples if t.profit_abs < 0))

    if gross_profit > 0 and gross_loss == 0:
        return None  # undefined (infinite edge)
    if gross_profit == 0 and gross_loss > 0:
        return 0.0
    if gross_profit == 0 and gross_loss == 0:
        return None

    return gross_profit / gross_loss


# ---------------------------------------------------------------------------
# Bootstrap confidence interval (stdlib-only)
# ---------------------------------------------------------------------------


def bootstrap_mean_diff_ci(
    canary_values: tuple[float, ...],
    control_values: tuple[float, ...],
    *,
    iterations: int,
    confidence_level: float,
    random_seed: int,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for the difference of means.

    Args:
        canary_values: Profit values from canary arm.
        control_values: Profit values from control arm.
        iterations: Number of bootstrap resamples (minimum 100).
        confidence_level: Desired confidence level (0.5 to 0.99).
        random_seed: Seed for deterministic bootstrap resampling.

    Returns:
        (ci_low, ci_high) — lower and upper bounds of the confidence
        interval for (canary_mean - control_mean).

    Uses only the Python standard library (random, statistics).
    """
    if not canary_values or not control_values:
        return (0.0, 0.0)

    rng = random.Random(random_seed)
    n_canary = len(canary_values)
    n_control = len(control_values)

    diffs: list[float] = []
    for _ in range(iterations):
        boot_canary = mean(rng.choices(canary_values, k=n_canary))
        boot_control = mean(rng.choices(control_values, k=n_control))
        diffs.append(boot_canary - boot_control)

    diffs.sort()
    tail = (1.0 - confidence_level) / 2.0
    low_idx = max(0, int(tail * iterations))
    high_idx = min(iterations - 1, int((1.0 - tail) * iterations))
    return (diffs[low_idx], diffs[high_idx])


# ---------------------------------------------------------------------------
# Effect size helper
# ---------------------------------------------------------------------------


def _compute_effect_size(
    canary_values: tuple[float, ...],
    control_values: tuple[float, ...],
) -> float:
    """Compute a simple effect size: (mean_canary - mean_control) / pooled_std.

    Pooled std uses the two-sample formula:
        pooled_std = sqrt(((n1-1)*s1^2 + (n2-1)*s2^2) / (n1 + n2 - 2))

    Returns 0.0 if pooled_std is zero or nan.
    """
    if not canary_values or not control_values:
        return 0.0

    n1 = len(canary_values)
    n2 = len(control_values)
    m1 = mean(canary_values)
    m2 = mean(control_values)

    # Guard: single-sample arms have no valid std
    try:
        s1 = stdev(canary_values) if n1 > 1 else 0.0
        s2 = stdev(control_values) if n2 > 1 else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0

    pooled_var = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / (n1 + n2 - 2)
    pooled_std = math.sqrt(pooled_var) if pooled_var > 0 else 0.0

    if pooled_std == 0.0 or math.isnan(pooled_std):
        return 0.0

    return (m1 - m2) / pooled_std


# ---------------------------------------------------------------------------
# Winrate helper
# ---------------------------------------------------------------------------


def _compute_winrate(samples: tuple[TradeSample, ...]) -> float:
    """Compute winrate = number of profitable trades / total trades.

    Returns 0.0 if no trades.
    """
    if not samples:
        return 0.0
    wins = sum(1 for t in samples if t.profit_abs > 0)
    return wins / len(samples)


# ---------------------------------------------------------------------------
# Evidence grade
# ---------------------------------------------------------------------------


def _grade_evidence(
    canary_n: int,
    control_n: int,
    mean_diff: float,
    ci_low: float,
    ci_high: float,
    effect_size: float,
    evidence_class: str,
) -> tuple[
    Literal["STRONG", "MODERATE", "WEAK", "INSUFFICIENT"],
    tuple[str, ...],
]:
    """Determine the evidence grade from statistical results.

    Returns (grade, reasons).
    """
    reasons: list[str] = []

    # Sample size check against class minimum
    class_min = DEFAULT_MIN_SAMPLES.get(evidence_class, 5)
    if canary_n < class_min or control_n < class_min:
        return "INSUFFICIENT", (
            f"sample_too_small: canary_n={canary_n}, "
            f"control_n={control_n}, need >= {class_min} for class {evidence_class}",
        )

    # CI entirely above zero
    if ci_low > 0:
        if effect_size > 0.5:
            reasons.append(f"ci_entirely_positive: [{ci_low:.4f}, {ci_high:.4f}], effect={effect_size:.4f}")
            return "STRONG", tuple(reasons)
        reasons.append(f"ci_positive: [{ci_low:.4f}, {ci_high:.4f}], effect={effect_size:.4f}")
        return "MODERATE", tuple(reasons)

    # CI entirely below zero
    if ci_high < 0:
        reasons.append(f"ci_entirely_negative: [{ci_low:.4f}, {ci_high:.4f}], effect={effect_size:.4f}")
        return "STRONG", tuple(reasons)

    # CI crosses zero
    if ci_low < 0 < ci_high:
        if effect_size > 0.3:
            reasons.append(f"ci_crosses_zero_but_moderate_effect: [{ci_low:.4f}, {ci_high:.4f}], "
                           f"effect={effect_size:.4f}")
            return "MODERATE", tuple(reasons)
        reasons.append(f"ci_crosses_zero: [{ci_low:.4f}, {ci_high:.4f}], effect={effect_size:.4f}")
        return "WEAK", tuple(reasons)

    reasons.append(f"default_weak: ci=[{ci_low:.4f}, {ci_high:.4f}]")
    return "WEAK", tuple(reasons)


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def _compute_recommendation(
    mean_diff: float,
    ci_low: float,
    ci_high: float,
    canary_pf: float | None,
    control_pf: float | None,
    evidence_grade: str,
) -> tuple[
    Literal["STAT_KEEP", "STAT_EXTEND", "STAT_ROLLBACK"],
    tuple[str, ...],
]:
    """Compute the recommendation from statistical evidence.

    Returns (recommendation, reasons).
    """
    reasons: list[str] = []

    # Strong positive evidence
    if ci_low > 0 and mean_diff >= 0:
        reasons.append(
            f"stat_keep: ci=[{ci_low:.4f}, {ci_high:.4f}], "
            f"mean_diff={mean_diff:+.6f}"
        )
        return "STAT_KEEP", tuple(reasons)

    # Strong negative evidence
    if ci_high < 0 and mean_diff < 0:
        reasons.append(
            f"stat_rollback: ci=[{ci_low:.4f}, {ci_high:.4f}], "
            f"mean_diff={mean_diff:+.6f}"
        )
        return "STAT_ROLLBACK", tuple(reasons)

    # CI crosses zero — ambiguous
    pf_worse = (
        canary_pf is not None
        and control_pf is not None
        and canary_pf < control_pf
    )

    if mean_diff >= 0 and not pf_worse:
        # Slightly positive but uncertain
        reasons.append(
            f"stat_extend_or_keep: positive_mean_diff={mean_diff:+.6f} "
            f"but ci_crosses_zero=[{ci_low:.4f}, {ci_high:.4f}]"
        )
        # Return keep when CI leans positive enough
        if ci_low >= -0.001:
            return "STAT_KEEP", tuple(reasons)
        return "STAT_EXTEND", tuple(reasons)

    if mean_diff < 0 and pf_worse:
        reasons.append(
            f"stat_rollback: negative_mean_diff={mean_diff:+.6f} "
            f"with worse_profit_factor"
        )
        return "STAT_ROLLBACK", tuple(reasons)

    # Default — extend
    reasons.append(
        f"stat_extend: ambiguous evidence, "
        f"mean_diff={mean_diff:+.6f}, "
        f"ci=[{ci_low:.4f}, {ci_high:.4f}]"
    )
    return "STAT_EXTEND", tuple(reasons)


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------


def evaluate_statistical_evidence(
    input_: StatisticalEvidenceInput,
) -> StatisticalEvidenceResult:
    """Evaluate statistical evidence from canary vs control trade samples.

    This function is PURE and READ-ONLY. It does not:
    - Execute runtime actions
    - Touch filesystems
    - Call external APIs
    - Mutate state

    Args:
        input_: All inputs for the evaluation.

    Returns:
        ``StatisticalEvidenceResult`` with recommendation and evidence.
    """
    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    if not input_.change_id:
        blocked.append("change_id_required: change_id must not be empty")
    if not input_.candidate_id:
        blocked.append("candidate_id_required: candidate_id must not be empty")
    if not input_.canary.bot_id:
        blocked.append("canary_bot_id_required: canary bot_id must not be empty")
    if not input_.control.bot_id:
        blocked.append("control_bot_id_required: control bot_id must not be empty")

    if input_.bootstrap_iterations < 100:
        blocked.append(
            f"bootstrap_iterations_too_low: {input_.bootstrap_iterations} < 100"
        )
    if not (0.5 <= input_.confidence_level <= 0.99):
        blocked.append(
            f"confidence_level_out_of_range: {input_.confidence_level} "
            f"(must be between 0.5 and 0.99)"
        )

    if input_.evidence_class not in ("A", "B", "C"):
        blocked.append(
            f"invalid_evidence_class: {input_.evidence_class!r} "
            f"(must be A, B, or C)"
        )

    canary_trades = input_.canary.trades
    control_trades = input_.control.trades

    if not canary_trades:
        blocked.append("canary_trades_empty: no canary trade samples provided")
    if not control_trades:
        blocked.append("control_trades_empty: no control trade samples provided")

    # Check for NaN / inf in profit_abs
    for arm_name, arm_trades in [("canary", canary_trades), ("control", control_trades)]:
        for t in arm_trades:
            if math.isnan(t.profit_abs) or math.isinf(t.profit_abs):
                blocked.append(
                    f"{arm_name}_trade_{t.trade_id}: "
                    f"profit_abs is NaN or Inf (value={t.profit_abs})"
                )
            if math.isnan(t.profit_ratio) or math.isinf(t.profit_ratio):
                blocked.append(
                    f"{arm_name}_trade_{t.trade_id}: "
                    f"profit_ratio is NaN or Inf (value={t.profit_ratio})"
                )

    if blocked:
        return StatisticalEvidenceResult(
            status="STAT_BLOCKED",
            recommendation="STAT_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            evidence_class=input_.evidence_class,
            canary_n=len(canary_trades),
            control_n=len(control_trades),
            canary_mean_profit=0.0,
            control_mean_profit=0.0,
            mean_profit_diff=0.0,
            bootstrap_ci_low=0.0,
            bootstrap_ci_high=0.0,
            effect_size=0.0,
            canary_winrate=0.0,
            control_winrate=0.0,
            canary_profit_factor=None,
            control_profit_factor=None,
            blocked_reasons=tuple(blocked),
            evidence_grade="BLOCKED",
            next_step="Fix input validation errors and retry.",
        )

    # ------------------------------------------------------------------
    # Sample adequacy check
    # ------------------------------------------------------------------

    min_samples = input_.min_samples
    canary_n = len(canary_trades)
    control_n = len(control_trades)

    if canary_n < min_samples or control_n < min_samples:
        return StatisticalEvidenceResult(
            status="STAT_INSUFFICIENT",
            recommendation="STAT_INSUFFICIENT",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            evidence_class=input_.evidence_class,
            canary_n=canary_n,
            control_n=control_n,
            canary_mean_profit=0.0,
            control_mean_profit=0.0,
            mean_profit_diff=0.0,
            bootstrap_ci_low=0.0,
            bootstrap_ci_high=0.0,
            effect_size=0.0,
            canary_winrate=0.0,
            control_winrate=0.0,
            canary_profit_factor=None,
            control_profit_factor=None,
            blocked_reasons=(
                f"insufficient_samples: canary_n={canary_n}, "
                f"control_n={control_n}, "
                f"need >= {min_samples} for class {input_.evidence_class}",
            ),
            evidence_grade="INSUFFICIENT",
            next_step=(
                f"Collect at least {min_samples} closed trades per arm. "
                f"Currently: canary={canary_n}, control={control_n}."
            ),
        )

    # ------------------------------------------------------------------
    # Compute metrics
    # ------------------------------------------------------------------

    canary_values = tuple(t.profit_abs for t in canary_trades)
    control_values = tuple(t.profit_abs for t in control_trades)

    canary_mean = mean(canary_values)
    control_mean = mean(control_values)
    mean_diff = canary_mean - control_mean

    canary_winrate = _compute_winrate(canary_trades)
    control_winrate = _compute_winrate(control_trades)

    canary_pf = calculate_profit_factor(canary_trades)
    control_pf = calculate_profit_factor(control_trades)

    # ------------------------------------------------------------------
    # Bootstrap CI
    # ------------------------------------------------------------------

    ci_low, ci_high = bootstrap_mean_diff_ci(
        canary_values,
        control_values,
        iterations=input_.bootstrap_iterations,
        confidence_level=input_.confidence_level,
        random_seed=input_.random_seed,
    )

    # ------------------------------------------------------------------
    # Effect size
    # ------------------------------------------------------------------

    effect_size = _compute_effect_size(canary_values, control_values)

    # ------------------------------------------------------------------
    # Evidence grade
    # ------------------------------------------------------------------

    evidence_grade, _ = _grade_evidence(
        canary_n=canary_n,
        control_n=control_n,
        mean_diff=mean_diff,
        ci_low=ci_low,
        ci_high=ci_high,
        effect_size=effect_size,
        evidence_class=input_.evidence_class,
    )

    # ------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------

    if evidence_grade == "INSUFFICIENT":
        recommendation: Literal[
            "STAT_KEEP", "STAT_EXTEND", "STAT_ROLLBACK",
            "STAT_INSUFFICIENT", "STAT_BLOCKED",
        ] = "STAT_INSUFFICIENT"
        next_step = (
            f"Evidence grade is INSUFFICIENT. "
            f"Need more samples ({min_samples} per arm minimum)."
        )
    else:
        rec, _rec_reasons = _compute_recommendation(
            mean_diff=mean_diff,
            ci_low=ci_low,
            ci_high=ci_high,
            canary_pf=canary_pf,
            control_pf=control_pf,
            evidence_grade=evidence_grade,
        )
        recommendation = rec
        next_step = _build_next_step(recommendation, evidence_grade, input_.candidate_id)

    return StatisticalEvidenceResult(
        status="STAT_READY" if evidence_grade != "INSUFFICIENT" else "STAT_INSUFFICIENT",
        recommendation=recommendation,
        change_id=input_.change_id,
        candidate_id=input_.candidate_id,
        evidence_class=input_.evidence_class,
        canary_n=canary_n,
        control_n=control_n,
        canary_mean_profit=canary_mean,
        control_mean_profit=control_mean,
        mean_profit_diff=mean_diff,
        bootstrap_ci_low=ci_low,
        bootstrap_ci_high=ci_high,
        effect_size=effect_size,
        canary_winrate=canary_winrate,
        control_winrate=control_winrate,
        canary_profit_factor=canary_pf,
        control_profit_factor=control_pf,
        blocked_reasons=(),
        evidence_grade=evidence_grade,
        next_step=next_step,
    )


def _build_next_step(
    recommendation: str,
    evidence_grade: str,
    candidate_id: str,
) -> str:
    """Build a human-readable next step from the recommendation."""
    if recommendation == "STAT_KEEP":
        return (
            f"Statistical evidence supports KEEP for {candidate_id} "
            f"(grade={evidence_grade}). Proceed with next candidate iteration."
        )
    if recommendation == "STAT_EXTEND":
        return (
            f"Statistical evidence suggests EXTEND for {candidate_id} "
            f"(grade={evidence_grade}). Collect more data and re-evaluate."
        )
    if recommendation == "STAT_ROLLBACK":
        return (
            f"Statistical evidence supports ROLLBACK for {candidate_id} "
            f"(grade={evidence_grade}). Canary underperforms control."
        )
    if recommendation == "STAT_INSUFFICIENT":
        return (
            f"Insufficient statistical evidence for {candidate_id}. "
            f"More closed trades needed."
        )
    return f"Statistical evidence evaluation completed for {candidate_id}."


# ---------------------------------------------------------------------------
# Snapshot helper — build StatisticalEvidenceInput from evidence snapshot dict
# ---------------------------------------------------------------------------


def build_stat_input_from_snapshot(
    *,
    change_id: str,
    candidate_id: str,
    snapshot: dict[str, object],
    canary_bot: str,
    control_bot: str,
    evidence_class: str = "A",
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> StatisticalEvidenceInput | None:
    """Build a StatisticalEvidenceInput from a raw evidence snapshot dict.

    Returns None if trade samples are missing or malformed (non-blocking).
    """
    canary_raw = snapshot.get("canary", {})
    control_raw = snapshot.get("control", {})

    if not isinstance(canary_raw, dict) or not isinstance(control_raw, dict):
        return None

    canary_trades_raw = canary_raw.get("trades_since_t0", [])
    control_trades_raw = control_raw.get("trades_since_t0", [])

    if not isinstance(canary_trades_raw, list) or not isinstance(control_trades_raw, list):
        return None

    if not canary_trades_raw or not control_trades_raw:
        return None

    try:
        canary_trades = tuple(
            TradeSample(
                trade_id=str(t.get("trade_id", f"c_{i}")),
                bot_id=canary_bot,
                close_timestamp_utc=str(t.get("close_timestamp_utc", "")),
                profit_abs=float(t.get("profit_abs", 0.0)),
                profit_ratio=float(t.get("profit_ratio", 0.0)),
            )
            for i, t in enumerate(canary_trades_raw)
        )
        control_trades = tuple(
            TradeSample(
                trade_id=str(t.get("trade_id", f"ctrl_{i}")),
                bot_id=control_bot,
                close_timestamp_utc=str(t.get("close_timestamp_utc", "")),
                profit_abs=float(t.get("profit_abs", 0.0)),
                profit_ratio=float(t.get("profit_ratio", 0.0)),
            )
            for i, t in enumerate(control_trades_raw)
        )
    except (TypeError, ValueError, KeyError):
        return None

    return StatisticalEvidenceInput(
        change_id=change_id,
        candidate_id=candidate_id,
        canary=ArmTradeEvidence(bot_id=canary_bot, trades=canary_trades),
        control=ArmTradeEvidence(bot_id=control_bot, trades=control_trades),
        evidence_class=evidence_class,  # type: ignore[arg-type]
        bootstrap_iterations=bootstrap_iterations,
        confidence_level=confidence_level,
        random_seed=random_seed,
    )
