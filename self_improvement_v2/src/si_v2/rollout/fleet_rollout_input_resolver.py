"""SI-v2 Phase 10.1 — Real Fleet Rollout Chain Input Resolver.

Fail-closed resolver that builds ``FleetRolloutChainInput`` from validated
SI-v2 artifacts: Measurement Watcher decision packs, fleet bot registry,
and candidate overlays.

This module is **read-only and dry-run-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Write to bot config paths or user_data directories
- Enable schedulers or watchers
- Execute rollback
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from si_v2.rollout.fleet_rollout_artifact_planner import (
    TargetBotRuntimeSpec,
)
from si_v2.rollout.fleet_rollout_chain_runner import (
    FleetRolloutChainInput,
    FleetRolloutChainResult,
    run_fleet_rollout_chain,
)
from si_v2.rollout.fleet_rollout_policy import (
    CANARY_BOT,
    CONTROL_BOT,
    FREQAI_REBEL_BOT,
    REGIME_HYBRID_BOT,
    FleetBot,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BOT_REGISTRY_PATH: Final[str] = (
    "self_improvement_v2/config/freqtrade_bots.readonly.json"
)

DEFAULT_DECISION_PACK_DIR: Final[str] = "var/si_v2/measurement_watcher/decision_packs"

DEFAULT_RESOLVER_OUTPUT_DIR: Final[str] = "var/si_v2/fleet_rollout_chain_inputs"

# Mapping from candidate overlay keys to real Freqtrade config keys.
# Only these are safe rollout parameters.
CANDIDATE_TO_REAL_KEY: Final[dict[str, str]] = {
    "max_open_trades_candidate": "max_open_trades",
    "cooldown_candles_candidate": "cooldown_candles",
    "stop_duration_candles_candidate": "stop_duration_candles",
    "entry_threshold_candidate": "entry_threshold",
    "exit_threshold_candidate": "exit_threshold",
}

# Freqtrade config keys that are NEVER allowed as rollout parameters.
BLOCKED_OVERLAY_KEYS: Final[frozenset[str]] = frozenset({
    "stake_amount",
    "minimal_roi",
    "stoploss",
    "pair_whitelist",
    "pair_blacklist",
    "dry_run",
    "stake_currency",
    "trading_mode",
    "margin_mode",
    "exchange",
    "telegram",
    "api_server",
})

# Bot role mapping from registry bot_id to FleetBot role.
BOT_ROLE_MAP: Final[dict[str, str]] = {
    CONTROL_BOT: "control",
    CANARY_BOT: "canary",
    REGIME_HYBRID_BOT: "experimental",
    FREQAI_REBEL_BOT: "freqai",
}

# Default safe target bots (dry-run, non-canary, non-control).
DEFAULT_ALLOWED_TARGETS: Final[tuple[str, ...]] = (
    REGIME_HYBRID_BOT,
    FREQAI_REBEL_BOT,
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetRolloutInputResolutionResult:
    """Structured result from the fleet rollout input resolver.

    Attributes:
        status: Resolution status.
        chain_input: Fully built chain input when READY, None otherwise.
        blocked_reasons: Human-readable reasons for blocking.
        decision_pack_path: Resolved decision pack path.
        source_overlay_path: Resolved or materialized overlay path.
        source_overlay_sha256: SHA-256 of the actual overlay file content.
        next_step: Suggested next action.
    """

    status: Literal[
        "CHAIN_INPUT_READY",
        "CHAIN_INPUT_BLOCKED",
        "CHAIN_INPUT_NOT_FOUND",
    ]
    chain_input: FleetRolloutChainInput | None
    blocked_reasons: tuple[str, ...]
    decision_pack_path: str
    source_overlay_path: str
    source_overlay_sha256: str
    next_step: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _read_json(path: str) -> dict[str, object] | None:
    """Read and parse a JSON file. Returns None on failure."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Decision pack lookup
# ---------------------------------------------------------------------------


