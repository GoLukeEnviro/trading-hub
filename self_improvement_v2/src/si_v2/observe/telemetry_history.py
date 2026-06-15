"""SI v2 — Multi-bot telemetry history store for trend-based ShadowProposals.

PURPOSE
  Provide an append-only, versioned, secret-free telemetry history store for
  all four Freqtrade dry-run bots. After each successful SI v2 active cycle,
  the normalized per-bot telemetry is appended as a single grouped JSONL record.
  The history reader and analyzer then compute trend metrics across the last N
  runs, enabling ShadowProposals backed by evidence windows rather than single
  snapshots.

DESIGN DECISIONS
  1. JSONL (append-only, one JSON object per line, no modification).
  2. One record per cycle containing ALL bot snapshots (grouped run).
  3. Date-based file rotation: telemetry_YYYYMMDD.jsonl.
  4. Pydantic v2 strict models with extra="forbid" — no unknown fields.
  5. No secrets, no JWTs, no credential values. Only env-var *names* if any.
  6. Pure I/O with JSON serialization — no network, no env reads.

CONTRACT
  - Schema version: "telemetry_history_v1"
  - Store path: self_improvement_v2/state/telemetry_history/
  - File names: telemetry_YYYYMMDD.jsonl
  - One record per line = one complete SI v2 run with all bots.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "telemetry_history_v1"

DEFAULT_STATE_DIR: Final[str] = "state/telemetry_history"

KNOWN_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)

SENSITIVE_FIELD_NAMES: Final[frozenset[str]] = frozenset({
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "api_key",
    "api_secret",
    "private_key",
    "passphrase",
    "wallet_address",
    "mnemonic",
    "jwt",
    "credential",
})

# ------------------------------------------------------------------
# Pydantic models — strict, no extra fields, no secrets
# ------------------------------------------------------------------


class BotSnapshot(BaseModel):
    """Normalized, secret-free telemetry snapshot for one bot in one cycle.

    All fields are safe to persist. No credential values, no JWTs,
    no raw API responses.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    # Identity
    bot_id: str = Field(min_length=1)

    # Timing
    timestamp_utc: str = Field(min_length=1)

    # Operational status: online | degraded | offline
    status: str = Field(default="unknown", pattern=r"^(online|degraded|offline|unknown)$")

    # --- Core metrics for trend analysis ---
    profit_abs: float | None = None
    profit_ratio: float | None = None
    profit_all_percent: float | None = None
    trade_count: int | None = Field(default=None, ge=0)
    open_trade_count: int | None = Field(default=None, ge=0)

    # Endpoint provenance
    source_endpoint: str = Field(default="/api/v1/profit")
    read_success: bool = False

    # Error metadata (redacted, safe)
    error_redacted: str = Field(default="", max_length=500)

    # --- Extended metrics for richer analysis ---
    count_current: int | None = Field(default=None, ge=0)
    count_max: int | None = Field(default=None, ge=0)
    daily_trade_count_total: int | None = Field(default=None, ge=0)
    daily_abs_profit_sum: float | None = None
    whitelist_pair_count: int | None = Field(default=None, ge=0)
    ping_ok: bool = False
    auth_outcome: str = Field(default="NOT_ATTEMPTED")
    signal_depth: float = Field(default=0.0, ge=0.0, le=1.0)

    @classmethod
    def from_signal_snapshot(
        cls,
        bot_id: str,
        timestamp_utc: str,
        ping_ok: bool,
        auth_outcome: str,
        profit_all_percent: float | None,
        profit_all_ratio: float | None,
        open_trade_count: int | None,
        count_current: int | None,
        count_max: int | None,
        daily_trade_count_total: int | None,
        daily_abs_profit_sum: float | None,
        whitelist_pair_count: int | None,
        signal_depth: float,
        error_redacted: str = "",
    ) -> BotSnapshot:
        """Factory: build from normalized signal data (no raw endpoints)."""
        # Derive status from auth + ping
        if ping_ok and auth_outcome == "AUTHENTICATED":
            status = "online"
        elif ping_ok:
            status = "degraded"
        elif not ping_ok:
            status = "offline"
        else:
            status = "unknown"

        return cls(
            bot_id=bot_id,
            timestamp_utc=timestamp_utc,
            status=status,
            profit_abs=daily_abs_profit_sum,
            profit_ratio=profit_all_ratio,
            profit_all_percent=profit_all_percent,
            trade_count=daily_trade_count_total,
            open_trade_count=open_trade_count,
            source_endpoint="/api/v1/profit",
            read_success=ping_ok and auth_outcome == "AUTHENTICATED",
            error_redacted=error_redacted,
            count_current=count_current,
            count_max=count_max,
            daily_trade_count_total=daily_trade_count_total,
            daily_abs_profit_sum=daily_abs_profit_sum,
            whitelist_pair_count=whitelist_pair_count,
            ping_ok=ping_ok,
            auth_outcome=auth_outcome,
            signal_depth=signal_depth,
        )


