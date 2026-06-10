"""Fail-closed redaction helpers for runtime-probe output summaries."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from si_v2.runtime_probe.models import RedactionSummary, RedactionSummaryLine


class RedactionFailureError(ValueError):
    """Raised when sensitive output cannot be safely redacted."""


RedactionFailure = RedactionFailureError


@dataclass(frozen=True)
class _ReplacementRule:
    pattern: re.Pattern[str]
    replacement: Callable[[re.Match[str]], str]


_SENSITIVE_NAME_FRAGMENT = (
    r"(?:api|access|secret|token|passphrase|pass|credential|auth|session|cookie|chat[_-]?id|account(?:[_-]?id)?|wallet)"
)
_SENSITIVE_QUERY_FRAGMENT = r"(?:key|secret|token|password|passphrase|credential|auth|cookie|session|chat[_-]?id)"
_PLACEHOLDER_PATTERN = re.compile(r"\[REDACTED_[A-Z_]+\]")
_ANY_AUTH_HEADER_PATTERN = re.compile(r"(?im)^authorization\s*:\s*.+$")
_AUTH_HEADER_PATTERN = re.compile(r"(?im)^(authorization)\s*:\s*(?:bearer|basic)\s+.+$")
_COOKIE_HEADER_PATTERN = re.compile(r"(?im)^(cookie|set-cookie)\s*:\s*.+$")
_TELEGRAM_TOKEN_PATTERN = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")
_URL_USERINFO_PATTERN = re.compile(r"\b(?P<scheme>https?|wss?)://(?P<userinfo>[^\s/@]+(?::[^\s/@]*)?)@")
_URL_SECRET_QUERY_PATTERN = re.compile(
    rf"(?P<prefix>[?&])(?P<name>[^=\s&#]*{_SENSITIVE_QUERY_FRAGMENT}[^=\s&#]*)=(?P<value>[^&#\s]+)",
    re.IGNORECASE,
)
_KEY_VALUE_PATTERN = re.compile(
    rf"(?P<key>[A-Za-z0-9_.-]*{_SENSITIVE_NAME_FRAGMENT}[A-Za-z0-9_.-]*)(?P<before_sep>\s*)(?P<sep>=|:)(?P<after_sep>\s*)(?P<value>\"[^\"]+\"|'[^']+'|[^\s,;]+)",
    re.IGNORECASE,
)
_PRIVATE_HOST_PATTERN = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})\b"
)
_ACCOUNT_ID_PATTERN = re.compile(
    r"\b(?:acct|account|user|chat)[_-]?(?:id|num|number)\b\s*(?:=|:)\s*[^\s,;]+",
    re.IGNORECASE,
)
_CANDIDATE_TOKEN_PATTERN = re.compile(r"\b[A-Za-z0-9+/=_-]{24,}\b")


_RULES: tuple[_ReplacementRule, ...] = (
    _ReplacementRule(
        pattern=_AUTH_HEADER_PATTERN,
        replacement=lambda match: f"{match.group(1)}: [REDACTED_AUTH_HEADER]",
    ),
    _ReplacementRule(
        pattern=_COOKIE_HEADER_PATTERN,
        replacement=lambda match: f"{match.group(1)}: [REDACTED_COOKIE]",
    ),
    _ReplacementRule(
        pattern=_TELEGRAM_TOKEN_PATTERN,
        replacement=lambda _match: "[REDACTED_TELEGRAM_TOKEN]",
    ),
    _ReplacementRule(
        pattern=_URL_USERINFO_PATTERN,
        replacement=lambda match: f"{match.group('scheme')}://[REDACTED_CREDENTIALS]@",
    ),
    _ReplacementRule(
        pattern=_URL_SECRET_QUERY_PATTERN,
        replacement=lambda match: f"{match.group('prefix')}{match.group('name')}=[REDACTED_QUERY_VALUE]",
    ),
    _ReplacementRule(
        pattern=_ACCOUNT_ID_PATTERN,
        replacement=lambda _match: "account_id=[REDACTED_ACCOUNT_IDENTIFIER]",
    ),
    _ReplacementRule(
        pattern=_PRIVATE_HOST_PATTERN,
        replacement=lambda _match: "[REDACTED_PRIVATE_HOST]",
    ),
    _ReplacementRule(
        pattern=_KEY_VALUE_PATTERN,
        replacement=lambda match: _redact_key_value(
            match.group("key"),
            match.group("before_sep"),
            match.group("sep"),
            match.group("after_sep"),
            match.group("value"),
        ),
    ),
)


def build_sanitized_output_summary(raw_output: str) -> RedactionSummary:
    """Return a typed sanitized summary or fail closed.

    The helper never returns partially redacted text. If a secret-like pattern
    survives the replacement pass, RedactionFailure is raised instead.
    """

    if raw_output == "":
        return RedactionSummary(
            line_count=0,
            redaction_count=0,
            redaction_applied=False,
            placeholders=[],
            lines=[],
        )

    sanitized_text = raw_output
    total_replacements = 0
    for rule in _RULES:
        sanitized_text, replacements = rule.pattern.subn(rule.replacement, sanitized_text)
        total_replacements += replacements

    sanitized_text, entropy_replacements = _replace_high_entropy_tokens(sanitized_text)
    total_replacements += entropy_replacements

    findings = _detect_unredacted_content(sanitized_text)
    if findings:
        detail = ", ".join(findings)
        msg = f"redaction failed for sensitive pattern(s): {detail}"
        raise RedactionFailure(msg)

    placeholders = sorted(set(_PLACEHOLDER_PATTERN.findall(sanitized_text)))
    lines = [
        RedactionSummaryLine(text=line, placeholders=_placeholders_for_line(line))
        for line in sanitized_text.splitlines()
        if line.strip()
    ]
    return RedactionSummary(
        line_count=len(lines),
        redaction_count=total_replacements,
        redaction_applied=total_replacements > 0,
        placeholders=placeholders,
        lines=lines,
    )


def _placeholders_for_line(line: str) -> list[str]:
    return sorted(set(_PLACEHOLDER_PATTERN.findall(line)))


def _redact_key_value(key: str, before_separator: str, separator: str, after_separator: str, value: str) -> str:
    if _PLACEHOLDER_PATTERN.fullmatch(value.strip("\"'")) is not None:
        return f"{key}{before_separator}{separator}{after_separator}{value}"
    placeholder = _placeholder_for_key(key)
    return f"{key}{before_separator}{separator}{after_separator}{placeholder}"


def _placeholder_for_key(key: str) -> str:
    lowered = key.lower()
    if "telegram" in lowered and ("token" in lowered or "chat" in lowered):
        if "chat" in lowered:
            return "[REDACTED_TELEGRAM_CHAT_ID]"
        return "[REDACTED_TELEGRAM_TOKEN]"
    if "cookie" in lowered or "session" in lowered:
        return "[REDACTED_COOKIE]"
    if "password" in lowered or "passphrase" in lowered or lowered.endswith("pass"):
        return "[REDACTED_CREDENTIAL]"
    if "account" in lowered or "wallet" in lowered or "chat_id" in lowered or "user_id" in lowered:
        return "[REDACTED_ACCOUNT_IDENTIFIER]"
    if "secret" in lowered:
        return "[REDACTED_EXCHANGE_SECRET]"
    if "auth" in lowered:
        return "[REDACTED_AUTH_HEADER]"
    if "token" in lowered:
        return "[REDACTED_API_KEY]"
    if "key" in lowered:
        return "[REDACTED_API_KEY]"
    return "[REDACTED_VALUE]"


def _replace_high_entropy_tokens(text: str) -> tuple[str, int]:
    replacements = 0
    parts: list[str] = []
    last_end = 0
    for match in _CANDIDATE_TOKEN_PATTERN.finditer(text):
        candidate_value = match.group(0)
        if _PLACEHOLDER_PATTERN.fullmatch(candidate_value) is not None:
            continue
        if _looks_high_entropy(candidate_value):
            parts.append(text[last_end : match.start()])
            parts.append("[REDACTED_HIGH_ENTROPY]")
            last_end = match.end()
            replacements += 1
    if replacements == 0:
        return text, 0
    parts.append(text[last_end:])
    return "".join(parts), replacements


def _looks_high_entropy(token: str) -> bool:
    if len(token) < 24:
        return False
    has_digit = any(character.isdigit() for character in token)
    has_alpha = any(character.isalpha() for character in token)
    if not has_digit or not has_alpha:
        return False
    if token.lower().startswith(("sha256", "commit", "candidate")):
        return False
    alphabet_size = len(set(token))
    if alphabet_size < 8:
        return False
    return _shannon_entropy(token) >= 3.5


def _shannon_entropy(token: str) -> float:
    length = len(token)
    frequencies = [token.count(character) / length for character in set(token)]
    return -sum(probability * math.log2(probability) for probability in frequencies)


def _detect_unredacted_content(text: str) -> list[str]:
    findings: list[str] = []
    if _has_unredacted_auth_header(text):
        findings.append("auth header")
    if _has_unredacted_cookie_header(text):
        findings.append("cookie header")
    if _TELEGRAM_TOKEN_PATTERN.search(text) is not None:
        findings.append("telegram token")
    if _has_unredacted_credential_url(text):
        findings.append("credential URL")
    if _has_unredacted_secret_query(text):
        findings.append("secret query")
    if _has_unredacted_account_identifier(text):
        findings.append("account identifier")
    if _has_unredacted_sensitive_assignment(text):
        findings.append("sensitive assignment")
    for match in _CANDIDATE_TOKEN_PATTERN.finditer(text):
        candidate_value = match.group(0)
        if _looks_high_entropy(candidate_value):
            findings.append("high entropy token")
            break
    return findings


def _has_unredacted_auth_header(text: str) -> bool:
    for match in _ANY_AUTH_HEADER_PATTERN.finditer(text):
        line = match.group(0).strip()
        if line != "Authorization: [REDACTED_AUTH_HEADER]" and line != "authorization: [REDACTED_AUTH_HEADER]":
            return True
    return False


def _has_unredacted_cookie_header(text: str) -> bool:
    return any("[REDACTED_COOKIE]" not in match.group(0) for match in _COOKIE_HEADER_PATTERN.finditer(text))


def _has_unredacted_credential_url(text: str) -> bool:
    for match in _URL_USERINFO_PATTERN.finditer(text):
        if "[REDACTED_CREDENTIALS]" not in match.group("userinfo"):
            return True
    return False


def _has_unredacted_secret_query(text: str) -> bool:
    for match in _URL_SECRET_QUERY_PATTERN.finditer(text):
        if _PLACEHOLDER_PATTERN.fullmatch(match.group("value")) is None:
            return True
    return False


def _has_unredacted_account_identifier(text: str) -> bool:
    return any("[REDACTED_ACCOUNT_IDENTIFIER]" not in match.group(0) for match in _ACCOUNT_ID_PATTERN.finditer(text))


def _has_unredacted_sensitive_assignment(text: str) -> bool:
    for match in _KEY_VALUE_PATTERN.finditer(text):
        value = match.group("value").strip("\"'")
        if _PLACEHOLDER_PATTERN.fullmatch(value) is None:
            return True
    return False
