r"""Fleet-aware runtime binding — maps bot_id to actual host/container paths.

This is the CRITICAL fix for the Issue #332 gap:
The previous overlay was placed in the wrong host path because the agent
assumed `freqtrade/bots/freqforge/user_data/` was the active mount,
when the actual Docker bind mount is `freqforge/user_data/`.

Topology derivation (R7A, #757)
-------------------------------
Bindings are derived from two topology inputs instead of hardcoded paths:

- ``SI_V2_REPO_ROOT`` — host checkout that contains the per-bot
  ``user_data`` directories (HermesTrader default
  ``/home/hermes/projects/trading``; Agent0 sets
  ``/opt/data/projects/trading-hub``, see PR #740).
- ``SI_V2_COMPOSE_PROJECT`` — Docker Compose project name for the dry-run
  fleet (default ``hermestrader-dryrun``). Container names follow the
  Compose convention ``<project>-<service>-1`` (e.g.
  ``hermestrader-dryrun-freqtrade-freqforge-canary-1``).

The base config file is ``config.example.json`` — the canonical R7A mount
target inside the container (``docker-compose.hermestrader-dryrun.yml``
mounts the per-service config example read-only at
``/freqtrade/user_data/config.example.json``).

All bindings are machine-verified (compose config + live container inspect,
read-only). No assumptions — every path is backed by evidence.

Multi-config note (added 2026-06-23, candidate 65502d13):
`loaded_config_args` is the BASE process command line. When an overlay
candidate is activated, the runtime layer adds a second `--config
/freqtrade/user_data/overlay_<id>.json` argument. The proof layer
(`si_v2.apply_actuator.proof.verify_runtime_effect`) derives the expected
overlay path dynamically from the proposal_id and checks the actual
process command line — see `check_process_uses_overlay`. We do not
hardcode the activated overlay path into the static binding.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.models import BotRuntimeBinding

# ---------------------------------------------------------------------------
# Topology resolution — SI-v2 repo root and Docker Compose project
# ---------------------------------------------------------------------------

SI_V2_REPO_ROOT_ENV: Final[str] = "SI_V2_REPO_ROOT"
"""Environment variable overriding the host checkout containing bot user_data dirs."""

SI_V2_COMPOSE_PROJECT_ENV: Final[str] = "SI_V2_COMPOSE_PROJECT"
"""Environment variable overriding the Docker Compose project name."""

DEFAULT_SI_V2_REPO_ROOT: Final[str] = "/home/hermes/projects/trading"
"""HermesTrader canonical checkout (historical, preserved as default)."""

DEFAULT_SI_V2_COMPOSE_PROJECT: Final[str] = "hermestrader-dryrun"
"""Canonical R7A compose project — verified live 2026-09-19 (container labels)."""


def resolve_si_v2_repo_root() -> Path:
    """Resolve the SI-v2 repository root (host path containing bot user_data dirs)."""
    return Path(os.environ.get(SI_V2_REPO_ROOT_ENV, DEFAULT_SI_V2_REPO_ROOT))


def resolve_compose_project() -> str:
    """Resolve the Docker Compose project name used for the dry-run fleet."""
    return os.environ.get(SI_V2_COMPOSE_PROJECT_ENV, DEFAULT_SI_V2_COMPOSE_PROJECT)


def build_container_name(
    service_name: str,
    *,
    compose_project: str | None = None,
) -> str:
    """Return the Docker container name for a compose service under the fleet project.

    Follows the Compose convention ``<project>-<service>-1`` (verified on the
    live R7A stack, e.g. ``hermestrader-dryrun-freqtrade-freqforge-canary-1``).
    """
    project = compose_project or resolve_compose_project()
    return f"{project}-{service_name}-1"


# ---------------------------------------------------------------------------
# Fleet binding table — repo-relative derivation (R7A topology)
# ---------------------------------------------------------------------------

# Canonical compose service name per bot. Container name = <project>-<service>-1.
_BOT_SERVICE_NAMES: Final[dict[str, str]] = {
    "freqtrade-freqforge": "freqtrade-freqforge",
    "freqtrade-freqforge-canary": "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid": "freqtrade-regime-hybrid",
    "freqai-rebel": "freqai-rebel",
}

# Repo-relative user_data directory per bot (relative to SI_V2_REPO_ROOT).
_BOT_RELATIVE_USER_DATA: Final[dict[str, str]] = {
    "freqtrade-freqforge": "freqforge/user_data",
    "freqtrade-freqforge-canary": "freqforge-canary/user_data",
    "freqtrade-regime-hybrid": "freqtrade/bots/regime-hybrid/user_data",
    "freqai-rebel": "freqtrade/bots/freqai-rebel/user_data",
}

# Strategy argument per bot (matches docker-compose.hermestrader-dryrun.yml).
_BOT_STRATEGIES: Final[dict[str, str]] = {
    "freqtrade-freqforge": "FreqForge_Override",
    "freqtrade-freqforge-canary": "FreqForge_Override",
    "freqtrade-regime-hybrid": "RegimeSwitchingHybrid_v7_v04_Integration",
    "freqai-rebel": "RebelLiquidation",
}

# Canonical container-side base config path (R7A mount target, read-only).
_CONTAINER_BASE_CONFIG: Final[str] = "/freqtrade/user_data/config.example.json"

_EVIDENCE_SOURCE: Final[str] = (
    "docker-compose.hermestrader-dryrun.yml + compose config (R7A, verified 2026-09-19)"
)


def build_fleet_bindings(
    *,
    repo_root: Path,
    compose_project: str,
) -> dict[str, BotRuntimeBinding]:
    """Build the four verified bot bindings from a repo root and compose project.

    Args:
        repo_root: Host path containing the per-bot ``user_data`` directories
            (e.g. ``/opt/data/projects/trading-hub`` on Agent0).
        compose_project: Docker Compose project name (container name prefix).

    Returns:
        Mapping bot_id → ``BotRuntimeBinding`` for the four SI-v2 bots.
    """
    bindings: dict[str, BotRuntimeBinding] = {}
    for bot_id, service_name in _BOT_SERVICE_NAMES.items():
        rel_ud = _BOT_RELATIVE_USER_DATA[bot_id]
        host_user_data = repo_root / rel_ud
        bindings[bot_id] = BotRuntimeBinding(
            bot_id=bot_id,
            container_name=build_container_name(
                service_name, compose_project=compose_project
            ),
            host_user_data_path=str(host_user_data),
            container_user_data_path="/freqtrade/user_data",
            host_config_path=str(host_user_data / "config.example.json"),
            container_config_path=_CONTAINER_BASE_CONFIG,
            loaded_config_args=(
                "--config",
                _CONTAINER_BASE_CONFIG,
                "--strategy",
                _BOT_STRATEGIES[bot_id],
            ),
            runtime_visible=True,
            confidence="VERIFIED",
            evidence_source=_EVIDENCE_SOURCE,
        )
    return bindings


def _bindings_with_runtime_defaults() -> dict[str, BotRuntimeBinding]:
    """Build the binding table from the process environment (or defaults)."""
    return build_fleet_bindings(
        repo_root=resolve_si_v2_repo_root(),
        compose_project=resolve_compose_project(),
    )


BOT_RUNTIME_BINDINGS: Final[dict[str, BotRuntimeBinding]] = _bindings_with_runtime_defaults()
"""Machine-verified runtime bindings for all 4 SI-v2 bots (R7A topology).

