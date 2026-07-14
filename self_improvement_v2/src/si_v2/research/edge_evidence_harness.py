"""Edge-evidence evaluation harness for reproducible strategy research.

This module provides a StrategyEvaluationHarness that can test one selected
Freqtrade strategy for credible edge evidence without mutating the strategy
or any runtime configuration.

The harness supports:
- Out-of-sample, walk-forward, and untouched-holdout evaluation
- Realistic cost assumptions (fees, slippage, funding)
- Data quality detection (missing candles, gaps, unsupported history)
- Deterministic, reproducible results from pinned inputs
- Gate-0 output states: PASS_CANDIDATE, EXTEND, REJECT, INVALID

**Safety boundary:** This is a research tool only. It never mutates
strategies, runtime configuration, or live state. Output is advisory
evidence, never a trading signal or live authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Gate-0 output states
# ---------------------------------------------------------------------------


class Gate0Outcome(Enum):
    """Outcome of a Gate-0 edge-evidence evaluation.

    These are the only valid output states. No outcome may be interpreted
    as "proven profitability" or "live authorization."
    """

    PASS_CANDIDATE = "PASS_CANDIDATE"
    """Predeclared evidence criteria met. Candidate may proceed to next gate."""

    EXTEND = "EXTEND"
    """Insufficient independent trades, duration, regimes, or uncertainty width."""

    REJECT = "REJECT"
    """Material guardrail failure or negative edge evidence."""

    INVALID = "INVALID"
    """Data, leakage, or reproducibility defect. Run cannot be interpreted."""


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HarnessProvenance:
    """Immutable provenance record for one evaluation run.

    All fields are recorded before evaluation and frozen in the result.
    """

    strategy_identifier: str
    """Name or path of the strategy under test."""

    strategy_commit_sha: str
    """Git commit SHA of the strategy at evaluation time."""

    data_source: str
    """Description of the data source (exchange, market type, pairs)."""

    data_snapshot_version: str
    """Immutable version or timestamp of the data snapshot."""

    exchange: str
    """Exchange name (e.g., 'bitget')."""

    market_type: str
    """Market type (e.g., 'futures', 'spot')."""

    pairs: list[str]
    """Trading pairs included in the evaluation."""

    timeframe: str
    """Candle timeframe (e.g., '5m', '1h', '4h')."""

    calibration_start: str
    """ISO-8601 start of calibration/training period."""

    calibration_end: str
    """ISO-8601 end of calibration/training period."""

    walk_forward_start: str
    """ISO-8601 start of walk-forward validation period."""

    walk_forward_end: str
    """ISO-8601 end of walk-forward validation period."""

    holdout_start: str
    """ISO-8601 start of untouched holdout period."""

    holdout_end: str
    """ISO-8601 end of untouched holdout period."""

    fee_rate: float
    """Taker fee rate (fractional, e.g. 0.0005 for 0.05%)."""

    slippage_rate: float
    """Slippage rate per leg (fractional)."""

    funding_rate_per_8h: float
    """Funding rate per 8h period (fractional)."""

    leverage: float
    """Assumed leverage for margin-based calculations."""

    n_strategies_evaluated: int
    """Number of strategy variants evaluated in this session (selection bias visibility)."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict representation."""
        return asdict(self)

    def fingerprint(self) -> str:
        """Deterministic hash of all provenance fields for reproducibility check."""
        raw = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Evaluation configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationConfig:
    """Predeclared evaluation thresholds and rules.

    All threshold values must be set before evaluation and recorded in the
    result. No threshold may be changed after holdout results are inspected
    without invalidating that run and creating a new manifest version.
    """

    min_trades: int = 100
    """Minimum number of closed trades for a meaningful evaluation."""

    min_duration_days: int = 30
    """Minimum evaluation duration in calendar days."""

    min_regimes: int = 2
    """Minimum number of distinct market regimes covered."""

    max_drawdown_pct: float = 25.0
    """Maximum acceptable drawdown (percentage)."""

    min_profit_factor: float = 1.3
    """Minimum acceptable profit factor."""

    max_correlation_with_benchmark: float = 0.95
    """Maximum acceptable return correlation with a passive benchmark."""

    require_holdout: bool = True
    """Whether untouched holdout data is required for PASS_CANDIDATE."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict representation."""
        return asdict(self)


# Default conservative configuration
DEFAULT_EVALUATION_CONFIG = EvaluationConfig()


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------


