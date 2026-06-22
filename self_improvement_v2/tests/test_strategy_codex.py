"""Tests for Strategy Codex registry."""

from __future__ import annotations

import json
import re

import pytest

from si_v2.strategy.strategy_codex import (
    _VALID_STRATEGY_ID_RE,
    EvidenceStatus,
    PromotionStatus,
    Strategy,
    StrategyCodex,
    create_initial_codex,
)

# -- Fixtures ---------------------------------------------------------------

@pytest.fixture
def codex() -> StrategyCodex:
    return create_initial_codex()


@pytest.fixture
def strategies(codex: StrategyCodex) -> list[Strategy]:
    return codex.strategies


# -- Test: initial strategies exist ----------------------------------------

def test_codex_contains_three_initial_strategies(codex: StrategyCodex) -> None:
    assert len(codex) == 3
    ids = [s.strategy_id for s in codex]
    assert "strat_btc_01" in ids
    assert "strat_eth_01" in ids
    assert "strat_sol_01" in ids


def test_all_strategy_ids_unique(strategies: list[Strategy]) -> None:
    ids = [s.strategy_id for s in strategies]
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"


def test_strategy_ids_match_format(strategies: list[Strategy]) -> None:
    pattern = re.compile(_VALID_STRATEGY_ID_RE)
    for s in strategies:
        assert pattern.match(s.strategy_id), (
            f"{s.strategy_id!r} does not match {_VALID_STRATEGY_ID_RE!r}"
        )


# -- Test: required fields non-empty ---------------------------------------

_REQUIRED_STRING_FIELDS = [
    "strategy_id",
    "name",
    "market_scope",
    "timeframe_scope",
    "entry_logic",
    "exit_logic",
    "risk_model",
    "minimum_data_requirements",
]


def test_required_string_fields_non_empty(strategies: list[Strategy]) -> None:
    for s in strategies:
        for field in _REQUIRED_STRING_FIELDS:
            value = getattr(s, field)
            assert isinstance(value, str) and value.strip(), (
                f"{s.strategy_id}: field {field!r} is empty"
            )


def test_required_indicators_not_empty(strategies: list[Strategy]) -> None:
    for s in strategies:
        assert len(s.required_indicators) > 0, (
            f"{s.strategy_id}: required_indicators is empty"
        )
        for ind in s.required_indicators:
            assert isinstance(ind, str) and ind.strip()


def test_known_failure_modes_not_empty(strategies: list[Strategy]) -> None:
    for s in strategies:
        assert len(s.known_failure_modes) > 0, (
            f"{s.strategy_id}: known_failure_modes is empty"
        )


# -- Test: conservative defaults -------------------------------------------

def test_all_strategies_start_as_draft(strategies: list[Strategy]) -> None:
    for s in strategies:
        assert s.promotion_status == PromotionStatus.DRAFT, (
            f"{s.strategy_id}: expected draft, got {s.promotion_status}"
        )


def test_all_evidence_statuses_start_not_run(strategies: list[Strategy]) -> None:
    for s in strategies:
        assert s.backtest_status == EvidenceStatus.NOT_RUN
        assert s.walk_forward_status == EvidenceStatus.NOT_RUN
        assert s.paper_trading_status == EvidenceStatus.NOT_RUN


def test_all_strategies_have_empty_evidence_refs(strategies: list[Strategy]) -> None:
    for s in strategies:
        assert s.evidence_refs == [], (
            f"{s.strategy_id}: expected empty evidence_refs"
        )


# -- Test: promotion gate --------------------------------------------------

def test_promotion_to_candidate_without_evidence_is_blocked() -> None:
    s = Strategy(
        strategy_id="strat_test_01",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.CANDIDATE,
        evidence_refs=[],
    )
    errors = s.validate_promotion()
    assert len(errors) == 1
    assert "no evidence_refs" in errors[0]


def test_promotion_to_shadow_without_evidence_is_blocked() -> None:
    s = Strategy(
        strategy_id="strat_test_02",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.SHADOW,
        evidence_refs=[],
    )
    errors = s.validate_promotion()
    assert len(errors) == 1
    assert "no evidence_refs" in errors[0]


def test_promotion_to_paper_live_without_evidence_is_blocked() -> None:
    s = Strategy(
        strategy_id="strat_test_03",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.PAPER_LIVE,
        evidence_refs=[],
    )
    errors = s.validate_promotion()
    assert len(errors) == 1
    assert "no evidence_refs" in errors[0]


