#!/usr/bin/env python3
"""FleetRisk watcher for the shared dry-run trading fleet.

This script is intentionally read-only. It polls the shared FleetRisk state,
Regime-Hybrid research artifacts, and live Docker logs from the three active
Freqtrade containers that should reflect FleetRisk behavior:

- freqtrade-freqforge
- freqtrade-freqforge-canary
- freqtrade-regime-hybrid

Default behavior:
- poll every 60 seconds
- run for 15 minutes
- print a compact, human-readable snapshot each cycle
- emit change-only detail lines for state, artifacts, warnings, and errors

Typical manual start:
    python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py

Longer background run:
    nohup python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py \
      > /tmp/fleet_watcher.log 2>&1 &
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path("/home/hermes/projects/trading")
SHARED = ROOT / "freqtrade/shared"
AUTOMATION = ROOT / "freqtrade/bots/regime-hybrid/config/research/automation"
DEFAULT_SIGNAL_SOURCE = ROOT / "freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json"
DEFAULT_LOG_DIR = SHARED / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "fleet_watcher.log"
DEFAULT_LOG_MAX_BYTES = 1_048_576
DEFAULT_LOG_BACKUPS = 5
DEFAULT_STATE_FILE = SHARED / "fleet_risk_state.json"
DEFAULT_ARTIFACTS = {
    "fleet_monitor_report": AUTOMATION / "latest_fleet_monitor_report.json",
    "self_optimizer_proposals": AUTOMATION / "latest_self_optimization_proposals.json",
    "self_optimizer_events": AUTOMATION / "self_optimizer_events.jsonl",
    "primo_signal_state": DEFAULT_SIGNAL_SOURCE,
    "historical_signals": ROOT / "freqtrade/bots/regime-hybrid/user_data/signals/historical_signals.jsonl",
}
DEFAULT_ARTIFACT_ORDER = (
    "fleet_monitor_report",
    "self_optimizer_proposals",
    "self_optimizer_events",
    "primo_signal_state",
    "historical_signals",
)
DEFAULT_BOT_ORDER = (
    "freqforge-canary",
    "freqforge-main",
    "regime-hybrid",
    "momentum",
    "freqai-rebel",
)
DEFAULT_CONTAINERS = [
    "freqtrade-freqforge",
    "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid",
]
UTC = dt.timezone.utc

ERROR_RE = re.compile(
    r"(traceback|exception|\berror\b|\bcritical\b|permission denied|connection refused|"
    r"no such file or directory|failed|cannot open|denied)",
    re.IGNORECASE,
)
WARNING_RE = re.compile(r"\bwarning\b|\bwarn\b|type': warning", re.IGNORECASE)
FLEET_RE = re.compile(
    r"(fleetrisk|fleet_risk|riskguard|drawdown|save state|state lock|correlation|quarantine)",
    re.IGNORECASE,
)
STATUS_RE = re.compile(
    r"(bot heartbeat|changing state to: running|application startup complete|started server process|"
    r"shutting down|finished server process|waiting for application shutdown|dry run is enabled|"
    r"using resolved protection|maxdrawdown|stoploss guard|lowprofitpairs)",
    re.IGNORECASE,
)


@dataclasses.dataclass
class StateSnapshot:
    path: Path
    exists: bool
    mtime_iso: str | None
    age_min: float | None
    error: str | None
    current_equity: float | None
    peak_equity: float | None
    drawdown: float | None
    open_trades: list[dict[str, Any]]
    history_count: int
    last_update: str | None
    signature: str


@dataclasses.dataclass
class ArtifactSnapshot:
    name: str
    path: Path
    exists: bool
    mtime_iso: str | None
    age_min: float | None
    size_bytes: int | None
    summary: str
    signature: str
    details: dict[str, Any]
    error: str | None = None


@dataclasses.dataclass
class ContainerLogSnapshot:
    name: str
    status: str
    started_at: str | None
    uptime_min: float | None
    restart_count: int | None
    heartbeat_ts: str | None
    heartbeat_age_min: float | None
    warning_count: int
    error_count: int
    fleet_count: int
    status_count: int
    new_lines: list[str]
    signature: str
    error: str | None = None


@dataclasses.dataclass
class CycleSnapshot:
    ts: dt.datetime
    state: StateSnapshot
    artifacts: dict[str, ArtifactSnapshot]
    containers: dict[str, ContainerLogSnapshot]


@dataclasses.dataclass
class AlertRecord:
    severity: str
    source: str
    message: str


class WatcherContext:
    def __init__(self) -> None:
        self.seen_log_lines: dict[str, set[str]] = {name: set() for name in DEFAULT_CONTAINERS}
        self.prev_state: StateSnapshot | None = None
        self.prev_artifacts: dict[str, ArtifactSnapshot] = {}
        self.prev_containers: dict[str, ContainerLogSnapshot] = {}


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if "." in text:
        head, tail = text.split(".", 1)
        frac_match = re.match(r"(\d+)(.*)", tail)
        if frac_match:
            digits = frac_match.group(1)[:6]
            rest = frac_match.group(2)
            text = f"{head}.{digits}{rest}"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_dt(value: dt.datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_minutes(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 0:
        return "0m"
    hours = int(value // 60)
    minutes = int(value % 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def format_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}"


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, str(exc)
    if not raw.strip():
        return None, "empty file"
    try:
        data = json.loads(raw)
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [], str(exc)
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    records: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, 1):
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            records.append(data)
    if not lines:
        return [], None
    return records, None


def file_age_minutes(path: Path) -> tuple[str | None, float | None]:
    if not path.exists():
        return None, None
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return format_dt(mtime), round((now_utc() - mtime).total_seconds() / 60.0, 2)


def hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def state_signature(data: dict[str, Any]) -> str:
    portfolio = data.get("portfolio") if isinstance(data.get("portfolio"), dict) else {}
    open_trades = data.get("open_trades") if isinstance(data.get("open_trades"), list) else []
    history = data.get("trade_history") if isinstance(data.get("trade_history"), list) else []
    payload = {
        "current_equity": portfolio.get("current_equity"),
        "peak_equity": portfolio.get("peak_equity"),
        "current_drawdown": portfolio.get("current_drawdown"),
        "last_update": data.get("last_update"),
        "open_keys": [entry.get("trade_key") for entry in open_trades if isinstance(entry, dict)],
        "history_len": len(history),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_state_snapshot(path: Path) -> StateSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return StateSnapshot(
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            error="missing file",
            current_equity=None,
            peak_equity=None,
            drawdown=None,
            open_trades=[],
            history_count=0,
            last_update=None,
            signature="missing",
        )

    data, error = load_json(path)
    if error or data is None:
        return StateSnapshot(
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            error=error or "unknown error",
            current_equity=None,
            peak_equity=None,
            drawdown=None,
            open_trades=[],
            history_count=0,
            last_update=None,
            signature=f"error:{hash_text(error or 'unknown')}",
        )

    portfolio = data.get("portfolio") if isinstance(data.get("portfolio"), dict) else {}
    open_trades_raw = data.get("open_trades") if isinstance(data.get("open_trades"), list) else []
    open_trades: list[dict[str, Any]] = [entry for entry in open_trades_raw if isinstance(entry, dict)]
    history = data.get("trade_history") if isinstance(data.get("trade_history"), list) else []
    signature = state_signature(data)
    return StateSnapshot(
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        error=None,
        current_equity=safe_float(portfolio.get("current_equity")),
        peak_equity=safe_float(portfolio.get("peak_equity")),
        drawdown=safe_float(portfolio.get("current_drawdown")),
        open_trades=open_trades,
        history_count=len(history),
        last_update=str(data.get("last_update") or "") or None,
        signature=signature,
    )


def summarize_open_trade(entry: dict[str, Any]) -> str:
    pair = entry.get("pair") or "?"
    direction = entry.get("direction") or "?"
    source = entry.get("source") or "?"
    trade_id = entry.get("trade_id")
    stake = safe_float(entry.get("stake"), None)
    opened_at = entry.get("opened_at") or "?"
    if stake is None:
        stake_text = "n/a"
    else:
        stake_text = f"{stake:.2f}"
    return f"{pair} {direction} stake={stake_text} src={source} id={trade_id} opened={opened_at}"


def state_summary(state: StateSnapshot) -> str:
    if state.error:
        return f"STATE ERROR: {state.error}"
    equity = state.current_equity
    peak = state.peak_equity
    drawdown = state.drawdown
    open_count = len(state.open_trades)
    last_update = parse_iso(state.last_update) if state.last_update else None
    state_age = None
    if last_update is not None:
        state_age = round((now_utc() - last_update).total_seconds() / 60.0, 2)
    parts = [
        f"equity={equity:.2f} USDT" if equity is not None else "equity=n/a",
        f"peak={peak:.2f} USDT" if peak is not None else "peak=n/a",
        f"dd={drawdown * 100:.2f}%" if drawdown is not None else "dd=n/a",
        f"open={open_count}",
        f"history={state.history_count}",
    ]
    if state_age is not None:
        parts.append(f"state_age={format_minutes(state_age)}")
    return " | ".join(parts)


def monitor_report_signature(data: dict[str, Any]) -> str:
    signals = data.get("signals") if isinstance(data.get("signals"), dict) else {}
    selfopt = data.get("self_optimizer") if isinstance(data.get("self_optimizer"), dict) else {}
    summary = selfopt.get("summary") if isinstance(selfopt.get("summary"), dict) else {}
    payload = {
        "timestamp_utc": data.get("timestamp_utc"),
        "bots": sorted((data.get("bots") or {}).keys()) if isinstance(data.get("bots"), dict) else [],
        "mode": data.get("mode"),
        "live": data.get("live_trading_allowed"),
        "selfopt_summary": summary,
        "regime": (selfopt.get("regime") or {}).get("regime") if isinstance(selfopt.get("regime"), dict) else None,
        "canonical_ts": (signals.get("canonical") or {}).get("timestamp_utc") if isinstance(signals.get("canonical"), dict) else None,
        "primo_ts": (signals.get("primo_state") or {}).get("timestamp_utc") if isinstance(signals.get("primo_state"), dict) else None,
        "archive_records": (signals.get("historical_archive") or {}).get("records") if isinstance(signals.get("historical_archive"), dict) else None,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_monitor_report(path: Path) -> ArtifactSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return ArtifactSnapshot(
            name="fleet_monitor_report",
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            size_bytes=None,
            summary="missing file",
            signature="missing",
            details={},
            error="missing file",
        )
    try:
        size_bytes = path.stat().st_size
    except Exception:
        size_bytes = None
    data, error = load_json(path)
    if error or data is None:
        return ArtifactSnapshot(
            name="fleet_monitor_report",
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            size_bytes=size_bytes,
            summary=f"error: {error}",
            signature=f"error:{hash_text(error or 'unknown')}",
            details={},
            error=error,
        )

    bots = data.get("bots") if isinstance(data.get("bots"), dict) else {}
    selfopt = data.get("self_optimizer") if isinstance(data.get("self_optimizer"), dict) else {}
    signals = data.get("signals") if isinstance(data.get("signals"), dict) else {}
    summary = selfopt.get("summary") if isinstance(selfopt.get("summary"), dict) else {}
    regime = selfopt.get("regime") if isinstance(selfopt.get("regime"), dict) else {}
    canonical = signals.get("canonical") if isinstance(signals.get("canonical"), dict) else {}
    primo = signals.get("primo_state") if isinstance(signals.get("primo_state"), dict) else {}
    hist = signals.get("historical_archive") if isinstance(signals.get("historical_archive"), dict) else {}
    summary_text = (
        f"ts={data.get('timestamp_utc')} | bots={len(bots)} | live={data.get('live_trading_allowed')} | "
        f"selfopt={summary.get('total_proposals', 0)} props (crit={summary.get('critical', 0)}, high={summary.get('high', 0)}) | "
        f"regime={regime.get('regime')} | canonical_age={canonical.get('mtime_age_min')}m | "
        f"primo_age={primo.get('mtime_age_min')}m{' STALE' if safe_float(primo.get('mtime_age_min'), 0.0) and safe_float(primo.get('mtime_age_min'), 0.0) > 45 else ''}"
    )
    details = {
        "timestamp_utc": data.get("timestamp_utc"),
        "mode": data.get("mode"),
        "live_trading_allowed": data.get("live_trading_allowed"),
        "bots": bots,
        "self_optimizer_summary": summary,
        "self_optimizer_regime": regime,
        "canonical": canonical,
        "primo_state": primo,
        "historical_archive": hist,
    }
    return ArtifactSnapshot(
        name="fleet_monitor_report",
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        size_bytes=size_bytes,
        summary=summary_text,
        signature=monitor_report_signature(data),
        details=details,
    )


def proposals_signature(data: dict[str, Any]) -> str:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    regime = data.get("regime") if isinstance(data.get("regime"), dict) else {}
    payload = {
        "timestamp_utc": data.get("timestamp_utc"),
        "summary": summary,
        "regime": regime.get("regime"),
        "fleet_proposals_len": len(data.get("fleet_proposals") or []),
        "bot_names": sorted((data.get("bots") or {}).keys()) if isinstance(data.get("bots"), dict) else [],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_proposals(path: Path) -> ArtifactSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return ArtifactSnapshot(
            name="self_optimizer_proposals",
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            size_bytes=None,
            summary="missing file",
            signature="missing",
            details={},
            error="missing file",
        )
    try:
        size_bytes = path.stat().st_size
    except Exception:
        size_bytes = None
    data, error = load_json(path)
    if error or data is None:
        return ArtifactSnapshot(
            name="self_optimizer_proposals",
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            size_bytes=size_bytes,
            summary=f"error: {error}",
            signature=f"error:{hash_text(error or 'unknown')}",
            details={},
            error=error,
        )

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    regime = data.get("regime") if isinstance(data.get("regime"), dict) else {}
    proposals = data.get("fleet_proposals") if isinstance(data.get("fleet_proposals"), list) else []
    summary_text = (
        f"ts={data.get('timestamp_utc')} | proposals={summary.get('total_proposals', 0)} "
        f"(crit={summary.get('critical', 0)}, high={summary.get('high', 0)}, med={summary.get('medium', 0)}) | "
        f"regime={regime.get('regime')} | archive_records={regime.get('archive_records')} | "
        f"watch_only_blocks={len(regime.get('watch_only_blocks') or [])}"
    )
    details = {
        "timestamp_utc": data.get("timestamp_utc"),
        "summary": summary,
        "regime": regime,
        "bots": data.get("bots") if isinstance(data.get("bots"), dict) else {},
        "proposal_types": [entry.get("type") for entry in proposals if isinstance(entry, dict)],
        "thresholds": data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {},
    }
    return ArtifactSnapshot(
        name="self_optimizer_proposals",
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        size_bytes=size_bytes,
        summary=summary_text,
        signature=proposals_signature(data),
        details=details,
    )


def events_signature(records: list[dict[str, Any]]) -> str:
    last = records[-1] if records else {}
    payload = {
        "records": len(records),
        "last_timestamp": last.get("timestamp_utc") or last.get("timestamp"),
        "last_summary": last.get("summary"),
        "last_keys": sorted(last.keys()) if isinstance(last, dict) else [],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_events(path: Path) -> ArtifactSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return ArtifactSnapshot(
            name="self_optimizer_events",
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            size_bytes=None,
            summary="missing file",
            signature="missing",
            details={},
            error="missing file",
        )
    try:
        size_bytes = path.stat().st_size
    except Exception:
        size_bytes = None
    records, error = load_jsonl(path)
    if error:
        return ArtifactSnapshot(
            name="self_optimizer_events",
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            size_bytes=size_bytes,
            summary=f"error: {error}",
            signature=f"error:{hash_text(error)}",
            details={},
            error=error,
        )
    last = records[-1] if records else {}
    summary = last.get("summary") if isinstance(last.get("summary"), dict) else {}
    summary_text = (
        f"records={len(records)} | last_ts={last.get('timestamp_utc') or last.get('timestamp')} | "
        f"summary={summary if summary else 'n/a'}"
    )
    return ArtifactSnapshot(
        name="self_optimizer_events",
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        size_bytes=size_bytes,
        summary=summary_text,
        signature=events_signature(records),
        details={
            "records": records,
            "last": last,
        },
    )


def signals_signature(records: list[dict[str, Any]]) -> str:
    last = records[-1] if records else {}
    data = last.get("data") if isinstance(last.get("data"), dict) else last
    payload = {
        "records": len(records),
        "last_ts": last.get("timestamp_utc") or last.get("timestamp") or last.get("generated_at"),
        "fresh": data.get("fresh") if isinstance(data, dict) else None,
        "pairs": sorted((data.get("pairs") or {}).keys()) if isinstance(data, dict) else [],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_historical_signals(path: Path) -> ArtifactSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return ArtifactSnapshot(
            name="historical_signals",
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            size_bytes=None,
            summary="missing file",
            signature="missing",
            details={},
            error="missing file",
        )
    try:
        size_bytes = path.stat().st_size
    except Exception:
        size_bytes = None
    records, error = load_jsonl(path)
    if error:
        return ArtifactSnapshot(
            name="historical_signals",
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            size_bytes=size_bytes,
            summary=f"error: {error}",
            signature=f"error:{hash_text(error)}",
            details={},
            error=error,
        )
    last = records[-1] if records else {}
    data = last.get("data") if isinstance(last.get("data"), dict) else last
    pairs = data.get("pairs") if isinstance(data.get("pairs"), dict) else {}
    pair_summaries: list[str] = []
    for pair, info in list(pairs.items())[:3]:
        if isinstance(info, dict):
            verdict = info.get("verdict") or info.get("action")
            direction = info.get("action") or info.get("bias") or "n/a"
            confidence = safe_float(info.get("confidence"), None)
            conf_text = f"{confidence:.2f}" if confidence is not None else "n/a"
            pair_summaries.append(f"{pair}:{verdict}/{direction}/{conf_text}")
    source_mtime_iso, source_age_min = file_age_minutes(DEFAULT_SIGNAL_SOURCE)
    summary_text = (
        f"records={len(records)} | last_ts={last.get('timestamp_utc') or last.get('timestamp') or last.get('generated_at')} | "
        f"fresh={data.get('fresh')} | pairs={len(pairs)} | source_mtime={source_mtime_iso or 'n/a'} | "
        f"source_age={format_minutes(source_age_min)} | sample={' ; '.join(pair_summaries) if pair_summaries else 'n/a'}"
    )
    return ArtifactSnapshot(
        name="historical_signals",
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        size_bytes=size_bytes,
        summary=summary_text,
        signature=signals_signature(records),
        details={
            "records": records,
            "last": last,
            "pairs": pairs,
        },
    )


ANSI_STYLES = {
    "critical": "\033[31;1m",
    "warning": "\033[33;1m",
    "info": "\033[36m",
    "ok": "\033[32m",
    "header": "\033[35;1m",
    "muted": "\033[90m",
}
SEVERITY_SYMBOLS = {
    "critical": "🚨",
    "warning": "⚠️",
    "info": "ℹ️",
    "ok": "✅",
}
BLOCK_RE = re.compile(
    r"(stake_up_blocked|quarantine_recommended|pending approval|pause entries|pause_entries|"
    r"max_open_trades_0|maxdrawdown|drawdown guard|state lock|failed to save state|blocked)",
    re.IGNORECASE,
)


def color_supported(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty() and os.environ.get("TERM", "") not in {"", "dumb"}


def style_text(text: str, severity: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{ANSI_STYLES.get(severity, '')}{text}\033[0m"


def shorten_text(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def format_float(value: Any, digits: int = 2) -> str:
    num = safe_float(value, None)
    if num is None:
        return "n/a"
    return f"{num:.{digits}f}"


def severity_rank(value: Any) -> int:
    return {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(str(value or "").lower(), -1)


def signal_state_signature(data: dict[str, Any]) -> str:
    pairs = data.get("pairs") if isinstance(data.get("pairs"), dict) else {}
    payload = {
        "generated_at": data.get("generated_at"),
        "processed_at": data.get("processed_at"),
        "fresh": data.get("fresh"),
        "stale": data.get("stale"),
        "age_minutes": data.get("age_minutes"),
        "pairs": sorted(str(pair) for pair in pairs.keys()),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def render_signal_state(path: Path) -> ArtifactSnapshot:
    exists = path.exists()
    mtime_iso, age_min = file_age_minutes(path)
    if not exists:
        return ArtifactSnapshot(
            name="primo_signal_state",
            path=path,
            exists=False,
            mtime_iso=None,
            age_min=None,
            size_bytes=None,
            summary="missing file",
            signature="missing",
            details={},
            error="missing file",
        )
    try:
        size_bytes = path.stat().st_size
    except Exception:
        size_bytes = None
    data, error = load_json(path)
    if error or data is None:
        return ArtifactSnapshot(
            name="primo_signal_state",
            path=path,
            exists=True,
            mtime_iso=mtime_iso,
            age_min=age_min,
            size_bytes=size_bytes,
            summary=f"error: {error}",
            signature=f"error:{hash_text(error or 'unknown')}",
            details={},
            error=error,
        )

    pairs = data.get("pairs") if isinstance(data.get("pairs"), dict) else {}
    pair_summaries: list[str] = []
    for pair, info in list(pairs.items())[:3]:
        if isinstance(info, dict):
            verdict = info.get("verdict") or info.get("action")
            direction = info.get("action") or info.get("bias") or "n/a"
            confidence = safe_float(info.get("confidence"), None)
            conf_text = f"{confidence:.2f}" if confidence is not None else "n/a"
            pair_summaries.append(f"{pair}:{verdict}/{direction}/{conf_text}")
    summary_text = (
        f"generated_at={data.get('generated_at')} | processed_at={data.get('processed_at')} | "
        f"fresh={data.get('fresh')} | stale={data.get('stale')} | age={data.get('age_minutes')}m | "
        f"pairs={len(pairs)} | sample={' ; '.join(pair_summaries) if pair_summaries else 'n/a'}"
    )
    return ArtifactSnapshot(
        name="primo_signal_state",
        path=path,
        exists=True,
        mtime_iso=mtime_iso,
        age_min=age_min,
        size_bytes=size_bytes,
        summary=summary_text,
        signature=signal_state_signature(data),
        details={
            "data": data,
            "pairs": pairs,
        },
    )


def summarize_top_proposal(proposals: Any) -> str:
    if not isinstance(proposals, list):
        return "none"
    ranked = [proposal for proposal in proposals if isinstance(proposal, dict)]
    if ranked:
        ranked.sort(key=lambda proposal: severity_rank(proposal.get("severity")), reverse=True)
        top = ranked[0]
        summary = f"{top.get('type') or 'proposal'}/{top.get('severity') or 'n/a'}"
        pieces = [summary]
        reason = shorten_text(top.get("reason"), 96)
        action = shorten_text(top.get("suggested_action"), 64)
        if reason:
            pieces.append(reason)
        if action:
            pieces.append(action)
        if len(ranked) > 1:
            secondary = ranked[1]
            pieces.append(f"+ {secondary.get('type') or 'proposal'}/{secondary.get('severity') or 'n/a'}")
        return " -> ".join(pieces)

    text_items = [shorten_text(item, 64) for item in proposals if shorten_text(item, 64)]
    if not text_items:
        return "none"
    if len(text_items) <= 2:
        return " -> ".join(text_items)
    return " -> ".join(text_items[:2]) + f" + {len(text_items) - 2} more"


def summarize_bot_line(bot_name: str, bot_data: dict[str, Any]) -> str:
    decision = bot_data.get("decision") if isinstance(bot_data.get("decision"), dict) else {}
    proposals = decision.get("proposals") if isinstance(decision.get("proposals"), list) else []
    verdict = decision.get("verdict") or "n/a"
    risk = decision.get("risk") or "n/a"
    pf_text = format_float(decision.get("profit_factor"), 4)
    wr_text = format_float(decision.get("winrate_pct"), 2)
    proposal_text = summarize_top_proposal(proposals)
    return f"{bot_name}: {verdict} | PF={pf_text} | WR={wr_text}% | risk={risk} | proposals={proposal_text}"


def build_alerts(snapshot: CycleSnapshot, ctx: WatcherContext) -> list[AlertRecord]:
    alerts: list[AlertRecord] = []
    seen: set[tuple[str, str, str]] = set()

    def add(severity: str, source: str, message: str) -> None:
        key = (severity, source, message)
        if key in seen:
            return
        seen.add(key)
        alerts.append(AlertRecord(severity=severity, source=source, message=message))

    state = snapshot.state
    if state.error:
        add("critical", "state", state.error)
        return alerts
    if state.drawdown is not None and state.drawdown >= 0.04:
        add("critical", "state", f"drawdown {state.drawdown * 100:.2f}% >= 4.00%")

    monitor = snapshot.artifacts.get("fleet_monitor_report")
    if monitor and not monitor.error:
        monitor_details = monitor.details if isinstance(monitor.details, dict) else {}
        if monitor_details.get("live_trading_allowed") is True:
            add("critical", "fleet_monitor_report", "live_trading_allowed=True in dry-run fleet")
        summary = monitor_details.get("self_optimizer_summary") if isinstance(monitor_details.get("self_optimizer_summary"), dict) else {}
        if safe_float(summary.get("critical"), 0.0) > 0:
            add(
                "critical",
                "self_optimizer",
                f"{int(safe_float(summary.get('critical'), 0.0) or 0)} critical / {int(safe_float(summary.get('high'), 0.0) or 0)} high proposals",
            )

    proposals = snapshot.artifacts.get("self_optimizer_proposals")
    if proposals and not proposals.error:
        proposal_details = proposals.details if isinstance(proposals.details, dict) else {}
        bot_map = proposal_details.get("bots") if isinstance(proposal_details.get("bots"), dict) else {}
        for bot_name in DEFAULT_BOT_ORDER:
            bot_data = bot_map.get(bot_name)
            if not isinstance(bot_data, dict):
                continue
            prop_list = [proposal for proposal in bot_data.get("proposals", []) if isinstance(proposal, dict)]
            if not prop_list:
                continue
            prop_list.sort(key=lambda proposal: severity_rank(proposal.get("severity")), reverse=True)
            top = prop_list[0]
            ptype = str(top.get("type") or "proposal")
            severity = str(top.get("severity") or "info").lower()
            if ptype == "quarantine_recommended":
                add(
                    "critical" if severity == "critical" else "warning",
                    bot_name,
                    f"{ptype}/{severity} -> {shorten_text(top.get('reason'), 96)}",
                )
            elif ptype == "stake_scale_down" and severity in {"high", "critical"}:
                add("warning", bot_name, f"{ptype}/{severity} -> {shorten_text(top.get('reason'), 96)}")

    for container_name in DEFAULT_CONTAINERS:
        snap = snapshot.containers.get(container_name)
        prev = ctx.prev_containers.get(container_name)
        if snap is None:
            continue
        if snap.error:
            add("critical", container_name, snap.error)
            continue
        if snap.status != "running":
            add("critical", container_name, f"status={snap.status}")
        if snap.restart_count is not None and prev is not None and prev.restart_count is not None and snap.restart_count > prev.restart_count:
            add("critical", container_name, f"restart_count {prev.restart_count} -> {snap.restart_count}")
        if snap.heartbeat_age_min is not None and snap.heartbeat_age_min >= 15:
            add(
                "critical" if snap.heartbeat_age_min >= 30 else "warning",
                container_name,
                f"heartbeat age {snap.heartbeat_age_min:.2f}m",
            )
        if snap.new_lines:
            error_hits = [line for line in snap.new_lines if ERROR_RE.search(line)]
            if error_hits:
                add("critical", container_name, shorten_text(error_hits[0], 120))
                continue
            warning_hits = [line for line in snap.new_lines if WARNING_RE.search(line) or BLOCK_RE.search(line)]
            if warning_hits:
                add("warning", container_name, shorten_text(warning_hits[0], 120))

    return alerts


def rotate_log_file(path: Path, max_bytes: int, backups: int) -> None:
    if not path.exists():
        return
    try:
        if path.stat().st_size < max_bytes:
            return
    except Exception:
        return
    backups = max(1, backups)
    oldest = path.with_name(f"{path.name}.{backups}")
    if oldest.exists():
        oldest.unlink()
    for index in range(backups - 1, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        if src.exists():
            src.rename(path.with_name(f"{path.name}.{index + 1}"))
    path.rename(path.with_name(f"{path.name}.1"))


def daemonize_watcher(args: argparse.Namespace) -> int:
    log_file = Path(args.log_file or DEFAULT_LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_file(log_file, int(args.log_max_bytes), int(args.log_backups))
    child_args = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--interval",
        str(args.interval),
        "--duration-minutes",
        str(args.duration_minutes),
        "--tail-lines",
        str(args.tail_lines),
        "--color",
        "never",
    ]
    with log_file.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            child_args,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
            close_fds=True,
        )
    print(f"FleetWatcher daemonized as pid={proc.pid} | log={log_file}", flush=True)
    return 0


def inspect_container(name: str, tail_lines: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        proc = subprocess.run(
            ["docker", "inspect", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, proc.stderr.strip() or proc.stdout.strip() or f"docker inspect exit {proc.returncode}"
    try:
        payload = json.loads(proc.stdout)
        if isinstance(payload, list) and payload:
            return payload[0], None
        return None, "unexpected docker inspect payload"
    except Exception as exc:
        return None, f"inspect parse error: {exc}"


def parse_log_line(line: str) -> tuple[dt.datetime | None, str]:
    if " " not in line:
        return None, line.strip()
    ts_text, content = line.split(" ", 1)
    ts = parse_iso(ts_text)
    return ts, content.rstrip()


def categorize_message(message: str) -> str | None:
    if not message:
        return None
    if ERROR_RE.search(message):
        return "error"
    if WARNING_RE.search(message):
        return "warning"
    if FLEET_RE.search(message):
        return "fleet"
    if STATUS_RE.search(message):
        if "bot heartbeat" in message.lower():
            return "heartbeat"
        return "status"
    if "bot heartbeat" in message.lower():
        return "heartbeat"
    return None


def capture_container_logs(context: WatcherContext, name: str, tail_lines: int) -> ContainerLogSnapshot:
    inspect_data, inspect_error = inspect_container(name, tail_lines)
    if inspect_error:
        return ContainerLogSnapshot(
            name=name,
            status="error",
            started_at=None,
            uptime_min=None,
            restart_count=None,
            heartbeat_ts=None,
            heartbeat_age_min=None,
            warning_count=0,
            error_count=0,
            fleet_count=0,
            status_count=0,
            new_lines=[],
            signature=f"inspect_error:{hash_text(inspect_error)}",
            error=inspect_error,
        )

    state = inspect_data.get("State") if isinstance(inspect_data.get("State"), dict) else {}
    status = str(state.get("Status") or "unknown")
    started_at = str(state.get("StartedAt") or "") or None
    restart_count = inspect_data.get("RestartCount")
    restart_count_int = int(restart_count) if isinstance(restart_count, int) or str(restart_count).isdigit() else None
    started_ts = parse_iso(started_at)
    uptime_min = None
    if started_ts is not None:
        uptime_min = round((now_utc() - started_ts).total_seconds() / 60.0, 2)

    try:
        proc = subprocess.run(
            ["docker", "logs", "--timestamps", "--tail", str(tail_lines), name],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return ContainerLogSnapshot(
            name=name,
            status=status,
            started_at=started_at,
            uptime_min=uptime_min,
            restart_count=restart_count_int,
            heartbeat_ts=None,
            heartbeat_age_min=None,
            warning_count=0,
            error_count=0,
            fleet_count=0,
            status_count=0,
            new_lines=[],
            signature=f"logs_error:{hash_text(str(exc))}",
            error=str(exc),
        )

    if proc.returncode != 0 and not proc.stdout:
        return ContainerLogSnapshot(
            name=name,
            status=status,
            started_at=started_at,
            uptime_min=uptime_min,
            restart_count=restart_count_int,
            heartbeat_ts=None,
            heartbeat_age_min=None,
            warning_count=0,
            error_count=0,
            fleet_count=0,
            status_count=0,
            new_lines=[],
            signature=f"logs_error:{hash_text(proc.stderr.strip() or proc.stdout.strip() or str(proc.returncode))}",
            error=proc.stderr.strip() or proc.stdout.strip() or f"docker logs exit {proc.returncode}",
        )

    raw_output = proc.stdout if proc.stdout else proc.stderr
    if proc.stdout and proc.stderr:
        raw_output = proc.stdout + "\n" + proc.stderr

    heartbeat_ts: dt.datetime | None = None
    heartbeat_age_min: float | None = None
    warning_count = 0
    error_count = 0
    fleet_count = 0
    status_count = 0
    new_lines: list[str] = []
    seen = context.seen_log_lines.setdefault(name, set())

    for raw_line in raw_output.splitlines():
        _ts, message = parse_log_line(raw_line)
        category = categorize_message(message)
        if category == "heartbeat":
            heartbeat_ts = _ts or heartbeat_ts
            continue
        if category == "warning":
            warning_count += 1
        elif category == "error":
            error_count += 1
        elif category == "fleet":
            fleet_count += 1
        elif category == "status":
            status_count += 1
        if category and message not in seen:
            seen.add(message)
            new_lines.append(message)

    if heartbeat_ts is not None:
        heartbeat_age_min = round((now_utc() - heartbeat_ts).total_seconds() / 60.0, 2)

    signature_payload = {
        "status": status,
        "started_at": started_at,
        "restart_count": restart_count_int,
        "heartbeat": heartbeat_ts.isoformat() if heartbeat_ts else None,
        "warning_count": warning_count,
        "error_count": error_count,
        "fleet_count": fleet_count,
        "status_count": status_count,
        "new_line_count": len(new_lines),
    }
    signature = hashlib.sha1(json.dumps(signature_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return ContainerLogSnapshot(
        name=name,
        status=status,
        started_at=started_at,
        uptime_min=uptime_min,
        restart_count=restart_count_int,
        heartbeat_ts=format_dt(heartbeat_ts) if heartbeat_ts else None,
        heartbeat_age_min=heartbeat_age_min,
        warning_count=warning_count,
        error_count=error_count,
        fleet_count=fleet_count,
        status_count=status_count,
        new_lines=new_lines,
        signature=signature,
        error=None,
    )


def format_container_line(snapshot: ContainerLogSnapshot) -> str:
    if snapshot.error:
        return f"{snapshot.name}: ERROR {snapshot.error}"
    heartbeat = snapshot.heartbeat_ts or "n/a"
    hb_age = format_minutes(snapshot.heartbeat_age_min)
    uptime = format_minutes(snapshot.uptime_min)
    restart_text = str(snapshot.restart_count) if snapshot.restart_count is not None else "n/a"
    return (
        f"{snapshot.name}: {snapshot.status} | uptime={uptime} | restarts={restart_text} | "
        f"heartbeat={heartbeat} (age={hb_age}) | WARN={snapshot.warning_count} ERR={snapshot.error_count} FLEET={snapshot.fleet_count} STATUS={snapshot.status_count}"
    )


def diff_state(prev: StateSnapshot | None, curr: StateSnapshot) -> list[str]:
    if prev is None or prev.error or curr.error:
        lines = []
        if curr.error:
            lines.append(f"state_error={curr.error}")
        else:
            lines.append("initial state snapshot")
        return lines

    lines: list[str] = []
    prev_eq = prev.current_equity or 0.0
    curr_eq = curr.current_equity or 0.0
    prev_dd = prev.drawdown or 0.0
    curr_dd = curr.drawdown or 0.0
    if abs(curr_eq - prev_eq) > 1e-9:
        lines.append(f"equity {format_delta(curr_eq - prev_eq)} USDT")
    if abs(curr_dd - prev_dd) > 1e-9:
        lines.append(f"drawdown {format_delta((curr_dd - prev_dd) * 100)} pct-points")
    if len(curr.open_trades) != len(prev.open_trades):
        lines.append(f"open_trades {len(prev.open_trades)} -> {len(curr.open_trades)}")
    if curr.history_count != prev.history_count:
        lines.append(f"history {prev.history_count} -> {curr.history_count}")
    if curr.last_update != prev.last_update:
        lines.append(f"last_update {prev.last_update} -> {curr.last_update}")
    prev_keys = {entry.get("trade_key") for entry in prev.open_trades if isinstance(entry, dict)}
    curr_keys = {entry.get("trade_key") for entry in curr.open_trades if isinstance(entry, dict)}
    opened = sorted(curr_keys - prev_keys)
    closed = sorted(prev_keys - curr_keys)
    if opened:
        lines.append("opened: " + ", ".join(opened))
    if closed:
        lines.append("closed: " + ", ".join(closed))
    return lines


def diff_artifact(prev: ArtifactSnapshot | None, curr: ArtifactSnapshot) -> list[str]:
    if prev is None or prev.signature != curr.signature:
        return [curr.summary]
    return []



def render_cycle(snapshot: CycleSnapshot, ctx: WatcherContext, use_color: bool = False) -> str:
    lines: list[str] = []
    ts_text = snapshot.ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(style_text(f"=== FleetWatcher {ts_text} ===", "header", use_color))
    lines.append(f"State: {state_summary(snapshot.state)}")
    if snapshot.state.open_trades:
        opened = "; ".join(summarize_open_trade(entry) for entry in snapshot.state.open_trades[:8])
        lines.append(f"Open trades: {opened}")
    else:
        lines.append("Open trades: none")

    alerts = build_alerts(snapshot, ctx)
    lines.append(style_text("Alerts:", "header", use_color))
    if alerts:
        for alert in alerts:
            symbol = SEVERITY_SYMBOLS.get(alert.severity, "•")
            line = f"  - {symbol} {alert.severity.upper()}: {alert.source} | {alert.message}"
            lines.append(style_text(line, alert.severity if alert.severity in ANSI_STYLES else "info", use_color))
    else:
        lines.append("  - none")

    lines.append(style_text("Artifacts:", "header", use_color))
    for name in DEFAULT_ARTIFACT_ORDER:
        art = snapshot.artifacts[name]
        age_text = format_minutes(art.age_min)
        size_text = f"{art.size_bytes} bytes" if art.size_bytes is not None else "n/a"
        mtime_text = art.mtime_iso or "n/a"
        line = f"  - {name}: {art.summary} | age={age_text} | mtime={mtime_text} | size={size_text}"
        if art.error:
            line += f" | error={art.error}"
        lines.append(style_text(line, "warning" if art.error else "info", use_color))

    lines.append(style_text("Bot decisions:", "header", use_color))
    monitor_details = snapshot.artifacts["fleet_monitor_report"].details if isinstance(snapshot.artifacts["fleet_monitor_report"].details, dict) else {}
    monitor_bots = monitor_details.get("bots") if isinstance(monitor_details.get("bots"), dict) else {}
    for bot_name in DEFAULT_BOT_ORDER:
        bot_data = monitor_bots.get(bot_name)
        if not isinstance(bot_data, dict):
            continue
        decision = bot_data.get("decision") if isinstance(bot_data.get("decision"), dict) else {}
        verdict = str(decision.get("verdict") or "n/a")
        severity = "warning" if verdict == "UNDERPERFORMING" else "ok" if verdict == "TOP_CANDIDATE" else "info"
        lines.append(style_text(f"  - {summarize_bot_line(bot_name, bot_data)}", severity, use_color))
    extra_bots = sorted(name for name in monitor_bots.keys() if name not in DEFAULT_BOT_ORDER)
    for bot_name in extra_bots:
        bot_data = monitor_bots.get(bot_name)
        if isinstance(bot_data, dict):
            decision = bot_data.get("decision") if isinstance(bot_data.get("decision"), dict) else {}
            verdict = str(decision.get("verdict") or "n/a")
            severity = "warning" if verdict == "UNDERPERFORMING" else "ok" if verdict == "TOP_CANDIDATE" else "info"
            lines.append(style_text(f"  - {summarize_bot_line(bot_name, bot_data)}", severity, use_color))

    lines.append(style_text("Containers:", "header", use_color))
    for container in DEFAULT_CONTAINERS:
        snap = snapshot.containers[container]
        container_line = f"  - {format_container_line(snap)}"
        severity = "critical" if snap.error or snap.status != "running" else "info"
        lines.append(style_text(container_line, severity, use_color))

    state_changes = diff_state(ctx.prev_state, snapshot.state)
    if state_changes:
        lines.append(style_text("Changes: state", "header", use_color))
        for item in state_changes:
            lines.append(f"  * {item}")
    else:
        lines.append("Changes: state unchanged")

    lines.append(style_text("Changes: artifacts", "header", use_color))
    for name in DEFAULT_ARTIFACT_ORDER:
        prev_art = ctx.prev_artifacts.get(name)
        curr_art = snapshot.artifacts[name]
        art_changes = diff_artifact(prev_art, curr_art)
        if art_changes:
            lines.append(f"  * {name}: changed")
            for item in art_changes:
                lines.append(f"    - {item}")
        else:
            lines.append(f"  * {name}: unchanged")

    lines.append(style_text("Changes: containers", "header", use_color))
    for container in DEFAULT_CONTAINERS:
        prev = ctx.prev_containers.get(container)
        curr = snapshot.containers[container]
        if prev is None or prev.signature != curr.signature:
            lines.append(f"  * {container}: changed")
            lines.append(f"    - {format_container_line(curr)}")
            if curr.new_lines:
                for line in curr.new_lines[:5]:
                    lines.append(f"    - {line}")
        else:
            lines.append(f"  * {container}: unchanged")
    return "\n".join(lines)


def capture_cycle(ctx: WatcherContext, tail_lines: int) -> CycleSnapshot:
    ts = now_utc()
    artifacts = {
        "fleet_monitor_report": render_monitor_report(DEFAULT_ARTIFACTS["fleet_monitor_report"]),
        "self_optimizer_proposals": render_proposals(DEFAULT_ARTIFACTS["self_optimizer_proposals"]),
        "self_optimizer_events": render_events(DEFAULT_ARTIFACTS["self_optimizer_events"]),
        "primo_signal_state": render_signal_state(DEFAULT_ARTIFACTS["primo_signal_state"]),
        "historical_signals": render_historical_signals(DEFAULT_ARTIFACTS["historical_signals"]),
    }
    containers = {name: capture_container_logs(ctx, name, tail_lines=tail_lines) for name in DEFAULT_CONTAINERS}
    return CycleSnapshot(ts=ts, state=render_state_snapshot(DEFAULT_STATE_FILE), artifacts=artifacts, containers=containers)


def update_context(ctx: WatcherContext, snapshot: CycleSnapshot) -> None:
    ctx.prev_state = snapshot.state
    ctx.prev_artifacts = snapshot.artifacts
    ctx.prev_containers = snapshot.containers


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only FleetRisk / Regime-Hybrid watcher")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between polls (default: 60)")
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=15.0,
        help="Run duration in minutes; use 0 to run indefinitely (default: 15)",
    )
    parser.add_argument("--once", action="store_true", help="Run a single snapshot and exit")
    parser.add_argument("--tail-lines", type=int, default=250, help="Docker log tail lines to inspect per cycle")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto", help="Colorize console output")
    parser.add_argument(
        "--background",
        "--daemon",
        action="store_true",
        dest="background",
        help="Detach into the background and write output to a log file",
    )
    parser.add_argument("--log-file", type=Path, default=None, help=f"Log file used with --background (default: {DEFAULT_LOG_FILE})")
    parser.add_argument("--log-max-bytes", type=int, default=DEFAULT_LOG_MAX_BYTES, help="Rotate the log file before daemon start if it grows beyond this size")
    parser.add_argument("--log-backups", type=int, default=DEFAULT_LOG_BACKUPS, help="How many rotated log files to keep")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.once and args.background:
        print("FleetWatcher: --background ignored with --once", flush=True)
        args.background = False
    if args.background:
        return daemonize_watcher(args)

    ctx = WatcherContext()
    start = now_utc()
    duration_limit = None if args.duration_minutes <= 0 else dt.timedelta(minutes=args.duration_minutes)
    cycle = 0
    use_color = color_supported(args.color)

    duration_text = "forever" if duration_limit is None else f"{args.duration_minutes:.0f}m"
    print(
        style_text(
            f"FleetWatcher started at {format_dt(start)} | interval={args.interval:.0f}s | duration={duration_text} | state={DEFAULT_STATE_FILE} | containers={', '.join(DEFAULT_CONTAINERS)}",
            "header",
            use_color,
        ),
        flush=True,
    )

    while True:
        cycle += 1
        snapshot = capture_cycle(ctx, args.tail_lines)
        print(render_cycle(snapshot, ctx, use_color=use_color), flush=True)
        update_context(ctx, snapshot)

        if args.once:
            break
        if duration_limit is not None and (now_utc() - start) >= duration_limit:
            break
        sleep_for = max(0.0, args.interval - 0.01)
        if sleep_for:
            time.sleep(sleep_for)

    print(style_text(f"FleetWatcher finished after {cycle} cycle(s).", "header", use_color), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
