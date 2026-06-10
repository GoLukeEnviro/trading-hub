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
    r"cron apply",
    r"cron install",
    r"cron write",
    r"cron enable",
    r"cron disable",
    r"cron delete",
    r"cron reactivate",
]

# Patterns that are forbidden in *source* (src/) but allowed in tests.
FORBIDDEN_IN_SRC: list[str] = [
    r"docker exec",
]

# Patterns that should never appear anywhere (src + tests).
FORBIDDEN_IMPORTS: list[str] = [
    r"^import (requests|docker|telegram)\b",
    r"^from (requests|docker|telegram)\b",
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


@pytest.mark.parametrize("pattern", FORBIDDEN_IN_SRC)
def test_no_forbidden_patterns_in_src(pattern: str) -> None:
    """No *source* file should contain patterns forbidden in production code."""
    src_root = PROJECT_ROOT / "src"
    py_files = sorted(src_root.rglob("*.py"))
    regex = re.compile(pattern, re.IGNORECASE)
    violations: list[str] = []

    for py_file in py_files:
        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                # Skip self-check
                if "test_no_forbidden" in str(py_file):
                    continue
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

    assert len(violations) == 0, f"Forbidden pattern '{pattern}' found in src:\n" + "\n".join(violations)


@pytest.mark.parametrize("pattern", FORBIDDEN_IMPORTS)
def test_no_forbidden_imports(pattern: str) -> None:
    """No .py file should import forbidden network/library packages."""
    py_files = _find_py_files()
    regex = re.compile(pattern)
    violations: list[str] = []

    for py_file in py_files:
        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                if "test_no_forbidden" in str(py_file):
                    continue
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

    assert len(violations) == 0, f"Forbidden import '{pattern}' found:\n" + "\n".join(violations)
