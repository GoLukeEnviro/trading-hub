"""Secret redaction for executor client output.

Redacts credential-like patterns before local display or report generation.
Never modifies the original response — only produces a safe copy for output.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate a value might be a secret
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth|credential|private[_-]?key)",
)

# Mask for redacted values
REDACTED = "[REDACTED]"


def _is_secret_key(key: str) -> bool:
    """Check if a key name looks like it holds a secret."""
    return bool(_SECRET_KEY_RE.search(key))


def redact_value(key: str, value: Any) -> Any:
    """Redact a single value if its key matches a secret pattern."""
    if _is_secret_key(str(key)):
        return REDACTED
    if isinstance(value, str) and len(value) > 40 and _looks_like_token(value):
        return REDACTED
    return value


def _looks_like_token(value: str) -> bool:
    """Heuristic: long base64/hex strings are likely tokens."""
    if len(value) < 40:
        return False
    # Check if mostly base64 or hex characters
    b64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    hex_chars = set("0123456789abcdefABCDEF")
    chars = set(value)
    if chars.issubset(b64_chars) and len(value) >= 40:
        return True
    if chars.issubset(hex_chars) and len(value) >= 40:
        return True
    return False


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact secret-like values from a dict."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_key(key):
            result[key] = REDACTED
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(item) if isinstance(item, dict) else redact_value(key, item)
                for item in value
            ]
        else:
            result[key] = redact_value(key, value)
    return result


_SECRET_KEY_FRAGMENT = (
    r"[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|API[_-]?KEY|"
    r"PRIVATE[_-]?KEY|ACCESS[_-]?KEY|AUTH|CREDENTIAL)[A-Za-z0-9_]*"
)

# Credential shapes that are secrets regardless of the surrounding key name.
_TOKEN_SHAPE_RE = re.compile(
    r"\b(?:ghp|gho|ghs|ghr|ghu)_[A-Za-z0-9]{20,}\b"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_JSON_KV_RE = re.compile(rf'(?i)("(?:{_SECRET_KEY_FRAGMENT})"\s*:\s*)"[^"]*"')
_YAML_KV_RE = re.compile(rf"(?im)^(\s*{_SECRET_KEY_FRAGMENT}\s*:\s*).+$")
_ENV_KV_RE = re.compile(rf"(?im)^(\s*{_SECRET_KEY_FRAGMENT}\s*=\s*).+$")


def redact_text_output(value: str) -> str:
    """Redact secret-like content from free-text command output
    (stdout/stderr), e.g. a rendered docker-compose config or environment
    dump. Unlike redact_dict/redact_argv (structured data with known key
    boundaries), this operates on arbitrary text, so it combines known
    credential *shapes* (GitHub PAT/token prefixes, Bearer headers) with
    key=value / "key": value / key: value patterns for secret-like key
    names. Applied unconditionally at the daemon response boundary and
    again at the client boundary — no debug bypass, no raw-output flag.
    """
    if not value:
        return value

    text = _TOKEN_SHAPE_RE.sub(REDACTED, value)
    text = _BEARER_RE.sub(r"\1" + REDACTED, text)
    text = _JSON_KV_RE.sub(r"\1" + f'"{REDACTED}"', text)
    text = _YAML_KV_RE.sub(r"\1" + REDACTED, text)
    text = _ENV_KV_RE.sub(r"\1" + REDACTED, text)
    return text


def redact_argv(argv: list[str]) -> list[str]:
    """Redact secret-like arguments from an argv list.

    Redacts any argument that contains '=' followed by a long token-like string,
    or matches known secret patterns like --api-key=..., -e KEY=..., etc.
    """
    result: list[str] = []
    for arg in argv:
        if "=" in arg:
            key, _, val = arg.partition("=")
            if _is_secret_key(key.lstrip("-")):
                result.append(f"{key}={REDACTED}")
                continue
            if _looks_like_token(val):
                result.append(f"{key}={REDACTED}")
                continue
        result.append(arg)
    return result
