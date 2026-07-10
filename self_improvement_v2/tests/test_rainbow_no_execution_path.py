"""Guard tests proving no Rainbow-to-execution path exists.

Verifies:
- Rainbow modules do not import execution modules
- candidate_quality helper remains pure (no I/O, no network)
- no direct file write in the quality evaluator
- no network call in candidate ranking
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAINBOW_SRC = Path(__file__).resolve().parent.parent / "src" / "si_v2" / "rainbow"
EXECUTION_MODULES = [
    "apply_actuator",
    "live",
    "rollout",
    "docker",
    "cron",
    "scheduler",
]


def _get_rainbow_py_files() -> list[Path]:
    """Get all .py files in the rainbow package."""
    return sorted(RAINBOW_SRC.rglob("*.py"))


class TestRainbowNoExecutionPath:
    """Prove no code path exists from Rainbow to execution."""

    def test_rainbow_does_not_import_execution_modules(self) -> None:
        """Rainbow modules must not import execution modules."""
        for py_file in _get_rainbow_py_files():
            content = py_file.read_text()
            for mod in EXECUTION_MODULES:
                if f"import {mod}" in content or f"from {mod}" in content:
                    pytest.fail(
                        f"{py_file.relative_to(RAINBOW_SRC.parent.parent)} "
                        f"imports execution module '{mod}'"
                    )

    def test_rainbow_does_not_import_primo_signal_state(self) -> None:
        """Rainbow modules must not reference primo_signal_state.json."""
        for py_file in _get_rainbow_py_files():
            content = py_file.read_text()
            if "primo_signal_state" in content:
                pytest.fail(
                    f"{py_file.relative_to(RAINBOW_SRC.parent.parent)} "
                    f"references primo_signal_state"
                )

    def test_rainbow_does_not_import_execute_apply(self) -> None:
        """Rainbow modules must not reference execute_apply."""
        for py_file in _get_rainbow_py_files():
            content = py_file.read_text()
            if "execute_apply" in content:
                pytest.fail(
                    f"{py_file.relative_to(RAINBOW_SRC.parent.parent)} "
                    f"references execute_apply"
                )

    def test_rainbow_does_not_import_canary_restart(self) -> None:
        """Rainbow modules must not reference canary restart functions."""
        for py_file in _get_rainbow_py_files():
            content = py_file.read_text()
            if "run_canary_restart" in content or "execute_canary_rollback" in content:
                pytest.fail(
                    f"{py_file.relative_to(RAINBOW_SRC.parent.parent)} "
                    f"references canary restart/rollback"
                )

    def test_candidate_quality_is_pure(self) -> None:
        """candidate_quality.py must not do I/O, network, or file writes."""
        quality_path = RAINBOW_SRC / "candidate_quality.py"
        content = quality_path.read_text()
        forbidden = ["open(", "urlopen", "httpx", "requests", "subprocess", "sqlite3"]
        for pattern in forbidden:
            if pattern in content:
                pytest.fail(
                    f"candidate_quality.py contains forbidden I/O pattern: {pattern}"
                )

    def test_candidate_quality_no_network(self) -> None:
        """candidate_quality.py must not make network calls."""
        quality_path = RAINBOW_SRC / "candidate_quality.py"
        content = quality_path.read_text()
        for pattern in ["http://", "https://", "socket", "connect"]:
            if pattern in content:
                pytest.fail(
                    f"candidate_quality.py contains network pattern: {pattern}"
                )
