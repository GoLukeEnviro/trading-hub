"""SI v2 Dynamic Exit Engine.

This module is intentionally pure and deterministic:

- no exchange I/O
- no REST calls
- no config mutation
- no live-trading side effects
- no dependency on runtime containers

It computes conservative stop-loss / take-profit levels for long and short
setups using one of three modes:

- fixed
- atr
- bollinger_distance

Inputs are validated strictly and unusable data produces a blocked result with
explicit reason codes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from si_v2.propose.proposal_scoring.decimal_safe import to_decimal

DYNAMIC_EXIT_QUANTUM: Final[Decimal] = Decimal("0.000001")
DYNAMIC_EXIT_STATUSES: Final[tuple[str, str]] = ("valid", "blocked")
DYNAMIC_EXIT_MODES: Final[tuple[str, str, str]] = ("fixed", "atr", "bollinger_distance")
DYNAMIC_EXIT_DIRECTIONS: Final[tuple[str, str]] = ("long", "short")

STATUS_VALID: Final[str] = "valid"
STATUS_BLOCKED: Final[str] = "blocked"

MODE_FIXED: Final[str] = "fixed"
MODE_ATR: Final[str] = "atr"
MODE_BOLLINGER_DISTANCE: Final[str] = "bollinger_distance"

DIRECTION_LONG: Final[str] = "long"
DIRECTION_SHORT: Final[str] = "short"

REASON_MISSING_COLUMNS: Final[str] = "missing_columns"
REASON_MISSING_ATR: Final[str] = "missing_atr"
REASON_INVALID_ENTRY_PRICE: Final[str] = "invalid_entry_price"
REASON_INVALID_ATR: Final[str] = "invalid_atr"
REASON_MISSING_BOLLINGER_VALUES: Final[str] = "missing_bollinger_values"
REASON_INCONSISTENT_BOLLINGER_VALUES: Final[str] = "inconsistent_bollinger_values"
REASON_INVALID_PARAMETERS: Final[str] = "invalid_parameters"
REASON_INSUFFICIENT_CANDLES: Final[str] = "insufficient_candles"
REASON_MINIMUM_RISK_DISTANCE_APPLIED: Final[str] = "minimum_risk_distance_applied"
REASON_MAXIMUM_STOP_DISTANCE_APPLIED: Final[str] = "maximum_stop_distance_applied"
REASON_UNSUPPORTED_DIRECTION: Final[str] = "unsupported_direction"
REASON_UNSUPPORTED_MODE: Final[str] = "unsupported_mode"

_REQUIRED_ROW_COLUMNS_COMMON: Final[tuple[str, ...]] = (
    "entry_price",
    "direction",
    "mode",
    "stop_multiplier",
    "take_profit_multiplier",
    "minimum_risk_distance",
    "candle_count",
    "minimum_candles",
)
_REQUIRED_ROW_COLUMNS_BY_MODE: Final[dict[str, tuple[str, ...]]] = {
    MODE_FIXED: (),
    MODE_ATR: ("atr",),
    MODE_BOLLINGER_DISTANCE: ("bollinger_upper", "bollinger_mid", "bollinger_lower"),
}


@dataclass(frozen=True, slots=True)
class DynamicExitResult:
    """Result of a dynamic exit calculation."""

    status: str
    mode: str
    direction: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    risk_reward_ratio: Decimal | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dictionary.

        Decimal values are stringified to preserve exact deterministic
        rounding without depending on JSON encoder behavior.
        """

        def _dump_decimal(value: Decimal | None) -> str | None:
            if value is None:
                return None
            return format(value, "f")

        return {
            "status": self.status,
            "mode": self.mode,
            "direction": self.direction,
            "stop_loss": _dump_decimal(self.stop_loss),
            "take_profit": _dump_decimal(self.take_profit),
            "risk_distance": _dump_decimal(self.risk_distance),
            "reward_distance": _dump_decimal(self.reward_distance),
            "risk_reward_ratio": _dump_decimal(self.risk_reward_ratio),
            "reason_codes": list(self.reason_codes),
        }


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(DYNAMIC_EXIT_QUANTUM, rounding=ROUND_HALF_EVEN)