def _find_latest_qualified_decision_pack(
    decision_pack_dir: str,
) -> tuple[str | None, tuple[str, ...]]:
    """Find the latest qualified decision pack in a directory.

    A qualified decision pack must have:
    - event == "autonomous_measurement_decision"
    - status == "FINAL_DECISION_EMITTED"
    - decision == "KEEP_CANARY_OVERLAY"
    - target_bot == CANARY_BOT
    - runtime_mutation == "NONE"

    Returns (path, reasons) where path is None if no qualified pack found.
    """
    reasons: list[str] = []
    p = Path(decision_pack_dir)
    if not p.is_dir():
        return None, (f"decision_pack_dir_not_found: {decision_pack_dir}",)

    # Collect all JSON files with their modification times
    candidates: list[tuple[float, Path]] = []
    for f in sorted(p.iterdir()):
        if not f.is_file() or f.suffix != ".json":
            continue
        if f.name.endswith(".tmp."):
            continue
        pack = _read_json(str(f))
        if pack is None:
            continue

        event = str(pack.get("event", ""))
        status = str(pack.get("status", ""))
        decision = str(pack.get("decision", ""))
        target_bot = str(pack.get("target_bot", ""))
        runtime_mutation = str(pack.get("runtime_mutation", ""))

        if event != "autonomous_measurement_decision":
            continue
        if status != "FINAL_DECISION_EMITTED":
            continue
        if decision != "KEEP_CANARY_OVERLAY":
            continue
        if target_bot != CANARY_BOT:
            continue
        if runtime_mutation != "NONE":
            continue

        mtime = f.stat().st_mtime
        candidates.append((mtime, f))

    if not candidates:
        return None, (
            "no_qualified_decision_pack: no decision pack with "
            "KEEP_CANARY_OVERLAY / FINAL_DECISION_EMITTED found",
        )

    # Sort by mtime descending (newest first), then by path name for stability
    candidates.sort(key=lambda x: (-x[0], x[1].name))
    return str(candidates[0][1]), tuple(reasons)


# ---------------------------------------------------------------------------
# Fleet bot registry reader
# ---------------------------------------------------------------------------


def _read_fleet_bot_registry(
    registry_path: str,
) -> tuple[tuple[FleetBot, ...], tuple[str, ...]]:
    """Read the fleet bot registry JSON and build FleetBot tuples.

    Returns (fleet_bots, reasons).
    """
    reasons: list[str] = []
    data = _read_json(registry_path)
    if data is None:
        return (), (f"registry_not_readable: {registry_path}",)

    bots_raw = data.get("bots", [])
    if not isinstance(bots_raw, list):
        return (), ("registry_invalid: 'bots' is not a list",)

    fleet_bots: list[FleetBot] = []
    for entry in bots_raw:
        if not isinstance(entry, dict):
            continue
        bot_id = str(entry.get("bot_id", ""))
        if not bot_id:
            continue

        enabled = bool(entry.get("enabled", False))
        if not enabled:
            continue

        dry_run = bool(entry.get("dry_run_expected", True))
        role = BOT_ROLE_MAP.get(bot_id, "experimental")

        # allow_rollout_target: canary never, control only if policy allows,
        # experimental/freqai by default
        if role == "canary":
            allow_target = False
        elif role == "control":
            allow_target = False  # Phase 10.1: control not a target by default
        else:
            allow_target = True

        fleet_bots.append(FleetBot(
            bot_id=bot_id,
            role=role,  # type: ignore[arg-type]
            dry_run=dry_run,
            allow_rollout_target=allow_target,
        ))

    if not fleet_bots:
        return (), ("no_enabled_bots: no enabled bots in registry",)

    return tuple(fleet_bots), tuple(reasons)


# ---------------------------------------------------------------------------
# Allowed target builder
# ---------------------------------------------------------------------------


