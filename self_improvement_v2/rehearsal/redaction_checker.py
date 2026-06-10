"""Rehearsal artifact redaction checker (#146).

Scans rehearsal artifact text for unredacted sensitive content
(API keys, secrets, private keys, wallet addresses, tokens,
internal IPs, absolute home/deployment paths) using the policy
defined in ``security/rehearsal_artifact_redaction_policy.md``.

Usage::

    from rehearsal.redaction_checker import RedactionChecker

    checker = RedactionChecker()
    findings = checker.check_artifact("some text with code=abc123")
    # → list[Finding]  (sorted deterministically)
"""

from __future__ import annotations

import re
from typing import ClassVar

from rehearsal.planning_models import Finding, ReasonCode, Severity, Verdict


class RedactionChecker:
    """Deterministic redaction checker for rehearsal artifacts.

    Attributes
    ----------
    BLOCKER_PATTERNS : ClassVar[list[tuple[str, str, str]]]
        Patterns that **must** be redacted. Each tuple is
        ``(name, regex, reason_code)`` where *name* is a short label,
        *regex* is the compiled-pattern string, and *reason_code* is the
        ``ReasonCode`` value (as a string) to use in the ``Finding``.
    WARNING_PATTERNS : ClassVar[list[tuple[str, str, str]]]
        Patterns that trigger a ``WARNING`` (YELLOW) finding rather
        than ``BLOCKED``.  Currently this covers absolute paths.
    """

    BLOCKER_PATTERNS: ClassVar[list[tuple[str, str, str]]] = [
        # R-01
        ("api_key", r"api[_-]?key", "UNSAFE_CONTENT"),
        # R-02
        ("api_secret", r"api[_-]?secret", "UNSAFE_CONTENT"),
        # R-03
        ("passphrase", r"passphrase", "UNSAFE_CONTENT"),
        # R-04 — wallet address (0x + 40 hex chars)
        ("wallet_address", r"0x[a-fA-F0-9]{40}", "UNSAFE_CONTENT"),
        # R-05 — private key block (BEGIN line)
        ("private_key", r"-----BEGIN.*PRIVATE KEY-----", "UNSAFE_CONTENT"),
        # R-06 — bot / discord token
        ("bot_token", r"[0-9]{8,10}:[a-zA-Z0-9_-]{35}", "UNSAFE_CONTENT"),
        # R-07 — home directory path
        ("home_path", r"/home/.*?/projects/", "UNSAFE_PATH"),
        # R-08 — deploy path
        ("deploy_path", r"/opt/data/", "UNSAFE_PATH"),
        # R-09 — internal IP 192.168.x.x
        ("internal_ip_192", r"192\.168\.", "UNSAFE_PATH"),
        # R-10 — internal IP 10.x.x.x
        ("internal_ip_10", r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}", "UNSAFE_PATH"),
    ]

    WARNING_PATTERNS: ClassVar[list[tuple[str, str, str]]] = [
        # Absolute paths (catch-all — /home/ or /opt/data/ are already
        # caught by BLOCKER_PATTERNS, but more generic absolute paths
        # trigger a warning)
        ("absolute_path", r"/(?:home|opt|data|tmp|var|etc|usr|root)", "UNSAFE_PATH"),
    ]

    # Regex that describes a safe [REDACTED_*] placeholder
    _REDACTED_PLACEHOLDER_RE: ClassVar[re.Pattern] = re.compile(
        r"\[REDACTED_[A-Z_]+\]"
    )

    # Section header marker for "Forbidden Conditions"
    _FORBIDDEN_SECTION_RE: ClassVar[re.Pattern] = re.compile(
        r"^##\s+\d+\.\s+Forbidden Conditions",
        re.MULTILINE | re.IGNORECASE,
    )

    # Approximate end-of-section boundary (next ## heading or end-of-string)
    _SECTION_END_RE: ClassVar[re.Pattern] = re.compile(
        r"^##\s+\d+\.\s+",
        re.MULTILINE,
    )

    def __init__(self) -> None:
        # Pre-compile patterns
        self._blocker_regexes: list[tuple[str, re.Pattern, ReasonCode]] = []
        for name, pat_str, rc_str in self.BLOCKER_PATTERNS:
            rc = ReasonCode(rc_str)
            self._blocker_regexes.append((name, re.compile(pat_str), rc))

        self._warning_regexes: list[tuple[str, re.Pattern, ReasonCode]] = []
        for name, pat_str, rc_str in self.WARNING_PATTERNS:
            rc = ReasonCode(rc_str)
            self._warning_regexes.append((name, re.compile(pat_str), rc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_artifact(self, text: str) -> list[Finding]:
        """Scan *text* for unredacted sensitive content.

        Returns a deterministic list of ``Finding`` instances sorted
        by ``reason_code`` (stable-sort order).

        Parameters
        ----------
        text : str
            The raw text of a rehearsal artifact.

        Returns
        -------
        list[Finding]
            Zero or more findings.  An empty list means the artifact
            is clean (``PASS``).
        """
        findings: list[Finding] = []

        # Determine safe regions: [REDACTED_*] placeholders
        safe_regions: set[tuple[int, int]] = set()
        for m in self._REDACTED_PLACEHOLDER_RE.finditer(text):
            safe_regions.add((m.start(), m.end()))

        # Determine safe regions: within "Forbidden Conditions" sections
        for m in self._FORBIDDEN_SECTION_RE.finditer(text):
            section_start = m.start()
            # Find the next heading boundary
            next_section = self._SECTION_END_RE.search(text, section_start + 1)
            section_end = next_section.start() if next_section else len(text)
            safe_regions.add((section_start, section_end))

        # Helper: is a given span safe?
        def _is_safe(start: int, end: int) -> bool:
            return any(start >= s_start and end <= s_end for s_start, s_end in safe_regions)

        # --- BLOCKER checks ---
        for name, pattern, rc in self._blocker_regexes:
            for m in pattern.finditer(text):
                if _is_safe(m.start(), m.end()):
                    continue
                # Determine severity and verdict
                if rc in (ReasonCode.UNSAFE_PATH,):
                    sev = Severity.MAJOR
                    verd = Verdict.WARNING
                else:
                    sev = Severity.BLOCKER
                    verd = Verdict.BLOCKED

                snippet = text[max(0, m.start() - 20) : m.end() + 20]
                evidence = f"Matched pattern '{name}' at position {m.start()}: ...{snippet}..."

                findings.append(
                    Finding(
                        reason_code=rc,
                        severity=sev,
                        verdict=verd,
                        message=f"Unredacted sensitive content: '{name}' pattern found",
                        check_id=f"RC-{rc.value}-{name}",
                        field_path="artifact_text",
                        evidence=evidence,
                        remediation=(
                            f"Replace the matched text with [REDACTED_{name.upper()}] "
                            "or ensure it is inside a [REDACTED_*] placeholder"
                        ),
                    )
                )

        # --- WARNING checks (absolute paths not caught above) ---
        for name, pattern, rc in self._warning_regexes:
            for m in pattern.finditer(text):
                if _is_safe(m.start(), m.end()):
                    continue
                snippet = text[max(0, m.start() - 20) : m.end() + 20]

                findings.append(
                    Finding(
                        reason_code=rc,
                        severity=Severity.MINOR,
                        verdict=Verdict.WARNING,
                        message=f"Absolute path detected: '{name}' pattern found",
                        check_id=f"RC-{rc.value}-{name}",
                        field_path="artifact_text",
                        evidence=f"Matched at position {m.start()}: ...{snippet}...",
                        remediation=(
                            "Replace absolute path with a relative path or "
                            "[REDACTED_PATH] placeholder"
                        ),
                    )
                )

        # Deterministic sort: by reason_code, then check_id
        findings.sort(key=lambda f: (f.reason_code.value, f.check_id))
        return findings

    def _check_has_redactions(self, text: str) -> bool:
        """Return ``True`` if *text* contains at least one ``[REDACTED_*]`` placeholder."""
        return bool(self._REDACTED_PLACEHOLDER_RE.search(text))
