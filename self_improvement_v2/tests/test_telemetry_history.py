"""Tests for the SI v2 telemetry history store, reader, and analyzer.

Covers:
  1. TelemetryHistoryRecord Pydantic validation
  2. BotSnapshot factory and validation
  3. TelemetryHistoryStore append/read
  4. TelemetryHistoryReader safe loading (malformed entries, partial data)
  5. Four-bot completeness validation
  6. Secret/persistence redaction safety
  7. TelemetryHistoryAnalyzer trend calculation with synthetic multi-bot runs
  8. EvidenceWindow construction
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ------------------------------------------------------------------
# Module import (same pattern as conftest)
# ------------------------------------------------------------------
_HISTORY_PATH = Path(__file__).resolve().parents[1] / "src" / "si_v2" / "observe" / "telemetry_history.py"


@pytest.fixture(scope="module")
def th() -> object:
    """Import the telemetry_history module."""
    import importlib.util as iu

    spec = iu.spec_from_file_location("telemetry_history", _HISTORY_PATH)
    assert spec is not None, f"Could not find module at {_HISTORY_PATH}"
    mod = iu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------
# 1. Structure and constants
# ------------------------------------------------------------------
class TestModuleStructure:
    def test_has_constants(self, th):
        assert th.SCHEMA_VERSION == "telemetry_history_v1"
        assert len(th.KNOWN_BOT_IDS) == 4
        assert "freqtrade-freqforge" in th.KNOWN_BOT_IDS
        assert "freqtrade-regime-hybrid" in th.KNOWN_BOT_IDS
        assert "freqtrade-freqforge-canary" in th.KNOWN_BOT_IDS
        assert "freqai-rebel" in th.KNOWN_BOT_IDS

    def test_has_models(self, th):
        assert hasattr(th, "BotSnapshot")
        assert hasattr(th, "TelemetryHistoryRecord")
        assert hasattr(th, "TelemetryHistoryStore")
        assert hasattr(th, "TelemetryHistoryReader")
        assert hasattr(th, "TelemetryHistoryAnalyzer")
        assert hasattr(th, "TrendAnalysis")
        assert hasattr(th, "PerBotTrendSummary")
        assert hasattr(th, "EvidenceWindow")

    def test_version_constant(self, th):
        record = th.TelemetryHistoryRecord(
            cycle_id="test-1",
            generated_at_utc="2026-06-15T12:00:00",
            total_bots=4,
            bots=(),
        )
        assert record.schema_version == "telemetry_history_v1"


# ------------------------------------------------------------------
# 2. BotSnapshot validation
# ------------------------------------------------------------------
class TestBotSnapshot:
    def test_minimal_online(self, th):
        snap = th.BotSnapshot(
            bot_id="freqtrade-freqforge",
            timestamp_utc="2026-06-15T12:00:00Z",
            status="online",
            read_success=True,
        )
        assert snap.bot_id == "freqtrade-freqforge"
        assert snap.status == "online"
        assert snap.read_success

    def test_invalid_status_rejected(self, th):
        with pytest.raises((ValueError, RuntimeError)):
            th.BotSnapshot(
                bot_id="test",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="INVALID_STATUS",
                read_success=False,
            )

    def test_extra_fields_rejected(self, th):
        with pytest.raises((ValueError, RuntimeError, TypeError)):
            th.BotSnapshot(
                bot_id="test",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
                secret_token="should-not-exist",
            )

    def test_from_signal_snapshot_online(self, th):
        snap = th.BotSnapshot.from_signal_snapshot(
            bot_id="freqtrade-freqforge",
            timestamp_utc="2026-06-15T12:00:00Z",
            ping_ok=True,
            auth_outcome="AUTHENTICATED",
            profit_all_percent=1.23,
            profit_all_ratio=0.0123,
            open_trade_count=2,
            count_current=2,
            count_max=5,
            daily_trade_count_total=10,
            daily_abs_profit_sum=12.34,
            whitelist_pair_count=20,
            signal_depth=0.875,
        )
        assert snap.status == "online"
        assert snap.ping_ok is True
        assert snap.auth_outcome == "AUTHENTICATED"
        assert snap.profit_all_percent == 1.23
        assert snap.profit_ratio == 0.0123
        assert snap.open_trade_count == 2
        assert snap.read_success

    def test_from_signal_snapshot_degraded(self, th):
        snap = th.BotSnapshot.from_signal_snapshot(
            bot_id="freqtrade-freqforge",
            timestamp_utc="2026-06-15T12:00:00Z",
            ping_ok=True,
            auth_outcome="FAILED",
            profit_all_percent=None,
            profit_all_ratio=None,
            open_trade_count=None,
            count_current=None,
            count_max=None,
            daily_trade_count_total=None,
            daily_abs_profit_sum=None,
            whitelist_pair_count=None,
            signal_depth=0.0,
        )
        assert snap.status == "degraded"
        assert snap.read_success is False

    def test_from_signal_snapshot_offline(self, th):
        snap = th.BotSnapshot.from_signal_snapshot(
            bot_id="freqtrade-freqforge",
            timestamp_utc="2026-06-15T12:00:00Z",
            ping_ok=False,
            auth_outcome="NOT_ATTEMPTED",
            profit_all_percent=None,
            profit_all_ratio=None,
            open_trade_count=None,
            count_current=None,
            count_max=None,
            daily_trade_count_total=None,
            daily_abs_profit_sum=None,
            whitelist_pair_count=None,
            signal_depth=0.0,
        )
        assert snap.status == "offline"
        assert snap.read_success is False


# ------------------------------------------------------------------
# 3. TelemetryHistoryRecord validation
# ------------------------------------------------------------------
class TestTelemetryHistoryRecord:
    def test_minimal_record(self, th):
        record = th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=4,
            fleet_verdict="GREEN",
            bots=(),
        )
        assert record.cycle_id == "cycle-001"
        assert record.total_bots == 4
        assert record.fleet_verdict == "GREEN"

    def test_with_bot_snapshots(self, th):
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=2,
            bots=bots,
        )
        assert len(record.bots) == 2
        assert record.bots[0].bot_id == "freqtrade-freqforge"

    def test_invalid_fleet_verdict_rejected(self, th):
        with pytest.raises((ValueError, RuntimeError)):
            th.TelemetryHistoryRecord(
                cycle_id="cycle-001",
                generated_at_utc="2026-06-15T12:00:00Z",
                total_bots=4,
                fleet_verdict="INVALID",
                bots=(),
            )

    def test_model_dump_json_roundtrip(self, th):
        """Verify that dumping to JSON and re-loading works (list -> tuple coercion)."""
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
                profit_ratio=0.0123,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            bots=bots,
        )
        raw = record.model_dump(mode="json")
        # JSON serialization converts tuples to lists, so raw["bots"] is a list
        assert isinstance(raw["bots"], list)
        restored = th.TelemetryHistoryRecord(**raw)
        assert restored.cycle_id == record.cycle_id
        assert restored.bots[0].bot_id == record.bots[0].bot_id
        assert restored.bots[0].profit_ratio == record.bots[0].profit_ratio


# ------------------------------------------------------------------
# 4. Store: append and read
# ------------------------------------------------------------------
class TestTelemetryHistoryStore:
    def test_append_and_file_exists(self, th, tmp_path):
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        record = th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=0,
            bots=(),
        )
        file_path = store.append(record)
        assert file_path.exists()
        assert file_path.suffix == ".jsonl"

    def test_append_multiple_records(self, th, tmp_path):
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        for i in range(3):
            record = th.TelemetryHistoryRecord(
                cycle_id=f"cycle-{i:03d}",
                generated_at_utc=f"2026-06-15T12:0{i}:00Z",
                total_bots=0,
                bots=(),
            )
            store.append(record)

        lines = list(store._current_file().open())
        assert len(lines) == 3
        for line in lines:
            data = json.loads(line)
            assert data["schema_version"] == "telemetry_history_v1"

    def test_append_with_bots_and_read_back(self, th, tmp_path):
        """Verifies store append + reader read_all roundtrip."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
                profit_ratio=0.0123,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            bots=bots,
        )
        store.append(record)

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        loaded = reader.read_all()
        assert len(loaded) == 1
        assert loaded[0].bots[0].bot_id == "freqtrade-freqforge"

    def test_default_state_dir(self, th):
        store = th.TelemetryHistoryStore()
        assert store._state_dir.name == "telemetry_history"


