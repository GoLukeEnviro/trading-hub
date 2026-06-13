"""SI v2 Phase 2 — Multi-bot fleet analyzer for the Self-Improvement Loop.

Takes the normalized per-bot evidence (produced by the multi-bot read cycle)
and produces per-bot ShadowProposal-or-NO_PROPOSAL decisions plus a
fleet-level summary.

Decision policy (deterministic, evidence-only):

  Per bot, we consider these signals in order:

    1. ping_ok
         True if /api/v1/ping returned HTTP 200 within the configured timeout.
         If False -> NO_PROPOSAL (reason="ping_failed"). The bot is
         unreachable; we have no telemetry to reason about.

    2. status_auth_outcome
         One of:
           - "NOT_ATTEMPTED"           (auth config absent in registry)
           - "YELLOW_MISSING_ENV_VARS" (env vars not set in session)
           - "FAILED"                  (login error / network)
           - "AUTHENTICATED"           (login succeeded)
           - "AUTHENTICATED_NO_STATUS" (login succeeded but /status
                                         fetch failed for reasons other
                                         than auth)
         This becomes part of the proposal metadata (no secret value).

    3. status_open_trades
         Number of open trades from /api/v1/status (0 if unknown).
         Used to gate the proposal hypothesis (cannot reason about
         behavior with no observed positions).

  Decision rules:

    A. If ping_ok AND (status_auth_outcome in {"NOT_ATTEMPTED",
       "YELLOW_MISSING_ENV_VARS", "AUTHENTICATED_NO_STATUS"}) ->
       emit a metadata-only ShadowProposal with hypothesis
       "telemetry_reachability_baseline_established". The proposal
       documents that the bot is reachable but full status telemetry
       is unavailable in this cycle. base_mode=proposal_only,
       requires_human_approval=True, parameters empty.

    B. If ping_ok AND status_auth_outcome == "AUTHENTICATED" ->
       emit a metadata-only ShadowProposal with hypothesis
       "telemetry_status_endpoint_observable_v1", recording
       status_open_trades as a metadata_only_candidate value.
       base_mode=proposal_only, requires_human_approval=True.

    C. If ping_ok AND status_auth_outcome == "FAILED" (login attempted
       but failed) -> NO_PROPOSAL with reason="auth_failed", because
       the evidence is ambiguous (we don't know if the bot is healthy
       or not).

    D. If not ping_ok -> NO_PROPOSAL with reason="ping_failed".

  All ShadowProposals are proposal_only with requires_human_approval=True
  and mutation_policy=safe_parameter_overlay_only. The runtime MUST NOT
  apply them without human approval.

  No bot's parameters are modified. No credentials are logged. The output
  is a fleet_decision dict ready to be passed to the existing
  shadow-only safety path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Final

# ------------------------------------------------------------------
# Decision constants
# ------------------------------------------------------------------
DECISION_SHADOW_PROPOSAL: Final[str] = "SHADOW_PROPOSAL"
DECISION_NO_PROPOSAL: Final[str] = "NO_PROPOSAL"

NO_PROPOSAL_REASON_PING_FAILED: Final[str] = "ping_failed"
NO_PROPOSAL_REASON_AUTH_FAILED: Final[str] = "auth_failed"
NO_PROPOSAL_REASON_MISSING_BOT_ID: Final[str] = "missing_bot_id"
NO_PROPOSAL_REASON_INVALID_EVIDENCE: Final[str] = "invalid_evidence"

PROPOSAL_HYPOTHESIS_REACHABILITY: Final[str] = "telemetry_reachability_baseline_established"
PROPOSAL_HYPOTHESIS_STATUS_OBSERVABLE: Final[str] = "telemetry_status_endpoint_observable_v1"

# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BotEvidence:
    """Normalized evidence for a single bot collected by the read phase.

    All fields are redacted / non-secret. Auth metadata references env-var
    names only; no credentials are stored here.
    """

    bot_id: str
    base_url: str
    auth_type: str
    username_env: str | None
    password_env: str | None
    ping_endpoint: str
    ping_status_code: int
    ping_ok: bool
    ping_response_summary: str
    status_endpoint: str
    status_status_code: int
    status_ok: bool
    status_response_summary: str
    status_auth_outcome: str
    status_open_trades: int
    missing_env_vars: tuple[str, ...]
    auth_error_summary: str
    fetched_at_utc: str


@dataclass(frozen=True)
class ShadowProposalDecision:
    """A single per-bot ShadowProposal decision.

    The proposal is metadata-only. base_mode is always "proposal_only".
    requires_human_approval is always True. parameters is always empty
    (the loop never proposes executable config changes from a single
    ping+status read).
    """

    decision_type: str  # DECISION_SHADOW_PROPOSAL or DECISION_NO_PROPOSAL
    bot_id: str
    candidate_sha256: str
    base_mode: str
    mutation_policy: str
    requires_human_approval: bool
    hypothesis: str
    parameters: dict[str, float | int]
    metadata_only_candidates: dict[str, int]
    evidence_summary: dict[str, Any]
    no_proposal_reason: str | None
    fetched_at_utc: str


@dataclass(frozen=True)
class FleetSummary:
    """Fleet-level summary across all processed bots."""

    total_bots: int
    ping_ok_count: int
    ping_failed_count: int
    status_authenticated_count: int
    status_yellow_missing_env_count: int
    status_failed_count: int
    shadow_proposal_count: int
    no_proposal_count: int
    fleet_verdict: str  # GREEN | YELLOW | RED
    fleet_verdict_reason: str
    runtime_mutations: int
    config_mutations: int
    live_trading_mutations: int


@dataclass(frozen=True)
class FleetDecision:
    """Aggregate fleet decision: per-bot proposals + fleet-level summary."""

    cycle_id: str
    generated_at_utc: str
    per_bot: list[ShadowProposalDecision] = field(default_factory=list)
    fleet_summary: FleetSummary | None = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _candidate_sha(bot_id: str, evidence: BotEvidence, hypothesis: str) -> str:
    """Deterministic short SHA256 for a ShadowProposal candidate."""
    payload = {
        "bot_id": bot_id,
        "hypothesis": hypothesis,
        "ping_status_code": evidence.ping_status_code,
        "status_auth_outcome": evidence.status_auth_outcome,
        "status_status_code": evidence.status_status_code,
        "status_open_trades": evidence.status_open_trades,
        "missing_env_vars": list(evidence.missing_env_vars),
        "fetched_at_utc": evidence.fetched_at_utc,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _evidence_summary(evidence: BotEvidence) -> dict[str, Any]:
    """Redacted, bounded evidence summary safe to embed in a proposal."""
    return {
        "bot_id": evidence.bot_id,
        "base_url": evidence.base_url,
        "auth_type": evidence.auth_type,
        "username_env": evidence.username_env,
        "password_env": evidence.password_env,
        "ping": {
            "endpoint": evidence.ping_endpoint,
            "status_code": evidence.ping_status_code,
            "ok": evidence.ping_ok,
            "response_summary": evidence.ping_response_summary[:200],
        },
        "status": {
            "endpoint": evidence.status_endpoint,
            "status_code": evidence.status_status_code,
            "ok": evidence.status_ok,
            "response_summary": evidence.status_response_summary[:200],
            "auth_outcome": evidence.status_auth_outcome,
            "open_trades": evidence.status_open_trades,
        },
        "missing_env_vars": list(evidence.missing_env_vars),
        "auth_error_summary": evidence.auth_error_summary[:200] if evidence.auth_error_summary else "",
        "fetched_at_utc": evidence.fetched_at_utc,
    }


# ------------------------------------------------------------------
# Decision logic
# ------------------------------------------------------------------


def _decide_one(evidence: BotEvidence) -> ShadowProposalDecision:
    """Apply decision rules A/B/C/D to a single bot's evidence."""
    if not evidence.bot_id or not isinstance(evidence.bot_id, str):
        return ShadowProposalDecision(
            decision_type=DECISION_NO_PROPOSAL,
            bot_id=evidence.bot_id or "<missing>",
            candidate_sha256="0" * 16,
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis="",
            parameters={},
            metadata_only_candidates={},
            evidence_summary=_evidence_summary(evidence),
            no_proposal_reason=NO_PROPOSAL_REASON_MISSING_BOT_ID,
            fetched_at_utc=evidence.fetched_at_utc,
        )

    # Rule D: ping failed -> no proposal
    if not evidence.ping_ok:
        return ShadowProposalDecision(
            decision_type=DECISION_NO_PROPOSAL,
            bot_id=evidence.bot_id,
            candidate_sha256=_candidate_sha(evidence.bot_id, evidence, "n/a"),
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis="",
            parameters={},
            metadata_only_candidates={},
            evidence_summary=_evidence_summary(evidence),
            no_proposal_reason=NO_PROPOSAL_REASON_PING_FAILED,
            fetched_at_utc=evidence.fetched_at_utc,
        )

    outcome = evidence.status_auth_outcome

    # Rule B: fully authenticated
    if outcome == "AUTHENTICATED":
        hypothesis = PROPOSAL_HYPOTHESIS_STATUS_OBSERVABLE
        sha = _candidate_sha(evidence.bot_id, evidence, hypothesis)
        return ShadowProposalDecision(
            decision_type=DECISION_SHADOW_PROPOSAL,
            bot_id=evidence.bot_id,
            candidate_sha256=sha,
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis=hypothesis,
            parameters={},
            metadata_only_candidates={
                "status_endpoint_observable": 1,
                "open_trades_observed": int(evidence.status_open_trades),
            },
            evidence_summary=_evidence_summary(evidence),
            no_proposal_reason=None,
            fetched_at_utc=evidence.fetched_at_utc,
        )

    # Rule A: ping ok but status telemetry unavailable in this cycle
    if outcome in {"NOT_ATTEMPTED", "YELLOW_MISSING_ENV_VARS", "AUTHENTICATED_NO_STATUS"}:
        hypothesis = PROPOSAL_HYPOTHESIS_REACHABILITY
        sha = _candidate_sha(evidence.bot_id, evidence, hypothesis)
        return ShadowProposalDecision(
            decision_type=DECISION_SHADOW_PROPOSAL,
            bot_id=evidence.bot_id,
            candidate_sha256=sha,
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis=hypothesis,
            parameters={},
            metadata_only_candidates={
                "ping_reachable": 1,
                "status_auth_outcome_observed": 1,
            },
            evidence_summary=_evidence_summary(evidence),
            no_proposal_reason=None,
            fetched_at_utc=evidence.fetched_at_utc,
        )

    # Rule C: auth attempted and failed
    if outcome == "FAILED":
        return ShadowProposalDecision(
            decision_type=DECISION_NO_PROPOSAL,
            bot_id=evidence.bot_id,
            candidate_sha256=_candidate_sha(evidence.bot_id, evidence, "n/a"),
            base_mode="proposal_only",
            mutation_policy="safe_parameter_overlay_only",
            requires_human_approval=True,
            hypothesis="",
            parameters={},
            metadata_only_candidates={},
            evidence_summary=_evidence_summary(evidence),
            no_proposal_reason=NO_PROPOSAL_REASON_AUTH_FAILED,
            fetched_at_utc=evidence.fetched_at_utc,
        )

    # Unknown outcome -> treat as insufficient evidence
    return ShadowProposalDecision(
        decision_type=DECISION_NO_PROPOSAL,
        bot_id=evidence.bot_id,
        candidate_sha256=_candidate_sha(evidence.bot_id, evidence, "n/a"),
        base_mode="proposal_only",
        mutation_policy="safe_parameter_overlay_only",
        requires_human_approval=True,
        hypothesis="",
        parameters={},
        metadata_only_candidates={},
        evidence_summary=_evidence_summary(evidence),
        no_proposal_reason=NO_PROPOSAL_REASON_INVALID_EVIDENCE,
        fetched_at_utc=evidence.fetched_at_utc,
    )


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def analyze_fleet(evidence_list: list[BotEvidence], cycle_id: str) -> FleetDecision:
    """Apply per-bot decision logic and compute the fleet-level summary.

    Args:
        evidence_list: Normalized per-bot evidence (one entry per bot from
                       the registry). The list should contain one entry
                       per enabled bot; ordering is preserved.
        cycle_id: Stable identifier for this Self-Improvement cycle
                  (e.g. ISO timestamp, used for traceability).

    Returns:
        A FleetDecision with per-bot decisions and a fleet_summary.

    The function does not perform I/O. It does not call any Freqtrade
    endpoint. It does not mutate any external state. It is safe to call
    from tests with synthetic evidence.
    """
    from datetime import UTC, datetime

    per_bot: list[ShadowProposalDecision] = [_decide_one(ev) for ev in evidence_list]

    total = len(per_bot)
    ping_ok = sum(1 for d in per_bot if d.evidence_summary["ping"]["ok"])
    ping_failed = total - ping_ok
    status_auth = sum(
        1
        for d in per_bot
        if d.evidence_summary["status"]["auth_outcome"] == "AUTHENTICATED"
    )
    status_yellow_missing = sum(
        1
        for d in per_bot
        if d.evidence_summary["status"]["auth_outcome"] == "YELLOW_MISSING_ENV_VARS"
    )
    status_failed = sum(
        1
        for d in per_bot
        if d.evidence_summary["status"]["auth_outcome"] == "FAILED"
    )
    shadow_proposal = sum(1 for d in per_bot if d.decision_type == DECISION_SHADOW_PROPOSAL)
    no_proposal = total - shadow_proposal

    # Fleet verdict:
    #   GREEN: all 4 bots ping_ok AND all 4 produced a decision (proposal or NO_PROPOSAL)
    #   YELLOW: at least one bot missing env vars OR partial ping success
    #   RED:    no bots processed at all OR >50% ping failure
    if total == 0:
        verdict = "RED"
        reason = "no bots were processed in this cycle"
    elif ping_ok == 0:
        verdict = "RED"
        reason = f"all {total} bots failed /api/v1/ping; no telemetry collected"
    elif status_failed == total:
        verdict = "RED"
        reason = f"all {total} bots had auth failure; no decision evidence available"
    elif status_yellow_missing == total:
        verdict = "YELLOW"
        reason = (
            f"all {total} bots reachable (/ping=200) but JWT env vars not set; "
            f"loop logic executed with reachability-only evidence"
        )
    elif status_yellow_missing > 0 or status_failed > 0 or (shadow_proposal + no_proposal) < total:
        verdict = "YELLOW"
        reason = (
            f"partial success: {ping_ok}/{total} ping_ok, "
            f"{status_yellow_missing} missing env, {status_failed} auth failed"
        )
    else:
        verdict = "GREEN"
        reason = f"all {total} bots authenticated and decisions generated"

    summary = FleetSummary(
        total_bots=total,
        ping_ok_count=ping_ok,
        ping_failed_count=ping_failed,
        status_authenticated_count=status_auth,
        status_yellow_missing_env_count=status_yellow_missing,
        status_failed_count=status_failed,
        shadow_proposal_count=shadow_proposal,
        no_proposal_count=no_proposal,
        fleet_verdict=verdict,
        fleet_verdict_reason=reason,
        runtime_mutations=0,
        config_mutations=0,
        live_trading_mutations=0,
    )

    return FleetDecision(
        cycle_id=cycle_id,
        generated_at_utc=datetime.now(UTC).isoformat(),
        per_bot=per_bot,
        fleet_summary=summary,
    )


def fleet_decision_to_dict(decision: FleetDecision) -> dict[str, Any]:
    """Serialize a FleetDecision to a JSON-safe dict.

    The output is suitable for writing to the evidence bundle JSON
    (no secrets, bounded fields). The ShadowLogger is fed from this
    dict, not the raw evidence, to guarantee no secret values are
    ever logged.
    """
    return {
        "cycle_id": decision.cycle_id,
        "generated_at_utc": decision.generated_at_utc,
        "per_bot": [asdict(d) for d in decision.per_bot],
        "fleet_summary": asdict(decision.fleet_summary) if decision.fleet_summary else None,
    }
