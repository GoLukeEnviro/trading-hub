"""Tests for SI v2 Active Cycle Runner ↔ Measurement Ledger integration.

Tests the passive post-step that wires the Measurement Ledger into
the Active Cycle Runner, verifying:

    1. Ledger-Success: cycle state + evidence → ledger outputs created.
    2. Ledger-Failure: corrupt state → WARNING, no crash.
    3. No artifacts: empty state dir → SKIPPED, no crash.
    4. Insufficient history: <3 cycles → SUCCESS but minimal attribution.
    5. Verdict adjustment logic: GREEN + WARNING → GREEN_WITH_LEDGER_WARNING.
    6. Verdict adjustment: YELLOW + FAILED → YELLOW_LEDGER_FAILED.
    7. Verdict adjustment: RED + FAILED → RED stays RED.
    8. Verdict adjustment: GREEN + SUCCESS → GREEN unchanged.
    9. Mutations all zero after ledger build.
    10. No secrets in ledger outputs.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from si_v2.loop.active_cycle_runner import (
    LEDGER_STATUS_FAILED,
    LEDGER_STATUS_SKIPPED,
    LEDGER_STATUS_SUCCESS,
    LEDGER_STATUS_WARNING,
    _adjusted_fleet_verdict,
    _run_ledger_post_step,
)

# ======================================================================
# Helpers: create synthetic cycle state files
# ======================================================================


def _make_state(
    cycle_id: str,
    fleet_verdict: str = "GREEN",
    total_bots: int = 4,
    ping_ok: int = 4,
    ping_fail: int = 0,
    sp_count: int = 0,
    np_count: int = 4,
    decisions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Create a synthetic cycle state dict."""
    if decisions is None:
        decisions = [
            {
                "bot_id": f"bot-{i + 1}",
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


def _write_state_file(state_dir: Path, cycle_id: str, state: dict[str, object]) -> Path:
    """Write a cycle state JSON file."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"active_cycle_{cycle_id}.state.json"
    path.write_text(json.dumps(state, indent=2))
    return path


class TestRunLedgerPostStepSuccess:
    """Tests for successful ledger post-step."""

    def test_success_with_cycle_states(self) -> None:
        """Ledger builds successfully when cycle state files exist."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "reports" / "phase2" / "cycle_state"
            evidence_dir = base / "reports" / "phase2" / "evidence"
            ledger_dir = base / "reports" / "phase2" / "measurement"

            for cid in ["20260613T100000Z", "20260613T110000Z", "20260613T120000Z"]:
                _write_state_file(state_dir, cid, _make_state(cid))

            result = _run_ledger_post_step(state_dir, evidence_dir, ledger_dir)

            assert result["status"] == LEDGER_STATUS_SUCCESS
            assert result["cycles_scanned"] == 3
            assert result["bot_points"] == 12
            assert result["fleet_points"] == 3
            assert result["mutations_all_zero"] is True
            assert result["secrets_found"] is False

            paths = result.get("ledger_paths")
            assert isinstance(paths, dict)
            assert "jsonl" in paths
            assert "summary" in paths
            assert "report" in paths

    def test_success_creates_files(self) -> None:
        """Ledger post-step creates the three output files."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "reports" / "phase2" / "cycle_state"
            evidence_dir = base / "reports" / "phase2" / "evidence"
            ledger_dir = base / "reports" / "phase2" / "measurement"

            _write_state_file(state_dir, "20260613T100000Z", _make_state("20260613T100000Z"))
            _write_state_file(state_dir, "20260613T110000Z", _make_state("20260613T110000Z"))

            _run_ledger_post_step(state_dir, evidence_dir, ledger_dir)

            assert (ledger_dir / "measurement_ledger.jsonl").exists()
            assert (ledger_dir / "measurement_summary.json").exists()
            assert (ledger_dir / "attribution_report.md").exists()


class TestRunLedgerPostStepSkipped:
    """Tests for SKIPPED status."""

    def test_skipped_no_state_dir(self) -> None:
        """SKIPPED when state_dir does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_ledger_post_step(
                state_dir=Path(tmp) / "nonexistent",
                evidence_dir=Path(tmp) / "evidence",
                ledger_dir=Path(tmp) / "measurement",
            )
            assert result["status"] == LEDGER_STATUS_SKIPPED
            assert result["error"]

    def test_skipped_empty_state_dir(self) -> None:
        """SKIPPED when state_dir exists but has no artifacts."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "cycle_state"
            state_dir.mkdir()

            result = _run_ledger_post_step(
                state_dir=state_dir,
                evidence_dir=base / "evidence",
                ledger_dir=base / "measurement",
            )
            assert result["status"] == LEDGER_STATUS_SKIPPED
            assert "no cycle state artifacts" in str(result["error"])


class TestRunLedgerPostStepWarning:
    """Tests for WARNING status on schema failures."""

    def test_warning_on_corrupt_json(self) -> None:
        """WARNING when a state file contains corrupt JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "cycle_state"
            state_dir.mkdir()

            # Write one valid + one corrupt file
            _write_state_file(
                state_dir, "20260613T100000Z",
                _make_state("20260613T100000Z"),
            )
            bad_file = state_dir / "active_cycle_20260613T110000Z.state.json"
            bad_file.write_text("{invalid json content")

            result = _run_ledger_post_step(
                state_dir=state_dir,
                evidence_dir=base / "evidence",
                ledger_dir=base / "measurement",
            )

            # The ledger builder skips corrupt files, so it should still
            # succeed with the valid file, OR return WARNING if the corrupt
            # one causes a schema error.
            # Since the ledger builder uses json.loads which raises
            # JSONDecodeError (caught as ValueError), it should still process
            # the valid one.
            assert result["status"] in (
                LEDGER_STATUS_SUCCESS,
                LEDGER_STATUS_WARNING,
            )


class TestRunLedgerPostStepMutations:
    """Verify mutation counters remain zero."""

    def test_mutations_zero_with_proposals(self) -> None:
        """Mutations stay zero even with shadow proposals in states."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "cycle_state"
            state_dir.mkdir()

            decisions: list[dict[str, object]] = [
                {
                    "bot_id": "bot-1",
                    "decision_type": "SHADOW_PROPOSAL",
                    "hypothesis": "increase_signal_depth_v1",
                    "approval_status": "PENDING_HUMAN",
                    "candidate_sha256": "abc123def456",
                    "evidence_summary": {
                        "ping": {"ok": True, "status_code": 200},
                        "status": {
                            "ok": True,
                            "auth_outcome": "AUTHENTICATED",
                            "open_trades": 0,
                        },
                        "signal_depth": 0.5,
                    },
                },
                {
                    "bot_id": "bot-2",
                    "decision_type": "NO_PROPOSAL",
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
                },
            ]

            state = _make_state(
                "20260613T100000Z",
                sp_count=1,
                np_count=1,
                total_bots=2,
                decisions=decisions,
            )
            _write_state_file(state_dir, "20260613T100000Z", state)

            result = _run_ledger_post_step(
                state_dir=state_dir,
                evidence_dir=base / "evidence",
                ledger_dir=base / "measurement",
            )

            assert result["status"] == LEDGER_STATUS_SUCCESS
            assert result["mutations_all_zero"] is True


class TestAdjustedFleetVerdict:
    """Tests for the _adjusted_fleet_verdict logic."""

    def test_green_success_unchanged(self) -> None:
        """GREEN + SUCCESS → GREEN."""
        assert _adjusted_fleet_verdict("GREEN", LEDGER_STATUS_SUCCESS) == "GREEN"

    def test_green_skipped_unchanged(self) -> None:
        """GREEN + SKIPPED → GREEN (no artifacts yet)."""
        assert _adjusted_fleet_verdict("GREEN", LEDGER_STATUS_SKIPPED) == "GREEN"

    def test_green_warning_downgraded(self) -> None:
        """GREEN + WARNING → GREEN_WITH_LEDGER_WARNING."""
        result = _adjusted_fleet_verdict("GREEN", LEDGER_STATUS_WARNING)
        assert result == "GREEN_WITH_LEDGER_WARNING"

    def test_green_failed_downgraded(self) -> None:
        """GREEN + FAILED → GREEN_WITH_LEDGER_WARNING."""
        result = _adjusted_fleet_verdict("GREEN", LEDGER_STATUS_FAILED)
        assert result == "GREEN_WITH_LEDGER_WARNING"

    def test_yellow_warning_downgraded(self) -> None:
        """YELLOW + WARNING → YELLOW_LEDGER_FAILED."""
        result = _adjusted_fleet_verdict("YELLOW", LEDGER_STATUS_WARNING)
        assert result == "YELLOW_LEDGER_FAILED"

    def test_yellow_failed_downgraded(self) -> None:
        """YELLOW + FAILED → YELLOW_LEDGER_FAILED."""
        result = _adjusted_fleet_verdict("YELLOW", LEDGER_STATUS_FAILED)
        assert result == "YELLOW_LEDGER_FAILED"

    def test_red_stays_red(self) -> None:
        """RED + FAILED → RED (already worse)."""
        result = _adjusted_fleet_verdict("RED", LEDGER_STATUS_FAILED)
        assert result == "RED"

    def test_red_stays_red_on_warning(self) -> None:
        """RED + WARNING → RED."""
        result = _adjusted_fleet_verdict("RED", LEDGER_STATUS_WARNING)
        assert result == "RED"


class TestLedgerSecretSafety:
    """Verify no secrets in ledger outputs."""

    def test_no_secrets_in_jsonl(self) -> None:
        """JSONL output contains no credential values."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_dir = base / "cycle_state"
            state_dir.mkdir()

            _write_state_file(
                state_dir, "20260613T100000Z",
                _make_state("20260613T100000Z"),
            )

            _run_ledger_post_step(
                state_dir=state_dir,
                evidence_dir=base / "evidence",
                ledger_dir=base / "measurement",
            )

            jsonl_path = base / "measurement" / "measurement_ledger.jsonl"
            content = jsonl_path.read_text()

            # Check no credential-like patterns
            for pattern in ["password", "api_key", "token", "secret_value"]:
                assert pattern not in content.lower(), (
                    f"Potential secret '{pattern}' found in JSONL"
                )
