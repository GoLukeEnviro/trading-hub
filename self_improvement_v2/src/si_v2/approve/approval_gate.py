"""Approval gate manager for human-in-the-loop review of mutations.

Provides the ApprovalGateManager which evaluates a backtest + walk-forward
result pair against a configurable set of guardrails. Phase D only knows
two outcomes: "rejected" (auto-rejected by guardrails) or "pending" (sent
to Telegram for human review). Auto-approval is impossible in Phase D and
the test suite enforces this invariant.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from si_v2.adapters.telegram_adapter import TelegramAdapter
from si_v2.backtest.walk_forward import WalkForwardResult
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate


class ApprovalStatus(StrEnum):
    """Possible approval outcomes in Phase D.

    NOTE: "approved" is deliberately NOT a member. Auto-approval is
    impossible in Phase D — only humans (or future phases) can approve
    a candidate.
    """

    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalConfig(BaseModel):
    """Configurable thresholds for the auto-rejection guardrails."""

    model_config = ConfigDict(strict=True)

    max_drawdown_pct: float = Field(default=0.15, ge=0.0, le=1.0)
    min_stability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    min_profit_factor: float = Field(default=1.0, ge=0.0)
    min_total_trades: int = Field(default=5, ge=0)


class ApprovalDecision(BaseModel):
    """The result of evaluating a candidate through the approval gate."""

    model_config = ConfigDict(strict=False)

    bot_id: str
    candidate_sha256: str
    status: ApprovalStatus
    reason: str
    auto_reject_reasons: list[str] = Field(default_factory=list)
    telegram_message_id: str | None = None


class ApprovalGateManager:
    """Manages the approval gate for mutation candidates.

    The manager is simulation-only — it never writes to live config
    paths and never starts/stops/restarts anything. It only:
      * evaluates a (backtest, walk-forward) pair against guardrails,
      * emits an ApprovalDecision (always "rejected" or "pending"), and
      * when pending, captures a Telegram message via the injected
        TelegramAdapter and writes a structured entry to the
        ShadowLogger.
    """

    def __init__(
        self,
        telegram_adapter: TelegramAdapter,
        approval_config: ApprovalConfig,
        shadow_logger: ShadowLogger,
    ) -> None:
        """Initialise with a TelegramAdapter, ApprovalConfig, and ShadowLogger.

        Args:
            telegram_adapter: Adapter used to capture approval requests.
            approval_config: Configurable guardrail thresholds.
            shadow_logger: Logger used to record approval decisions.
        """
        self._telegram_adapter = telegram_adapter
        self._approval_config = approval_config
        self._shadow_logger = shadow_logger

    def evaluate(
        self,
        backtest_result: BacktestResult,
        walk_forward_result: WalkForwardResult,
        bot_config: BotConfig,
        candidate: MutationCandidate,
    ) -> ApprovalDecision:
        """Evaluate a candidate and return an ApprovalDecision.

        Auto-rejects if ANY of the following are true:
          * backtest_result.passed is False,
          * walk_forward_result.passed is False,
          * backtest_result.profit_total_pct <= 0,
          * backtest_result.max_drawdown_pct >= approval_config.max_drawdown_pct,
          * walk_forward_result.stability_score < approval_config.min_stability_score,
          * backtest_result.total_trades < approval_config.min_total_trades,
          * walk_forward_result.reason contains "insufficient".

        If no auto-reject triggers, the decision status is "pending",
        a Telegram approval request is sent, and the decision is logged
        to the ShadowLogger. The returned ApprovalDecision has its
        telegram_message_id set.

        Auto-approve is impossible in Phase D — this method will never
        return ApprovalStatus.APPROVED (which is intentionally not a
        member of the enum).

        Args:
            backtest_result: Backtest result for the candidate.
            walk_forward_result: Walk-forward result for the candidate.
            bot_config: Bot configuration (used for context only).
            candidate: Mutation candidate being evaluated.

        Returns:
            An ApprovalDecision with status "rejected" or "pending".
        """
        del bot_config  # context only — guardrails are computed below

        cfg = self._approval_config
        reasons: list[str] = []

        if not backtest_result.passed:
            reasons.append("backtest.passed=False")
        if not walk_forward_result.passed:
            reasons.append("walk_forward.passed=False")
        if backtest_result.profit_total_pct <= 0:
            reasons.append(
                f"backtest.profit_total_pct={backtest_result.profit_total_pct} <= 0",
            )
        if backtest_result.max_drawdown_pct >= cfg.max_drawdown_pct:
            reasons.append(
                f"backtest.max_drawdown_pct={backtest_result.max_drawdown_pct} >= {cfg.max_drawdown_pct}",
            )
        if walk_forward_result.stability_score < cfg.min_stability_score:
            reasons.append(
                f"walk_forward.stability_score={walk_forward_result.stability_score} < {cfg.min_stability_score}",
            )
        if backtest_result.total_trades < cfg.min_total_trades:
            reasons.append(
                f"backtest.total_trades={backtest_result.total_trades} < {cfg.min_total_trades}",
            )
        if "insufficient" in walk_forward_result.reason:
            reasons.append("walk_forward.reason contains 'insufficient'")

        if reasons:
            decision = ApprovalDecision(
                bot_id=candidate.bot_id,
                candidate_sha256=candidate.candidate_sha256,
                status=ApprovalStatus.REJECTED,
                reason="; ".join(reasons),
                auto_reject_reasons=list(reasons),
                telegram_message_id=None,
            )
            self._shadow_logger.log(
                bot_id=candidate.bot_id,
                candidate_sha=candidate.candidate_sha256,
                params=dict(candidate.parameters),
                outcome="rejected",
                phase="approve",
                decision="block",
                reason=decision.reason,
            )
            return decision

        # No auto-reject: build a pending decision and send the approval
        # request. The Telegram adapter captures the message in memory
        # and never calls the real Telegram API.
        backtest_summary: dict[str, str | int | float] = {
            "profit_total_pct": backtest_result.profit_total_pct,
            "profit_total_abs": backtest_result.profit_total_abs,
            "max_drawdown_pct": backtest_result.max_drawdown_pct,
            "total_trades": backtest_result.total_trades,
            "win_rate_pct": backtest_result.win_rate_pct,
        }
        if backtest_result.sharpe is not None:
            backtest_summary["sharpe"] = backtest_result.sharpe
        if backtest_result.profit_factor is not None:
            backtest_summary["profit_factor"] = backtest_result.profit_factor

        walk_forward_summary: dict[str, str | int | float] = {
            "stability_score": walk_forward_result.stability_score,
            "passed": walk_forward_result.passed,
            "reason": walk_forward_result.reason,
        }

        risk_reason = (
            f"candidate {candidate.candidate_sha256} for {candidate.bot_id} "
            "passed all auto-guardrails; awaiting human review"
        )

        message = self._telegram_adapter.send_approval_request(
            chat_id_hint=f"approval:{candidate.bot_id}",
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            backtest_summary=backtest_summary,
            walk_forward_summary=walk_forward_summary,
            risk_reason=risk_reason,
        )

        decision = ApprovalDecision(
            bot_id=candidate.bot_id,
            candidate_sha256=candidate.candidate_sha256,
            status=ApprovalStatus.PENDING,
            reason="awaiting human approval",
            auto_reject_reasons=[],
            telegram_message_id=message.timestamp_utc,
        )

        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome="pending_human_approval",
            phase="approve",
            decision="pass",
            reason=decision.reason,
        )

        return decision
