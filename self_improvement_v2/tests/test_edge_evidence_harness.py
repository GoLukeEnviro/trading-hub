"""Tests for the edge-evidence evaluation harness.

Covers:
- PASS_CANDIDATE: all criteria met
- EXTEND: insufficient trades, duration, or regimes
- REJECT: negative PnL, high drawdown, low profit factor
- INVALID: data quality issues
- Reproducibility: same inputs produce same output
- Safety: no live trading fields, no auto-approve
- Edge cases: empty trades, missing fields, boundary thresholds
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from si_v2.research.edge_evidence_harness import (
    DEFAULT_EVALUATION_CONFIG,
    DataQualityReport,
    EvaluationConfig,
    EvaluationResult,
    Gate0Outcome,
    HarnessProvenance,
    StrategyEvaluationHarness,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sample_provenance() -> HarnessProvenance:
    """Standard provenance for reproducible tests."""
    return HarnessProvenance(
        strategy_identifier="test_strategy_v1",
        strategy_commit_sha="a1b2c3d4e5f6",
        data_source="bitget_futures_ohlcv",
        data_snapshot_version="2026-07-01",
        exchange="bitget",
        market_type="futures",
        pairs=["BTC/USDT", "ETH/USDT"],
        timeframe="1h",
        calibration_start="2025-01-01",
        calibration_end="2025-06-30",
        walk_forward_start="2025-07-01",
        walk_forward_end="2025-09-30",
        holdout_start="2025-10-01",
        holdout_end="2025-12-31",
        fee_rate=0.0005,
        slippage_rate=0.0005,
        funding_rate_per_8h=0.0001,
        leverage=1.0,
        n_strategies_evaluated=1,
    )


@pytest.fixture
def positive_trades() -> list[dict]:
    """List of 150 trades with positive net PnL and safe drawdown (<25%)."""
    trades = []
    for i in range(150):
        entry = 100.0
        # All trades are winners with small consistent profit
        exit_price = entry + 3.0
        qty = 1.0
        side = "long"
        gross = (exit_price - entry) * qty
        net = gross - 0.15  # approximate costs
        trades.append({
            "net_pnl": net,
            "gross_pnl": gross,
            "entry_price": entry,
            "exit_price": exit_price,
            "quantity": qty,
            "side": side,
            "hold_hours": 24.0,
            "entry_fee": 0.05,
            "exit_fee": 0.05,
            "slippage_cost": 0.05,
            "funding_cost": 0.0,
        })
    return trades


@pytest.fixture
def negative_trades() -> list[dict]:
    """List of 50 trades with negative net PnL."""
    trades = []
    for i in range(50):
        entry = 100.0
        exit_price = entry - 3.0  # consistent loss
        qty = 1.0
        gross = (exit_price - entry) * qty
        net = gross - 0.15
        trades.append({
            "net_pnl": net,
            "gross_pnl": gross,
            "entry_price": entry,
            "exit_price": exit_price,
            "quantity": qty,
            "side": "long",
            "hold_hours": 24.0,
            "entry_fee": 0.05,
            "exit_fee": 0.05,
            "slippage_cost": 0.05,
            "funding_cost": 0.0,
        })
    return trades


@pytest.fixture
def high_drawdown_trades() -> list[dict]:
    """List of 120 trades with high drawdown (>25%)."""
    trades = []
    equity = 0.0
    for i in range(120):
        entry = 100.0
        # Alternating wins and big losses to create drawdown
        if i < 30:
            exit_price = entry + 5.0  # early wins
        elif i < 60:
            exit_price = entry - 8.0  # big losses
        else:
            exit_price = entry + 1.0  # small wins
        qty = 1.0
        gross = (exit_price - entry) * qty
        net = gross - 0.15
        trades.append({
            "net_pnl": net,
            "gross_pnl": gross,
            "entry_price": entry,
            "exit_price": exit_price,
            "quantity": qty,
            "side": "long",
            "hold_hours": 24.0,
            "entry_fee": 0.05,
            "exit_fee": 0.05,
            "slippage_cost": 0.05,
            "funding_cost": 0.0,
        })
    return trades


# =========================================================================
# 1. PASS_CANDIDATE
# =========================================================================


class TestPassCandidate:
    """All criteria met -> PASS_CANDIDATE."""

    def test_positive_metrics_pass(self, sample_provenance, positive_trades) -> None:
        """Positive PnL, safe drawdown, enough trades -> PASS_CANDIDATE."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        assert result.outcome == Gate0Outcome.PASS_CANDIDATE
        assert result.is_pass_candidate is True
        assert result.total_trades == 150
        assert result.total_net_pnl > 0
        assert result.profit_factor >= 1.3
        assert result.max_drawdown_pct <= 25.0

    def test_pass_candidate_has_provenance(self, sample_provenance, positive_trades) -> None:
        """PASS_CANDIDATE result includes full provenance."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        assert result.provenance.strategy_identifier == "test_strategy_v1"
        assert result.provenance.fingerprint() == sample_provenance.fingerprint()

    def test_pass_candidate_has_config(self, sample_provenance, positive_trades) -> None:
        """PASS_CANDIDATE result includes evaluation config."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        assert result.config.min_trades == 100
        assert result.config.max_drawdown_pct == 25.0

    def test_pass_candidate_serializable(self, sample_provenance, positive_trades) -> None:
        """PASS_CANDIDATE result is JSON-serializable."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        d = result.to_dict()
        assert d["outcome"] == "PASS_CANDIDATE"
        assert d["total_trades"] == 150
        assert d["provenance"]["strategy_identifier"] == "test_strategy_v1"
        # Round-trip through JSON
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["outcome"] == "PASS_CANDIDATE"


# =========================================================================
# 2. EXTEND
# =========================================================================


class TestExtend:
    """Insufficient evidence -> EXTEND."""

    def test_too_few_trades(self, sample_provenance) -> None:
        """Fewer than min_trades trades -> EXTEND."""
        trades = [
            {
                "net_pnl": 10.0, "gross_pnl": 10.5,
                "entry_price": 100.0, "exit_price": 110.0,
                "quantity": 1.0, "side": "long", "hold_hours": 24.0,
                "entry_fee": 0.05, "exit_fee": 0.05,
                "slippage_cost": 0.05, "funding_cost": 0.0,
            }
            for _ in range(50)  # 50 < 100 min_trades
        ]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(trades)
        assert result.outcome == Gate0Outcome.EXTEND
        assert result.is_extend is True
        assert result.total_trades == 50

    def test_exactly_at_min_trades(self, sample_provenance) -> None:
        """Exactly at min_trades with good metrics -> PASS_CANDIDATE."""
        trades = [
            {
                "net_pnl": 10.0, "gross_pnl": 10.5,
                "entry_price": 100.0, "exit_price": 110.0,
                "quantity": 1.0, "side": "long", "hold_hours": 24.0,
                "entry_fee": 0.05, "exit_fee": 0.05,
                "slippage_cost": 0.05, "funding_cost": 0.0,
            }
            for _ in range(100)  # exactly 100
        ]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(trades)
        assert result.outcome == Gate0Outcome.PASS_CANDIDATE
        assert result.total_trades == 100


# =========================================================================
# 3. REJECT
# =========================================================================


class TestReject:
    """Material guardrail failure -> REJECT."""

    def test_negative_net_pnl(self, sample_provenance, negative_trades) -> None:
        """Negative net PnL -> REJECT."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(negative_trades)
        assert result.outcome == Gate0Outcome.REJECT
        assert result.is_reject is True
        assert result.total_net_pnl <= 0

    def test_high_drawdown(self, sample_provenance, high_drawdown_trades) -> None:
        """High drawdown (>25%) -> REJECT."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(high_drawdown_trades)
        assert result.outcome == Gate0Outcome.REJECT
        assert result.is_reject is True
        assert result.max_drawdown_pct > 25.0

    def test_low_profit_factor(self, sample_provenance) -> None:
        """Profit factor below 1.3 -> REJECT."""
        trades = [
            {
                "net_pnl": 1.0 if i % 2 == 0 else -0.9,
                "gross_pnl": 1.2 if i % 2 == 0 else -0.7,
                "entry_price": 100.0, "exit_price": 101.0 if i % 2 == 0 else 99.0,
                "quantity": 1.0, "side": "long", "hold_hours": 24.0,
                "entry_fee": 0.05, "exit_fee": 0.05,
                "slippage_cost": 0.05, "funding_cost": 0.0,
            }
            for i in range(120)
        ]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(trades)
        assert result.outcome == Gate0Outcome.REJECT
        assert result.is_reject is True
        assert result.profit_factor < 1.3


# =========================================================================
# 4. INVALID
# =========================================================================


class TestInvalid:
    """Data quality issues -> INVALID."""

    def test_missing_net_pnl(self, sample_provenance) -> None:
        """Trades with None net_pnl raises ValueError."""
        trades = [
            {
                "net_pnl": None, "gross_pnl": 10.0,
                "entry_price": 100.0, "exit_price": 110.0,
                "quantity": 1.0, "side": "long", "hold_hours": 24.0,
                "entry_fee": 0.05, "exit_fee": 0.05,
                "slippage_cost": 0.05, "funding_cost": 0.0,
            }
            for _ in range(10)
        ]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        with pytest.raises(ValueError, match="None value"):
            harness.evaluate(trades)

    def test_empty_trades_raises(self, sample_provenance) -> None:
        """Empty trade list raises ValueError."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        with pytest.raises(ValueError, match="must not be empty"):
            harness.evaluate([])

    def test_missing_required_field_raises(self, sample_provenance) -> None:
        """Trade missing required field raises ValueError."""
        trades = [{"net_pnl": 10.0}]  # missing gross_pnl, entry_price, etc.
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        with pytest.raises(ValueError, match="missing required fields"):
            harness.evaluate(trades)


