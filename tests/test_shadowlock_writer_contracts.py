from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import shadowlock.shadowlock_writer as writer


BOT = "alpha-bot"
SCHEMA_VERSION = writer.SCHEMA_VERSION


def _base_dir(tmp_path: Path) -> Path:
    base = tmp_path / "shadowlock"
    for sub in writer.REQUIRED_SUBDIRS:
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def _entry(ts: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "event_type": "default",
        "timestamp_utc": ts,
        "bot_name": BOT,
    }
    if payload:
        data.update(payload)
    return data


def _inbox_path(base: Path, name: str) -> Path:
    return base / "inbox" / name


class TestShadowlockWriterContracts:
    def test_compute_entry_sha256_is_canonical(self) -> None:
        first = {
            "schema_version": SCHEMA_VERSION,
            "event_type": "default",
            "timestamp_utc": "2026-06-15T00:00:00Z",
            "bot_name": BOT,
            "z": 3,
            "a": 1,
        }
        second = {
            "bot_name": BOT,
            "timestamp_utc": "2026-06-15T00:00:00Z",
            "event_type": "default",
            "schema_version": SCHEMA_VERSION,
            "a": 1,
            "z": 3,
        }
        hashed_1, sha_1 = writer.compute_entry_sha256(first)
        hashed_2, sha_2 = writer.compute_entry_sha256(second)
        assert sha_1 == sha_2
        assert hashed_1["entry_sha256"] == sha_1
        assert hashed_2["entry_sha256"] == sha_2
        assert hashed_1["entry_sha256"] != ""

    def test_validate_entry_rejects_missing_fields_and_bad_timestamp(self) -> None:
        valid, reason = writer.validate_entry(_entry("2026-06-15T00:00:00Z"))
        assert valid is True
        assert reason is None

        valid, reason = writer.validate_entry({"schema_version": SCHEMA_VERSION})
        assert valid is False
        assert "missing required fields" in str(reason)

        valid, reason = writer.validate_entry(_entry("2026-06-15 00:00:00"))
        assert valid is False
        assert "timestamp_utc" in str(reason)

    def test_process_inbox_file_appends_and_sequences(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _base_dir(tmp_path)
        monkeypatch.setattr(writer, "_trigger_indexer", lambda: None)

        ts = "2026-06-15T12:00:00Z"
        payload_1 = {"payload": {"b": 2, "a": 1}}
        payload_2 = {"payload": {"c": 3}}

        inbox_1 = _inbox_path(base, "one.json")
        inbox_1.write_text(json.dumps(_entry(ts, payload_1)))
        inbox_2 = _inbox_path(base, "two.json")
        inbox_2.write_text(json.dumps(_entry(ts, payload_2)))

        assert writer.process_inbox_file(str(base), str(inbox_1)) is True
        assert writer.process_inbox_file(str(base), str(inbox_2)) is True

        log_file = base / "logs" / "2026" / "06" / "15.jsonl"
        assert log_file.exists()
        lines = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        assert [line["sequence_number"] for line in lines] == [1, 2]
        assert writer.read_sequence(str(base), BOT) == 2

        first_hash, _ = writer.compute_entry_sha256(_entry(ts, payload_1))
        second_hash, _ = writer.compute_entry_sha256(_entry(ts, payload_2))
        assert lines[0]["entry_sha256"] == first_hash["entry_sha256"]
        assert lines[1]["entry_sha256"] == second_hash["entry_sha256"]
        today = dt.date.today().strftime("%Y-%m-%d")
        assert (base / "processed" / f"{today}-one.json").exists()
        assert (base / "processed" / f"{today}-two.json").exists()

    def test_process_inbox_file_quarantines_invalid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _base_dir(tmp_path)
        monkeypatch.setattr(writer, "_trigger_indexer", lambda: None)

        inbox = _inbox_path(base, "bad.json")
        inbox.write_text("{not-json")

        assert writer.process_inbox_file(str(base), str(inbox)) is False
        quarantine = base / "quarantine"
        assert any(quarantine.iterdir())
        assert not inbox.exists()

    def test_process_inbox_file_dead_letters_on_write_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _base_dir(tmp_path)
        monkeypatch.setattr(writer, "write_with_retry", lambda *args, **kwargs: False)

        inbox = _inbox_path(base, "dead.json")
        inbox.write_text(json.dumps(_entry("2026-06-15T12:00:00Z", {"payload": 1})))

        assert writer.process_inbox_file(str(base), str(inbox)) is False
        assert any((base / "dead-letter").iterdir())
        assert not inbox.exists()

    def test_process_inbox_file_missing_source_is_safe(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _base_dir(tmp_path)
        monkeypatch.setattr(writer, "_trigger_indexer", lambda: None)
        missing = _inbox_path(base, "missing.json")

        assert writer.process_inbox_file(str(base), str(missing)) is False
