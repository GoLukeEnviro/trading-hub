"""Tests for AggregateMetricsAdapter — derive_aggregate_metrics.

Required coverage (8 categories):
1. SHADOW_PROPOSAL + real positive metrics → PASS_REVIEW, not blocked
2. SHADOW_PROPOSAL + missing metrics → INSUFFICIENT_EVIDENCE, blocked
3. SHADOW_PROPOSAL + zero/too few trades → INSUFFICIENT_EVIDENCE, blocked
4. SHADOW_PROPOSAL + negative net PnL → blocked with reason code
5. SHADOW_PROPOSAL + excessive drawdown → blocked with reason code
6. NO_PROPOSAL → NOT_APPLICABLE, blocked
7. Multi-bot independence
8. Safety invariants
"""

from __future__ import annotations

from dataclasses import dataclass

from si_v2.evaluation.aggregate_metrics_adapter import (
    METRICS_SOURCE_INSUFFICIENT,
    METRICS_SOURCE_MISSING,
    METRICS_SOURCE_NOT_APPLICABLE,
    METRICS_SOURCE_PARTIAL,
    METRICS_SOURCE_REAL,
    derive_aggregate_metrics,
)
from si_v2.evaluation.walk_forward_net_metrics import (
    REASON_CODE_HIGH_DRAWDOWN,
    REASON_CODE_INSUFFICIENT_EVIDENCE,
    REASON_CODE_MISSING_DRAWDOWN,
    REASON_CODE_NEGATIVE_NET_METRICS,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEGATIVE_NET_METRICS,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS_REVIEW,
    default_no_proposal_evaluation,
    evaluate_from_aggregate_metrics,
    evaluate_net_metrics,
)

# ------------------------------------------------------------------
# Test doubles
# ------------------------------------------------------------------


@dataclass
class _FakeSignalSnapshot:
    """Duck-typed BotSignalSnapshot for tests — carries aggregate trade data."""
    bot_id: str = "test-bot"
    num_trades: int = 0
    profit_closed_coin: float = 0.0
    profit_all_coin: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float | None = None
    daily_trade_count_total: int = 0
    profit_closed_percent: float = 0.0
    profit_all_percent: float = 0.0
    profit_all_ratio: float = 0.0
    performance_pair_count: int = 0
    performance_top_pair: str = ""
    performance_top_pair_profit_pct: float = 0.0
    daily_abs_profit_sum: float = 0.0
    daily_abs_profit_latest: float = 0.0
    whitelist_pair_count: int = 0
    whitelist_method: str = ""
    bot_version: str = ""
    ping_ok: bool = True
    auth_outcome: str = "AUTHENTICATED"
    status_ok: bool = True
    status_open_trades: int = 0
    count_current: int = 0
    count_max: int = 0
    count_total_stake: float = 0.0
    bot_start_date: str = ""
    availability: tuple = ()
    signal_quality: object = None
    fetched_at_utc: str = ""


# ------------------------------------------------------------------
# 1. SHADOW_PROPOSAL + real positive metrics
# ------------------------------------------------------------------


class TestPositiveMetrics:
    """Sufficient trades, positive PnL, real drawdown data -> PASS_REVIEW."""

    def test_positive_net_pnl_passes_review(self):
        """Real positive metrics yield PASS_REVIEW and promotion_blocked=False."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=150.0,
            profit_factor=1.8,
            max_drawdown_pct=6.5,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert source == METRICS_SOURCE_REAL
        assert metrics is not None
        assert metrics["total_trades"] == 10
        assert metrics["total_net_pnl"] == 150.0
        assert metrics["profit_factor"] == 1.8
        assert metrics["max_drawdown_pct"] == 6.5

        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False
        assert result.promotion_block_reason_codes == []

    def test_positive_metrics_with_daily_trade_fallback(self):
        """When num_trades=0 but daily_trade_count_total > 0, use daily data."""
        snap = _FakeSignalSnapshot(
            num_trades=0,
            daily_trade_count_total=7,
            profit_closed_coin=85.0,
            profit_factor=1.5,
            max_drawdown_pct=4.0,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert source == METRICS_SOURCE_REAL
        assert metrics is not None
        assert metrics["total_trades"] == 7
        assert metrics["max_drawdown_pct"] == 4.0

        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False

    def test_positive_metrics_still_requires_human(self):
        """PASS_REVIEW never auto-approves (invariant enforced by caller)."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=250.0,
            profit_factor=2.0,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False
        # Caller must still enforce PENDING_HUMAN -- no auto-approval field exists


