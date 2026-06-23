"""SI v2 Apply Actuator — Fleet-Aware Runtime Proof Gate (#332).

Transforms approved ShadowProposals into machine-verified runtime-effective
configuration changes. The actuator must NOT increment the mutation counter
or allow measurement unless runtime proof is GREEN.

Core invariant:
  Mutation counter increments ONLY if RuntimeEffectProof.proof_status == "GREEN"
  Measurement starts ONLY if ApplyActuatorResult.status == "APPLIED_WITH_RUNTIME_PROOF"

Key components:
  - BotRuntimeBinding: Maps bot_id → actual host/container paths
  - OverlayProposal: Validated proposal with parameter intent
  - EffectiveConfigDraft: Generated config that WOULD be applied
  - RuntimeEffectProof: Machine-verified proof of runtime effect
  - ApplyActuatorResult: Final verdict with mutation and measurement gates
  - ControlledApplyRunner: Token-gated wiring into the SI-v2 apply flow (#335)

Safety: fail-closed. Any uncertainty → BLOCKED.
"""

from si_v2.apply_actuator.controlled_apply import (
    ACTIVATION_TOKEN_ENV,
    ACTIVATION_TOKEN_VALUE,
    ControlledApplyMode,
    ControlledApplyResult,
    check_activation_token,
    proposal_to_overlay,
    run_controlled_apply,
    run_controlled_apply_batch,
    summarize_results,
)
from si_v2.apply_actuator.models import (
    ApplyActuatorResult,
    ApplyStatus,
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
    ProofStatus,
    RuntimeEffectProof,
)
from si_v2.apply_actuator.overlay_merge import (
    generate_effective_config,
    validate_overlay_safety,
)
from si_v2.apply_actuator.policy import compute_apply_result
from si_v2.apply_actuator.proof import (
    check_container_visibility,
    check_effective_config_loaded,
    verify_runtime_effect,
)
from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    validate_fleet_bindings,
)

__all__ = [
    "ACTIVATION_TOKEN_ENV",
    "ACTIVATION_TOKEN_VALUE",
    "BOT_RUNTIME_BINDINGS",
    "ApplyActuatorResult",
    "ApplyStatus",
    "BotRuntimeBinding",
    "ControlledApplyMode",
    "ControlledApplyResult",
    "EffectiveConfigDraft",
    "OverlayProposal",
    "ProofStatus",
    "RuntimeEffectProof",
    "check_activation_token",
    "check_container_visibility",
    "check_effective_config_loaded",
    "compute_apply_result",
    "generate_effective_config",
    "proposal_to_overlay",
    "run_controlled_apply",
    "run_controlled_apply_batch",
    "summarize_results",
    "validate_fleet_bindings",
    "validate_overlay_safety",
    "verify_runtime_effect",
]