# ------------------------------------------------------------------
# 5. Reader: safe loading with edge cases
# ------------------------------------------------------------------
class TestTelemetryHistoryReader:
    def test_read_empty_store(self, th, tmp_path):
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        assert reader.read_all() == []
        assert reader.read_last_n() == []
        assert reader.count_runs() == 0

    def test_read_missing_directory(self, th):
        reader = th.TelemetryHistoryReader(
            state_dir="/tmp/nonexistent-telemetry-dir-12345"
        )
        assert reader.read_all() == []

    def test_read_last_n_ordering(self, th, tmp_path):
        """Records are ordered newest-first in read_last_n."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        for i in range(5):
            record = th.TelemetryHistoryRecord(
                cycle_id=f"cycle-{i:03d}",
                generated_at_utc=f"2026-06-15T12:0{i}:00Z",
                total_bots=0,
                bots=(),
            )
            store.append(record)

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        last_3 = reader.read_last_n(n=3)
        assert len(last_3) == 3
        # Newest first
        assert last_3[0].cycle_id == "cycle-004"
        assert last_3[2].cycle_id == "cycle-002"

    def test_read_last_n_more_than_available(self, th, tmp_path):
        """Requesting more records than exist returns all."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        store.append(th.TelemetryHistoryRecord(
            cycle_id="cycle-001",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=0,
            bots=(),
        ))
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        result = reader.read_last_n(n=10)
        assert len(result) == 1

    def test_malformed_json_lines_skipped(self, th, tmp_path):
        """Corrupted lines should be silently skipped."""
        file_path = tmp_path / "telemetry_20260615.jsonl"
        file_path.write_text(
            '{"cycle_id":"valid-1","generated_at_utc":"2026-06-15T12:00:00Z","total_bots":0,"bots":[],"schema_version":"telemetry_history_v1","fleet_verdict":"UNKNOWN"}\n'
            'NOT VALID JSON\n'
            '{"cycle_id":"valid-2","generated_at_utc":"2026-06-15T12:00:00Z","total_bots":0,"bots":[],"schema_version":"telemetry_history_v1","fleet_verdict":"UNKNOWN"}\n'
        )
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        records = reader.read_all()
        assert len(records) == 2
        assert records[0].cycle_id == "valid-1"
        assert records[1].cycle_id == "valid-2"

    def test_partial_records_skipped(self, th, tmp_path):
        """Incomplete records (missing required fields) should be skipped."""
        file_path = tmp_path / "telemetry_20260615.jsonl"
        file_path.write_text(
            '{"cycle_id":"valid","generated_at_utc":"2026-06-15T12:00:00Z","total_bots":0,"bots":[],"schema_version":"telemetry_history_v1","fleet_verdict":"UNKNOWN"}\n'
            '{"cycle_id":"missing-fields"}\n'
        )
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        records = reader.read_all()
        assert len(records) == 1

    def test_schema_version_mismatch_skipped(self, th, tmp_path):
        """Records with non-matching schema_version should be skipped."""
        file_path = tmp_path / "telemetry_20260615.jsonl"
        file_path.write_text(
            '{"cycle_id":"v1-record","generated_at_utc":"2026-06-15T12:00:00Z","total_bots":0,"bots":[],"schema_version":"telemetry_history_v1","fleet_verdict":"UNKNOWN"}\n'
            '{"cycle_id":"v2-record","generated_at_utc":"2026-06-15T12:00:00Z","total_bots":0,"bots":[],"schema_version":"telemetry_history_v2","fleet_verdict":"UNKNOWN"}\n'
        )
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        records = reader.read_all()
        assert len(records) == 1
        assert records[0].cycle_id == "v1-record"

    def test_missing_bot_coverage_not_crashing(self, th, tmp_path):
        """A record with only 2 out of 4 known bots loads without error."""
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
        )
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        store.append(th.TelemetryHistoryRecord(
            cycle_id="partial-cycle",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=2,
            bots=bots,
        ))
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        records = reader.read_all()
        assert len(records) == 1
        assert len(records[0].bots) == 2

    def test_count_runs(self, th, tmp_path):
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        for i in range(7):
            store.append(th.TelemetryHistoryRecord(
                cycle_id=f"c-{i}",
                generated_at_utc="2026-06-15T12:00:00Z",
                total_bots=0,
                bots=(),
            ))
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        assert reader.count_runs() == 7


