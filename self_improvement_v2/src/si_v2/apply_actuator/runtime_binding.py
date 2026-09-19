r"""Fleet-aware runtime binding — maps bot_id to actual host/container paths.

This is the CRITICAL fix for the Issue #332 gap:
The previous overlay was placed in the wrong host path because the agent
assumed `freqtrade/bots/freqforge/user_data/` was the active mount,
when the actual Docker bind mount is `freqforge/user_data/`.

Resolution rules (R7A topology, portable across hosts)
------------------------------------------------------
- Host paths are **repo-relative**: resolved from this file's location
  (``<repo>/self_improvement_v2/src/si_v2/apply_actuator/runtime_binding.py``),
  so the same binding table holds on any checkout (the historical
  HermesTrader tree and Agent0 alike). The historical absolute root
  (``/home/hermes/projects/trading``) is intentionally not used.
- Container names derive from the compose project
  (``SI_V2_COMPOSE_PROJECT``, default ``hermestrader-dryrun``) as
  ``<project>-<service>-1``.
- The R7A compose mounts the host config file at
  ``/freqtrade/user_data/config.example.json`` inside the container (the
  host file is bind-mounted to that name, keeping its secrets out of Git).
  The overlay is added as a *second* ``--config`` at runtime, and the
  compose override bind-mounts it into the same user_data directory.

Multi-config note (added 2026-06-23, candidate 65502d13):
`loaded_config_args` is the BASE compose command line (starting with
``trade``). When an overlay candidate is activated, the runtime layer adds a
second ``--config /freqtrade/user_data/overlay_<id>.json`` argument. The
proof layer (`si_v2.apply_actuator.proof.verify_runtime_effect`) derives the
expected overlay path dynamically from the proposal_id and checks the actual
process command line — see `check_process_uses_overlay`. We do not hardcode
the activated overlay path into the static binding.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.models import BotRuntimeBinding

# ---------------------------------------------------------------------------
# Topology (repo-relative host paths + compose project)
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
"""Repository root (checkout) this binding table lives in."""

DEFAULT_COMPOSE_PROJECT: Final[str] = "hermestrader-dryrun"
"""Canonical compose project of the R7A dry-run stack."""

CONTAINER_CONFIG_PATH: Final[str] = "/freqtrade/user_data/config.example.json"
"""Container-side base config path (R7A mount target of the host config)."""

CONTROLLED_APPLY_STATE_DIR: Final[Path] = Path(
    os.environ.get("SI_V2_CONTROLLED_APPLY_STATE_DIR")
    or (REPO_ROOT / "var" / "si-v2-controlled-apply")
)
"""Default state directory for controlled-apply artifacts.

Repo-relative (``var/`` is gitignored) so it is writable on any checkout —
the historical ``/opt/data/profiles/orchestrator/...`` default was only
valid inside the HermesTrader orchestrator profile and is not portable.
Production callers may override via ``SI_V2_CONTROLLED_APPLY_STATE_DIR`` or
by passing explicit ``state_dir`` arguments.
"""


def compose_project_name() -> str:
    """Return the compose project name (env read at call time)."""
    return os.environ.get("SI_V2_COMPOSE_PROJECT", DEFAULT_COMPOSE_PROJECT)


def container_name_for_service(service: str) -> str:
    """Return the compose container name for a service (env read at call time)."""
    return f"{compose_project_name()}-{service}-1"


# ---------------------------------------------------------------------------
# Compose invocation context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComposeContext:
    """Explicit compose invocation context for a real recreate (R7A stack).

    A real ``docker compose`` recreate must never be invoked against an
    implicitly guessed compose file: the executor fails closed when no
    context is supplied, and real callers pass
    :meth:`ComposeContext.default` (or an explicit context).
    """

    repo_root: str
    """Working directory for the compose invocation (interpolation base)."""

    compose_file: str
    """Absolute path to the main compose file."""

    env_file: str
    """Absolute path to the env-file used for interpolation (may not exist)."""

    @classmethod
    def default(cls) -> ComposeContext:
        """Return the context for the current checkout (R7A compose)."""
        return cls(
            repo_root=str(REPO_ROOT),
            compose_file=str(REPO_ROOT / "docker-compose.hermestrader-dryrun.yml"),
            env_file=str(REPO_ROOT / ".env"),
        )


# ---------------------------------------------------------------------------
# Fleet binding table — repo-relative, compose-derived (R7A topology)
# ---------------------------------------------------------------------------


def _binding(
    bot_id: str,
    service: str,
    user_data_relative: str,
    strategy: str,
) -> BotRuntimeBinding:
    host_user_data = REPO_ROOT / user_data_relative
    container_name = container_name_for_service(service)
    return BotRuntimeBinding(
        bot_id=bot_id,
        container_name=container_name,
        host_user_data_path=str(host_user_data),
        container_user_data_path="/freqtrade/user_data",
        host_config_path=str(host_user_data / "config.json"),
        container_config_path=CONTAINER_CONFIG_PATH,
        # `loaded_config_args` reflects the BASE compose command (compose-style,
        # starting with `trade`). When a multi-config overlay is activated, the
        # running process includes an additional
        # `--config /freqtrade/user_data/overlay_<id>.json` argument. The proof
        # layer derives the expected overlay path dynamically from the
        # proposal_id at verification time — we do NOT hardcode the activated
        # overlay into the static binding here.
        loaded_config_args=(
            "trade",
            "--config",
            CONTAINER_CONFIG_PATH,
            "--strategy",
            strategy,
        ),
        runtime_visible=True,
        confidence="VERIFIED",
        evidence_source=f"compose-live:{container_name}",
    )


BOT_RUNTIME_BINDINGS: Final[dict[str, BotRuntimeBinding]] = {
    "freqtrade-freqforge": _binding(
        "freqtrade-freqforge",
        "freqtrade-freqforge",
        "freqforge/user_data",
        "FreqForge_Override",
    ),
    "freqtrade-freqforge-canary": _binding(
        "freqtrade-freqforge-canary",
        "freqtrade-freqforge-canary",
        "freqforge-canary/user_data",
        "FreqForge_Override",
    ),
    "freqtrade-regime-hybrid": _binding(
        "freqtrade-regime-hybrid",
        "freqtrade-regime-hybrid",
        "freqtrade/bots/regime-hybrid/user_data",
        "RegimeSwitchingHybrid_v7_v04_Integration",
    ),
    "freqai-rebel": _binding(
        "freqai-rebel",
        "freqai-rebel",
        "freqtrade/bots/freqai-rebel/user_data",
        "RebelLiquidation",
    ),
}
"""Runtime bindings for all 4 SI-v2 bots (repo-relative + compose-derived)."""


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
