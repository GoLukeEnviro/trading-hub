"""Tests for Freqtrade config credential safety (P0-4).

Validates that all tracked example/template config files:
- Contain only safe placeholder values (never real secrets)
- Include api_server with jwt_secret_key and password fields
- Cover the four-bot fleet shape
- Use consistent placeholder naming

These tests prevent accidental credential commits by running as
part of the main-gate CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Known safe placeholder values — these are never real secrets
_SAFE_PLACEHOLDERS = {
    "",
    "CHANGE_ME",
    "CHANGE_ME_LOCAL_ONLY_KEY",
    "CHANGE_ME_LOCAL_ONLY_SECRET",
    "CHANGE_ME_LOCAL_ONLY_PASSWORD",
    "CHANGE_ME_LOCAL_ONLY_TOKEN",
    "PLACEHOLDER",
    "YOUR_SECRET_HERE",
    "REDACTED",
    "***",
}

# Credential keys that must have placeholder values in tracked configs
_CREDENTIAL_KEYS = {
    "jwt_secret_key",
    "password",
    "secret",
    "key",
    "token",
    "passphrase",
    "api_key",
    "api_secret",
}

# Expected example configs for the four-bot fleet
_EXPECTED_EXAMPLE_CONFIGS = [
    "freqforge/user_data/config.example.json",
    "freqforge-canary/user_data/config.example.json",
    "freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.example.json",
    "freqtrade/bots/freqai-rebel/user_data/config.example.json",
]


def _scan_config_for_credentials(data: dict, path: str = "") -> list[tuple[str, str]]:
    """Recursively find credential keys and their values. Returns (key_path, value) tuples."""
    findings: list[tuple[str, str]] = []
    for k, v in data.items():
        full_path = f"{path}.{k}" if path else k
        if isinstance(v, dict):
            findings.extend(_scan_config_for_credentials(v, full_path))
        elif (
            isinstance(v, str)
            and any(ck in k.lower() for ck in _CREDENTIAL_KEYS)
            and v not in _SAFE_PLACEHOLDERS
            and not v.startswith("${")
            and not v.startswith("CHANGE_ME")
        ):
            findings.append((full_path, v))
    return findings


class TestExampleConfigsAreSafe:
    """Verify all tracked example configs contain only safe placeholders."""

    @pytest.mark.parametrize("config_rel", _EXPECTED_EXAMPLE_CONFIGS)
    def test_config_exists(self, config_rel: str) -> None:
        """Each expected example config must exist."""
        config_path = _REPO_ROOT / config_rel
        assert config_path.exists(), f"Missing expected example config: {config_rel}"

    @pytest.mark.parametrize("config_rel", _EXPECTED_EXAMPLE_CONFIGS)
    def test_no_real_secrets_in_config(self, config_rel: str) -> None:
        """No credential value in tracked example configs may be a real secret."""
        config_path = _REPO_ROOT / config_rel
        if not config_path.exists():
            pytest.skip(f"Config not found: {config_rel}")

        with open(config_path) as f:
            data = json.load(f)

        findings = _scan_config_for_credentials(data)
        assert findings == [], (
            f"Non-placeholder credential values found in {config_rel}: "
            f"{[(k, f'len={len(v)}') for k, v in findings]}"
        )

    @pytest.mark.parametrize("config_rel", _EXPECTED_EXAMPLE_CONFIGS)
    def test_api_server_has_required_fields(self, config_rel: str) -> None:
        """Example configs with api_server must include jwt_secret_key and password."""
        config_path = _REPO_ROOT / config_rel
        if not config_path.exists():
            pytest.skip(f"Config not found: {config_rel}")

        with open(config_path) as f:
            data = json.load(f)

        api_server = data.get("api_server")
        if api_server is None:
            pytest.skip(f"{config_rel} has no api_server section")
        if not isinstance(api_server, dict):
            return

        # If api_server exists and is enabled, it must have credential fields
        if api_server.get("enabled", False):
            assert "jwt_secret_key" in api_server, (
                f"{config_rel}: api_server.enabled=true but jwt_secret_key missing"
            )
            assert "password" in api_server, (
                f"{config_rel}: api_server.enabled=true but password missing"
            )

    def test_dry_run_preserved(self) -> None:
        """All example configs must have dry_run=true."""
        for config_rel in _EXPECTED_EXAMPLE_CONFIGS:
            config_path = _REPO_ROOT / config_rel
            if not config_path.exists():
                continue
            with open(config_path) as f:
                data = json.load(f)
            if "dry_run" in data:
                assert data["dry_run"] is True, (
                    f"{config_rel}: dry_run must be true in example configs"
                )

    def test_four_bot_coverage(self) -> None:
        """Verify example configs exist for all four active fleet bots."""
        missing = []
        for config_rel in _EXPECTED_EXAMPLE_CONFIGS:
            if not (_REPO_ROOT / config_rel).exists():
                missing.append(config_rel)
        assert missing == [], f"Missing example configs for bots: {missing}"


class TestGitignoreCoverage:
    """Verify real config files are gitignored and examples are not."""

    def test_real_configs_ignored(self) -> None:
        """Non-example config.json files must be gitignored."""
        import subprocess

        bot_dirs = [
            "freqtrade/bots/freqai-rebel",
            "freqtrade/bots/regime-hybrid",
            "freqforge",
            "freqforge-canary",
        ]
        for bot_dir in bot_dirs:
            config_path = f"{bot_dir}/user_data/config.json"
            r = subprocess.run(
                ["git", "check-ignore", config_path],
                capture_output=True, text=True, cwd=_REPO_ROOT,
            )
            assert r.returncode == 0, (
                f"{config_path} is NOT gitignored — real secrets could be committed"
            )

    def test_example_configs_not_ignored(self) -> None:
        """Example config files must NOT be gitignored."""
        import subprocess

        for config_rel in _EXPECTED_EXAMPLE_CONFIGS:
            if not (_REPO_ROOT / config_rel).exists():
                continue
            r = subprocess.run(
                ["git", "check-ignore", config_rel],
                capture_output=True, text=True, cwd=_REPO_ROOT,
            )
            assert r.returncode != 0, (
                f"{config_rel} IS gitignored — example configs must be trackable"
            )
