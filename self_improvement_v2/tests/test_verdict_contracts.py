"""Phase 1E tests — Verdict contracts (Issue #599)."""
from __future__ import annotations

from si_v2.risk.verdict_contracts import (
    CONTRACT_MAP,
    EntryGateVerdict,
    FleetSafetyState,
    ObservationClassification,
    combine_entry_and_fleet,
    entry_gate_to_str,
    entry_verdict_from_observation,
    is_observation_only,
    is_trading_authoritative,
    reduce_verdicts,
    str_to_entry_gate,
    str_to_fleet_safety,
    str_to_observation,
)


class TestEntryGateVerdict:
    def test_block_entry_is_blocked(self) -> None:
        assert EntryGateVerdict.BLOCK_ENTRY.is_blocked()

    def test_accepted_is_tradeable(self) -> None:
        assert EntryGateVerdict.ACCEPTED.is_tradeable()

    def test_watch_only_not_blocked_not_tradeable(self) -> None:
        v = EntryGateVerdict.WATCH_ONLY
        assert not v.is_blocked()
        assert not v.is_tradeable()

    def test_str_to_entry_gate_known(self) -> None:
        assert str_to_entry_gate("BLOCK_ENTRY") == EntryGateVerdict.BLOCK_ENTRY
        assert str_to_entry_gate("WATCH_ONLY") == EntryGateVerdict.WATCH_ONLY
        assert str_to_entry_gate("ACCEPTED") == EntryGateVerdict.ACCEPTED

    def test_str_to_entry_gate_unknown_fail_closed(self) -> None:
        """Unknown verdict must fail closed (BLOCK_ENTRY)."""
        assert str_to_entry_gate("BOGUS") == EntryGateVerdict.BLOCK_ENTRY
        assert str_to_entry_gate("") == EntryGateVerdict.BLOCK_ENTRY

    def test_str_to_entry_gate_observation_neutral_not_entry(self) -> None:
        """'NEUTRAL' is an observation term, not an entry verdict → BLOCK_ENTRY."""
        assert str_to_entry_gate("NEUTRAL") == EntryGateVerdict.BLOCK_ENTRY

    def test_roundtrip(self) -> None:
        for v in EntryGateVerdict:
            assert str_to_entry_gate(entry_gate_to_str(v)) == v


class TestObservationClassification:
    def test_is_not_trading_authoritative(self) -> None:
        assert not is_trading_authoritative(ObservationClassification.NEUTRAL)

    def test_is_observation_only(self) -> None:
        assert is_observation_only(ObservationClassification.CAUTION)

    def test_observation_never_authorizes_trade(self) -> None:
        """Observation must never return an entry verdict that authorizes."""
        for obs in ObservationClassification:
            entry = entry_verdict_from_observation(obs)
            assert entry == EntryGateVerdict.WATCH_ONLY
            assert not entry.is_tradeable()
            assert not entry.is_blocked()

    def test_str_to_observation_known(self) -> None:
        assert str_to_observation("NEUTRAL") == ObservationClassification.NEUTRAL

    def test_str_to_observation_unknown_neutral(self) -> None:
        assert str_to_observation("BOGUS") == ObservationClassification.NEUTRAL


class TestFleetSafetyState:
    def test_precedence_order(self) -> None:
        assert FleetSafetyState.EMERGENCY.precedence() > FleetSafetyState.HALT_NEW.precedence()
        assert FleetSafetyState.HALT_NEW.precedence() > FleetSafetyState.REDUCE_ONLY.precedence()
        assert FleetSafetyState.REDUCE_ONLY.precedence() > FleetSafetyState.NORMAL.precedence()

    def test_most_restrictive(self) -> None:
        assert FleetSafetyState.most_restrictive(
            FleetSafetyState.NORMAL, FleetSafetyState.EMERGENCY
        ) == FleetSafetyState.EMERGENCY

    def test_str_to_fleet_safety_unknown_fail_closed(self) -> None:
        assert str_to_fleet_safety("BOGUS") == FleetSafetyState.HALT_NEW


class TestCombineEntryAndFleet:
    def test_normal_fleet_passes_through(self) -> None:
        for entry in EntryGateVerdict:
            result = combine_entry_and_fleet(entry, FleetSafetyState.NORMAL)
            assert result == entry

    def test_non_normal_fleet_blocks_all(self) -> None:
        for fleet in [FleetSafetyState.HALT_NEW, FleetSafetyState.EMERGENCY,
                       FleetSafetyState.REDUCE_ONLY]:
            result = combine_entry_and_fleet(EntryGateVerdict.ACCEPTED, fleet)
            assert result == EntryGateVerdict.BLOCK_ENTRY

    def test_block_entry_stays_blocked(self) -> None:
        """BLOCK_ENTRY cannot be neutralized even by NORMAL fleet."""
        result = combine_entry_and_fleet(EntryGateVerdict.BLOCK_ENTRY,
                                         FleetSafetyState.NORMAL)
        assert result == EntryGateVerdict.BLOCK_ENTRY


class TestReduceVerdicts:
    def test_emergency_wins(self) -> None:
        assert reduce_verdicts(["ACCEPTED", "WATCH_ONLY", "EMERGENCY"]) == "EMERGENCY"

    def test_block_entry_wins_over_accepted(self) -> None:
        assert reduce_verdicts(["ACCEPTED", "BLOCK_ENTRY"]) == "BLOCK_ENTRY"

    def test_unknown_fails_closed(self) -> None:
        assert reduce_verdicts(["ACCEPTED", "BOGUS"]) == "BOGUS"

    def test_all_accepted(self) -> None:
        assert reduce_verdicts(["ACCEPTED", "ACCEPTED"]) == "ACCEPTED"

    def test_neutral_lowest(self) -> None:
        assert reduce_verdicts(["NEUTRAL", "ACCEPTED"]) == "ACCEPTED"


class TestContractMap:
    def test_contract_map_exists(self) -> None:
        assert CONTRACT_MAP["version"] == 1
        assert "trading_authority" in CONTRACT_MAP["layers"]
        assert "observation" in CONTRACT_MAP["layers"]
        assert "fleet_safety" in CONTRACT_MAP["layers"]

    def test_observation_cannot_authorize_trade(self) -> None:
        layer = CONTRACT_MAP["layers"]["observation"]
        assert layer["can_authorize_trade"] is False

    def test_trading_authority_can_authorize(self) -> None:
        layer = CONTRACT_MAP["layers"]["trading_authority"]
        assert layer["can_authorize_trade"] is True
        assert layer["fail_closed"] is True


class TestBlockEntryNeutralizationGuard:
    """Regression: BLOCK_ENTRY must never be neutralized by any helper."""

    def test_observation_to_entry_never_blocks(self) -> None:
        for obs in ObservationClassification:
            entry = entry_verdict_from_observation(obs)
            assert entry != EntryGateVerdict.BLOCK_ENTRY
            assert entry != EntryGateVerdict.ACCEPTED

    def test_block_entry_survives_fleet_normal(self) -> None:
        result = combine_entry_and_fleet(EntryGateVerdict.BLOCK_ENTRY,
                                         FleetSafetyState.NORMAL)
        assert result.is_blocked()

    def test_block_entry_survives_reduce_all_accepted(self) -> None:
        # Block must always win, even if 100 accepted around it
        result = reduce_verdicts(["ACCEPTED"] * 10 + ["BLOCK_ENTRY"])
        assert result == "BLOCK_ENTRY"
