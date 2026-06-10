"""Safe parameter definitions and validation.

Defines the set of mutable parameters, forbidden keys, and validation
functions for guarding mutation candidates.
"""

from __future__ import annotations

# The 6 parameters that are safe to mutate
SAFE_PARAMETERS: tuple[str, ...] = (
    "rsi_period",
    "stoploss_pct",
    "take_profit_pct",
    "stake_factor",
    "max_open_trades",
    "cooldown_candles",
)

# Keys that must never appear in a mutation candidate
FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "dry_run",
        "exchange",
        "secret",
        "password",
        "key",
        "telegram",
        "api_server",
        "stake_currency",
        "leverage",
        "force_exit",
        "force_sell",
        "db_url",
        "db_urls",
        "dry_run_wallet",
        "api_key",
        "token",
    }
)

# Parameter ranges for validation
_PARAMETER_RANGES: dict[str, tuple[float, float]] = {
    "rsi_period": (2, 50),
    "stoploss_pct": (-0.5, -0.001),
    "take_profit_pct": (0.001, 0.5),
    "stake_factor": (0.1, 5.0),
    "max_open_trades": (1, 20),
    "cooldown_candles": (0, 100),
}


def guard_candidate(params: dict[str, float | int]) -> bool:
    """Check whether a parameter dict contains only safe, non-forbidden keys.

    Args:
        params: Parameter dictionary to validate.

    Returns:
        True if all keys are in SAFE_PARAMETERS and none are in FORBIDDEN_KEYS.
    """
    if not params:
        return False
    for key in params:
        if key in FORBIDDEN_KEYS:
            return False
        if key not in SAFE_PARAMETERS:
            return False
    return True


def validate_safe_parameter(name: str, value: float | int) -> bool:
    """Validate an individual parameter against its allowed range.

    Args:
        name: Parameter name (must be in SAFE_PARAMETERS).
        value: Parameter value to validate.

    Returns:
        True if the value is within the allowed range for the parameter.
    """
    if name not in _PARAMETER_RANGES:
        return False
    low, high = _PARAMETER_RANGES[name]
    return low <= float(value) <= high
