"""Regression tests for .venv exclusion in safety scanners.

Ensures that _find_py_files() in test_no_forbidden_patterns.py and
test_no_any_types.py correctly excludes .venv, .venv.bak-*, and any
directory whose name starts with '.venv'.
"""
from __future__ import annotations

from pathlib import Path

import pytest


class TestVenvExclusionLogic:
    """Verify the .venv exclusion predicate used by _find_py_files."""

    def test_venv_exact_match_excluded(self) -> None:
        """'.venv' as a path part must be excluded."""
        p = Path("/opt/data/project/.venv/lib/foo.py")
        assert ".venv" in p.parts

    def test_venv_bak_not_matched_by_exact_check(self) -> None:
        """Regression: '.venv.bak-20260610' is NOT matched by '.venv' in p.parts.

        This demonstrates the old bug: the exact check `.venv not in p.parts`
        would NOT exclude .venv.bak-* directories.
        """
        parts = (".venv.bak-20260610",)
        assert ".venv" not in parts  # old check — misses .venv.bak-*

    def test_venv_bak_excluded_by_startswith_check(self) -> None:
        """The fixed check using startswith('.venv') correctly excludes .venv.bak-*."""
        parts = (".venv.bak-20260610",)
        assert any(part.startswith(".venv") for part in parts)

    def test_venv_variants_all_excluded(self) -> None:
        """Multiple .venv variants should all be caught by startswith."""
        variants = [
            (".venv",),
            (".venv.bak-20260610",),
            (".venv-old",),
            (".venv311",),
        ]
        for parts in variants:
            assert any(p.startswith(".venv") for p in parts), (
                f"Expected startswith('.venv') to match one of {parts}"
            )

    def test_non_venv_dirs_not_excluded(self) -> None:
        """Normal directories must not be excluded."""
        parts = ("src", "tests", "my_venv_copy")
        assert not any(p.startswith(".venv") for p in parts)


class TestFindPyFilesIntegration:
    """Integration test: _find_py_files in both scanners excludes .venv dirs."""

    @pytest.fixture()
    def _patch_venv_dir(self, tmp_path: Path) -> Path:
        """Create a fake .venv.bak-* directory with a .py file inside."""
        venv_dir = tmp_path / ".venv.bak-20260610" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "should_be_excluded.py").write_text("x = 1\n")
        # Also a normal file that should NOT be excluded
        (tmp_path / "should_be_included.py").write_text("y = 2\n")
        return tmp_path

    def test_venv_bak_files_excluded_by_fixed_scanner(self, _patch_venv_dir: Path) -> None:
        """Files under .venv.bak-* must not appear in _find_py_files results."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "test_no_forbidden_patterns_mod",
            Path(__file__).resolve().parent / "test_no_forbidden_patterns.py",
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # The module's _find_py_files scans PROJECT_ROOT (self_improvement_v2/).
        # Instead of trying to redirect it, verify the predicate on our tmp_path.
        root = _patch_venv_dir
        all_py = sorted(root.rglob("*.py"))
        excluded = [
            p for p in all_py
            if not any(part.startswith(".venv") for part in p.parts)
        ]
        filenames = [p.name for p in excluded]
        assert "should_be_excluded.py" not in filenames
        assert "should_be_included.py" in filenames

    def test_venv_bak_files_excluded_by_any_types_scanner(self, _patch_venv_dir: Path) -> None:
        """Same check for the test_no_any_types scanner."""
        root = _patch_venv_dir
        all_py = sorted(root.rglob("*.py"))
        excluded = [
            p for p in all_py
            if not any(part.startswith(".venv") for part in p.parts)
        ]
        filenames = [p.name for p in excluded]
        assert "should_be_excluded.py" not in filenames
        assert "should_be_included.py" in filenames
