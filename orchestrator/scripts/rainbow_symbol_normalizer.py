"""Symbol normalizer for Rainbow producer signals.

Maps between Bitget raw symbols (BTCUSDT) and trading-hub canonical
symbol format (BTC/USDT:USDT).

This is needed because the TA collector uses Bitget API format (BTCUSDT)
but SI v2 proposals and cost models expect the canonical format.

Usage:
    from orchestrator.scripts.rainbow_symbol_normalizer import normalize_symbol

    sym = normalize_symbol("BTCUSDT")  # -> "BTC/USDT:USDT"
    sym = normalize_symbol("BTC/USDT:USDT")  # -> "BTC/USDT:USDT" (no-op)
"""

from __future__ import annotations

# Map of known Bitget raw symbols to trading-hub canonical format.
# Futures pairs use ":" separator, spot pairs use "/".
_KNOWN_MAP: dict[str, str] = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
    # Add more as needed
}


def normalize_symbol(raw: str) -> str:
    """Normalize a symbol to trading-hub canonical format.

    Examples:
        BTCUSDT      -> BTC/USDT:USDT
        ETHUSDT      -> ETH/USDT:USDT
        SOLUSDT      -> SOL/USDT:USDT
        BTC/USDT     -> BTC/USDT:USDT  (already canonical-ish)
        BTC/USDT:USDT -> BTC/USDT:USDT (already canonical)
    """
    # Direct lookup
    if raw in _KNOWN_MAP:
        return _KNOWN_MAP[raw]

    # Already canonical format (contains / and :)
    if "/" in raw and ":" in raw:
        return raw

    # Already has slash but missing futures suffix
    if "/" in raw:
        base, quote = raw.split("/", 1)
        return f"{base}/{quote}:{quote}"

    # Raw format like BTCUSDT -> split on first non-alpha
    # Common quote currencies: USDT, USDC, BUSD, BTC, ETH
    for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"):
        if raw.endswith(quote) and len(raw) > len(quote):
            base = raw[: -len(quote)]
            return f"{base}/{quote}:{quote}"

    # Fallback: return as-is
    return raw


def normalize_symbols(raw_symbols: list[str]) -> list[str]:
    """Normalize a list of symbols."""
    return [normalize_symbol(s) for s in raw_symbols]
