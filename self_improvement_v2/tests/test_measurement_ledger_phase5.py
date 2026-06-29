"""Tests for measurement/ledger.py — persistence, helpers, edge cases.

Tests cover:
- _safe_float, _safe_int, _cycle_timestamp_from_id, _check_secrets_in_text
- _empty_ledger
- persist_ledger (JSONL write, summary, report)
- _build_summary
- build_ledger edge cases (corrupted state, evidence dir, missing fields)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.measurement.ledger import (
    _build_summary,
    _check_secrets_in_text,
    _cycle_timestamp_from_id,
    _empty_ledger,
    _safe_float,
    _safe_int,
    build_ledger,
    persist_ledger,
)
from si_v2.measurement.models import (
    BotMeasurementPoint,
    FleetMeasurementPoint,
    MeasurementLedger,
)

# ======================================================================
# Pure helpers
# ======================================================================

class TestSafeFloat:
    def test_float_input(self) -> None:
        assert _safe_float(3.14) == 3.14

    def test_int_input(self) -> None:
        assert _safe_float(42) == 42.0

    def test_none_input(self) -> None:
        assert _safe_float(None) is None

    def test_string_input(self) -> None:
        assert _safe_float("3.14") is None  # not a number type

    def test_custom_default(self) -> None:
        assert _safe_float(None, default=0.0) == 0.0


class TestSafeInt:
    def test_int_input(self) -> None:
        assert _safe_int(42) == 42

    def test_float_input(self) -> None:
        assert _safe_int(3.14) == 3

    def test_none_input(self) -> None:
        assert _safe_int(None) is None

    def test_string_input(self) -> None:
        assert _safe_int("42") is None

    def test_custom_default(self) -> None:
        assert _safe_int(None, default=0) == 0


class TestCycleTimestampFromId:
    def test_valid_cycle_id(self) -> None:
        result = _cycle_timestamp_from_id("20260613T120000Z")
        assert "2026-06-13" in result
        assert "12:00:00" in result

    def test_invalid_cycle_id(self) -> None:
        """Invalid format should return the input unchanged."""
        result = _cycle_timestamp_from_id("not-a-cycle-id")
        assert result == "not-a-cycle-id"

    def test_empty_string(self) -> None:
        result = _cycle_timestamp_from_id("")
        assert result == ""


class TestCheckSecretsInText:
    def test_always_false(self) -> None:
        """Currently always returns False."""
        assert _check_secrets_in_text("any text") is False
        assert _check_secrets_in_text("") is False
        assert _check_secrets_in_text("SI_V2_PASS" + "WORD=secret") is False


class TestEmptyLedger:
    def test_empty_ledger_structure(self) -> None:
        ledger = _empty_ledger()
        assert ledger.cycle_count == 0
        assert ledger.bot_count == 0
        assert len(ledger.bot_points) == 0
        assert len(ledger.fleet_points) == 0
        assert len(ledger.proposal_records) == 0
        assert len(ledger.attribution_windows) == 0
        assert len(ledger.source_artifacts) == 0
        assert ledger.build_timestamp is not None


# ======================================================================
# persist_ledger
# ======================================================================

class TestPersistLedger:
    def _make_ledger(self) -> MeasurementLedger:
        """Create a minimal ledger with one bot and one fleet point."""
        bp = BotMeasurementPoint(
            cycle_id="c1", cycle_timestamp="2026-06-13T12:00:00",
            bot_id="freqforge", fleet_verdict="GREEN",
            decision_type="NO_PROPOSAL", hypothesis="", approval_status="PENDING_HUMAN",
            candidate_sha256="", signal_depth=0.0, ping_ok=True, auth_ok=True,
            status_ok=True, open_trade_count=0, count_current=None, count_max=None,
            profit_all_percent=None, profit_all_ratio=None, daily_trade_count=None,
            whitelist_pair_count=None, runtime_mutations=0, config_mutations=0,
            live_trading_mutations=0, docker_mutations=0, strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY", source_artifact="test.json",
        )
        fp = FleetMeasurementPoint(
            cycle_id="c1", cycle_timestamp="2026-06-13T12:00:00",
            fleet_verdict="GREEN", total_bots=4, ping_ok_count=4, ping_failed_count=0,
            shadow_proposal_count=0, no_proposal_count=4, mean_signal_depth=0.0,
            mean_profit_all_percent=None, total_open_trades=None,
            runtime_mutations=0, config_mutations=0, live_trading_mutations=0,
            docker_mutations=0, strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY", source_artifact="test.json",
        )
        return MeasurementLedger(
            build_timestamp="2026-06-29T12:00:00",
            cycle_count=1, bot_count=4,
            bot_points=(bp,), fleet_points=(fp,),
            proposal_records=(), attribution_windows=(),
            source_artifacts=("test.json",),
        )

    def test_persist_jsonl(self, tmp_path: Path) -> None:
        """JSONL file should be created with bot and fleet points."""
        ledger = self._make_ledger()
        paths = persist_ledger(ledger, ledger_dir=tmp_path)
        assert "jsonl" in paths
        jsonl_path = paths["jsonl"]
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 2  # 1 bot + 1 fleet
        # Each line should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert isinstance(data, dict)

    def test_persist_summary(self, tmp_path: Path) -> None:
        """Summary JSON should be created."""
        ledger = self._make_ledger()
        paths = persist_ledger(ledger, ledger_dir=tmp_path)
        assert "summary" in paths
        summary_path = paths["summary"]
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        assert data["total_cycles_scanned"] == 1
        assert data["total_bot_points"] == 1

    def test_persist_report(self, tmp_path: Path) -> None:
        """Markdown report should be created."""
        ledger = self._make_ledger()
        paths = persist_ledger(ledger, ledger_dir=tmp_path)
        assert "report" in paths
        report_path = paths["report"]
        assert report_path.exists()
        text = report_path.read_text()
        assert len(text) > 0

    def test_persist_empty_ledger(self, tmp_path: Path) -> None:
        """Empty ledger should still produce files."""
        ledger = _empty_ledger()
        paths = persist_ledger(ledger, ledger_dir=tmp_path)
        assert "jsonl" in paths
        jsonl_path = paths["jsonl"]
        assert jsonl_path.exists()
        # Empty ledger = no bot/fleet points = empty JSONL
        content = jsonl_path.read_text().strip()
        assert content == "" or content == ""

    def test_persist_creates_dir(self, tmp_path: Path) -> None:
        """persist_ledger should create the directory if it doesn't exist."""
        ledger = self._make_ledger()
        nested = tmp_path / "a" / "b" / "c"
        paths = persist_ledger(ledger, ledger_dir=nested)
        assert nested.exists()
        assert paths["jsonl"].exists()

    def test_persist_fleet_type_marker(self, tmp_path: Path) -> None:
        """Fleet points should have _type='fleet' marker in JSONL."""
        ledger = self._make_ledger()
        paths = persist_ledger(ledger, ledger_dir=tmp_path)
        lines = paths["jsonl"].read_text().strip().split("\n")
        fleet_lines = [line for line in lines if json.loads(line).get("_type") == "fleet"]
        assert len(fleet_lines) == 1


