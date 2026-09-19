"""Tests for the runtime-execution wiring gate (P3).

The switch (`activation.json` -> `runtime_execution.wired`) is only honoured
when the referenced rehearsal evidence exists, parses, and carries a PASS
result. Every other combination stays prepare-only or blocks — the switch
alone is never enough.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.pipeline.apply_chain_evaluation import (
    _read_runtime_wiring,
)

MARKER_ID = "APPROVED_AUTONOMOUS_DRY_RUN_AGENT0"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _record(state_dir: Path, **overrides: object) -> Path:
    record: dict[str, object] = {"marker": MARKER_ID, "mode": "AUTONOMOUS_DRY_RUN"}
    record.update(overrides)
    record_path = state_dir / "activation.json"
    _write_json(record_path, record)
    return record_path


def _rehearsal(path: Path, *, result: str = "P2_REHEARSAL_PASS") -> Path:
    _write_json(path, {"run_id": "20260919T081735Z", "result": result})
    return path


class TestReadRuntimeWiring:
    def test_no_record_is_not_wired(self, tmp_path: Path) -> None:
        wired, reason, detail = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert reason == ""
        assert detail == {}

    def test_record_without_section_is_not_wired(self, tmp_path: Path) -> None:
        _record(tmp_path)
        wired, reason, _detail = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert reason == ""

    def test_wired_false_is_not_wired(self, tmp_path: Path) -> None:
        _record(tmp_path, runtime_execution={"wired": False})
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert reason == ""

    def test_wired_true_with_pass_evidence(self, tmp_path: Path) -> None:
        ev = _rehearsal(tmp_path / "rehearsal" / "rehearsal-1.json")
        _record(
            tmp_path,
            runtime_execution={
                "wired": True,
                "rehearsal_evidence": str(ev),
                "rehearsal_result": "P2_REHEARSAL_PASS",
            },
        )
        wired, reason, detail = _read_runtime_wiring(tmp_path)
        assert wired is True
        assert reason == ""
        assert detail["rehearsal_evidence"] == str(ev)
        assert detail["rehearsal_result"] == "P2_REHEARSAL_PASS"

    def test_wired_true_without_evidence_path_blocks(self, tmp_path: Path) -> None:
        _record(tmp_path, runtime_execution={"wired": True})
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert "rehearsal_evidence" in reason

    def test_wired_true_with_missing_evidence_blocks(self, tmp_path: Path) -> None:
        _record(
            tmp_path,
            runtime_execution={
                "wired": True,
                "rehearsal_evidence": str(tmp_path / "nope.json"),
            },
        )
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert "not_found" in reason or "missing" in reason

    def test_wired_true_with_failed_evidence_blocks(self, tmp_path: Path) -> None:
        ev = _rehearsal(tmp_path / "rehearsal.json", result="P2_REHEARSAL_EXIT4")
        _record(
            tmp_path,
            runtime_execution={"wired": True, "rehearsal_evidence": str(ev)},
        )
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert "PASS" in reason or "not_pass" in reason

    def test_wired_true_with_unreadable_evidence_blocks(self, tmp_path: Path) -> None:
        ev = tmp_path / "rehearsal.json"
        ev.write_text("{not json", encoding="utf-8")
        _record(
            tmp_path,
            runtime_execution={"wired": True, "rehearsal_evidence": str(ev)},
        )
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert "unreadable" in reason

    def test_wired_true_with_unreadable_record_blocks(self, tmp_path: Path) -> None:
        (tmp_path / "activation.json").write_text("{not json", encoding="utf-8")
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert reason

    def test_wired_mode_mismatch_blocks(self, tmp_path: Path) -> None:
        ev = _rehearsal(tmp_path / "rehearsal.json")
        _record(
            tmp_path,
            mode="MANUAL",
            runtime_execution={"wired": True, "rehearsal_evidence": str(ev)},
        )
        wired, reason, _ = _read_runtime_wiring(tmp_path)
        assert wired is False
        assert "mode" in reason