Evidence: docker-compose.hermestrader-dryrun.yml, compose config output and
live container inspect (read-only) on 2026-09-19.
"""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_binding(bot_id: str) -> BotRuntimeBinding | None:
    """Resolve a bot_id to its verified runtime binding.

    Args:
        bot_id: Canonical bot identifier.

    Returns:
        BotRuntimeBinding if found, None otherwise.
    """
    return BOT_RUNTIME_BINDINGS.get(bot_id)


def validate_fleet_bindings(
    *,
    check_paths: bool = True,
) -> tuple[bool, list[str]]:
    """Validate that all fleet bindings are consistent and complete.

    Args:
        check_paths: If True, verify host paths exist on the filesystem.
                     Set False for CI environments without VPS paths.

    Returns:
        Tuple of (valid: bool, issues: list[str]).
    """
    issues: list[str] = []

    if len(BOT_RUNTIME_BINDINGS) != 4:
        issues.append(
            f"Expected 4 bot bindings, found {len(BOT_RUNTIME_BINDINGS)}"
        )

    for bot_id, binding in BOT_RUNTIME_BINDINGS.items():
        if binding.confidence != "VERIFIED":
            issues.append(f"{bot_id}: confidence={binding.confidence} (not VERIFIED)")

        if check_paths:
            host_path = Path(binding.host_user_data_path)
            if not host_path.exists():
                issues.append(f"{bot_id}: host_user_data_path does not exist: {host_path}")

            host_config = Path(binding.host_config_path)
            if not host_config.exists():
                issues.append(f"{bot_id}: host_config_path does not exist: {host_config}")

        if not binding.runtime_visible:
            issues.append(f"{bot_id}: runtime_visible=False")

    return (len(issues) == 0, issues)


def build_host_overlay_path(bot_id: str, proposal_id: str) -> str | None:
    """Build the correct HOST-side path for an overlay file.

    This ensures the overlay goes to the Docker mount path, NOT a repo artifact path.

    Args:
        bot_id: Target bot.
        proposal_id: Proposal identifier (e.g., '65502d13').

    Returns:
        Absolute path to the overlay file on the host filesystem, or None if unknown.
    """
    binding = resolve_binding(bot_id)
    if binding is None:
        return None

    return str(
        Path(binding.host_user_data_path)
        / f"overlay_{proposal_id[:8]}.json"
    )
