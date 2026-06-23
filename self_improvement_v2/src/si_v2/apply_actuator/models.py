r"""Apply Actuator data models — typed, immutable, fail-closed.

All status enums and data classes used by the Apply Actuator.
No runtime mutation; pure data representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Status enums
# ---------------------------------------------------------------------------

class ApplyStatus(StrEnum):
    """The final status of an apply attempt."""
    NO_RUNTIME_EFFECT = "NO_RUNTIME_EFFECT"
    """Overlay exists but has zero runtime impact (wrong path, not loaded, etc.)."""

    DRAFTED_NOT_APPLIED = "DRAFTED_NOT_APPLIED"
    """Effective config generated but not placed in runtime path."""

    RUNTIME_PROOF_REQUIRED = "RUNTIME_PROOF_REQUIRED"
    """Overlay placed in correct path but not yet loaded by bot."""

    APPLIED_WITH_RUNTIME_PROOF = "APPLIED_WITH_RUNTIME_PROOF"
    """Runtime proof GREEN — config change is active and verified."""

    BLOCKED = "BLOCKED"
    """Apply blocked by safety gate (wrong path, dry_run set to False, strategy change, etc.)."""


class ProofStatus(StrEnum):
    """Status of runtime effect verification."""
    GREEN = "GREEN"
    """Runtime proof confirmed — bot can see and load the change."""

    YELLOW = "YELLOW"
    """Partial — file visible but effective config not confirmed loaded."""

    RED = "RED"
    """Proof failed — file not visible, values don't match, or safety violation."""

    NOT_CHECKED = "NOT_CHECKED"
    """Proof has not been attempted yet."""


