"""Symbol normalizer for Rainbow producer signals.

Maps between raw exchange symbols (BTCUSDT) and trading-hub canonical
format (BTC/USDT:USDT).
"""

from __future__ import annotations

# Map of known raw symbols to trading-hub canonical format
_KNOWN_MAP: dict[str, str] = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
    # Raw format used by TA collector
    "BTC/USDT": "BTC/USDT:USDT",
    "ETH/USDT": "ETH/USDT:USDT",
    "SOL/USDT": "SOL/USDT:USDT",
}


def normalize_symbol(raw: str | None) -> str:
    """Normalize a symbol to trading-hub canonical format.

    Examples:
        BTCUSDT  -> BTC/USDT:USDT
        ETHUSDT  -> ETH/USDT:USDT
        SOLUSDT  -> SOL/USDT:USDT
        BTC/USDT -> BTC/USDT:USDT
    """
    if not raw:
        return "unknown"
    if raw in _KNOWN_MAP:
        return _KNOWN_MAP[raw]

    # Already canonical (contains : separator)
    if ":" in raw and "/" in raw:
        return raw

    # Has slash but missing futures suffix
    if "/" in raw:
        base, quote = raw.split("/", 1)
        return f"{base}/{quote}:{quote}"

    # Raw format like BTCUSDT -> extract base + quote
    for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"):
        if raw.endswith(quote) and len(raw) > len(quote):
            base = raw[: -len(quote)]
            return f"{base}/{quote}:{quote}"

    # Unknown symbol — return UNMAPPED prefix to prevent silent downstream
    # mapping issues. The raw upstream asset remains auditable via
    # metadata.upstream_signal.raw_asset.
    return f"UNMAPPED:{raw}"


def normalize_symbols(raw_symbols: list[str]) -> list[str]:
    """Normalize a list of symbols."""
    return [normalize_symbol(s) for s in raw_symbols]


def is_known_symbol(raw: str | None) -> bool:
    """Check whether a symbol is known to the normalizer."""
    if not raw:
        return False
    if raw in _KNOWN_MAP:
        return True
    if ":" in raw and "/" in raw:
        return True
    if "/" in raw:
        return True
    return any(raw.endswith(quote) and len(raw) > len(quote) for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"))