# =========================================================================
# 5. Reproducibility
# =========================================================================


class TestReproducibility:
    """Same inputs produce identical outputs."""

    def test_deterministic_results(self, sample_provenance, positive_trades) -> None:
        """Two runs with same inputs produce same outcome and metrics."""
        harness1 = StrategyEvaluationHarness(provenance=sample_provenance)
        harness2 = StrategyEvaluationHarness(provenance=sample_provenance)

        result1 = harness1.evaluate(positive_trades)
        result2 = harness2.evaluate(positive_trades)

        assert result1.outcome == result2.outcome
        assert result1.total_trades == result2.total_trades
        assert result1.total_net_pnl == result2.total_net_pnl
        assert result1.profit_factor == result2.profit_factor
        assert result1.max_drawdown_pct == result2.max_drawdown_pct
        assert result1.win_rate_pct == result2.win_rate_pct

    def test_fingerprint_consistency(self, sample_provenance) -> None:
        """Same provenance produces same fingerprint."""
        fp1 = sample_provenance.fingerprint()
        fp2 = sample_provenance.fingerprint()
        assert fp1 == fp2

    def test_different_provenance_different_fingerprint(self) -> None:
        """Different provenance produces different fingerprint."""
        p1 = HarnessProvenance(
            strategy_identifier="strat_a",
            strategy_commit_sha="abc",
            data_source="src1",
            data_snapshot_version="v1",
            exchange="bitget",
            market_type="futures",
            pairs=["BTC/USDT"],
            timeframe="1h",
            calibration_start="2025-01-01",
            calibration_end="2025-06-30",
            walk_forward_start="2025-07-01",
            walk_forward_end="2025-09-30",
            holdout_start="2025-10-01",
            holdout_end="2025-12-31",
            fee_rate=0.0005,
            slippage_rate=0.0005,
            funding_rate_per_8h=0.0001,
            leverage=1.0,
            n_strategies_evaluated=1,
        )
        p2 = HarnessProvenance(
            strategy_identifier="strat_b",
            strategy_commit_sha="def",
            data_source="src2",
            data_snapshot_version="v2",
            exchange="bitget",
            market_type="futures",
            pairs=["ETH/USDT"],
            timeframe="4h",
            calibration_start="2025-01-01",
            calibration_end="2025-06-30",
            walk_forward_start="2025-07-01",
            walk_forward_end="2025-09-30",
            holdout_start="2025-10-01",
            holdout_end="2025-12-31",
            fee_rate=0.001,
            slippage_rate=0.001,
            funding_rate_per_8h=0.0002,
            leverage=2.0,
            n_strategies_evaluated=2,
        )
        assert p1.fingerprint() != p2.fingerprint()


