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
    r":\s*Any\b",          # Any type annotations (must use concrete types)
    r"shell\s*=\s*True",   # shell=True in subprocess (security risk)
]

# Patterns that should never appear anywhere (src + tests).
FORBIDDEN_IMPORTS: list[str] = [
    r"^import (requests|docker|telegram)\b",
    r"^from (requests|docker|telegram)\b",
]


def _find_py_files() -> list[Path]:
    """Find all .py files in the self_improvement_v2 directory, excluding .venv."""
    root = PROJECT_ROOT
    return sorted(
        p for p in root.rglob("*.py")
        if ".venv" not in p.parts
    )


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
                # Allow test files that assert safety documentation contains patterns
                if py_file.name in (
                    "test_controlled_dry_run_rehearsal_runbook.py",
                    "test_human_approval_gate_checklist.py",
                    "test_live_readiness_blocker_inventory.py",
                ):
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


def test_no_any_in_source_types() -> None:
    """Verify no source file uses bare 'Any' in type annotations."""
    src_root = PROJECT_ROOT / "src"
    py_files = sorted(src_root.rglob("*.py"))
    regex = re.compile(r":\s*Any\b")
    violations: list[str] = []

    for py_file in py_files:
        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if regex.search(stripped):
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {stripped}")

    assert len(violations) == 0, "Found 'Any' type annotations in src (use concrete types):\n" + "\n".join(violations)


def test_no_shell_true_in_src() -> None:
    """Verify no source file uses shell=True in subprocess calls."""
    src_root = PROJECT_ROOT / "src"
    py_files = sorted(src_root.rglob("*.py"))
    regex = re.compile(r"shell\s*=\s*True")
    violations: list[str] = []

    for py_file in py_files:
        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if regex.search(stripped):
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {stripped}")

    assert len(violations) == 0, "Found 'shell=True' in src (security risk):\n" + "\n".join(violations)
