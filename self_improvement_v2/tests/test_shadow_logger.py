"""Unit tests for ShadowLogger with file persistence and in-memory mode."""

from __future__ import annotations

from pathlib import Path

from si_v2.deploy.shadow_logger import ShadowLogger


class TestShadowLoggerInMemory:
    """Tests for ShadowLogger in-memory mode (log_dir=None)."""

    def test_log_stores_in_memory(self) -> None:
        """Entries should be stored in memory when log_dir is None."""
        logger = ShadowLogger(log_dir=None)
        logger.log(
            bot_id="bot_a",
            candidate_sha="abc123",
            params={"stoploss_pct": -0.02},
            outcome="pass",
            phase="backtest",
            decision="pass",
            reason="criteria met",
        )

        entries = logger.get_entries("bot_a")
        assert len(entries) == 1
        assert entries[0]["bot_id"] == "bot_a"
        assert entries[0]["candidate_sha"] == "abc123"
        assert entries[0]["phase"] == "backtest"
        assert entries[0]["decision"] == "pass"

    def test_multiple_entries_same_bot(self) -> None:
        """Multiple entries for the same bot should accumulate."""
        logger = ShadowLogger(log_dir=None)
        logger.log("bot_a", "sha1", {"rsi_period": 14}, None, "observe", "hold", "no data")
        logger.log("bot_a", "sha2", {"rsi_period": 15}, None, "analyze", "mutate", "negative pnl")

        entries = logger.get_entries("bot_a")
        assert len(entries) == 2
        assert entries[0]["candidate_sha"] == "sha1"
        assert entries[1]["candidate_sha"] == "sha2"

    def test_entries_isolated_per_bot(self) -> None:
        """Entries for different bots should be isolated."""
        logger = ShadowLogger(log_dir=None)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "reason1")
        logger.log("bot_b", "sha2", {}, None, "observe", "hold", "reason2")

        assert len(logger.get_entries("bot_a")) == 1
        assert len(logger.get_entries("bot_b")) == 1

    def test_empty_entries_for_unknown_bot(self) -> None:
        """Requesting entries for an unknown bot should return empty list."""
        logger = ShadowLogger(log_dir=None)
        entries = logger.get_entries("unknown")
        assert entries == []

    def test_entry_has_timestamp(self) -> None:
        """Each entry should have a timestamp_utc field."""
        logger = ShadowLogger(log_dir=None)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "reason")

        entries = logger.get_entries("bot_a")
        assert "timestamp_utc" in entries[0]
        assert isinstance(entries[0]["timestamp_utc"], str)

    def test_get_entries_returns_copy(self) -> None:
        """get_entries should return a copy, not the internal list."""
        logger = ShadowLogger(log_dir=None)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "reason")

        entries1 = logger.get_entries("bot_a")
        entries2 = logger.get_entries("bot_a")
        assert entries1 is not entries2
        assert entries1 == entries2


class TestShadowLoggerFilePersistence:
    """Tests for ShadowLogger file persistence mode."""

    def test_writes_to_jsonl_file(self, tmp_path: Path) -> None:
        """Entries should be appended to the JSONL file."""
        logger = ShadowLogger(log_dir=tmp_path)
        logger.log(
            bot_id="bot_a",
            candidate_sha="abc123",
            params={"stoploss_pct": -0.02},
            outcome="pass",
            phase="backtest",
            decision="pass",
            reason="criteria met",
        )

        log_file = tmp_path / "shadow_bot_a.jsonl"
        assert log_file.exists()

        entries = logger.get_entries("bot_a")
        assert len(entries) == 1
        assert entries[0]["bot_id"] == "bot_a"

    def test_append_does_not_overwrite(self, tmp_path: Path) -> None:
        """Multiple log calls should append, not overwrite."""
        logger = ShadowLogger(log_dir=tmp_path)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "r1")
        logger.log("bot_a", "sha2", {}, None, "analyze", "mutate", "r2")

        entries = logger.get_entries("bot_a")
        assert len(entries) == 2

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Should create log_dir if it doesn't exist."""
        nested_dir = tmp_path / "logs" / "shadow"
        logger = ShadowLogger(log_dir=nested_dir)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "reason")

        assert nested_dir.exists()
        entries = logger.get_entries("bot_a")
        assert len(entries) == 1

    def test_separate_files_per_bot(self, tmp_path: Path) -> None:
        """Each bot should have its own JSONL file."""
        logger = ShadowLogger(log_dir=tmp_path)
        logger.log("bot_a", "sha1", {}, None, "observe", "hold", "r1")
        logger.log("bot_b", "sha2", {}, None, "observe", "hold", "r2")

        assert (tmp_path / "shadow_bot_a.jsonl").exists()
        assert (tmp_path / "shadow_bot_b.jsonl").exists()

        assert len(logger.get_entries("bot_a")) == 1
        assert len(logger.get_entries("bot_b")) == 1

    def test_read_nonexistent_bot_returns_empty(self, tmp_path: Path) -> None:
        """Reading entries for a bot with no log file should return empty list."""
        logger = ShadowLogger(log_dir=tmp_path)
        entries = logger.get_entries("nonexistent")
        assert entries == []

    def test_entry_format(self, tmp_path: Path) -> None:
        """Each entry should have the correct JSON structure."""
        logger = ShadowLogger(log_dir=tmp_path)
        logger.log(
            bot_id="bot_a",
            candidate_sha="sha1",
            params={"stoploss_pct": -0.02, "rsi_period": 14},
            outcome="tested",
            phase="propose",
            decision="mutate",
            reason="negative pnl",
        )

        entries = logger.get_entries("bot_a")
        entry = entries[0]
        assert set(entry.keys()) == {
            "timestamp_utc",
            "bot_id",
            "candidate_sha",
            "params",
            "outcome",
            "phase",
            "decision",
            "reason",
        }
