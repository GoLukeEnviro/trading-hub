"""Tests for autonomous_measurement_watcher.py — Phase 7.

All tests use tmp_path and FakeEvidenceReader — no real DB, API, or
Docker calls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from si_v2.measurement.autonomous_measurement_watcher import (
    CANARY_BOT_ID,
    CONTROL_BOT_ID,
    EXPECTED_NEXT_COMPONENT,
    FleetEvidenceReader,
    MeasurementPoint,
    MeasurementWatcherInput,
    MeasurementWatcherResult,
    T0ActivationRecord,
    run_autonomous_measurement_watcher,
)

# ---------------------------------------------------------------------------
# Fake evidence reader
# ---------------------------------------------------------------------------


class FakeEvidenceReader:
    """Produces configurable fake evidence snapshots."""

    def __init__(
        self,
        *,
        canary_closed: int = 5,
        control_closed: int = 4,
        canary_profit: float = 2.0,
        control_profit: float = 1.0,
        canary_pf: float | None = 1.5,
        control_pf: float | None = 1.3,
        raise_error: bool = False,
    ) -> None:
        self.canary_closed = canary_closed
        self.control_closed = control_closed
        self.canary_profit = canary_profit
        self.control_profit = control_profit
        self.canary_pf = canary_pf
        self.control_pf = control_pf
        self.raise_error = raise_error

    def read_measurement_snapshot(
        self,
        *,
        change_id: str,
        t0_timestamp_utc: str,
        control_bot: str,
        canary_bot: str,
    ) -> dict[str, object]:
        if self.raise_error:
            raise FileNotFoundError("simulated evidence error")
        return {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "source": "fake_evidence_reader",
            "label": "T1",
            "control": {
                "bot_id": control_bot,
                "closed_trades_since_t0": self.control_closed,
                "open_trades": 0,
                "profit_abs_since_t0": self.control_profit,
                "profit_factor_since_t0": self.control_pf,
            },
            "canary": {
                "bot_id": canary_bot,
                "closed_trades_since_t0": self.canary_closed,
                "open_trades": 1,
                "profit_abs_since_t0": self.canary_profit,
                "profit_factor_since_t0": self.canary_pf,
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_t0_record(tmp_path: Path, **overrides: Any) -> str:
    """Write a valid T0 activation record and return its path."""
    defaults = {
        "event": "runtime_ceremony_t0_active",
        "change_id": "test-change-001",
        "candidate_id": "test-candidate-001",
        "target_bot": CANARY_BOT_ID,
        "runtime_status": "CEREMONY_EXECUTED_GREEN",
        "runtime_proof_status": "GREEN",
        "t0_timestamp_utc": datetime.now(UTC).isoformat(),
        "next_required_component": EXPECTED_NEXT_COMPONENT,
    }
    defaults.update(overrides)
    path = tmp_path / "t0_active_record.json"
    path.write_text(json.dumps(defaults))
    return str(path)


def make_fake_evidence(tmp_path: Path, **overrides: Any) -> str:
    """Write a fake evidence JSON file and return its path."""
    defaults = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "source": "fake_evidence_file",
        "label": "T1",
        "control": {
            "bot_id": CONTROL_BOT_ID,
            "closed_trades_since_t0": 4,
            "open_trades": 0,
            "profit_abs_since_t0": 1.0,
            "profit_factor_since_t0": 1.2,
        },
        "canary": {
            "bot_id": CANARY_BOT_ID,
            "closed_trades_since_t0": 5,
            "open_trades": 1,
            "profit_abs_since_t0": 2.0,
            "profit_factor_since_t0": 1.5,
        },
    }
    defaults.update(overrides)
    path = tmp_path / "evidence_snapshot.json"
    path.write_text(json.dumps(defaults))
    return str(path)


def run_watcher(
    tmp_path: Path,
    *,
    t0_overrides: dict[str, Any] | None = None,
    evidence_reader: FleetEvidenceReader | None = None,
    input_overrides: dict[str, Any] | None = None,
) -> MeasurementWatcherResult:
    """Helper to run the watcher with a valid T0 record."""
    t0_path = make_t0_record(tmp_path, **(t0_overrides or {}))
    dec_dir = tmp_path / "decision_packs"
    inputs: dict[str, Any] = {
        "t0_record_path": t0_path,
        "fleet_evidence_ref": "test_ref",
        "min_closed_trades_per_arm": 3,
        "max_measurement_age_hours": 72,
        "allow_extend": True,
    }
    inputs.update(input_overrides or {})
    watcher_input = MeasurementWatcherInput(**inputs)
    return run_autonomous_measurement_watcher(
        watcher_input,
        evidence_reader=evidence_reader,
        decision_pack_dir=dec_dir,
    )


# ======================================================================
# Tests
# ======================================================================


class TestT0RecordValidation:
    """T0 activation record path and content checks."""

    def test_blocks_missing_t0_record(self, tmp_path: Path) -> None:
        """1. Block when T0 record path is empty."""
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path="",
                fleet_evidence_ref="test_ref",
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("empty" in r for r in result.blocked_reasons)

    def test_blocks_missing_t0_file(self, tmp_path: Path) -> None:
        """Block when T0 file doesn't exist."""
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=str(tmp_path / "nonexistent.json"),
                fleet_evidence_ref="test_ref",
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("exist" in r.lower() for r in result.blocked_reasons)

    def test_blocks_t0_not_green(self, tmp_path: Path) -> None:
        """2. Block when T0 runtime_status is not CEREMONY_EXECUTED_GREEN."""
        result = run_watcher(
            tmp_path,
            t0_overrides={"runtime_status": "CEREMONY_EXECUTED_YELLOW"},
            evidence_reader=FakeEvidenceReader(),
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("not_green" in r for r in result.blocked_reasons)

    def test_blocks_wrong_target_bot(self, tmp_path: Path) -> None:
        """3. Block when T0 target_bot doesn't match canary."""
        result = run_watcher(
            tmp_path,
            t0_overrides={"target_bot": "wrong-bot"},
            evidence_reader=FakeEvidenceReader(),
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("wrong_target_bot" in r for r in result.blocked_reasons)

    def test_blocks_wrong_next_component(self, tmp_path: Path) -> None:
        """4. Block when next_required_component is wrong."""
        result = run_watcher(
            tmp_path,
            t0_overrides={"next_required_component": "wrong_component"},
            evidence_reader=FakeEvidenceReader(),
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("wrong_next_component" in r for r in result.blocked_reasons)

    def test_blocks_stale_t0(self, tmp_path: Path) -> None:
        """Block when T0 is older than max age."""
        t0_path = make_t0_record(
            tmp_path,
            t0_timestamp_utc="2020-01-01T00:00:00Z",
        )
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref="test_ref",
                max_measurement_age_hours=1,
            ),
            evidence_reader=FakeEvidenceReader(),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("stale" in r.lower() for r in result.blocked_reasons)


class TestEvidenceValidation:
    """Evidence snapshot validation checks."""

    def test_blocks_missing_evidence_snapshot(self, tmp_path: Path) -> None:
        """5. Block when evidence snapshot is missing."""
        t0_path = make_t0_record(tmp_path)
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(tmp_path / "missing.json"),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("exist" in r.lower() for r in result.blocked_reasons)

    def test_blocks_malformed_evidence(self, tmp_path: Path) -> None:
        """Block when evidence is malformed JSON."""
        t0_path = make_t0_record(tmp_path)
        ev_path = tmp_path / "bad.json"
        ev_path.write_text("not json")
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(ev_path),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"

    def test_blocks_evidence_reader_error(self, tmp_path: Path) -> None:
        """Block when evidence reader raises."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(raise_error=True),
        )
        assert result.status == "MEASUREMENT_BLOCKED"
        assert any("error" in r.lower() for r in result.blocked_reasons)


class TestReadiness:
    """Measurement readiness checks."""

    def test_not_ready_when_too_few_closed_trades(
        self, tmp_path: Path,
    ) -> None:
        """6. Not ready when both arms have too few closed trades."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=1,
                control_closed=0,
            ),
        )
        assert result.status == "MEASUREMENT_NOT_READY"
        assert any("insufficient" in r.lower() for r in result.blocked_reasons)

    def test_not_ready_when_canary_too_few(self, tmp_path: Path) -> None:
        """Not ready when canary alone has too few closed trades."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=2,
                control_closed=5,
            ),
        )
        assert result.status == "MEASUREMENT_NOT_READY"
        assert any("canary" in r for r in result.blocked_reasons)


class TestDecisionEmission:
    """Final decision emission tests."""

    def test_keep_when_canary_outperforms_control(
        self, tmp_path: Path,
    ) -> None:
        """7. KEEP when canary outperforms control."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5,
                control_closed=4,
                canary_profit=2.0,
                control_profit=1.0,
                canary_pf=1.5,
                control_pf=1.2,
            ),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "KEEP_CANARY_OVERLAY"

    def test_extend_when_evidence_ambiguous(
        self, tmp_path: Path,
    ) -> None:
        """8. EXTEND when evidence is ambiguous."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5,
                control_closed=4,
                canary_profit=1.0,
                control_profit=1.2,
                canary_pf=1.4,
                control_pf=1.2,
            ),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "EXTEND_MEASUREMENT"

    def test_rollback_when_canary_underperforms(
        self, tmp_path: Path,
    ) -> None:
        """9. ROLLBACK when canary clearly underperforms."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5,
                control_closed=4,
                canary_profit=0.5,
                control_profit=3.0,
                canary_pf=0.8,
                control_pf=1.5,
            ),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "ROLLBACK_CANARY_OVERLAY"

    def test_rollback_when_pf_critical(self, tmp_path: Path) -> None:
        """Rollback when canary profit factor is critically below control."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5,
                control_closed=4,
                canary_profit=1.5,
                control_profit=2.5,
                canary_pf=0.7,
                control_pf=1.6,
            ),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "ROLLBACK_CANARY_OVERLAY"


class TestDecisionPack:
    """Decision pack file checks."""

    def _run_and_get_pack(
        self, tmp_path: Path, reader: FleetEvidenceReader,
    ) -> dict[str, object]:
        result = run_watcher(tmp_path, evidence_reader=reader)
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.decision_pack_path
        pack_path = Path(result.decision_pack_path)
        assert pack_path.exists()
        return json.loads(pack_path.read_text())

    def test_decision_pack_written_for_keep(
        self, tmp_path: Path,
    ) -> None:
        """10. Decision pack written for KEEP."""
        pack = self._run_and_get_pack(
            tmp_path,
            FakeEvidenceReader(
                canary_closed=5, control_closed=4,
                canary_profit=2.0, control_profit=1.0,
            ),
        )
        assert pack["decision"] == "KEEP_CANARY_OVERLAY"
        assert pack["runtime_mutation"] == "NONE"
        assert pack["event"] == "autonomous_measurement_decision"

    def test_decision_pack_written_for_extend(
        self, tmp_path: Path,
    ) -> None:
        """11. Decision pack written for EXTEND."""
        pack = self._run_and_get_pack(
            tmp_path,
            FakeEvidenceReader(
                canary_closed=5, control_closed=4,
                canary_profit=0.5, control_profit=1.0,
                canary_pf=1.5, control_pf=1.3,
            ),
        )
        assert pack["decision"] == "EXTEND_MEASUREMENT"

    def test_decision_pack_written_for_rollback(
        self, tmp_path: Path,
    ) -> None:
        """12. Decision pack written for ROLLBACK."""
        pack = self._run_and_get_pack(
            tmp_path,
            FakeEvidenceReader(
                canary_closed=5, control_closed=4,
                canary_profit=0.3, control_profit=3.0,
                canary_pf=0.6, control_pf=1.8,
            ),
        )
        assert pack["decision"] == "ROLLBACK_CANARY_OVERLAY"


class TestSafetyAndSerialization:
    """Safety invariants and serialization."""

    def test_no_runtime_mutation_fields(
        self, tmp_path: Path,
    ) -> None:
        """13. No runtime mutation is indicated in result."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        # Verify we can read the pack and it says NONE
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["runtime_mutation"] == "NONE"

    def test_result_serializable(
        self, tmp_path: Path,
    ) -> None:
        """14. Result is JSON-serializable."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5, control_closed=4,
            ),
        )
        d = result.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0
        # Deserialize back
        loaded = json.loads(serialized)
        assert loaded["status"] == "FINAL_DECISION_EMITTED"
        assert loaded["final_decision"] == "KEEP_CANARY_OVERLAY"

    def test_reader_contract_receives_change_id_and_t0(
        self, tmp_path: Path,
    ) -> None:
        """15. Evidence reader receives change_id and t0_timestamp_utc."""
        received: dict[str, str] = {}

        class CapturingReader:
            def read_measurement_snapshot(
                self,
                *,
                change_id: str,
                t0_timestamp_utc: str,
                control_bot: str,
                canary_bot: str,
            ) -> dict[str, object]:
                received["change_id"] = change_id
                received["t0_timestamp_utc"] = t0_timestamp_utc
                return {
                    "timestamp_utc": "2026-07-01T12:00:00Z",
                    "source": "capture_test",
                    "label": "T1",
                    "control": {
                        "bot_id": control_bot,
                        "closed_trades_since_t0": 4,
                        "open_trades": 0,
                        "profit_abs_since_t0": 1.0,
                        "profit_factor_since_t0": 1.2,
                    },
                    "canary": {
                        "bot_id": canary_bot,
                        "closed_trades_since_t0": 5,
                        "open_trades": 1,
                        "profit_abs_since_t0": 2.0,
                        "profit_factor_since_t0": 1.5,
                    },
                }

        t0_path = make_t0_record(
            tmp_path,
            change_id="test-change-abc",
            t0_timestamp_utc="2026-07-01T12:00:00Z",
        )
        run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref="ref",
            ),
            evidence_reader=CapturingReader(),
            decision_pack_dir=tmp_path / "packs",
            now_utc="2026-07-01T13:00:00Z",
        )
        assert received.get("change_id") == "test-change-abc"
        assert received.get("t0_timestamp_utc") == "2026-07-01T12:00:00Z"

    def test_allow_extend_false_rollbacks_ambiguous(
        self, tmp_path: Path,
    ) -> None:
        """When allow_extend=False, ambiguous evidence rolls back."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(
                canary_closed=5,
                control_closed=4,
                canary_profit=0.5,
                control_profit=1.0,
                canary_pf=1.1,
                control_pf=1.3,
            ),
            input_overrides={"allow_extend": False},
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "ROLLBACK_CANARY_OVERLAY"

    def test_model_from_dict(self) -> None:
        """T0ActivationRecord.from_dict parses correctly."""
        data: dict[str, object] = {
            "change_id": "c1",
            "candidate_id": "cand1",
            "target_bot": CANARY_BOT_ID,
            "runtime_status": "CEREMONY_EXECUTED_GREEN",
            "runtime_proof_status": "GREEN",
            "t0_timestamp_utc": "2026-07-01T12:00:00Z",
            "next_required_component": EXPECTED_NEXT_COMPONENT,
        }
        record = T0ActivationRecord.from_dict(data)
        assert record.change_id == "c1"
        assert record.runtime_status == "CEREMONY_EXECUTED_GREEN"

    def test_measurement_point_to_dict(self) -> None:
        """MeasurementPoint.to_dict serializes correctly."""
        mp = MeasurementPoint(
            label="T1",
            timestamp_utc="2026-07-01T12:00:00Z",
            canary_closed_trades=5,
            control_closed_trades=4,
            canary_open_trades=1,
            control_open_trades=0,
            canary_profit_abs=2.0,
            control_profit_abs=1.0,
            canary_profit_factor=1.5,
            control_profit_factor=1.2,
            evidence_source="test",
        )
        d = mp.to_dict()
        assert d["label"] == "T1"
        assert d["canary_closed_trades"] == 5

    def test_result_with_evidence_file_fallback(
        self, tmp_path: Path,
    ) -> None:
        """Watcher works with evidence file fallback."""
        t0_path = make_t0_record(tmp_path)
        ev_path = make_fake_evidence(tmp_path)
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=ev_path,
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "KEEP_CANARY_OVERLAY"

    def test_evidence_validation_rejects_missing_fields(
        self, tmp_path: Path,
    ) -> None:
        """Block when evidence is missing required fields."""
        t0_path = make_t0_record(tmp_path)
        bad_ev = {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "test",
            # control is missing
            "canary": {
                "bot_id": CANARY_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 1,
                "profit_abs_since_t0": 2.0,
            },
        }
        ev_path = tmp_path / "bad_ev.json"
        ev_path.write_text(json.dumps(bad_ev))
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(ev_path),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "MEASUREMENT_BLOCKED"