# ---------------------------------------------------------------------------
# BotRuntimeBinding — fleet-aware host/container path mapping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BotRuntimeBinding:
    """Machine-verified mapping from bot_id to actual runtime paths.

    This is the critical piece that prevents the previous bug:
    the overlay was written to the wrong host path (freqtrade/bots/freqforge/)
    instead of the actual Docker mount path (freqforge/).
    """

    bot_id: str
    """Canonical bot identifier (e.g., 'freqtrade-freqforge')."""

    container_name: str
    """Docker container name (e.g., 'trading-freqtrade-freqforge-1')."""

    host_user_data_path: str
    """Absolute host path mounted as user_data (e.g., '/.../freqforge/user_data')."""

    container_user_data_path: str
    """Container-side user_data path (e.g., '/freqtrade/user_data')."""

    host_config_path: str
    """Absolute host path to active config.json."""

    container_config_path: str
    """Container-side config.json path."""

    loaded_config_args: tuple[str, ...] = field(default_factory=tuple)
    """The --config arguments passed to freqtrade trade."""

    current_config_sha256: str = ""
    """SHA-256 of the currently loaded config.json."""

    runtime_visible: bool = False
    """Whether the container is currently running and reachable."""

    confidence: str = "UNVERIFIED"
    """Confidence level: VERIFIED, DOCKER_ONLY, ASSUMED, UNVERIFIED."""

    evidence_source: str = ""
    """Path to the evidence file documenting this binding."""

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict for reporting."""
        return {
            "bot_id": self.bot_id,
            "container_name": self.container_name,
            "host_user_data_path": self.host_user_data_path,
            "container_user_data_path": self.container_user_data_path,
            "host_config_path": self.host_config_path,
            "container_config_path": self.container_config_path,
            "loaded_config_args": list(self.loaded_config_args),
            "current_config_sha256": self.current_config_sha256,
            "runtime_visible": self.runtime_visible,
            "confidence": self.confidence,
            "evidence_source": self.evidence_source,
        }


# ---------------------------------------------------------------------------
# OverlayProposal — what we intend to apply
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OverlayProposal:
    """A validated proposal describing which parameters to change."""

    proposal_id: str
    """Unique proposal identifier (e.g., '65502d13a99bfadd')."""

    bot_id: str
    """Target bot ID."""

    policy: str = "safe_parameter_overlay_only"
    """Mutation policy — must be safe_parameter_overlay_only."""

    parameters: dict[str, object] = field(default_factory=dict)
    """Parameters to overlay."""

    expected_base_values: dict[str, object] = field(default_factory=dict)
    """Expected current values before application."""

    expected_new_values: dict[str, object] = field(default_factory=dict)
    """Expected values after application."""

    created_at_utc: str = ""
    """ISO timestamp of proposal creation."""

    source_cycle_id: str = ""
    """Evidence cycle ID that generated this proposal."""

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "policy": self.policy,
            "parameters": dict(self.parameters),
            "expected_base_values": dict(self.expected_base_values),
            "expected_new_values": dict(self.expected_new_values),
            "created_at_utc": self.created_at_utc,
            "source_cycle_id": self.source_cycle_id,
        }


# ---------------------------------------------------------------------------
# EffectiveConfigDraft — generated config, not yet deployed
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EffectiveConfigDraft:
    """A generated effective config that merges base + overlay.

    This is a DRAFT — it has NOT been deployed to the bot's runtime path.
    Deployment requires a separate L3 activation with explicit approval.
    """

    proposal_id: str
    bot_id: str
    base_config_path: str = ""
    effective_config_path: str = ""
    changed_keys: tuple[str, ...] = field(default_factory=tuple)
    before_values: dict[str, object] = field(default_factory=dict)
    after_values: dict[str, object] = field(default_factory=dict)
    sha256: str = ""
    dry_run_preserved: bool = True
    live_trading_forbidden: bool = True
    multi_config_compatible: bool = False
    """Whether native --config overlay is supported (Freqtrade >= 2026.3)."""

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "base_config_path": self.base_config_path,
            "effective_config_path": self.effective_config_path,
            "changed_keys": list(self.changed_keys),
            "before_values": dict(self.before_values),
            "after_values": dict(self.after_values),
            "sha256": self.sha256,
            "dry_run_preserved": self.dry_run_preserved,
            "live_trading_forbidden": self.live_trading_forbidden,
            "multi_config_compatible": self.multi_config_compatible,
        }


# ---------------------------------------------------------------------------
# RuntimeEffectProof — machine verification result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeEffectProof:
    """Machine-verified proof that the bot can see and load the change.

    This is the gate that prevents false APPLIED status.
    """

    proposal_id: str = ""
    bot_id: str = ""
    file_visible_to_bot: bool = False
    """Whether the overlay/effective config file is visible inside the container."""

    effective_config_contains_expected_values: bool = False
    """Whether the generated config (base + overlay merge) has the expected new values."""

    loaded_config_contains_expected_values: bool = False
    """Whether the bot's ACTUALLY LOADED config has the expected values.

    Derived from either the Freqtrade API (show_config) or the deterministic
    in-container merge. NOT from a raw cat of the base config.json — that
    would conflate the base with the effective runtime state.
    """

    process_command_uses_overlay: bool = False
    """Whether the Freqtrade process command line references the overlay config path.

    Authoritative evidence that the bot was started with the overlay file. Without
    this, the file may be visible in the container but never actually loaded.
    """

    proof_method: str = ""
    """Which proof strategy was used: 'api', 'merged_fallback', or 'none'."""

    dry_run_true: bool = True
    live_trading_false: bool = True
    strategy_unchanged: bool = True
    restart_required: bool = False
    """Whether bot restart is needed for config to take effect (multi-config may avoid this)."""

    proof_status: ProofStatus = ProofStatus.NOT_CHECKED
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "file_visible_to_bot": self.file_visible_to_bot,
            "effective_config_contains_expected_values": self.effective_config_contains_expected_values,
            "loaded_config_contains_expected_values": self.loaded_config_contains_expected_values,
            "process_command_uses_overlay": self.process_command_uses_overlay,
            "proof_method": self.proof_method,
            "dry_run_true": self.dry_run_true,
            "live_trading_false": self.live_trading_false,
            "strategy_unchanged": self.strategy_unchanged,
            "restart_required": self.restart_required,
            "proof_status": self.proof_status.value,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# ApplyActuatorResult — final verdict
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplyActuatorResult:
    """The complete result of an apply attempt with all safety gates."""

    status: ApplyStatus = ApplyStatus.BLOCKED
    proposal_id: str = ""
    bot_id: str = ""
    proof: RuntimeEffectProof = field(default_factory=RuntimeEffectProof)  # type: ignore[call-overload]
    mutation_counter_should_increment: bool = False
    measurement_allowed: bool = False
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "proof": self.proof.to_dict(),
            "mutation_counter_should_increment": self.mutation_counter_should_increment,
            "measurement_allowed": self.measurement_allowed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }
