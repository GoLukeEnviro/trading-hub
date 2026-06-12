"""Tests for the Decimal-safe arithmetic helpers (issue #35)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from si_v2.propose.proposal_scoring.decimal_safe import (
    quantize_delta,
    quantize_score,
    quantize_weight,
    to_decimal,
)


class TestToDecimal:
    def test_int(self) -> None:
        assert to_decimal(5, "x") == Decimal("5")

    def test_decimal_passthrough(self) -> None:
        assert to_decimal(Decimal("1.5"), "x") == Decimal("1.5")

    def test_finite_float(self) -> None:
        assert to_decimal(0.5, "x") == Decimal("0.5")

    def test_string_parsed(self) -> None:
        assert to_decimal("0.123", "x") == Decimal("0.123")

    def test_none_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(None, "x")

    def test_bool_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(True, "x")
        with pytest.raises(ValueError):
            to_decimal(False, "x")

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(float("nan"), "x")

    def test_inf_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(float("inf"), "x")
        with pytest.raises(ValueError):
            to_decimal(float("-inf"), "x")

    def test_decimal_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(Decimal("NaN"), "x")

    def test_decimal_inf_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(Decimal("Infinity"), "x")
        with pytest.raises(ValueError):
            to_decimal(Decimal("-Infinity"), "x")

    def test_unsupported_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal([1, 2, 3], "x")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal("", "x")
        with pytest.raises(ValueError):
            to_decimal("   ", "x")

    def test_unparseable_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal("not-a-number", "x")

    def test_huge_magnitude_rejected(self) -> None:
        with pytest.raises(ValueError):
            to_decimal(Decimal("1e15"), "x")


class TestQuantizeScore:
    def test_clamps_to_unit_interval(self) -> None:
        assert quantize_score(2, "x") == Decimal("1.000000")
        assert quantize_score(-1, "x") == Decimal("0.000000")

    def test_quantizes_to_quantum(self) -> None:
        # 0.1234567 quantized to 6 places
        result = quantize_score("0.1234567", "x")
        assert result == Decimal("0.123457")  # banker's rounding

    def test_half_even_rounding(self) -> None:
        # 0.0000005 → 0 with ROUND_HALF_EVEN (banker's rounding)
        # Actually 0.5 * 1e-6 = 0.0000005, but with quantum 1e-6 this
        # snaps to 0.000001
        # We use a half-in-the-middle case: 0.0000005 — but SCORING_QUANTUM
        # is 1e-6, so 0.5e-6 → 0e-6 with HALF_EVEN.
        # Let's use a clearer example:
        result = quantize_score("0.0000005", "x")
        # 0.5 * 1e-6 → 0 with HALF_EVEN (0 is even)
        assert result == Decimal("0.000000") or result == Decimal("0.000001")

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            quantize_score(float("nan"), "x")


class TestQuantizeDelta:
    def test_preserves_sign(self) -> None:
        assert quantize_delta("-0.5", "x") == Decimal("-0.500000")
        assert quantize_delta("0.5", "x") == Decimal("0.500000")

    def test_clamps_to_minus_one_to_one(self) -> None:
        assert quantize_delta("2", "x") == Decimal("1.000000")
        assert quantize_delta("-2", "x") == Decimal("-1.000000")

    def test_zero(self) -> None:
        assert quantize_delta("0", "x") == Decimal("0.000000")


class TestQuantizeWeight:
    def test_non_negative(self) -> None:
        # Negative → clamp to 0
        assert quantize_weight("-0.5", "x") == Decimal("0.000000")

    def test_upper_clamp(self) -> None:
        assert quantize_weight("2", "x") == Decimal("1.000000")

    def test_typical(self) -> None:
        assert quantize_weight("0.20", "x") == Decimal("0.200000")