def test_draft_without_evidence_is_allowed() -> None:
    s = Strategy(
        strategy_id="strat_test_04",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.DRAFT,
        evidence_refs=[],
    )
    assert s.validate_promotion() == []


def test_blocked_without_evidence_is_allowed() -> None:
    s = Strategy(
        strategy_id="strat_test_05",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.BLOCKED,
        evidence_refs=[],
    )
    assert s.validate_promotion() == []


def test_candidate_with_evidence_is_allowed() -> None:
    s = Strategy(
        strategy_id="strat_test_06",
        name="Test",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
        promotion_status=PromotionStatus.CANDIDATE,
        evidence_refs=["evidence/backtest_2026.json"],
    )
    assert s.validate_promotion() == []


# -- Test: duplicate ID detection ------------------------------------------

def test_duplicate_strategy_id_raises() -> None:
    codex = create_initial_codex()
    duplicate = Strategy(
        strategy_id="strat_btc_01",
        name="Duplicate",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
    )
    with pytest.raises(ValueError, match="duplicate strategy_id"):
        codex.add(duplicate)


def test_codex_validate_ids_unique_finds_duplicates() -> None:
    codex = StrategyCodex()
    s1 = Strategy(
        strategy_id="strat_a_01",
        name="A",
        market_scope="BTC/USDT",
        timeframe_scope="5m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
    )
    s2 = Strategy(
        strategy_id="strat_a_01",
        name="A Duplicate",
        market_scope="ETH/USDT",
        timeframe_scope="15m",
        entry_logic="test",
        exit_logic="test",
        risk_model="test",
    )
    codex.strategies = [s1, s2]
    errors = codex.validate_ids_unique()
    assert len(errors) == 1
    assert "duplicate" in errors[0]


# -- Test: find by ID ------------------------------------------------------

def test_find_existing_strategy(codex: StrategyCodex) -> None:
    s = codex.find("strat_eth_01")
    assert s is not None
    assert s.strategy_id == "strat_eth_01"
    assert s.name == "ETH Momentum Break"


def test_find_nonexistent_strategy(codex: StrategyCodex) -> None:
    assert codex.find("strat_nonexistent_99") is None


# -- Test: serialization ---------------------------------------------------

def test_strategy_to_dict_is_json_serializable(strategies: list[Strategy]) -> None:
    for s in strategies:
        d = s.to_dict()
        assert isinstance(d, dict)
        # Must be JSON-serializable
        json.dumps(d)


def test_codex_to_dict_is_json_serializable(codex: StrategyCodex) -> None:
    d = codex.to_dict()
    assert d["count"] == 3
    assert len(d["strategies"]) == 3
    json.dumps(d)


def test_to_dict_roundtrip_preserves_fields(codex: StrategyCodex) -> None:
    d = codex.to_dict()
    for entry in d["strategies"]:
        for field in _REQUIRED_STRING_FIELDS:
            assert field in entry, f"missing field {field!r}"
        assert "required_indicators" in entry
        assert "promotion_status" in entry
        assert "evidence_refs" in entry


# -- Test: no strategy is candidate without evidence -----------------------

def test_no_strategy_starts_as_candidate_without_evidence(
    strategies: list[Strategy],
) -> None:
    for s in strategies:
        if s.promotion_status in (
            PromotionStatus.CANDIDATE,
            PromotionStatus.SHADOW,
            PromotionStatus.PAPER_LIVE,
        ):
            assert len(s.evidence_refs) > 0, (
                f"{s.strategy_id}: promoted to {s.promotion_status} without evidence"
            )


# -- Test: empty codex -----------------------------------------------------

def test_empty_codex_is_falsy() -> None:
    assert not StrategyCodex()


def test_populated_codex_is_truthy() -> None:
    codex = create_initial_codex()
    assert codex


# -- Test: status enum values are controlled -------------------------------

def test_promotion_status_values() -> None:
    valid = {"draft", "candidate", "shadow", "paper_live", "blocked", "retired"}
    assert {s.value for s in PromotionStatus} == valid


def test_evidence_status_values() -> None:
    valid = {"not_run", "pending", "passed", "failed", "insufficient_evidence"}
    assert {s.value for s in EvidenceStatus} == valid


# -- Test: codex validation of all promotions ------------------------------

def test_initial_codex_passes_validate_promotions(codex: StrategyCodex) -> None:
    errors = codex.validate_promotions()
    assert errors == [], f"unexpected promotion errors: {errors}"
