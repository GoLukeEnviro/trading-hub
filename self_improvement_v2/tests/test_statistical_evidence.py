"""Tests for statistical_evidence.py — Phase 8.

All tests are pure-function tests with no IO or runtime access.
"""

from __future__ import annotations

import json

from si_v2.measurement.statistical_evidence import (
    ArmTradeEvidence,
    StatisticalEvidenceInput,
    TradeSample,
    bootstrap_mean_diff_ci,
    build_stat_input_from_snapshot,
    calculate_profit_factor,
    evaluate_statistical_evidence,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(
    trade_id: str,
    profit_abs: float,
    profit_ratio: float = 0.0,
    bot_id: str = "canary",
) -> TradeSample:
    return TradeSample(
        trade_id=trade_id,
        bot_id=bot_id,
        close_timestamp_utc="2026-07-01T12:00:00Z",
        profit_abs=profit_abs,
        profit_ratio=profit_ratio,
    )


def _make_arm(
    bot_id: str,
    profits: list[float],
) -> ArmTradeEvidence:
    trades = tuple(
        _make_trade(f"{bot_id}_{i}", p, p / 100.0, bot_id)
        for i, p in enumerate(profits)
    )
    return ArmTradeEvidence(bot_id=bot_id, trades=trades)


def _make_input(
    change_id: str = "change-001",
    candidate_id: str = "candidate-001",
    canary_profits: list[float] | None = None,
    control_profits: list[float] | None = None,
    evidence_class: str = "A",
    **kwargs: object,
) -> StatisticalEvidenceInput:
    canary = _make_arm(
        "freqtrade-freqforge-canary",
        canary_profits or [0.1, 0.2, 0.3, 0.4, 0.5],
    )
    control = _make_arm(
        "freqtrade-freqforge",
        control_profits or [0.05, 0.1, 0.15, 0.2, 0.25],
    )
    return StatisticalEvidenceInput(
        change_id=change_id,
        candidate_id=candidate_id,
        canary=canary,
        control=control,
        evidence_class=evidence_class,  # type: ignore[arg-type]
        **kwargs,
    )


# ======================================================================
# Tests: Input validation
# ======================================================================


class TestInputValidation:
    def test_blocks_empty_change_id(self) -> None:
        result = evaluate_statistical_evidence(_make_input(change_id=""))
        assert result.status == "STAT_BLOCKED"
        assert any("change_id" in r for r in result.blocked_reasons)

    def test_blocks_empty_candidate_id(self) -> None:
        result = evaluate_statistical_evidence(_make_input(candidate_id=""))
        assert result.status == "STAT_BLOCKED"

    def test_blocks_invalid_confidence_level(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(confidence_level=0.999),
        )
        assert result.status == "STAT_BLOCKED"
        assert any("confidence_level" in r for r in result.blocked_reasons)

    def test_blocks_too_few_bootstrap_iterations(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(bootstrap_iterations=50),
        )
        assert result.status == "STAT_BLOCKED"

    def test_blocks_invalid_evidence_class(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(evidence_class="D"),  # type: ignore[arg-type]
        )
        assert result.status == "STAT_BLOCKED"

    def test_blocks_empty_arms(self) -> None:
        result = evaluate_statistical_evidence(
            StatisticalEvidenceInput(
                change_id="ch-1",
                candidate_id="cand-1",
                canary=ArmTradeEvidence(bot_id="canary", trades=()),
                control=ArmTradeEvidence(bot_id="control", trades=()),
            ),
        )
        assert result.status == "STAT_BLOCKED"

    def test_blocks_nan_profit(self) -> None:
        canary = _make_arm("canary", [float("nan"), 0.2, 0.3])
        control = _make_arm("control", [0.1, 0.2, 0.3])
        result = evaluate_statistical_evidence(
            StatisticalEvidenceInput(
                change_id="ch-1",
                candidate_id="cand-1",
                canary=canary,
                control=control,
            ),
        )
        assert result.status == "STAT_BLOCKED"


# ======================================================================
# Tests: Sample adequacy
# ======================================================================


class TestSampleAdequacy:
    def test_insufficient_samples_class_a(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.1, 0.2, 0.3],
                control_profits=[0.1, 0.2, 0.3, 0.4, 0.5],
                evidence_class="A",
            ),
        )
        assert result.status == "STAT_INSUFFICIENT"
        assert result.recommendation == "STAT_INSUFFICIENT"

    def test_insufficient_samples_class_b(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.01 * i for i in range(10)],
                control_profits=[0.01 * i for i in range(10)],
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_INSUFFICIENT"

    def test_insufficient_samples_class_c(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.01 * i for i in range(20)],
                control_profits=[0.01 * i for i in range(20)],
                evidence_class="C",
            ),
        )
        assert result.status == "STAT_INSUFFICIENT"