def _build_allowed_targets(
    fleet_bots: tuple[FleetBot, ...],
    explicit_allowed: tuple[str, ...] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Build the list of allowed rollout target bots.

    Uses explicit allowlist if provided, otherwise derives from fleet bots.

    Rules:
    - Bot must be in fleet
    - Bot must be enabled (implied by being in fleet_bots)
    - Bot must have dry_run=True
    - Bot must not be canary
    - Bot must not be control (Phase 10.1 default)

    Returns (allowed_targets, reasons).
    """
    reasons: list[str] = []

    if explicit_allowed:
        # Validate explicit allowlist against fleet
        valid: list[str] = []
        fleet_ids = {b.bot_id for b in fleet_bots}
        for bot_id in explicit_allowed:
            if bot_id not in fleet_ids:
                reasons.append(f"explicit_target_not_in_fleet: {bot_id}")
                continue
            bot = next(b for b in fleet_bots if b.bot_id == bot_id)
            if not bot.dry_run:
                reasons.append(f"explicit_target_not_dry_run: {bot_id}")
                continue
            if bot.role == "canary":
                reasons.append(f"explicit_target_is_canary: {bot_id}")
                continue
            if bot.role == "control":
                reasons.append(f"explicit_target_is_control: {bot_id}")
                continue
            valid.append(bot_id)
        return tuple(valid), tuple(reasons)

    # Derive from fleet: experimental + freqai, dry-run, non-canary, non-control
    allowed: list[str] = []
    for bot in fleet_bots:
        if bot.role == "canary":
            continue
        if bot.role == "control":
            continue
        if not bot.dry_run:
            reasons.append(f"target_not_dry_run: {bot.bot_id}")
            continue
        if not bot.allow_rollout_target:
            reasons.append(f"target_not_allowed: {bot.bot_id}")
            continue
        allowed.append(bot.bot_id)

    if not allowed:
        reasons.append(
            "no_allowed_targets: no eligible dry-run non-canary non-control bots"
        )

    return tuple(allowed), tuple(reasons)


# ---------------------------------------------------------------------------
# Target runtime spec builder
# ---------------------------------------------------------------------------


def _build_target_runtime_specs(
    fleet_bots: tuple[FleetBot, ...],
    allowed_targets: tuple[str, ...],
) -> tuple[TargetBotRuntimeSpec, ...]:
    """Build read-only TargetBotRuntimeSpec for each allowed target.

    These specs are deterministic and non-mutating — they describe what
    the bot *would* look like for planning purposes only.
    """
    specs: list[TargetBotRuntimeSpec] = []
    for bot in fleet_bots:
        if bot.bot_id not in allowed_targets:
            continue

        # Deterministic config paths based on bot_id
        if bot.bot_id == REGIME_HYBRID_BOT:
            config_path = "/freqtrade/user_data/config.json"
            user_data_dir = "/freqtrade/user_data"
        elif bot.bot_id == FREQAI_REBEL_BOT:
            config_path = "/freqai/user_data/config.json"
            user_data_dir = "/freqai/user_data"
        elif bot.bot_id == CONTROL_BOT:
            config_path = "/freqtrade/user_data/config.json"
            user_data_dir = "/freqtrade/user_data"
        else:
            config_path = f"/{bot.bot_id}/user_data/config.json"
            user_data_dir = f"/{bot.bot_id}/user_data"

        specs.append(TargetBotRuntimeSpec(
            bot_id=bot.bot_id,
            role=bot.role,  # type: ignore[arg-type]
            dry_run=bot.dry_run,
            config_path=config_path,
            user_data_dir=user_data_dir,
            current_command=(
                "freqtrade", "trade",
                "--config", config_path,
            ),
        ))

    return tuple(specs)


# ---------------------------------------------------------------------------
# Overlay resolver
# ---------------------------------------------------------------------------


def _resolve_source_overlay(
    *,
    explicit_overlay_path: str | None,
    candidate_overlay: dict[str, object] | None,
    change_id: str,
    resolver_output_dir: Path,
) -> tuple[str, str, str, int | float, tuple[str, ...]]:
    """Resolve the source overlay path and extract rollout parameters.

    Option A: Use an explicit overlay path (must exist, be valid JSON,
    contain dry_run: true, and have exactly one safe rollout parameter).

    Option B: Materialize from candidate_overlay dict by mapping candidate
    keys to real Freqtrade keys.

    Returns:
        (overlay_path, overlay_sha256, expected_parameter, expected_value, reasons)
    """
    reasons: list[str] = []

    # --- Option A: explicit overlay path ---
    if explicit_overlay_path:
        p = Path(explicit_overlay_path)
        if not p.exists():
            return ("", "", "", 0, (
                f"explicit_overlay_not_found: {explicit_overlay_path}",
            ))
        if not p.is_file():
            return ("", "", "", 0, (
                f"explicit_overlay_not_file: {explicit_overlay_path}",
            ))

        overlay_data = _read_json(explicit_overlay_path)
        if overlay_data is None:
            return ("", "", "", 0, (
                f"explicit_overlay_not_readable: {explicit_overlay_path}",
            ))

        return _validate_and_extract_overlay(
            overlay_data, p, explicit_overlay_path, reasons,
        )

    # --- Option B: materialize from candidate_overlay ---
    if candidate_overlay:
        return _materialize_overlay_from_candidate(
            candidate_overlay, change_id, resolver_output_dir, reasons,
        )

    return ("", "", "", 0, (
        "no_overlay_source: neither explicit_overlay_path nor "
        "candidate_overlay provided",
    ))


def _validate_and_extract_overlay(
    overlay_data: dict[str, object],
    overlay_path: Path,
    overlay_path_str: str,
    reasons: list[str],
) -> tuple[str, str, str, int | float, tuple[str, ...]]:
    """Validate an existing overlay and extract rollout parameters."""
    # Check dry_run
    dry_run_val = overlay_data.get("dry_run")
    if dry_run_val is False:
        return ("", "", "", 0, (
            f"overlay_dry_run_disabled: {overlay_path_str} has dry_run disabled",
        ))

    # Check for blocked keys (skip metadata fields)
    for key in overlay_data:
        if key in ("dry_run", "stake_currency"):
            continue
        if key in BLOCKED_OVERLAY_KEYS:
            return ("", "", "", 0, (
                f"overlay_blocked_key: {key} in {overlay_path_str}",
            ))

    # Find rollout parameters (keys that are in CANDIDATE_TO_REAL_KEY
    # or are real keys that map to safe rollout params)
    rollout_params: list[tuple[str, int | float]] = []
    for key, value in overlay_data.items():
        if key in ("dry_run", "stake_currency"):
            continue
        if key in BLOCKED_OVERLAY_KEYS:
            continue

        # Check if it's a real Freqtrade key (not a candidate key)
        if key in CANDIDATE_TO_REAL_KEY.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rollout_params.append((key, value))
            else:
                reasons.append(
                    f"overlay_non_numeric_value: {key}={value!r}"
                )

    if len(rollout_params) == 0:
        return ("", "", "", 0, (*reasons,
            "overlay_no_rollout_params: no safe rollout parameters found",
        ))

    if len(rollout_params) > 1:
        param_names = [p[0] for p in rollout_params]
        return ("", "", "", 0, (*reasons,
            f"overlay_multiple_params: {param_names} — "
            f"only one rollout parameter allowed at a time",
        ))

    expected_param, expected_val = rollout_params[0]
    sha256 = _sha256_file(overlay_path)

    return (overlay_path_str, sha256, expected_param, expected_val, tuple(reasons))


def _materialize_overlay_from_candidate(
    candidate_overlay: dict[str, object],
    change_id: str,
    resolver_output_dir: Path,
    reasons: list[str],
) -> tuple[str, str, str, int | float, tuple[str, ...]]:
    """Materialize a source overlay from candidate_overlay dict.

    Maps candidate keys (e.g. max_open_trades_candidate) to real
    Freqtrade keys (e.g. max_open_trades).
    """
    # Find candidate keys that map to rollout parameters
    rollout_candidates: list[tuple[str, str, int | float]] = []
    for cand_key, cand_value in candidate_overlay.items():
        if cand_key == "pair_cluster_action":
            continue  # Not a rollout parameter
        real_key = CANDIDATE_TO_REAL_KEY.get(cand_key)
        if real_key is None:
            reasons.append(f"unknown_candidate_key: {cand_key}")
            continue
        if not isinstance(cand_value, (int, float)) or isinstance(cand_value, bool):
            reasons.append(
                f"candidate_non_numeric: {cand_key}={cand_value!r}"
            )
            continue
        rollout_candidates.append((cand_key, real_key, cand_value))

    if len(rollout_candidates) == 0:
        return ("", "", "", 0, (*reasons,
            "no_rollout_candidates: no valid rollout parameters in "
            "candidate_overlay",
        ))

    if len(rollout_candidates) > 1:
        cand_names = [c[0] for c in rollout_candidates]
        return ("", "", "", 0, (*reasons,
            f"multiple_rollout_candidates: {cand_names} — "
            f"only one rollout parameter allowed at a time",
        ))

    cand_key, real_key, real_value = rollout_candidates[0]

    # Build the overlay dict
    overlay_dict: dict[str, object] = {
        real_key: real_value,
        "dry_run": True,
    }

    # Write to resolver output directory
    overlay_dir = resolver_output_dir / change_id[:24]
    overlay_path = overlay_dir / "source_overlay.json"
    _atomic_write_json(overlay_path, overlay_dict)

    sha256 = _sha256_file(overlay_path)

    return (str(overlay_path), sha256, real_key, real_value, tuple(reasons))


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------


def resolve_fleet_rollout_chain_input(
    *,
    decision_pack_path: str | None = None,
    decision_pack_dir: str | None = None,
    bot_registry_path: str | None = None,
    explicit_allowed_targets: tuple[str, ...] | None = None,
    explicit_overlay_path: str | None = None,
    candidate_overlay: dict[str, object] | None = None,
    change_id_override: str | None = None,
    resolver_output_dir: str | None = None,
) -> FleetRolloutInputResolutionResult:
    """Resolve a complete ``FleetRolloutChainInput`` from SI-v2 artifacts.

    This is the primary entry point for Phase 10.1. It performs a
    fail-closed resolution: if any required artifact is missing, invalid,
    or ambiguous, it returns ``CHAIN_INPUT_BLOCKED`` or
    ``CHAIN_INPUT_NOT_FOUND`` with precise reasons.

    Args:
        decision_pack_path: Explicit path to a decision pack. If provided,
            skips directory lookup.
        decision_pack_dir: Directory to search for the latest qualified
            decision pack. Defaults to ``DEFAULT_DECISION_PACK_DIR``.
        bot_registry_path: Path to the fleet bot registry JSON. Defaults to
            ``DEFAULT_BOT_REGISTRY_PATH``.
        explicit_allowed_targets: Explicit allowlist of target bot IDs.
            If None, derived from fleet bots.
        explicit_overlay_path: Explicit path to a source overlay JSON.
            If provided, skips candidate_overlay materialization.
        candidate_overlay: Candidate overlay dict (from
            ``ProposalCandidate.candidate_overlay``). Used to materialize
            a source overlay when no explicit path is given.
        change_id_override: Override for change_id (used when resolving
            from candidate data without a decision pack).
        resolver_output_dir: Output directory for resolver artifacts.
            Defaults to ``DEFAULT_RESOLVER_OUTPUT_DIR``.

    Returns:
        ``FleetRolloutInputResolutionResult`` with status, chain input,
        and audit trail.
    """
    blocked: list[str] = []
    resolved_decision_pack_dir = decision_pack_dir or DEFAULT_DECISION_PACK_DIR
    resolved_registry_path = bot_registry_path or DEFAULT_BOT_REGISTRY_PATH
    resolved_output_dir = Path(resolver_output_dir or DEFAULT_RESOLVER_OUTPUT_DIR)

    # ------------------------------------------------------------------
    # Step 1: Resolve decision pack
    # ------------------------------------------------------------------

    resolved_decision_pack_path: str = ""
    change_id: str = ""
    candidate_id: str = ""
    decision_pack_candidate_overlay: dict[str, object] | None = None

    if decision_pack_path:
        # Explicit path
        pack = _read_json(decision_pack_path)
        if pack is None:
            return FleetRolloutInputResolutionResult(
                status="CHAIN_INPUT_NOT_FOUND",
                chain_input=None,
                blocked_reasons=(
                    f"decision_pack_not_readable: {decision_pack_path}",
                ),
                decision_pack_path=decision_pack_path,
                source_overlay_path="",
                source_overlay_sha256="",
                next_step="Provide a valid decision pack path and retry.",
            )
        resolved_decision_pack_path = decision_pack_path
        change_id = str(pack.get("change_id", ""))
        candidate_id = str(pack.get("candidate_id", ""))
    else:
        # Directory lookup
        pack_path, lookup_reasons = _find_latest_qualified_decision_pack(
            resolved_decision_pack_dir,
        )
        if pack_path is None:
            return FleetRolloutInputResolutionResult(
                status="CHAIN_INPUT_NOT_FOUND",
                chain_input=None,
                blocked_reasons=lookup_reasons,
                decision_pack_path="",
                source_overlay_path="",
                source_overlay_sha256="",
                next_step=(
                    "Ensure a qualified decision pack exists in "
                    f"{resolved_decision_pack_dir} and retry."
                ),
            )
        resolved_decision_pack_path = pack_path
        pack = _read_json(pack_path)
        if pack is not None:
            change_id = str(pack.get("change_id", ""))
            candidate_id = str(pack.get("candidate_id", ""))

    # Use override if provided
    if change_id_override:
        change_id = change_id_override

    if not change_id:
        blocked.append("change_id_empty: resolved decision pack has no change_id")

    # ------------------------------------------------------------------
    # Step 2: Read fleet bot registry
    # ------------------------------------------------------------------

    fleet_bots, registry_reasons = _read_fleet_bot_registry(
        resolved_registry_path,
    )
    if not fleet_bots:
        return FleetRolloutInputResolutionResult(
            status="CHAIN_INPUT_BLOCKED",
            chain_input=None,
            blocked_reasons=registry_reasons,
            decision_pack_path=resolved_decision_pack_path,
            source_overlay_path="",
            source_overlay_sha256="",
            next_step="Fix fleet bot registry and retry.",
        )

    # ------------------------------------------------------------------
    # Step 3: Build allowed targets
    # ------------------------------------------------------------------

    allowed_targets, target_reasons = _build_allowed_targets(
        fleet_bots,
        explicit_allowed=explicit_allowed_targets,
    )
    if not allowed_targets:
        return FleetRolloutInputResolutionResult(
            status="CHAIN_INPUT_BLOCKED",
            chain_input=None,
            blocked_reasons=target_reasons,
            decision_pack_path=resolved_decision_pack_path,
            source_overlay_path="",
            source_overlay_sha256="",
            next_step="Ensure eligible dry-run target bots exist and retry.",
        )

    # ------------------------------------------------------------------
    # Step 4: Build target runtime specs
    # ------------------------------------------------------------------

    target_specs = _build_target_runtime_specs(fleet_bots, allowed_targets)

    # ------------------------------------------------------------------
    # Step 5: Resolve source overlay
    # ------------------------------------------------------------------

    overlay_path, overlay_sha256, expected_param, expected_val, overlay_reasons = (
        _resolve_source_overlay(
            explicit_overlay_path=explicit_overlay_path,
            candidate_overlay=candidate_overlay or decision_pack_candidate_overlay,
            change_id=change_id,
            resolver_output_dir=resolved_output_dir,
        )
    )

    if not overlay_path:
        return FleetRolloutInputResolutionResult(
            status="CHAIN_INPUT_BLOCKED",
            chain_input=None,
            blocked_reasons=overlay_reasons,
            decision_pack_path=resolved_decision_pack_path,
            source_overlay_path="",
            source_overlay_sha256="",
            next_step="Provide a valid source overlay or candidate_overlay and retry.",
        )

    if overlay_reasons:
        blocked.extend(overlay_reasons)

    if blocked:
        return FleetRolloutInputResolutionResult(
            status="CHAIN_INPUT_BLOCKED",
            chain_input=None,
            blocked_reasons=tuple(blocked),
            decision_pack_path=resolved_decision_pack_path,
            source_overlay_path=overlay_path,
            source_overlay_sha256=overlay_sha256,
            next_step="Review blocked reasons and fix before retrying.",
        )

    # ------------------------------------------------------------------
    # Step 6: Build chain input
    # ------------------------------------------------------------------

    chain_input = FleetRolloutChainInput(
        decision_pack_path=resolved_decision_pack_path,
        fleet_bots=fleet_bots,
        allowed_target_bots=allowed_targets,
        target_runtime_specs=target_specs,
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha256,
        expected_parameter=expected_param,
        expected_value=expected_val,
        execute_fleet_runtime=False,
    )

    return FleetRolloutInputResolutionResult(
        status="CHAIN_INPUT_READY",
        chain_input=chain_input,
        blocked_reasons=(),
        decision_pack_path=resolved_decision_pack_path,
        source_overlay_path=overlay_path,
        source_overlay_sha256=overlay_sha256,
        next_step=(
            f"Chain input ready for candidate {candidate_id}. "
            f"Call run_fleet_rollout_chain() with this input to "
            f"reach FLEET_CHAIN_READY."
        ),
    )


# ---------------------------------------------------------------------------
# Active Cycle integration helper
# ---------------------------------------------------------------------------


def maybe_resolve_and_run_chain(
    *,
    decision_pack_path: str | None = None,
    decision_pack_dir: str | None = None,
    bot_registry_path: str | None = None,
    explicit_allowed_targets: tuple[str, ...] | None = None,
    explicit_overlay_path: str | None = None,
    candidate_overlay: dict[str, object] | None = None,
    change_id_override: str | None = None,
    fleet_rollout_chain_enabled: bool = False,
    chain_output_dir: str | None = None,
    resolver_output_dir: str | None = None,
) -> FleetRolloutChainResult | None:
    """Active Cycle integration: resolve inputs and optionally run the chain.

    When ``fleet_rollout_chain_enabled`` is False (default), returns None.

    When enabled, resolves chain inputs from real artifacts and runs the
    fleet rollout chain in READY-only mode (``execute_fleet_runtime=False``).

    Args:
        decision_pack_path: Explicit decision pack path.
        decision_pack_dir: Decision pack directory for lookup.
        bot_registry_path: Fleet bot registry path.
        explicit_allowed_targets: Explicit target allowlist.
        explicit_overlay_path: Explicit overlay path.
        candidate_overlay: Candidate overlay dict for materialization.
        change_id_override: Override change_id.
        fleet_rollout_chain_enabled: Master switch. Default False.
        chain_output_dir: Override for chain output directory.
        resolver_output_dir: Override for resolver output directory.

    Returns:
        ``FleetRolloutChainResult`` when chain runs, None when disabled.
    """
    if not fleet_rollout_chain_enabled:
        return None

    # Step 1: Resolve inputs
    resolution = resolve_fleet_rollout_chain_input(
        decision_pack_path=decision_pack_path,
        decision_pack_dir=decision_pack_dir,
        bot_registry_path=bot_registry_path,
        explicit_allowed_targets=explicit_allowed_targets,
        explicit_overlay_path=explicit_overlay_path,
        candidate_overlay=candidate_overlay,
        change_id_override=change_id_override,
        resolver_output_dir=resolver_output_dir,
    )

    if resolution.status != "CHAIN_INPUT_READY":
        # Cannot proceed — return a synthetic blocked result
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_BLOCKED",
            change_id="",
            candidate_id="",
            policy_status="",
            planner_status="",
            ceremony_status="",
            rollout_policy_path="",
            rollout_plan_path="",
            chain_audit_path="",
            blocked_reasons=resolution.blocked_reasons,
            next_step=resolution.next_step,
        )

    # Step 2: Run the chain (READY-only, execute_fleet_runtime=False)
    assert resolution.chain_input is not None
    resolved_chain_dir = (
        Path(chain_output_dir) if chain_output_dir
        else Path("var/si_v2/fleet_rollout_chain")
    )

    return run_fleet_rollout_chain(
        resolution.chain_input,
        chain_output_dir=resolved_chain_dir,
        runtime_executor=None,
    )
