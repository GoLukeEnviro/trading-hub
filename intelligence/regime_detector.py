#!/usr/bin/env python3
"""
Regime Detector v1.0

Detects market regime for crypto pairs to enable regime-aware weighting
in the Rainbow Intelligence Engine and Self-Improvement system.

Regimes:
- strong_trend_up / strong_trend_down
- weak_trend_up / weak_trend_down
- ranging
- high_volatility
- choppy

Author: Consolidated from trading-hub Self-Improvement architecture
"""

import pandas as pd
import numpy as np
from typing import Literal, Dict, Any

Regime = Literal[
    "strong_trend_up", "strong_trend_down",
    "weak_trend_up", "weak_trend_down",
    "ranging", "high_volatility", "choppy"
]


def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate ADX (Average Directional Index)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    tr = pd.concat([high - low, 
                    (high - close.shift()).abs(), 
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(period).mean()
    return adx


def detect_regime(df: pd.DataFrame, 
                  adx_period: int = 14,
                  atr_period: int = 14,
                  ema_period: int = 200,
                  strong_trend_threshold: float = 25.0,
                  high_vol_threshold: float = 0.035) -> Dict[str, Any]:
    """
    Detect current market regime from OHLCV dataframe.

    Returns dict with:
        - regime: str
        - confidence: float (0-1)
        - adx: float
        - atr_pct: float
        - ema_slope: float
        - details: dict
    """
    required_columns = {"high", "low", "close"}
    missing = sorted(required_columns - set(df.columns))
    if missing:
        return {"regime": "unknown", "confidence": 0.0, "error": f"missing_columns:{','.join(missing)}"}

    if len(df) < ema_period + 5:
        return {"regime": "unknown", "confidence": 0.0, "error": "insufficient_data"}

    close = df['close']
    high = df['high']
    low = df['low']

    adx = calculate_adx(high, low, close, adx_period).iloc[-1]
    atr = ((high - low).rolling(atr_period).mean() / close).iloc[-1]
    ema = close.ewm(span=ema_period).mean()
    ema_slope = (ema.iloc[-1] - ema.iloc[-5]) / ema.iloc[-5]   # 5-bar slope

    regime = "ranging"
    confidence = 0.6

    # Strong trend
    if adx > strong_trend_threshold:
        if ema_slope > 0.002:
            regime = "strong_trend_up"
            confidence = min(0.95, 0.6 + (adx - 25) / 50)
        elif ema_slope < -0.002:
            regime = "strong_trend_down"
            confidence = min(0.95, 0.6 + (adx - 25) / 50)
        else:
            regime = "weak_trend_up" if ema_slope > 0 else "weak_trend_down"
            confidence = 0.7

    # High volatility / choppy
    elif atr > high_vol_threshold:
        if adx < 20:
            regime = "choppy"
            confidence = 0.75
        else:
            regime = "high_volatility"
            confidence = 0.7

    # Default ranging
    else:
        regime = "ranging"
        confidence = 0.65

    return {
        "regime": regime,
        "confidence": round(confidence, 3),
        "adx": round(adx, 2),
        "atr_pct": round(atr * 100, 3),
        "ema_slope": round(ema_slope * 100, 4),
        "details": {
            "adx_period": adx_period,
            "atr_period": atr_period,
            "ema_period": ema_period
        }
    }


def regime_to_weight_multiplier(regime: str) -> float:
    """Simple mapping from regime to strategy aggressiveness multiplier."""
    mapping = {
        "strong_trend_up": 1.15,
        "strong_trend_down": 0.85,
        "weak_trend_up": 1.05,
        "weak_trend_down": 0.95,
        "ranging": 0.80,
        "high_volatility": 0.70,
        "choppy": 0.60,
        "unknown": 1.0
    }
    return mapping.get(regime, 1.0)


if __name__ == "__main__":
    # Quick test
    print("Regime Detector v1.0 loaded successfully.")