def _coerce_decimal(value: object, field_name: str) -> Decimal:
    return to_decimal(value, field_name)


def _coerce_optional_decimal(value: object | None, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return _coerce_decimal(value, field_name)


def _normalize_direction(direction: object) -> str | None:
    if not isinstance(direction, str):
        return None
    normalized = direction.strip().lower()
    if normalized in (DIRECTION_LONG, DIRECTION_SHORT):
        return normalized
    return None


def _normalize_mode(mode: object) -> str | None:
    if not isinstance(mode, str):
        return None
    normalized = mode.strip().lower()
    if normalized in DYNAMIC_EXIT_MODES:
        return normalized
    return None


def _blocked(
    *,
    mode: str,
    direction: str,
    reason_codes: tuple[str, ...],
) -> DynamicExitResult:
    return DynamicExitResult(
        status=STATUS_BLOCKED,
        mode=mode,
        direction=direction,
        stop_loss=None,
        take_profit=None,
        risk_distance=None,
        reward_distance=None,
        risk_reward_ratio=None,
        reason_codes=reason_codes,
    )


def _validate_positive_quantity(value: object, field_name: str) -> Decimal:
    decimal_value = _coerce_decimal(value, field_name)
    if decimal_value <= 0:
        raise ValueError(f"{field_name} must be > 0; got {decimal_value}")
    return decimal_value


def _validate_non_negative_quantity(value: object, field_name: str) -> Decimal:
    decimal_value = _coerce_decimal(value, field_name)
    if decimal_value < 0:
        raise ValueError(f"{field_name} must be >= 0; got {decimal_value}")
    return decimal_value


def _validate_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an int; got {type(value).__name__}")
    return value


def _missing_row_columns(row: Mapping[str, object], mode: str) -> tuple[str, ...]:
    required: list[str] = list(_REQUIRED_ROW_COLUMNS_COMMON)
    for column in _REQUIRED_ROW_COLUMNS_BY_MODE[mode]:
        required.append(column)
    missing = [column for column in required if column not in row]
    return tuple(missing)


def calculate_dynamic_exit_from_row(row: Mapping[str, object]) -> DynamicExitResult:
    """Calculate exits from a mapping such as a candle/indicator row.

    This helper detects missing columns explicitly before delegating to the
    core calculator.
    """

    mode = _normalize_mode(row.get("mode"))
    direction = _normalize_direction(row.get("direction"))
    if mode is None or direction is None:
        return _blocked(
            mode=mode or str(row.get("mode", "unknown")),
            direction=direction or str(row.get("direction", "unknown")),
            reason_codes=(REASON_UNSUPPORTED_MODE if mode is None else REASON_UNSUPPORTED_DIRECTION,),
        )

    missing = _missing_row_columns(row, mode)
    if missing:
        return _blocked(
            mode=mode,
            direction=direction,
            reason_codes=(REASON_MISSING_COLUMNS,),
        )

    return calculate_dynamic_exit(
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


def calculate_dynamic_exit(
    *,
    entry_price: object,
    direction: object,
    mode: object,
    atr: object | None = None,
    bollinger_upper: object | None = None,
    bollinger_mid: object | None = None,
    bollinger_lower: object | None = None,
    stop_multiplier: object = Decimal("1"),
    take_profit_multiplier: object = Decimal("2"),
    minimum_risk_distance: object = Decimal("0"),
    maximum_stop_distance: object | None = None,
    candle_count: object = 0,
    minimum_candles: object = 1,
) -> DynamicExitResult:
    """Compute deterministic stop-loss and take-profit levels.

    The calculation is purely advisory. It never mutates runtime state and
    never interacts with exchanges or live trading controls.
    """

    normalized_mode = _normalize_mode(mode)
    normalized_direction = _normalize_direction(direction)
    if normalized_mode is None:
        return _blocked(
            mode=str(mode),
            direction=normalized_direction or str(direction),
            reason_codes=(REASON_UNSUPPORTED_MODE,),
        )
    if normalized_direction is None:
        return _blocked(
            mode=normalized_mode,
            direction=str(direction),
            reason_codes=(REASON_UNSUPPORTED_DIRECTION,),
        )

    try:
        entry = _validate_positive_quantity(entry_price, "entry_price")
    except ValueError:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_ENTRY_PRICE,),
        )

    try:
        candles = _validate_int(candle_count, "candle_count")
        min_candles = _validate_int(minimum_candles, "minimum_candles")
    except ValueError:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )

    if candles < 0 or min_candles <= 0:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )
    if candles < min_candles:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INSUFFICIENT_CANDLES,),
        )

    try:
        stop_mult = _validate_positive_quantity(stop_multiplier, "stop_multiplier")
        take_profit_mult = _validate_positive_quantity(take_profit_multiplier, "take_profit_multiplier")
        min_risk_distance = _validate_non_negative_quantity(minimum_risk_distance, "minimum_risk_distance")
        max_stop_distance = _coerce_optional_decimal(maximum_stop_distance, "maximum_stop_distance")
        if max_stop_distance is not None and max_stop_distance <= 0:
            raise ValueError("maximum_stop_distance must be > 0 when provided")
    except ValueError:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )

    if normalized_mode == MODE_FIXED:
        base_risk_distance = min_risk_distance
        base_reward_distance = min_risk_distance
        if base_risk_distance <= 0:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_INVALID_PARAMETERS,),
            )
        reason_codes: list[str] = []
    elif normalized_mode == MODE_ATR:
        if atr is None:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_MISSING_ATR,),
            )
        try:
            atr_value = _validate_positive_quantity(atr, "atr")
        except ValueError:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_INVALID_ATR,),
            )
        base_risk_distance = atr_value
        base_reward_distance = atr_value
        reason_codes = []
    elif normalized_mode == MODE_BOLLINGER_DISTANCE:
        if bollinger_upper is None or bollinger_mid is None or bollinger_lower is None:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_MISSING_BOLLINGER_VALUES,),
            )
        try:
            upper = _validate_positive_quantity(bollinger_upper, "bollinger_upper")
            mid = _validate_positive_quantity(bollinger_mid, "bollinger_mid")
            lower = _validate_positive_quantity(bollinger_lower, "bollinger_lower")
        except ValueError:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_MISSING_BOLLINGER_VALUES,),
            )
        if not (upper > mid > lower):
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_INCONSISTENT_BOLLINGER_VALUES,),
            )
        if normalized_direction == DIRECTION_LONG:
            base_risk_distance = mid - lower
            base_reward_distance = upper - mid
        else:
            base_risk_distance = upper - mid
            base_reward_distance = mid - lower
        reason_codes = []
    else:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_UNSUPPORTED_MODE,),
        )

    risk_distance = _quantize(base_risk_distance * stop_mult)
    reward_distance = _quantize(base_reward_distance * take_profit_mult)

    if risk_distance <= 0 or reward_distance <= 0:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )

    if min_risk_distance > 0 and risk_distance < min_risk_distance:
        risk_distance = _quantize(min_risk_distance)
        reason_codes.append(REASON_MINIMUM_RISK_DISTANCE_APPLIED)

    if max_stop_distance is not None and risk_distance > max_stop_distance:
        if max_stop_distance < min_risk_distance and min_risk_distance > 0:
            return _blocked(
                mode=normalized_mode,
                direction=normalized_direction,
                reason_codes=(REASON_INVALID_PARAMETERS,),
            )
        risk_distance = _quantize(max_stop_distance)
        reason_codes.append(REASON_MAXIMUM_STOP_DISTANCE_APPLIED)

    if risk_distance <= 0 or reward_distance <= 0:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )

    if normalized_direction == DIRECTION_LONG:
        stop_loss = _quantize(entry - risk_distance)
        take_profit = _quantize(entry + reward_distance)
    else:
        stop_loss = _quantize(entry + risk_distance)
        take_profit = _quantize(entry - reward_distance)

    if stop_loss <= 0 or take_profit <= 0:
        return _blocked(
            mode=normalized_mode,
            direction=normalized_direction,
            reason_codes=(REASON_INVALID_PARAMETERS,),
        )

    risk_reward_ratio = _quantize(reward_distance / risk_distance)

    return DynamicExitResult(
        status=STATUS_VALID,
        mode=normalized_mode,
        direction=normalized_direction,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        risk_reward_ratio=risk_reward_ratio,
        reason_codes=tuple(reason_codes),
    )