# ------------------------------------------------------------------
# 6. Secret redaction / safety
# ------------------------------------------------------------------
class TestSecretSafety:
    def test_sensitive_key_detected_in_dict(self, th):
        """_assert_no_secrets must catch sensitive keys at any nesting level."""
        with pytest.raises(ValueError, match="SECRET DETECTED"):
            th.TelemetryHistoryStore._assert_no_secrets(
                {"safe_key": "safe_value", "api_key": "should-not-be-here"}
            )

    def test_sensitive_key_nested(self, th):
        with pytest.raises(ValueError, match="SECRET DETECTED"):
            th.TelemetryHistoryStore._assert_no_secrets(
                {"outer": {"inner": {"token": "leaked"}}}
            )

    def test_sensitive_key_in_list(self, th):
        with pytest.raises(ValueError, match="SECRET DETECTED"):
            th.TelemetryHistoryStore._assert_no_secrets(
                {"items": [{"safe": 1}, {"password": "hunter2"}]}
            )

    def test_no_secrets_in_bot_snapshot(self, th):
        """Ensure no sensitive key names exist in the BotSnapshot model dump."""
        snap = th.BotSnapshot(
            bot_id="test",
            timestamp_utc="2026-06-15T12:00:00Z",
            status="online",
            read_success=True,
        )
        raw = snap.model_dump(mode="json")
        th.TelemetryHistoryStore._assert_no_secrets(raw)

    def test_no_secrets_in_telemetry_record(self, th):
        """Ensure no sensitive key names in full record."""
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="test",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            bots=bots,
        )
        raw = record.model_dump(mode="json")
        th.TelemetryHistoryStore._assert_no_secrets(raw)

    def test_secret_not_in_jsonl_output(self, th, tmp_path):
        """After append, the JSONL file must not contain any sensitive keys."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc="2026-06-15T12:00:00Z",
                status="online",
                read_success=True,
            ),
        )
        record = th.TelemetryHistoryRecord(
            cycle_id="safe-test",
            generated_at_utc="2026-06-15T12:00:00Z",
            total_bots=1,
            bots=bots,
        )
        store.append(record)
        raw_text = store._current_file().read_text()
        for key in ("api_key", "password", "token", "secret", "private_key"):
            assert key not in raw_text, f"Sensitive key {key!r} found in JSONL output"


# ------------------------------------------------------------------
# 7. Analyzer: trend calculation
# ------------------------------------------------------------------
class TestTelemetryHistoryAnalyzer:
    @staticmethod
    def _make_snapshot(th, bot_id: str, profit_pct: float | None,
                       ping_ok: bool = True, auth: str = "AUTHENTICATED",
                       ts: str = "") -> object:
        """Helper to create a BotSnapshot."""
        return th.BotSnapshot.from_signal_snapshot(
            bot_id=bot_id,
            timestamp_utc=ts or datetime.now(UTC).isoformat(),
            ping_ok=ping_ok,
            auth_outcome=auth,
            profit_all_percent=profit_pct,
            profit_all_ratio=profit_pct / 100.0 if profit_pct is not None else None,
            open_trade_count=2,
            count_current=2,
            count_max=5,
            daily_trade_count_total=10,
            daily_abs_profit_sum=profit_pct or 0.0,
            whitelist_pair_count=20,
            signal_depth=0.875,
        )

    def _build_4_bot_record(
        self, th, bot_profits: dict[str, float | None], ts: str,
        cycle_id: str = "cycle-001",
        fleet_verdict: str = "GREEN",
    ) -> object:
        """Build a TelemetryHistoryRecord with 4 bots and specified profits."""
        bots = tuple(
            self._make_snapshot(th, bid, profit_pct, ts=ts)
            for bid, profit_pct in bot_profits.items()
        )
        return th.TelemetryHistoryRecord(
            cycle_id=cycle_id,
            generated_at_utc=ts,
            total_bots=len(bots),
            fleet_verdict=fleet_verdict,
            bots=bots,
        )

    def test_analyze_empty_store(self, th, tmp_path):
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)
        assert trend.runs_observed == 0
        assert trend.fleet_profit_trend == "insufficient_data"

    def test_analyze_single_run(self, th, tmp_path):
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        ts = datetime.now(UTC).isoformat()
        store.append(self._build_4_bot_record(th, {
            "freqtrade-freqforge": 5.0,
            "freqtrade-regime-hybrid": 3.0,
            "freqtrade-freqforge-canary": 1.0,
            "freqai-rebel": -2.0,
        }, ts))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        assert trend.runs_observed == 1
        assert trend.weakest_bot == "freqai-rebel"
        assert trend.strongest_bot == "freqtrade-freqforge"
        assert trend.fleet_profit_trend == "insufficient_data"  # only 1 run

    def test_analyze_multiple_runs_identifies_weakest(self, th, tmp_path):
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)

        paths = {
            "freqtrade-freqforge": [5.0, 4.5, 5.2],
            "freqtrade-regime-hybrid": [4.0, 3.5, 4.2],
            "freqtrade-freqforge-canary": [3.0, 2.8, 3.1],
            "freqai-rebel": [0.5, 0.3, -1.0],
        }
        for i in range(3):
            profits = {bid: vals[i] for bid, vals in paths.items()}
            store.append(self._build_4_bot_record(
                th, profits, (now - timedelta(hours=2 - i)).isoformat(),
                cycle_id=f"c-{i:03d}",
            ))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        assert trend.runs_observed == 3
        assert trend.weakest_bot == "freqai-rebel"
        assert trend.strongest_bot == "freqtrade-freqforge"

        bot_ids_in_result = {s.bot_id for s in trend.per_bot}
        for bid in ("freqtrade-freqforge", "freqtrade-regime-hybrid",
                    "freqtrade-freqforge-canary", "freqai-rebel"):
            assert bid in bot_ids_in_result, f"Missing bot {bid} in trend analysis"

    def test_analyze_trend_improving(self, th, tmp_path):
        """Test profit_trend detection: improving."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)
        for i, profit in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
            store.append(self._build_4_bot_record(th, {
                "freqtrade-freqforge": profit,
                "freqtrade-regime-hybrid": 3.0,
                "freqtrade-freqforge-canary": 3.0,
                "freqai-rebel": 3.0,
            }, (now - timedelta(hours=5 - i)).isoformat(), cycle_id=f"c-{i:03d}"))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        forge = next(s for s in trend.per_bot if s.bot_id == "freqtrade-freqforge")
        assert forge.profit_trend == "improving"

    def test_analyze_trend_declining(self, th, tmp_path):
        """Test profit_trend detection: declining."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)
        for i, profit in enumerate([5.0, 4.0, 3.0, 2.0, 1.0]):
            store.append(self._build_4_bot_record(th, {
                "freqtrade-freqforge": 3.0,
                "freqtrade-regime-hybrid": 3.0,
                "freqtrade-freqforge-canary": 3.0,
                "freqai-rebel": profit,
            }, (now - timedelta(hours=5 - i)).isoformat(), cycle_id=f"c-{i:03d}"))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        rebel = next(s for s in trend.per_bot if s.bot_id == "freqai-rebel")
        assert rebel.profit_trend == "declining"

    def test_analyze_with_failures(self, th, tmp_path):
        """Analyzer correctly accounts for read failures."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)

        for i in range(3):
            rebel_ok = i < 2  # fails in run 0 and 1
            bots = (
                th.BotSnapshot(
                    bot_id="freqtrade-freqforge",
                    timestamp_utc=now.isoformat(),
                    status="online", read_success=True,
                    ping_ok=True, auth_outcome="AUTHENTICATED",
                    signal_depth=0.875, profit_ratio=0.03,
                ),
                th.BotSnapshot(
                    bot_id="freqtrade-regime-hybrid",
                    timestamp_utc=now.isoformat(),
                    status="online", read_success=True,
                    ping_ok=True, auth_outcome="AUTHENTICATED",
                    signal_depth=0.875, profit_ratio=0.02,
                ),
                th.BotSnapshot(
                    bot_id="freqtrade-freqforge-canary",
                    timestamp_utc=now.isoformat(),
                    status="online", read_success=True,
                    ping_ok=True, auth_outcome="AUTHENTICATED",
                    signal_depth=0.875, profit_ratio=0.025,
                ),
                th.BotSnapshot(
                    bot_id="freqai-rebel",
                    timestamp_utc=now.isoformat(),
                    status="offline" if rebel_ok else "online",
                    read_success=not rebel_ok,
                    ping_ok=not rebel_ok,
                    auth_outcome="AUTHENTICATED" if not rebel_ok else "FAILED",
                    signal_depth=0.0 if rebel_ok else 0.875,
                    profit_ratio=None,
                ),
            )
            store.append(th.TelemetryHistoryRecord(
                cycle_id=f"c-{i:03d}",
                generated_at_utc=now.isoformat(),
                total_bots=4,
                fleet_verdict="YELLOW",
                bots=bots,
            ))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        rebel = next(s for s in trend.per_bot if s.bot_id == "freqai-rebel")
        assert rebel.failure_rate > 0.5
        assert rebel.ping_ok_rate < 0.5

    def test_analyze_stable_trend(self, th, tmp_path):
        """Stable profits should produce 'stable' trend."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)
        for i in range(5):
            store.append(self._build_4_bot_record(th, {
                "freqtrade-freqforge": 3.0,
                "freqtrade-regime-hybrid": 3.0,
                "freqtrade-freqforge-canary": 3.0,
                "freqai-rebel": 3.0,
            }, (now - timedelta(hours=5 - i)).isoformat(), cycle_id=f"c-{i:03d}"))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        stable_count = sum(1 for s in trend.per_bot if s.profit_trend == "stable")
        assert stable_count >= 3

    def test_fleet_freshness_recent(self, th, tmp_path):
        """Fleet freshness should be 'fresh' when last record is recent."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        store.append(self._build_4_bot_record(th, {
            "freqtrade-freqforge": 3.0,
            "freqtrade-regime-hybrid": 3.0,
            "freqtrade-freqforge-canary": 3.0,
            "freqai-rebel": 3.0,
        }, datetime.now(UTC).isoformat()))
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)
        assert trend.fleet_freshness == "fresh"

    def test_evidence_window_construction(self, th, tmp_path):
        """EvidenceWindow must contain all 4 bots with correct structure."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)
        for i in range(3):
            store.append(self._build_4_bot_record(th, {
                "freqtrade-freqforge": 5.0,
                "freqtrade-regime-hybrid": 4.0,
                "freqtrade-freqforge-canary": 3.0,
                "freqai-rebel": 1.0,
            }, (now - timedelta(hours=3 - i)).isoformat(), cycle_id=f"c-{i:03d}"))

        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        ew = analyzer.build_evidence_window(n=5)

        assert ew.runs_observed == 3
        assert isinstance(ew.per_bot_trend_summary, dict)
        for bid in ("freqtrade-freqforge", "freqtrade-regime-hybrid",
                    "freqtrade-freqforge-canary", "freqai-rebel"):
            assert bid in ew.per_bot_trend_summary
            s = ew.per_bot_trend_summary[bid]
            assert "runs_observed" in s
            assert "mean_profit_ratio" in s
            assert "failure_rate" in s
            assert "profit_trend" in s


# ------------------------------------------------------------------
# 8. Integration: store/read/analyze roundtrip with 3 synthetic runs
# ------------------------------------------------------------------
class TestIntegrationRoundtrip:
    def test_full_roundtrip_3_synthetic_runs(self, th, tmp_path):
        """End-to-end: append 3 multi-bot runs, read, analyze, validate."""
        store = th.TelemetryHistoryStore(state_dir=tmp_path)
        now = datetime.now(UTC)

        # Run 1: baseline
        run1_bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc=(now - timedelta(hours=6)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.05,
                profit_all_percent=5.0, open_trade_count=3,
                trade_count=15, signal_depth=0.875,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc=(now - timedelta(hours=6)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.03,
                profit_all_percent=3.0, open_trade_count=2,
                trade_count=10, signal_depth=0.75,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-freqforge-canary",
                timestamp_utc=(now - timedelta(hours=6)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.04,
                profit_all_percent=4.0, open_trade_count=1,
                trade_count=8, signal_depth=0.8,
            ),
            th.BotSnapshot(
                bot_id="freqai-rebel",
                timestamp_utc=(now - timedelta(hours=6)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.01,
                profit_all_percent=1.0, open_trade_count=1,
                trade_count=5, signal_depth=0.5,
            ),
        )
        # Run 2: rebel has a failed read
        run2_bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc=(now - timedelta(hours=3)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.055,
                profit_all_percent=5.5, open_trade_count=2,
                trade_count=16, signal_depth=0.875,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc=(now - timedelta(hours=3)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.032,
                profit_all_percent=3.2, open_trade_count=2,
                trade_count=11, signal_depth=0.75,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-freqforge-canary",
                timestamp_utc=(now - timedelta(hours=3)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.042,
                profit_all_percent=4.2, open_trade_count=1,
                trade_count=9, signal_depth=0.8,
            ),
            th.BotSnapshot(
                bot_id="freqai-rebel",
                timestamp_utc=(now - timedelta(hours=3)).isoformat(),
                status="offline", read_success=False, ping_ok=False,
                auth_outcome="FAILED", profit_ratio=None,
                profit_all_percent=None, open_trade_count=0,
                trade_count=0, signal_depth=0.0,
                error_redacted="Connection timeout",
            ),
        )
        # Run 3: rebel back online but still underperforming
        run3_bots = (
            th.BotSnapshot(
                bot_id="freqtrade-freqforge",
                timestamp_utc=(now - timedelta(hours=1)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.06,
                profit_all_percent=6.0, open_trade_count=2,
                trade_count=17, signal_depth=0.875,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-regime-hybrid",
                timestamp_utc=(now - timedelta(hours=1)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.033,
                profit_all_percent=3.3, open_trade_count=2,
                trade_count=11, signal_depth=0.75,
            ),
            th.BotSnapshot(
                bot_id="freqtrade-freqforge-canary",
                timestamp_utc=(now - timedelta(hours=1)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.044,
                profit_all_percent=4.4, open_trade_count=2,
                trade_count=10, signal_depth=0.8,
            ),
            th.BotSnapshot(
                bot_id="freqai-rebel",
                timestamp_utc=(now - timedelta(hours=1)).isoformat(),
                status="online", read_success=True, ping_ok=True,
                auth_outcome="AUTHENTICATED", profit_ratio=0.008,
                profit_all_percent=0.8, open_trade_count=1,
                trade_count=6, signal_depth=0.5,
            ),
        )

        store.append(th.TelemetryHistoryRecord(
            cycle_id="run-001", generated_at_utc=(now - timedelta(hours=6)).isoformat(),
            total_bots=4, fleet_verdict="GREEN", bots=run1_bots,
        ))
        store.append(th.TelemetryHistoryRecord(
            cycle_id="run-002", generated_at_utc=(now - timedelta(hours=3)).isoformat(),
            total_bots=4, fleet_verdict="YELLOW", bots=run2_bots,
        ))
        store.append(th.TelemetryHistoryRecord(
            cycle_id="run-003", generated_at_utc=(now - timedelta(hours=1)).isoformat(),
            total_bots=4, fleet_verdict="GREEN", bots=run3_bots,
        ))

        # Reader
        reader = th.TelemetryHistoryReader(state_dir=tmp_path)
        all_records = reader.read_all()
        assert len(all_records) == 3
        assert all_records[0].cycle_id == "run-001"
        assert all_records[2].cycle_id == "run-003"

        # Analyzer
        analyzer = th.TelemetryHistoryAnalyzer(reader=reader)
        trend = analyzer.analyze_window(n=5)

        assert trend.runs_observed == 3
        assert trend.weakest_bot == "freqai-rebel"
        assert trend.strongest_bot == "freqtrade-freqforge"

        summaries_by_bot = {s.bot_id: s for s in trend.per_bot}
        rebel = summaries_by_bot["freqai-rebel"]
        forge = summaries_by_bot["freqtrade-freqforge"]
        assert rebel.failure_rate == pytest.approx(1 / 3, rel=0.01)
        assert forge.runs_observed == 3

        # EvidenceWindow
        ew = analyzer.build_evidence_window(n=5)
        assert ew.runs_observed == 3
        assert "freqai-rebel" in ew.per_bot_trend_summary
        rebel_ew = ew.per_bot_trend_summary["freqai-rebel"]
        assert rebel_ew["runs_observed"] == 3
        assert rebel_ew["failure_rate"] == pytest.approx(1 / 3, rel=0.01)
