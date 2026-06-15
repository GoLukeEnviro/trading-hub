from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pytest

pd = pytest.importorskip("pandas")

from intelligence import regime_detector


def _frame(close: Iterable[float], high_delta: float = 1.0, low_delta: float = 1.0) -> object:
    close_s = pd.Series(list(close), dtype=float)
    return pd.DataFrame(
        {
            "high": close_s + high_delta,
            "low": close_s - low_delta,
            "close": close_s,
        }
    )


class TestRegimeDetector:
    def test_insufficient_data_returns_unknown(self) -> None:
        df = _frame([100.0 + i * 0.1 for i in range(10)])
        result = regime_detector.detect_regime(df)
        assert result["regime"] == "unknown"
        assert result["confidence"] == 0.0
        assert result["error"] == "insufficient_data"

    def test_missing_columns_returns_unknown(self) -> None:
        df = pd.DataFrame({"close": [1, 2, 3], "high": [2, 3, 4]})
        result = regime_detector.detect_regime(df)
        assert result["regime"] == "unknown"
        assert result["confidence"] == 0.0
        assert result["error"].startswith("missing_columns:")

    @pytest.mark.parametrize(
        "adx_value, close_series, expected_regime, high_delta, low_delta",
        [
            (30.0, [100.0 + i * (100.0 / 219.0) for i in range(220)], "strong_trend_up", 2.0, 2.0),
            (30.0, [200.0 - i * (100.0 / 219.0) for i in range(220)], "strong_trend_down", 2.0, 2.0),
            (22.0, [100.0 for _ in range(220)], "high_volatility", 2.0, 2.0),
            (10.0, [100.0 for _ in range(220)], "choppy", 2.0, 2.0),
            (10.0, [100.0 + i * (0.2 / 219.0) for i in range(220)], "ranging", 0.1, 0.1),
        ],
    )
    def test_deterministic_classification(
        self,
        monkeypatch: pytest.MonkeyPatch,
        adx_value: float,
        close_series: list[float],
        expected_regime: str,
        high_delta: float,
        low_delta: float,
    ) -> None:
        df = _frame(close_series, high_delta=high_delta, low_delta=low_delta)
        monkeypatch.setattr(
            regime_detector,
            "calculate_adx",
            lambda high, low, close, period=14: pd.Series([0.0] * (len(close) - 1) + [adx_value]),
        )
        result = regime_detector.detect_regime(df)
        assert result["regime"] == expected_regime
        assert set(result.keys()) == {"regime", "confidence", "adx", "atr_pct", "ema_slope", "details"}
        assert isinstance(result["details"], dict)

    def test_multiplier_mapping_defaults_unknown(self) -> None:
        assert regime_detector.regime_to_weight_multiplier("strong_trend_up") == 1.15
        assert regime_detector.regime_to_weight_multiplier("unknown") == 1.0
        assert regime_detector.regime_to_weight_multiplier("something_else") == 1.0