class TelemetryHistoryRecord(BaseModel):
    """Complete record for one SI v2 active cycle run (all bots grouped).

    This is the atom unit of the telemetry history store: one JSONL line
    = one run = up to N bot snapshots.

    Schema versioning allows future format migration detection.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    cycle_id: str = Field(min_length=1)
    generated_at_utc: str = Field(min_length=1)
    total_bots: int = Field(ge=0, le=10)
    fleet_verdict: str = Field(default="UNKNOWN", pattern=r"^(GREEN|YELLOW|RED|UNKNOWN)$")
    bots: tuple[BotSnapshot, ...]

    # Accept list from JSON deserialization (Pydantic v2 strict mode rejects
    # list for a tuple field). Pre-processing keeps tuple in Python.
    @field_validator("bots", mode="before")
    @classmethod
    def _coerce_bots_to_tuple(cls, v: object) -> object:
        if isinstance(v, list):
            return tuple(v)
        return v


# Resolve forward reference for BotSnapshot (required with from __future__ import annotations)
TelemetryHistoryRecord.model_rebuild()


# ------------------------------------------------------------------
# Trend analysis models
# ------------------------------------------------------------------


class PerBotTrendSummary(BaseModel):
    """Trend summary for one bot over an evidence window."""

    model_config = ConfigDict(strict=True, extra="forbid")

    bot_id: str
    runs_observed: int
    mean_profit_ratio: float | None = None
    mean_profit_all_percent: float | None = None
    total_trades: int | None = None
    mean_open_trades: float | None = None
    failure_rate: float = 0.0  # 0.0 to 1.0
    latest_status: str = "unknown"
    profit_trend: str = "stable"  # improving | declining | stable | insufficient_data
    ping_ok_rate: float = 0.0
    mean_signal_depth: float = 0.0


class TrendAnalysis(BaseModel):
    """Fleet-wide trend analysis over an evidence window."""

    model_config = ConfigDict(strict=True, extra="forbid")

    runs_observed: int
    window_start_utc: str
    window_end_utc: str
    per_bot: tuple[PerBotTrendSummary, ...]
    strongest_bot: str | None = None
    strongest_bot_reason: str = ""
    weakest_bot: str | None = None
    weakest_bot_reason: str = ""
    fleet_profit_trend: str = "stable"
    fleet_freshness: str = "unknown"  # fresh | stale | unknown
    fleet_mean_failure_rate: float = 0.0


# Resolve forward reference for PerBotTrendSummary
TrendAnalysis.model_rebuild()


class EvidenceWindow(BaseModel):
    """Evidence window metadata for ShadowProposal extension.

    Embedding this in a ShadowProposal allows the reviewer to understand
    how many runs of data informed the proposal.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    runs_observed: int
    window_start_utc: str
    window_end_utc: str
    per_bot_trend_summary: dict[str, dict[str, object]]  # bot_id -> summary dict


# ------------------------------------------------------------------
# Telemetry History Store — append-only JSONL writer
# ------------------------------------------------------------------


