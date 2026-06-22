"""SI v2 Strategy Codex.

A machine-readable, evidence-gated registry for trading strategies.

The codex provides:
- structured strategy definitions with required and optional fields
- controlled promotion statuses (draft → candidate → shadow → paper_live)
- evidence-gated promotion rules: no strategy may be candidate or higher
  without explicit evidence references
- JSON-safe serialization for integration with SI v2 proposal/evaluation loops

Safety:
- no exchange I/O
- no live trading
- no runtime mutation
- no Freqtrade strategy file writes
- no Docker/Compose/Cron changes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


# -- Status enums ----------------------------------------------------------

class PromotionStatus(StrEnum):
    """Controlled promotion lifecycle for a strategy.

    Rules:
    - `draft` and `blocked` are safe starting states.
    - `candidate`, `shadow`, and `paper_live` require evidence_refs.
    - `retired` is terminal.
    - Promotion status may only advance when evidence gates are met.
    """

    DRAFT = "draft"
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PAPER_LIVE = "paper_live"
    BLOCKED = "blocked"
    RETIRED = "retired"


class EvidenceStatus(StrEnum):
    """Status for backtest, walk-forward, and paper-trading evidence.

    `insufficient_evidence` is the default for strategies that have not yet
    been tested or whose results are inconclusive.
    """

    NOT_RUN = "not_run"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# -- Promotion helpers -----------------------------------------------------

_EVIDENCE_REQUIRED_STATUSES: frozenset[PromotionStatus] = frozenset(
    {PromotionStatus.CANDIDATE, PromotionStatus.SHADOW, PromotionStatus.PAPER_LIVE}
)


def _promotion_requires_evidence(status: PromotionStatus) -> bool:
    return status in _EVIDENCE_REQUIRED_STATUSES


_VALID_STRATEGY_ID_RE = r"^strat_[a-z]{2,8}_[0-9]{2}$"


# -- Strategy dataclass ----------------------------------------------------

@dataclass(slots=True)
class Strategy:
    """A single trading strategy definition in the codex.

    All fields must be populated.  Status fields default to the most
    conservative value.  Evidence refs default to empty — strategies without
    evidence are blocked from promotion beyond `draft`.
    """

    strategy_id: str
    name: str
    market_scope: str
    timeframe_scope: str

    # Logic
    entry_logic: str
    exit_logic: str
    risk_model: str

    # Requirements
    required_indicators: list[str] = field(default_factory=list)
    minimum_data_requirements: str = ""

    # Quality / diagnostics
    known_failure_modes: list[str] = field(default_factory=list)

    # Evidence statuses — all start as `not_run`
    backtest_status: EvidenceStatus = EvidenceStatus.NOT_RUN
    walk_forward_status: EvidenceStatus = EvidenceStatus.NOT_RUN
    paper_trading_status: EvidenceStatus = EvidenceStatus.NOT_RUN
    test_coverage_status: EvidenceStatus = EvidenceStatus.NOT_RUN

    # Promotion — conservative default
    promotion_status: PromotionStatus = PromotionStatus.DRAFT

    # Supporting evidence
    evidence_refs: list[str] = field(default_factory=list)

    def validate_promotion(self) -> list[str]:
        """Return a list of validation errors if promotion is invalid.

        An empty list means the promotion state is consistent with evidence.
        """
        errors: list[str] = []
        if _promotion_requires_evidence(self.promotion_status) and not self.evidence_refs:
            errors.append(
                f"strategy {self.strategy_id!r} has promotion_status="
                f"{self.promotion_status.value!r} but no evidence_refs"
            )
        return errors

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "market_scope": self.market_scope,
            "timeframe_scope": self.timeframe_scope,
            "entry_logic": self.entry_logic,
            "exit_logic": self.exit_logic,
            "risk_model": self.risk_model,
            "required_indicators": list(self.required_indicators),
            "minimum_data_requirements": self.minimum_data_requirements,
            "known_failure_modes": list(self.known_failure_modes),
            "backtest_status": self.backtest_status.value,
            "walk_forward_status": self.walk_forward_status.value,
            "paper_trading_status": self.paper_trading_status.value,
            "test_coverage_status": self.test_coverage_status.value,
            "promotion_status": self.promotion_status.value,
            "evidence_refs": list(self.evidence_refs),
        }


# -- Codex registry --------------------------------------------------------

@dataclass
class StrategyCodex:
    """Ordered registry of Strategy definitions.

    Maintains uniqueness of strategy IDs and provides validation
    across the entire registry.
    """

    strategies: list[Strategy] = field(default_factory=list)

    def __iter__(self) -> Iterator[Strategy]:
        return iter(self.strategies)

    def __len__(self) -> int:
        return len(self.strategies)

    def __bool__(self) -> bool:
        return bool(self.strategies)

    def add(self, strategy: Strategy) -> None:
        """Register a strategy.  Raises ValueError on duplicate ID."""
        existing_ids = {s.strategy_id for s in self.strategies}
        if strategy.strategy_id in existing_ids:
            raise ValueError(
                f"duplicate strategy_id {strategy.strategy_id!r}"
            )
        self.strategies.append(strategy)

    def validate_ids_unique(self) -> list[str]:
        """Check for duplicate strategy IDs.  Returns list of errors."""
        seen: set[str] = set()
        errors: list[str] = []
        for s in self.strategies:
            if s.strategy_id in seen:
                errors.append(f"duplicate strategy_id {s.strategy_id!r}")
            seen.add(s.strategy_id)
        return errors

    def validate_promotions(self) -> list[str]:
        """Check all strategies for invalid promotion states."""
        errors: list[str] = []
        for s in self.strategies:
            errors.extend(s.validate_promotion())
        return errors

    def find(self, strategy_id: str) -> Strategy | None:
        """Look up a strategy by ID."""
        for s in self.strategies:
            if s.strategy_id == strategy_id:
                return s
        return None

    def to_dict(self) -> dict[str, object]:
        """Serialize the full codex to a JSON-safe dictionary."""
        return {
            "strategies": [s.to_dict() for s in self.strategies],
            "count": len(self.strategies),
        }


# -- Initial strategies ----------------------------------------------------

def create_initial_codex() -> StrategyCodex:
    """Create a codex populated with the three initial strategies.

    All start in `draft` with no evidence — the safest possible state.
    """
    codex = StrategyCodex()

    # -- strat_btc_01 -------------------------------------------------------
    codex.add(
        Strategy(
            strategy_id="strat_btc_01",
            name="BTC Pullback Bounce",
            market_scope="BTC/USDT",
            timeframe_scope="5m, 15m",
            entry_logic=(
                "Enter long when price pulls back to a key support level "
                "(e.g., 20 EMA, previous swing low) and shows a bullish "
                "reversal candle pattern with volume confirmation. "
                "RSI should be above 30 and recovering."
            ),
            exit_logic=(
                "Exit on take-profit at the next resistance level or "
                "on stop-loss breach below the entry swing low. "
                "Trailing stop may be used after price moves 1R in profit. "
                "Exit immediately if volume dries up during rally."
            ),
            risk_model=(
                "Fixed 1% account risk per trade. Stop-loss placed below "
                "the entry swing low. Take-profit set at 2:1 reward-to-risk "
                "minimum. Maximum 1 concurrent BTC position."
            ),
            required_indicators=["EMA_20", "RSI_14", "volume"],
            minimum_data_requirements=(
                "Minimum 100 candles at entry timeframe. "
                "Volume data required. OHLCV must be complete."
            ),
            known_failure_modes=[
                "False breakout from support in ranging market",
                "Volume spike without follow-through",
                "News-driven gap through stop-loss level",
            ],
        )
    )

    # -- strat_eth_01 -------------------------------------------------------
    codex.add(
        Strategy(
            strategy_id="strat_eth_01",
            name="ETH Momentum Break",
            market_scope="ETH/USDT",
            timeframe_scope="15m, 1h",
            entry_logic=(
                "Enter long when ETH breaks above a consolidation range "
                "with momentum confirmation. Requires: price above 50 EMA, "
                "ADX > 25 and rising, volume > 1.5x 20-period average. "
                "Breakout candle must close above resistance."
            ),
            exit_logic=(
                "Take-profit at measured move target (range height added "
                "to breakout level). Stop-loss below breakout level or "
                "below 50 EMA, whichever is tighter. Trail stop after 1.5R. "
                "Exit if ADX drops below 20 (momentum failure)."
            ),
            risk_model=(
                "Fixed 1.5% account risk per trade. Stop-loss based on ATR "
                "(2x ATR from entry). Maximum 1 concurrent ETH position. "
                "Reduce risk to 1% if volatility (ATR/price) exceeds 5%."
            ),
            required_indicators=["EMA_50", "ADX_14", "ATR_14", "volume"],
            minimum_data_requirements=(
                "Minimum 150 candles at entry timeframe. "
                "ATR and ADX must have sufficient history (period + 20). "
                "Volume data required."
            ),
            known_failure_modes=[
                "Fake breakout in low-liquidity periods",
                "Momentum exhaustion before reaching target",
                "ADX whipsaw in choppy markets",
            ],
        )
    )

    # -- strat_sol_01 -------------------------------------------------------
    codex.add(
        Strategy(
            strategy_id="strat_sol_01",
            name="SOL Volume Spike Reversal",
            market_scope="SOL/USDT",
            timeframe_scope="5m, 15m",
            entry_logic=(
                "Enter long after a sharp sell-off when volume spikes > 3x "
                "the 20-period average and price forms a bullish reversal "
                "candle (hammer, engulfing). RSI must be oversold (< 30) "
                "and beginning to recover. Entry on next candle open "
                "after reversal confirmation."
            ),
            exit_logic=(
                "Take-profit at the 20 EMA or previous support-turned-"
                "resistance level. Stop-loss below the reversal candle "
                "low. Trail stop to breakeven after 1R. Exit if volume "
                "returns to below-average without price follow-through."
            ),
            risk_model=(
                "Fixed 1% account risk per trade. Stop-loss placed below "
                "the reversal candle low minus 1 tick. Maximum 1 concurrent "
                "SOL position. Re-entry cooldown of 30 minutes after a "
                "stop-out to avoid overtrading."
            ),
            required_indicators=["EMA_20", "RSI_14", "volume"],
            minimum_data_requirements=(
                "Minimum 200 candles at entry timeframe. "
                "Volume data required. RSI must have 14-period history."
            ),
            known_failure_modes=[
                "Catching a falling knife — trend continuation after spike",
                "Volume spike from exchange liquidation cascade, not organic",
                "RSI staying oversold for extended period in strong downtrend",
            ],
        )
    )

    return codex
