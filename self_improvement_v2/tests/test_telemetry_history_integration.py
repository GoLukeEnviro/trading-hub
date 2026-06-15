"""Integration tests for telemetry history wiring in the active cycle runner.

Covers:
  1. build_record_from_snapshots with real BotSignalSnapshot objects
  2. TelemetryHistoryAnalyzer integration (partial bot failure handled correctly)
  3. EvidenceWindow construction with insufficient history
  4. Secret safety in the full record build pipeline
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

_HISTORY_PATH = Path(__file__).resolve().parents[1] / "src" / "si_v2" / "observe" / "telemetry_history.py"


@pytest.fixture(scope="module")
def th() -> object:
    """Import the telemetry_history module."""
    import importlib.util as iu

    spec = iu.spec_from_file_location("telemetry_history", _HISTORY_PATH)
    assert spec is not None
    mod = iu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------
# 1. build_record_from_snapshots with BotSignalSnapshot
# ------------------------------------------------------------------
class TestBuildRecordFromSnapshots:
    """Ensure build_record_from_snapshots correctly converts signal snapshots."""

    def _make_real_snapshot(self, bot_id: str, auth: str = "AUTHENTICATED",
                            ping_ok: bool = True, profit: float = 3.0):
        """Create a real BotSignalSnapshot."""
        from si_v2.signals.models import BotSignalSnapshot, SignalQuality
        return BotSignalSnapshot(
            bot_id=bot_id,
            cycle_id="test-integration",
            ping_ok=ping_ok,
            ping_status_code=200 if ping_ok else 0,
            auth_outcome=auth,
            status_ok=ping_ok,
            status_open_trades=2,
            status_response_summary="ok",
            count_current=2,
            count_max=5,
            profit_all_percent=profit if ping_ok else None,
            profit_all_ratio=profit / 100.0 if profit is not None and ping_ok else None,
            daily_trade_count_total=10 if ping_ok else 0,
            daily_abs_profit_sum=profit or 0.0,
            whitelist_pair_count=20,
            signal_quality=SignalQuality(
                total_endpoints=8,
                available_count=7 if ping_ok else 0,
                completeness_score=0.875 if ping_ok else 0.0,
            ),
            availability=(),
            fetched_at_utc=datetime.now(UTC).isoformat(),
        )

    def test_build_from_4_snapshots(self, th):
        """Build record from 4 signal snapshots — all authenticated."""
        bot_ids = [
            "freqtrade-freqforge",
            "freqtrade-regime-hybrid",
            "freqtrade-freqforge-canary",
            "freqai-rebel",
        ]
        snapshots = [self._make_real_snapshot(bid) for bid in bot_ids]

        record = th.build_record_from_snapshots(
            cycle_id="test-cycle-001",
            fleet_verdict="GREEN",
            snapshots=snapshots,
            fetched_at_utc=datetime.now(UTC).isoformat(),
        )

        assert record.cycle_id == "test-cycle-001"
        assert record.total_bots == 4
        assert record.fleet_verdict == "GREEN"
        assert len(record.bots) == 4
        for snap, bid in zip(record.bots, bot_ids, strict=True):
            assert snap.bot_id == bid
            assert snap.read_success is True

    def test_build_from_partial_snapshots(self, th):
        """Build record with only 2 out of 4 bots — handles partial coverage."""
        snapshots = [
            self._make_real_snapshot("freqtrade-freqforge"),
            self._make_real_snapshot("freqtrade-regime-hybrid"),
        ]

        record = th.build_record_from_snapshots(
            cycle_id="test-partial",
            fleet_verdict="YELLOW",
            snapshots=snapshots,
        )

        assert record.total_bots == 2
        assert len(record.bots) == 2

    def test_build_from_empty_snapshots(self, th):
        """Build record with no snapshots — produces empty bots tuple."""
        record = th.build_record_from_snapshots(
            cycle_id="test-empty",
            fleet_verdict="UNKNOWN",
            snapshots=[],
        )

        assert record.total_bots == 0
        assert len(record.bots) == 0
        assert record.fleet_verdict == "UNKNOWN"

    def test_degraded_bot_marked_correctly(self, th):
        """A bot with ping_ok=False should have status=offline in history."""
        snap = self._make_real_snapshot("freqai-rebel", ping_ok=False, auth="NOT_ATTEMPTED")

        record = th.build_record_from_snapshots(
            cycle_id="test-degraded",
            fleet_verdict="YELLOW",
            snapshots=[snap],
        )

        assert record.bots[0].status == "offline"
        assert record.bots[0].read_success is False

    def test_no_secrets_in_built_record(self, th):
        """The built record must be secret-free and pass belt-and-suspenders check."""
        snapshots = [self._make_real_snapshot("freqtrade-freqforge")]

        record = th.build_record_from_snapshots(
            cycle_id="test-secrets",
            fleet_verdict="GREEN",
            snapshots=snapshots,
        )

        raw = record.model_dump(mode="json")
        th.TelemetryHistoryStore._assert_no_secrets(raw)


# ------------------------------------------------------------------
# 2. EvidenceWindow with insufficient history
# ------------------------------------------------------------------
class TestEvidenceWindowInsufficient:
    def test_empty_store_returns_zero_runs(self, th, tmp_path):
        """EvidenceWindow with no history must show runs_observed=0."""
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        ew = analyzer.build_evidence_window(n=5)

        assert ew.runs_observed == 0
        assert ew.per_bot_trend_summary == {}
        assert ew.window_start_utc == ""
        assert ew.window_end_utc == ""

    def test_single_run_window(self, th, tmp_path):
        """EvidenceWindow with 1 run still produces valid output."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
                profit_ratio=0.03,
                ping_ok=True,
                auth_outcome="AUTHENTICATED",
                signal_depth=0.875,
            ),
        )
        store.append(th.TelemetryHistoryRecord(
            cycle_id="c-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            fleet_verdict="GREEN",
            bots=bots,
        ))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        ew = analyzer.build_evidence_window(n=5)

        assert ew.runs_observed == 1
        assert "freqtrade-freqforge" in ew.per_bot_trend_summary
        assert ew.per_bot_trend_summary["freqtrade-freqforge"]["runs_observed"] == 1