# ======================================================================
# _build_summary
# ======================================================================

class TestBuildSummary:
    def test_empty_ledger(self) -> None:
        summary = _build_summary(_empty_ledger())
        assert summary.total_cycles_scanned == 0
        assert summary.total_bot_points == 0
        assert summary.insufficient_history is True

    def test_with_data(self) -> None:
        bp = BotMeasurementPoint(
            cycle_id="c1", cycle_timestamp="2026-06-13T12:00:00",
            bot_id="freqforge", fleet_verdict="GREEN",
            decision_type="NO_PROPOSAL", hypothesis="", approval_status="PENDING_HUMAN",
            candidate_sha256="", signal_depth=0.0, ping_ok=True, auth_ok=True,
            status_ok=True, open_trade_count=0, count_current=None, count_max=None,
            profit_all_percent=None, profit_all_ratio=None, daily_trade_count=None,
            whitelist_pair_count=None, runtime_mutations=0, config_mutations=0,
            live_trading_mutations=0, docker_mutations=0, strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY", source_artifact="test.json",
        )
        fp = FleetMeasurementPoint(
            cycle_id="c1", cycle_timestamp="2026-06-13T12:00:00",
            fleet_verdict="GREEN", total_bots=4, ping_ok_count=4, ping_failed_count=0,
            shadow_proposal_count=0, no_proposal_count=4, mean_signal_depth=0.0,
            mean_profit_all_percent=None, total_open_trades=None,
            runtime_mutations=0, config_mutations=0, live_trading_mutations=0,
            docker_mutations=0, strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY", source_artifact="test.json",
        )
        ledger = MeasurementLedger(
            build_timestamp="2026-06-29T12:00:00",
            cycle_count=1, bot_count=4,
            bot_points=(bp,), fleet_points=(fp,),
            proposal_records=(), attribution_windows=(),
            source_artifacts=("test.json",),
        )
        summary = _build_summary(ledger)
        assert summary.total_cycles_scanned == 1
        assert summary.total_bot_points == 1
        assert summary.total_fleet_points == 1
        assert summary.mutations_all_zero is True
        assert summary.secrets_found is False
        assert summary.insufficient_history is True  # < 3 cycles


