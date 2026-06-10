"""Tests for #146: Rehearsal artifact redaction policy.

Verifies:
  - Unsafe artifact fixture fails redaction checks
  - Safe sanitized fixture passes redaction checks
  - Output ordering and report content are deterministic
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REDACTION_POLICY_PATH = (
    PROJECT_ROOT / "security" / "rehearsal_artifact_redaction_policy.md"
)
SAFE_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "redaction" / "safe" / "clean_config.json"
UNSAFE_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "redaction" / "unsafe" / "exposed_secrets.json"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


# Detection patterns from the redaction policy
UNSAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?(?!\[REDACTED_)[^\"' ]{8,}", re.IGNORECASE),
    re.compile(r"api[_-]?secret\s*[:=]\s*[\"']?[^\"' ]{8,}", re.IGNORECASE),
    re.compile(r"passphrase\s*[:=]\s*[\"']?[^\"' ]{8,}", re.IGNORECASE),
    re.compile(r"0x[a-fA-F0-9]{40}\b"),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"/home/[^/\s]+/projects/"),
    re.compile(r"/opt/data/"),
]

# Redaction placeholders that are safe
SAFE_PLACEHOLDERS: list[str] = [
    "[REDACTED_API_KEY]",
    "[REDACTED_API_SECRET]",
    "[REDACTED_BOT_TOKEN]",
    "[REDACTED_PRIVATE_KEY]",
    "[REDACTED_IP]",
]


def _check_unsafe(text: str) -> list[str]:
    """Return list of unsafe pattern matches in text."""
    found: list[str] = []
    for pat in UNSAFE_PATTERNS:
        if pat.search(text):
            found.append(pat.pattern)
    return found


def _check_safe_placeholders(text: str) -> list[str]:
    """Return list of safe placeholders found in text."""
    found: list[str] = []
    for placeholder in SAFE_PLACEHOLDERS:
        if placeholder in text:
            found.append(placeholder)
    return found


# ──────────────────────────────────────────────
# Policy artifact exists
# ──────────────────────────────────────────────


class TestRedactionPolicyArtifactExists:
    """The redaction policy markdown must exist."""

    def test_policy_file_exists(self) -> None:
        assert REDACTION_POLICY_PATH.is_file(), (
            f"Redaction policy not found: {REDACTION_POLICY_PATH}"
        )

    def test_policy_file_nonempty(self) -> None:
        text = REDACTION_POLICY_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Redaction policy file is too short"

    def test_policy_has_sensitive_categories(self) -> None:
        text = REDACTION_POLICY_PATH.read_text(encoding="utf-8")
        assert "Sensitive-Material Categories" in text

    def test_policy_has_approved_placeholders(self) -> None:
        text = REDACTION_POLICY_PATH.read_text(encoding="utf-8")
        assert "Approved Redaction Placeholders" in text

    def test_policy_has_fail_closed_behaviour(self) -> None:
        text = REDACTION_POLICY_PATH.read_text(encoding="utf-8")
        assert "Fail-Closed" in text


# ──────────────────────────────────────────────
# Unsafe fixture fails
# ──────────────────────────────────────────────


class TestUnsafeFixtureFailsRedaction:
    """An unsafe fixture with unredacted content should fail redaction checks."""

    def test_unsafe_fixture_exists(self) -> None:
        assert UNSAFE_FIXTURE.is_file()

    def test_unsafe_fixture_has_unredacted_api_key(self) -> None:
        text = UNSAFE_FIXTURE.read_text(encoding="utf-8")
        matches = _check_unsafe(text)
        assert len(matches) >= 1, (
            "Expected at least 1 unsafe pattern match in unsafe fixture, got 0"
        )

    def test_unsafe_fixture_has_home_path(self) -> None:
        text = UNSAFE_FIXTURE.read_text(encoding="utf-8")
        assert "/home/" in text, "Unsafe fixture should contain an absolute home path"

    def test_unsafe_fixture_has_private_key(self) -> None:
        text = UNSAFE_FIXTURE.read_text(encoding="utf-8")
        assert "PRIVATE KEY" in text, (
            "Unsafe fixture should contain a private key marker"
        )


# ──────────────────────────────────────────────
# Safe fixture passes
# ──────────────────────────────────────────────


class TestSafeFixturePassesRedaction:
    """A safe fixture with all sensitive content redacted should pass."""

    def test_safe_fixture_exists(self) -> None:
        assert SAFE_FIXTURE.is_file()

    def test_safe_fixture_has_no_unredacted_patterns(self) -> None:
        text = SAFE_FIXTURE.read_text(encoding="utf-8")
        matches = _check_unsafe(text)
        assert len(matches) == 0, (
            f"Safe fixture should have 0 unsafe pattern matches, got {len(matches)}: {matches}"
        )

    def test_safe_fixture_has_redacted_placeholders(self) -> None:
        text = SAFE_FIXTURE.read_text(encoding="utf-8")
        placeholders = _check_safe_placeholders(text)
        assert len(placeholders) >= 2, (
            f"Safe fixture should have at least 2 redaction placeholders, "
            f"got {len(placeholders)}: {placeholders}"
        )

    def test_safe_fixture_uses_relative_paths(self) -> None:
        text = SAFE_FIXTURE.read_text(encoding="utf-8")
        # Should not contain absolute home paths
        assert "/home/" not in text, "Safe fixture should not contain absolute home paths"

    def test_safe_fixture_uses_tilde_for_home(self) -> None:
        text = SAFE_FIXTURE.read_text(encoding="utf-8")
        assert "~/" in text, "Safe fixture should use ~/ for home path"


# ──────────────────────────────────────────────
# Detection patterns
# ──────────────────────────────────────────────


class TestDetectionPatterns:
    """The detection patterns must correctly classify safe vs unsafe content."""

    def test_unsafe_content_flagged(self) -> None:
        unsafe_text = '{"apiKey": "abcd1234efgh5678"}'
        matches = _check_unsafe(unsafe_text)
        assert len(matches) >= 1, "Unsafe apiKey pattern should be detected"

    def test_safe_placeholder_not_flagged(self) -> None:
        safe_text = '{"apiKey": "[REDACTED_API_KEY]"}'
        matches = _check_unsafe(safe_text)
        assert len(matches) == 0, (
            f"Safe placeholder should not be flagged, got {matches}"
        )

    def test_empty_content_not_flagged(self) -> None:
        matches = _check_unsafe("")
        assert len(matches) == 0

    def test_redacted_placeholder_is_detected_as_safe(self) -> None:
        for placeholder in SAFE_PLACEHOLDERS:
            # Placeholder itself should not trigger unsafe patterns
            matches = _check_unsafe(placeholder)
            assert len(matches) == 0, (
                f"Placeholder '{placeholder}' should not trigger unsafe patterns, got {matches}"
            )


# ──────────────────────────────────────────────
# Deterministic output
# ──────────────────────────────────────────────


class TestDeterministicChecks:
    """Redaction checks must be deterministic."""

    def test_safe_fixture_always_passes(self) -> None:
        text = SAFE_FIXTURE.read_text(encoding="utf-8")
        for _ in range(3):
            matches = _check_unsafe(text)
            assert len(matches) == 0, "Safe fixture must deterministically pass"

    def test_unsafe_fixture_always_fails(self) -> None:
        text = UNSAFE_FIXTURE.read_text(encoding="utf-8")
        for _ in range(3):
            matches = _check_unsafe(text)
            assert len(matches) >= 1, "Unsafe fixture must deterministically fail"
