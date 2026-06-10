"""Pydantic v2 state schemas for Self-Improvement v2.

Defines all data models used across the SI v2 pipeline: safe parameters,
window stats, analysis results, approval gates, loop status, mutation
candidates, mutation overlays, backtest results, and bot configuration.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SafeParameters(BaseModel):
    """The 6 mutable parameters with strict validation ranges."""

    model_config = ConfigDict(strict=True)

    rsi_period: int = Field(ge=2, le=50, description="RSI calculation period")
    stoploss_pct: float = Field(ge=-0.5, le=-0.001, description="Stop-loss percentage (negative)")
    take_profit_pct: float = Field(ge=0.001, le=0.5, description="Take-profit percentage")
    stake_factor: float = Field(ge=0.1, le=5.0, description="Stake size multiplier")
    max_open_trades: int = Field(ge=1, le=20, description="Maximum concurrent open trades")
    cooldown_candles: int = Field(ge=0, le=100, description="Minimum candles between trades")


class WindowStats(BaseModel):
    """Per-window analysis statistics for a time window."""

    model_config = ConfigDict(strict=True)

    trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    pnl_abs: float = Field(default=0.0)
    profit_factor: float | None = Field(default=None, ge=0.0)
    max_drawdown_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    sharpe: float | None = Field(default=None)
    slippage_pct: float | None = Field(default=None, ge=0.0)
    consecutive_losses: int = Field(default=0, ge=0)


class AnalysisResult(BaseModel):
    """Full analysis output from the performance analyzer."""

    model_config = ConfigDict(strict=False)

    bot_id: str
    bot_name: str
    decision: str = Field(pattern=r"^(hold|mutate|block)$")
    mode: str = Field(default="proposal_only")
    risk_profile: str = Field(default="core_conservative")
    hard_blocks: list[str] = Field(default_factory=list)
    proposals: list[str] = Field(default_factory=list)
    latest_mutation_sha: str | None = Field(default=None)
    recent_mutation_review_notes: list[str] = Field(default_factory=list)
    windows: dict[str, WindowStats] = Field(default_factory=dict)
    ts: datetime


class ApprovalGate(BaseModel):
    """Approval state for a mutation candidate."""

    model_config = ConfigDict(strict=True)

    approved: bool
    candidate_sha256: str


class LoopStatus(BaseModel):
    """Per-bot loop tracking state."""

    model_config = ConfigDict(strict=False)

    alias: str
    bot_name: str
    container: str
    strategy: str
    status: str
    health_score_0_100: int = Field(ge=0, le=100)
    last_decision: str
    last_block_reason: str | None = Field(default=None)
    latest_candidate_sha: str | None = Field(default=None)
    requires_human_approval: bool = Field(default=False)
    stale_flags: list[str] = Field(default_factory=list)
    last_trade_export_ts: datetime | None = Field(default=None)
    last_analyze_ts: datetime | None = Field(default=None)
    last_backtest_ts: datetime | None = Field(default=None)
    last_mutation_ts: datetime | None = Field(default=None)
    last_deployment_check_ts: datetime | None = Field(default=None)
    updated_ts: datetime


class MutationCandidate(BaseModel):
    """Proposed configuration mutation for a bot."""

    model_config = ConfigDict(strict=True)

    schema_name: str = Field(default="self_improvement_candidate_v1", alias="schema")
    bot_id: str
    bot_name: str
    candidate_sha256: str
    mutation_policy: str = Field(default="safe_parameter_overlay_only")
    base_mode: str = Field(default="proposal_only")
    source_decision: str
    parameters: dict[str, float | int]
    active_overlay_candidates: dict[str, float | int]
    metadata_only_candidates: dict[str, int] = Field(default_factory=dict)
    requires_backtest: bool = Field(default=True)
    requires_paper_validation: bool = Field(default=True)
    requires_human_approval: bool = Field(default=True)
    requires_strategy_adapter: list[str] = Field(default_factory=list)
    guardrail_violations: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        strict=True,
        populate_by_name=True,
    )


class MutationOverlay(BaseModel):
    """Freqtrade overlay parameters applied to the live config."""

    model_config = ConfigDict(strict=True)

    max_open_trades: int = Field(ge=1, le=20)
    stake_amount: float = Field(gt=0)
    stoploss: float = Field(ge=-0.5, le=-0.001)
    minimal_roi: dict[str, float] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    """Backtest execution result."""

    model_config = ConfigDict(strict=True)

    bot_id: str
    candidate_sha256: str
    total_trades: int = Field(ge=0)
    profit_total_pct: float
    profit_total_abs: float
    max_drawdown_pct: float = Field(ge=0.0)
    win_rate_pct: float = Field(ge=0.0, le=100.0)
    sharpe: float | None = Field(default=None)
    profit_factor: float | None = Field(default=None)
    duration_seconds: float = Field(ge=0.0)
    passed: bool
    ts: datetime


class BotConfig(BaseModel):
    """Per-bot configuration from cron_defs."""

    model_config = ConfigDict(strict=True)

    bot_id: str
    bot_name: str
    alias: str
    container: str
    strategy: str
    schedules: dict[str, str] = Field(default_factory=dict)
