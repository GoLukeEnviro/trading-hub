r"""Fleet-aware runtime binding — maps bot_id to actual host/container paths.

This is the CRITICAL fix for the Issue #332 gap:
The previous overlay was placed in the wrong host path because the agent
assumed `freqtrade/bots/freqforge/user_data/` was the active mount,
when the actual Docker bind mount is `freqforge/user_data/`.

All bindings are machine-verified (Docker inspect, read-only container exec).
No assumptions — every path is backed by evidence.

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

from pathlib import Path
from typing import Final

from si_v2.apply_actuator.models import BotRuntimeBinding

# ---------------------------------------------------------------------------
# Fleet binding table — verified via Docker inspect on 2026-06-23
# ---------------------------------------------------------------------------

BOT_RUNTIME_BINDINGS: Final[dict[str, BotRuntimeBinding]] = {
    "freqtrade-freqforge": BotRuntimeBinding(
        bot_id="freqtrade-freqforge",
        container_name="trading-freqtrade-freqforge-1",
        host_user_data_path="/home/hermes/projects/trading/freqforge/user_data",
        container_user_data_path="/freqtrade/user_data",
        host_config_path="/home/hermes/projects/trading/freqforge/user_data/config.json",
        container_config_path="/freqtrade/user_data/config.json",
        # Note: `loaded_config_args` reflects the BASE process args only.
        # When a multi-config overlay is activated, the running process
        # will include an additional `--config /freqtrade/user_data/overlay_<id>.json`
        # argument. The proof layer derives the expected overlay path
        # dynamically from the proposal_id at verification time — we do NOT
        # hardcode the activated overlay into the static binding here,
        # because that would make the binding stale the next time a
        # different candidate is activated.
        loaded_config_args=(
            "--config",
            "/freqtrade/user_data/config.json",
            "--strategy",
            "FreqForge_Override",
        ),
        runtime_visible=True,
        confidence="VERIFIED",
        evidence_source="container-trading-freqtrade-freqforge-1-inspect.txt",
    ),
    "freqtrade-freqforge-canary": BotRuntimeBinding(
        bot_id="freqtrade-freqforge-canary",
        container_name="trading-freqtrade-freqforge-canary-1",
        host_user_data_path="/home/hermes/projects/trading/freqforge-canary/user_data",
        container_user_data_path="/freqtrade/user_data",
        host_config_path="/home/hermes/projects/trading/freqforge-canary/user_data/config.json",
        container_config_path="/freqtrade/user_data/config.json",
        loaded_config_args=(
            "--config",
            "/freqtrade/user_data/config.json",
            "--strategy",
            "FreqForge_Override",
        ),
        runtime_visible=True,
        confidence="VERIFIED",
        evidence_source="container-trading-freqtrade-freqforge-canary-1-inspect.txt",
    ),
    "freqtrade-regime-hybrid": BotRuntimeBinding(
        bot_id="freqtrade-regime-hybrid",
        container_name="trading-freqtrade-regime-hybrid-1",
        host_user_data_path="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data",
        container_user_data_path="/freqtrade/user_data",
        host_config_path="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/config.json",
        container_config_path="/freqtrade/user_data/config.json",
        loaded_config_args=(
            "--config",
            "/freqtrade/user_data/config.json",
            "--strategy",
            "RegimeSwitchingHybrid_v7_v04_Integration",
        ),
        runtime_visible=True,
        confidence="VERIFIED",
        evidence_source="container-trading-freqtrade-regime-hybrid-1-inspect.txt",
    ),
    "freqai-rebel": BotRuntimeBinding(
        bot_id="freqai-rebel",
        container_name="trading-freqai-rebel-1",
        host_user_data_path="/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data",
        container_user_data_path="/freqtrade/user_data",
        host_config_path="/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/config.json",
        container_config_path="/freqtrade/user_data/config.json",
        loaded_config_args=(
            "--config",
            "/freqtrade/user_data/config.json",
            "--strategy",
            "RebelLiquidation",
        ),
        runtime_visible=True,
        confidence="VERIFIED",
        evidence_source="container-trading-freqai-rebel-1-inspect.txt",
    ),
}
"""Machine-verified runtime bindings for all 4 SI-v2 bots.

Evidence: Docker inspect mounts, container exec read-only checks.
Verified: 2026-06-23 via fleet runtime binding audit (Issue #332).
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
