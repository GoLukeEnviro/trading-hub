"""Tests for Dynamic Exit Evidence enrichment and gate evaluation."""

from __future__ import annotations

import json
from decimal import Decimal

from si_v2.evaluation.dynamic_exit_evidence import (
    DEFAULT_FLEET_BOT_IDS,
    DEFAULT_STRATEGY_BOT_MAPPING,
    GATE_VERDICT_BLOCKED,
    GATE_VERDICT_CANDIDATE,
    GATE_VERDICT_INCONCLUSIVE,
    REASON_STRATEGY_MAPPING_MISSING,
    STATUS_BLOCKED,
    STATUS_VALID,
    enrich_bot_exit_evidence,
    enrich_fleet_exit_evidence,
    evaluate_exit_evidence_gate,
)
from si_v2.risk.dynamic_exits import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    MODE_ATR,
    MODE_BOLLINGER_DISTANCE,
)

D = Decimal


# ==========================================================================
# 1. Valid long ATR exit evidence
# ==========================================================================

def test_valid_long_atr_exit_evidence() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("50000"),
            "direction": "long",
            "exit_mode": "atr",
            "atr": D("500"),
            "candle_count": 100,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.bot_id == "freqtrade-freqforge"
    assert evidence.strategy_id == "strat_btc_01"
    assert evidence.mode == MODE_ATR
    assert evidence.direction == DIRECTION_LONG
    assert evidence.stop_loss is not None
    assert evidence.take_profit is not None
    assert evidence.risk_distance is not None
    assert evidence.reward_distance is not None
    assert evidence.risk_reward_ratio is not None

    # Long ATR with stop=1.5, tp=2.0 → risk=750, reward=1000
    assert evidence.risk_distance == "750.000000"
    assert evidence.reward_distance == "1000.000000"


# ==========================================================================
# 2. Valid short ATR exit evidence
# ==========================================================================