# ======================================================================
# build_ledger edge cases
# ======================================================================

class TestBuildLedgerEdgeCases:
    def test_corrupted_state_file(self, tmp_path: Path) -> None:
        """Corrupted JSON should be skipped, not crash."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        (state_dir / "active_cycle_bad.state.json").write_text("{invalid json}")
        ledger = build_ledger(state_dir=state_dir)
        assert ledger.cycle_count == 0

    def test_state_without_cycle_id(self, tmp_path: Path) -> None:
        """State without cycle_id should be skipped."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        (state_dir / "active_cycle_no_id.state.json").write_text(
            json.dumps({"fleet_verdict": "GREEN"})
        )
        ledger = build_ledger(state_dir=state_dir)
        assert ledger.cycle_count == 0

    def test_with_evidence_dir(self, tmp_path: Path) -> None:
        """Evidence directory should be read without crashing."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        # Write a valid state file
        state = {
            "cycle_id": "20260613T120000Z",
            "fleet_verdict": "GREEN",
            "total_bots": 4,
            "ping_ok_count": 4, "ping_failed_count": 0,
            "shadow_proposal_count": 0, "no_proposal_count": 4,
            "runtime_mutations": 0, "config_mutations": 0,
            "live_trading_mutations": 0, "docker_mutations": 0,
            "strategy_mutations": 0,
            "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
            "schema_version": "cycle_state_v1",
            "per_bot_decisions": [
                {
                    "bot_id": "bot-1",
                    "decision_type": "NO_PROPOSAL",
                    "hypothesis": "no_action_insufficient_evidence_v1",
                    "approval_status": "PENDING_HUMAN",
                    "candidate_sha256": "",
                    "evidence_summary": {
                        "ping": {"ok": True, "status_code": 200},
                        "status": {"ok": True, "auth_outcome": "AUTHENTICATED", "open_trades": 0},
                        "signal_depth": 0.0,
                    },
                }
                for i in range(4)
            ],
        }
        (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(json.dumps(state))
        # Write a valid evidence file
        (evidence_dir / "active_cycle_20260613T120000Z.json").write_text(
            json.dumps({"cycle_id": "20260613T120000Z", "extra": "data"})
        )
        ledger = build_ledger(state_dir=state_dir, evidence_dir=evidence_dir)
        assert ledger.cycle_count == 1
        assert len(ledger.bot_points) == 4

    def test_corrupted_evidence_file(self, tmp_path: Path) -> None:
        """Corrupted evidence file should not crash the builder."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        state = {
            "cycle_id": "20260613T120000Z",
            "fleet_verdict": "GREEN",
            "total_bots": 4,
            "ping_ok_count": 4, "ping_failed_count": 0,
            "shadow_proposal_count": 0, "no_proposal_count": 4,
            "runtime_mutations": 0, "config_mutations": 0,
            "live_trading_mutations": 0, "docker_mutations": 0,
            "strategy_mutations": 0,
            "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
            "schema_version": "cycle_state_v1",
            "per_bot_decisions": [
                {
                    "bot_id": f"bot-{i+1}",
                    "decision_type": "NO_PROPOSAL",
                    "hypothesis": "no_action_insufficient_evidence_v1",
                    "approval_status": "PENDING_HUMAN",
                    "candidate_sha256": "",
                    "evidence_summary": {
                        "ping": {"ok": True, "status_code": 200},
                        "status": {"ok": True, "auth_outcome": "AUTHENTICATED", "open_trades": 0},
                        "signal_depth": 0.0,
                    },
                }
                for i in range(4)
            ],
        }
        (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(json.dumps(state))
        (evidence_dir / "active_cycle_bad.json").write_text("{invalid}")
        ledger = build_ledger(state_dir=state_dir, evidence_dir=evidence_dir)
        assert ledger.cycle_count == 1  # State file still processed

    def test_missing_state_dir(self) -> None:
        """Missing state dir should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            build_ledger(state_dir=Path("/nonexistent"))

    def test_rainbow_scoring_eligible(self, tmp_path: Path) -> None:
        """Rainbow scoring eligibility should be computed correctly."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        state = {
            "cycle_id": "20260613T120000Z",
            "fleet_verdict": "GREEN",
            "total_bots": 4,
            "ping_ok_count": 4, "ping_failed_count": 0,
            "shadow_proposal_count": 0, "no_proposal_count": 4,
            "runtime_mutations": 0, "config_mutations": 0,
            "live_trading_mutations": 0, "docker_mutations": 0,
            "strategy_mutations": 0,
            "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
            "schema_version": "cycle_state_v1",
            "per_bot_decisions": [],
            "external_signals": {
                "rainbow": {
                    "status": "SUCCESS",
                    "count": 5,
                    "symbols": ["BTC/USDT:USDT"],
                    "directions": ["long"],
                    "confidence_min": 0.65,
                    "confidence_max": 0.92,
                    "confidence_avg": 0.78,
                    "errors": [],
                    "source": "read_only",
                    "fresh": True,
                    "freshness_seconds": 30,
                    "freshness_max_seconds": 900,
                    "fresh_signal_count": 5,
                    "stale_signal_count": 0,
                    "future_signal_count": 0,
                    "invalid_timestamp_count": 0,
                    "batch_freshness_status": "FRESH",
                }
            },
        }
        (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(json.dumps(state))
        ledger = build_ledger(state_dir=state_dir)
        assert len(ledger.fleet_points) == 1
        fp = ledger.fleet_points[0]
        assert fp.rainbow_scoring_eligible is True
        assert fp.rainbow_fresh is True
        assert fp.rainbow_freshness_seconds == 30
        assert fp.rainbow_batch_freshness_status == "FRESH"

    def test_rainbow_scoring_not_eligible_fixture(self, tmp_path: Path) -> None:
        """Fixture source should not be scoring eligible."""
        state_dir = tmp_path / "cycle_state"
        state_dir.mkdir()
        state = {
            "cycle_id": "20260613T120000Z",
            "fleet_verdict": "GREEN",
            "total_bots": 4,
            "ping_ok_count": 4, "ping_failed_count": 0,
            "shadow_proposal_count": 0, "no_proposal_count": 4,
            "runtime_mutations": 0, "config_mutations": 0,
            "live_trading_mutations": 0, "docker_mutations": 0,
            "strategy_mutations": 0,
            "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
            "schema_version": "cycle_state_v1",
            "per_bot_decisions": [],
            "external_signals": {
                "rainbow": {
                    "status": "SUCCESS",
                    "count": 5,
                    "source": "fixture",
                    "fresh": False,
                }
            },
        }
        (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(json.dumps(state))
        ledger = build_ledger(state_dir=state_dir)
        fp = ledger.fleet_points[0]
        assert fp.rainbow_scoring_eligible is False
