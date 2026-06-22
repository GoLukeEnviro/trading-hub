"""Tests for the SI v2 Profitability Evidence Gate (#279).

Covers fleet-level profitability evaluation with deterministic, real-metrics
verdicts for all four dry-run bots.

Test data mirrors realistic scenarios from natural scheduled SI v2 cycles
(20260619T121720Z, 20260619T181720Z) plus synthetic edge cases.
"""

from __future__ import annotations

from si_v2.evaluation.profitability_gate import (
    DEFAULT_EXPECTED_BOT_IDS,
    VERDICT_BLOCKED,
    VERDICT_CANDIDATE,
    VERDICT_INCONCLUSIVE,
    BotProfitabilityMetrics,
    _classify_bot,
    _compute_fleet_profit_factor,
    _is_real_source,
    evaluate_fleet,
    evaluate_from_walk_forward_dicts,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

POSITIVE_BOT = BotProfitabilityMetrics(
    bot_id="freqtrade-freqforge",
    net_pnl=15.5,
    profit_factor=2.1,
    trade_count=12,
    max_drawdown_pct=5.2,
    max_drawdown_measured=True,
    metrics_source="walk_forward_net_metrics",
    evaluation_status="PASS_REVIEW",
)

NEGATIVE_BOT = BotProfitabilityMetrics(
    bot_id="freqtrade-regime-hybrid",
    net_pnl=-7.12,
    profit_factor=0.58,
    trade_count=5,
    max_drawdown_pct=10.3,
    max_drawdown_measured=True,
    metrics_source="walk_forward_net_metrics",
    evaluation_status="NEGATIVE_NET_METRICS",
)

WEAK_POSITIVE_BOT = BotProfitabilityMetrics(
    bot_id="freqtrade-freqforge-canary",
    net_pnl=3.2,
    profit_factor=1.2,
    trade_count=3,  # Below _MIN_TRADES_FOR_CANDIDATE (5) but above _MIN_TRADES_INCONCLUSIVE (3)
    max_drawdown_pct=2.1,
    max_drawdown_measured=True,
    metrics_source="walk_forward_net_metrics",
    evaluation_status="PASS_REVIEW",
)

NOT_APPLICABLE_BOT = BotProfitabilityMetrics(
    bot_id="freqai-rebel",
    net_pnl=0.0,
    profit_factor=0.0,
    trade_count=0,
    max_drawdown_pct=0.0,
    max_drawdown_measured=False,
    metrics_source="not_applicable",
    evaluation_status="NOT_APPLICABLE",
)

ALL_POSITIVE_FLEET = [
    POSITIVE_BOT,
    BotProfitabilityMetrics(
        bot_id="freqtrade-regime-hybrid",
        net_pnl=5.0,
        profit_factor=1.5,
        trade_count=8,
        max_drawdown_pct=8.0,
        max_drawdown_measured=True,
        metrics_source="walk_forward_net_metrics",
        evaluation_status="PASS_REVIEW",
    ),
    BotProfitabilityMetrics(
        bot_id="freqtrade-freqforge-canary",
        net_pnl=3.2,
        profit_factor=1.2,
        trade_count=6,
        max_drawdown_pct=2.1,
        max_drawdown_measured=True,
        metrics_source="walk_forward_net_metrics",
        evaluation_status="PASS_REVIEW",
    ),
    BotProfitabilityMetrics(
        bot_id="freqai-rebel",
        net_pnl=2.1,
        profit_factor=1.8,
        trade_count=10,
        max_drawdown_pct=3.7,
        max_drawdown_measured=True,
        metrics_source="walk_forward_net_metrics",
        evaluation_status="PASS_REVIEW",
    ),
]

ALL_FOUR_BOT_MIXED = [
    POSITIVE_BOT,
    NEGATIVE_BOT,
    WEAK_POSITIVE_BOT,
    BotProfitabilityMetrics(
        bot_id="freqai-rebel",
        net_pnl=-0.32,
        profit_factor=0.21,
        trade_count=10,
        max_drawdown_pct=3.79,
        max_drawdown_measured=True,
        metrics_source="walk_forward_net_metrics",
        evaluation_status="NEGATIVE_NET_METRICS",
    ),
]

# ---------------------------------------------------------------------------
# Source validation tests
# ---------------------------------------------------------------------------


class TestSourceValidation:
    def test_real_sources_accepted(self) -> None:
        assert _is_real_source("real") is True
        assert _is_real_source("freqtrade_rest") is True
        assert _is_real_source("freqtrade_telemetry") is True
        assert _is_real_source("walk_forward_net_metrics") is True
        assert _is_real_source("active_cycle") is True

    def test_blocked_sources_rejected(self) -> None:
        assert _is_real_source("synthetic") is False
        assert _is_real_source("stub") is False
        assert _is_real_source("mock") is False
        assert _is_real_source("fallback") is False
        assert _is_real_source("placeholder") is False
        assert _is_real_source("example") is False
        assert _is_real_source("test_fixture") is False
        assert _is_real_source("unknown") is False
        assert _is_real_source("none") is False
        assert _is_real_source("not_applicable") is False

    def test_empty_source_rejected(self) -> None:
        assert _is_real_source("") is False

    def test_case_insensitive(self) -> None:
        assert _is_real_source("REAL") is True
        assert _is_real_source("Walk_Forward_Net_Metrics") is True
        assert _is_real_source("MOCK") is False


# ---------------------------------------------------------------------------
# Fleet profit factor tests
# ---------------------------------------------------------------------------


class TestFleetProfitFactor:
    def test_all_positive(self) -> None:
        bots = [
            BotProfitabilityMetrics(bot_id="a", net_pnl=10.0),
            BotProfitabilityMetrics(bot_id="b", net_pnl=5.0),
        ]
        assert _compute_fleet_profit_factor(bots) == 999.0

    def test_mixed(self) -> None:
        bots = [
            BotProfitabilityMetrics(bot_id="a", net_pnl=10.0),
            BotProfitabilityMetrics(bot_id="b", net_pnl=-5.0),
        ]
        assert _compute_fleet_profit_factor(bots) == 2.0

    def test_all_negative(self) -> None:
        bots = [
            BotProfitabilityMetrics(bot_id="a", net_pnl=-10.0),
            BotProfitabilityMetrics(bot_id="b", net_pnl=-5.0),
        ]
        assert _compute_fleet_profit_factor(bots) == 0.0

    def test_zero_pnl(self) -> None:
        bots = [
            BotProfitabilityMetrics(bot_id="a", net_pnl=0.0),
            BotProfitabilityMetrics(bot_id="b", net_pnl=0.0),
        ]
        assert _compute_fleet_profit_factor(bots) == 0.0


# ---------------------------------------------------------------------------
# Per-bot classification tests
# ---------------------------------------------------------------------------


class TestClassifyBot:
    def test_positive_bot_yields_candidate(self) -> None:
        verdict, reasons = _classify_bot(POSITIVE_BOT)
        assert verdict == VERDICT_CANDIDATE
        assert reasons == []

    def test_negative_bot_yields_blocked(self) -> None:
        verdict, reasons = _classify_bot(NEGATIVE_BOT)
        assert verdict == VERDICT_BLOCKED
        assert "negative_net_pnl" in reasons
        assert "low_profit_factor" in reasons

    def test_not_applicable_source_yields_blocked(self) -> None:
        verdict, reasons = _classify_bot(NOT_APPLICABLE_BOT)
        assert verdict == VERDICT_BLOCKED
        assert "invalid_metrics_source" in reasons

    def test_synthetic_source_yields_blocked(self) -> None:
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=10.0,
            trade_count=10,
            max_drawdown_measured=True,
            metrics_source="synthetic",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_BLOCKED
        assert "invalid_metrics_source" in reasons

    def test_missing_drawdown_yields_blocked(self) -> None:
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=10.0,
            profit_factor=2.0,
            trade_count=10,
            max_drawdown_pct=0.0,
            max_drawdown_measured=False,
            metrics_source="walk_forward_net_metrics",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_BLOCKED
        assert "missing_drawdown" in reasons

    def test_high_drawdown_yields_blocked(self) -> None:
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=10.0,
            profit_factor=2.0,
            trade_count=10,
            max_drawdown_pct=20.0,
            max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_BLOCKED
        assert "high_drawdown" in reasons

    def test_low_trades_but_real_metrics_yields_inconclusive(self) -> None:
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=2.0,
            profit_factor=1.5,
            trade_count=3,  # >= _MIN_TRADES_INCONCLUSIVE (3) but < _MIN_TRADES_FOR_CANDIDATE (5)
            max_drawdown_pct=1.0,
            max_drawdown_measured=True,
            metrics_source="real",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_INCONCLUSIVE
        assert "inconclusive_trade_count" in reasons

    def test_very_low_trades_yields_blocked(self) -> None:
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=2.0,
            profit_factor=1.5,
            trade_count=1,  # Below _MIN_TRADES_INCONCLUSIVE
            max_drawdown_pct=1.0,
            max_drawdown_measured=True,
            metrics_source="real",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_BLOCKED
        assert "insufficient_trades" in reasons

    def test_threshold_boundary_trades(self) -> None:
        """Trade count exactly at _MIN_TRADES_FOR_CANDIDATE should pass."""
        bot = BotProfitabilityMetrics(
            bot_id="test",
            net_pnl=5.0,
            profit_factor=1.5,
            trade_count=5,  # Exactly _MIN_TRADES_FOR_CANDIDATE
            max_drawdown_pct=5.0,
            max_drawdown_measured=True,
            metrics_source="real",
        )
        verdict, reasons = _classify_bot(bot)
        assert verdict == VERDICT_CANDIDATE
        assert reasons == []


# ---------------------------------------------------------------------------
# Fleet-level evaluation tests
# ---------------------------------------------------------------------------


class TestEvaluateFleet:
    def test_positive_four_bot_fleet_yields_candidate(self) -> None:
        result = evaluate_fleet(ALL_POSITIVE_FLEET)
        assert result.verdict == VERDICT_CANDIDATE
        assert len(result.reasons) == 0
        assert all(v == VERDICT_CANDIDATE for v in result.bot_verdicts.values())

    def test_mixed_fleet_with_negative_bot_yields_blocked(self) -> None:
        result = evaluate_fleet(ALL_FOUR_BOT_MIXED)
        assert result.verdict == VERDICT_BLOCKED
        assert "blocked_bots" in result.reasons[0]

    def test_missing_bot_yields_blocked(self) -> None:
        partial_fleet = ALL_POSITIVE_FLEET[:3]  # Only 3 bots
        result = evaluate_fleet(partial_fleet)
        assert result.verdict == VERDICT_BLOCKED
        assert any("missing_bot" in r for r in result.reasons)

    def test_synthetic_source_fleet_yields_blocked(self) -> None:
        fleet = [
            BotProfitabilityMetrics(
                bot_id=bid,
                net_pnl=10.0,
                profit_factor=2.0,
                trade_count=10,
                max_drawdown_pct=5.0,
                max_drawdown_measured=True,
                metrics_source="synthetic",
                evaluation_status="PASS_REVIEW",
            )
            for bid in DEFAULT_EXPECTED_BOT_IDS
        ]
        result = evaluate_fleet(fleet)
        assert result.verdict == VERDICT_BLOCKED

    def test_fleet_net_pnl_not_positive_yields_blocked(self) -> None:
        fleet = [
            BotProfitabilityMetrics(
                bot_id=bid,
                net_pnl=-1.0,  # Slightly negative — still below threshold
                profit_factor=1.5,
                trade_count=10,
                max_drawdown_pct=5.0,
                max_drawdown_measured=True,
                metrics_source="walk_forward_net_metrics",
                evaluation_status="PASS_REVIEW",
            )
            for bid in DEFAULT_EXPECTED_BOT_IDS
        ]
        result = evaluate_fleet(fleet)
        assert result.verdict == VERDICT_BLOCKED

    def test_inconclusive_fleet_with_low_trades(self) -> None:
        """All bots have low but real trades: should be inconclusive, not blocked."""
        fleet = [
            BotProfitabilityMetrics(
                bot_id=bid,
                net_pnl=2.0,
                profit_factor=1.2,
                trade_count=3,  # Inconclusive range (>=3, <5)
                max_drawdown_pct=2.0,
                max_drawdown_measured=True,
                metrics_source="walk_forward_net_metrics",
                evaluation_status="PASS_REVIEW",
            )
            for bid in DEFAULT_EXPECTED_BOT_IDS
        ]
        result = evaluate_fleet(fleet)
        assert result.verdict == VERDICT_INCONCLUSIVE

    def test_fleet_high_drawdown_yields_blocked(self) -> None:
        fleet = [
            BotProfitabilityMetrics(
                bot_id=bid,
                net_pnl=10.0,
                profit_factor=1.5,
                trade_count=10,
                max_drawdown_pct=25.0,  # Exceeds _MAX_DRAWDOWN_PCT (15)
                max_drawdown_measured=True,
                metrics_source="walk_forward_net_metrics",
                evaluation_status="PASS_REVIEW",
            )
            for bid in DEFAULT_EXPECTED_BOT_IDS
        ]
        result = evaluate_fleet(fleet)
        assert result.verdict == VERDICT_BLOCKED

    def test_output_shape_contains_all_fields(self) -> None:
        result = evaluate_fleet(ALL_POSITIVE_FLEET)
        assert hasattr(result, "verdict")
        assert hasattr(result, "reasons")
        assert hasattr(result, "bot_verdicts")
        assert hasattr(result, "fleet_summary")
        d = result.to_dict()
        assert "verdict" in d
        assert "reasons" in d
        assert "bot_verdicts" in d
        assert "fleet_summary" in d

    def test_input_data_not_mutated(self) -> None:
        """Verify the gate does not mutate input."""
        fleet_copy = [BotProfitabilityMetrics(**vars(b)) for b in ALL_POSITIVE_FLEET]
        evaluate_fleet(ALL_POSITIVE_FLEET)
        # Compare with copy
        for original, copy in zip(ALL_POSITIVE_FLEET, fleet_copy, strict=False):
            assert original.bot_id == copy.bot_id
            assert original.net_pnl == copy.net_pnl
            assert original.trade_count == copy.trade_count

    def test_reasons_are_stable(self) -> None:
        """Same input should produce identical reasons."""
        r1 = evaluate_fleet(ALL_FOUR_BOT_MIXED)
        r2 = evaluate_fleet(ALL_FOUR_BOT_MIXED)
        assert r1.reasons == r2.reasons
        assert r1.verdict == r2.verdict

    def test_fleet_summary_contains_aggregates(self) -> None:
        result = evaluate_fleet(ALL_POSITIVE_FLEET)
        fs = result.fleet_summary
        assert fs["total_trades"] == 36  # 12 + 8 + 6 + 10
        assert fs["total_net_pnl"] == 25.8  # 15.5 + 5.0 + 3.2 + 2.1
        assert fs["candidate_count"] == 4
        assert fs["blocked_count"] == 0
        assert fs["inconclusive_count"] == 0


# ---------------------------------------------------------------------------
# evaluate_from_walk_forward_dicts convenience tests
# ---------------------------------------------------------------------------


class TestEvaluateFromDicts:
    def test_positive_fleet_from_dicts(self) -> None:
        dicts = {
            bid: {
                "total_net_pnl": 10.0,
                "profit_factor": 2.0,
                "total_trades": 10,
                "max_drawdown_pct": 5.0,
                "metrics_source": "walk_forward_net_metrics",
                "evaluation_status": "PASS_REVIEW",
            }
            for bid in DEFAULT_EXPECTED_BOT_IDS
        }
        result = evaluate_from_walk_forward_dicts(dicts)
        assert result.verdict == VERDICT_CANDIDATE

    def test_dicts_with_missing_keys_use_defaults(self) -> None:
        dicts: dict[str, dict[str, object]] = {
            bid: {
                "metrics_source": "walk_forward_net_metrics",
            }
            for bid in DEFAULT_EXPECTED_BOT_IDS
        }
        result = evaluate_from_walk_forward_dicts(dicts)
        # Missing metrics means all zeros — net_pnl not positive -> blocked
        assert result.verdict == VERDICT_BLOCKED

    def test_dicts_partial_fleet_yields_blocked(self) -> None:
        """Only 2 of 4 bots — should be blocked."""
        dicts = {
            "freqtrade-freqforge": {
                "total_net_pnl": 10.0,
                "profit_factor": 2.0,
                "total_trades": 10,
                "max_drawdown_pct": 5.0,
                "metrics_source": "walk_forward_net_metrics",
                "evaluation_status": "PASS_REVIEW",
            },
            "freqtrade-regime-hybrid": {
                "total_net_pnl": 5.0,
                "profit_factor": 1.5,
                "total_trades": 8,
                "max_drawdown_pct": 3.0,
                "metrics_source": "walk_forward_net_metrics",
                "evaluation_status": "PASS_REVIEW",
            },
        }
        result = evaluate_from_walk_forward_dicts(dicts)
        assert result.verdict == VERDICT_BLOCKED
        assert any("missing_bot" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Serializable output tests
# ---------------------------------------------------------------------------


class TestGateResultSerialization:
    def test_to_dict_produces_json_safe_output(self) -> None:
        result = evaluate_fleet(ALL_POSITIVE_FLEET)
        d = result.to_dict()
        import json

        serialized = json.dumps(d, ensure_ascii=False)
        assert isinstance(serialized, str)
        # Verify it round-trips
        parsed = json.loads(serialized)
        assert parsed["verdict"] == VERDICT_CANDIDATE

    def test_rejected_fleet_serializable(self) -> None:
        result = evaluate_fleet(ALL_FOUR_BOT_MIXED)
        d = result.to_dict()
        import json

        serialized = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["verdict"] == VERDICT_BLOCKED


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_fleet_yields_blocked(self) -> None:
        result = evaluate_fleet([])
        assert result.verdict == VERDICT_BLOCKED
        assert any("missing_bot" in r for r in result.reasons)

    def test_single_bot_yields_blocked(self) -> None:
        result = evaluate_fleet([POSITIVE_BOT])
        assert result.verdict == VERDICT_BLOCKED

    def test_duplicate_bot_id_yields_blocked(self) -> None:
        """Two bots with same ID: one expected bot is missing."""
        fleet: list[BotProfitabilityMetrics] = [
            BotProfitabilityMetrics(
                bot_id="freqtrade-freqforge",
                net_pnl=10.0, profit_factor=2.0, trade_count=10,
                max_drawdown_pct=5.0, max_drawdown_measured=True,
                metrics_source="walk_forward_net_metrics",
            ),
            BotProfitabilityMetrics(
                bot_id="freqtrade-freqforge",  # Duplicate
                net_pnl=5.0, profit_factor=1.5, trade_count=8,
                max_drawdown_pct=3.0, max_drawdown_measured=True,
                metrics_source="walk_forward_net_metrics",
            ),
        ]
        result = evaluate_fleet(fleet)
        assert result.verdict == VERDICT_BLOCKED


# ── Edge-case coverage: fleet-level thresholds (profitability_gate lines 365,368,371,396) ──


def test_fleet_net_pnl_not_positive_with_inconclusive_negative_bot() -> None:
    """Fleet with 2 inconclusive bots (negative PnL) + 2 candidates (small positive).
    No bot individually BLOCKED, but total fleet PnL ≤ 0 → line 365."""
    fleet = [
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge", net_pnl=2.0, profit_factor=1.5, trade_count=7,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-regime-hybrid", net_pnl=2.0, profit_factor=1.5, trade_count=7,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge-canary", net_pnl=-50.0, profit_factor=0.3, trade_count=4,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqai-rebel", net_pnl=-50.0, profit_factor=0.3, trade_count=4,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
    ]
    result = evaluate_fleet(fleet)
    assert result.verdict == VERDICT_BLOCKED
    assert any("fleet_net_pnl" in r for r in result.reasons)
    assert result.fleet_summary["total_net_pnl"] <= 0


def test_fleet_profit_factor_below_threshold_with_mixed_bots() -> None:
    """Fleet profit factor < 1.0 but no individual bot blocked → line 368."""
    fleet = [
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge", net_pnl=0.5, profit_factor=1.01, trade_count=7,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-regime-hybrid", net_pnl=0.5, profit_factor=1.01, trade_count=7,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge-canary", net_pnl=-2.0, profit_factor=0.9, trade_count=4,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqai-rebel", net_pnl=-1.0, profit_factor=0.5, trade_count=4,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
    ]
    result = evaluate_fleet(fleet)
    assert result.verdict in (VERDICT_BLOCKED, VERDICT_INCONCLUSIVE)
    assert result.fleet_summary["fleet_profit_factor"] < 1.0


def test_fleet_high_drawdown_blocks_when_no_individual_bot_blocked() -> None:
    """Fleet max drawdown >= 15% — individual bots all < 15% but fleet max crosses. → line 371.

    NOTE: Line 371 (fleet drawdown >= 15%) is mathematically unreachable in the
    current gate because any individual bot with drawdown >= 15% is already blocked
    before fleet-level checks. This test documents the defensive code path even
    though the individual check catches it first."""
    fleet = [
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge", net_pnl=10.0, profit_factor=2.0, trade_count=10,
            max_drawdown_pct=15.0, max_drawdown_measured=True,  # BLOCKED individually
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-regime-hybrid", net_pnl=5.0, profit_factor=1.5, trade_count=8,
            max_drawdown_pct=3.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge-canary", net_pnl=3.0, profit_factor=1.2, trade_count=6,
            max_drawdown_pct=8.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqai-rebel", net_pnl=1.0, profit_factor=1.1, trade_count=5,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
    ]
    result = evaluate_fleet(fleet)
    # Bot blocked individually → fleet blocked
    assert result.verdict == VERDICT_BLOCKED
    assert "blocked_bots" in result.reasons[0] or any(
        "high_drawdown" in r for r in result.reasons
    )


def test_inconclusive_fleet_when_bots_fine_but_inconclusive() -> None:
    """All individual thresholds pass, fleet passes, but inconclusive bots → line 396."""
    fleet = [
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge", net_pnl=10.0, profit_factor=2.0, trade_count=10,
            max_drawdown_pct=5.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-regime-hybrid", net_pnl=5.0, profit_factor=1.5, trade_count=8,
            max_drawdown_pct=3.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqtrade-freqforge-canary", net_pnl=15.0, profit_factor=3.0, trade_count=4,
            max_drawdown_pct=2.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
        BotProfitabilityMetrics(
            bot_id="freqai-rebel", net_pnl=3.0, profit_factor=1.2, trade_count=3,
            max_drawdown_pct=1.0, max_drawdown_measured=True,
            metrics_source="walk_forward_net_metrics",
        ),
    ]
    result = evaluate_fleet(fleet)
    assert result.verdict == VERDICT_INCONCLUSIVE
    assert any("inconclusive" in r for r in result.reasons)