class TelemetryHistoryStore:
    """Append-only JSONL store for telemetry history records.

    Usage:
        store = TelemetryHistoryStore()
        record = TelemetryHistoryRecord(...)
        store.append(record)
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        """Initialize store.

        Args:
            state_dir: Directory for JSONL files. Defaults to
                       ``self_improvement_v2/state/telemetry_history/``
                       relative to the repo root.
        """
        if state_dir is None:
            state_dir = self._default_state_dir()
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_state_dir() -> Path:
        """Resolve the default state directory from the repository root."""
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / DEFAULT_STATE_DIR

    def _current_file(self) -> Path:
        """Return the JSONL file path for today's date."""
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        return self._state_dir / f"telemetry_{date_str}.jsonl"

    def append(self, record: TelemetryHistoryRecord) -> Path:
        """Append a record to today's JSONL file.

        Args:
            record: A validated, secret-free TelemetryHistoryRecord.

        Returns:
            The path to the file that was written to.

        Raises:
            ValueError: If the record contains sensitive field names
                        in unexpected places (belt-and-suspenders check).
        """
        # Belt-and-suspenders: verify no sensitive keys in the model dump
        raw = record.model_dump(mode="json")
        self._assert_no_secrets(raw)

        file_path = self._current_file()
        json_line = json.dumps(raw, sort_keys=True, default=str)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json_line + "\n")
        return file_path

    @staticmethod
    def _assert_no_secrets(obj: object, path: str = "") -> None:
        """Recursively check for sensitive field names in a JSON-safe structure.

        This is a belt-and-suspenders safety check. It prevents accidental
        persistence of secret-like keys even if a model field name changes.

        Args:
            obj: The JSON-safe structure to check.
            path: Dot-separated path for error messages (recursion).

        Raises:
            ValueError: If any key matches SENSITIVE_FIELD_NAMES.
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                current = f"{path}.{key}" if path else key
                if isinstance(key, str) and key.lower() in SENSITIVE_FIELD_NAMES:
                    raise ValueError(
                        f"SECRET DETECTED at {current}: key {key!r} matches "
                        f"sensitive field name. This should never appear in "
                        f"telemetry history."
                    )
                TelemetryHistoryStore._assert_no_secrets(value, current)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                TelemetryHistoryStore._assert_no_secrets(item, f"{path}[{i}]")


# ------------------------------------------------------------------
# Telemetry History Reader — safe load of last N runs
# ------------------------------------------------------------------


class TelemetryHistoryReader:
    """Read telemetry history records from JSONL files.

    Safe against:
      - Missing directories
      - Corrupted lines (skipped with logged warning)
      - Partial / incomplete records
      - Schema version mismatch
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        if state_dir is None:
            state_dir = TelemetryHistoryStore._default_state_dir()
        self._state_dir = Path(state_dir)

    def read_all(self) -> list[TelemetryHistoryRecord]:
        """Read ALL records from all telemetry JSONL files.

        Returns:
            Chronologically ordered list of valid records.
        """
        if not self._state_dir.exists():
            return []

        jsonl_files = sorted(self._state_dir.glob("telemetry_*.jsonl"))
        records: list[TelemetryHistoryRecord] = []

        for file_path in jsonl_files:
            records.extend(self._read_file(file_path))

        return records

    def read_last_n(self, n: int = 5) -> list[TelemetryHistoryRecord]:
        """Read the last N valid records across all JSONL files.

        Args:
            n: Maximum number of records to return (most recent first).

        Returns:
            List of up to N valid records, newest first.
        """
        all_records = self.read_all()
        # all_records is chronologically ordered (oldest first)
        return all_records[-n:][::-1]  # newest first

    def count_runs(self) -> int:
        """Return the total number of valid records in the store."""
        return len(self.read_all())

    def _read_file(self, file_path: Path) -> list[TelemetryHistoryRecord]:
        """Read all valid records from a single JSONL file.

        Args:
            file_path: Path to a JSONL file.

        Returns:
            List of valid records, preserving order.
        """
        records: list[TelemetryHistoryRecord] = []
        if not file_path.exists():
            return records

        with open(file_path, encoding="utf-8") as f:
            for _line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue  # skip empty lines
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    # Corrupted line — skip (would log in production)
                    continue

                try:
                    record = TelemetryHistoryRecord(**parsed)
                except (ValueError, TypeError, RuntimeError):
                    # Schema mismatch or incomplete record — skip
                    continue

                # Schema version check: skip incompatible records
                if record.schema_version != SCHEMA_VERSION:
                    continue

                records.append(record)

        return records


# ------------------------------------------------------------------
# Telemetry History Analyzer — trend computation
# ------------------------------------------------------------------


