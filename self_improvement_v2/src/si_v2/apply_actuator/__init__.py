r"""SI v2 Apply Actuator — Fleet-Aware Runtime Proof Gate (#332).

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

Safety: fail-closed. Any uncertainty → BLOCKED.
"""

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
from si_v2.apply_actuator.policy import (
    compute_apply_result,
    compute_measurement_rule,
    compute_mutation_counter_rule,
)
from si_v2.apply_actuator.proof import (
    check_container_visibility,
    check_effective_config_loaded,
    verify_runtime_effect,
)
from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    resolve_binding,
    validate_fleet_bindings,
)

__all__ = [
    "BOT_RUNTIME_BINDINGS",
    "ApplyActuatorResult",
    "ApplyStatus",
    "BotRuntimeBinding",
    "EffectiveConfigDraft",
    "OverlayProposal",
    "ProofStatus",
    "RuntimeEffectProof",
    "check_container_visibility",
    "check_effective_config_loaded",
    "compute_apply_result",
    "compute_measurement_rule",
    "compute_mutation_counter_rule",
    "generate_effective_config",
    "resolve_binding",
    "validate_fleet_bindings",
    "validate_overlay_safety",
    "verify_runtime_effect",
]