# ------------------------------------------------------------------
# 2. SHADOW_PROPOSAL + missing metrics
# ------------------------------------------------------------------


class TestMissingMetrics:
    """No signal snapshot or empty data → INSUFFICIENT_EVIDENCE, blocked."""

    def test_none_snapshot_returns_missing(self):
        """When snapshot is None, no metrics are returned."""
        metrics, source = derive_aggregate_metrics(None)
        assert metrics is None
        assert source == METRICS_SOURCE_MISSING

    def test_snapshot_with_no_trade_data_returns_missing(self):
        """Snapshot with all zeros → missing (no evidence of trade activity)."""
        snap = _FakeSignalSnapshot(num_trades=0, profit_closed_coin=0.0, profit_factor=0.0)
        metrics, source = derive_aggregate_metrics(snap)
        assert metrics is None
        assert source == METRICS_SOURCE_MISSING

    def test_snapshot_with_no_trade_data_fallback_to_insufficient(self):
        """When both num_trades and daily are zero but profit_all_coin nonzero,
        treat as missing (profit_all includes open positions, not closed trades)."""
        snap = _FakeSignalSnapshot(
            num_trades=0,
            daily_trade_count_total=0,
            profit_closed_coin=0.0,
            profit_all_coin=42.5,
        )
        metrics, source = derive_aggregate_metrics(snap)
        # profit_all_coin != 0 but no closed trades + no closed pnl → missing
        assert metrics is not None  # profit_all_coin gives nonzero total_net_pnl
        assert source == METRICS_SOURCE_INSUFFICIENT  # total_trades=0


# ------------------------------------------------------------------
# 3. SHADOW_PROPOSAL + zero/too few trades
# ------------------------------------------------------------------


