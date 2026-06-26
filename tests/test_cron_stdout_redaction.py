"""Tests for cron stdout/stderr secret redaction.

These tests verify that secret patterns are redacted before persistence
in the cron history database. The redaction function mirrors the scheduler's
own `agent.redact.redact_sensitive_text()`.

Run with: pytest tests/test_cron_stdout_redaction.py -v
"""

import sys
from pathlib import Path

import pytest


# ============================================================
# Redaction function (standalone, no agent.redact dependency)
# ============================================================

def redact_output(text: str) -> str:
    """Redact likely secrets from output text.

    This is a standalone implementation used in cron_history_writer.py
    to avoid importing from the Hermes agent package (which may not be
    available in standalone scripts).
    """
    import re

    if not text:
        return text

    patterns = [
        (r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?[a-z0-9_\-]{20,60}["\']?', r'\1=***REDACTED***'),
        (r'-----BEGIN\s+.+?KEY-----', '-----BEGIN REDACTED KEY-----'),
        (r'(?i)"password"\s*:\s*"[^"]{3,}"', '"password": "***REDACTED***"'),
        (r'https?://[^:@\s]+:[^@\s]+@', 'https://***:***@'),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


# ============================================================
# Redaction tests
# ============================================================

def test_redact_api_key():
    """An explicit API key string must be redacted."""
    text = 'api_key = "abcdef1234567890abcdef1234567890abcdef12"'
    redacted = redact_output(text)
    assert "abcdef1234567890abcdef1234567890abcdef12" not in redacted
    assert "***REDACTED***" in redacted


def test_redact_apikey():
    """apikey (no underscore) must also be redacted."""
    text = 'apikey: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"'
    redacted = redact_output(text)
    assert "***REDACTED***" in redacted


def test_redact_private_key():
    """Private key markers must be redacted."""
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
    redacted = redact_output(text)
    assert "RSA PRIVATE KEY" not in redacted, f"Key marker leaked: {redacted}"
    assert "REDACTED" in redacted.upper(), f"REDACTED not in output: {redacted}"


def test_redact_password_field():
    """JSON password fields must be redacted."""
    text = '"password": "mySecretPass123!"'
    redacted = redact_output(text)
    assert "mySecretPass123!" not in redacted
    assert '"***REDACTED***"' in redacted


def test_redact_url_credentials():
    """URLs with embedded credentials must be redacted."""
    text = "http://user:pass@example.com/api"
    redacted = redact_output(text)
    assert "user:pass@" not in redacted
    assert "***:***@" in redacted


def test_no_false_positive_normal_text():
    """Normal operational text must not be falsely redacted."""
    text = "Starting job 'test' at 2026-06-26 12:00:00 UTC"
    redacted = redact_output(text)
    assert redacted == text


def test_redact_short_password_not_redacted():
    """Short password-like strings (< 3 chars) should not trigger."""
    text = '"password": "ab"'
    redacted = redact_output(text)
    assert '"ab"' in redacted


# ============================================================
# Truncation tests (require cron_history_writer module)
# ============================================================

def test_truncate_long_output():
    """Output longer than MAX_EXCERPT_LENGTH must be truncated."""
    from orchestrator.scripts.cron_history_writer import MAX_EXCERPT_LENGTH
    text = "A" * (MAX_EXCERPT_LENGTH + 1000)
    from orchestrator.scripts.cron_history_writer import _truncate
    result = _truncate(text)
    assert len(result) <= MAX_EXCERPT_LENGTH
    assert result.endswith("...[truncated]")


def test_truncate_short_output():
    """Short outputs must not be truncated."""
    from orchestrator.scripts.cron_history_writer import _truncate
    text = "short output"
    result = _truncate(text)
    assert result == text


def test_truncate_exact_length():
    """Output at exactly MAX_EXCERPT_LENGTH must not be truncated."""
    from orchestrator.scripts.cron_history_writer import MAX_EXCERPT_LENGTH, _truncate
    text = "B" * MAX_EXCERPT_LENGTH
    result = _truncate(text)
    assert len(result) == MAX_EXCERPT_LENGTH
    assert "[truncated]" not in result
