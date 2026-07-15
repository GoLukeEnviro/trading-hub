"""ATR-based risk position sizing contract (Phase 1C, Issue #597).

Formula:
    position_size = allowed_capital_risk / effective_stop_distance
    effective_stop_distance = ATR * atr_multiplier

ATR must never be treated as the accepted financial loss by itself.

A1 scope: code/tests/contracts only. No strategy rollout, Freqtrade config
mutation, runtime restart or live-capital use.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Status codes
# ---------------------------------------------------------------------------

SIZING_OK = "OK"
SIZING_CAPPED_NOTIONAL = "CAPPED_NOTIONAL"
SIZING_CAPPED_RISK = "CAPPED_RISK"
SIZING_MIN_NOTIONAL_FAIL = "MIN_NOTIONAL_FAIL"
SIZING_INVALID_INPUT = "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionSizingInput:
    """All inputs required for ATR-based position sizing."""

    equity: float
    risk_fraction: float
    atr_value: float
    atr_multiplier: float
    entry_price: float
    min_notional: float = 0.0
    max_notional: float = float("inf")
    precision: int = 2
    fee_slippage_pct: float = 0.1
    leverage: float = 1.0


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SizingDecision:
    """Structured sizing decision with evidence."""

    status: str
    raw_size: float
    capped_size: float
    risk_budget: float
    stop_distance: float
    effective_risk: float
    decision: str  # ACCEPTED | CAPPED | REJECTED


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_input(inp: PositionSizingInput) -> str | None:
    """Return SIZING_INVALID_INPUT if any field is invalid, else None."""
    if not (isinstance(inp.equity, (int, float)) and math.isfinite(inp.equity) and inp.equity > 0):
        return SIZING_INVALID_INPUT
    if not (isinstance(inp.risk_fraction, (int, float)) and math.isfinite(inp.risk_fraction)
            and 0.0 < inp.risk_fraction <= 1.0):
        return SIZING_INVALID_INPUT
    if not (isinstance(inp.atr_value, (int, float)) and math.isfinite(inp.atr_value) and inp.atr_value > 0):
        return SIZING_INVALID_INPUT
    if not (isinstance(inp.atr_multiplier, (int, float)) and math.isfinite(inp.atr_multiplier)
            and inp.atr_multiplier > 0):
        return SIZING_INVALID_INPUT
    if not (isinstance(inp.entry_price, (int, float)) and math.isfinite(inp.entry_price)
            and inp.entry_price > 0):
        return SIZING_INVALID_INPUT
    if not (isinstance(inp.leverage, (int, float)) and math.isfinite(inp.leverage) and inp.leverage > 0):
        return SIZING_INVALID_INPUT
    return None


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def _floor_to_precision(value: float, precision: int) -> float:
    """Round down to given decimal precision. Never round up."""
    if precision <= 0:
        return math.floor(value)
    factor = 10**precision
    return math.floor(value * factor) / factor


def calculate_position_size(inp: PositionSizingInput) -> SizingDecision:
    """Calculate ATR-risk-based position size with caps and rounding.

    Returns a ``SizingDecision`` whose ``.decision`` is one of:
    - ``ACCEPTED`` — within all limits.
    - ``CAPPED`` — truncated by notional or risk cap.
    - ``REJECTED`` — cannot satisfy min notional within risk budget,
      or invalid input.
    """
    # 1) input validation
    err = _validate_input(inp)
    if err is not None:
        return SizingDecision(
            status=err,
            raw_size=0.0,
            capped_size=0.0,
            risk_budget=0.0,
            stop_distance=0.0,
            effective_risk=0.0,
            decision="REJECTED",
        )

    # 2) compute risk budget and stop distance
    risk_budget = inp.equity * inp.risk_fraction
    stop_distance = inp.atr_value * inp.atr_multiplier

    # 3) raw position size (before caps, fees or rounding)
    raw_size = risk_budget / stop_distance

    # 4) fee / slippage buffer (never negative)
    fee_factor = max(0.0, 1.0 - inp.fee_slippage_pct / 100.0)
    after_fee = raw_size * fee_factor

    # 5) leverage adjustment — raw_size is in contract/unit terms;
    #    more leverage means less margin per unit, but the risk budget
    #    per unit remains the same, so size stays unchanged. We record
    #    leverage for audit purposes.
    after_fee = raw_size * fee_factor  # leverage already priced into risk per contract

    # 6) conservative rounding (never round up) — apply BEFORE cap checks
    #    so that the capped_size reflects exchange-precision reality
    rounded = _floor_to_precision(after_fee, inp.precision)

    # 7) convert to notional for cap comparisons
    notional = rounded * inp.entry_price

    # 8) apply caps: most restrictive wins (compared in notional terms)
    status = SIZING_OK

    if inp.max_notional != float("inf") and notional > inp.max_notional:
        # Cap to max_notional in notional terms, then convert back to contracts
        capped_notional = inp.max_notional
        capped = _floor_to_precision(capped_notional / inp.entry_price, inp.precision)
        status = SIZING_CAPPED_NOTIONAL
    elif notional < inp.min_notional:
        # Min notional conflict: do NOT increase size to meet min.
        # Risk budget would be exceeded.
        return SizingDecision(
            status=SIZING_MIN_NOTIONAL_FAIL,
            raw_size=raw_size,
            capped_size=rounded,
            risk_budget=risk_budget,
            stop_distance=stop_distance,
            effective_risk=rounded * stop_distance,
            decision="REJECTED",
        )
    else:
        capped = rounded

    # 9) effective risk = capped_size * stop_distance
    effective_risk = capped * stop_distance

    # 10) final decision
    if effective_risk > risk_budget * 1.0001:
        status = SIZING_CAPPED_RISK
        decision = "CAPPED"
    elif status == SIZING_CAPPED_NOTIONAL:
        decision = "CAPPED"
    else:
        decision = "ACCEPTED"

    return SizingDecision(
        status=status,
        raw_size=raw_size,
        capped_size=capped,
        risk_budget=risk_budget,
        stop_distance=stop_distance,
        effective_risk=effective_risk,
        decision=decision,
    )