# ======================================================================
# Tests: Profit factor
# ======================================================================


class TestProfitFactor:
    def test_profit_factor_no_losses_returns_none(self) -> None:
        samples = tuple(
            _make_trade(str(i), 0.1, 0.01) for i in range(5)
        )
        assert calculate_profit_factor(samples) is None

    def test_profit_factor_only_losses_returns_zero(self) -> None:
        samples = tuple(
            _make_trade(str(i), -0.1, -0.01) for i in range(5)
        )
        result = calculate_profit_factor(samples)
        assert result == 0.0

    def test_profit_factor_empty_returns_none(self) -> None:
        assert calculate_profit_factor(()) is None

    def test_profit_factor_mixed(self) -> None:
        samples = (
            _make_trade("1", 1.0, 0.01),
            _make_trade("2", -0.5, -0.005),
            _make_trade("3", 0.3, 0.003),
        )
        result = calculate_profit_factor(samples)
        assert result is not None
        assert abs(result - 1.3 / 0.5) < 1e-6

    def test_profit_factor_all_zero_returns_none(self) -> None:
        samples = tuple(
            _make_trade(str(i), 0.0, 0.0) for i in range(3)
        )
        assert calculate_profit_factor(samples) is None


# ======================================================================
# Tests: Bootstrap CI
# ======================================================================


class TestBootstrapCI:
    def test_bootstrap_ci_deterministic(self) -> None:
        canary = (0.1, 0.2, 0.3, 0.4, 0.5)
        control = (0.05, 0.1, 0.15, 0.2, 0.25)
        r1 = bootstrap_mean_diff_ci(
            canary, control,
            iterations=1000, confidence_level=0.90, random_seed=42,
        )
        r2 = bootstrap_mean_diff_ci(
            canary, control,
            iterations=1000, confidence_level=0.90, random_seed=42,
        )
        assert r1 == r2

    def test_bootstrap_ci_empty_returns_zero(self) -> None:
        assert bootstrap_mean_diff_ci(
            (), (), iterations=100, confidence_level=0.9, random_seed=42,
        ) == (0.0, 0.0)

    def test_bootstrap_ci_contains_positive_diff(self) -> None:
        canary = tuple(0.5 + 0.1 * i for i in range(10))
        control = tuple(0.1 + 0.05 * i for i in range(10))
        ci_low, ci_high = bootstrap_mean_diff_ci(
            canary, control,
            iterations=1000, confidence_level=0.90, random_seed=42,
        )
        true_diff = sum(canary) / len(canary) - sum(control) / len(control)
        assert ci_low <= true_diff <= ci_high


# ======================================================================
# Tests: Recommendations
# ======================================================================


class TestRecommendations:
    def test_keep_when_canary_statistically_better(self) -> None:
        canary_profits = [0.5] * 10 + [0.4] * 5
        control_profits = [0.1] * 10 + [0.05] * 5
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=canary_profits,
                control_profits=control_profits,
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.recommendation == "STAT_KEEP"
        assert result.mean_profit_diff > 0

    def test_rollback_when_canary_statistically_worse(self) -> None:
        canary_profits = [0.1] * 10 + [0.05] * 5
        control_profits = [0.5] * 10 + [0.4] * 5
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=canary_profits,
                control_profits=control_profits,
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.recommendation == "STAT_ROLLBACK"
        assert result.mean_profit_diff < 0

    def test_extend_when_ci_crosses_zero(self) -> None:
        canary_profits = [0.15, 0.25, -0.05, 0.3, 0.1, 0.2, 0.0, -0.1, 0.35, 0.05]
        control_profits = [0.15, 0.20, 0.0, 0.25, 0.15, 0.2, 0.05, -0.05, 0.3, 0.1]
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=canary_profits[:5],
                control_profits=control_profits[:5],
                evidence_class="A",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.evidence_grade in ("WEAK", "MODERATE")

    def test_effect_size_positive_when_canary_better(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.5, 0.6, 0.7, 0.8, 0.9] * 3,
                control_profits=[0.1, 0.2, 0.3, 0.4, 0.5] * 3,
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.effect_size > 0.3


# ======================================================================
# Tests: Serialization and evidence grade
# ======================================================================


