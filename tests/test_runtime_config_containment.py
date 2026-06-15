from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SANITIZED_EXAMPLES = [
    ROOT / "freqforge" / "user_data" / "config.example.json",
    ROOT / "freqforge-canary" / "user_data" / "config.example.json",
    ROOT.joinpath(
        "freqtrade",
        "bots",
        "regime-hybrid",
        "config",
        "research",
        "config_regime_hybrid_sideaware_v1.example.json",
    ),
    ROOT.joinpath(
        "freqtrade",
        "bots",
        "regime-hybrid",
        "config",
        "research",
        "config_regime_hybrid_sideaware_v2.example.json",
    ),
    ROOT.joinpath(
        "freqtrade",
        "bots",
        "regime-hybrid",
        "config",
        "research",
        "config_regime_hybrid_sideaware_v3.example.json",
    ),
    ROOT / "freqtrade" / "bots" / "regime-hybrid" / "user_data" / "momentum_v2_backtest.example.json",
]

IGNORED_RUNTIME_CONFIGS = [
    "freqforge/user_data/config.json",
    "freqforge-canary/user_data/config.json",
    "freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.json",
    "freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v2.json",
    "freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v3.json",
    "freqtrade/bots/regime-hybrid/user_data/momentum_v2_backtest.json",
    "orchestrator/reports/canonical_trading_status_latest.json",
    "orchestrator/reports/phase-33-observation-log.jsonl",
    "var/kill_switch.json",
]


def _walk_values(obj: object, path: str = "") -> list[tuple[str, object]]:
    if isinstance(obj, dict):
        values: list[tuple[str, object]] = []
        for key, value in obj.items():
            key_path = f"{path}.{key}" if path else str(key)
            values.extend(_walk_values(value, key_path))
        return values
    if isinstance(obj, list):
        values = []
        for index, item in enumerate(obj):
            values.extend(_walk_values(item, f"{path}[{index}]"))
        return values
    return [(path, obj)]


def test_runtime_config_files_are_not_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", *IGNORED_RUNTIME_CONFIGS],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()

    assert tracked == []


def test_runtime_config_patterns_are_ignored() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", *IGNORED_RUNTIME_CONFIGS],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()

    assert sorted(ignored) == sorted(IGNORED_RUNTIME_CONFIGS)


def test_sanitized_examples_are_dry_run_local_only_and_placeholdered() -> None:
    for path in SANITIZED_EXAMPLES:
        assert path.exists(), f"missing sanitized example: {path}"
        payload = json.loads(path.read_text())
        if "dry_run" in payload:
            assert payload["dry_run"] is True
        api_server = payload.get("api_server")
        if isinstance(api_server, dict):
            assert api_server.get("listen_ip_address") == "127.0.0.1"
            assert api_server.get("enable_openapi") is False
        for key_path, value in _walk_values(payload):
            lower = key_path.lower()
            if any(marker in lower for marker in ("password", "secret", "token", ".key", "jwt")):
                text = str(value)
                assert "CHANGE_ME_LOCAL_ONLY" in text or text.startswith("${"), f"{path}:{key_path} not placeholdered"
