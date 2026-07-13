"""Tests for fleet_post_fleet_measurement_watcher.py — Phase 10.4.

All tests use tmp_path, fake measurement start records, fake evidence
snapshots — no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.rollout.fleet_post_fleet_measurement_watcher import (
    PostFleetMeasurementInput,
    run_post_fleet_measurement_watcher,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_measurement_start_record(
    tmp_path: Path,
    *,
    target_bot: str = "freqtrade-regime-hybrid",
    ceremony_status: str = "EXECUTED",
    runtime_mutation: str = "NONE",
    expected_parameter: str = "max_open_trades",
    expected_value: int = 2,
) -> str:
    """Write a synthetic measurement start record."""
    global _serial
    _serial += 1
    record: dict[str, object] = {
        "event": "measurement_start_record",
        "target_bot": target_bot,
        "ceremony_status": ceremony_status,
        "measurement_started_at_utc": "2026-07-01T12:00:00Z",
        "expected_parameter": expected_parameter,
        "expected_value": expected_value,
        "runtime_mutation": runtime_mutation,
    }
    path = tmp_path / f"measurement_start_{_serial}.json"
    path.write_text(json.dumps(record))
    return str(path)


def _make_evidence_snapshot(
    *,
    label: str = "T1",
    target_closed: int = 5,
    target_open: int = 1,
    target_profit: float = 2.5,
    target_pf: float | None = 1.5,
    control_closed: int = 4,
    control_open: int = 0,
    control_profit: float = 1.0,
    control_pf: float | None = 1.2,
    source: str = "test_fixture",
) -> dict[str, object]:
    """Build a synthetic evidence snapshot dict."""
    target: dict[str, object] = {
        "bot_id": "freqtrade-regime-hybrid",
        "closed_trades_since_t0": target_closed,
        "open_trades": target_open,
        "profit_abs_since_t0": target_profit,
    }
    if target_pf is not None:
        target["profit_factor_since_t0"] = target_pf

    control: dict[str, object] = {
        "bot_id": "freqtrade-freqforge",
        "closed_trades_since_t0": control_closed,
        "open_trades": control_open,
        "profit_abs_since_t0": control_profit,
    }
    if control_pf is not None:
        control["profit_factor_since_t0"] = control_pf

    return {
        "timestamp_utc": "2026-07-01T14:00:00Z",
        "source": source,
        "label": label,
        "target": target,
        "control": control,
    }


def _default_input(
    tmp_path: Path,
    *,
    target_bot: str = "freqtrade-regime-hybrid",
    min_closed_trades: int = 3,
    allow_extend: bool = True,
) -> PostFleetMeasurementInput:
    """Build a default watcher input for testing."""
    record_path = _make_measurement_start_record(tmp_path, target_bot=target_bot)
    return PostFleetMeasurementInput(
        measurement_start_record_path=record_path,
        target_bot=target_bot,
        min_closed_trades=min_closed_trades,
        allow_extend=allow_extend,
    )


# ---------------------------------------------------------------------------
# Tests: Blocked paths
# ---------------------------------------------------------------------------


def test_blocks_missing_start_record(tmp_path: Path) -> None:
    """Block when the measurement start record does not exist."""
    input_ = PostFleetMeasurementInput(
        measurement_start_record_path=str(tmp_path / "nonexistent.json"),
        target_bot="freqtrade-regime-hybrid",
    )
    result = run_post_fleet_measurement_watcher(
        input_, decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_BLOCKED"
    assert any(
        "measurement_start_record_not_readable" in r
        for r in result.blocked_reasons
    )


def test_blocks_invalid_start_record(tmp_path: Path) -> None:
    """Block when the start record has invalid fields."""
    path = tmp_path / "bad_record.json"
    path.write_text(json.dumps({"event": "wrong_event"}))
    input_ = PostFleetMeasurementInput(
        measurement_start_record_path=str(path),
        target_bot="freqtrade-regime-hybrid",
    )
    result = run_post_fleet_measurement_watcher(
        input_, decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_BLOCKED"


def test_blocks_target_bot_mismatch(tmp_path: Path) -> None:
    """Block when target bot in start record doesn't match input."""
    record_path = _make_measurement_start_record(
        tmp_path, target_bot="freqai-rebel",
    )
    input_ = PostFleetMeasurementInput(
        measurement_start_record_path=record_path,
        target_bot="freqtrade-regime-hybrid",
    )
    result = run_post_fleet_measurement_watcher(
        input_, decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_BLOCKED"
    assert any("target_bot_mismatch" in r for r in result.blocked_reasons)


def test_blocks_no_evidence_snapshot(tmp_path: Path) -> None:
    """Block when no evidence snapshot is provided."""
    input_ = _default_input(tmp_path)
    result = run_post_fleet_measurement_watcher(
        input_, decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_BLOCKED"
    assert any("no_evidence_snapshot" in r for r in result.blocked_reasons)


def test_blocks_invalid_evidence_snapshot(tmp_path: Path) -> None:
    """Block when evidence snapshot has invalid schema."""
    input_ = _default_input(tmp_path)
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot={"bad": "data"},
        decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_BLOCKED"
    assert any(
        "missing_or_invalid" in r for r in result.blocked_reasons
    )


# ---------------------------------------------------------------------------
# Tests: Not ready
# ---------------------------------------------------------------------------


def test_not_ready_insufficient_closed_trades(tmp_path: Path) -> None:
    """Return NOT_READY when both arms have too few closed trades."""
    input_ = _default_input(tmp_path, min_closed_trades=3)
    snapshot = _make_evidence_snapshot(
        target_closed=1, control_closed=1,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_NOT_READY"
    assert result.final_decision == "NONE"
    assert any("insufficient_closed_trades" in r for r in result.blocked_reasons)


def test_not_ready_target_insufficient(tmp_path: Path) -> None:
    """Return NOT_READY when only target has too few closed trades."""
    input_ = _default_input(tmp_path, min_closed_trades=3)
    snapshot = _make_evidence_snapshot(
        target_closed=1, control_closed=5,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
    )
    assert result.status == "MEASUREMENT_NOT_READY"
    assert any("target_insufficient_closed_trades" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Tests: KEEP decision
# ---------------------------------------------------------------------------


def test_keep_when_target_outperforms(tmp_path: Path) -> None:
    """Emit KEEP_FLEET_OVERLAY when target outperforms control."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=2.5,
        control_closed=4, control_profit=1.0,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "KEEP_FLEET_OVERLAY"
    assert result.target_bot == "freqtrade-regime-hybrid"


def test_keep_when_target_matches(tmp_path: Path) -> None:
    """Emit KEEP_FLEET_OVERLAY when target matches control."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=1.0,
        control_closed=4, control_profit=1.0,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "KEEP_FLEET_OVERLAY"


# ---------------------------------------------------------------------------
# Tests: ROLLBACK decision
# ---------------------------------------------------------------------------


def test_rollback_when_target_underperforms(tmp_path: Path) -> None:
    """Emit ROLLBACK_FLEET_OVERLAY when target clearly underperforms."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=-1.0, target_pf=0.8,
        control_closed=4, control_profit=2.0, control_pf=1.5,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "ROLLBACK_FLEET_OVERLAY"


# ---------------------------------------------------------------------------
# Tests: EXTEND decision
# ---------------------------------------------------------------------------


def test_extend_when_ambiguous(tmp_path: Path) -> None:
    """Emit EXTEND_MEASUREMENT when evidence is ambiguous."""
    input_ = _default_input(tmp_path, allow_extend=True)
    # profit_gap < -0.01 but target_pf >= control_pf → ambiguous
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=0.5, target_pf=1.3,
        control_closed=4, control_profit=1.0, control_pf=1.2,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "EXTEND_MEASUREMENT"


def test_rollback_when_ambiguous_and_no_extend(tmp_path: Path) -> None:
    """Rollback when evidence is ambiguous and allow_extend=False."""
    input_ = _default_input(tmp_path, allow_extend=False)
    # profit_gap < -0.01 but target_pf >= control_pf → ambiguous
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=0.5, target_pf=1.3,
        control_closed=4, control_profit=1.0, control_pf=1.2,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "ROLLBACK_FLEET_OVERLAY"


# ---------------------------------------------------------------------------
# Tests: Artifact writing
# ---------------------------------------------------------------------------


def test_writes_decision_pack(tmp_path: Path) -> None:
    """Watcher writes a decision pack JSON file."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot()
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.decision_pack_path
    pack_path = Path(result.decision_pack_path)
    assert pack_path.exists()
    pack = json.loads(pack_path.read_text())
    assert pack["event"] == "post_fleet_measurement_decision"
    assert pack["decision"] == "KEEP_FLEET_OVERLAY"
    assert pack["runtime_mutation"] == "NONE"


def test_decision_pack_has_measurement_points(tmp_path: Path) -> None:
    """Decision pack includes measurement points."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(label="T1")
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    pack = json.loads(Path(result.decision_pack_path).read_text())
    points = pack.get("measurement_points", [])
    assert len(points) == 1
    assert points[0]["label"] == "T1"
    assert points[0]["target_closed_trades"] == 5
    assert points[0]["control_closed_trades"] == 4


# ---------------------------------------------------------------------------
# Tests: Result serialization
# ---------------------------------------------------------------------------


def test_result_serializable(tmp_path: Path) -> None:
    """PostFleetMeasurementResult must be JSON-serializable."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot()
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["event"] == "post_fleet_measurement_result"
    assert deserialized["status"] == "FINAL_DECISION_EMITTED"


# ---------------------------------------------------------------------------
# Tests: No live trading fields
# ---------------------------------------------------------------------------


def test_no_live_trading_fields(tmp_path: Path) -> None:
    """Result must not contain live trading fields."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot()
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
    )
    d = result.to_dict()
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "LIVE" not in d["status"]


# ---------------------------------------------------------------------------
# Tests: Runtime mutation is always NONE
# ---------------------------------------------------------------------------


def test_runtime_mutation_always_none(tmp_path: Path) -> None:
    """Decision pack must have runtime_mutation=NONE."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot()
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    pack = json.loads(Path(result.decision_pack_path).read_text())
    assert pack["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Tests: Evidence snapshot with missing profit factor
# ---------------------------------------------------------------------------


def test_keep_without_profit_factor(tmp_path: Path) -> None:
    """KEEP decision works when profit factor is not available."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(
        target_closed=5, target_profit=2.5, target_pf=None,
        control_closed=4, control_profit=1.0, control_pf=None,
    )
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    assert result.status == "FINAL_DECISION_EMITTED"
    assert result.final_decision == "KEEP_FLEET_OVERLAY"


# ---------------------------------------------------------------------------
# Tests: Measurement point label extraction
# ---------------------------------------------------------------------------


def test_preserves_snapshot_label(tmp_path: Path) -> None:
    """Watcher preserves the label from the evidence snapshot."""
    input_ = _default_input(tmp_path)
    snapshot = _make_evidence_snapshot(label="T2")
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",
    )
    pack = json.loads(Path(result.decision_pack_path).read_text())
    points = pack.get("measurement_points", [])
    assert points[0]["label"] == "T2"


# ---------------------------------------------------------------------------
# Tests: Stale measurement
# ---------------------------------------------------------------------------


def test_blocks_stale_measurement(tmp_path: Path) -> None:
    """Block when measurement is older than max age."""
    record_path = _make_measurement_start_record(tmp_path)
    input_ = PostFleetMeasurementInput(
        measurement_start_record_path=record_path,
        target_bot="freqtrade-regime-hybrid",
        max_measurement_age_hours=1,
    )
    snapshot = _make_evidence_snapshot()
    result = run_post_fleet_measurement_watcher(
        input_,
        evidence_snapshot=snapshot,
        decision_pack_dir=tmp_path,
        now_utc="2026-07-02T12:00:00Z",  # >1 hour after start
    )
    assert result.status == "MEASUREMENT_BLOCKED"
    assert any("measurement_stale" in r for r in result.blocked_reasons)
