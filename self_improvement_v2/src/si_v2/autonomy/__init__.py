"""SI-v2 Autonomy Policy — policy-as-code for autonomous dry-run decisions.

This module is a pure decision layer. It does not:
- mutate any runtime state
- write files
- call Docker or Freqtrade
- access secrets or exchange keys

It evaluates a candidate against policy gates and returns a structured
decision: APPROVED, BLOCKED, or DEFERRED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from si_v2.propose.safe_parameters import FORBIDDEN_KEYS, SAFE_PARAMETERS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_IDS: Final[frozenset[str]] = frozenset({
    "freqtrade-freqforge-canary",
})

# Parameters that are safe for autonomous dry-run mutation
AUTONOMY_SAFE_PARAMETERS: Final[frozenset[str]] = frozenset(SAFE_PARAMETERS)

# Parameters that must never appear in an autonomous dry-run overlay
AUTONOMY_FORBIDDEN_KEYS: Final[frozenset[str]] = FORBIDDEN_KEYS | frozenset({
    "strategy",
    "pair_whitelist",
    "pair_blacklist",
    "telegram",
    "api_server",
    "db_url",
    "dry_run_wallet",
})

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutonomyPolicyInput:
    """All inputs needed for the autonomy policy to make a decision.

    Every field must be populated from real runtime evidence — no mocked,
    simulated, or hardcoded values.
    """

    candidate_id: str
    """Unique candidate identifier (e.g. ``max_open_trades_3_to_2``)."""

    candidate_sha: str
    """SHA-256 hash of the candidate content (evidence identity, not token)."""

    target_bot: str
    """Target bot ID (e.g. ``freqtrade-freqforge-canary``)."""

    hypothesis: str
    """Hypothesis being tested (e.g. ``reduce_max_open_trades``)."""

    parameter_overlay: dict[str, int | float]
    """Parameter changes to apply (e.g. ``{"max_open_trades": 2}``)."""

    source_cycle: str
    """Source cycle ID that produced this candidate."""

    confidence: float | None
    """Optional confidence score (0.0-1.0)."""

    dry_run_all_true: bool
    """True if ALL active fleet bots have ``dry_run=true``."""

    kill_switch_mode: str
    """Current kill switch mode (``NORMAL``, ``HALT_NEW``, ``EMERGENCY``)."""

    riskguard_status: str
    """Current RiskGuard status (``PASS``, ``FAIL``, ``UNKNOWN``)."""

    active_measurement_candidate_id: str | None
    """If a measurement window is active, the candidate ID being measured."""

    rollback_available: bool
    """True if a rollback plan exists and is importable."""

    allowlist_compatible: bool
    """True if the candidate is allowlist-compatible (no trading mutation)."""

    canary_first: bool
    """True if the target is a canary bot or the change is canary-first."""

    open_trades_on_target: int | None = None
    """Optional: current open trades count on the target bot."""


@dataclass(frozen=True)
class AutonomyPolicyDecision:
    """Structured decision from the autonomy policy."""

    status: Literal[
        "AUTO_DRY_RUN_APPROVED",
        "AUTO_DRY_RUN_BLOCKED",
        "AUTO_DRY_RUN_DEFERRED",
    ]
    candidate_id: str
    candidate_sha: str
    target_bot: str
    reasons: tuple[str, ...]
    required_next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "candidate_id": self.candidate_id,
            "candidate_sha": self.candidate_sha,
            "target_bot": self.target_bot,
            "reasons": list(self.reasons),
            "required_next_step": self.required_next_step,
        }


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------


def _check_dry_run(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.dry_run_all_true:
        return True, ""
    return False, (
        "dry_run_not_all_true: not all fleet bots have dry_run=true. "
        "Autonomous apply requires dry_run=true fleet-wide."
    )


def _check_kill_switch(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.kill_switch_mode == "NORMAL":
        return True, ""
    if input_.kill_switch_mode in ("HALT_NEW", "EMERGENCY"):
        return False, (
            f"kill_switch_{input_.kill_switch_mode.lower()}: "
            f"kill switch is {input_.kill_switch_mode!r}. "
            f"Autonomous apply requires NORMAL."
        )
    return False, (
        f"kill_switch_unknown: kill_switch_mode={input_.kill_switch_mode!r}. "
        f"Expected NORMAL, HALT_NEW, or EMERGENCY."
    )


def _check_riskguard(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.riskguard_status == "PASS":
        return True, ""
    return False, (
        f"riskguard_not_pass: riskguard_status={input_.riskguard_status!r}. "
        f"Autonomous apply requires PASS."
    )


def _check_canary_first(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.canary_first:
        return True, ""
    return False, (
        f"not_canary_first: target_bot={input_.target_bot!r} is not a canary "
        f"and canary_first=False. Autonomous apply requires canary-first."
    )


def _check_allowlist(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.allowlist_compatible:
        return True, ""
    return False, (
        "not_allowlist_compatible: candidate is not allowlist-compatible. "
        "Autonomous apply requires allowlist compatibility."
    )


def _check_rollback(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.rollback_available:
        return True, ""
    return False, (
        "rollback_not_available: no rollback plan exists. "
        "Autonomous apply requires a rollback plan."
    )


def _check_measurement_window(input_: AutonomyPolicyInput) -> tuple[bool, str, bool]:
    """Check measurement window. Returns (ok, reason, is_deferred)."""
    if input_.active_measurement_candidate_id is None:
        return True, "", False
    if input_.active_measurement_candidate_id == input_.candidate_id:
        return True, "already_measuring: this candidate is already in measurement", False
    return (
        False,
        f"measurement_active_for: {input_.active_measurement_candidate_id!r} — "
        f"defer new candidate {input_.candidate_id!r} until measurement completes",
        True,
    )


def _check_parameter_overlay(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if not input_.parameter_overlay:
        return False, "empty_parameter_overlay: no parameters to apply."
    for key in input_.parameter_overlay:
        if key in AUTONOMY_FORBIDDEN_KEYS:
            return False, (
                f"forbidden_parameter: {key!r} is in AUTONOMY_FORBIDDEN_KEYS."
            )
        if key not in AUTONOMY_SAFE_PARAMETERS:
            return False, (
                f"unsafe_parameter: {key!r} is not in AUTONOMY_SAFE_PARAMETERS."
            )
    return True, ""


def _check_target_bot(input_: AutonomyPolicyInput) -> tuple[bool, str]:
    if input_.target_bot in CANARY_BOT_IDS:
        return True, ""
    return False, (
        f"non_canary_target: {input_.target_bot!r} is not a recognized canary bot. "
        f"Autonomous apply requires a canary target."
    )


# ---------------------------------------------------------------------------
# Main policy function
# ---------------------------------------------------------------------------


def evaluate_autonomy_policy(
    input_: AutonomyPolicyInput,
) -> AutonomyPolicyDecision:
    """Evaluate a candidate against the autonomy policy.

    Returns a structured decision: APPROVED, BLOCKED, or DEFERRED.

    This function is pure — it does not mutate state, write files, or
    call external services.
    """
    reasons: list[str] = []

    # --- Hard blockers (BLOCKED) ---

    dry_ok, dry_reason = _check_dry_run(input_)
    if not dry_ok:
        reasons.append(dry_reason)

    ks_ok, ks_reason = _check_kill_switch(input_)
    if not ks_ok:
        reasons.append(ks_reason)

    rg_ok, rg_reason = _check_riskguard(input_)
    if not rg_ok:
        reasons.append(rg_reason)

    canary_ok, canary_reason = _check_canary_first(input_)
    if not canary_ok:
        reasons.append(canary_reason)

    allow_ok, allow_reason = _check_allowlist(input_)
    if not allow_ok:
        reasons.append(allow_reason)

    roll_ok, roll_reason = _check_rollback(input_)
    if not roll_ok:
        reasons.append(roll_reason)

    param_ok, param_reason = _check_parameter_overlay(input_)
    if not param_ok:
        reasons.append(param_reason)

    bot_ok, bot_reason = _check_target_bot(input_)
    if not bot_ok:
        reasons.append(bot_reason)

    if reasons:
        return AutonomyPolicyDecision(
            status="AUTO_DRY_RUN_BLOCKED",
            candidate_id=input_.candidate_id,
            candidate_sha=input_.candidate_sha,
            target_bot=input_.target_bot,
            reasons=tuple(reasons),
            required_next_step=(
                "Review blocked reasons. Fix policy violations before "
                "re-evaluating."
            ),
        )

    # --- Deferred checks ---

    _mw_ok, mw_reason, mw_deferred = _check_measurement_window(input_)
    if mw_deferred:
        return AutonomyPolicyDecision(
            status="AUTO_DRY_RUN_DEFERRED",
            candidate_id=input_.candidate_id,
            candidate_sha=input_.candidate_sha,
            target_bot=input_.target_bot,
            reasons=(mw_reason,),
            required_next_step=(
                f"Wait for measurement completion of "
                f"{input_.active_measurement_candidate_id!r}."
            ),
        )

    # --- All gates pass ---

    return AutonomyPolicyDecision(
        status="AUTO_DRY_RUN_APPROVED",
        candidate_id=input_.candidate_id,
        candidate_sha=input_.candidate_sha,
        target_bot=input_.target_bot,
        reasons=(),
        required_next_step=(
            "All policy gates pass. Candidate is approved for autonomous "
            "dry-run apply. Wire autonomous dry-run executor in Phase 6B."
        ),
    )
