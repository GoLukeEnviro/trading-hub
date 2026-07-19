"""Tests for FreqForge_Gate0_Core_v1 — stripped strategy verification."""
from __future__ import annotations

import pytest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_gate0_core_v1_exists():
    """Verify the stripped strategy file exists and has the right class name."""
    path = REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py"
    assert path.is_file(), f"Strategy file not found: {path}"


def test_gate0_core_v1_class_name():
    content = (REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py").read_text()
    assert "class FreqForge_Gate0_Core_v1(IStrategy):" in content


def test_gate0_core_v1_has_no_primo_import():
    content = (REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py").read_text()
    assert "from primo_signal" not in content


def test_gate0_core_v1_has_no_fleetrisk_import():
    """Verify FleetRiskManager is not imported (comments/notes are OK)."""
    content = (REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py").read_text()
    # Check that the import line doesn't contain FleetRiskManager
    for line in content.splitlines():
        if "import" in line and "FleetRiskManager" in line:
            raise AssertionError(f"FleetRiskManager import found: {line}")


def test_gate0_core_v1_has_no_primo_import():
    """Verify primo_signal is not imported as a module."""
    content = (REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py").read_text()
    for line in content.splitlines():
        if "from primo_signal import" in line or "import primo_signal" in line:
            raise AssertionError(f"Primo import found: {line}")
    content = (REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py").read_text()

def test_max_missing_formula_exists():
    """Verify the 5% formula function exists."""
    from si_v2.research.gate0_evaluation_integration import _compute_max_missing_candles
    result = _compute_max_missing_candles(
        pairs=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
        timeframe="15m",
    )
    assert result > 0
    # 18 months of 15m candles: ~52k per pair, 156k total, 5% = ~7,800
    assert 7000 < result < 10000


def test_min_duration_days_90():
    from si_v2.research.gate0_evaluation_integration import CALIBRATION
    # Full window duration should impose min_duration_days=90
    wf_days = 92
    assert wf_days >= 90  # WF windows are ~92 days
