"""Historical signal loader for research strategies.

The loader reads JSONL records produced by signal_archiver.py and returns the last
known pair signal at or before a requested candle timestamp.
"""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def normalize_pair(pair: str | None) -> str:
    """Normalize Freqtrade futures pairs like BTC/USDT:USDT -> BTC/USDT."""
    if not pair:
        return ""
    value = str(pair).strip().upper()
    if ":" in value:
        value = value.split(":", 1)[0]
    return value


def parse_timestamp(value: str | datetime) -> datetime:
    """Parse ISO timestamp and return timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class HistoricalSignalRecord:
    timestamp_utc: datetime
    data: dict[str, Any]


class HistoricalSignalLoader:
    """Load archived signal states and query pair signal by timestamp.

    Example in a strategy:
        from signal_loader import HistoricalSignalLoader
        loader = HistoricalSignalLoader('/freqtrade/user_data/signals/historical_signals.jsonl')
        signal = loader.get_signal_at(metadata['pair'], dataframe.iloc[-1]['date'].to_pydatetime())
    """

    def __init__(self, archive_path: str | Path, *, strict: bool = False) -> None:
        self.archive_path = Path(archive_path)
        self.strict = strict
        self.records: list[HistoricalSignalRecord] = []
        self.timestamps: list[datetime] = []
        self._load()

    def _iter_records(self) -> Iterable[HistoricalSignalRecord]:
        if not self.archive_path.exists():
            if self.strict:
                raise FileNotFoundError(f"Signal archive not found: {self.archive_path}")
            return

        with self.archive_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = parse_timestamp(rec["timestamp_utc"])
                    data = rec.get("data")
                    if not isinstance(data, dict):
                        continue
                    yield HistoricalSignalRecord(timestamp_utc=ts, data=data)
                except Exception as exc:
                    if self.strict:
                        raise ValueError(f"Invalid archive line {line_no} in {self.archive_path}: {exc}") from exc
                    continue

    def _load(self) -> None:
        self.records = sorted(self._iter_records(), key=lambda item: item.timestamp_utc)
        self.timestamps = [item.timestamp_utc for item in self.records]

    def reload(self) -> None:
        """Reload the JSONL archive from disk."""
        self._load()

    def get_state_at(self, timestamp: datetime) -> dict[str, Any]:
        """Return the last known full signal state at or before timestamp."""
        if not self.records:
            return {}
        ts = parse_timestamp(timestamp)
        idx = bisect.bisect_right(self.timestamps, ts) - 1
        if idx < 0:
            return {}
        return self.records[idx].data

    def get_signal_at(self, pair: str, timestamp: datetime) -> dict[str, Any]:
        """Return the last known signal for pair at or before timestamp.

        Supports both raw futures keys (BTC/USDT:USDT) and normalized keys (BTC/USDT).
        Returns {} when no archive state exists, no pair entry exists, or timestamp is
        earlier than the first archived record.
        """
        state = self.get_state_at(timestamp)
        pairs = state.get("pairs") if isinstance(state.get("pairs"), dict) else {}
        if not pairs:
            return {}

        raw = str(pair or "").strip().upper()
        norm = normalize_pair(raw)
        signal = pairs.get(raw) or pairs.get(norm)
        if isinstance(signal, dict):
            return dict(signal)
        return {}

    def __len__(self) -> int:
        return len(self.records)
