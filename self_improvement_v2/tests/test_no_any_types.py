"""Test that no 'Any' types are used in the source code."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Patterns that indicate actual Any type usage (not in comments/docstrings)
ANY_USAGE_PATTERNS: list[str] = [
    r"from\s+typing\s+import\s+.*\bAny\b",
    r":\s*Any\b",
    r"\bAny\]",
    r"\bAny\s*\.",
    r"\[\s*Any\s*,",
    r"\[\s*Any\s*\]",
]


def _find_py_files() -> list[Path]:
    """Find all .py files in the self_improvement_v2 directory, excluding .venv*."""
    root = PROJECT_ROOT
    return sorted(
        p for p in root.rglob("*.py")
        if not any(part.startswith(".venv") for part in p.parts)
    )


def test_no_any_types() -> None:
    """No .py file should use typing.Any."""
    py_files = _find_py_files()
    violations: list[str] = []

    for py_file in py_files:
        # Skip test files themselves
        if "test_no_any_types" in str(py_file):
            continue

        content = py_file.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            # Skip comments and docstrings (simple heuristic)
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue

            for pattern in ANY_USAGE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

    assert len(violations) == 0, "Found typing.Any usage:\n" + "\n".join(violations)