class TelemetryHistoryAnalyzer:
    """Compute trend summaries over a window of telemetry history runs.

    Usage:
        analyzer = TelemetryHistoryAnalyzer()
        trend = analyzer.analyze_window(n=5)
        print(trend.weakest_bot, trend.strongest_bot)
    """

    def __init__(self, reader: TelemetryHistoryReader | None = None) -> None:
        self._reader = reader or TelemetryHistoryReader()

    def analyze_window(self, n: int = 5) -> TrendAnalysis:
        """Analyze the last N runs and produce a trend analysis.

        Args:
            n: Number of recent runs to include in the window.

        Returns:
            A TrendAnalysis with per-bot summaries, strongest/weakest
            bot identification, and fleet-level metrics.
        """
        records = self._reader.read_last_n(n)

        if not records:
            return TrendAnalysis(
                runs_observed=0,
                window_start_utc="",
                window_end_utc="",
                per_bot=(),
                fleet_profit_trend="insufficient_data",
            )

        # Chronological order for trend computation (read_last_n returns newest-first)
        records = list(reversed(records))
        window_start = records[0].generated_at_utc  # oldest in window
        window_end = records[-1].generated_at_utc  # newest in window

        # Build per-bot aggregators across all runs
        bot_data: dict[str, _BotAggregator] = {
            bid: _BotAggregator(bid) for bid in KNOWN_BOT_IDS
        }

        for record in records:
            for bot_snap in record.bots:
                bid = bot_snap.bot_id
                if bid not in bot_data:
                    bot_data[bid] = _BotAggregator(bid)
                agg = bot_data[bid]
                agg.add_snapshot(bot_snap)

        # Build per-bot trend summaries
        per_bot_summaries: list[PerBotTrendSummary] = []
        for bid in KNOWN_BOT_IDS:
            agg = bot_data.get(bid)
            if agg is None or agg.count == 0:
                per_bot_summaries.append(
                    PerBotTrendSummary(
                        bot_id=bid,
                        runs_observed=0,
                        failure_rate=0.0,
                        profit_trend="insufficient_data",
                    )
                )
            else:
                per_bot_summaries.append(agg.to_summary())

        # Identify strongest and weakest bots by mean profit ratio
        strongest_bot: str | None = None
        strongest_reason = ""
        weakest_bot: str | None = None
        weakest_reason = ""

        bots_with_profit = [
            s for s in per_bot_summaries
            if s.runs_observed > 0 and s.mean_profit_ratio is not None
        ]

        if len(bots_with_profit) >= 2:
            sorted_by_profit = sorted(
                bots_with_profit,
                key=lambda s: s.mean_profit_ratio if s.mean_profit_ratio is not None else 0.0,
            )
            weakest = sorted_by_profit[0]
            strongest = sorted_by_profit[-1]

            if strongest.mean_profit_ratio is not None:
                strongest_bot = strongest.bot_id
                strongest_reason = (
                    f"Highest mean profit ratio: {strongest.mean_profit_ratio:.6f} "
                    f"over {strongest.runs_observed} runs, "
                    f"failure_rate={strongest.failure_rate:.2f}"
                )

            if weakest.mean_profit_ratio is not None:
                weakest_bot = weakest.bot_id
                mean_all = sum(
                    s.mean_profit_ratio for s in bots_with_profit
                    if s.mean_profit_ratio is not None
                ) / len(bots_with_profit)
                weakest_reason = (
                    f"Lowest mean profit ratio: {weakest.mean_profit_ratio:.6f} "
                    f"(fleet avg: {mean_all:.6f}), "
                    f"failure_rate={weakest.failure_rate:.2f}"
                )

        # Fleet-level metrics
        failure_rates = [s.failure_rate for s in per_bot_summaries if s.runs_observed > 0]
        fleet_mean_failure = sum(failure_rates) / len(failure_rates) if failure_rates else 0.0

        # Check freshness: is the most recent record within the last 24h?
        fleet_freshness = "unknown"
        if records:
            try:
                last_ts = datetime.fromisoformat(records[-1].generated_at_utc)
                now = datetime.now(UTC)
                hours_ago = (now - last_ts).total_seconds() / 3600
                fleet_freshness = "fresh" if hours_ago < 24 else "stale"
            except (ValueError, TypeError):
                fleet_freshness = "unknown"

        return TrendAnalysis(
            runs_observed=len(records),
            window_start_utc=window_start,
            window_end_utc=window_end,
            per_bot=tuple(per_bot_summaries),
            strongest_bot=strongest_bot,
            strongest_bot_reason=strongest_reason,
            weakest_bot=weakest_bot,
            weakest_bot_reason=weakest_reason,
            fleet_profit_trend=_compute_fleet_profit_trend(per_bot_summaries),
            fleet_freshness=fleet_freshness,
            fleet_mean_failure_rate=round(fleet_mean_failure, 4),
        )

    def build_evidence_window(self, n: int = 5) -> EvidenceWindow:
        """Build an EvidenceWindow for embedding in a ShadowProposal.

        Args:
            n: Number of recent runs to include.

        Returns:
            An EvidenceWindow with serializable per-bot trend summaries.
        """
        trend = self.analyze_window(n)

        per_bot_dict: dict[str, dict[str, object]] = {}
        for s in trend.per_bot:
            per_bot_dict[s.bot_id] = {
                "runs_observed": s.runs_observed,
                "mean_profit_ratio": s.mean_profit_ratio,
                "mean_profit_all_percent": s.mean_profit_all_percent,
                "total_trades": s.total_trades,
                "failure_rate": s.failure_rate,
                "latest_status": s.latest_status,
                "profit_trend": s.profit_trend,
                "ping_ok_rate": s.ping_ok_rate,
                "mean_signal_depth": s.mean_signal_depth,
            }

        return EvidenceWindow(
            runs_observed=trend.runs_observed,
            window_start_utc=trend.window_start_utc,
            window_end_utc=trend.window_end_utc,
            per_bot_trend_summary=per_bot_dict,
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


class _BotAggregator:
    """Internal per-bot trend aggregator across multiple runs."""

    __slots__ = (
        "bot_id", "count", "failures", "latest_status",
        "open_trades", "ping_oks", "profit_pcts", "profit_ratios",
        "signal_depths", "timestamps", "trades",
    )

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self.count: int = 0
        self.profit_ratios: list[float] = []
        self.profit_pcts: list[float] = []
        self.trades: list[int] = []
        self.open_trades: list[int] = []
        self.failures: int = 0
        self.ping_oks: int = 0
        self.signal_depths: list[float] = []
        self.latest_status: str = "unknown"
        self.timestamps: list[str] = []

    def add_snapshot(self, snap: BotSnapshot) -> None:
        """Accumulate one bot snapshot into this aggregator."""
        self.count += 1
        self.timestamps.append(snap.timestamp_utc)
        self.latest_status = snap.status

        if snap.profit_ratio is not None:
            self.profit_ratios.append(snap.profit_ratio)
        if snap.profit_all_percent is not None:
            self.profit_pcts.append(snap.profit_all_percent)
        if snap.trade_count is not None:
            self.trades.append(snap.trade_count)
        if snap.open_trade_count is not None:
            self.open_trades.append(snap.open_trade_count)
        if snap.ping_ok:
            self.ping_oks += 1
        if not snap.read_success:
            self.failures += 1
        self.signal_depths.append(snap.signal_depth)

    def to_summary(self) -> PerBotTrendSummary:
        """Derive a PerBotTrendSummary from accumulated data."""
        if self.count == 0:
            return PerBotTrendSummary(
                bot_id=self.bot_id,
                runs_observed=0,
                profit_trend="insufficient_data",
            )

        mean_profit_ratio = (
            round(sum(self.profit_ratios) / len(self.profit_ratios), 6)
            if self.profit_ratios else None
        )
        mean_profit_pct = (
            round(sum(self.profit_pcts) / len(self.profit_pcts), 4)
            if self.profit_pcts else None
        )
        total_trades = sum(self.trades) if self.trades else None
        mean_open = (
            round(sum(self.open_trades) / len(self.open_trades), 2)
            if self.open_trades else None
        )
        failure_rate = round(self.failures / self.count, 4)
        ping_ok_rate = round(self.ping_oks / self.count, 4)
        mean_sd = round(sum(self.signal_depths) / len(self.signal_depths), 4)

        # Profit trend: compare first half to second half
        profit_trend = _compute_trend(self.profit_pcts)

        return PerBotTrendSummary(
            bot_id=self.bot_id,
            runs_observed=self.count,
            mean_profit_ratio=mean_profit_ratio,
            mean_profit_all_percent=mean_profit_pct,
            total_trades=total_trades,
            mean_open_trades=mean_open,
            failure_rate=failure_rate,
            latest_status=self.latest_status,
            profit_trend=profit_trend,
            ping_ok_rate=ping_ok_rate,
            mean_signal_depth=mean_sd,
        )


def _compute_trend(values: list[float]) -> str:
    """Compute trend direction from a time-ordered list of values.

    Args:
        values: Chronological list of numeric values.

    Returns:
        "improving", "declining", "stable", or "insufficient_data".
    """
    if len(values) < 3:
        return "insufficient_data"

    midpoint = len(values) // 2
    first_half = values[:midpoint]
    second_half = values[midpoint:]

    mean_first = sum(first_half) / len(first_half)
    mean_second = sum(second_half) / len(second_half)

    # Threshold: at least 5% relative change
    if mean_first == 0:
        return "stable" if abs(mean_second) < 0.001 else ("improving" if mean_second > 0 else "declining")

    relative_change = (mean_second - mean_first) / abs(mean_first)
    if relative_change > 0.05:
        return "improving"
    if relative_change < -0.05:
        return "declining"
    return "stable"


def _compute_fleet_profit_trend(summaries: list[PerBotTrendSummary]) -> str:
    """Aggregate per-bot trends into a fleet profit trend."""
    trends = [s.profit_trend for s in summaries if s.runs_observed > 0]
    if not trends:
        return "insufficient_data"

    # If all trends are insufficient_data, fleet trend is also insufficient_data
    if all(t == "insufficient_data" for t in trends):
        return "insufficient_data"

    improving = sum(1 for t in trends if t == "improving")
    declining = sum(1 for t in trends if t == "declining")

    if improving > declining:
        return "improving"
    if declining > improving:
        return "declining"
    return "stable"


# ------------------------------------------------------------------
# Convenience: build a TelemetryHistoryRecord from BotSignalSnapshots
# ------------------------------------------------------------------

# Late import to avoid circular dependency at module level
_imports_loaded = False


def build_record_from_snapshots(
    cycle_id: str,
    fleet_verdict: str,
    snapshots: list,
    fetched_at_utc: str | None = None,
) -> TelemetryHistoryRecord:
    """Build a TelemetryHistoryRecord from a list of BotSignalSnapshot objects.

    Args:
        cycle_id: The SI v2 cycle identifier.
        fleet_verdict: Fleet verdict string (GREEN/YELLOW/RED).
        snapshots: List of BotSignalSnapshot objects (duck-typed).
        fetched_at_utc: Override timestamp. Defaults to current UTC time.

    Returns:
        A validated TelemetryHistoryRecord ready for append().
    """
    from si_v2.signals.models import BotSignalSnapshot as _BotSignalSnapshot

    ts = fetched_at_utc or datetime.now(UTC).isoformat()
    bot_snapshots: list[BotSnapshot] = []

    for snap in snapshots:
        if not isinstance(snap, _BotSignalSnapshot):
            # Duck-type for test compatibility
            bid = getattr(snap, "bot_id", "unknown")
            error = f"Invalid snapshot type: {type(snap).__name__}"
            bot_snapshots.append(
                BotSnapshot(
                    bot_id=bid,
                    timestamp_utc=ts,
                    status="unknown",
                    read_success=False,
                    error_redacted=error,
                    source_endpoint="n/a",
                )
            )
            continue

        bot_snapshots.append(
            BotSnapshot.from_signal_snapshot(
                bot_id=snap.bot_id,
                timestamp_utc=ts,
                ping_ok=snap.ping_ok,
                auth_outcome=snap.auth_outcome,
                profit_all_percent=snap.profit_all_percent,
                profit_all_ratio=snap.profit_all_ratio,
                open_trade_count=snap.status_open_trades,
                count_current=snap.count_current,
                count_max=snap.count_max,
                daily_trade_count_total=snap.daily_trade_count_total,
                daily_abs_profit_sum=snap.daily_abs_profit_sum,
                whitelist_pair_count=snap.whitelist_pair_count,
                signal_depth=snap.signal_depth,
            )
        )

    return TelemetryHistoryRecord(
        cycle_id=cycle_id,
        generated_at_utc=ts,
        total_bots=len(bot_snapshots),
        fleet_verdict=fleet_verdict,
        bots=tuple(bot_snapshots),
    )
