"""Pydantic schemas for strategy mutation sandbox operations.

Defines the data models for requesting, planning, and reporting on
strategy parameter mutations within a sandbox (no live mutation).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class StrategyParameterName(StrEnum):
    """Enum of strategy parameters that can be mutated in the sandbox."""

    RSI_PERIOD = "rsi_period"
    COOLDOWN_CANDLES = "cooldown_candles"


class StrategyMutationRequest(BaseModel):
    """Request payload to initiate a sandbox strategy mutation.

    Attributes:
        bot_id: Identifier of the trading bot.
        strategy_name: Name of the strategy to mutate.
        source_path: Path to the original strategy file (read-only reference).
        sandbox_root: Temporary directory for sandbox operations.
        parameter_changes: Mapping from parameter name to new integer value.
        candidate_sha: SHA hash of the mutation candidate parameters.
    """

    bot_id: str
    strategy_name: str
    source_path: Path
    sandbox_root: Path
    parameter_changes: dict[StrategyParameterName, int]
    candidate_sha: str


class StrategyMutationPlan(BaseModel):
    """Plan produced after copying strategy files into the sandbox.

    Attributes:
        source_path: Original strategy file path (unchanged).
        sandbox_path: Copy of the strategy file inside the sandbox.
        backup_path: Immutable backup copy of the original in the sandbox.
        diff_preview: Unified diff text between backup and sandbox copy.
        changed_parameters: List of parameters that were changed.
        validation_status: Current validation status (pending|passed|failed).
    """

    source_path: Path
    sandbox_path: Path
    backup_path: Path
    diff_preview: str = ""
    changed_parameters: list[StrategyParameterName] = Field(default_factory=list)
    validation_status: str = "pending"


class StrategyMutationResult(BaseModel):
    """Result of a sandbox mutation operation.

    Attributes:
        status: Final status — "ok" or "failed".
        reason: Human-readable reason for failure.
        plan: The mutation plan (None if setup failed before plan creation).
        compile_error: Python compile error text, if any.
        diff_text: Unified diff text between backup and mutated copy.
    """

    status: str
    reason: str = ""
    plan: StrategyMutationPlan | None = None
    compile_error: str | None = None
    diff_text: str = ""
