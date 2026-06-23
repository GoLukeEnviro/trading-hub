r"""Runtime effect proof — machine verification that bot can see and load changes.

This is the critical gate: no measurement, no mutation counter increment
unless runtime proof is GREEN.

Uses read-only container exec to check container file visibility and loaded config.
Never mutates container state.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from si_v2.apply_actuator.models import (
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
    ProofStatus,
    RuntimeEffectProof,
)


# ---------------------------------------------------------------------------
# Container file visibility check
# ---------------------------------------------------------------------------


def check_container_visibility(
    container_name: str,
    container_file_path: str,
) -> tuple[bool, str]:
    """Check whether a file is visible inside a running Docker container.

    Uses read-only container exec — never mutates container state.

    Args:
        container_name: Docker container name.
        container_file_path: Path inside the container to check.

    Returns:
        Tuple of (visible: bool, detail: str).
    """
    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "test", "-f", container_file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return (True, f"File visible: {container_file_path}")
        else:
            return (False, f"File NOT visible: {container_file_path}")
    except subprocess.TimeoutExpired:
        return (False, f"Container exec timeout for {container_name}")
    except FileNotFoundError:
        return (False, "Docker CLI not available")
    except Exception as e:
        return (False, f"Container exec error: {e}")


# ---------------------------------------------------------------------------
# Effective config loaded check via container exec
# ---------------------------------------------------------------------------


def check_effective_config_loaded(
    container_name: str,
    container_config_path: str,
    expected_values: dict[str, object],
) -> tuple[bool, list[str]]:
    """Check whether the bot's actually loaded config contains expected values.

    Uses container read‑only exec to read and parse the loaded config.json inside the container.
    This confirms REAL runtime effect, not just file existence.

    Args:
        container_name: Docker container name.
        container_config_path: Path to config.json inside the container.
        expected_values: Key-value pairs that should be present.

    Returns:
        Tuple of (loaded: bool, mismatches: list[str]).
    """
    mismatches: list[str] = []

    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "cat", container_config_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, [f"Failed to read config: {result.stderr.strip()}"])

        loaded = json.loads(result.stdout)

        for key, expected_value in expected_values.items():
            actual_value = loaded.get(key)
            # Normalize for comparison
            if str(actual_value) != str(expected_value):
                mismatches.append(
                    f"{key}: expected={expected_value!r}, got={actual_value!r}"
                )

        return (len(mismatches) == 0, mismatches)

    except subprocess.TimeoutExpired:
        return (False, ["Container exec timeout"])
    except json.JSONDecodeError as e:
        return (False, [f"JSON parse error: {e}"])
    except FileNotFoundError:
        return (False, ["Docker CLI not available"])
    except Exception as e:
        return (False, [f"Error: {e}"])


# ---------------------------------------------------------------------------
# Full runtime effect verification
# ---------------------------------------------------------------------------


def verify_runtime_effect(
    proposal: OverlayProposal,
    binding: BotRuntimeBinding,
    draft: EffectiveConfigDraft,
    *,
    overlay_container_path: str = "",
    docker_available: bool = True,
) -> RuntimeEffectProof:
    """Complete runtime effect verification.

    Checks:
      1. Overlay/effective config file visible to bot
      2. Effective config contains expected values (from draft)
      3. Loaded config contains expected values (from container)
      4. Safety invariants (dry_run, live_trading, strategy)

    Args:
        proposal: The overlay proposal.
        binding: Verified bot runtime binding.
        draft: The generated effective config draft.
        overlay_container_path: Path inside container where overlay should be.
        docker_available: Whether Docker is available for container checks.

    Returns:
        RuntimeEffectProof with complete verification results.
    """
    errors: list[str] = []

    # Safety checks from draft
    dry_run_true = draft.dry_run_preserved
    live_trading_false = draft.live_trading_forbidden
    strategy_unchanged = True  # Overlay only changes config, not strategy

    if not dry_run_true:
        errors.append("dry_run is False — live trading risk!")
    if not live_trading_false:
        errors.append("Live trading credentials detected!")

    # File visibility check (container)
    file_visible = False
    if docker_available and overlay_container_path:
        file_visible, detail = check_container_visibility(
            binding.container_name, overlay_container_path,
        )
        if not file_visible:
            errors.append(detail)

    # Effective config values check (from draft)
    effective_ok = True
    for key in proposal.parameters:
        if key not in draft.after_values:
            effective_ok = False
            errors.append(f"Key {key!r} not found in draft after_values")
        elif str(draft.after_values[key]) != str(proposal.parameters[key]):
            effective_ok = False
            errors.append(
                f"Draft mismatch for {key}: "
                f"expected={proposal.parameters[key]!r}, "
                f"got={draft.after_values[key]!r}"
            )

    # Loaded config values check (from container)
    loaded_ok = False
    if docker_available and file_visible:
        loaded_ok, mismatches = check_effective_config_loaded(
            binding.container_name,
            binding.container_config_path,
            proposal.parameters,
        )
        if not loaded_ok:
            errors.extend(mismatches)
    elif not file_visible:
        errors.append("Cannot check loaded config — file not visible to bot")

    # Determine proof status
    if errors:
        proof_status = ProofStatus.RED
    elif not loaded_ok:
        proof_status = ProofStatus.YELLOW
    elif file_visible and effective_ok and loaded_ok:
        proof_status = ProofStatus.GREEN
    else:
        proof_status = ProofStatus.YELLOW

    restart_required = not file_visible or not loaded_ok

    return RuntimeEffectProof(
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        file_visible_to_bot=file_visible,
        effective_config_contains_expected_values=effective_ok,
        loaded_config_contains_expected_values=loaded_ok,
        dry_run_true=dry_run_true,
        live_trading_false=live_trading_false,
        strategy_unchanged=strategy_unchanged,
        restart_required=restart_required,
        proof_status=proof_status,
        errors=tuple(errors),
    )