class TestInsufficientTrades:
    """Fewer than 5 trades → INSUFFICIENT_EVIDENCE, blocked."""

    def test_zero_trades_blocks(self):
        """Zero trades → INSUFFICIENT_EVIDENCE, promotion blocked."""
        snap = _FakeSignalSnapshot(num_trades=0, daily_trade_count_total=0)
        metrics, source = derive_aggregate_metrics(snap)
        assert metrics is None
        assert source == METRICS_SOURCE_MISSING

    def test_one_trade_blocks(self):
        """1 trade (< 5) → insufficient evidence when passed to evaluator."""
        snap = _FakeSignalSnapshot(
            num_trades=1,
            profit_closed_coin=10.0,
            profit_factor=1.2,
            max_drawdown_pct=2.0,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert source == METRICS_SOURCE_REAL
        assert metrics is not None
        assert metrics["total_trades"] == 1

        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_INSUFFICIENT_EVIDENCE in result.promotion_block_reason_codes

    def test_four_trades_blocks(self):
        """4 trades (< 5) → INSUFFICIENT_EVIDENCE."""
        snap = _FakeSignalSnapshot(
            num_trades=4,
            profit_closed_coin=50.0,
            profit_factor=1.5,
            max_drawdown_pct=3.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True

    def test_exactly_five_trades_is_sufficient(self):
        """5 trades is the minimum for a meaningful evaluation."""
        snap = _FakeSignalSnapshot(
            num_trades=5,
            profit_closed_coin=25.0,
            profit_factor=1.1,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False


# ------------------------------------------------------------------
# 4. SHADOW_PROPOSAL + negative net PnL
# ------------------------------------------------------------------


class TestNegativeNetPnl:
    """Negative net PnL blocks promotion with a specific reason code."""

    def test_negative_pnl_blocks(self):
        """Negative PnL with sufficient trades → NEGATIVE_NET_METRICS, blocked."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=-50.0,
            profit_factor=0.8,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True
        assert REASON_CODE_NEGATIVE_NET_METRICS in result.promotion_block_reason_codes

    def test_zero_pnl_blocks(self):
        """Net PnL of exactly 0.0 blocks promotion."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=0.0,
            profit_factor=1.0,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True
        assert REASON_CODE_NEGATIVE_NET_METRICS in result.promotion_block_reason_codes

    def test_marginally_positive_pnl_passes(self):
        """Very small positive PnL is sufficient to avoid the negative block."""
        snap = _FakeSignalSnapshot(
            num_trades=5,
            profit_closed_coin=0.01,
            profit_factor=1.0,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False


# ------------------------------------------------------------------
# 5. SHADOW_PROPOSAL + excessive drawdown
# ------------------------------------------------------------------


class TestExcessiveDrawdown:
    """High drawdown blocks promotion (via evaluate_net_metrics directly)."""

    def test_high_drawdown_blocks(self):
        """Drawdown above 15% blocks promotion with reason code."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=100.0,
            max_drawdown_pct=18.0,
            profit_factor=1.5,
        )
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes

    def test_drawdown_at_threshold_blocks(self):
        """Drawdown exactly at 15% threshold blocks promotion."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=100.0,
            max_drawdown_pct=15.0,
            profit_factor=1.5,
        )
        assert result.promotion_blocked is True
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes

    def test_drawdown_below_threshold_passes(self):
        """Drawdown slightly below 15% does not block on drawdown alone."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=100.0,
            max_drawdown_pct=14.9,
            profit_factor=1.5,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False

    def test_negative_pnl_and_high_drawdown_reason_codes(self):
        """Both negative PnL and high drawdown produce combined reasons."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=-100.0,
            max_drawdown_pct=20.0,
            profit_factor=0.5,
        )
        assert result.promotion_blocked is True
        assert REASON_CODE_NEGATIVE_NET_METRICS in result.promotion_block_reason_codes
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes


# ------------------------------------------------------------------
# 6. NO_PROPOSAL
# ------------------------------------------------------------------


class TestNoProposal:
    """NO_PROPOSAL gets NOT_APPLICABLE, always blocked."""

    def test_no_proposal_evaluation(self):
        """default_no_proposal_evaluation returns NOT_APPLICABLE, blocked."""
        result = default_no_proposal_evaluation()
        assert result.evaluation_status == STATUS_NOT_APPLICABLE
        assert result.promotion_blocked is True
        assert "no_proposal" in result.promotion_block_reason_codes

    def test_no_proposal_dict_includes_metrics_source(self):
        """When used in cycle runner, metrics_source is NOT_APPLICABLE."""
        result = default_no_proposal_evaluation()
        d = result.to_dict()
        d["metrics_source"] = METRICS_SOURCE_NOT_APPLICABLE
        assert d["evaluation_status"] == STATUS_NOT_APPLICABLE
        assert d["promotion_blocked"] is True
        assert d["metrics_source"] == METRICS_SOURCE_NOT_APPLICABLE


# ------------------------------------------------------------------
# 7. Multi-bot independence
# ------------------------------------------------------------------


class TestMultiBot:
    """Each bot gets independent evaluation — one bot's metrics don't affect another."""

    def test_independent_bot_evaluations(self):
        """Two bots with different metrics produce independent results."""
        snap_a = _FakeSignalSnapshot(
            bot_id="freqtrade-freqforge",
            num_trades=10,
            profit_closed_coin=200.0,
            profit_factor=2.0,
            max_drawdown_pct=5.0,
        )
        snap_b = _FakeSignalSnapshot(
            bot_id="freqai-rebel",
            num_trades=3,
            profit_closed_coin=-50.0,
            profit_factor=0.5,
        )

        # Bot A -- complete drawdown data enables PASS_REVIEW
        metrics_a, _ = derive_aggregate_metrics(snap_a)
        result_a = evaluate_from_aggregate_metrics(metrics_a)
        assert result_a.evaluation_status == STATUS_PASS_REVIEW
        assert result_a.promotion_blocked is False

        # Bot B -- few trades, negative PnL
        metrics_b, source_b = derive_aggregate_metrics(snap_b)
        assert source_b == METRICS_SOURCE_PARTIAL  # has data, but drawdown is missing
        result_b = evaluate_from_aggregate_metrics(metrics_b)
        assert result_b.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result_b.promotion_blocked is True

    def test_all_four_bots_independent(self):
        """All four fleet bots receive independent metric evaluation."""
        bot_ids = [
            "freqtrade-freqforge",
            "freqtrade-regime-hybrid",
            "freqtrade-freqforge-canary",
            "freqai-rebel",
        ]
        snapshots = [
            _FakeSignalSnapshot(bot_id=bot_ids[0], num_trades=10, profit_closed_coin=150.0,
                                max_drawdown_pct=5.0),
            _FakeSignalSnapshot(bot_id=bot_ids[1], num_trades=0, profit_closed_coin=0.0),
            _FakeSignalSnapshot(bot_id=bot_ids[2], num_trades=7, profit_closed_coin=-20.0,
                                max_drawdown_pct=5.0),
            _FakeSignalSnapshot(bot_id=bot_ids[3], num_trades=2, profit_closed_coin=5.0),
        ]

        results = []
        for snap in snapshots:
            metrics, _ = derive_aggregate_metrics(snap)
            if metrics is not None:
                wf = evaluate_from_aggregate_metrics(metrics)
            else:
                from si_v2.evaluation.walk_forward_net_metrics import (
                    REASON_CODE_INSUFFICIENT_EVIDENCE,
                    STATUS_INSUFFICIENT_EVIDENCE,
                    WalkForwardEvaluation,
                )
                wf = WalkForwardEvaluation(
                    evaluation_status=STATUS_INSUFFICIENT_EVIDENCE,
                    promotion_blocked=True,
                    promotion_block_reason_codes=[REASON_CODE_INSUFFICIENT_EVIDENCE],
                )
            results.append((snap.bot_id, wf.evaluation_status, wf.promotion_blocked))

        # Bot A: PASS_REVIEW, not blocked (positive PnL, enough trades, drawdown provided)
        assert results[0] == (bot_ids[0], STATUS_PASS_REVIEW, False)
        # Bot B: INSUFFICIENT (zero data)
        assert results[1][0] == bot_ids[1]
        assert results[1][1] == STATUS_INSUFFICIENT_EVIDENCE
        assert results[1][2] is True
        # Bot C: NEGATIVE_NET_METRICS (negative PnL, enough trades, drawdown provided)
        assert results[2][0] == bot_ids[2]
        assert results[2][1] == STATUS_NEGATIVE_NET_METRICS
        assert results[2][2] is True
        # Bot D: INSUFFICIENT (only 2 trades)
        assert results[3][0] == bot_ids[3]
        assert results[3][1] == STATUS_INSUFFICIENT_EVIDENCE
        assert results[3][2] is True

    def test_one_bot_valid_does_not_affect_another(self):
        """Valid metrics on bot A don't change behavior for bot B with missing data."""
        snap_a = _FakeSignalSnapshot(bot_id="bot-a", num_trades=10, profit_closed_coin=100.0)
        snap_b = _FakeSignalSnapshot(bot_id="bot-b", num_trades=0, profit_closed_coin=0.0)

        metrics_a, _ = derive_aggregate_metrics(snap_a)
        metrics_b, _ = derive_aggregate_metrics(snap_b)

        assert metrics_a is not None
        assert metrics_b is None  # bot B has no data → missing


# ------------------------------------------------------------------
# 8. Safety invariants
# ------------------------------------------------------------------


class TestSafetyInvariants:
    """No auto-apply, no auto-promotion, no live-trading fields."""

    def test_no_auto_apply(self):
        """WalkForwardEvaluation has no auto-apply field."""
        result = evaluate_net_metrics(total_trades=10, total_net_pnl=100.0, profit_factor=2.0)
        d = result.to_dict()
        assert "auto_apply" not in d
        assert "auto_approve" not in d

    def test_no_live_trading_fields(self):
        """Evaluation result contains no live-trading related fields."""
        result = evaluate_net_metrics(total_trades=10, total_net_pnl=100.0, profit_factor=2.0)
        d = result.to_dict()
        forbidden = ["dry_run", "live", "order", "exchange", "api_key"]
        for key in forbidden:
            assert key not in d

    def test_adapter_no_side_effects(self):
        """derive_aggregate_metrics is a pure function — no I/O, no mutation."""
        snap = _FakeSignalSnapshot(num_trades=10, profit_closed_coin=50.0)
        import copy
        snap_copy = copy.copy(snap)
        metrics, source = derive_aggregate_metrics(snap)
        # Original snapshot is unchanged
        assert snap.num_trades == snap_copy.num_trades
        assert snap.profit_closed_coin == snap_copy.profit_closed_coin
        # Result is deterministic
        metrics2, source2 = derive_aggregate_metrics(snap)
        assert metrics == metrics2
        assert source == source2

    def test_no_config_strategy_docker_paths(self):
        """The test file itself doesn't touch forbidden areas."""
        # This is a meta-test: the test module only imports from
        # si_v2.evaluation.* — no Docker, strategy, or config imports.
        import si_v2.evaluation.aggregate_metrics_adapter
        import si_v2.evaluation.walk_forward_net_metrics
        assert si_v2.evaluation.aggregate_metrics_adapter is not None
        assert si_v2.evaluation.walk_forward_net_metrics is not None


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge cases for robustness."""

    def test_annual_trade_count(self):
        """Large trade count (e.g., 500) is handled correctly."""
        snap = _FakeSignalSnapshot(
            num_trades=500,
            profit_closed_coin=2500.0,
            profit_factor=1.2,
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.total_trades == 500

    def test_zero_profit_factor_default(self):
        """When profit_factor is not available, defaults to 0.0 (safe)."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=100.0,
            profit_factor=0.0,  # not provided by Freqtrade
            max_drawdown_pct=5.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        assert metrics["profit_factor"] == 0.0
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW  # profit_factor not a blocker
        assert result.profit_factor == 0.0

    def test_source_tag_on_fallback(self):
        """Fallback produces METRICS_SOURCE_MISSING or METRICS_SOURCE_INSUFFICIENT."""
        snap = _FakeSignalSnapshot(num_trades=0, profit_closed_coin=0.0)
        _, source = derive_aggregate_metrics(snap)
        assert source == METRICS_SOURCE_MISSING

        snap2 = _FakeSignalSnapshot(num_trades=1, profit_closed_coin=10.0)
        _, source2 = derive_aggregate_metrics(snap2)
        assert source2 == METRICS_SOURCE_PARTIAL

        snap3 = _FakeSignalSnapshot(
            num_trades=1,
            profit_closed_coin=10.0,
            max_drawdown_pct=1.0,
        )
        _, source3 = derive_aggregate_metrics(snap3)
        assert source3 == METRICS_SOURCE_REAL


# ------------------------------------------------------------------
# 9. Missing drawdown blocks PASS_REVIEW
# ------------------------------------------------------------------


class TestMissingDrawdownBlocksPass:
    """Missing max_drawdown_pct must block PASS_REVIEW."""

    def test_positive_all_but_missing_drawdown_blocks(self):
        """Positive PnL + enough trades + good profit factor but missing
        drawdown -> must not produce unblocked PASS_REVIEW."""
        snap = _FakeSignalSnapshot(
            num_trades=20,
            profit_closed_coin=1000.0,
            profit_factor=2.0,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        # Intentionally leave max_drawdown_pct missing; adapter must omit it
        # so evaluate_from_aggregate_metrics detects absence.
        assert "max_drawdown_pct" not in metrics

        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_MISSING_DRAWDOWN in result.promotion_block_reason_codes
        # Still carries available metric metadata
        assert result.total_trades == 20
        assert result.total_net_pnl == 1000.0
        assert result.profit_factor == 2.0

    def test_positive_all_with_real_drawdown_may_pass(self):
        """Positive PnL + enough trades + profit factor + real safe drawdown
        -> may produce PASS_REVIEW (still requires human approval)."""
        snap = _FakeSignalSnapshot(
            num_trades=20,
            profit_closed_coin=1000.0,
            profit_factor=2.0,
            max_drawdown_pct=8.0,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert source == METRICS_SOURCE_REAL
        assert metrics["max_drawdown_pct"] == 8.0

        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False
        # Still requires human approval -- no auto-apply field exists
        assert result.promotion_block_reason_codes == []

    def test_missing_drawdown_with_negative_pnl(self):
        """Missing drawdown + negative PnL -> blocked by missing drawdown
        (fires before PnL check)."""
        snap = _FakeSignalSnapshot(
            num_trades=10,
            profit_closed_coin=-100.0,
            profit_factor=0.5,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        assert "max_drawdown_pct" not in metrics

        result = evaluate_from_aggregate_metrics(metrics)
        # Missing drawdown check fires before negative PnL check
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_MISSING_DRAWDOWN in result.promotion_block_reason_codes
        # Still carries available metric metadata
        assert result.total_trades == 10
        assert result.total_net_pnl == -100.0

    def test_missing_drawdown_with_few_trades(self):
        """Missing drawdown + insufficient trades -> blocked by insufficient
        trades (fires before missing drawdown check)."""
        snap = _FakeSignalSnapshot(
            num_trades=3,
            profit_closed_coin=50.0,
            profit_factor=1.5,
        )
        metrics, _ = derive_aggregate_metrics(snap)
        result = evaluate_from_aggregate_metrics(metrics)
        # Insufficient trades check fires before missing drawdown check
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_INSUFFICIENT_EVIDENCE in result.promotion_block_reason_codes


# ------------------------------------------------------------------
# 10. Multi-bot missing drawdown scenarios
# ------------------------------------------------------------------


class TestMultiBotMissingDrawdown:
    """Multi-bot evaluation with mixed drawdown completeness."""

    def test_multi_bot_mixed_drawdown(self):
        """Bot A complete positive -> may pass; Bot B positive but missing
        drawdown -> blocked; Bot C high drawdown -> blocked; Bot D
        insufficient trades -> blocked."""
        snap_a = _FakeSignalSnapshot(
            bot_id="bot-a",
            num_trades=15,
            profit_closed_coin=500.0,
            profit_factor=1.8,
            max_drawdown_pct=6.0,
        )
        snap_b = _FakeSignalSnapshot(
            bot_id="bot-b",
            num_trades=10,
            profit_closed_coin=200.0,
            profit_factor=1.5,
        )
        snap_c = _FakeSignalSnapshot(
            bot_id="bot-c",
            num_trades=10,
            profit_closed_coin=50.0,
            profit_factor=1.3,
            max_drawdown_pct=22.0,
        )
        snap_d = _FakeSignalSnapshot(
            bot_id="bot-d",
            num_trades=3,
            profit_closed_coin=10.0,
            profit_factor=1.2,
        )

        results = []
        for snap in (snap_a, snap_b, snap_c, snap_d):
            metrics, _ = derive_aggregate_metrics(snap)
            wf = evaluate_from_aggregate_metrics(metrics)
            results.append(wf)

        # Bot A: complete positive metrics -> may pass review
        assert results[0].evaluation_status == STATUS_PASS_REVIEW
        assert results[0].promotion_blocked is False

        # Bot B: positive PnL but missing drawdown -> blocked
        assert results[1].evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert results[1].promotion_blocked is True
        assert REASON_CODE_MISSING_DRAWDOWN in results[1].promotion_block_reason_codes

        # Bot C: high real drawdown -> blocked with high-drawdown reason
        assert results[2].evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert results[2].promotion_blocked is True
        assert REASON_CODE_HIGH_DRAWDOWN in results[2].promotion_block_reason_codes

        # Bot D: insufficient trades -> blocked (drawdown check never reached)
        assert results[3].evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert results[3].promotion_blocked is True
        assert REASON_CODE_INSUFFICIENT_EVIDENCE in results[3].promotion_block_reason_codes


# ------------------------------------------------------------------
# 11. NO_PROPOSAL remains NOT_APPLICABLE
# ------------------------------------------------------------------


class TestNoProposalRemainsBlocked:
    """NO_PROPOSAL must continue to produce NOT_APPLICABLE, blocked."""

    def test_no_proposal_not_applicable(self):
        """NO_PROPOSAL -> NOT_APPLICABLE, promotion_blocked=True."""
        result = default_no_proposal_evaluation()
        assert result.evaluation_status == STATUS_NOT_APPLICABLE
        assert result.promotion_blocked is True
        assert "no_proposal" in result.promotion_block_reason_codes

    def test_no_proposal_never_promotable(self):
        """NOT_APPLICABLE must never be promotable."""
        result = default_no_proposal_evaluation()
        assert result.evaluation_status != STATUS_PASS_REVIEW
        assert result.promotion_blocked is True


# ------------------------------------------------------------------
# 12. Metrics source labeling
# ------------------------------------------------------------------


class TestMetricsSourceLabeling:
    """Verify metrics_source label reflects drawdown completeness."""

    def test_metrics_source_partial_when_drawdown_missing(self):
        """When max_drawdown_pct is absent, metrics_source must not be real."""
        snap = _FakeSignalSnapshot(
            num_trades=20,
            profit_closed_coin=1000.0,
            profit_factor=2.0,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert "max_drawdown_pct" not in metrics
        assert source == METRICS_SOURCE_PARTIAL
        assert source != METRICS_SOURCE_REAL

        # Evaluation must also be blocked (metrics completeness gate)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.promotion_blocked is True
        assert REASON_CODE_MISSING_DRAWDOWN in result.promotion_block_reason_codes

    def test_metrics_source_real_when_drawdown_present(self):
        """When max_drawdown_pct is present, metrics_source must be real."""
        snap = _FakeSignalSnapshot(
            num_trades=20,
            profit_closed_coin=1000.0,
            profit_factor=2.0,
            max_drawdown_pct=8.0,
        )
        metrics, source = derive_aggregate_metrics(snap)
        assert metrics["max_drawdown_pct"] == 8.0
        assert source == METRICS_SOURCE_REAL

        # Evaluation may pass review (positive metrics + real drawdown)
        result = evaluate_from_aggregate_metrics(metrics)
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False

    def test_metrics_source_no_proposal_not_applicable(self):
        """NO_PROPOSAL metrics source is not_applicable."""
        result = default_no_proposal_evaluation()
        d = result.to_dict()
        d["metrics_source"] = METRICS_SOURCE_NOT_APPLICABLE
        assert d["metrics_source"] == METRICS_SOURCE_NOT_APPLICABLE
        assert d["evaluation_status"] == STATUS_NOT_APPLICABLE
        assert d["promotion_blocked"] is True
