"""Invariant tests: prove SI v2 cannot accidentally enable live trading.

These tests are structural/static checks against source code and configuration.
They do not require runtime, Docker, Freqtrade, or exchange connectivity.
Every test below must pass before any live-readiness discussion can begin.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import ClassVar

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
ALL_PY_FILES = list(PROJECT_ROOT.rglob("*.py"))
SRC_PY_FILES = list(SRC_DIR.rglob("*.py"))


# ──────────────────────────────────────────────
# Invariant 1: No dry_run=False in source
# ──────────────────────────────────────────────


def _find_dry_run_false_in_ast(filepath: Path) -> list[tuple[int, str]]:
    """Return (line_number, line_text) for any dry_run=False assignment."""
    text = filepath.read_text(encoding="utf-8")
    results: list[tuple[int, str]] = []
    try:
        tree = ast.parse(text, filename=str(filepath))
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "dry_run"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is False
                ):
                    lineno = getattr(node, "lineno", 0)
                    results.append((lineno, text.splitlines()[lineno - 1].strip()))
    return results


class TestDryRunInvariant:
    """No source file may contain dry_run=False."""

    def test_no_dry_run_false_in_source(self) -> None:
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            matches = _find_dry_run_false_in_ast(fp)
            for lineno, line in matches:
                failures.append(f"{fp}:{lineno}: {line}")
        assert not failures, (
            f"Found dry_run=False assignments in source ({len(failures)}):\n"
            + "\n".join(failures)
        )

    def test_no_dry_run_false_string_in_source(self) -> None:
        """Also check for the literal string 'dry_run=False' in source files."""
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "dry_run" in line and "False" in line and "dry_run=False" in line:
                    failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found dry_run=False string in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 2: No exchange credentials
# ──────────────────────────────────────────────


class TestExchangeCredentialInvariant:
    """No source file may contain exchange credential patterns."""

    EXCHANGE_CREDENTIAL_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"(?:api[_-]?key|api[_-]?secret|passphrase|wallet[_-]?address)\s*[=:]"),
        re.compile(r"(?:exchange|ccxt)\.(?:apiKey|secret|password)"),
        re.compile(r"(?:access[_-]?key|secret[_-]?key|private[_-]?key)\s*[=:]"),
    ]

    def test_no_exchange_credentials_in_source(self) -> None:
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for pat in self.EXCHANGE_CREDENTIAL_PATTERNS:
                    if pat.search(line):
                        failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found exchange credential patterns in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 3: No forcebuy / forcesell
# ──────────────────────────────────────────────


class TestForceTradeInvariant:
    """No source file may reference forcebuy or forcesell commands."""

    FORCE_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"\bforcebuy\b", re.IGNORECASE),
        re.compile(r"\bforcesell\b", re.IGNORECASE),
        re.compile(r"\bforce_entry\b", re.IGNORECASE),
        re.compile(r"\bforce_exit\b", re.IGNORECASE),
    ]

    def test_no_force_trade_in_source(self) -> None:
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                # Skip lines that are clearly string literals in forbidden-keys lists
                stripped = line.strip()
                if stripped.startswith(('"', "'", "#")):
                    continue
                for pat in self.FORCE_PATTERNS:
                    if pat.search(line):
                        failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found forcebuy/forcesell references in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 4: All adapters default to dry_run mode
# ──────────────────────────────────────────────


class TestAdapterModeInvariant:
    """Every adapter class must default to dry-run behaviour."""

    def test_dry_run_stub_config_is_dry_run(self) -> None:
        """DryRunStubDocker and DryRunStubFreqtrade return dry_run configs."""
        from si_v2.adapters.dry_run_stub import DryRunStubDocker, DryRunStubFreqtrade

        docker_stub = DryRunStubDocker()
        assert docker_stub.container_is_running("test") is True

        freqtrade_stub = DryRunStubFreqtrade()
        config = freqtrade_stub.read_config("test")
        assert config.get("dry_run") is True

    def test_real_adapters_require_env_var(self) -> None:
        """Real adapters cannot be instantiated without SI_V2_ENABLE_REAL_ADAPTERS=1."""
        import os

        from si_v2.adapters.audit import InMemoryAdapterAuditSink
        from si_v2.adapters.real_docker_adapter import RealDockerAdapter
        from si_v2.adapters.real_freqtrade_adapter import RealFreqtradeAdapter

        old = os.environ.pop("SI_V2_ENABLE_REAL_ADAPTERS") if "SI_V2_ENABLE_REAL_ADAPTERS" in os.environ else None

        sink = InMemoryAdapterAuditSink()
        with pytest.raises(RuntimeError, match="SI_V2_ENABLE_REAL_ADAPTERS"):
            RealDockerAdapter(sink)
        with pytest.raises(RuntimeError, match="SI_V2_ENABLE_REAL_ADAPTERS"):
            RealFreqtradeAdapter(sink)

        if old is not None:
            os.environ["SI_V2_ENABLE_REAL_ADAPTERS"] = old

    def test_telegram_adapter_is_protocol(self) -> None:
        """TelegramAdapter is a Protocol, not instantiable directly."""
        from typing import Protocol

        from si_v2.adapters.telegram_adapter import TelegramAdapter

        assert issubclass(TelegramAdapter, Protocol)

    def test_no_real_telegram_adapter_import(self) -> None:
        """No source file may import Telegram bot credentials or real telegram."""
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "telegram.ext" in line or "python-telegram-bot" in line:
                    failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found real telegram imports in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 5: No real adapter imports in pipeline src
# ──────────────────────────────────────────────


class TestRealAdapterImportInvariant:
    """Pipeline code must not import real adapter implementations."""

    REAL_ADAPTER_MODULES: ClassVar[list[str]] = [
        "si_v2.adapters.real_docker_adapter",
        "si_v2.adapters.real_freqtrade_adapter",
    ]

    def _find_imports(self, filepath: Path) -> list[str]:
        """Return list of real adapter import strings found in file."""
        text = filepath.read_text(encoding="utf-8")
        found: list[str] = []
        try:
            tree = ast.parse(text, filename=str(filepath))
        except SyntaxError:
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for mod in self.REAL_ADAPTER_MODULES:
                        if alias.name == mod or alias.name.startswith(mod + "."):
                            found.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                    for mod in self.REAL_ADAPTER_MODULES:
                        if node.module == mod or node.module.startswith(mod + "."):
                            names = [a.name for a in node.names]
                            found.append(f"from {node.module} import {', '.join(names)}")
        return found

    def test_no_real_adapter_imports_in_pipeline_src(self) -> None:
        """Pipeline pipeline/decision code must not import real adapters."""
        pipeline_src = SRC_DIR / "si_v2" / "propose"
        pipeline_files = list(pipeline_src.rglob("*.py"))
        pipeline_files += list((SRC_DIR / "si_v2" / "episode").rglob("*.py"))
        pipeline_files += list((SRC_DIR / "si_v2" / "analyze").rglob("*.py"))
        pipeline_files += list((SRC_DIR / "si_v2" / "backtest").rglob("*.py"))

        failures: list[str] = []
        for fp in pipeline_files:
            imports = self._find_imports(fp)
            for imp in imports:
                failures.append(f"{fp}: {imp}")
        assert not failures, (
            f"Pipeline code imports real adapters ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 6: No shell=True or subprocess with shell
# ──────────────────────────────────────────────


class TestShellInvariant:
    """No source file may use shell=True in subprocess calls."""

    SHELL_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"shell\s*=\s*True"),
        re.compile(r"shell\s*=\s*true"),
    ]

    def test_no_shell_true_in_source(self) -> None:
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for pat in self.SHELL_PATTERNS:
                    if pat.search(line):
                        failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found shell=True in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 7: No live-trading state machine bypass
# ──────────────────────────────────────────────


class TestLiveStateInvariant:
    """Prove the LIVE_FORBIDDEN default is never overridden to LIVE_APPROVED in code."""

    def test_no_live_approved_in_source(self) -> None:
        """Literal LIVE_APPROVED state may only appear in tests or governance docs."""
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "LIVE_APPROVED" in line:
                    failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found LIVE_APPROVED in source ({len(failures)}):\n"
            + "\n".join(failures)
        )

    def test_no_live_active_in_source(self) -> None:
        """Literal LIVE_ACTIVE state may only appear in tests or governance docs."""
        failures: list[str] = []
        for fp in SRC_PY_FILES:
            text = fp.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "LIVE_ACTIVE" in line:
                    failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Found LIVE_ACTIVE in source ({len(failures)}):\n"
            + "\n".join(failures)
        )


# ──────────────────────────────────────────────
# Invariant 8: No deployment or cron-modifying code in pipeline
# ──────────────────────────────────────────────


class TestDeploymentInvariant:
    """Pipeline code must not contain deployment or cron commands."""

    DEPLOYMENT_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"\b(?:deploy|rollout|promote)\b", re.IGNORECASE),
    ]

    # These are allowed in the deploy module itself
    ALLOWED_DEPLOY_DIRS: ClassVar[set[str]] = {"deploy"}

    def test_no_deployment_calls_in_pipeline(self) -> None:
        """Pipeline code (propose, analyze, backtest, episode) must not deploy."""
        pipeline_dirs = ["propose", "analyze", "backtest", "episode", "observe"]
        failures: list[str] = []
        for dirname in pipeline_dirs:
            dirpath = SRC_DIR / "si_v2" / dirname
            if not dirpath.exists():
                continue
            for fp in dirpath.rglob("*.py"):
                text = fp.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), 1):
                    for pat in self.DEPLOYMENT_PATTERNS:
                        if pat.search(line) and not line.strip().startswith("#"):
                            failures.append(f"{fp}:{lineno}: {line.strip()}")
        assert not failures, (
            f"Pipeline code contains deployment references ({len(failures)}):\n"
            + "\n".join(failures)
        )