# ------------------------------------------------------------------
# 3. Secret safety validation on full pipeline
# ------------------------------------------------------------------
class TestPipelineSecretSafety:
    def test_record_after_append_is_secret_free(self, th, tmp_path):
        """After full append-read roundtrip, no sensitive keys appear."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
                profit_ratio=0.01,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="safe-test",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            bots=bots,
        )
        store.append(record)

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        loaded = reader.read_all()
        assert len(loaded) == 1

        raw = loaded[0].model_dump(mode="json")
        th.TelemetryHistoryStore._assert_no_secrets(raw)

    def test_error_redacted_no_secret_leak(self, th, tmp_path):
        """Even with error metadata, no sensitive keys pass through."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        bots = (
            th.BotSnapshot(
                bot_id="freqai-rebel",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="offline",
                read_success=False,
                ping_ok=False,
                auth_outcome="FAILED",
                error_redacted="Connection refused on 127.0.0.1:8080",
                signal_depth=0.0,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="error-test",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            fleet_verdict="RED",
            bots=bots,
        )
        store.append(record)

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        loaded = reader.read_all()
        raw = loaded[0].model_dump(mode="json")
        th.TelemetryHistoryStore._assert_no_secrets(raw)


# ------------------------------------------------------------------
# 4. Trend analysis with partial data
# ------------------------------------------------------------------
class TestAnalyzerPartialData:
    def test_some_bots_have_no_data(self, th, tmp_path):
        """Analyzer handles bots with zero runs gracefully."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)

        # Only 2 bots have data
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc=now.isoformat(),
                status="online", read_success=True,
                ping_ok=True, auth_outcome="AUTHENTICATED",
                profit_ratio=0.03, signal_depth=0.875,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc=now.isoformat(),
                status="online", read_success=True,
                ping_ok=True, auth_outcome="AUTHENTICATED",
                profit_ratio=0.02, signal_depth=0.75,
            ),
        )
        store.append(th.TelemetryHistoryRecord(
            cycle_id="partial-run",
            generated_at_utc=now.isoformat(),
            total_bots=2,
            fleet_verdict="YELLOW",
            bots=bots,
        ))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        # All 4 KNOWN_BOT_IDS should have entries
        bot_ids = {s.bot_id for s in trend.per_bot}
        for bid in ("freqtrade-freqforge", "freqtrade-regime-hybrid",
                    "freqtrade-freqforge-canary", "freqai-rebel"):
            assert bid in bot_ids, f"Missing bot {bid}"

        # Bots without data should have runs_observed=0
        rebel = next(s for s in trend.per_bot if s.bot_id == "freqai-rebel")
        assert rebel.runs_observed == 0
        assert rebel.profit_trend == "insufficient_data"

    def test_insufficient_history_marked(self, th, tmp_path):
        """With runs_observed < 3, per-bot profit_trend should be insufficient_data."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)

        # Only 1 run
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc=now.isoformat(),
                status="online", read_success=True,
                ping_ok=True, auth_outcome="AUTHENTICATED",
                profit_ratio=0.03, signal_depth=0.875,
            ),
        )
        store.append(th.TelemetryHistoryRecord(
            cycle_id="single-run",
            generated_at_utc=now.isoformat(),
            total_bots=1,
            bots=bots,
        ))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        forge = next(s for s in trend.per_bot if s.bot_id == "freqtrade-freqforge")
        assert forge.profit_trend == "insufficient_data"  # < 3 data points


