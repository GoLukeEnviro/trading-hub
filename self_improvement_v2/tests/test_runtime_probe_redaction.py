"""Tests for fail-closed runtime-probe output redaction."""

from __future__ import annotations

import pytest

from si_v2.runtime_probe.redaction import RedactionFailure, build_sanitized_output_summary


def test_redacts_api_key_like_value() -> None:
    key_name = "_".join(["api", "key"])
    raw_output = f"{key_name}=ABCD1234EFGH5678IJKL9012"

    summary = build_sanitized_output_summary(raw_output)

    assert summary.redaction_applied is True
    assert summary.lines[0].text.endswith("[REDACTED_API_KEY]")


def test_redacts_exchange_secret_like_value() -> None:
    field_name = "_".join(["exchange", "secret"])
    raw_output = f"{field_name}: shh-super-sensitive-value"

    summary = build_sanitized_output_summary(raw_output)

    assert "[REDACTED_EXCHANGE_SECRET]" in summary.lines[0].text


def test_redacts_telegram_token_like_value() -> None:
    raw_output = "telegram status 123456789:AbCdEfGhIjKlMnOpQrStUvWx"

    summary = build_sanitized_output_summary(raw_output)

    assert summary.lines[0].text.endswith("[REDACTED_TELEGRAM_TOKEN]")


def test_redacts_credentials_in_urls() -> None:
    raw_output = "https://alice:opensesame@example.com/health?passphrase=hidden"

    summary = build_sanitized_output_summary(raw_output)

    assert "[REDACTED_CREDENTIALS]" in summary.lines[0].text
    assert "[REDACTED_QUERY_VALUE]" in summary.lines[0].text


def test_redacts_auth_headers() -> None:
    raw_output = "Authorization: Bearer abcdEFGH1234567890secret"

    summary = build_sanitized_output_summary(raw_output)

    assert summary.lines[0].text == "Authorization: [REDACTED_AUTH_HEADER]"


def test_redacts_cookies() -> None:
    raw_output = "Cookie: sessionid=abcd1234efgh5678ijkl9012"

    summary = build_sanitized_output_summary(raw_output)

    assert summary.lines[0].text == "Cookie: [REDACTED_COOKIE]"


def test_redacts_account_identifiers() -> None:
    raw_output = "account_id: acct-user-992341"

    summary = build_sanitized_output_summary(raw_output)

    assert "[REDACTED_ACCOUNT_IDENTIFIER]" in summary.lines[0].text


def test_redacts_high_entropy_strings() -> None:
    raw_output = "entropy zX83aBc91LmN45pQrT67uVwX89yZaBcd"

    summary = build_sanitized_output_summary(raw_output)

    assert summary.lines[0].text.endswith("[REDACTED_HIGH_ENTROPY]")


def test_redaction_fails_closed_when_sensitive_value_survives() -> None:
    raw_output = "Authorization: Digest still-sensitive-value"

    with pytest.raises(RedactionFailure):
        build_sanitized_output_summary(raw_output)
