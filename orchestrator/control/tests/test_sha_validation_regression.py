"""Regression tests for commit-SHA validation in reconcile_controller_baseline.

Covers the 40-char SHA-1 fix (commit 593d55e) and boundary cases for both
SHA-1 (40-char) and SHA-256 (64-char) validation paths.
"""

from __future__ import annotations

import pytest

from orchestrator.control.reconcile_controller_baseline import (
    _validate_sha,
)


# ---------------------------------------------------------------------------
# SHA-1 (40-char) acceptance and rejection
# ---------------------------------------------------------------------------


class TestSHA1Validation:
    """Tests for 40-character Git SHA-1 acceptance."""

    def test_valid_40char_lowercase_hex_accepted(self) -> None:
        _validate_sha("a" * 40)

    def test_valid_40char_realistic_sha(self) -> None:
        _validate_sha("593d55e877b379100133d4760766806b4ba828df")

    def test_39char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 39)

    def test_41char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 41)


# ---------------------------------------------------------------------------
# SHA-256 (64-char) acceptance and rejection
# ---------------------------------------------------------------------------


class TestSHA256Validation:
    """Tests for 64-character SHA-256 acceptance."""

    def test_valid_64char_lowercase_hex_accepted(self) -> None:
        _validate_sha("a" * 64)

    def test_63char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 63)

    def test_65char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 65)


# ---------------------------------------------------------------------------
# Case rejection
# ---------------------------------------------------------------------------


class TestSHACaseRejection:
    """Uppercase hex characters must be rejected."""

    def test_uppercase_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("A" * 40)

    def test_uppercase_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("A" * 64)

    def test_mixed_case_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("aB" * 20)

    def test_mixed_case_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("aB" * 32)


# ---------------------------------------------------------------------------
# Non-hex character rejection
# ---------------------------------------------------------------------------


class TestNonHexRejection:
    """Non-hexadecimal characters must be rejected."""

    def test_g_in_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("g" + "a" * 39)

    def test_z_in_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("z" + "a" * 63)

    def test_space_in_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha(" " + "a" * 39)

    def test_dash_in_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("-" + "a" * 63)


# ---------------------------------------------------------------------------
# Whitespace rejection
# ---------------------------------------------------------------------------


class TestWhitespaceRejection:
    """Leading or trailing whitespace must be rejected."""

    def test_leading_space_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha(" " + "a" * 40)

    def test_trailing_space_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 40 + " ")

    def test_leading_newline_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("\n" + "a" * 64)

    def test_trailing_newline_64char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a" * 64 + "\n")

    def test_tab_wrapped_40char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("\t" + "a" * 40 + "\t")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestSHAEdgeCases:
    """Edge-case inputs."""

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("")

    def test_single_char_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            _validate_sha("a")

    def test_all_zeros_40char_accepted(self) -> None:
        _validate_sha("0" * 40)

    def test_all_f_64char_accepted(self) -> None:
        _validate_sha("f" * 64)

    def test_all_nines_40char_rejected(self) -> None:
        """Digit 9 is valid hex, so all-9s should be accepted."""
        _validate_sha("9" * 40)
