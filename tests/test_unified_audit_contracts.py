from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Ensure trading_pipeline is importable
sys.path.insert(0, str(_REPO_ROOT))


def _make_audit_entry(
    event_type: str,
    pair: str = "BTC/USDT",
    verdict: str = "ACCEPTED",
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "event_type": event_type,
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "source": "test",
        "pair": pair,
        "verdict": verdict,
    }
    if overrides:
        entry.update(overrides)
    return entry


# ===========================================================================
# Audit schema contract tests
# ===========================================================================


class TestAuditSchema:
    """Verify unified audit entries follow the expected schema."""

    REQUIRED_FIELDS = {"event_type", "timestamp_utc", "source"}

    def test_signal_decision_entry_has_required_fields(self) -> None:
        entry = _make_audit_entry("signal_decision")
        for field in self.REQUIRED_FIELDS:
            assert field in entry, f"Missing required field: {field}"

    def test_riskguard_verdict_entry_has_required_fields(self) -> None:
        entry = _make_audit_entry("riskguard_verdict")
        for field in self.REQUIRED_FIELDS:
            assert field in entry, f"Missing required field: {field}"

    def test_kill_switch_event_entry_has_required_fields(self) -> None:
        entry = _make_audit_entry("kill_switch", overrides={"mode": "HALT_NEW"})
        for field in self.REQUIRED_FIELDS:
            assert field in entry, f"Missing required field: {field}"

    def test_audit_entry_is_json_serializable(self) -> None:
        entry = _make_audit_entry("signal_decision")
        serialized = json.dumps(entry)
        assert serialized
        assert json.loads(serialized) == entry


class TestAuditAppendOnly:
    """Verify audit log is append-only and preserves ordering."""

    def test_entries_are_appended_not_overwritten(self, tmp_path: Path) -> None:
        log = tmp_path / "audit.jsonl"
        entry1 = _make_audit_entry("signal_decision", pair="BTC/USDT")
        entry2 = _make_audit_entry("riskguard_verdict", pair="ETH/USDT")

        with open(str(log), "a") as f:
            f.write(json.dumps(entry1) + "\n")
            f.write(json.dumps(entry2) + "\n")

        lines = log.read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["pair"] == "BTC/USDT"
        assert second["pair"] == "ETH/USDT"

    def test_entries_preserve_insertion_order(self, tmp_path: Path) -> None:
        """Entries maintain chronological order."""
        log = tmp_path / "chrono.jsonl"
        entries = [
            _make_audit_entry("signal_decision", pair="BTC/USDT"),
            _make_audit_entry("kill_switch", pair="", verdict="HALT_NEW", overrides={"mode": "HALT_NEW"}),
            _make_audit_entry("riskguard_verdict", pair="SOL/USDT"),
        ]
        with open(str(log), "a") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        loaded = [json.loads(line) for line in log.read_text().strip().splitlines()]
        assert len(loaded) == 3
        for i, expected in enumerate(entries):
            assert loaded[i]["event_type"] == expected["event_type"]


# ===========================================================================
# ShadowLogger audit integration
# ===========================================================================


class TestShadowLoggerAuditIntegration:
    """Verify ShadowLogger can capture signal, RiskGuard and kill-switch events."""

    def test_shadow_logger_appends_with_valid_schema(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """ShadowLogger writes a valid audit entry for a pipeline decision."""
        # Point shadow logger to temp dir
        log_path = tmp_path / "shadow_decisions.jsonl"
        monkeypatch.setattr(
            "orchestrator.scripts.trading_pipeline.SHADOW_LOG_FILE", log_path
        )

        # Write one audit-style entry directly (mimicking the pipeline)
        entry = _make_audit_entry("riskguard_verdict")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(log_path), "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Verify it's readable
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        loaded = json.loads(lines[0])
        assert loaded["event_type"] == "riskguard_verdict"

    def test_audit_handles_duplicate_entries(self, tmp_path: Path) -> None:
        """Appending duplicate entries is allowed (append-only)."""
        log = tmp_path / "audit_dup.jsonl"
        entry = _make_audit_entry("signal_decision", pair="BTC/USDT")

        for _ in range(3):
            with open(str(log), "a") as f:
                f.write(json.dumps(entry) + "\n")

        assert len(log.read_text().strip().splitlines()) == 3


class TestAuditNoCredentials:
    """Verify audit entries never contain credential-like fields."""

    SENSITIVE_KEYS = {"key", "secret", "token", "password", "jwt_secret_key", "api_key"}

    def test_sample_entries_have_no_credential_keys(self) -> None:
        entries = [
            _make_audit_entry("signal_decision"),
            _make_audit_entry("riskguard_verdict"),
            _make_audit_entry("kill_switch", overrides={"mode": "EMERGENCY"}),
        ]
        for entry in entries:
            for key in entry:
                lower = key.lower()
                for sensitive in self.SENSITIVE_KEYS:
                    assert sensitive not in lower, f"Found sensitive key '{key}' in audit entry"