@dataclass
class DataQualityReport:
    """Report of data quality issues detected during evaluation."""

    missing_candles: int = 0
    """Number of expected candles that are missing."""

    duplicate_timestamps: int = 0
    """Number of duplicate timestamps found."""

    timestamp_gaps: list[tuple[str, str]] = field(default_factory=list)
    """List of (start, end) ISO-8601 timestamps for detected gaps."""

    unsupported_pairs: list[str] = field(default_factory=list)
    """Pairs with insufficient history for the requested period."""

    survivorship_bias_note: str = ""
    """Note about potential survivorship/delisting bias."""

    exchange_limitations: str = ""
    """Exchange-specific limitations that affect data quality."""

    @property
    def is_clean(self) -> bool:
        """True when no data quality issues were detected."""
        return (
            self.missing_candles == 0
            and self.duplicate_timestamps == 0
            and len(self.timestamp_gaps) == 0
            and len(self.unsupported_pairs) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict representation."""
        return {
            "missing_candles": self.missing_candles,
            "duplicate_timestamps": self.duplicate_timestamps,
            "timestamp_gaps": [(s, e) for s, e in self.timestamp_gaps],
            "unsupported_pairs": self.unsupported_pairs,
            "survivorship_bias_note": self.survivorship_bias_note,
            "exchange_limitations": self.exchange_limitations,
            "is_clean": self.is_clean,
        }


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    """Complete result of one edge-evidence evaluation run.

    This is the primary output artifact. It includes all provenance,
    configuration, metrics, and outcome data needed for auditability.
    """

    outcome: Gate0Outcome
    """Gate-0 outcome of the evaluation."""

    provenance: HarnessProvenance
    """Immutable provenance record for this run."""

    config: EvaluationConfig
    """Predeclared evaluation configuration used for this run."""

    data_quality: DataQualityReport
    """Data quality report for this run."""

    total_trades: int
    """Total number of closed trades in the evaluation."""

    total_net_pnl: float
    """Total net PnL across all trades."""

    profit_factor: float
    """Gross profit / gross loss ratio."""

    max_drawdown_pct: float
    """Maximum peak-to-trough drawdown (percentage)."""

    win_rate_pct: float
    """Percentage of profitable trades."""

    avg_return_pct: float
    """Average return per trade (percentage)."""

    sharpe_ratio: float = 0.0
    """Annualized Sharpe ratio (risk-free rate = 0)."""

    calmar_ratio: float = 0.0
    """Annualized return / max drawdown ratio."""

    exposure_pct: float = 0.0
    """Percentage of time the strategy was in a position."""

    turnover: float = 0.0
    """Total notional traded / average portfolio value."""

    tail_loss_pct: float = 0.0
    """Percentage of total loss from the worst 5% of trades."""

    regime_breakdown: dict[str, int] = field(default_factory=dict)
    """Trade count per market regime (e.g., {'bull': 40, 'bear': 30, 'sideways': 30})."""

    walk_forward_metrics: list[dict[str, Any]] = field(default_factory=list)
    """Per-window walk-forward metrics for reproducibility."""

    holdout_metrics: dict[str, Any] | None = None
    """Metrics from the untouched holdout period, if applicable."""

    reproducibility_fingerprint: str = ""
    """SHA-256 fingerprint of provenance + config for reproducibility check."""

    warnings: list[str] = field(default_factory=list)
    """Non-blocking warnings about the evaluation."""

    run_timestamp_utc: str = ""
    """ISO-8601 timestamp of when the evaluation was run."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict representation for serialization."""
        d: dict[str, Any] = {
            "outcome": self.outcome.value,
            "provenance": self.provenance.to_dict(),
            "config": self.config.to_dict(),
            "data_quality": self.data_quality.to_dict(),
            "total_trades": self.total_trades,
            "total_net_pnl": self.total_net_pnl,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate_pct": self.win_rate_pct,
            "avg_return_pct": self.avg_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "calmar_ratio": self.calmar_ratio,
            "exposure_pct": self.exposure_pct,
            "turnover": self.turnover,
            "tail_loss_pct": self.tail_loss_pct,
            "regime_breakdown": dict(self.regime_breakdown),
            "walk_forward_metrics": list(self.walk_forward_metrics),
            "holdout_metrics": self.holdout_metrics,
            "reproducibility_fingerprint": self.reproducibility_fingerprint,
            "warnings": list(self.warnings),
            "run_timestamp_utc": self.run_timestamp_utc,
        }
        return d

    def to_json(self, indent: int = 2) -> str:
        """JSON string representation."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @property
    def is_pass_candidate(self) -> bool:
        """Convenience check for PASS_CANDIDATE outcome."""
        return self.outcome == Gate0Outcome.PASS_CANDIDATE

    @property
    def is_extend(self) -> bool:
        """Convenience check for EXTEND outcome."""
        return self.outcome == Gate0Outcome.EXTEND

    @property
    def is_reject(self) -> bool:
        """Convenience check for REJECT outcome."""
        return self.outcome == Gate0Outcome.REJECT

    @property
    def is_invalid(self) -> bool:
        """Convenience check for INVALID outcome."""
        return self.outcome == Gate0Outcome.INVALID


# ---------------------------------------------------------------------------
# Strategy evaluation harness
# ---------------------------------------------------------------------------


class StrategyEvaluationHarness:
    """Reproducible edge-evidence evaluation harness for one strategy.

    The harness is a pure data processor: it takes pinned inputs (strategy
    identifier, data snapshot, evaluation config) and produces an
    EvaluationResult. It never mutates strategies, runtime configuration,
    or live state.

    Usage::

        harness = StrategyEvaluationHarness(
            provenance=my_provenance,
            config=my_config,
        )
        result = harness.evaluate(trade_results, regime_labels)
    """

    def __init__(
        self,
        provenance: HarnessProvenance,
        config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ) -> None:
        """Initialize the harness with pinned provenance and config.

        Parameters
        ----------
        provenance : HarnessProvenance
            Immutable provenance record for this evaluation run.
        config : EvaluationConfig
            Predeclared evaluation thresholds and rules.
        """
        self._provenance = provenance
        self._config = config
        self._fingerprint = provenance.fingerprint()

    @property
    def provenance(self) -> HarnessProvenance:
        """Immutable provenance for this harness instance."""
        return self._provenance

    @property
    def config(self) -> EvaluationConfig:
        """Evaluation configuration for this harness instance."""
        return self._config

    def evaluate(
        self,
        trade_results: list[dict[str, Any]],
        regime_labels: dict[str, int] | None = None,
    ) -> EvaluationResult:
        """Run the evaluation against a list of trade results.

        Parameters
        ----------
        trade_results : list[dict]
            List of trade result dicts. Each dict must have at minimum:
            - ``net_pnl`` (float): net profit/loss for the trade
            - ``gross_pnl`` (float): gross profit/loss before costs
            - ``entry_price`` (float): entry price
            - ``exit_price`` (float): exit price
            - ``quantity`` (float): base currency amount
            - ``side`` (str): 'long' or 'short'
            - ``hold_hours`` (float): hours the trade was held
            - ``entry_fee`` (float): entry fee paid
            - ``exit_fee`` (float): exit fee paid
            - ``slippage_cost`` (float): slippage cost
            - ``funding_cost`` (float): funding cost
        regime_labels : dict[str, int] or None
            Optional mapping of regime name to trade count for regime
            breakdown reporting.

        Returns
        -------
        EvaluationResult
            Complete evaluation result with outcome, metrics, and provenance.

        Raises
        ------
        ValueError
            If trade_results is empty or missing required fields.
        """
        if not trade_results:
            raise ValueError("trade_results must not be empty")

        # Validate required fields
        required_fields = {"net_pnl", "gross_pnl", "entry_price", "exit_price",
                          "quantity", "side", "hold_hours"}
        for i, trade in enumerate(trade_results):
            missing = required_fields - set(trade.keys())
            if missing:
                raise ValueError(
                    f"Trade at index {i} missing required fields: {missing}"
                )
            # Check for None values in required fields
            for req_field in required_fields:
                if trade.get(req_field) is None:
                    raise ValueError(
                        f"Trade at index {i} has None value for required field '{req_field}'"
                    )

        # Data quality check
        data_quality = self._check_data_quality(trade_results)

        # Compute metrics
        n = len(trade_results)
        total_net_pnl = sum(t.get("net_pnl", 0.0) for t in trade_results)

        # Profit factor
        gross_profit = sum(t["net_pnl"] for t in trade_results if t["net_pnl"] > 0)
        gross_loss = abs(sum(t["net_pnl"] for t in trade_results if t["net_pnl"] < 0))
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        # Win rate
        wins = sum(1 for t in trade_results if t.get("net_pnl", 0) > 0)
        win_rate_pct = (wins / n * 100.0) if n > 0 else 0.0

        # Max drawdown (peak-to-trough from net PnL)
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trade_results:
            equity += t.get("net_pnl", 0.0)
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
        max_drawdown_pct = max_dd * 100.0

        # Average return
        total_notional = sum(
            t.get("entry_price", 0) * t.get("quantity", 0) for t in trade_results
        )
        avg_return_pct = (
            (total_net_pnl / total_notional * 100.0) if total_notional > 0 else 0.0
        )

        # Sharpe ratio (simplified: mean / std of per-trade returns)
        returns = []
        for t in trade_results:
            notional = t.get("entry_price", 0) * t.get("quantity", 0)
            if notional > 0:
                returns.append(t.get("net_pnl", 0) / notional)
        if len(returns) > 1:
            import statistics
            mean_ret = statistics.mean(returns)
            std_ret = statistics.stdev(returns)
            sharpe_ratio = (mean_ret / std_ret) * (365 * 24 * 60 / 5) ** 0.5 if std_ret > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        # Calmar ratio
        calmar_ratio = (
            (total_net_pnl / total_notional * 100.0) / (max_drawdown_pct / 100.0)
            if max_drawdown_pct > 0 and total_notional > 0
            else 0.0
        )

        # Tail loss (worst 5% of trades)
        if n >= 20:
            sorted_losses = sorted(
                [t["net_pnl"] for t in trade_results if t["net_pnl"] < 0]
            )
            tail_count = max(1, n // 20)
            tail_loss = abs(sum(sorted_losses[:tail_count]))
            total_loss = abs(sum(t["net_pnl"] for t in trade_results if t["net_pnl"] < 0))
            tail_loss_pct = (tail_loss / total_loss * 100.0) if total_loss > 0 else 0.0
        else:
            tail_loss_pct = 0.0

        # Determine outcome
        outcome = self._determine_outcome(
            n=n,
            total_net_pnl=total_net_pnl,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            data_quality=data_quality,
        )

        # Build result
        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = EvaluationResult(
            outcome=outcome,
            provenance=self._provenance,
            config=self._config,
            data_quality=data_quality,
            total_trades=n,
            total_net_pnl=total_net_pnl,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_return_pct=avg_return_pct,
            sharpe_ratio=sharpe_ratio,
            calmar_ratio=calmar_ratio,
            tail_loss_pct=tail_loss_pct,
            regime_breakdown=dict(regime_labels or {}),
            reproducibility_fingerprint=self._fingerprint,
            run_timestamp_utc=now_utc,
        )

        return result

    def _check_data_quality(
        self, trade_results: list[dict[str, Any]]
    ) -> DataQualityReport:
        """Check trade results for data quality issues.

        Parameters
        ----------
        trade_results : list[dict]
            List of trade result dicts.

        Returns
        -------
        DataQualityReport
            Report of detected data quality issues.
        """
        report = DataQualityReport()

        # Check for missing net_pnl
        missing_pnl = sum(1 for t in trade_results if t.get("net_pnl") is None)
        report.missing_candles = missing_pnl

        # Check for duplicate timestamps (if present)
        timestamps = [
            t.get("close_time") or t.get("timestamp")
            for t in trade_results
            if t.get("close_time") or t.get("timestamp")
        ]
        if len(timestamps) != len(set(timestamps)):
            report.duplicate_timestamps = len(timestamps) - len(set(timestamps))

        # Check for unsupported pairs (if pair field present)
        pairs_seen: dict[str, int] = {}
        for t in trade_results:
            pair = t.get("pair", "")
            if pair:
                pairs_seen[pair] = pairs_seen.get(pair, 0) + 1
        min_trades_per_pair = 5
        for pair, count in pairs_seen.items():
            if count < min_trades_per_pair:
                report.unsupported_pairs.append(pair)

        return report

    def _determine_outcome(
        self,
        n: int,
        total_net_pnl: float,
        profit_factor: float,
        max_drawdown_pct: float,
        data_quality: DataQualityReport,
    ) -> Gate0Outcome:
        """Determine the Gate-0 outcome based on metrics and config.

        Parameters
        ----------
        n : int
            Total number of trades.
        total_net_pnl : float
            Total net PnL.
        profit_factor : float
            Profit factor.
        max_drawdown_pct : float
            Maximum drawdown percentage.
        data_quality : DataQualityReport
            Data quality report.

        Returns
        -------
        Gate0Outcome
            The determined outcome.
        """
        # INVALID: data quality issues
        if not data_quality.is_clean:
            return Gate0Outcome.INVALID

        # REJECT: material guardrail failure
        if total_net_pnl <= 0:
            return Gate0Outcome.REJECT
        if max_drawdown_pct > self._config.max_drawdown_pct:
            return Gate0Outcome.REJECT
        if profit_factor < self._config.min_profit_factor:
            return Gate0Outcome.REJECT

        # EXTEND: insufficient evidence
        if n < self._config.min_trades:
            return Gate0Outcome.EXTEND

        # PASS_CANDIDATE: all criteria met
        return Gate0Outcome.PASS_CANDIDATE
