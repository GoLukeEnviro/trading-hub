r"""Safe overlay merge — generates effective config without runtime mutation.

Key principle: This module GENERATES effective config drafts but does NOT
deploy them to runtime paths. Deployment requires L3 approval.

Strategy: Freqtrade >= 2026.3 supports native multi-config loading
(--config config.json --config overlay_NNN.json). This is the recommended
approach because it:
  1. Never modifies the base config.json
  2. Allows atomic rollback (just remove the overlay file)
  3. Keeps a clear audit trail
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.models import (
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFETY_FORBIDDEN_KEYS: Final[tuple[str, ...]] = (
    "dry_run",
    "exchange",
    "api_server",
    "telegram",
    "external_message_consumer",
)
"""Keys that must NEVER appear in an overlay. Changing them could enable live trading
or break critical infrastructure."""

SAFETY_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "max_open_trades",
    "stake_amount",
    "tradable_balance_ratio",
    "stoploss",
    "minimal_roi",
)
"""Keys that ARE allowed in safe_parameter_overlay_only policy."""


# ---------------------------------------------------------------------------
# Safety validation
# ---------------------------------------------------------------------------


def validate_overlay_safety(
    proposal: OverlayProposal,
) -> tuple[bool, list[str]]:
    """Check that an overlay proposal is safe to generate as a config draft.

    Args:
        proposal: The overlay proposal to validate.

    Returns:
        Tuple of (safe: bool, issues: list[str]).
    """
    issues: list[str] = []

    # Policy must be safe_parameter_overlay_only
    if proposal.policy != "safe_parameter_overlay_only":
        issues.append(
            f"Unsafe policy: {proposal.policy!r} != 'safe_parameter_overlay_only'"
        )

    # Check forbidden keys
    for key in SAFETY_FORBIDDEN_KEYS:
        if key in proposal.parameters:
            issues.append(
                f"Forbidden key in overlay: {key!r} (could enable live trading)"
            )

    # Check that all parameters are in approved list
    for key in proposal.parameters:
        if key not in SAFETY_REQUIRED_KEYS:
            issues.append(
                f"Unknown parameter key: {key!r} not in approved list {SAFETY_REQUIRED_KEYS}"
            )

    return (len(issues) == 0, issues)


# ---------------------------------------------------------------------------
# Effective config generation
# ---------------------------------------------------------------------------


def generate_effective_config(
    proposal: OverlayProposal,
    binding: BotRuntimeBinding,
    *,
    overlay_output_dir: str | Path | None = None,
) -> tuple[EffectiveConfigDraft | None, list[str]]:
    """Generate an effective config by merging base + overlay — without deployment.

    This produces a DRAFT that describes what the effective config WOULD look like.
    It does NOT write to the bot's runtime path. Deployment is a separate L3 step.

    Args:
        proposal: Validated overlay proposal.
        binding: Verified bot runtime binding.
        overlay_output_dir: Optional directory to write the overlay JSON file
            (repo-only, not runtime). If None, no file is written.

    Returns:
        Tuple of (draft or None, errors).
    """
    errors: list[str] = []

    # Safety check
    safe, issues = validate_overlay_safety(proposal)
    if not safe:
        return (None, issues)
    errors.extend(issues)

    # Load base config
    base_config_path = Path(binding.host_config_path)
    if not base_config_path.exists():
        return (None, [f"Base config not found: {base_config_path}"])

    try:
        with open(base_config_path) as f:
            base = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return (None, [f"Failed to read base config: {e}"])

    # Extract before values
    before_values: dict[str, object] = {}
    for key in proposal.parameters:
        if key in base:
            before_values[key] = base[key]

    # Generate merged config (deep copy to avoid mutation)
    merged = deepcopy(base)
    changed_keys: list[str] = []
    for key, value in proposal.parameters.items():
        merged[key] = value
        changed_keys.append(key)

    after_values: dict[str, object] = {
        k: merged[k] for k in changed_keys
    }

    # Compute SHA-256
    merged_json = json.dumps(merged, sort_keys=True, indent=2)
    sha256 = hashlib.sha256(merged_json.encode()).hexdigest()

    # Safety: verify dry_run is preserved
    dry_run_preserved = merged.get("dry_run", False) is True
    if not dry_run_preserved:
        errors.append("CRITICAL: dry_run is False in merged config!")

    # Safety: verify no live trading keys
    live_trading_forbidden = True
    if merged.get("exchange", {}).get("key", "") or merged.get("exchange", {}).get("secret", ""):
        live_trading_forbidden = False
        errors.append("CRITICAL: exchange credentials detected in merged config!")

    # Write overlay file if requested (repo-only, NOT runtime)
    effective_config_path = ""
    if overlay_output_dir is not None:
        out_dir = Path(overlay_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = out_dir / f"overlay_{proposal.proposal_id[:8]}.json"
        with open(overlay_path, "w") as f:
            json.dump(merged, f, sort_keys=True, indent=2)
        effective_config_path = str(overlay_path)

    draft = EffectiveConfigDraft(
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        base_config_path=str(base_config_path),
        effective_config_path=effective_config_path,
        changed_keys=tuple(changed_keys),
        before_values=before_values,
        after_values=after_values,
        sha256=sha256,
        dry_run_preserved=dry_run_preserved,
        live_trading_forbidden=live_trading_forbidden,
        multi_config_compatible=True,  # Freqtrade 2026.3 supports --config stacking
    )

    return (draft, errors)
