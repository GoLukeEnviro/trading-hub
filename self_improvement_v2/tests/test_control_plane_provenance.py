"""Regression tests for the safety control-plane provenance collector.

Covers the read-only provenance recorded into the active-cycle evidence
bundle: canonical host kill-switch state, container projection and the
RiskGuard state — including the fail-closed paths for missing/corrupt state.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.loop.active_cycle_runner import (
    _collect_control_plane_provenance,
    _read_kill_switch_provenance,
)


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestKillSwitchProvenance:
    def test_normal_state_is_readable_and_inactive(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "kill_switch.json", {"mode": "NORMAL"})
        prov = _read_kill_switch_provenance(p)
        assert prov["readable"] is True
        assert prov["mode"] == "NORMAL"
        assert prov["active"] is False
        assert prov["fail_closed"] is False
        assert isinstance(prov["sha256"], str) and len(prov["sha256"]) == 64

    def test_v2_safety_state_field_is_used(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path / "kill_switch.json",
            {"version": 2, "safety_state": "HALT_NEW", "mode": "HALT_NEW"},
        )
        prov = _read_kill_switch_provenance(p)
        assert prov["mode"] == "HALT_NEW"
        assert prov["active"] is True

    def test_missing_state_is_fail_closed(self, tmp_path: Path) -> None:
        prov = _read_kill_switch_provenance(tmp_path / "missing.json")
        assert prov["readable"] is False
        assert prov["mode"] is None
        assert prov["fail_closed"] is True
        assert prov["active"] is True

    def test_corrupt_state_is_fail_closed(self, tmp_path: Path) -> None:
        p = tmp_path / "kill_switch.json"
        p.write_text("{not valid json", encoding="utf-8")
        prov = _read_kill_switch_provenance(p)
        assert prov["readable"] is False
        assert prov["mode"] is None
        assert prov["fail_closed"] is True


class TestCollectControlPlaneProvenance:
    def test_full_shape_with_normal_and_pass(self, tmp_path: Path) -> None:
        host = _write(tmp_path / "host.json", {"mode": "NORMAL"})
        projection = _write(tmp_path / "projection.json", {"mode": "NORMAL"})
        rg = _write(
            tmp_path / "riskguard_state.json",
            {"summary": {"status": "ACTIVE"}, "pairs": {"BTC/USDT": {"verdict": "ACCEPTED"}}},
        )
        prov = _collect_control_plane_provenance(
            kill_switch_path=host,
            kill_switch_projection_path=projection,
            riskguard_state_path=rg,
        )
        ks = prov["kill_switch"]
        assert ks["host"]["mode"] == "NORMAL"
        assert ks["container_projection"]["mode"] == "NORMAL"
        assert ks["consistent"] is True
        assert prov["riskguard"]["status"] == "PASS"
        assert prov["riskguard"]["fail_closed"] is False
        assert prov["riskguard"]["present"] is True

    def test_inconsistent_kill_switch_is_flagged(self, tmp_path: Path) -> None:
        host = _write(tmp_path / "host.json", {"mode": "HALT_NEW"})
        projection = _write(tmp_path / "projection.json", {"mode": "NORMAL"})
        prov = _collect_control_plane_provenance(
            kill_switch_path=host,
            kill_switch_projection_path=projection,
            riskguard_state_path=tmp_path / "missing_rg.json",
        )
        assert prov["kill_switch"]["consistent"] is False
        assert prov["kill_switch"]["host"]["active"] is True

    def test_missing_riskguard_is_fail_closed(self, tmp_path: Path) -> None:
        host = _write(tmp_path / "host.json", {"mode": "NORMAL"})
        projection = _write(tmp_path / "projection.json", {"mode": "NORMAL"})
        prov = _collect_control_plane_provenance(
            kill_switch_path=host,
            kill_switch_projection_path=projection,
            riskguard_state_path=tmp_path / "missing_rg.json",
        )
        assert prov["riskguard"]["status"] == "FAIL"
        assert prov["riskguard"]["fail_closed"] is True
        assert prov["riskguard"]["present"] is False
        assert prov["riskguard"]["sha256"] is None

    def test_corrupt_riskguard_is_fail_closed(self, tmp_path: Path) -> None:
        host = _write(tmp_path / "host.json", {"mode": "NORMAL"})
        projection = _write(tmp_path / "projection.json", {"mode": "NORMAL"})
        rg = tmp_path / "riskguard_state.json"
        rg.write_text("{bad json}", encoding="utf-8")
        prov = _collect_control_plane_provenance(
            kill_switch_path=host,
            kill_switch_projection_path=projection,
            riskguard_state_path=rg,
        )
        assert prov["riskguard"]["status"] == "FAIL"
        assert prov["riskguard"]["fail_closed"] is True

    def test_no_trigger_on_unreadable_kill_switches(self, tmp_path: Path) -> None:
        prov = _collect_control_plane_provenance(
            kill_switch_path=tmp_path / "missing_host.json",
            kill_switch_projection_path=tmp_path / "missing_proj.json",
            riskguard_state_path=tmp_path / "missing_rg.json",
        )
        assert prov["kill_switch"]["consistent"] is False
        assert prov["kill_switch"]["host"]["fail_closed"] is True
        assert prov["kill_switch"]["container_projection"]["fail_closed"] is True
