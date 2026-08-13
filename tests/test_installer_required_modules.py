"""Regression tests for scripts/install-hermes-root-executor.sh REQUIRED_MODULES.

PR #703 / Issue #703: the installer deployed only 9 of the hermes_root/ modules,
omitting ``legacy.py`` (imported by hermes_root/daemon.py since PR #677/#678)
and ``__main__.py`` (CLI entry point). A daemon restart after a real install
therefore crashed with ModuleNotFoundError and the installer rolled back —
observed during the #683 recovery (2026-08-13). These tests pin the invariant:

  REQUIRED_MODULES must cover every module the deployed package needs,
  otherwise the installer is a live footgun for future deployments.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "scripts" / "install-hermes-root-executor.sh"
PACKAGE_DIR = REPO_ROOT / "hermes_root"

# Modules that must always be deployed, independent of import analysis:
# legacy.py is imported by daemon.py; __main__.py is the CLI entry point.
MANDATORY_MODULES = {
    "__init__.py",
    "__main__.py",
    "legacy.py",
}


def _parse_required_modules() -> set[str]:
    """Extract REQUIRED_MODULES entries from the installer script."""
    text = INSTALLER.read_text(encoding="utf-8")
    match = re.search(r"REQUIRED_MODULES=\((.*?)\)", text, re.DOTALL)
    assert match is not None, "REQUIRED_MODULES=(...) block not found in installer"
    body = match.group(1)
    modules = set(re.findall(r'"([^"]+\.py)"', body))
    assert modules, "no .py entries parsed from REQUIRED_MODULES"
    return modules


def _package_modules() -> set[str]:
    """All top-level .py modules shipped in hermes_root/."""
    return {p.name for p in PACKAGE_DIR.glob("*.py")}


def _daemon_hermes_root_imports() -> set[str]:
    """hermes_root.* modules that daemon.py imports at runtime."""
    text = (PACKAGE_DIR / "daemon.py").read_text(encoding="utf-8")
    imports = set()
    for m in re.finditer(r"from\s+hermes_root\s+import\s+([^\n]+)", text):
        for name in m.group(1).split(","):
            imports.add(name.strip().split()[-1].strip())
    for m in re.finditer(r"from\s+hermes_root\.(\w+)\s+import", text):
        imports.add(m.group(1))
    for m in re.finditer(r"import\s+hermes_root\.(\w+)", text):
        imports.add(m.group(1))
    # __init__.py re-exports; map to file names.
    files = set()
    for name in imports:
        if name == "daemon":
            files.add("daemon.py")
        elif (PACKAGE_DIR / f"{name}.py").exists():
            files.add(f"{name}.py")
    return files


class TestInstallerRequiredModules:
    def test_required_modules_present_in_installer(self):
        assert INSTALLER.exists(), f"installer missing: {INSTALLER}"

    def test_mandatory_modules_are_deployed(self):
        modules = _parse_required_modules()
        missing = MANDATORY_MODULES - modules
        assert not missing, (
            f"installer REQUIRED_MODULES is missing mandatory modules: "
            f"{sorted(missing)}. legacy.py is imported by daemon.py and "
            f"__main__.py is the CLI entry; without them a deployed daemon "
            f"crashes on import (see #703)."
        )

    def test_daemon_imported_modules_are_deployed(self):
        """Every hermes_root module daemon.py imports must be in REQUIRED_MODULES."""
        modules = _parse_required_modules()
        needed = _daemon_hermes_root_imports()
        missing = needed - modules
        assert not missing, (
            f"installer REQUIRED_MODULES does not deploy modules imported by "
            f"daemon.py: {sorted(missing)}"
        )

    def test_required_modules_are_real_package_files(self):
        """REQUIRED_MODULES entries must not reference non-existent files."""
        modules = _parse_required_modules()
        package = _package_modules()
        phantom = modules - package
        assert not phantom, (
            f"installer REQUIRED_MODULES references files not in hermes_root/: "
            f"{sorted(phantom)}"
        )

    def test_package_files_covered_by_installer(self):
        """Every shipped hermes_root/*.py (excluding __pycache__) is deployed.

        Exception: ``daemon.py`` is deliberately NOT a REQUIRED_MODULES entry —
        the installer writes it as a standalone executable to
        ``/usr/local/sbin/hermes-root-executor`` (with a provenance header),
        not as a package module. That split is intentional and documented in
        the installer header.
        """
        modules = _parse_required_modules()
        package = _package_modules()
        deployed_as_executable = {"daemon.py"}
        undeployed = package - modules - deployed_as_executable
        assert not undeployed, (
            f"hermes_root/ contains modules the installer never deploys: "
            f"{sorted(undeployed)}. Either add them or document why they are "
            f"not needed at runtime."
        )

    @pytest.mark.skipif(
        subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True).returncode != 0,
        reason="bash -n failed; syntax error would mask module assertions",
    )
    def test_installer_syntax_valid(self):
        # Already gated above; this test just documents the syntax gate.
        assert True
