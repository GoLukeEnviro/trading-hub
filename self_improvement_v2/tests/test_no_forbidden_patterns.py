"""Test that no forbidden patterns exist in the source code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_PATTERNS: list[str] = [
    r"dry_run\s*=\s*False",
    r"proposal_only\s*=\s*False",
    r"docker restart",
    r"docker stop",
    r"docker start",
    r"compose up",
    r"compose down",
    r"chmod -R",
    r"chown -R",
    r"rm -rf",
    r"api_key\s*[=:]",
    r"secret\s*=",
    r"password\s*=",
    r"token\s*=",
]


def _find_py_files() -> list[Path]:
    """Find all .py files in the self_improvement_v2 directory."""
    root = PROJECT_ROOT
    return sorted(root.rglob("*.py"))


@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS)
def test_no_forbidden_patterns(pattern: str) -> None:
    """No .py file should contain forbidden patterns."""
    py_files = _find_py_files()
    regex = re.compile(pattern, re.IGNORECASE)
    violations: list[str] = []

    for py_file in py_files:
        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                # Allow in test files that check for patterns as strings
                if "test_no_forbidden" in str(py_file):
                    continue
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

    assert len(violations) == 0, f"Forbidden pattern '{pattern}' found:\n" + "\n".join(violations)
