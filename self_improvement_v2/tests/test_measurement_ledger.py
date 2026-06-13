"""Tests for SI v2 Measurement Ledger Builder.

Tests parsing cycle state artifacts, building Bot/FleetMeasurementPoint
records, proposal tracking, and edge cases.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from si_v2.measurement.ledger import _build_proposal_records, build_ledger
from si_v2.measurement.models import (
    BotMeasurementPoint,
)


def _make_state(
    cycle_id: str,
    fleet_verdict: str = "GREEN",
    total_bots: int = 4,
    ping_ok: int = 4,
    ping_fail: int = 0,
    sp_count: int = 0,
    np_count: int = 4,
    decisions: list[dict] | None = None,
) -> dict:
    """Create a synthetic cycle state dict."""
    if decisions is None:
        decisions = [
            {
                "bot_id": f"bot-{i+1}",
                "decision_type": "NO_PROPOSAL" if np_count > 0 else "SHADOW_PROPOSAL",
                "hypothesis": "no_action_insufficient_evidence_v1",
                "approval_status": "PENDING_HUMAN",
                "candidate_sha256": "",
                "evidence_summary": {
                    "ping": {"ok": True, "status_code": 200},
                    "status": {
                        "ok": True,
                        "auth_outcome": "AUTHENTICATED",
                        "open_trades": 0,
                    },
                    "signal_depth": 0.0,
                },
            }
            for i in range(total_bots)
        ]
    return {
        "cycle_id": cycle_id,
        "fleet_verdict": fleet_verdict,
        "total_bots": total_bots,
        "ping_ok_count": ping_ok,
        "ping_failed_count": ping_fail,
        "shadow_proposal_count": sp_count,
        "no_proposal_count": np_count,
        "runtime_mutations": 0,
        "config_mutations": 0,
        "live_trading_mutations": 0,
        "docker_mutations": 0,
        "strategy_mutations": 0,
        "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
        "schema_version": "cycle_state_v1",
        "per_bot_decisions": decisions,
    }


class TestBuildLedger:
    """Tests for the ledger builder with synthetic state files."""

    def test_empty_directory(self) -> None:
        """Empty dir returns empty ledger."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            ledger = build_ledger(state_dir=state_dir)
            assert ledger.cycle_count == 0
            assert len(ledger.bot_points) == 0

    def test_single_cycle_four_bots(self) -> None:
        """One cycle with 4 bots produces 4 bot points + 1 fleet point."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = _make_state("20260613T120000Z", sp_count=0, np_count=4)
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            assert ledger.cycle_count == 1
            assert len(ledger.bot_points) == 4
            assert len(ledger.fleet_points) == 1

    def test_chronological_order(self) -> None:
        """Multiple cycles are ordered by cycle_id (chronological)."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            for _i, cid in enumerate(
                ["20260613T100000Z", "20260613T110000Z", "20260613T120000Z"]
            ):
                data = _make_state(cid)
                (state_dir / f"active_cycle_{cid}.state.json").write_text(
                    json.dumps(data)
                )
            ledger = build_ledger(state_dir=state_dir)
            assert ledger.cycle_count == 3
            cids = [fp.cycle_id for fp in ledger.fleet_points]
            assert cids == sorted(cids)

    def test_missing_optional_metrics(self) -> None:
        """Missing optional fields produce None, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = _make_state("20260613T120000Z")
            # Remove optional keys
            data.pop("shadow_proposal_count", None)
            data.pop("no_proposal_count", None)
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            assert ledger.cycle_count >= 1

    def test_proposal_tracking(self) -> None:
        """SHADOW_PROPOSAL decisions create proposal records."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            dec_sha = "abc123def456"
            decisions = [
                {
                    "bot_id": "bot-1",
                    "decision_type": "SHADOW_PROPOSAL",
                    "hypothesis": "test_hypothesis",
                    "approval_status": "PENDING_HUMAN",
                    "candidate_sha256": dec_sha,
                    "evidence_summary": {
                        "ping": {"ok": True, "status_code": 200},
                        "status": {
                            "ok": True,
                            "auth_outcome": "AUTHENTICATED",
                            "open_trades": 1,
                        },
                        "signal_depth": 1.0,
                    },
                },
                {
                    "bot_id": "bot-2",
                    "decision_type": "NO_PROPOSAL",
                    "hypothesis": "",
                    "approval_status": "PENDING_HUMAN",
                    "candidate_sha256": "",
                    "evidence_summary": {
                        "ping": {"ok": True, "status_code": 200},
                        "status": {
                            "ok": True,
                            "auth_outcome": "AUTHENTICATED",
                            "open_trades": 0,
                        },
                        "signal_depth": 0.0,
                    },
                },
            ]
            data = _make_state(
                "20260613T120000Z",
                sp_count=1,
                np_count=1,
                decisions=decisions,
            )
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            assert len(ledger.proposal_records) == 1
            rec = ledger.proposal_records[0]
            assert rec.proposal_id == dec_sha
            assert rec.bot_id == "bot-1"
            assert rec.applied is False
            assert rec.attribution_status == "PENDING_APPLICATION"

    def test_no_proposals_baseline_only(self) -> None:
        """NO_PROPOSAL cycles get BASELINE_ONLY status."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = _make_state("20260613T120000Z", sp_count=0, np_count=4)
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            for bp in ledger.bot_points:
                assert bp.measurement_status == "BASELINE_ONLY"

    def test_mutations_zero(self) -> None:
        """Mutation counters remain zero in all points."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = _make_state("20260613T120000Z")
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            for bp in ledger.bot_points:
                assert bp.runtime_mutations == 0
                assert bp.config_mutations == 0
                assert bp.live_trading_mutations == 0
                assert bp.docker_mutations == 0
                assert bp.strategy_mutations == 0

    def test_secrets_not_present(self) -> None:
        """State files should not contain actual secrets."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = _make_state("20260613T120000Z")
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            text = json.dumps([bp.to_json_safe() for bp in ledger.bot_points])
            # No actual password values should appear
            assert "password" not in text.lower() or "SI_V2_" in text
            assert "access_token" not in text.lower()


class TestBuildProposalRecords:
    """Tests for the internal proposal record builder."""

    def test_no_proposals(self) -> None:
        records = _build_proposal_records([])
        assert records == []

    def test_single_proposal(self) -> None:

        points = [
            BotMeasurementPoint(
                cycle_id="c1",
                cycle_timestamp="2026-01-01",
                bot_id="bot-1",
                fleet_verdict="GREEN",
                decision_type="SHADOW_PROPOSAL",
                hypothesis="test",
                approval_status="PENDING_HUMAN",
                candidate_sha256="sha123",
                signal_depth=1.0,
                ping_ok=True,
                auth_ok=True,
                status_ok=True,
                open_trade_count=1,
                count_current=None,
                count_max=None,
                profit_all_percent=None,
                profit_all_ratio=None,
                daily_trade_count=None,
                whitelist_pair_count=None,
                runtime_mutations=0,
                config_mutations=0,
                live_trading_mutations=0,
                docker_mutations=0,
                strategy_mutations=0,
                controller_state="PAUSED / L3_REPOSITORY_ONLY",
                measurement_status="PENDING_APPLICATION",
                source_artifact="test.json",
            )
        ]
        records = _build_proposal_records(points)
        assert len(records) == 1
        assert records[0].proposal_id == "sha123"
        assert records[0].decision_count == 1