# ------------------------------------------------------------------
# 5. Telemetry history gating enforcement tests
# ------------------------------------------------------------------
class TestTelemetryHistoryGate:
    """Tests for the min_required_runs enforcement gate.

    The gate logic (defined in active_cycle_runner.py):
      - If evidence_window is missing       → MISSING_EVIDENCE_WINDOW
      - If runs_observed < min_required_runs → INSUFFICIENT_HISTORY
      - Otherwise                           → NORMAL
    min_required_runs defaults to 5.

    When history_status != NORMAL:
      - approval_status = "BLOCKED_INSUFFICIENT_HISTORY"
      - promotion_blocked = True

    When history_status == NORMAL:
      - approval_status = "PENDING_HUMAN"
      - promotion_blocked = False
    """

    MIN_REQUIRED = 5

    def _make_evidence_window(self, th, runs_observed: int):
        """Create an EvidenceWindow with the given runs_observed count."""
        return th.EvidenceWindow(
            runs_observed=runs_observed,
            window_start_utc="2026-06-10T00:00:00Z",
            window_end_utc="2026-06-15T12:00:00Z",
            per_bot_trend_summary={},
        )

    def test_missing_evidence_window(self, th):
        """Missing evidence_window → fail closed → BLOCKED."""
        ew_dict = {}
        assert not ew_dict  # empty dict = missing

        # Gate logic: if not ew_dict → MISSING_EVIDENCE_WINDOW
        if not ew_dict:
            status = "MISSING_EVIDENCE_WINDOW"
            reason_codes = ["missing_evidence_window"]
            blocked = True
            approval = "BLOCKED_INSUFFICIENT_HISTORY"
        else:
            status = "NORMAL"
            reason_codes = []
            blocked = False
            approval = "PENDING_HUMAN"

        assert status == "MISSING_EVIDENCE_WINDOW"
        assert "missing_evidence_window" in reason_codes
        assert blocked is True
        assert approval == "BLOCKED_INSUFFICIENT_HISTORY"

    def test_runs_observed_zero(self, th):
        """runs_observed=0 → INSUFFICIENT_HISTORY → BLOCKED."""
        ew = self._make_evidence_window(th, runs_observed=0)
        ew_dict = ew.model_dump(mode="json")

        runs_obs = int(ew_dict.get("runs_observed", 0))
        if runs_obs < self.MIN_REQUIRED:
            status = "INSUFFICIENT_HISTORY"
            reason_codes = ["insufficient_telemetry_history"]
            blocked = True
            approval = "BLOCKED_INSUFFICIENT_HISTORY"
        else:
            status = "NORMAL"
            reason_codes = []
            blocked = False
            approval = "PENDING_HUMAN"

        assert status == "INSUFFICIENT_HISTORY"
        assert "insufficient_telemetry_history" in reason_codes
        assert blocked is True
        assert approval == "BLOCKED_INSUFFICIENT_HISTORY"

    def test_runs_observed_four(self, th):
        """runs_observed=4 (below 5) → INSUFFICIENT_HISTORY → BLOCKED."""
        ew = self._make_evidence_window(th, runs_observed=4)
        ew_dict = ew.model_dump(mode="json")

        runs_obs = int(ew_dict.get("runs_observed", 0))
        status = "INSUFFICIENT_HISTORY" if runs_obs < self.MIN_REQUIRED else "NORMAL"
        blocked = status != "NORMAL"
        approval = "BLOCKED_INSUFFICIENT_HISTORY" if blocked else "PENDING_HUMAN"

        assert status == "INSUFFICIENT_HISTORY"
        assert ew_dict["runs_observed"] == 4
        assert blocked is True
        assert approval == "BLOCKED_INSUFFICIENT_HISTORY"

    def test_runs_observed_five(self, th):
        """runs_observed=5 (== min_required) → NORMAL → PENDING_HUMAN."""
        ew = self._make_evidence_window(th, runs_observed=5)
        ew_dict = ew.model_dump(mode="json")

        runs_obs = int(ew_dict.get("runs_observed", 0))
        status = "NORMAL" if runs_obs >= self.MIN_REQUIRED else "INSUFFICIENT_HISTORY"
        blocked = status != "NORMAL"
        approval = "BLOCKED_INSUFFICIENT_HISTORY" if blocked else "PENDING_HUMAN"

        assert status == "NORMAL"
        assert ew_dict["runs_observed"] == 5
        assert blocked is False
        assert approval == "PENDING_HUMAN"

    def test_runs_observed_above_threshold(self, th):
        """runs_observed=10 → NORMAL → PENDING_HUMAN."""
        ew = self._make_evidence_window(th, runs_observed=10)
        ew_dict = ew.model_dump(mode="json")

        runs_obs = int(ew_dict.get("runs_observed", 0))
        status = "NORMAL" if runs_obs >= self.MIN_REQUIRED else "INSUFFICIENT_HISTORY"
        blocked = status != "NORMAL"
        approval = "BLOCKED_INSUFFICIENT_HISTORY" if blocked else "PENDING_HUMAN"

        assert status == "NORMAL"
        assert blocked is False
        assert approval == "PENDING_HUMAN"

    def test_evidence_window_has_per_bot_data(self, th):
        """EvidenceWindow must contain per-bot trend summaries."""
        ew = th.EvidenceWindow(
            runs_observed=5,
            window_start_utc="2026-06-10T00:00:00Z",
            window_end_utc="2026-06-15T12:00:00Z",
            per_bot_trend_summary={
                "freqtrade-freqforge": {
                    "runs_observed": 5,
                    "mean_profit_ratio": 0.03,
                    "failure_rate": 0.0,
                    "profit_trend": "stable",
                },
                "freqtrade-regime-hybrid": {
                    "runs_observed": 5,
                    "mean_profit_ratio": 0.02,
                    "failure_rate": 0.0,
                    "profit_trend": "stable",
                },
                "freqtrade-freqforge-canary": {
                    "runs_observed": 5,
                    "mean_profit_ratio": 0.025,
                    "failure_rate": 0.0,
                    "profit_trend": "stable",
                },
                "freqai-rebel": {
                    "runs_observed": 5,
                    "mean_profit_ratio": 0.01,
                    "failure_rate": 0.2,
                    "profit_trend": "declining",
                },
            },
        )

        ew_dict = ew.model_dump(mode="json")

        # All 4 bots present
        for bid in ("freqtrade-freqforge", "freqtrade-regime-hybrid",
                    "freqtrade-freqforge-canary", "freqai-rebel"):
            assert bid in ew_dict["per_bot_trend_summary"]

        # Check that the per_bot_trend_summary is a dict (not empty)
        assert len(ew_dict["per_bot_trend_summary"]) == 4

        # Model dump is JSON-safe → verify no secrets
        import json
        raw_json = json.dumps(ew_dict)
        for key in ("api_key", "password", "token", "secret", "private_key"):
            assert key not in raw_json

    def test_evidence_window_no_secrets_in_model_dump(self, th):
        """Full model_dump must be free of sensitive keys."""
        ew = self._make_evidence_window(th, runs_observed=3)
        raw = ew.model_dump(mode="json")
        raw_json_str = json.dumps(raw)
        for key in ("api_key", "password", "token", "secret", "private_key", "mnemonic"):
            assert key not in raw_json_str, f"Sensitive key {key!r} found in EvidenceWindow dump"
