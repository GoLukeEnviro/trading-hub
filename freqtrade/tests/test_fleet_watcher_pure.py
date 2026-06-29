"""Tests for fleet_watcher.py pure functions — no Docker, no subprocess, no I/O.

Tests cover: parse_iso, format_dt, format_minutes, format_delta, safe_float,
load_json, load_jsonl, hash_text, state_signature, render_state_snapshot,
summarize_open_trade, state_summary, monitor_report_signature,
proposals_signature, events_signature, signals_signature,
signal_state_signature, color_supported, style_text, shorten_text,
format_float, severity_rank, summarize_top_proposal, summarize_bot_line,
build_alerts, diff_state, diff_artifact, render_cycle.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fleet_watcher import (
    AlertRecord,
    ArtifactSnapshot,
    ContainerLogSnapshot,
    CycleSnapshot,
    StateSnapshot,
    WatcherContext,
    build_alerts,
    color_supported,
    diff_artifact,
    diff_state,
    format_delta,
    format_dt,
    format_float,
    format_minutes,
    hash_text,
    load_json,
    load_jsonl,
    monitor_report_signature,
    now_utc,
    parse_iso,
    proposals_signature,
    render_cycle,
    render_monitor_report,
    render_proposals,
    render_signal_state,
    render_state_snapshot,
    safe_float,
    severity_rank,
    shorten_text,
    signal_state_signature,
    signals_signature,
    state_signature,
    state_summary,
    style_text,
    summarize_bot_line,
    summarize_open_trade,
    summarize_top_proposal,
)

UTC = timezone.utc


# ======================================================================
# parse_iso
# ======================================================================

class TestParseIso:
    def test_valid_iso_z(self) -> None:
        result = parse_iso("2026-06-22T12:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 22
        assert result.hour == 12
        assert result.minute == 0
        assert result.tzinfo is not None

    def test_valid_iso_offset(self) -> None:
        result = parse_iso("2026-06-22T12:00:00+00:00")
        assert result is not None
        assert result.hour == 12

    def test_valid_iso_no_offset(self) -> None:
        """Naive datetime should be treated as UTC."""
        result = parse_iso("2026-06-22T12:00:00")
        assert result is not None
        assert result.tzinfo is not None
        assert result.hour == 12

    def test_none_input(self) -> None:
        assert parse_iso(None) is None

    def test_empty_string(self) -> None:
        assert parse_iso("") is None

    def test_whitespace_string(self) -> None:
        assert parse_iso("   ") is None

    def test_invalid_string(self) -> None:
        assert parse_iso("not-a-date") is None

    def test_garbage_string(self) -> None:
        assert parse_iso("2026-13-40T99:99:99") is None

    def test_fractional_seconds(self) -> None:
        result = parse_iso("2026-06-22T12:00:00.123456Z")
        assert result is not None
        assert result.microsecond == 123456

    def test_long_fractional_truncated(self) -> None:
        """More than 6 fractional digits should be truncated."""
        result = parse_iso("2026-06-22T12:00:00.123456789Z")
        assert result is not None
        assert result.microsecond == 123456


# ======================================================================
# format_dt
# ======================================================================

class TestFormatDt:
    def test_format_datetime(self) -> None:
        dt = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
        result = format_dt(dt)
        assert "2026-06-22" in result
        assert "12:00:00" in result
        assert "UTC" in result

    def test_format_none(self) -> None:
        assert format_dt(None) == "n/a"

    def test_format_non_utc(self) -> None:
        """Non-UTC timezone should be converted to UTC."""
        import datetime as dt_mod
        tz_offset = dt_mod.timezone(dt_mod.timedelta(hours=2))
        dt = datetime(2026, 6, 22, 14, 0, 0, tzinfo=tz_offset)
        result = format_dt(dt)
        assert "12:00:00" in result  # 14:00 +02:00 = 12:00 UTC


# ======================================================================
# format_minutes
# ======================================================================

class TestFormatMinutes:
    def test_none(self) -> None:
        assert format_minutes(None) == "n/a"

    def test_zero(self) -> None:
        assert format_minutes(0) == "0m"

    def test_negative(self) -> None:
        assert format_minutes(-5) == "0m"

    def test_minutes_only(self) -> None:
        assert format_minutes(45) == "45m"

    def test_hours_and_minutes(self) -> None:
        assert format_minutes(125) == "2h05m"

    def test_exact_hour(self) -> None:
        assert format_minutes(60) == "1h00m"

    def test_large_value(self) -> None:
        assert format_minutes(1440) == "24h00m"


# ======================================================================
# format_delta
# ======================================================================

class TestFormatDelta:
    def test_none(self) -> None:
        assert format_delta(None) == "n/a"

    def test_positive(self) -> None:
        assert format_delta(1.5) == "+1.50"

    def test_negative(self) -> None:
        assert format_delta(-0.5) == "-0.50"

    def test_zero(self) -> None:
        assert format_delta(0.0) == "+0.00"


# ======================================================================
# safe_float
# ======================================================================

class TestSafeFloat:
    def test_float_input(self) -> None:
        assert safe_float(3.14) == 3.14

    def test_int_input(self) -> None:
        assert safe_float(42) == 42.0

    def test_str_input(self) -> None:
        assert safe_float("3.14") == 3.14

    def test_none_input(self) -> None:
        assert safe_float(None) is None

    def test_invalid_str(self) -> None:
        assert safe_float("not-a-number") is None

    def test_custom_default(self) -> None:
        assert safe_float(None, default=0.0) == 0.0

    def test_empty_string(self) -> None:
        assert safe_float("") is None

    def test_bool_input(self) -> None:
        assert safe_float(True) == 1.0
        assert safe_float(False) == 0.0


# ======================================================================
# load_json
# ======================================================================

class TestLoadJson:
    def test_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}')
        data, error = load_json(path)
        assert data == {"key": "value"}
        assert error is None

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        data, error = load_json(path)
        assert data is None
        assert error is not None

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("")
        data, error = load_json(path)
        assert data is None
        assert error is not None

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid}")
        data, error = load_json(path)
        assert data is None
        assert error is not None

    def test_json_array(self, tmp_path: Path) -> None:
        """JSON arrays should be rejected (expects object)."""
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]")
        data, error = load_json(path)
        assert data is None
        assert error is not None
        assert "list" in error.lower()

    def test_json_number(self, tmp_path: Path) -> None:
        """JSON primitives should be rejected."""
        path = tmp_path / "number.json"
        path.write_text("42")
        data, error = load_json(path)
        assert data is None
        assert error is not None


# ======================================================================
# load_jsonl
# ======================================================================

class TestLoadJsonl:
    def test_valid_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\n{"b": 2}\n')
        records, error = load_jsonl(path)
        assert len(records) == 2
        assert records[0] == {"a": 1}
        assert records[1] == {"b": 2}
        assert error is None

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.jsonl"
        records, error = load_jsonl(path)
        assert records == []
        assert error is not None

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        records, error = load_jsonl(path)
        assert records == []
        assert error is None

    def test_skip_invalid_lines(self, tmp_path: Path) -> None:
        """Invalid JSON lines should be skipped, not crash."""
        path = tmp_path / "mixed.jsonl"
        path.write_text('{"a": 1}\nnot-json\n{"b": 2}\n')
        records, error = load_jsonl(path)
        assert len(records) == 2
        assert records[0] == {"a": 1}
        assert records[1] == {"b": 2}

    def test_skip_non_dict_lines(self, tmp_path: Path) -> None:
        """JSON arrays or primitives should be skipped."""
        path = tmp_path / "non_dict.jsonl"
        path.write_text('{"a": 1}\n[1,2,3]\n"string"\n')
        records, error = load_jsonl(path)
        assert len(records) == 1
        assert records[0] == {"a": 1}


# ======================================================================
# hash_text
# ======================================================================

class TestHashText:
    def test_deterministic(self) -> None:
        assert hash_text("hello") == hash_text("hello")

    def test_different_inputs(self) -> None:
        assert hash_text("hello") != hash_text("world")

    def test_empty_string(self) -> None:
        result = hash_text("")
        assert isinstance(result, str)
        assert len(result) == 12

    def test_unicode(self) -> None:
        result = hash_text("héllo wörld 🔥")
        assert isinstance(result, str)
        assert len(result) == 12


# ======================================================================
# state_signature
# ======================================================================

class TestStateSignature:
    def test_deterministic(self) -> None:
        data = {"portfolio": {"current_equity": 1000}, "open_trades": [], "trade_history": []}
        assert state_signature(data) == state_signature(data)

    def test_different_data(self) -> None:
        assert state_signature({"portfolio": {"current_equity": 1000}, "open_trades": [], "trade_history": []}) != \
               state_signature({"portfolio": {"current_equity": 2000}, "open_trades": [], "trade_history": []})

    def test_empty_dict(self) -> None:
        sig = state_signature({})
        assert isinstance(sig, str)
        assert len(sig) == 16

    def test_missing_fields(self) -> None:
        """Missing optional fields should not crash."""
        sig = state_signature({"portfolio": {}})
        assert isinstance(sig, str)
        assert len(sig) == 16

    def test_open_trades_affects_signature(self) -> None:
        data1 = {"portfolio": {}, "open_trades": [{"trade_key": "abc"}], "trade_history": []}
        data2 = {"portfolio": {}, "open_trades": [{"trade_key": "xyz"}], "trade_history": []}
        assert state_signature(data1) != state_signature(data2)


# ======================================================================
# render_state_snapshot
# ======================================================================

class TestRenderStateSnapshot:
    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        snap = render_state_snapshot(path)
        assert snap.exists is False
        assert snap.error == "missing file"
        assert snap.signature == "missing"

    def test_valid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({
            "portfolio": {"current_equity": 1000.0, "peak_equity": 1100.0, "current_drawdown": 0.05},
            "open_trades": [{"trade_key": "abc", "pair": "BTC/USDT", "direction": "long"}],
            "trade_history": [{"profit": 0.1}],
            "last_update": "2026-06-22T12:00:00Z",
        }))
        snap = render_state_snapshot(path)
        assert snap.exists is True
        assert snap.error is None
        assert snap.current_equity == 1000.0
        assert snap.peak_equity == 1100.0
        assert snap.drawdown == 0.05
        assert len(snap.open_trades) == 1
        assert snap.history_count == 1
        assert snap.last_update is not None
        assert snap.signature != "missing"

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid}")
        snap = render_state_snapshot(path)
        assert snap.exists is True
        assert snap.error is not None
        assert snap.signature.startswith("error:")

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("")
        snap = render_state_snapshot(path)
        assert snap.exists is True
        assert snap.error is not None


# ======================================================================
# summarize_open_trade
# ======================================================================

class TestSummarizeOpenTrade:
    def test_full_entry(self) -> None:
        entry = {"pair": "BTC/USDT", "direction": "long", "source": "signal", "trade_id": 1, "stake": 100.0, "opened_at": "2026-06-22T12:00:00Z"}
        result = summarize_open_trade(entry)
        assert "BTC/USDT" in result
        assert "long" in result
        assert "100.00" in result

    def test_minimal_entry(self) -> None:
        entry = {}
        result = summarize_open_trade(entry)
        assert result is not None
        assert "?" in result  # fallback values

    def test_missing_stake(self) -> None:
        entry = {"pair": "BTC/USDT", "direction": "long", "trade_id": 1}
        result = summarize_open_trade(entry)
        assert "n/a" in result


# ======================================================================
# state_summary
# ======================================================================

class TestStateSummary:
    def test_error_state(self) -> None:
        snap = StateSnapshot(
            path=Path("/fake"), exists=False, mtime_iso=None, age_min=None,
            error="test error", current_equity=None, peak_equity=None,
            drawdown=None, open_trades=[], history_count=0, last_update=None,
            signature="error",
        )
        result = state_summary(snap)
        assert "ERROR" in result
        assert "test error" in result

    def test_healthy_state(self) -> None:
        snap = StateSnapshot(
            path=Path("/fake"), exists=True, mtime_iso="2026-06-22 12:00:00 UTC", age_min=5.0,
            error=None, current_equity=1000.0, peak_equity=1100.0,
            drawdown=0.05, open_trades=[], history_count=10, last_update="2026-06-22T12:00:00Z",
            signature="abc123",
        )
        result = state_summary(snap)
        assert "1000.00" in result
        assert "1100.00" in result
        assert "5.00" in result or "5" in result  # state_age

    def test_none_values(self) -> None:
        snap = StateSnapshot(
            path=Path("/fake"), exists=True, mtime_iso=None, age_min=None,
            error=None, current_equity=None, peak_equity=None,
            drawdown=None, open_trades=[], history_count=0, last_update=None,
            signature="abc",
        )
        result = state_summary(snap)
        assert "n/a" in result


# ======================================================================
# monitor_report_signature
# ======================================================================

class TestMonitorReportSignature:
    def test_deterministic(self) -> None:
        data = {"timestamp_utc": "2026-06-22T12:00:00Z", "bots": {}, "signals": {}}
        assert monitor_report_signature(data) == monitor_report_signature(data)

    def test_different_data(self) -> None:
        data1 = {"timestamp_utc": "2026-06-22T12:00:00Z", "bots": {}, "signals": {}}
        data2 = {"timestamp_utc": "2026-06-22T13:00:00Z", "bots": {}, "signals": {}}
        assert monitor_report_signature(data1) != monitor_report_signature(data2)

    def test_empty_dict(self) -> None:
        sig = monitor_report_signature({})
        assert isinstance(sig, str)
        assert len(sig) == 16


# ======================================================================
# proposals_signature
# ======================================================================

class TestProposalsSignature:
    def test_deterministic(self) -> None:
        data = {"timestamp_utc": "2026-06-22T12:00:00Z", "summary": {}, "fleet_proposals": []}
        assert proposals_signature(data) == proposals_signature(data)

    def test_empty_dict(self) -> None:
        sig = proposals_signature({})
        assert isinstance(sig, str)
        assert len(sig) == 16


# ======================================================================
# signal_state_signature
# ======================================================================

class TestSignalStateSignature:
    def test_deterministic(self) -> None:
        data = {"generated_at": "2026-06-22T12:00:00Z", "pairs": {"BTC/USDT": {}}}
        assert signal_state_signature(data) == signal_state_signature(data)

    def test_empty_dict(self) -> None:
        sig = signal_state_signature({})
        assert isinstance(sig, str)
        assert len(sig) == 16


# ======================================================================
# signals_signature
# ======================================================================

class TestSignalsSignature:
    def test_deterministic(self) -> None:
        data = [{"canonical": {"timestamp_utc": "2026-06-22T12:00:00Z"}}]
        assert signals_signature(data) == signals_signature(data)

    def test_empty_list(self) -> None:
        sig = signals_signature([])
        assert isinstance(sig, str)
        assert len(sig) == 16


# ======================================================================
# color_supported
# ======================================================================

class TestColorSupported:
    def test_always(self) -> None:
        assert color_supported("always") is True

    def test_never(self) -> None:
        assert color_supported("never") is False

    def test_auto_no_tty(self) -> None:
        """Without a TTY, auto should return False."""
        result = color_supported("auto")
        assert result is False  # No TTY in test runner


# ======================================================================
# style_text
# ======================================================================

class TestStyleText:
    def test_disabled(self) -> None:
        assert style_text("hello", "critical", enabled=False) == "hello"

    def test_known_severity(self) -> None:
        result = style_text("hello", "critical", enabled=True)
        assert result != "hello"  # Has ANSI codes

    def test_unknown_severity(self) -> None:
        result = style_text("hello", "unknown", enabled=True)
        # Unknown severity still appends ANSI reset code
        assert result == "hello\x1b[0m"


# ======================================================================
# shorten_text
# ======================================================================

class TestShortenText:
    def test_short_text(self) -> None:
        assert shorten_text("hello") == "hello"

    def test_long_text(self) -> None:
        text = "a" * 200
        result = shorten_text(text, limit=10)
        assert len(result) <= 10
        assert result.endswith("…")

    def test_none_input(self) -> None:
        assert shorten_text(None) == ""

    def test_empty_string(self) -> None:
        assert shorten_text("") == ""

    def test_exact_limit(self) -> None:
        text = "a" * 96
        assert shorten_text(text) == text  # Default limit is 96

    def test_custom_limit(self) -> None:
        text = "hello world"
        # shorten_text takes text[:limit-1] + "…"
        assert shorten_text(text, limit=5) == "hell…"


# ======================================================================
# format_float
# ======================================================================

class TestFormatFloat:
    def test_valid_number(self) -> None:
        assert format_float(3.14159, digits=2) == "3.14"

    def test_none(self) -> None:
        assert format_float(None) == "n/a"

    def test_int_input(self) -> None:
        assert format_float(42, digits=2) == "42.00"

    def test_custom_digits(self) -> None:
        assert format_float(1.23456, digits=4) == "1.2346"


# ======================================================================
# severity_rank
# ======================================================================

class TestSeverityRank:
    def test_critical(self) -> None:
        assert severity_rank("critical") == 3

    def test_high(self) -> None:
        assert severity_rank("high") == 2

    def test_medium(self) -> None:
        assert severity_rank("medium") == 1

    def test_low(self) -> None:
        assert severity_rank("low") == 0

    def test_unknown(self) -> None:
        assert severity_rank("unknown") == -1

    def test_none(self) -> None:
        assert severity_rank(None) == -1

    def test_case_insensitive(self) -> None:
        assert severity_rank("CRITICAL") == 3
        assert severity_rank("High") == 2


# ======================================================================
# summarize_top_proposal
# ======================================================================

class TestSummarizeTopProposal:
    def test_empty_list(self) -> None:
        assert summarize_top_proposal([]) == "none"

    def test_none_input(self) -> None:
        assert summarize_top_proposal(None) == "none"

    def test_not_a_list(self) -> None:
        assert summarize_top_proposal("string") == "none"

    def test_single_proposal(self) -> None:
        proposals = [{"type": "stake_scale_down", "severity": "high", "reason": "drawdown too high"}]
        result = summarize_top_proposal(proposals)
        assert "stake_scale_down" in result
        assert "high" in result
        assert "drawdown" in result

    def test_multiple_proposals(self) -> None:
        proposals = [
            {"type": "stake_scale_down", "severity": "high", "reason": "drawdown"},
            {"type": "quarantine_recommended", "severity": "critical", "reason": "bot failing"},
        ]
        result = summarize_top_proposal(proposals)
        # Should sort by severity, critical first
        assert "quarantine_recommended" in result
        assert "critical" in result

    def test_string_items(self) -> None:
        proposals = ["item1", "item2"]
        result = summarize_top_proposal(proposals)
        assert "item1" in result
        assert "item2" in result

    def test_many_string_items(self) -> None:
        proposals = ["a", "b", "c", "d"]
        result = summarize_top_proposal(proposals)
        assert "more" in result


# ======================================================================
# summarize_bot_line
# ======================================================================

class TestSummarizeBotLine:
    def test_full_decision(self) -> None:
        bot_data = {
            "decision": {
                "verdict": "TOP_CANDIDATE",
                "risk": "low",
                "profit_factor": 1.5,
                "winrate_pct": 60.0,
                "proposals": [{"type": "stake_scale_down", "severity": "low"}],
            }
        }
        result = summarize_bot_line("freqforge", bot_data)
        assert "freqforge" in result
        assert "TOP_CANDIDATE" in result
        assert "1.5000" in result
        assert "60.00" in result

    def test_missing_decision(self) -> None:
        result = summarize_bot_line("freqforge", {})
        assert "freqforge" in result
        assert "n/a" in result


# ======================================================================
# build_alerts
# ======================================================================

class TestBuildAlerts:
    def _make_state_snapshot(self, **overrides: object) -> StateSnapshot:
        defaults: dict = {
            "path": Path("/fake"),
            "exists": True,
            "mtime_iso": "2026-06-22 12:00:00 UTC",
            "age_min": 5.0,
            "error": None,
            "current_equity": 1000.0,
            "peak_equity": 1100.0,
            "drawdown": 0.02,
            "open_trades": [],
            "history_count": 10,
            "last_update": "2026-06-22T12:00:00Z",
            "signature": "abc",
        }
        defaults.update(overrides)
        return StateSnapshot(**defaults)

    def _make_artifact(self, name: str = "test", error: str | None = None, **details: object) -> ArtifactSnapshot:
        return ArtifactSnapshot(
            name=name, path=Path("/fake"), exists=True,
            mtime_iso="2026-06-22 12:00:00 UTC", age_min=5.0,
            size_bytes=100, summary="ok", signature="abc",
            details=details, error=error,
        )

    def _make_container(self, name: str = "trading-freqtrade-freqforge-1",
                        status: str = "running", error: str | None = None,
                        restart_count: int = 0, heartbeat_age_min: float | None = None,
                        new_lines: list[str] | None = None) -> ContainerLogSnapshot:
        return ContainerLogSnapshot(
            name=name, status=status, started_at="2026-06-22T12:00:00Z",
            uptime_min=60.0, restart_count=restart_count,
            heartbeat_ts="2026-06-22T12:00:00Z", heartbeat_age_min=heartbeat_age_min,
            warning_count=0, error_count=0, fleet_count=0, status_count=0,
            new_lines=new_lines or [], signature="abc", error=error,
        )

    def _make_snapshot(self, state: StateSnapshot | None = None,
                       artifacts: dict | None = None,
                       containers: dict | None = None) -> CycleSnapshot:
        if state is None:
            state = self._make_state_snapshot()
        if artifacts is None:
            artifacts = {
                "fleet_monitor_report": self._make_artifact("fleet_monitor_report"),
                "self_optimizer_proposals": self._make_artifact("self_optimizer_proposals"),
            }
        if containers is None:
            containers = {
                "trading-freqtrade-freqforge-1": self._make_container(),
                "trading-freqtrade-freqforge-canary-1": self._make_container("trading-freqtrade-freqforge-canary-1"),
                "trading-freqtrade-regime-hybrid-1": self._make_container("trading-freqtrade-regime-hybrid-1"),
            }
        return CycleSnapshot(
            ts=datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC),
            state=state, artifacts=artifacts, containers=containers,
        )

    def test_no_alerts_for_green_state(self) -> None:
        ctx = WatcherContext()
        snapshot = self._make_snapshot()
        alerts = build_alerts(snapshot, ctx)
        assert len(alerts) == 0

    def test_alert_on_state_error(self) -> None:
        ctx = WatcherContext()
        state = self._make_state_snapshot(error="file not found")
        snapshot = self._make_snapshot(state=state)
        alerts = build_alerts(snapshot, ctx)
        assert len(alerts) > 0
        assert any("file not found" in a.message for a in alerts)

    def test_alert_on_high_drawdown(self) -> None:
        ctx = WatcherContext()
        state = self._make_state_snapshot(drawdown=0.05)
        snapshot = self._make_snapshot(state=state)
        alerts = build_alerts(snapshot, ctx)
        assert len(alerts) > 0
        assert any("drawdown" in a.message.lower() for a in alerts)

    def test_alert_on_live_trading_allowed(self) -> None:
        ctx = WatcherContext()
        artifact = self._make_artifact("fleet_monitor_report", live_trading_allowed=True)
        snapshot = self._make_snapshot(artifacts={"fleet_monitor_report": artifact, "self_optimizer_proposals": self._make_artifact("self_optimizer_proposals")})
        alerts = build_alerts(snapshot, ctx)
        assert any("live_trading_allowed" in a.message for a in alerts)

    def test_alert_on_container_error(self) -> None:
        ctx = WatcherContext()
        container = self._make_container(error="connection refused")
        snapshot = self._make_snapshot(containers={"trading-freqtrade-freqforge-1": container})
        alerts = build_alerts(snapshot, ctx)
        assert any("connection refused" in a.message for a in alerts)

    def test_alert_on_container_not_running(self) -> None:
        ctx = WatcherContext()
        container = self._make_container(status="exited")
        snapshot = self._make_snapshot(containers={"trading-freqtrade-freqforge-1": container})
        alerts = build_alerts(snapshot, ctx)
        assert any("exited" in a.message or "status=exited" in a.message for a in alerts)

    def test_alert_on_stale_heartbeat(self) -> None:
        ctx = WatcherContext()
        container = self._make_container(heartbeat_age_min=20.0)
        snapshot = self._make_snapshot(containers={"trading-freqtrade-freqforge-1": container})
        alerts = build_alerts(snapshot, ctx)
        assert any("heartbeat" in a.message.lower() for a in alerts)

    def test_alert_on_container_restart(self) -> None:
        ctx = WatcherContext()
        prev_container = self._make_container(restart_count=0)
        curr_container = self._make_container(restart_count=2)
        ctx.prev_containers = {"trading-freqtrade-freqforge-1": prev_container}
        snapshot = self._make_snapshot(containers={"trading-freqtrade-freqforge-1": curr_container})
        alerts = build_alerts(snapshot, ctx)
        assert any("restart" in a.message.lower() for a in alerts)

    def test_alert_on_error_in_logs(self) -> None:
        ctx = WatcherContext()
        container = self._make_container(new_lines=["ERROR: something failed"])
        snapshot = self._make_snapshot(containers={"trading-freqtrade-freqforge-1": container})
        alerts = build_alerts(snapshot, ctx)
        assert any("ERROR" in a.message for a in alerts)

    def test_no_duplicate_alerts(self) -> None:
        """Same alert should not appear twice."""
        ctx = WatcherContext()
        state = self._make_state_snapshot(drawdown=0.05)
        snapshot = self._make_snapshot(state=state)
        alerts = build_alerts(snapshot, ctx)
        drawdown_alerts = [a for a in alerts if "drawdown" in a.message.lower()]
        assert len(drawdown_alerts) <= 1


# ======================================================================
# diff_state
# ======================================================================

class TestDiffState:
    def _make_state(self, **overrides: object) -> StateSnapshot:
        defaults: dict = {
            "path": Path("/fake"), "exists": True, "mtime_iso": None, "age_min": None,
            "error": None, "current_equity": 1000.0, "peak_equity": 1100.0,
            "drawdown": 0.05, "open_trades": [], "history_count": 10,
            "last_update": "2026-06-22T12:00:00Z", "signature": "abc",
        }
        defaults.update(overrides)
        return StateSnapshot(**defaults)

    def test_no_diff(self) -> None:
        prev = self._make_state()
        curr = self._make_state()
        assert diff_state(prev, curr) == []

    def test_equity_change(self) -> None:
        prev = self._make_state(current_equity=1000.0)
        curr = self._make_state(current_equity=1050.0)
        diffs = diff_state(prev, curr)
        assert any("equity" in d for d in diffs)

    def test_drawdown_change(self) -> None:
        prev = self._make_state(drawdown=0.05)
        curr = self._make_state(drawdown=0.08)
        diffs = diff_state(prev, curr)
        assert any("drawdown" in d for d in diffs)

    def test_open_trades_count_change(self) -> None:
        prev = self._make_state(open_trades=[])
        curr = self._make_state(open_trades=[{"trade_key": "abc"}])
        diffs = diff_state(prev, curr)
        assert any("open_trades" in d for d in diffs)

    def test_history_count_change(self) -> None:
        prev = self._make_state(history_count=10)
        curr = self._make_state(history_count=12)
        diffs = diff_state(prev, curr)
        assert any("history" in d for d in diffs)

    def test_last_update_change(self) -> None:
        prev = self._make_state(last_update="2026-06-22T12:00:00Z")
        curr = self._make_state(last_update="2026-06-22T13:00:00Z")
        diffs = diff_state(prev, curr)
        assert any("last_update" in d for d in diffs)

    def test_prev_is_none(self) -> None:
        curr = self._make_state()
        diffs = diff_state(None, curr)
        assert len(diffs) > 0
        assert any("initial" in d for d in diffs)

    def test_curr_error(self) -> None:
        prev = self._make_state()
        curr = self._make_state(error="something broke")
        diffs = diff_state(prev, curr)
        assert any("error" in d for d in diffs)

    def test_trade_key_diff(self) -> None:
        prev = self._make_state(open_trades=[{"trade_key": "abc"}])
        curr = self._make_state(open_trades=[{"trade_key": "xyz"}])
        diffs = diff_state(prev, curr)
        assert any("opened" in d for d in diffs) or any("closed" in d for d in diffs)


# ======================================================================
# diff_artifact
# ======================================================================

class TestDiffArtifact:
    def _make_artifact(self, signature: str = "abc", summary: str = "ok") -> ArtifactSnapshot:
        return ArtifactSnapshot(
            name="test", path=Path("/fake"), exists=True,
            mtime_iso=None, age_min=None, size_bytes=None,
            summary=summary, signature=signature, details={},
        )

    def test_no_diff(self) -> None:
        prev = self._make_artifact(signature="abc")
        curr = self._make_artifact(signature="abc")
        assert diff_artifact(prev, curr) == []

    def test_signature_change(self) -> None:
        prev = self._make_artifact(signature="abc")
        curr = self._make_artifact(signature="xyz")
        diffs = diff_artifact(prev, curr)
        assert len(diffs) > 0

    def test_prev_is_none(self) -> None:
        curr = self._make_artifact()
        diffs = diff_artifact(None, curr)
        assert len(diffs) > 0
        assert "ok" in diffs[0]


# ======================================================================
# render_cycle
# ======================================================================

class TestRenderCycle:
    def _make_state(self, **overrides: object) -> StateSnapshot:
        defaults: dict = {
            "path": Path("/fake"), "exists": True, "mtime_iso": None, "age_min": None,
            "error": None, "current_equity": 1000.0, "peak_equity": 1100.0,
            "drawdown": 0.02, "open_trades": [], "history_count": 10,
            "last_update": "2026-06-22T12:00:00Z", "signature": "abc",
        }
        defaults.update(overrides)
        return StateSnapshot(**defaults)

    def _make_artifact(self, name: str = "test", error: str | None = None) -> ArtifactSnapshot:
        return ArtifactSnapshot(
            name=name, path=Path("/fake"), exists=True,
            mtime_iso="2026-06-22 12:00:00 UTC", age_min=5.0,
            size_bytes=100, summary="ok", signature="abc",
            details={}, error=error,
        )

    def _make_container(self, name: str = "trading-freqtrade-freqforge-1") -> ContainerLogSnapshot:
        return ContainerLogSnapshot(
            name=name, status="running", started_at="2026-06-22T12:00:00Z",
            uptime_min=60.0, restart_count=0,
            heartbeat_ts="2026-06-22T12:00:00Z", heartbeat_age_min=1.0,
            warning_count=0, error_count=0, fleet_count=0, status_count=0,
            new_lines=[], signature="abc",
        )

    def test_render_normal(self) -> None:
        state = self._make_state()
        artifacts = {
            "fleet_monitor_report": self._make_artifact("fleet_monitor_report"),
            "self_optimizer_proposals": self._make_artifact("self_optimizer_proposals"),
            "self_optimizer_events": self._make_artifact("self_optimizer_events"),
            "primo_signal_state": self._make_artifact("primo_signal_state"),
            "historical_signals": self._make_artifact("historical_signals"),
        }
        containers = {
            "trading-freqtrade-freqforge-1": self._make_container(),
            "trading-freqtrade-freqforge-canary-1": self._make_container("trading-freqtrade-freqforge-canary-1"),
            "trading-freqtrade-regime-hybrid-1": self._make_container("trading-freqtrade-regime-hybrid-1"),
        }
        snapshot = CycleSnapshot(
            ts=datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC),
            state=state, artifacts=artifacts, containers=containers,
        )
        ctx = WatcherContext()
        result = render_cycle(snapshot, ctx)
        assert "FleetWatcher" in result
        assert "State:" in result
        assert "Alerts:" in result
        assert "Artifacts:" in result
        assert "Containers:" in result
        assert "Changes:" in result

    def test_render_with_alerts(self) -> None:
        state = self._make_state(drawdown=0.05)
        artifacts = {
            "fleet_monitor_report": self._make_artifact("fleet_monitor_report"),
            "self_optimizer_proposals": self._make_artifact("self_optimizer_proposals"),
            "self_optimizer_events": self._make_artifact("self_optimizer_events"),
            "primo_signal_state": self._make_artifact("primo_signal_state"),
            "historical_signals": self._make_artifact("historical_signals"),
        }
        containers = {
            "trading-freqtrade-freqforge-1": self._make_container(),
            "trading-freqtrade-freqforge-canary-1": self._make_container("trading-freqtrade-freqforge-canary-1"),
            "trading-freqtrade-regime-hybrid-1": self._make_container("trading-freqtrade-regime-hybrid-1"),
        }
        snapshot = CycleSnapshot(
            ts=datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC),
            state=state, artifacts=artifacts, containers=containers,
        )
        ctx = WatcherContext()
        result = render_cycle(snapshot, ctx)
        assert "CRITICAL" in result or "drawdown" in result

    def test_render_with_open_trades(self) -> None:
        state = self._make_state(open_trades=[{"pair": "BTC/USDT", "direction": "long", "trade_id": 1, "stake": 100.0, "opened_at": "2026-06-22T12:00:00Z"}])
        artifacts = {
            "fleet_monitor_report": self._make_artifact("fleet_monitor_report"),
            "self_optimizer_proposals": self._make_artifact("self_optimizer_proposals"),
            "self_optimizer_events": self._make_artifact("self_optimizer_events"),
            "primo_signal_state": self._make_artifact("primo_signal_state"),
            "historical_signals": self._make_artifact("historical_signals"),
        }
        containers = {
            "trading-freqtrade-freqforge-1": self._make_container(),
            "trading-freqtrade-freqforge-canary-1": self._make_container("trading-freqtrade-freqforge-canary-1"),
            "trading-freqtrade-regime-hybrid-1": self._make_container("trading-freqtrade-regime-hybrid-1"),
        }
        snapshot = CycleSnapshot(
            ts=datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC),
            state=state, artifacts=artifacts, containers=containers,
        )
        ctx = WatcherContext()
        result = render_cycle(snapshot, ctx)
        assert "Open trades:" in result
        assert "BTC/USDT" in result
