"""Safety regressions for the full SI v2 pipeline.

Verifies that no real adapters, non-localhost URLs, jobs.json writes,
live strategy writes, or env secret reads exist in the pipeline code.
"""

from __future__ import annotations

from pathlib import Path


def _src_files() -> list[Path]:
    """Return all Python source files in the pipeline src directory."""
    repo = Path(__file__).resolve().parent.parent / "self_improvement_v2"
    return list((repo / "src").rglob("*.py"))


def _read_file(path: Path) -> str:
    """Read file content as text."""
    return path.read_text(encoding="utf-8")


class TestPipelineSafety:
    """Safety regressions for the full pipeline."""

    def test_no_real_adapter_imports(self) -> None:
        """Verify no real Docker/Freqtrade/Telegram/ai4trade imports in pipeline src."""
        files = _src_files()

        forbidden_imports = [
            "import docker",
            "from docker import",
            "from freqtrade",
            "import freqtrade",
            "import telepot",
            "from telepot",
            "import telegram",
            "from telegram",
            "import requests",
            "from requests",
            "import httpx",
            "from httpx",
            "import urllib",
            "from urllib",
            "import websocket",
            "from websocket",
            "import ccxt",
            "from ccxt",
            "import aiohttp",
            "from aiohttp",
        ]

        errors: list[str] = []
        for py_file in files:
            content = _read_file(py_file)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for forbidden in forbidden_imports:
                    if forbidden in stripped:
                        errors.append(
                            f"{py_file.relative_to(py_file.parent.parent.parent)}:{i}: "
                            f"found forbidden import '{stripped}'"
                        )

        assert not errors, "Found forbidden real adapter imports:\n" + "\n".join(errors)

    def test_no_non_localhost_urls_in_src(self) -> None:
        """No non-localhost URLs in pipeline source code."""
        files = _src_files()

        url_patterns = ["http://", "https://"]
        localhost_prefixes = [
            "http://127.0.0.1",
            "http://localhost",
            "https://127.0.0.1",
            "https://localhost",
        ]

        errors: list[str] = []
        for py_file in files:
            content = _read_file(py_file)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for url_pat in url_patterns:
                    if url_pat in stripped:
                        is_localhost = any(p in stripped for p in localhost_prefixes)
                        if not is_localhost and "example.com" not in stripped:
                            errors.append(
                                f"{py_file.relative_to(py_file.parent.parent.parent)}:{i}: "
                                f"non-localhost URL: '{stripped}'"
                            )

        assert not errors, "Found non-localhost URLs in src:\n" + "\n".join(errors)

    def test_no_jobs_json_writes(self) -> None:
        """No jobs.json writes anywhere in pipeline source."""
        files = _src_files()

        forbidden_patterns = ["jobs.json", "cron_defs/jobs.yaml"]

        errors: list[str] = []
        for py_file in files:
            content = _read_file(py_file)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if '"' not in stripped and "'" not in stripped:
                    continue
                for pattern in forbidden_patterns:
                    if pattern in stripped and any(kw in stripped for kw in ("write", "open(")):
                        errors.append(
                            f"{py_file.relative_to(py_file.parent.parent.parent)}:{i}: "
                            f"possible jobs.json write: '{stripped}'"
                        )

        assert not errors, "Found possible jobs.json writes:\n" + "\n".join(errors)

    def test_no_live_strategy_writes(self) -> None:
        """No user_data/strategies or freqtrade/strategies writes in pipeline src."""
        files = _src_files()

        forbidden_paths = ["user_data/strategies", "freqtrade/strategies"]
        errors: list[str] = []
        for py_file in files:
            content = _read_file(py_file)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for path_pat in forbidden_paths:
                    if path_pat in stripped and any(kw in stripped for kw in ("write", "open(", "shutil")):
                        errors.append(
                            f"{py_file.relative_to(py_file.parent.parent.parent)}:{i}: "
                            f"possible live strategy write: '{stripped}'"
                        )

        assert not errors, "Found possible live strategy writes:\n" + "\n".join(errors)

    def test_no_env_secrets_read(self) -> None:
        """No os.environ or env var reads in pipeline src (except config gate)."""
        files = _src_files()

        forbidden_env_access = [
            "os.environ",
            "os.getenv",
            "environ.get",
        ]

        errors: list[str] = []
        for py_file in files:
            content = _read_file(py_file)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern in forbidden_env_access:
                    if pattern in stripped:
                        errors.append(
                            f"{py_file.relative_to(py_file.parent.parent.parent)}:{i}: env access: '{stripped}'"
                        )
                        break

        # Allow the config gate module (check_env_enabled reads SI_V2_ENABLE_REAL_ADAPTERS)
        errors = [e for e in errors if "config/gate.py" not in e]

        assert not errors, "Found env access in pipeline code:\n" + "\n".join(errors)
