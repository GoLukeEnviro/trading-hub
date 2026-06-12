"""Decimal-safe arithmetic for proposal scoring.

All thresholds, scores, and weights in the proposal-scoring policy are
``Decimal`` values quantized to a single documented precision using a
single documented rounding mode. This module provides the only entry
point for that quantization so the rounding mode cannot drift between
callers.

Rules (enforced both at validation time and at quantization time):

- Booleans, ``NaN``, ``+Infinity``, ``-Infinity`` are rejected.
- Strings and integers are accepted only if they parse cleanly.
- Floats are accepted only if they are finite (not NaN, not Inf).
- All quantized results are clamped to ``[0.0, 1.0]`` for component
  scores and to ``[0.0, 1.0]`` for the total score.
- The rounding mode is **banker's rounding** (``ROUND_HALF_EVEN``).
- The quantum is **6 decimal places** (``SCORING_QUANTUM``).
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

SCORING_QUANTUM: Final[Decimal] = Decimal("0.000001")
_MAX_INPUT_ABS: Final[Decimal] = Decimal("1e12")
_SCORE_MIN: Final[Decimal] = Decimal("0")
_SCORE_MAX: Final[Decimal] = Decimal("1")


def to_decimal(value: object, field_name: str) -> Decimal:
    """Convert a Python value to ``Decimal`` with full validation.

    Args:
        value: A ``Decimal``, ``int``, ``float``, or numeric string.
        field_name: Name of the field, used in error messages only.

    Returns:
        A finite ``Decimal``.

    Raises:
        ValueError: If the value is ``None``, ``bool``, ``NaN``,
            ``+Infinity``, ``-Infinity``, or otherwise unparseable.
    """
    if value is None:
        raise ValueError(f"{field_name}: None is not a valid Decimal value")
    if isinstance(value, bool):
        # ``bool`` is a subclass of ``int`` in Python, so we must reject
        # it explicitly to avoid silently treating True as 1.
        raise ValueError(f"{field_name}: bool is not a valid Decimal value")

    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"{field_name}: float {value!r} is not a finite Decimal"
            )
        d = Decimal(repr(value))
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError(f"{field_name}: empty string is not a valid Decimal")
        try:
            d = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(
                f"{field_name}: cannot parse string {value!r} as Decimal"
            ) from exc
    else:
        raise ValueError(
            f"{field_name}: unsupported type {type(value).__name__}"
        )

    if not d.is_finite():
        raise ValueError(f"{field_name}: Decimal {d} is not finite")
    if abs(d) > _MAX_INPUT_ABS:
        raise ValueError(
            f"{field_name}: Decimal {d} magnitude exceeds "
            f"{_MAX_INPUT_ABS}; refusing to quantize"
        )
    return d


def quantize_score(value: object, field_name: str) -> Decimal:
    """Convert ``value`` to a quantized score in ``[0.0, 1.0]``.

    The conversion is:

    1. ``to_decimal(value, field_name)``
    2. Clamp to ``[0.0, 1.0]``
    3. Quantize to ``SCORING_QUANTUM`` with ``ROUND_HALF_EVEN``.

    Args:
        value: Numeric input.
        field_name: Field name for error messages.

    Returns:
        A quantized ``Decimal`` in ``[0.0, 1.0]``.

    Raises:
        ValueError: If the value is not finite.
    """
    d = to_decimal(value, field_name)
    if d < _SCORE_MIN:
        d = _SCORE_MIN
    elif d > _SCORE_MAX:
        d = _SCORE_MAX
    return d.quantize(SCORING_QUANTUM, rounding=ROUND_HALF_EVEN)


def quantize_delta(value: object, field_name: str) -> Decimal:
    """Convert ``value`` to a quantized delta in ``[-1.0, 1.0]``.

    Used for proposal deltas (which are signed) and policy-level delta
    caps (which are non-negative). The output preserves sign.

    Args:
        value: Numeric input.
        field_name: Field name for error messages.

    Returns:
        A quantized ``Decimal`` in ``[-1.0, 1.0]``.

    Raises:
        ValueError: If the value is not finite.
    """
    d = to_decimal(value, field_name)
    if d < -_SCORE_MAX:
        d = -_SCORE_MAX
    elif d > _SCORE_MAX:
        d = _SCORE_MAX
    return d.quantize(SCORING_QUANTUM, rounding=ROUND_HALF_EVEN)


def quantize_weight(value: object, field_name: str) -> Decimal:
    """Convert ``value`` to a quantized non-negative weight in ``[0.0, 1.0]``.

    Weights are non-negative by policy. ``value`` is clamped to
    ``[0.0, 1.0]`` and quantized with ``ROUND_HALF_EVEN``.

    Args:
        value: Numeric input.
        field_name: Field name for error messages.

    Returns:
        A quantized ``Decimal`` in ``[0.0, 1.0]``.

    Raises:
        ValueError: If the value is not finite.
    """
    d = to_decimal(value, field_name)
    if d < _SCORE_MIN:
        d = _SCORE_MIN
    elif d > _SCORE_MAX:
        d = _SCORE_MAX
    return d.quantize(SCORING_QUANTUM, rounding=ROUND_HALF_EVEN)
