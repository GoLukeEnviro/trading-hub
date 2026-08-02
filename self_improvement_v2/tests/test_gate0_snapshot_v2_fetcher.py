"""Tests for the Gate-0 snapshot v2 fetcher (#693).

No real network access. All HTTP is scripted through the ``http_get``
injection point. Coverage per the #693 implementation contract:

- Pagination and deduplication (candles + funding)
- Rate-limit / retry behaviour
- Funding pagination (``idLessThan`` backward cursor)
- Window boundaries (half-open ``[start, end)``)
- 1h determinism (byte-identical second run)
- Gap / duplicate detection
- Holdout isolation (selection never sees holdout)
- Path traversal defence
- Atomic write / partial-failure behaviour
- Hash / seal reproducibility
- Marker expiry and missing marker
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from si_v2.research.gate0_snapshot_v2_fetcher import (
    DATASET_END,
    HOLDOUT_START,
    PAIR_TO_LABEL,
    PAIR_TO_SYMBOL,
    PAIRS,
    WARMUP_START,
    A2MarkerError,
    PathEscapeError,
    SnapshotFetchError,
    build_snapshot_v2,
    confine_path,
    dedup_and_sort_funding,
    derive_1h_candles,
    expected_15m_count,
    fetch_history_funding,
    normalize_funding_row,
    run_funding_quality_checks,
    run_quality_checks,
    validate_a2_marker,
    verify_holdout_seal,
    write_gz_csv_atomic,
)

VALID_MARKER = {
    "name": "APPROVED_A2_BITGET_SNAPSHOT_V2",
    "issued_by": "Luke",
    "host": "HermesTrader",
    "execution_class": "A2",
    "purpose": "Fetch and freeze immutable Bitget snapshot v2",
    "approval_scope": "ISSUE_693_ONLY",
    "live_trading": "PROHIBITED",
    "dry_run_false": "PROHIBITED",
    "valid_until": "2026-08-03T20:31:46Z",
    "comment_id": "5160213406",
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _ts_15m(minute: int) -> str:
    """Millisecond timestamp for WARMUP_START + minute*15m."""
    base = int(WARMUP_START.timestamp() * 1000)
    return str(base + minute * 15 * 60 * 1000)


def _raw_candle(minute: int, symbol: str = "BTCUSDT", o: float = 100.0) -> list[str]:
    return [
        _ts_15m(minute),
        str(o),
        str(o + 1.0),
        str(o - 1.0),
        str(o + 0.5),
        str(10.0),
    ]


def _funding_row(symbol: str, minute: int, rate: float = 0.0001) -> dict[str, str]:
    return {
        "symbol": symbol,
        "fundingRate": str(rate),
        "fundingTime": _ts_15m(minute),
    }


def _candles_for_pair(
    symbol: str, n_minutes: int, start_minute: int = 0, step: int = 1
) -> list[list[str]]:
    return [
        _raw_candle(start_minute + i * step, symbol=symbol, o=100.0 + i * 0.01)
        for i in range(n_minutes)
    ]


def _funding_for_pair(symbol: str, n: int, start_minute: int = 0, step: int = 32) -> list[dict[str, str]]:
    """Funding events every ``step`` 15m-slots (default 8h cadence)."""
    return [_funding_row(symbol, start_minute + i * step) for i in range(n)]


class ScriptedHttpGet:
    """Scripted public-API mock: candles + funding by symbol, optional failures."""

    def __init__(
        self,
        candles: dict[str, list[list[str]]] | None = None,
        funding: dict[str, list[dict[str, str]]] | None = None,
        *,
        fail_funding_symbols: set[str] | None = None,
        fail_candle_symbols: set[str] | None = None,
    ) -> None:
        self.candles = candles or {}
        self.funding = funding or {}
        self.fail_funding_symbols = fail_funding_symbols or set()
        self.fail_candle_symbols = fail_candle_symbols or set()
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str], headers: dict[str, str]) -> tuple[int, str]:
        self.calls.append((url, dict(params)))
        if url.endswith("history-candles"):
            symbol = params["symbol"]
            if symbol in self.fail_candle_symbols:
                return 500, "{\"code\":\"50000\",\"msg\":\"boom\"}"
            end_ms = int(params["endTime"])
            limit = int(params["limit"])
            rows = self.candles[symbol]
            page = [r for r in rows if int(r[0]) < end_ms][-limit:]
            return 200, json.dumps({"code": "00000", "data": page})
        if url.endswith("history-fund-rate"):
            symbol = params["symbol"]
            if symbol in self.fail_funding_symbols:
                return 500, "{\"code\":\"50000\",\"msg\":\"boom\"}"
            id_less = int(params.get("idLessThan", str(2**63 - 1)))
            rows = self.funding[symbol]
            page = [r for r in rows if int(r["fundingTime"]) < id_less][-100:]
            return 200, json.dumps({"code": "00000", "data": page})
        raise AssertionError(f"unexpected URL: {url}")


def _full_candle_dataset() -> dict[str, list[list[str]]]:
    """Full 19-month 15m dataset per pair (deterministic synthetic candles)."""
    total_slots = int((DATASET_END - WARMUP_START).total_seconds() // 900)
    result: dict[str, list[list[str]]] = {}
    for pair in PAIRS:
        symbol = PAIR_TO_SYMBOL[pair]
        result[symbol] = _candles_for_pair(symbol, total_slots)
    return result


def _full_funding_dataset() -> dict[str, list[dict[str, str]]]:
    total_slots = int((DATASET_END - WARMUP_START).total_seconds() // 900)
    result: dict[str, list[dict[str, str]]] = {}
    for pair in PAIRS:
        symbol = PAIR_TO_SYMBOL[pair]
        result[symbol] = _funding_for_pair(symbol, total_slots // 32)
    return result


# ---------------------------------------------------------------------------
# Marker validation (fail-closed)
# ---------------------------------------------------------------------------


class TestValidateA2Marker:
    def test_missing_marker(self):
        with pytest.raises(A2MarkerError) as exc:
            validate_a2_marker(None)
        assert exc.value.code == "MISSING_MARKER"

    def test_missing_required_field(self):
        bad = {k: v for k, v in VALID_MARKER.items() if k != "dry_run_false"}
        with pytest.raises(A2MarkerError) as exc:
            validate_a2_marker(bad)
        assert exc.value.code == "INVALID_MARKER"
        assert "dry_run_false" in str(exc.value)

    def test_wrong_marker_name(self):
        bad = dict(VALID_MARKER, name="APPROVED_SOMETHING_ELSE")
        with pytest.raises(A2MarkerError) as exc:
            validate_a2_marker(bad)
        assert exc.value.code == "INVALID_MARKER"

    def test_wrong_scope_fails_closed(self):
        bad = dict(VALID_MARKER, approval_scope="ISSUE_999_ONLY")
        with pytest.raises(A2MarkerError) as exc:
            validate_a2_marker(bad)
        assert exc.value.code == "WRONG_SCOPE"

    def test_expired_marker(self):
        with pytest.raises(A2MarkerError) as exc:
            validate_a2_marker(
                VALID_MARKER,
                now=datetime(2026, 8, 4, 0, 0, tzinfo=UTC),
            )
        assert exc.value.code == "EXPIRED_MARKER"

    def test_valid_marker_accepts(self):
        result = validate_a2_marker(
            VALID_MARKER,
            now=datetime(2026, 8, 2, 20, 31, tzinfo=UTC),
        )
        assert result["name"] == "APPROVED_A2_BITGET_SNAPSHOT_V2"


# ---------------------------------------------------------------------------
# Funding fetch: pagination, dedup, stop conditions, retries
# ---------------------------------------------------------------------------


class TestFetchHistoryFunding:
    def test_paginates_backward_and_deduplicates(self):
        rows = _funding_for_pair("BTCUSDT", 250, start_minute=0, step=32)
        http = ScriptedHttpGet(funding={"BTCUSDT": rows})
        result = fetch_history_funding(
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            start=WARMUP_START,
            end=DATASET_END,
            http_get=http,
            rate_limit_rps=0,
        )
        assert len(result) == 250
        assert result == sorted(result, key=lambda r: r.funding_time)
        # unique
        assert len({(r.symbol, r.funding_time) for r in result}) == 250
        fund_calls = [c for c in http.calls if c[0].endswith("history-fund-rate")]
        assert len(fund_calls) >= 3  # multiple pages required for 250 rows

    def test_stops_when_page_before_start(self):
        # All rows far before start -> one call, empty result
        rows = [_funding_row("BTCUSDT", -5000 + i * 32) for i in range(10)]
        http = ScriptedHttpGet(funding={"BTCUSDT": rows})
        result = fetch_history_funding(
            symbol="BTCUSDT", product_type="USDT-FUTURES",
            start=WARMUP_START, end=DATASET_END, http_get=http, rate_limit_rps=0,
        )
        assert result == []

    def test_empty_page_stops(self):
        http = ScriptedHttpGet(funding={"BTCUSDT": []})
        result = fetch_history_funding(
            symbol="BTCUSDT", product_type="USDT-FUTURES",
            start=WARMUP_START, end=DATASET_END, http_get=http, rate_limit_rps=0,
        )
        assert result == []

    def test_no_backward_progress_breaks_loop(self):
        # One page whose oldest row is also its newest (single row) -> cursor
        # cannot move backward; loop must terminate.
        rows = [_funding_row("BTCUSDT", 1000)]
        http = ScriptedHttpGet(funding={"BTCUSDT": rows})
        result = fetch_history_funding(
            symbol="BTCUSDT", product_type="USDT-FUTURES",
            start=WARMUP_START, end=DATASET_END, http_get=http, rate_limit_rps=0,
        )
        assert len(result) == 1

    def test_retries_on_429_then_succeeds(self):
        calls = {"n": 0}

        def flaky_http(url, params, headers):
            calls["n"] += 1
            if calls["n"] <= 2:
                return 429, "rate limited"
            return 200, json.dumps({"code": "00000", "data": [_funding_row("BTCUSDT", 1000)]})

        result = fetch_history_funding(
            symbol="BTCUSDT", product_type="USDT-FUTURES",
            start=WARMUP_START, end=DATASET_END,
            http_get=flaky_http, rate_limit_rps=0, retry_delay=0.0,
        )
        assert len(result) == 1
        # 2 failed attempts + 1 success; the loop then issues one follow-up
        # page request (cursor = fundingTime of the only row) which returns an
        # empty page and terminates — 4 calls total.
        assert calls["n"] == 4

    def test_429_exhausted_raises(self):
        calls = {"n": 0}

        def failing_http(url, params, headers):
            calls["n"] += 1
            return 429, "rate limited"

        with pytest.raises(SnapshotFetchError, match="429"):
            fetch_history_funding(
                symbol="BTCUSDT", product_type="USDT-FUTURES",
                start=WARMUP_START, end=DATASET_END,
                http_get=failing_http, rate_limit_rps=0, retry_delay=0.0,
                max_retries=2,
            )
        assert calls["n"] == 3  # initial + 2 retries

    def test_malformed_row_fails_closed(self):
        def malformed_http(url, params, headers):
            return 200, json.dumps({"code": "00000", "data": [{"symbol": "BTCUSDT"}]})

        with pytest.raises(SnapshotFetchError, match="malformed funding row"):
            fetch_history_funding(
                symbol="BTCUSDT", product_type="USDT-FUTURES",
                start=WARMUP_START, end=DATASET_END,
                http_get=malformed_http, rate_limit_rps=0,
            )

    def test_normalize_funding_row_dict_and_array(self):
        d = normalize_funding_row(_funding_row("BTCUSDT", 0), "BTCUSDT")
        assert d.funding_time == WARMUP_START
        a = normalize_funding_row(["BTCUSDT", "0.0001", _ts_15m(32)], "BTCUSDT")
        assert a.funding_time == datetime(2024, 12, 1, 8, 0, tzinfo=UTC)

    def test_dedup_and_sort_funding(self):
        r1 = normalize_funding_row(_funding_row("BTCUSDT", 32), "BTCUSDT")
        r2 = normalize_funding_row(_funding_row("BTCUSDT", 32), "BTCUSDT")
        r0 = normalize_funding_row(_funding_row("BTCUSDT", 0), "BTCUSDT")
        result = dedup_and_sort_funding([r1, r2, r0])
        assert len(result) == 2
        assert result[0].funding_time == WARMUP_START


# ---------------------------------------------------------------------------
# Window boundaries and quality gates
# ---------------------------------------------------------------------------


class TestQualityChecks:
    def test_half_open_boundary(self):
        candles = [
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 15, tzinfo=UTC), "BTC/USDT:USDT"),
        ]
        report = run_quality_checks(
            candles, pair="BTC/USDT:USDT", timeframe="15m",
            window_label="warmup", window_start=WARMUP_START,
            window_end=datetime(2024, 12, 1, 0, 30, tzinfo=UTC),
        )
        assert report["out_of_window_count"] == 0
        assert report["pass"] is True

    def test_window_end_exclusive(self):
        end = datetime(2024, 12, 1, 0, 30, tzinfo=UTC)
        candles = [candle_at(end, "BTC/USDT:USDT")]  # exactly at end -> out
        report = run_quality_checks(
            candles, pair="BTC/USDT:USDT", timeframe="15m",
            window_label="warmup", window_start=WARMUP_START, window_end=end,
        )
        assert report["out_of_window_count"] == 1
        assert report["pass"] is False

    def test_expected_15m_count(self):
        assert expected_15m_count(WARMUP_START, HOLDOUT_START) == int(
            (HOLDOUT_START - WARMUP_START).total_seconds() // 900
        )
        assert expected_15m_count(WARMUP_START, WARMUP_START) == 0

    def test_duplicates_detected(self):
        candles = [
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
        ]
        report = run_quality_checks(
            candles, pair="BTC/USDT:USDT", timeframe="15m",
            window_label="warmup", window_start=WARMUP_START,
            window_end=datetime(2024, 12, 1, 1, 0, tzinfo=UTC),
        )
        assert report["duplicate_count"] == 1
        assert report["pass"] is False

    def test_gap_above_5pct_fails(self):
        # 1-hour window expects 4 candles; only 3 present -> 25 % missing
        candles = [
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 15, tzinfo=UTC), "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 30, tzinfo=UTC), "BTC/USDT:USDT"),
        ]
        report = run_quality_checks(
            candles, pair="BTC/USDT:USDT", timeframe="15m",
            window_label="warmup", window_start=WARMUP_START,
            window_end=datetime(2024, 12, 1, 1, 0, tzinfo=UTC),
        )
        assert report["missing_ratio"] == 0.25
        assert report["pass"] is False

    def test_non_monotonic_detected(self):
        candles = [
            candle_at(datetime(2024, 12, 1, 0, 15, tzinfo=UTC), "BTC/USDT:USDT"),
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
        ]
        report = run_quality_checks(
            candles, pair="BTC/USDT:USDT", timeframe="15m",
            window_label="warmup", window_start=WARMUP_START,
            window_end=datetime(2024, 12, 1, 1, 0, tzinfo=UTC),
        )
        assert report["non_monotonic_count"] == 1
        assert report["pass"] is False

    def test_funding_quality_checks(self):
        rows = [
            normalize_funding_row(_funding_row("BTCUSDT", 0), "BTCUSDT"),
            normalize_funding_row(_funding_row("BTCUSDT", 32), "BTCUSDT"),
        ]
        report = run_funding_quality_checks(
            rows, symbol="BTCUSDT", window_label="selection",
            window_start=WARMUP_START, window_end=HOLDOUT_START,
        )
        assert report["pass"] is True


def candle_at(ts: datetime, pair: str):
    from si_v2.research.evaluation_bundle_v1 import CandleV1

    return CandleV1(pair=pair, timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)


# ---------------------------------------------------------------------------
# 1h derivation determinism
# ---------------------------------------------------------------------------


class TestDerive1hCandles:
    def test_aggregates_four_full_slots(self):
        candles = [
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 15, tzinfo=UTC), "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 30, tzinfo=UTC), "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 45, tzinfo=UTC), "BTC/USDT:USDT"),
        ]
        hourly, incomplete = derive_1h_candles(candles)
        assert len(hourly) == 1
        assert hourly[0].timestamp == WARMUP_START
        assert hourly[0].open == 100.0
        assert hourly[0].volume == 40.0
        assert incomplete == []

    def test_incomplete_hour_dropped_and_reported(self):
        candles = [
            candle_at(WARMUP_START, "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 15, tzinfo=UTC), "BTC/USDT:USDT"),
            candle_at(datetime(2024, 12, 1, 0, 30, tzinfo=UTC), "BTC/USDT:USDT"),
        ]
        hourly, incomplete = derive_1h_candles(candles)
        assert hourly == []
        assert len(incomplete) == 1
        assert incomplete[0]["missing_slots"] == [45]

    def test_byte_identical_second_run(self):
        candles = _candles_for_pair("BTCUSDT", 500)
        from si_v2.research.gate0_snapshot_fetcher import normalize_candles

        c15 = normalize_candles(candles, pair="BTC/USDT:USDT", timeframe="15m")
        h1, _ = derive_1h_candles(c15)
        h2, _ = derive_1h_candles(c15)
        rows1 = [
            [c.pair, c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume]
            for c in h1
        ]
        rows2 = [
            [c.pair, c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume]
            for c in h2
        ]
        assert rows1 == rows2


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------


class TestPathConfinement:
    def test_escape_rejected(self, tmp_path: Path):
        with pytest.raises(PathEscapeError):
            confine_path(tmp_path, "..", "escape")

    def test_write_with_traversal_filename_rejected(self, tmp_path: Path):
        with pytest.raises(PathEscapeError):
            write_gz_csv_atomic(
                [["a", "b"]], ["x", "y"], tmp_path, "../evil.csv.gz"
            )

    def test_nested_subdir_inside_root_allowed(self, tmp_path: Path):
        p = confine_path(tmp_path, "selection", "market-15m", "a.csv.gz")
        assert str(p).startswith(str(tmp_path.resolve()))


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


class TestAtomicWrites:
    def test_write_gz_csv_atomic_no_tmp_leftover(self, tmp_path: Path):
        digest = write_gz_csv_atomic(
            [["BTC/USDT:USDT", "2024-12-01T00:00:00Z", "100", "101", "99", "100.5", "10"]],
            ["pair", "timestamp", "open", "high", "low", "close", "volume"],
            tmp_path,
            "BTC_USDT_15m.csv.gz",
        )
        target = tmp_path / "BTC_USDT_15m.csv.gz"
        assert target.exists()
        assert digest == __import__("hashlib").sha256(target.read_bytes()).hexdigest()
        assert (tmp_path / "BTC_USDT_15m.csv.gz.sha256").exists()
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []

    def test_partial_failure_no_completion_report(self, tmp_path: Path):
        candles = _full_candle_dataset()
        funding = _full_funding_dataset()
        fail_symbols = {PAIR_TO_SYMBOL["ETH/USDT:USDT"]}
        http = ScriptedHttpGet(
            candles=candles, funding=funding, fail_candle_symbols=fail_symbols
        )
        with pytest.raises(SnapshotFetchError):
            build_snapshot_v2(
                target_root=tmp_path,
                snapshot_id="snap-partial",
                marker=VALID_MARKER,
                http_get=http,
                rate_limit_rps=0,
                retry_delay=0.0,
                max_retries=0,
                now=datetime(2026, 8, 2, 20, 31, tzinfo=UTC),
            )
        # No completion report may exist for a partial run.
        assert not (tmp_path / "reports" / "snapshot_completion_report.json").exists()
        assert not (tmp_path / "manifests" / "snapshot_manifest.json").exists()
        # Audit must record the failure.
        audit = (tmp_path / "audit" / "fetch_audit.jsonl").read_text()
        assert "candles_fetch_error" in audit


# ---------------------------------------------------------------------------
# Full build: isolation, seal, determinism
# ---------------------------------------------------------------------------


class TestBuildSnapshotV2:
    def _build(self, root: Path, snapshot_id: str = "snap-test-001"):
        candles = _full_candle_dataset()
        funding = _full_funding_dataset()
        http = ScriptedHttpGet(candles=candles, funding=funding)
        result = build_snapshot_v2(
            target_root=root,
            snapshot_id=snapshot_id,
            marker=VALID_MARKER,
            http_get=http,
            rate_limit_rps=0,
            retry_delay=0.0,
            now=datetime(2026, 8, 2, 20, 31, tzinfo=UTC),
        )
        return result

    def test_full_build_complete(self, tmp_path: Path):
        result = self._build(tmp_path)
        assert result["completion_status"] == "COMPLETE"
        assert result["quality_gate"] == "PASS"
        assert result["holdout_seal_verify"] is True
        # 18 data files: 3 pairs x (sel 15m, sel 1h, sel funding, hold 15m, hold 1h, hold funding)
        assert result["file_count"] == 18
        assert (tmp_path / "manifests" / "snapshot_manifest.json").exists()
        assert (tmp_path / "manifests" / "snapshot_manifest.json.sha256").exists()
        assert (tmp_path / "reports" / "snapshot_completion_report.json").exists()
        assert (tmp_path / "quality" / "data_quality_report.json").exists()
        assert (tmp_path / "holdout-sealed" / "holdout_seal.json").exists()

    def test_selection_excludes_holdout_physically(self, tmp_path: Path):
        self._build(tmp_path)
        for pair in PAIRS:
            label = PAIR_TO_LABEL[pair]
            f = tmp_path / "selection" / "market-15m" / f"{label}_15m.csv.gz"
            with gzip.open(f, "rt") as fh:
                lines = fh.readlines()[1:]  # drop header
            timestamps = [line.split(",")[1] for line in lines]
            assert timestamps, f"empty selection file for {pair}"
            max_ts = max(datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) for t in timestamps)
            assert max_ts < HOLDOUT_START, f"holdout leaked into selection for {pair}"

    def test_holdout_files_are_only_holdout(self, tmp_path: Path):
        self._build(tmp_path)
        for pair in PAIRS:
            label = PAIR_TO_LABEL[pair]
            f = tmp_path / "holdout-sealed" / "market-15m" / f"{label}_15m.csv.gz"
            with gzip.open(f, "rt") as fh:
                lines = fh.readlines()[1:]
            assert lines
            first_ts = datetime.strptime(lines[0].split(",")[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            assert first_ts >= HOLDOUT_START

    def test_holdout_seal_verify_and_tamper_detection(self, tmp_path: Path):
        self._build(tmp_path)
        seal_dir = tmp_path / "holdout-sealed"
        verify = verify_holdout_seal(seal_dir)
        assert verify["ok"] is True
        # Tamper with one holdout file -> verification must fail.
        target = next((seal_dir / "market-15m").glob("*.csv.gz"))
        original = target.read_bytes()
        target.write_bytes(original + b"tampered")
        assert verify_holdout_seal(seal_dir)["ok"] is False
        target.write_bytes(original)  # restore

    def test_manifest_seal_reproducible(self, tmp_path: Path):
        self._build(tmp_path, snapshot_id="snap-repro")
        manifest1 = (tmp_path / "manifests" / "snapshot_manifest.json").read_bytes()
        seal1 = (tmp_path / "holdout-sealed" / "holdout_seal.json").read_bytes()

        other = tmp_path / "other"
        other.mkdir()
        self._build(other, snapshot_id="snap-repro")
        manifest2 = (other / "manifests" / "snapshot_manifest.json").read_bytes()
        seal2 = (other / "holdout-sealed" / "holdout_seal.json").read_bytes()
        assert manifest1 == manifest2
        assert seal1 == seal2

    def test_build_fails_before_writes_when_marker_missing(self, tmp_path: Path):
        with pytest.raises(A2MarkerError) as exc:
            build_snapshot_v2(
                target_root=tmp_path,
                snapshot_id="snap-no-marker",
                marker=None,
                http_get=ScriptedHttpGet(),
                rate_limit_rps=0,
            )
        assert exc.value.code == "MISSING_MARKER"
        assert not tmp_path.exists() or not list(tmp_path.iterdir())

    def test_build_fails_before_writes_when_marker_expired(self, tmp_path: Path):
        with pytest.raises(A2MarkerError) as exc:
            build_snapshot_v2(
                target_root=tmp_path,
                snapshot_id="snap-expired",
                marker=VALID_MARKER,
                http_get=ScriptedHttpGet(),
                rate_limit_rps=0,
                now=datetime(2026, 8, 4, 0, 0, tzinfo=UTC),
            )
        assert exc.value.code == "EXPIRED_MARKER"
        assert not tmp_path.exists() or not list(tmp_path.iterdir())

    def test_no_selection_reference_to_holdout_path(self, tmp_path: Path):
        self._build(tmp_path)
        manifest = json.loads((tmp_path / "manifests" / "snapshot_manifest.json").read_text())
        selection_paths = [f["path"] for f in manifest["files"] if f["path"].startswith("selection/")]
        assert selection_paths
        assert all("holdout" not in p for p in selection_paths)