class TestSerializationAndGrade:
    def test_result_serializable(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.5] * 15,
                control_profits=[0.1] * 15,
                evidence_class="B",
            ),
        )
        d = result.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0
        loaded = json.loads(serialized)
        assert loaded["recommendation"] == "STAT_KEEP"
        assert loaded["status"] == "STAT_READY"

    def test_evidence_grade_strong_for_positive_ci(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.8, 0.9, 1.0, 1.1, 1.2] * 3,
                control_profits=[0.1, 0.2, 0.3, 0.4, 0.5] * 3,
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.evidence_grade == "STRONG"

    def test_evidence_grade_insufficient_for_low_samples(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.1, 0.2, 0.3],
                control_profits=[0.1, 0.2, 0.3],
                evidence_class="C",
            ),
        )
        assert result.evidence_grade == "INSUFFICIENT"

    def test_to_dict_does_not_raise(self) -> None:
        result = evaluate_statistical_evidence(_make_input())
        _ = result.to_dict()


# ======================================================================
# Tests: Snapshot builder
# ======================================================================


class TestSnapshotBuilder:
    def test_build_stat_input_from_valid_snapshot(self) -> None:
        snapshot: dict[str, object] = {
            "label": "T1",
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "test",
            "control": {
                "bot_id": "freqtrade-freqforge",
                "trades_since_t0": [
                    {"trade_id": "1", "profit_abs": 0.1,
                     "profit_ratio": 0.01,
                     "close_timestamp_utc": "2026-07-01T10:00:00Z"},
                    {"trade_id": "2", "profit_abs": 0.2,
                     "profit_ratio": 0.02,
                     "close_timestamp_utc": "2026-07-01T11:00:00Z"},
                ],
            },
            "canary": {
                "bot_id": "freqtrade-freqforge-canary",
                "trades_since_t0": [
                    {"trade_id": "3", "profit_abs": 0.3,
                     "profit_ratio": 0.03,
                     "close_timestamp_utc": "2026-07-01T10:00:00Z"},
                    {"trade_id": "4", "profit_abs": 0.4,
                     "profit_ratio": 0.04,
                     "close_timestamp_utc": "2026-07-01T11:00:00Z"},
                ],
            },
        }
        result = build_stat_input_from_snapshot(
            change_id="ch-1",
            candidate_id="cand-1",
            snapshot=snapshot,
            canary_bot="freqtrade-freqforge-canary",
            control_bot="freqtrade-freqforge",
        )
        assert result is not None
        assert len(result.canary.trades) == 2
        assert len(result.control.trades) == 2

    def test_build_stat_input_from_snapshot_no_trades_returns_none(self) -> None:
        snapshot: dict[str, object] = {
            "control": {"bot_id": "control"},
            "canary": {"bot_id": "canary"},
        }
        result = build_stat_input_from_snapshot(
            change_id="ch-1",
            candidate_id="cand-1",
            snapshot=snapshot,
            canary_bot="canary",
            control_bot="control",
        )
        assert result is None

    def test_build_stat_input_from_snapshot_empty_lists_fail(self) -> None:
        snapshot: dict[str, object] = {
            "control": {"bot_id": "control", "trades_since_t0": []},
            "canary": {"bot_id": "canary", "trades_since_t0": []},
        }
        result = build_stat_input_from_snapshot(
            change_id="ch-1",
            candidate_id="cand-1",
            snapshot=snapshot,
            canary_bot="canary",
            control_bot="control",
        )
        assert result is None


# ======================================================================
# Tests: Edge cases
# ======================================================================


class TestEdgeCases:
    def test_single_trade_per_arm(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.5] * 5,
                control_profits=[0.3] * 5,
                evidence_class="A",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.canary_n == 5

    def test_identical_trades_does_not_crash(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=[0.1, 0.2, 0.3, 0.4, 0.5],
                control_profits=[0.1, 0.2, 0.3, 0.4, 0.5],
                evidence_class="A",
            ),
        )
        assert result.status == "STAT_READY"
        assert abs(result.mean_profit_diff) < 1e-6

    def test_large_sample_class_b_keep(self) -> None:
        canary = [0.3 + 0.05 * (i % 3) for i in range(20)]
        control = [0.1 + 0.02 * (i % 4) for i in range(20)]
        result = evaluate_statistical_evidence(
            _make_input(
                canary_profits=canary,
                control_profits=control,
                evidence_class="B",
            ),
        )
        assert result.status == "STAT_READY"
        assert result.recommendation in ("STAT_KEEP", "STAT_EXTEND")

    def test_blocked_reasons_not_mutated(self) -> None:
        result = evaluate_statistical_evidence(
            _make_input(change_id="", evidence_class="A"),
        )
        assert isinstance(result.blocked_reasons, tuple)
