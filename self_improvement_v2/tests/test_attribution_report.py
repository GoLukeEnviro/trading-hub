"""Tests for SI v2 Attribution Report renderer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from si_v2.measurement.ledger import _build_summary, build_ledger, persist_ledger
from si_v2.measurement.models import MeasurementLedger
from si_v2.measurement.report import render_attribution_report


def _make_empty_ledger() -> MeasurementLedger:
    return MeasurementLedger(
        build_timestamp="2026-01-01T00:00:00",
        cycle_count=0,
        bot_count=0,
        bot_points=(),
        fleet_points=(),
        proposal_records=(),
        attribution_windows=(),
        source_artifacts=(),
    )


class TestRenderEmpty:
    def test_empty_ledger(self) -> None:
        ledger = _make_empty_ledger()
        from si_v2.measurement.ledger import _build_summary
        summary = _build_summary(ledger)
        report = render_attribution_report(ledger, summary)
        assert "No cycle artifacts found" in report
        assert "Measurement Ledger" in report

    def test_empty_has_expected_sections(self) -> None:
        ledger = _make_empty_ledger()
        summary = _build_summary(ledger)
        report = render_attribution_report(ledger, summary)
        for section in [
            "Executive Verdict",
            "Input Artifacts",
            "Secret-Safety",
            "Next Recommended",
        ]:
            assert section in report, f"Expected section '{section}' in report"


class TestRenderWithData:
    def test_with_one_state(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "cycle_state"
            state_dir.mkdir()
            data = {
                "cycle_id": "20260613T120000Z",
                "fleet_verdict": "GREEN",
                "total_bots": 4,
                "ping_ok_count": 4,
                "ping_failed_count": 0,
                "shadow_proposal_count": 0,
                "no_proposal_count": 4,
                "runtime_mutations": 0,
                "config_mutations": 0,
                "live_trading_mutations": 0,
                "docker_mutations": 0,
                "strategy_mutations": 0,
                "controller_state": "PAUSED / L3_REPOSITORY_ONLY",
                "schema_version": "cycle_state_v1",
                "per_bot_decisions": [
                    {
                        "bot_id": f"bot-{i+1}",
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
                    }
                    for i in range(4)
                ],
            }
            (state_dir / "active_cycle_20260613T120000Z.state.json").write_text(
                json.dumps(data)
            )
            ledger = build_ledger(state_dir=state_dir)
            summary = _build_summary(ledger)
            report = render_attribution_report(ledger, summary)
            assert "GREEN" in report
            assert "bot-1" in report or "bot" in report.lower()
            assert "INSUFFICIENT" in report or "PENDING" in report

    def test_report_contains_secret_statement(self) -> None:
        """The report always contains a secret-safety statement."""
        ledger = _make_empty_ledger()
        summary = _build_summary(ledger)
        report = render_attribution_report(ledger, summary)
        assert "Secret-Safety" in report
        assert "secrets" in report.lower()


class TestPersistLedger:
    def test_persist_empty_produces_files(self) -> None:
        ledger = _make_empty_ledger()
        with tempfile.TemporaryDirectory() as tmp:
            paths = persist_ledger(ledger, ledger_dir=Path(tmp))
            assert "jsonl" in paths
            assert paths["jsonl"].exists()
            assert paths["summary"].exists()
            assert paths["summary"].stat().st_size > 0
            assert paths["report"].exists()
            assert paths["report"].stat().st_size > 0
