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
    ApiConfigProofResult,
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
    check_effective_config_from_api,
    check_effective_config_from_api_surface,
    check_effective_config_from_merged_files,
    check_effective_config_loaded,  # deprecated backward-compat shim
    check_process_uses_overlay,
    verify_runtime_effect,
)
from si_v2.apply_actuator.restart_gate import (
    CANARY_COMPOSE_SERVICE,
    CanaryRecreatePlan,
    RestartGateResult,
    build_canary_recreate_plan,
    check_restart_gate,
    render_compose_override_preview,
)
from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_BOT_ID as RESTART_CANARY_BOT_ID,
)
from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_CONTAINER_NAME,
    CANARY_SERVICE_NAME,
    RESTART_FORBIDDEN_KEYS,
    RestartExecutionResult,
    RestartPlan,
    RestartPlanResult,
    execute_canary_restart_with_overlay,
    plan_canary_restart_with_overlay,
)
from si_v2.apply_actuator.rollback_rehearsal import (
    EXPECTED_BASELINE_MAX_OPEN_TRADES,
    RollbackExecutionResult,
    RollbackGateResult,
    RollbackPlan,
    RollbackPreview,
    build_rollback_preview,
    check_rollback_gate,
    execute_canary_rollback,
    plan_canary_rollback_from_overlay,
    render_rollback_compose_preview,
)
from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    validate_fleet_bindings,
)
from si_v2.apply_actuator.runtime_executor import (
    L3_RESTART_TOKEN_ENV,
    L3_RESTART_TOKEN_VALUE,
    run_canary_restart_with_overlay,
    write_compose_override_file,
)
from si_v2.apply_actuator.runtime_executor import (
    RuntimeExecutionResult as RuntimeExecutorResult,
)

__all__ = [
    "ACTIVATION_TOKEN_ENV",
    "ACTIVATION_TOKEN_VALUE",
    "BOT_RUNTIME_BINDINGS",
    "CANARY_COMPOSE_SERVICE",
    "CANARY_CONTAINER_NAME",
    "CANARY_SERVICE_NAME",
    "EXPECTED_BASELINE_MAX_OPEN_TRADES",
    "L3_RESTART_TOKEN_ENV",
    "L3_RESTART_TOKEN_VALUE",
    "RESTART_CANARY_BOT_ID",
    "RESTART_FORBIDDEN_KEYS",
    "ApiConfigProofResult",
    "ApplyActuatorResult",
    "ApplyStatus",
    "BotRuntimeBinding",
    "CanaryRecreatePlan",
    "ControlledApplyMode",
    "ControlledApplyResult",
    "EffectiveConfigDraft",
    "OverlayProposal",
    "ProofStatus",
    "RestartExecutionResult",
    "RestartGateResult",
    "RestartPlan",
    "RestartPlanResult",
    "RollbackExecutionResult",
    "RollbackGateResult",
    "RollbackPlan",
    "RollbackPreview",
    "RuntimeEffectProof",
    "RuntimeExecutorResult",
    "build_canary_recreate_plan",
    "build_rollback_preview",
    "check_activation_token",
    "check_container_visibility",
    "check_effective_config_from_api",
    "check_effective_config_from_api_surface",
    "check_effective_config_from_merged_files",
    "check_effective_config_loaded",
    "check_process_uses_overlay",
    "check_restart_gate",
    "check_rollback_gate",
    "compute_apply_result",
    "execute_canary_restart_with_overlay",
    "execute_canary_rollback",
    "generate_effective_config",
    "plan_canary_restart_with_overlay",
    "plan_canary_rollback_from_overlay",
    "proposal_to_overlay",
    "render_compose_override_preview",
    "render_rollback_compose_preview",
    "run_canary_restart_with_overlay",
    "run_controlled_apply",
    "run_controlled_apply_batch",
    "summarize_results",
    "validate_fleet_bindings",
    "validate_overlay_safety",
    "verify_runtime_effect",
    "write_compose_override_file",
]