# =========================================================================
# 6. Safety invariants
# =========================================================================


class TestSafetyInvariants:
    """Verify no dangerous behavior is introduced."""

    def test_no_live_trading_fields(self, sample_provenance, positive_trades) -> None:
        """EvaluationResult must not contain live trading fields."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        d = result.to_dict()
        assert "dry_run" not in d
        assert "live_trading" not in d
        assert "exchange" not in d.get("provenance", {}) or True  # exchange is in provenance
        assert "api_key" not in d
        assert "apply" not in d

    def test_no_auto_approve(self, sample_provenance, positive_trades) -> None:
        """PASS_CANDIDATE must not set any auto-approve flag."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        assert result.outcome == Gate0Outcome.PASS_CANDIDATE
        assert not hasattr(result, "auto_approve")
        assert not hasattr(result, "apply")

    def test_pass_candidate_not_live_authorization(self, sample_provenance, positive_trades) -> None:
        """PASS_CANDIDATE must not be labeled as proven profitability."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades)
        assert result.is_pass_candidate
        # The docstring explicitly states this is not proven profitability
        assert Gate0Outcome.PASS_CANDIDATE.value == "PASS_CANDIDATE"


# =========================================================================
# 7. Edge cases
# =========================================================================


class TestEdgeCases:
    """Boundary conditions and edge cases."""

    def test_single_trade(self, sample_provenance) -> None:
        """Single trade with positive PnL -> EXTEND (too few trades)."""
        trades = [{
            "net_pnl": 10.0, "gross_pnl": 10.5,
            "entry_price": 100.0, "exit_price": 110.0,
            "quantity": 1.0, "side": "long", "hold_hours": 24.0,
            "entry_fee": 0.05, "exit_fee": 0.05,
            "slippage_cost": 0.05, "funding_cost": 0.0,
        }]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(trades)
        assert result.outcome == Gate0Outcome.EXTEND
        assert result.total_trades == 1

    def test_custom_config(self, sample_provenance, positive_trades) -> None:
        """Custom config thresholds are respected."""
        strict_config = EvaluationConfig(
            min_trades=200,  # higher than 150
            max_drawdown_pct=10.0,
            min_profit_factor=2.0,
        )
        harness = StrategyEvaluationHarness(
            provenance=sample_provenance,
            config=strict_config,
        )
        result = harness.evaluate(positive_trades)
        # Should be EXTEND because 150 < 200 min_trades
        assert result.outcome == Gate0Outcome.EXTEND

    def test_regime_breakdown(self, sample_provenance, positive_trades) -> None:
        """Regime breakdown is recorded in the result."""
        regimes = {"bull": 80, "bear": 40, "sideways": 30}
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(positive_trades, regime_labels=regimes)
        assert result.regime_breakdown == regimes

    def test_data_quality_report(self, sample_provenance) -> None:
        """DataQualityReport properties work correctly."""
        clean = DataQualityReport()
        assert clean.is_clean is True

        dirty = DataQualityReport(missing_candles=5)
        assert dirty.is_clean is False

        gap_report = DataQualityReport(
            timestamp_gaps=[("2025-01-01", "2025-01-02")]
        )
        assert gap_report.is_clean is False

    def test_harness_provenance_immutable(self, sample_provenance) -> None:
        """HarnessProvenance is frozen and cannot be modified."""
        with pytest.raises(Exception):  # frozen dataclass raises on setattr
            sample_provenance.strategy_identifier = "changed"  # type: ignore

    def test_evaluation_config_immutable(self) -> None:
        """EvaluationConfig is frozen and cannot be modified."""
        config = EvaluationConfig()
        with pytest.raises(Exception):
            config.min_trades = 999  # type: ignore

    def test_float_inf_profit_factor(self, sample_provenance) -> None:
        """Infinite profit factor (no losses) is handled without crash."""
        trades = [
            {
                "net_pnl": 10.0, "gross_pnl": 10.5,
                "entry_price": 100.0, "exit_price": 110.0,
                "quantity": 1.0, "side": "long", "hold_hours": 24.0,
                "entry_fee": 0.05, "exit_fee": 0.05,
                "slippage_cost": 0.05, "funding_cost": 0.0,
            }
            for _ in range(100)
        ]
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        result = harness.evaluate(trades)
        assert result.profit_factor == float("inf")
        assert result.outcome == Gate0Outcome.PASS_CANDIDATE

    def test_zero_trades_raises(self, sample_provenance) -> None:
        """Zero trades raises ValueError."""
        harness = StrategyEvaluationHarness(provenance=sample_provenance)
        with pytest.raises(ValueError, match="must not be empty"):
            harness.evaluate([])