class TestMeasurementLabels:
    """MeasurementPoint label semantics (T0 is activation record, not a measurement point)."""

    def test_snapshot_label_defaults_to_t1(self, tmp_path: Path) -> None:
        """Evidence without 'label' defaults to T1."""
        t0_path = make_t0_record(tmp_path)
        ev = {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "no_label_test",
            "control": {
                "bot_id": CONTROL_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 0,
                "profit_abs_since_t0": 2.0,
                "profit_factor_since_t0": 1.5,
            },
            "canary": {
                "bot_id": CANARY_BOT_ID,
                "closed_trades_since_t0": 6,
                "open_trades": 1,
                "profit_abs_since_t0": 3.0,
                "profit_factor_since_t0": 1.6,
            },
        }
        ev_path = tmp_path / "no_label.json"
        ev_path.write_text(json.dumps(ev))
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(ev_path),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert len(result.measurement_points) >= 1
        assert result.measurement_points[0].label == "T1"

    def test_snapshot_label_t2_preserved(self, tmp_path: Path) -> None:
        """Evidence with label=T2 preserves it."""
        t0_path = make_t0_record(tmp_path)
        ev = {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "t2_label_test",
            "label": "T2",
            "control": {
                "bot_id": CONTROL_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 0,
                "profit_abs_since_t0": 2.0,
                "profit_factor_since_t0": 1.5,
            },
            "canary": {
                "bot_id": CANARY_BOT_ID,
                "closed_trades_since_t0": 6,
                "open_trades": 1,
                "profit_abs_since_t0": 3.0,
                "profit_factor_since_t0": 1.6,
            },
        }
        ev_path = tmp_path / "t2_label.json"
        ev_path.write_text(json.dumps(ev))
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(ev_path),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        assert len(result.measurement_points) >= 1
        assert result.measurement_points[0].label == "T2"

    def test_t0_record_is_not_used_as_measurement_point(self, tmp_path: Path) -> None:
        """No MeasurementPoint has label T0."""
        t0_path = make_t0_record(tmp_path)
        ev = {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "check_label_test",
            "label": "T1",
            "control": {
                "bot_id": CONTROL_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 0,
                "profit_abs_since_t0": 2.0,
                "profit_factor_since_t0": 1.5,
            },
            "canary": {
                "bot_id": CANARY_BOT_ID,
                "closed_trades_since_t0": 6,
                "open_trades": 1,
                "profit_abs_since_t0": 3.0,
                "profit_factor_since_t0": 1.6,
            },
        }
        ev_path = tmp_path / "check_label.json"
        ev_path.write_text(json.dumps(ev))
        result = run_autonomous_measurement_watcher(
            MeasurementWatcherInput(
                t0_record_path=t0_path,
                fleet_evidence_ref=str(ev_path),
            ),
            decision_pack_dir=tmp_path / "packs",
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        for mp in result.measurement_points:
            assert mp.label != "T0", "Unexpected T0 label in measurement point"

class TestStatisticalEvidence:
    """Phase 8B — Statistical evidence enrichment tests."""

    def test_statistical_evidence_disabled_preserves_existing_decision_pack_shape(
        self, tmp_path: Path,
    ) -> None:
        """Decision pack without stat has null stat fields."""
        result = run_watcher(
            tmp_path,
            evidence_reader=FakeEvidenceReader(),
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        # Legacy shape preserved
        assert pack["runtime_mutation"] == "NONE"
        # New stat fields present but null
        assert pack["statistical_evidence"] is None
        assert pack["statistical_conflict"] is not None
        assert pack["statistical_conflict"]["has_conflict"] is False

    def test_statistical_evidence_enabled_with_samples_adds_statistical_evidence(
        self, tmp_path: Path,
    ) -> None:
        """Stat enabled with trade samples adds stat evidence to pack."""
        reader = FakeEvidenceReader(
            canary_closed=5, control_closed=5,
            canary_profit=2.0, control_profit=1.0,
        )
        canary_trades = [{"trade_id": str(i), "profit_abs": 0.2,
                          "profit_ratio": 0.01,
                          "close_timestamp_utc": "2026-07-01T10:00:00Z"}
                         for i in range(5)]
        control_trades = [{"trade_id": str(i), "profit_abs": 0.1,
                           "profit_ratio": 0.005,
                           "close_timestamp_utc": "2026-07-01T10:00:00Z"}
                          for i in range(5)]
        reader.canary_trades = canary_trades
        reader.control_trades = control_trades
        reader._extra_canary = "trades_since_t0"
        reader._extra_control = "trades_since_t0"

        # We need the reader to include trades in the snapshot
        original_read = reader.read_measurement_snapshot

        def read_with_trades(**kw):
            snap = original_read(**kw)
            snap["canary"]["trades_since_t0"] = canary_trades
            snap["control"]["trades_since_t0"] = control_trades
            return snap

        reader.read_measurement_snapshot = read_with_trades

        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "stat_packs"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
            evidence_class="A",
        )
        result = run_autonomous_measurement_watcher(
            watcher_input,
            evidence_reader=reader,
            decision_pack_dir=dec_dir,
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["statistical_evidence"] is not None
        assert pack["statistical_evidence"]["recommendation"] == "STAT_KEEP"
        assert pack["statistical_evidence"]["evidence_grade"] in ("STRONG", "MODERATE", "WEAK")

    def test_statistical_evidence_missing_samples_does_not_block_simple_decision(
        self, tmp_path: Path,
    ) -> None:
        """Missing trade samples with stat enabled does not block."""
        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "missing_stat"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
        )
        result = run_autonomous_measurement_watcher(
            watcher_input,
            evidence_reader=FakeEvidenceReader(),
            decision_pack_dir=dec_dir,
        )
        assert result.status == "FINAL_DECISION_EMITTED"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        # Simple decision still works
        assert pack["decision"] in ("KEEP_CANARY_OVERLAY", "EXTEND_MEASUREMENT")
        # Stat evidence is null (no trades in snapshot)
        assert pack["statistical_evidence"] is None

    def test_statistical_keep_aligns_with_simple_keep_no_conflict(
        self, tmp_path: Path,
    ) -> None:
        """Aligned KEEP/STAT_KEEP produces no conflict."""
        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "align_keep"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
        )
        # Monkeypatch to return STAT_KEEP
        import si_v2.measurement.autonomous_measurement_watcher as watcher_mod

        original = watcher_mod._maybe_evaluate_statistical_evidence

        def fake_stat(**kw):
            return {
                "status": "STAT_READY",
                "recommendation": "STAT_KEEP",
                "evidence_grade": "MODERATE",
                "canary_mean_profit": 0.3,
                "control_mean_profit": 0.1,
                "mean_profit_diff": 0.2,
                "bootstrap_ci_low": 0.05,
                "bootstrap_ci_high": 0.35,
                "effect_size": 0.8,
            }

        watcher_mod._maybe_evaluate_statistical_evidence = fake_stat
        try:
            result = run_autonomous_measurement_watcher(
                watcher_input,
                evidence_reader=FakeEvidenceReader(
                    canary_closed=5, control_closed=4,
                    canary_profit=2.0, control_profit=1.0,
                ),
                decision_pack_dir=dec_dir,
            )
        finally:
            watcher_mod._maybe_evaluate_statistical_evidence = original

        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "KEEP_CANARY_OVERLAY"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["statistical_conflict"]["has_conflict"] is False
        assert pack["statistical_conflict"]["severity"] == "NONE"

    def test_statistical_rollback_conflicts_with_simple_keep_hard_conflict(
        self, tmp_path: Path,
    ) -> None:
        """KEEP vs STAT_ROLLBACK produces HARD conflict."""
        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "hard_conflict"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
        )
        import si_v2.measurement.autonomous_measurement_watcher as watcher_mod

        original = watcher_mod._maybe_evaluate_statistical_evidence

        def fake_rollback(**kw):
            return {
                "status": "STAT_READY",
                "recommendation": "STAT_ROLLBACK",
                "evidence_grade": "STRONG",
                "canary_mean_profit": 0.1,
                "control_mean_profit": 0.3,
                "mean_profit_diff": -0.2,
                "bootstrap_ci_low": -0.35,
                "bootstrap_ci_high": -0.05,
                "effect_size": -0.8,
            }

        watcher_mod._maybe_evaluate_statistical_evidence = fake_rollback
        try:
            result = run_autonomous_measurement_watcher(
                watcher_input,
                evidence_reader=FakeEvidenceReader(
                    canary_closed=5, control_closed=4,
                    canary_profit=2.0, control_profit=1.0,
                ),
                decision_pack_dir=dec_dir,
            )
        finally:
            watcher_mod._maybe_evaluate_statistical_evidence = original

        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "KEEP_CANARY_OVERLAY"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["statistical_conflict"]["has_conflict"] is True
        assert pack["statistical_conflict"]["severity"] == "HARD"

    def test_statistical_extend_soft_conflict_with_simple_keep(
        self, tmp_path: Path,
    ) -> None:
        """KEEP vs STAT_EXTEND produces SOFT conflict."""
        import si_v2.measurement.autonomous_measurement_watcher as watcher_mod

        original = watcher_mod._maybe_evaluate_statistical_evidence
        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "soft_conflict"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
        )

        def fake_extend(**kw):
            return {
                "status": "STAT_READY",
                "recommendation": "STAT_EXTEND",
                "evidence_grade": "WEAK",
                "canary_mean_profit": 0.15,
                "control_mean_profit": 0.14,
                "mean_profit_diff": 0.01,
                "bootstrap_ci_low": -0.05,
                "bootstrap_ci_high": 0.07,
                "effect_size": 0.1,
            }

        watcher_mod._maybe_evaluate_statistical_evidence = fake_extend
        try:
            result = run_autonomous_measurement_watcher(
                watcher_input,
                evidence_reader=FakeEvidenceReader(
                    canary_closed=5, control_closed=4,
                    canary_profit=2.0, control_profit=1.0,
                ),
                decision_pack_dir=dec_dir,
            )
        finally:
            watcher_mod._maybe_evaluate_statistical_evidence = original

        assert result.status == "FINAL_DECISION_EMITTED"
        assert result.final_decision == "KEEP_CANARY_OVERLAY"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["statistical_conflict"]["has_conflict"] is True
        assert pack["statistical_conflict"]["severity"] == "SOFT"

    def test_statistical_evidence_class_passed_to_engine(
        self, tmp_path: Path,
    ) -> None:
        """Evidence class is passed through to stats."""
        from si_v2.measurement.autonomous_measurement_watcher import (
            _maybe_evaluate_statistical_evidence,
        )

        snapshot: dict[str, object] = {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "test",
            "label": "T1",
            "control": {
                "bot_id": CONTROL_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 0,
                "profit_abs_since_t0": 0.5,
                "profit_factor_since_t0": 1.2,
                "trades_since_t0": [
                    {"trade_id": str(i), "profit_abs": 0.1,
                     "profit_ratio": 0.01,
                     "close_timestamp_utc": "2026-07-01T10:00:00Z"}
                    for i in range(5)
                ],
            },
            "canary": {
                "bot_id": CANARY_BOT_ID,
                "closed_trades_since_t0": 5,
                "open_trades": 1,
                "profit_abs_since_t0": 1.0,
                "profit_factor_since_t0": 1.5,
                "trades_since_t0": [
                    {"trade_id": str(i), "profit_abs": 0.2,
                     "profit_ratio": 0.02,
                     "close_timestamp_utc": "2026-07-01T10:00:00Z"}
                    for i in range(5)
                ],
            },
        }

        stat = _maybe_evaluate_statistical_evidence(
            enabled=True,
            change_id="ch-1",
            candidate_id="cand-1",
            snapshot=snapshot,
            canary_bot=CANARY_BOT_ID,
            control_bot=CONTROL_BOT_ID,
            evidence_class="B",
            bootstrap_iterations=1000,
            confidence_level=0.90,
            random_seed=42,
        )
        assert stat is not None
        assert stat["status"] == "STAT_INSUFFICIENT"  # class B needs 15
        assert "INSUFFICIENT" in str(stat["evidence_grade"])

    def test_statistical_result_never_executes_runtime_mutation(
        self, tmp_path: Path,
    ) -> None:
        """Decision pack runtime_mutation remains NONE with stat."""
        import si_v2.measurement.autonomous_measurement_watcher as watcher_mod

        original = watcher_mod._maybe_evaluate_statistical_evidence

        def fake_stat(**kw):
            return {
                "status": "STAT_READY",
                "recommendation": "STAT_ROLLBACK",
            }

        watcher_mod._maybe_evaluate_statistical_evidence = fake_stat
        t0_path = make_t0_record(tmp_path)
        dec_dir = tmp_path / "no_mut"
        watcher_input = MeasurementWatcherInput(
            t0_record_path=t0_path,
            fleet_evidence_ref="test_ref",
            use_statistical_evidence=True,
        )
        try:
            result = run_autonomous_measurement_watcher(
                watcher_input,
                evidence_reader=FakeEvidenceReader(
                    canary_closed=5, control_closed=4,
                ),
                decision_pack_dir=dec_dir,
            )
        finally:
            watcher_mod._maybe_evaluate_statistical_evidence = original

        assert result.status == "FINAL_DECISION_EMITTED"
        pack_path = Path(result.decision_pack_path)
        pack = json.loads(pack_path.read_text())
        assert pack["runtime_mutation"] == "NONE"
