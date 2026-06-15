"""Safe SI v2 Freqtrade REST auth resolver.

Reads credentials only from existing environment variables or allowlisted local
Freqtrade dry-run config files. Never prints, persists, logs, or commits
secret values.

Resolution priority per bot:
1. Check if username_env and password_env are already set in os.environ.
2. If missing, read api_server.username and api_server.password from an
   allowlisted host-side config file for that bot.
3. Set missing env vars in-process via os.environ.
4. Return sanitized AuthResolution with status only (no secret values).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# JSON type aliases (no Any)
# ---------------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOLVED_FROM_ENV = "RESOLVED_FROM_ENV"
RESOLVED_FROM_FILE = "RESOLVED_FROM_FILE"
MISSING = "MISSING"

# Allowlisted local config paths per bot. Read-only — never modified.
ALLOWED_CONFIG_PATHS: Final[dict[str, list[Path]]] = {
    "freqtrade-freqforge": [
        Path("/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json"),
        Path("/home/hermes/projects/trading/freqtrade/bots/freqforge/config/config_freqforge_dryrun.json"),
    ],
    "freqtrade-regime-hybrid": [
        Path("/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json"),
    ],
    "freqtrade-freqforge-canary": [
        Path("/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json"),
        Path("/home/hermes/projects/trading/freqtrade/bots/freqforge-canary/config/config_canary_dryrun.json"),
    ],
    "freqai-rebel": [
        Path("/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/config.json"),
        Path("/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/config/config.json"),
        Path("/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/config/config_freqai_rebel_dryrun.json"),
    ],
}


# ---------------------------------------------------------------------------
# Sanitized resolution result (no secret values)
# ---------------------------------------------------------------------------


class AuthResolution:
    """Sanitized auth resolution result for one bot.

    Contains no credential values. Only status metadata.
    Not a frozen dataclass to avoid Python 3.13 + from __future__ import annotations
    compatibility issues with importlib.util.spec_from_file_location in tests.
    """

    __slots__ = ("bot_id", "error", "password_env", "source_path",
                 "status", "username_env")

    def __init__(
        self,
        bot_id: str = "",
        username_env: str = "",
        password_env: str = "",
        status: str = "",
        source_path: str = "",
        error: str = "",
    ) -> None:
        self.bot_id = bot_id
        self.username_env = username_env
        self.password_env = password_env
        self.status = status  # RESOLVED_FROM_ENV | RESOLVED_FROM_FILE | MISSING
        self.source_path = source_path
        self.error = error


# ---------------------------------------------------------------------------
# Internal: read api_server credentials from a Freqtrade config file
# ---------------------------------------------------------------------------


def _read_api_credentials(path: Path) -> tuple[str, str]:
    """Read api_server.username and api_server.password from a config file.

    Args:
        path: Path to an existing Freqtrade config JSON file.

    Returns:
        (username, password) tuple.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if the config is not a JSON object, or if
            api_server.username / api_server.password are missing or empty.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"config is not a JSON object: {path}")

    api = raw.get("api_server")
    if not isinstance(api, dict):
        raise ValueError(f"config missing api_server object: {path}")

    username_value = api.get("username")
    password_value = api.get("password")

    if not isinstance(username_value, str) or not username_value:
        raise ValueError(f"config missing non-empty api_server.username: {path}")

    if not isinstance(password_value, str) or not password_value:
        raise ValueError(f"config missing non-empty api_server.password: {path}")

    return username_value, password_value


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------


def _load_registry(path: Path) -> list[JsonObject]:
    """Load enabled bot entries from the SI v2 bot registry.

    Args:
        path: Path to freq_trade_bots.readonly.json.

    Returns:
        List of enabled bot registry entries.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if the registry structure is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("registry is not a JSON object")

    bots_raw = raw.get("bots")
    if not isinstance(bots_raw, list):
        raise ValueError("registry.bots is not a list")

    enabled: list[JsonObject] = []
    for entry in bots_raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled", False):
            enabled.append(entry)

    return enabled


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------


def resolve_all(
    registry_path: Path,
    allowed_paths: dict[str, list[Path]] | None = None,
) -> list[AuthResolution]:
    """Resolve SI v2 auth credentials for all enabled bots in the registry.

    For each bot:
    1. Check os.environ for username_env and password_env.
    2. If either is missing, attempt to read from allowlisted local config files.
    3. Set missing env vars in-process via os.environ.
    4. Return a sanitized AuthResolution (no secret values).

    Args:
        registry_path: Path to the SI v2 bot registry JSON file.
        allowed_paths: Optional dict of bot_id → list of allowlisted config paths.
            Defaults to ALLOWED_CONFIG_PATHS.

    Returns:
        List of AuthResolution — one per enabled bot — with no credential values.

    Raises:
        FileNotFoundError: if registry_path does not exist.
        ValueError: if registry is structurally invalid.
    """
    if allowed_paths is None:
        allowed_paths = ALLOWED_CONFIG_PATHS

    bots = _load_registry(registry_path)
    results: list[AuthResolution] = []

    for bot in bots:
        bot_id_raw = bot.get("bot_id")
        if not isinstance(bot_id_raw, str):
            continue
        bot_id: str = bot_id_raw

        auth = bot.get("auth")
        if not isinstance(auth, dict):
            results.append(AuthResolution(
                bot_id=bot_id, username_env="", password_env="",
                status=MISSING, error="missing auth block in registry",
            ))
            continue

        username_env = auth.get("username_env", "")
        password_env = auth.get("password_env", "")

        if not isinstance(username_env, str) or not isinstance(password_env, str):
            results.append(AuthResolution(
                bot_id=bot_id, username_env=str(username_env),
                password_env=str(password_env), status=MISSING,
                error="username_env or password_env is not a string",
            ))
            continue

        # Step 1: Check existing env
        existing_user = os.environ.get(username_env)
        existing_pass = os.environ.get(password_env)

        if existing_user and existing_pass:
            results.append(AuthResolution(
                bot_id=bot_id, username_env=username_env,
                password_env=password_env, status=RESOLVED_FROM_ENV,
            ))
            continue

        # Step 2: Try allowlisted local config files
        candidates = allowed_paths.get(bot_id, [])
        resolved = False
        last_error = ""

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                username_val, password_val = _read_api_credentials(candidate)
                os.environ[username_env] = username_val
                os.environ[password_env] = password_val
                results.append(AuthResolution(
                    bot_id=bot_id, username_env=username_env,
                    password_env=password_env, status=RESOLVED_FROM_FILE,
                    source_path=str(candidate),
                ))
                resolved = True
                break
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)

        if not resolved:
            missing_hint = "no allowlisted config found"
            if last_error:
                missing_hint = f"config read failed: {last_error[:100]}"
            results.append(AuthResolution(
                bot_id=bot_id, username_env=username_env,
                password_env=password_env, status=MISSING,
                error=missing_hint,
            ))

    return results