def test_valid_short_atr_exit_evidence() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqai-rebel",
        bot_metrics={
            "entry_price": D("100"),
            "direction": "short",
            "exit_mode": "atr",
            "atr": D("2"),
            "candle_count": 50,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.direction == DIRECTION_SHORT
    assert evidence.stop_loss is not None
    assert evidence.take_profit is not None


# ==========================================================================
# 3. Valid Bollinger exit evidence
# ==========================================================================

def test_valid_bollinger_exit_evidence() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-regime-hybrid",
        bot_metrics={
            "entry_price": D("100"),
            "direction": "long",
            "exit_mode": "bollinger_distance",
            "bollinger_lower": D("95"),
            "bollinger_mid": D("100"),
            "bollinger_upper": D("110"),
            "candle_count": 50,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.mode == MODE_BOLLINGER_DISTANCE
    assert evidence.stop_loss is not None
    assert evidence.take_profit is not None


# ==========================================================================
# 4. Insufficient candle data blocks
# ==========================================================================

def test_insufficient_candle_data_blocks_exit() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("50000"),
            "direction": "long",
            "exit_mode": "atr",
            "atr": D("500"),
            "candle_count": 5,  # below default minimum_candles=20
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_BLOCKED
    assert "insufficient_candles" in evidence.reason_codes
    assert evidence.stop_loss is None
    assert evidence.take_profit is None


# ==========================================================================
# 5. Missing strategy mapping → strategy_mapping_missing
# ==========================================================================

def test_missing_strategy_mapping_produces_soft_block() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-unknown-bot",
        bot_metrics={"entry_price": D("100")},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_BLOCKED
    assert REASON_STRATEGY_MAPPING_MISSING in evidence.reason_codes
    assert evidence.strategy_id is None


def test_no_mapping_at_all_produces_soft_block() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={"entry_price": D("100")},
        strategy_bot_mapping={},  # empty mapping
    )

    assert evidence.status == STATUS_BLOCKED
    assert REASON_STRATEGY_MAPPING_MISSING in evidence.reason_codes


# ==========================================================================
# 6. Low risk/reward blocks promotion
# ==========================================================================

def test_low_risk_reward_ratio_blocks_fleet_gate() -> None:
    # Build evidence where risk=reward → risk_reward_ratio=1.0
    # With min_risk_reward_ratio=1.5, this should block.
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("100"),
            "direction": "long",
            "exit_mode": "atr",
            "atr": D("2"),
            "stop_multiplier": D("1"),
            "take_profit_multiplier": D("1"),  # 1:1 ratio
            "candle_count": 50,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.risk_reward_ratio == "1.000000"

    result = evaluate_exit_evidence_gate(
        [evidence], min_risk_reward_ratio=D("1.5")
    )

    assert result.verdict == GATE_VERDICT_BLOCKED
    assert any("risk_reward_failures" in r for r in result.reasons)


# ==========================================================================
# 7. All four bots receive dynamic exit evidence block
# ==========================================================================

def test_all_four_bots_receive_exit_evidence() -> None:
    bot_metrics_map = {
        "freqtrade-freqforge": {
            "entry_price": D("50000"), "atr": D("500"), "candle_count": 100,
        },
        "freqtrade-regime-hybrid": {
            "entry_price": D("3000"), "atr": D("50"), "candle_count": 100,
        },
        "freqtrade-freqforge-canary": {
            "entry_price": D("50000"), "atr": D("500"), "candle_count": 100,
        },
        "freqai-rebel": {
            "entry_price": D("100"), "atr": D("5"), "candle_count": 100,
        },
    }

    evidence_list = enrich_fleet_exit_evidence(
        bot_metrics_map=bot_metrics_map,
        fleet_bot_ids=DEFAULT_FLEET_BOT_IDS,
    )

    assert len(evidence_list) == 4
    bot_ids = {e.bot_id for e in evidence_list}
    assert bot_ids == set(DEFAULT_FLEET_BOT_IDS)

    # All should be valid with proper ATR exit evidence
    for e in evidence_list:
        assert e.status == STATUS_VALID, f"{e.bot_id}: {e.reason_codes}"
        assert e.stop_loss is not None
        assert e.take_profit is not None


# ==========================================================================
# 8. JSON serialization is stable
# ==========================================================================

def test_dynamic_exit_evidence_json_roundtrip() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("50000"),
            "atr": D("500"),
            "candle_count": 100,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    d = evidence.to_dict()
    # Must be JSON-serializable
    json_str = json.dumps(d)
    loaded = json.loads(json_str)

    assert loaded["bot_id"] == "freqtrade-freqforge"
    assert loaded["strategy_id"] == "strat_btc_01"
    assert loaded["status"] == "valid"
    assert loaded["stop_loss"] is not None
    assert loaded["take_profit"] is not None
    assert isinstance(loaded["reason_codes"], list)


def test_exit_evidence_gate_result_json_roundtrip() -> None:
    evidence_list = enrich_fleet_exit_evidence(
        bot_metrics_map={},
        fleet_bot_ids=DEFAULT_FLEET_BOT_IDS,
    )
    result = evaluate_exit_evidence_gate(evidence_list)
    d = result.to_dict()

    json_str = json.dumps(d)
    loaded = json.loads(json_str)

    assert loaded["verdict"] in ("candidate", "blocked", "inconclusive")
    assert len(loaded["per_bot_evidence"]) == 4


# ==========================================================================
# 9. Negative bot (zero entry price) remains blocked
# ==========================================================================

def test_zero_entry_price_blocks_exit() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("0"),
            "atr": D("500"),
            "candle_count": 100,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_BLOCKED
    assert evidence.stop_loss is None
    assert evidence.take_profit is None


# ==========================================================================
# 10. Mixed fleet: some valid, some soft-blocked → INCONCLUSIVE
# ==========================================================================

def test_mixed_fleet_valid_and_soft_blocked_is_inconclusive() -> None:
    # FreqForge: valid evidence
    valid = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={"entry_price": D("50000"), "atr": D("500"), "candle_count": 100},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    assert valid.status == STATUS_VALID

    # Unknown bot: soft blocked
    soft = enrich_bot_exit_evidence(
        "unknown-bot-xyz",
        bot_metrics={},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    assert soft.status == STATUS_BLOCKED
    assert REASON_STRATEGY_MAPPING_MISSING in soft.reason_codes

    result = evaluate_exit_evidence_gate([valid, soft])

    assert result.verdict == GATE_VERDICT_INCONCLUSIVE
    assert any("mixed_evidence" in r for r in result.reasons)


# ==========================================================================
# 11. All soft-blocked (strategy_mapping_missing) → INCONCLUSIVE
# ==========================================================================

def test_all_soft_blocked_is_inconclusive() -> None:
    evidence_list = [
        enrich_bot_exit_evidence(
            f"bot-{i}",
            bot_metrics={},
            strategy_bot_mapping={},
        )
        for i in range(4)
    ]

    for e in evidence_list:
        assert e.status == STATUS_BLOCKED
        assert REASON_STRATEGY_MAPPING_MISSING in e.reason_codes

    result = evaluate_exit_evidence_gate(evidence_list)

    assert result.verdict == GATE_VERDICT_INCONCLUSIVE


# ==========================================================================
# 12. Hard block (insufficient candles) → BLOCKED
# ==========================================================================

def test_hard_block_insufficient_candles_is_blocked() -> None:
    blocked = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("50000"),
            "atr": D("500"),
            "candle_count": 5,  # insufficient
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    assert blocked.status == STATUS_BLOCKED

    result = evaluate_exit_evidence_gate([blocked])
    assert result.verdict == GATE_VERDICT_BLOCKED


# ==========================================================================
# 13. All valid → CANDIDATE
# ==========================================================================

def test_all_valid_exit_evidence_is_candidate() -> None:
    bot_metrics_map = {
        bid: {"entry_price": D("50000"), "atr": D("500"), "candle_count": 100}
        for bid in DEFAULT_FLEET_BOT_IDS
    }

    evidence_list = enrich_fleet_exit_evidence(
        bot_metrics_map=bot_metrics_map,
        fleet_bot_ids=DEFAULT_FLEET_BOT_IDS,
    )

    for e in evidence_list:
        assert e.status == STATUS_VALID, f"{e.bot_id}: {e.reason_codes}"

    result = evaluate_exit_evidence_gate(evidence_list)
    assert result.verdict == GATE_VERDICT_CANDIDATE


# ==========================================================================
# 14. Empty evidence list → INCONCLUSIVE
# ==========================================================================

def test_empty_evidence_list_is_inconclusive() -> None:
    result = evaluate_exit_evidence_gate([])
    assert result.verdict == GATE_VERDICT_INCONCLUSIVE


# ==========================================================================
# 15. Fixed mode with minimum_risk_distance works
# ==========================================================================

def test_fixed_mode_with_minimum_risk_distance() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={
            "entry_price": D("100"),
            "direction": "long",
            "exit_mode": "fixed",
            "minimum_risk_distance": D("2"),
            "candle_count": 100,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.mode == "fixed"
    assert evidence.stop_loss is not None
    assert evidence.take_profit is not None


# ==========================================================================
# 16. Short Bollinger mode works
# ==========================================================================

def test_short_bollinger_mode() -> None:
    evidence = enrich_bot_exit_evidence(
        "freqai-rebel",
        bot_metrics={
            "entry_price": D("100"),
            "direction": "short",
            "exit_mode": "bollinger_distance",
            "bollinger_lower": D("95"),
            "bollinger_mid": D("100"),
            "bollinger_upper": D("110"),
            "candle_count": 50,
        },
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )

    assert evidence.status == STATUS_VALID
    assert evidence.direction == DIRECTION_SHORT
    assert evidence.mode == MODE_BOLLINGER_DISTANCE


# ==========================================================================
# 17. is_valid / is_blocked properties
# ==========================================================================

def test_is_valid_and_is_blocked_properties() -> None:
    valid = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={"entry_price": D("50000"), "atr": D("500"), "candle_count": 100},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    assert valid.is_valid is True
    assert valid.is_blocked is False

    blocked = enrich_bot_exit_evidence(
        "unknown-bot",
        bot_metrics={},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    assert blocked.is_valid is False
    assert blocked.is_blocked is True


# ==========================================================================
# 18. No secrets / no forbidden patterns
# ==========================================================================

def test_no_forbidden_patterns_in_exit_evidence() -> None:
    """Ensure exit evidence dicts don't leak credentials or secrets."""
    evidence = enrich_bot_exit_evidence(
        "freqtrade-freqforge",
        bot_metrics={"entry_price": D("50000"), "atr": D("500"), "candle_count": 100},
        strategy_bot_mapping=DEFAULT_STRATEGY_BOT_MAPPING,
    )
    d = evidence.to_dict()

    forbidden = {
        "api_key", "secret", "password", "token", "credential",
        "private_key", "wallet", "passphrase",
    }
    json_str = json.dumps(d).lower()
    for pattern in forbidden:
        assert pattern not in json_str, f"forbidden pattern {pattern!r} found"
