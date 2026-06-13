"""SI v2 Active Cycle Runner — cycle state persistence.

Manages the durable cycle state artifact that connects a run of the
active cycle runner to the future measurement/attribution step.

Schema semantics:
    - A ``CycleState`` is written once per active cycle run.
    - It is immutable after writing (the active cycle runner never
      overwrites a cycle state).
    - It is the single source of truth for what the cycle observed,
      what it decided, and what the mutation counters were.
    - Subsequent measurement/attribution steps read the latest
      cycle state to compute delta against previous cycles.

File layout:
    ``self_improvement_v2/reports/phase2/cycle_state/``
        ``active_cycle_<cycle_id>.state.json``  — current cycle state
        ``active_cycle_latest.state.json``       — symlink to latest
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from si_v2.loop.fleet_analyzer import FleetDecision

# Type alias for pydantic's ExtraValues
_ExtraValues = Literal["allow", "ignore", "forbid"] | None

CYCLE_STATE_SCHEMA_VERSION: str = "cycle_state_v1"

# ------------------------------------------------------------------
# Typed cycle state
# ------------------------------------------------------------------


class PerBotDecisionState(BaseModel):
    """Decision state for one bot in one cycle."""

    model_config = ConfigDict(strict=True, extra="forbid")

    bot_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)  # SHADOW_PROPOSAL | NO_PROPOSAL
    candidate_sha256: str = Field(default="")
    hypothesis: str = Field(default="")
    no_proposal_reason: str | None = None
    approval_status: str = Field(default="PENDING_HUMAN")


class CycleState(BaseModel):
    """Immutable cycle state artifact for one active cycle run.

    This model is the contract between:
      - ``active_cycle_runner.py`` (writes it)
      - future measurement/attribution step (reads it)

    Fields:
        schema_version: Version of this schema.
        cycle_id: Stable identifier for this cycle (e.g. ISO timestamp).
        generated_at_utc: ISO 8601 timestamp.
        branch: Git branch at time of cycle.
        commit_sha: Git commit SHA at time of cycle.
        total_bots: Number of bots processed.
        ping_ok_count: Number of bots with successful /ping.
        ping_failed_count: Number of bots with failed /ping.
        shadow_proposal_count: How many bots received a SHADOW_PROPOSAL.
        no_proposal_count: How many bots received a NO_PROPOSAL.
        fleet_verdict: GREEN | YELLOW | RED.
        fleet_verdict_reason: Human-readable reason.
        per_bot_decisions: One entry per bot, in registry order.
        runtime_mutations: Always 0 (this step never mutates).
        config_mutations: Always 0.
        live_trading_mutations: Always 0.
        docker_mutations: Always 0.
        strategy_mutations: Always 0.
        controller_state: Always "PAUSED / L3_REPOSITORY_ONLY".
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = CYCLE_STATE_SCHEMA_VERSION
    cycle_id: str = Field(min_length=1)
    generated_at_utc: str = Field(min_length=1)
    branch: str = Field(default="")
    commit_sha: str = Field(default="")

    total_bots: int = Field(ge=0)
    ping_ok_count: int = Field(ge=0)
    ping_failed_count: int = Field(ge=0)
    shadow_proposal_count: int = Field(ge=0)
    no_proposal_count: int = Field(ge=0)
    fleet_verdict: str = Field(min_length=1)  # GREEN | YELLOW | RED
    fleet_verdict_reason: str = Field(default="")

    per_bot_decisions: tuple[PerBotDecisionState, ...] = Field(default_factory=tuple)

    @classmethod
    def _coerce_per_bot(cls, data: dict[str, object]) -> dict[str, object]:
        """Coerce per_bot_decisions from list to tuple if needed."""
        if "per_bot_decisions" in data and isinstance(data["per_bot_decisions"], list):
            data["per_bot_decisions"] = tuple(data["per_bot_decisions"])
        return data

    @classmethod
    def model_validate(
        cls,
        obj: object,
        *,
        strict: bool | None = None,
        extra: _ExtraValues = None,
        from_attributes: bool | None = None,
        context: object = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> CycleState:
        """Wrap model_validate to coerce list->tuple for per_bot_decisions."""
        if isinstance(obj, dict):
            obj = cls._coerce_per_bot(obj)
        return super().model_validate(
            obj,
            strict=strict,
            extra=extra,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    # Mutation counters — always zero for active cycle runner
    runtime_mutations: int = Field(ge=0, default=0)
    config_mutations: int = Field(ge=0, default=0)
    live_trading_mutations: int = Field(ge=0, default=0)
    docker_mutations: int = Field(ge=0, default=0)
    strategy_mutations: int = Field(ge=0, default=0)

    # Controller state
    controller_state: str = Field(default="PAUSED / L3_REPOSITORY_ONLY")


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


def _default_state_dir(repo_root: Path | None = None) -> Path:
    """Return the default cycle state directory."""
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "self_improvement_v2" / "reports" / "phase2" / "cycle_state"


def persist_cycle_state(
    state: CycleState,
    state_dir: Path | None = None,
    *,
    create_symlink: bool = True,
) -> Path:
    """Persist a cycle state to disk.

    Writes one JSON file per cycle and creates/updates a symlink to
    the latest state.

    Args:
        state: The cycle state to persist.
        state_dir: Target directory. Defaults to
            ``self_improvement_v2/reports/phase2/cycle_state/``.
        create_symlink: If True (default), create/update a
            ``active_cycle_latest.state.json`` symlink.

    Returns:
        The path to the written state file.

    Raises:
        OSError: If the file cannot be written.
    """
    dir_path = state_dir or _default_state_dir()
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = f"active_cycle_{state.cycle_id}.state.json"
    filepath = dir_path / filename

    # Write state file
    with open(filepath, "w") as f:
        json.dump(state.model_dump(mode="json"), f, indent=2, sort_keys=True)

    # Create/update symlink to latest
    if create_symlink:
        latest_path = dir_path / "active_cycle_latest.state.json"
        try:
            if latest_path.exists() or latest_path.is_symlink():
                latest_path.unlink()
            os.symlink(filename, latest_path)
        except OSError:
            # Symlink creation is best-effort (may fail on some filesystems)
            pass

    return filepath


def load_cycle_state(state_path: Path) -> CycleState:
    """Load a cycle state from disk.

    Args:
        state_path: Path to a ``.state.json`` file.

    Returns:
        The deserialized ``CycleState``.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not valid cycle state.
    """
    with open(state_path) as f:
        raw = json.load(f)
    return CycleState.model_validate(raw)


def load_latest_cycle_state(
    state_dir: Path | None = None,
) -> CycleState | None:
    """Load the latest cycle state from the symlink.

    Args:
        state_dir: Target directory. Defaults to the standard path.

    Returns:
        The deserialized ``CycleState``, or None if no latest state exists.
    """
    dir_path = state_dir or _default_state_dir()
    latest_path = dir_path / "active_cycle_latest.state.json"

    if not (latest_path.exists() or latest_path.is_symlink()):
        return None

    try:
        return load_cycle_state(latest_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------------
# Builder helper
# ------------------------------------------------------------------


def build_cycle_state(
    cycle_id: str,
    branch: str,
    commit_sha: str,
    fleet_decision: FleetDecision,  # FleetDecision from fleet_analyzer
    per_bot_decisions_raw: list[dict[str, object]],
) -> CycleState:
    """Build a ``CycleState`` from the fleet analyzer output.

    Args:
        cycle_id: Stable cycle identifier.
        branch: Git branch name.
        commit_sha: Git commit SHA.
        fleet_decision: ``FleetDecision`` from ``analyze_fleet()``.
        per_bot_decisions_raw: List of raw per-bot decision dicts
            (``asdict()`` results from ``ShadowProposalDecision``).

    Returns:
        A populated ``CycleState`` ready for persistence.
    """
    summary = fleet_decision.fleet_summary
    if summary is None:
        raise ValueError("fleet_decision has no fleet_summary")

    per_bot: list[PerBotDecisionState] = []
    for raw in per_bot_decisions_raw:
        bot_id = raw.get("bot_id", "")
        decision_type = raw.get("decision_type", "NO_PROPOSAL")
        candidate_sha256 = raw.get("candidate_sha256", "")
        hypothesis = raw.get("hypothesis", "")
        no_proposal_reason = raw.get("no_proposal_reason")
        per_bot.append(
            PerBotDecisionState(
                bot_id=bot_id if isinstance(bot_id, str) else str(bot_id),
                decision_type=decision_type if isinstance(decision_type, str) else str(decision_type),
                candidate_sha256=(
                    candidate_sha256 if isinstance(candidate_sha256, str)
                    else str(candidate_sha256)
                ),
                hypothesis=hypothesis if isinstance(hypothesis, str) else str(hypothesis),
                no_proposal_reason=(
                    no_proposal_reason
                    if isinstance(no_proposal_reason, str)
                    else str(no_proposal_reason) if no_proposal_reason is not None
                    else None
                ),
                approval_status="PENDING_HUMAN",
            )
        )

    return CycleState(
        cycle_id=cycle_id,
        generated_at_utc=datetime.now(UTC).isoformat(),
        branch=branch,
        commit_sha=commit_sha,
        total_bots=summary.total_bots,
        ping_ok_count=summary.ping_ok_count,
        ping_failed_count=summary.ping_failed_count,
        shadow_proposal_count=summary.shadow_proposal_count,
        no_proposal_count=summary.no_proposal_count,
        fleet_verdict=summary.fleet_verdict,
        fleet_verdict_reason=summary.fleet_verdict_reason,
        per_bot_decisions=tuple(per_bot),
        runtime_mutations=0,
        config_mutations=0,
        live_trading_mutations=0,
        docker_mutations=0,
        strategy_mutations=0,
        controller_state="PAUSED / L3_REPOSITORY_ONLY",
    )


# ------------------------------------------------------------------
# CLI helper
# ------------------------------------------------------------------


def print_cycle_state(state: CycleState) -> str:
    """Render a cycle state as a human-readable summary string.

    Args:
        state: The cycle state to render.

    Returns:
        A multi-line string summary.
    """
    lines: list[str] = [
        f"Cycle ID:          {state.cycle_id}",
        f"Generated:         {state.generated_at_utc}",
        f"Branch:            {state.branch}",
        f"Commit SHA:        {state.commit_sha}",
        "",
        f"Total bots:        {state.total_bots}",
        f"Ping OK:           {state.ping_ok_count}",
        f"Ping FAIL:         {state.ping_failed_count}",
        f"Shadow Proposals:  {state.shadow_proposal_count}",
        f"No Proposals:      {state.no_proposal_count}",
        f"Fleet Verdict:     {state.fleet_verdict}",
        f"Reason:            {state.fleet_verdict_reason}",
        "",
        f"Runtime mutations:   {state.runtime_mutations}",
        f"Config mutations:    {state.config_mutations}",
        f"Live-trading mut.:   {state.live_trading_mutations}",
        f"Docker mutations:    {state.docker_mutations}",
        f"Strategy mutations:  {state.strategy_mutations}",
        f"Controller state:    {state.controller_state}",
        "",
        "Per-bot decisions:",
    ]
    for d in state.per_bot_decisions:
        lines.append(
            f"  - {d.bot_id}: {d.decision_type} (SHA={d.candidate_sha256[:8]}, "
            f"approval={d.approval_status})"
        )
    return "\n".join(lines) + "\n"
