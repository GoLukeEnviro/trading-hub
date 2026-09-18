"""Tests for the RiskGuard baseline contract v1.

Covers the contract's binding rules end-to-end:

- baseline builder / strict validator / atomic persistence / initializer
- mandate contract (expiry, replay, snapshot, measurement window, limits)
- consumer derivation (`derive_riskguard_status`) incl. BLOCK_ENTRY
- kill-switch interlock (HALT_NEW / EMERGENCY block the apply path)
- positive admissible dry-run case
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from si_v2.apply_actuator.controlled_apply_actuator import (
    check_kill_switch,
    derive_riskguard_status,
)
from si_v2.risk.riskguard_baseline import (
    ALLOWED_BOTS,
    CONTRACT_NAME,
    CONTRACT_VERSION,
    MIN_APPLY_COOLDOWN_DAYS,
    SCHEMA_VERSION,
    build_conservative_baseline,
    initialize_baseline,
    mandate_is_expired,
    validate_mandate,
    validate_state,
    write_state_atomic,
)

BINDING_COMMIT = "df17a27af6eb11a9a69dc9c93da11c08ab11719a"


def _baseline(**kwargs: object) -> dict[str, object]:
    return build_conservative_baseline(binding_commit=BINDING_COMMIT, **kwargs)  # type: ignore[arg-type]


def _valid_mandate(**overrides: object) -> dict[str, object]:
    now = datetime.now(tz=UTC)
    mandate: dict[str, object] = {
        "proposal_id": "max_open_trades_3_to_2",
        "bot_id": "freqtrade-freqforge-canary",
        "parameter": "max_open_trades",
        "from_value": 3,
        "to_value": 2,
        "allowlist_match": True,
        "evidence_refs": ["cycle:20260918T143928Z", "docs/reports/agent0-dryrun-operational-2026-09-18.md"],
        "dry_run_mandate": "DRY_RUN_ONLY",
        "snapshot_id": "snap-20260918T143928Z",
        "canary_target": True,
        "measurement_window": {
            "opened_at_utc": now.isoformat(),
            "closes_at_utc": (now + timedelta(hours=6)).isoformat(),
        },
        "rollback_criterion": "measurement decision ROLLBACK/INVALID",
        "expires_at_utc": (now + timedelta(hours=24)).isoformat(),
        "revision": "rev-001",
        "state": "ACCEPTED",
    }
    mandate.update(overrides)
    return mandate


# ---------------------------------------------------------------------------
# 1. Valid conservative baseline
# ---------------------------------------------------------------------------


class TestValidBaseline:
    def test_baseline_validates(self) -> None:
        result = validate_state(_baseline())
        assert result.ok, result.reason

    def test_baseline_shape(self) -> None:
        state = _baseline()
        assert state["schema_version"] == SCHEMA_VERSION
        assert state["contract_name"] == CONTRACT_NAME
        assert state["contract_version"] == CONTRACT_VERSION
        assert state["mode"] == "ACTIVE"
        assert state["operating_mode"] == "DRY_RUN_ONLY"
        assert state["live_authority"] is False
        assert state["mandates"] == []
        assert state["summary"]["status"] == "ACTIVE"
        assert state["bot_scope"]["allowed"] == sorted(ALLOWED_BOTS)
        assert state["limits"]["min_apply_cooldown_days"] == MIN_APPLY_COOLDOWN_DAYS

    def test_derives_pass_for_consumer(self) -> None:
        assert derive_riskguard_status(_baseline()) == "PASS"


# ---------------------------------------------------------------------------
# 2-4. Missing / empty / invalid state (fail-closed)
# ---------------------------------------------------------------------------


class TestFailClosedReads:
    def test_missing_state_not_a_dict(self) -> None:
        result = validate_state(None)
        assert not result.ok
        assert result.reason == "state_not_a_dict"

    def test_empty_state(self) -> None:
        result = validate_state({})
        assert not result.ok
        assert result.reason.startswith("missing_required_field:")

    def test_invalid_json_is_not_a_dict(self, tmp_path: Path) -> None:
        # A corrupt file never parses to a dict -> validator fail-closes.
        raw = "{not valid json"
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        assert not validate_state(parsed).ok

    def test_consumer_fails_closed_on_missing_file(self, tmp_path: Path) -> None:
        from si_v2.apply_actuator.controlled_apply_actuator import read_riskguard_status

        result = read_riskguard_status(tmp_path / "missing.json")
        assert not result.passed
        assert "fail-closed" in result.reason.lower()


# ---------------------------------------------------------------------------
# 5-7. Schema version / unknown bot / rebel
# ---------------------------------------------------------------------------


class TestScopeAndVersion:
    def test_unknown_schema_version(self) -> None:
        state = _baseline()
        state["schema_version"] = 99
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "unknown_schema_version:99"

    def test_unknown_bot_in_scope(self) -> None:
        state = _baseline()
        state["bot_scope"]["allowed"] = ["freqtrade-freqforge", "freqtrade-mystery"]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "unknown_bot_in_scope:freqtrade-mystery"

    def test_rebel_forbidden_in_state_scope(self) -> None:
        state = _baseline()
        state["bot_scope"]["allowed"] = ["freqai-rebel"]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "forbidden_bot_in_scope:freqai-rebel"

    def test_rebel_forbidden_in_mandate(self) -> None:
        result = validate_mandate(_valid_mandate(bot_id="freqai-rebel"))
        assert not result.ok
        assert result.reason == "mandate_forbidden_bot:freqai-rebel"

    def test_non_trading_actor_rejected(self) -> None:
        state = _baseline()
        state["bot_scope"]["allowed"] = ["freqtrade-freqforge", "rainbow"]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "non_trading_actor_in_scope:rainbow"


# ---------------------------------------------------------------------------
# 8-10. Forbidden fields / dry_run=false / limit breach
# ---------------------------------------------------------------------------


class TestForbiddenFields:
    def test_dry_run_false_is_forbidden_field(self) -> None:
        state = _baseline()
        state["pairs"]["BTC/USDT"]["dry_run"] = False  # type: ignore[index]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "forbidden_field:pairs.BTC/USDT.dry_run"

    def test_locked_field_rejected(self) -> None:
        state = _baseline()
        state["strategy"] = "SomeOtherStrategy"
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "forbidden_field:strategy"

    def test_live_authority_true_rejected(self) -> None:
        state = _baseline()
        state["live_authority"] = True
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "live_authority_must_be_false"

    def test_operating_mode_must_be_dry_run(self) -> None:
        state = _baseline()
        state["operating_mode"] = "LIVE"
        result = validate_state(state)
        assert not result.ok
        assert result.reason.startswith("operating_mode_not_dry_run_only")

    def test_limit_breach_rejected(self) -> None:
        state = _baseline()
        state["limits"]["parameters"]["max_open_trades"] = [1, 99]  # type: ignore[index]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "limit_breach:max_open_trades"

    def test_unknown_parameter_rejected(self) -> None:
        state = _baseline()
        state["limits"]["parameters"]["mystery_param"] = [1, 2]  # type: ignore[index]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "unknown_parameter:mystery_param"

    def test_cooldown_below_minimum_rejected(self) -> None:
        state = _baseline()
        state["limits"]["min_apply_cooldown_days"] = 1  # type: ignore[index]
        result = validate_state(state)
        assert not result.ok
        assert result.reason == "cooldown_below_accepted_minimum"


# ---------------------------------------------------------------------------
# 11-14. Mandate contract: expiry, snapshot, window, replay
# ---------------------------------------------------------------------------


class TestMandateContract:
    def test_valid_mandate(self) -> None:
        result = validate_mandate(_valid_mandate())
        assert result.ok, result.reason

    def test_expired_mandate(self) -> None:
        past = datetime.now(tz=UTC) - timedelta(hours=1)
        result = validate_mandate(_valid_mandate(expires_at_utc=past.isoformat()))
        assert not result.ok
        assert result.reason == "mandate_expired"

    def test_mandate_is_expired_helper(self) -> None:
        past = datetime.now(tz=UTC) - timedelta(minutes=1)
        assert mandate_is_expired(_valid_mandate(expires_at_utc=past.isoformat()))
        future = datetime.now(tz=UTC) + timedelta(hours=1)
        assert not mandate_is_expired(_valid_mandate(expires_at_utc=future.isoformat()))

    def test_missing_snapshot(self) -> None:
        mandate = _valid_mandate()
        del mandate["snapshot_id"]
        result = validate_mandate(mandate)
        assert not result.ok
        assert result.reason == "mandate_missing_field:snapshot_id"

    def test_empty_snapshot(self) -> None:
        result = validate_mandate(_valid_mandate(snapshot_id="  "))
        assert not result.ok
        assert result.reason == "mandate_snapshot_missing"

    def test_missing_measurement_window(self) -> None:
        mandate = _valid_mandate()
        del mandate["measurement_window"]
        result = validate_mandate(mandate)
        assert not result.ok
        assert result.reason == "mandate_missing_field:measurement_window"

    def test_replay_detected(self) -> None:
        result = validate_mandate(
            _valid_mandate(),
            seen_revisions=frozenset({"rev-001"}),
        )
        assert not result.ok
        assert result.reason == "mandate_replay_detected"

    def test_unknown_parameter_in_mandate(self) -> None:
        result = validate_mandate(_valid_mandate(parameter="stake_currency"))
        assert not result.ok
        assert result.reason == "mandate_parameter_not_allowlisted:stake_currency"

    def test_mandate_limit_breach(self) -> None:
        result = validate_mandate(_valid_mandate(parameter="max_open_trades", to_value=999))
        assert not result.ok
        assert result.reason == "mandate_limit_breach:max_open_trades=999"

    def test_non_canary_mandate_rejected(self) -> None:
        result = validate_mandate(_valid_mandate(canary_target=False))
        assert not result.ok
        assert result.reason == "mandate_canary_target_not_true"

    def test_mandate_must_be_dry_run_only(self) -> None:
        result = validate_mandate(_valid_mandate(dry_run_mandate="LIVE"))
        assert not result.ok
        assert result.reason == "mandate_not_dry_run_only"

    def test_non_accepted_states_rejected(self) -> None:
        for state_name in ("REJECTED", "BLOCK_ENTRY", "EXPIRED", "INVALID"):
            result = validate_mandate(_valid_mandate(state=state_name))
            assert not result.ok
            assert result.reason == f"mandate_state_not_accepted:{state_name!r}"

    def test_missing_evidence_refs(self) -> None:
        result = validate_mandate(_valid_mandate(evidence_refs=[]))
        assert not result.ok
        assert result.reason == "mandate_evidence_refs_missing"


# ---------------------------------------------------------------------------
# 15. BLOCK_ENTRY pair verdict blocks the consumer
# ---------------------------------------------------------------------------


class TestBlockEntry:
    def test_active_block_entry_fails_derivation(self) -> None:
        state = _baseline()
        state["pairs"]["ETH/USDT"]["verdict"] = "BLOCK_ENTRY"  # type: ignore[index]
        assert derive_riskguard_status(state) == "FAIL"

    def test_block_entry_in_mandate_state_rejected(self) -> None:
        result = validate_mandate(_valid_mandate(state="BLOCK_ENTRY"))
        assert not result.ok


# ---------------------------------------------------------------------------
# 16-17. Kill-switch interlock: HALT_NEW / EMERGENCY block the apply path
# ---------------------------------------------------------------------------


class TestKillSwitchInterlock:
    def _ks(self, tmp_path: Path, mode: str) -> Path:
        path = tmp_path / "kill_switch.json"
        path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "safety_state": mode,
                    "mode": mode,
                    "reason": "test",
                    "triggered_at": "",
                    "triggered_by": "test",
                    "auto_clear_at": "",
                    "actions": {},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_halt_new_blocks_apply_gate(self, tmp_path: Path) -> None:
        gate = check_kill_switch(self._ks(tmp_path, "HALT_NEW"))
        assert not gate.passed
        assert "HALT_NEW" in gate.reason

    def test_emergency_blocks_apply_gate(self, tmp_path: Path) -> None:
        gate = check_kill_switch(self._ks(tmp_path, "EMERGENCY"))
        assert not gate.passed
        assert "EMERGENCY" in gate.reason

    def test_normal_passes_kill_switch_gate(self, tmp_path: Path) -> None:
        gate = check_kill_switch(self._ks(tmp_path, "NORMAL"))
        assert gate.passed


# ---------------------------------------------------------------------------
# 18. Positive admissible dry-run case (end-to-end on temp paths)
# ---------------------------------------------------------------------------


class TestPositiveDryRunCase:
    def test_initialize_then_read_pass(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        record = initialize_baseline(
            state_path,
            binding_commit=BINDING_COMMIT,
            backup_dir=tmp_path / "backup",
        )
        assert record["action"] == "initialized"
        assert record["validation"]["ok"] is True

        written = json.loads(state_path.read_text(encoding="utf-8"))
        assert validate_state(written).ok
        assert derive_riskguard_status(written) == "PASS"

    def test_reinitialize_backs_up_previous_state(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        state_path.write_text(json.dumps({"old": "state"}), encoding="utf-8")
        record = initialize_baseline(
            state_path,
            binding_commit=BINDING_COMMIT,
            backup_dir=tmp_path / "backup",
        )
        assert record["action"] == "reinitialized"
        assert record["backup_path"] is not None
        backup = Path(record["backup_path"])
        assert backup.exists()
        assert json.loads(backup.read_text(encoding="utf-8")) == {"old": "state"}

    def test_reinitialize_unchanged_when_identical(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        first = initialize_baseline(state_path, binding_commit=BINDING_COMMIT, backup_dir=tmp_path / "b")
        assert first["action"] == "initialized"
        # Re-running with the same binding commit re-writes identical bytes.
        second = initialize_baseline(state_path, binding_commit=BINDING_COMMIT, backup_dir=tmp_path / "b")
        assert second["action"] in ("unchanged", "reinitialized")

    def test_atomic_write_and_readback(self, tmp_path: Path) -> None:
        state_path = tmp_path / "riskguard_state.json"
        record = write_state_atomic(_baseline(), state_path)
        assert state_path.exists()
        assert record["sha256"]
        assert json.loads(state_path.read_text(encoding="utf-8"))["mode"] == "ACTIVE"

    def test_mandate_roundtrip_through_state(self) -> None:
        state = _baseline()
        state["mandates"] = [_valid_mandate()]
        result = validate_state(state)
        assert result.ok, result.reason


# ---------------------------------------------------------------------------
# Schema validation (JSON Schema artifact, contract section 8)
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def _schema(self) -> dict:
        import pytest

        pytest.importorskip("jsonschema")
        schema_path = (
            Path(__file__).resolve().parents[1] / "contracts" / "riskguard_state.schema.json"
        )
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def test_baseline_matches_json_schema(self) -> None:
        import jsonschema

        jsonschema.validate(instance=_baseline(), schema=self._schema())

    def test_state_with_mandate_matches_json_schema(self) -> None:
        import jsonschema

        state = _baseline()
        state["mandates"] = [_valid_mandate()]
        jsonschema.validate(instance=state, schema=self._schema())
