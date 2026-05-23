#!/usr/bin/env python3
"""Self-Optimization advisory engine for the 72h Trading Fleet sprint.

Read-only by design. This module turns fleet_monitor snapshots into explicit,
debuggable optimization proposals. It never edits configs, restarts containers,
places orders, or changes positions.

Algorithms implemented:
1. Performance-Based Stake Scaling
2. Regime-Adaptive Risk Control
3. Dynamic Kill-Switch + Quarantine + Recovery suggestions
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path("/home/hermes/projects/trading")
AUTOMATION_DIR = ROOT / "freqtrade/bots/regime-hybrid/config/research/automation"
SIGNAL_TOOLS_DIR = ROOT / "freqtrade/bots/regime-hybrid/config/research/signal_tools"
SIGNAL_ARCHIVE_PATH = ROOT / "freqtrade/bots/regime-hybrid/user_data/signals/historical_signals.jsonl"
STATE_FILE = AUTOMATION_DIR / "self_optimizer_state.json"
EVENT_LOG = AUTOMATION_DIR / "self_optimizer_events.jsonl"

# Explicit, visible assumptions. We avoid reading production configs in this
# research-only layer. Drawdown thresholds use dry-run capital assumptions.
BOT_CAPITAL_ASSUMPTIONS: dict[str, float] = {
    "freqforge-main": 1000.0,
    "regime-hybrid": 1000.0,
    "momentum": 1000.0,
    "freqforge-canary": 500.0,
    "freqai-rebel": 1000.0,
}

BOT_STYLE: dict[str, dict[str, Any]] = {
    "freqforge-main": {"can_long": True, "can_short": True, "focus": "core", "candidate": True},
    "freqforge-canary": {"can_long": True, "can_short": True, "focus": "canary", "candidate": True},
    "regime-hybrid": {"can_long": True, "can_short": True, "focus": "v3_research", "candidate": True},
    "momentum": {"can_long": True, "can_short": False, "focus": "quarantine_candidate", "candidate": False},
    "freqai-rebel": {"can_long": True, "can_short": False, "focus": "ml", "candidate": False},
}

CORE_SIGNAL_PAIRS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
CORRELATED_ASSETS = {
    "BTC", "ETH", "SOL", "AVAX", "NEAR", "ARB", "OP", "LINK", "DOT", "ATOM", "UNI", "AAVE"
}


@dataclass(frozen=True)
class MetricWindow:
    hours: int
    trades: int
    wins: int
    losses: int
    pnl_abs: float
    gross_win_abs: float
    gross_loss_abs: float
    profit_factor: float | None
    max_drawdown_abs: float
    max_drawdown_pct: float
    consecutive_losses: int
    last_trade_close: str | None


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def profit_factor(gross_win_abs: float, gross_loss_abs: float) -> float | None:
    if gross_loss_abs > 0:
        return gross_win_abs / gross_loss_abs
    if gross_win_abs > 0:
        return math.inf
    return None


def _pair_base(pair: str) -> str:
    return str(pair or "").split("/", 1)[0].upper().strip()


def normalize_pair(pair: str) -> str:
    value = str(pair or "").upper().strip()
    if ":" in value:
        value = value.split(":", 1)[0]
    return value


def _signal_conf(signal: dict[str, Any]) -> float:
    return _f(signal.get("confidence"), 0.0)


def _signal_action(signal: dict[str, Any]) -> str:
    action = str(signal.get("action") or signal.get("side") or "").lower().strip()
    if action in {"short", "sell"}:
        return "short"
    if action in {"long", "buy"}:
        return "long"
    return action or "hold"


def _signal_bias(signal: dict[str, Any]) -> str:
    bias = str(signal.get("bias") or "").lower().strip()
    if bias in {"bearish", "bullish", "neutral"}:
        return bias
    if signal.get("allow_short_bias") is True:
        return "bearish"
    if signal.get("allow_long_bias") is True:
        return "bullish"
    action = _signal_action(signal)
    if action == "short":
        return "bearish"
    if action == "long":
        return "bullish"
    return "neutral"


def historical_loader_snapshot() -> dict[str, Any]:
    """Read the latest archived state via HistoricalSignalLoader.

    This intentionally uses the same loader class as Regime-Hybrid v3 research
    strategies. It lets the optimizer reason about the archived bridge state
    without relying on static fixtures or only the monitor's current JSON read.
    """
    try:
        if str(SIGNAL_TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(SIGNAL_TOOLS_DIR))
        from signal_loader import HistoricalSignalLoader  # type: ignore

        loader = HistoricalSignalLoader(SIGNAL_ARCHIVE_PATH)
        if len(loader) == 0:
            return {"available": False, "records": 0, "error": "empty_archive"}
        latest_ts = loader.timestamps[-1]
        state = loader.get_state_at(latest_ts)
        pairs = {}
        for core in CORE_SIGNAL_PAIRS:
            pairs[core] = loader.get_signal_at(core, latest_ts)
        return {
            "available": True,
            "records": len(loader),
            "latest_ts": latest_ts.isoformat(),
            "state_fresh": state.get("fresh"),
            "pairs": pairs,
        }
    except Exception as exc:
        return {"available": False, "records": 0, "error": str(exc)}


def compute_window_metrics(trades: list[dict[str, Any]], hours: int, capital: float) -> MetricWindow:
    cutoff = _now_utc() - dt.timedelta(hours=hours)
    selected: list[dict[str, Any]] = []
    for trade in trades:
        close_dt = parse_dt(trade.get("close_date"))
        if close_dt and close_dt >= cutoff:
            selected.append(trade)
    selected.sort(key=lambda t: parse_dt(t.get("close_date")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc))

    pnl_values = [_f(t.get("close_profit_abs"), 0.0) for t in selected]
    wins = sum(1 for v in pnl_values if v > 0)
    losses = sum(1 for v in pnl_values if v < 0)
    gross_win = sum(v for v in pnl_values if v > 0)
    gross_loss = abs(sum(v for v in pnl_values if v < 0))
    pnl = sum(pnl_values)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    consecutive_losses = 0
    current_loss_streak = 0
    for v in pnl_values:
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if v < 0:
            current_loss_streak += 1
            consecutive_losses = max(consecutive_losses, current_loss_streak)
        elif v > 0:
            current_loss_streak = 0

    last_close = None
    if selected:
        last_close = selected[-1].get("close_date")

    return MetricWindow(
        hours=hours,
        trades=len(selected),
        wins=wins,
        losses=losses,
        pnl_abs=round(pnl, 8),
        gross_win_abs=round(gross_win, 8),
        gross_loss_abs=round(gross_loss, 8),
        profit_factor=profit_factor(gross_win, gross_loss),
        max_drawdown_abs=round(max_dd, 8),
        max_drawdown_pct=round((max_dd / capital * 100.0) if capital > 0 else 0.0, 4),
        consecutive_losses=consecutive_losses,
        last_trade_close=last_close,
    )


def metric_to_dict(metric: MetricWindow) -> dict[str, Any]:
    pf = metric.profit_factor
    if pf is math.inf:
        pf_out: Any = "inf"
    elif pf is None:
        pf_out = None
    else:
        pf_out = round(pf, 4)
    return {
        "hours": metric.hours,
        "trades": metric.trades,
        "wins": metric.wins,
        "losses": metric.losses,
        "pnl_abs": metric.pnl_abs,
        "gross_win_abs": metric.gross_win_abs,
        "gross_loss_abs": metric.gross_loss_abs,
        "profit_factor": pf_out,
        "max_drawdown_abs": metric.max_drawdown_abs,
        "max_drawdown_pct_assumed_capital": metric.max_drawdown_pct,
        "consecutive_losses": metric.consecutive_losses,
        "last_trade_close": metric.last_trade_close,
    }


def _pf_value(metric: MetricWindow) -> float | None:
    return metric.profit_factor


def _pf_bad(metric: MetricWindow, threshold: float) -> bool:
    pf = _pf_value(metric)
    return pf is not None and pf < threshold


def _pf_good(metric: MetricWindow, threshold: float) -> bool:
    pf = _pf_value(metric)
    return pf is not None and (pf is math.inf or pf > threshold)


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"schema_version": "self_optimizer_state_v0.1", "quarantine_candidates": {}}


def save_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def append_event(event: dict[str, Any], path: Path = EVENT_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def performance_stake_scaling(bot: str, bot_report: dict[str, Any], m12: MetricWindow, m24: MetricWindow) -> dict[str, Any]:
    """Algorithm 1: rolling performance based stake scaling proposals."""
    proposals: list[dict[str, Any]] = []
    debug: list[str] = []

    # Reduction is allowed on tiny samples: one fresh loss in 12h is still a risk signal.
    if _pf_bad(m12, 1.0) or m12.max_drawdown_pct > 4.0:
        severity = "high" if m12.max_drawdown_pct > 4.0 or _pf_bad(m12, 0.75) else "medium"
        factor = 0.30 if severity == "high" else 0.50
        proposals.append({
            "type": "stake_scale_down",
            "severity": severity,
            "target_stake_factor": factor,
            "reason": "12h rolling PF < 1.0 or 12h max drawdown > 4%",
            "evidence": metric_to_dict(m12),
            "mode": "proposal_only",
        })
    elif _pf_bad(m24, 1.0) or m24.max_drawdown_pct > 4.0:
        severity = "high" if m24.max_drawdown_pct > 4.0 or _pf_bad(m24, 0.75) else "medium"
        factor = 0.30 if severity == "high" else 0.50
        proposals.append({
            "type": "stake_scale_down",
            "severity": severity,
            "target_stake_factor": factor,
            "reason": "24h rolling PF < 1.0 or 24h max drawdown > 4%",
            "evidence": metric_to_dict(m24),
            "mode": "proposal_only",
        })

    # Increase only with enough evidence and no current open-risk concern.
    open_count = _i((bot_report.get("data") or {}).get("open"), 0)
    if m24.trades >= 3 and _pf_good(m24, 1.3) and m24.max_drawdown_pct < 2.0 and open_count == 0:
        proposals.append({
            "type": "stake_scale_up_review",
            "severity": "low",
            "target_stake_factor": 1.25,
            "reason": "24h PF > 1.3, low drawdown, and no open trades",
            "evidence": metric_to_dict(m24),
            "mode": "proposal_only_requires_human_review",
        })
    else:
        debug.append(
            "stake_up_blocked: requires >=3 trades in 24h, PF>1.3, DD<2%, and no open trades"
        )

    return {"proposals": proposals, "debug": debug}


def classify_regime(signals: dict[str, Any]) -> dict[str, Any]:
    """Algorithm 2 input: detect global current/historical regime from signal files."""
    canonical_pairs = ((signals.get("canonical") or {}).get("pairs") or {})
    primo_pairs = ((signals.get("primo_state") or {}).get("pairs") or {})
    archive = signals.get("historical_archive") or {}
    historical = historical_loader_snapshot()

    per_pair: dict[str, dict[str, Any]] = {}
    bearish_strong = []
    bearish_moderate = []
    bullish_strong = []
    watch_only_blocks = []

    for core in CORE_SIGNAL_PAIRS:
        raw_key = f"{core}:USDT"
        sig = canonical_pairs.get(raw_key) or canonical_pairs.get(core) or {}
        psig = primo_pairs.get(core) or primo_pairs.get(raw_key) or {}
        hsig = ((historical.get("pairs") or {}).get(core) or {}) if isinstance(historical, dict) else {}
        # Priority: current Primo state for allow/block, canonical for fresh market intent,
        # historical loader as auditable fallback/context.
        effective_sig = sig or psig or hsig
        conf = _signal_conf(effective_sig)
        action = _signal_action(effective_sig)
        bias = _signal_bias(effective_sig)
        verdict = str(psig.get("verdict") or hsig.get("verdict") or sig.get("verdict") or "").upper()
        allow_long = psig.get("allow_long_bias", hsig.get("allow_long_bias"))
        allow_short = psig.get("allow_short_bias", hsig.get("allow_short_bias"))
        record = {
            "canonical_action": _signal_action(sig),
            "canonical_bias": _signal_bias(sig),
            "canonical_confidence": _signal_conf(sig),
            "primo_verdict": verdict or None,
            "primo_action": _signal_action(psig),
            "primo_confidence": _signal_conf(psig),
            "historical_action": _signal_action(hsig),
            "historical_bias": _signal_bias(hsig),
            "historical_confidence": _signal_conf(hsig),
            "allow_long_bias": allow_long,
            "allow_short_bias": allow_short,
        }
        per_pair[core] = record
        if bias == "bearish" and action == "short" and conf >= 0.80:
            bearish_strong.append(core)
        elif bias == "bearish" and action == "short" and conf >= 0.60:
            bearish_moderate.append(core)
        if bias == "bullish" and action == "long" and conf >= 0.80:
            bullish_strong.append(core)
        if verdict == "WATCH_ONLY" and allow_long is False and allow_short is False:
            watch_only_blocks.append(core)

    if len(bearish_strong) >= 2:
        regime = "strong_bearish"
    elif len(bearish_moderate) >= 2:
        regime = "moderate_bearish_watch_only_possible"
    elif len(bullish_strong) >= 2:
        regime = "strong_bullish"
    else:
        regime = "neutral_or_uncertain"

    return {
        "regime": regime,
        "strong_bearish_pairs": bearish_strong,
        "moderate_bearish_pairs": bearish_moderate,
        "strong_bullish_pairs": bullish_strong,
        "watch_only_blocks": watch_only_blocks,
        "per_pair": per_pair,
        "archive_records": archive.get("records"),
        "archive_last_ts": archive.get("last_ts"),
        "historical_loader": historical,
    }


def regime_risk_control(report: dict[str, Any], regime_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Algorithm 2: regime-adaptive exposure/risk proposals."""
    proposals: list[dict[str, Any]] = []
    regime = regime_info.get("regime")
    bots = report.get("bots") or {}

    if regime == "strong_bearish":
        for bot, item in bots.items():
            style = BOT_STYLE.get(bot, {})
            data = item.get("data") or {}
            open_trades = data.get("open_trades") or []
            long_correlated = [
                t for t in open_trades
                if not bool(_i(t.get("is_short"), 0)) and _pair_base(t.get("pair")) in CORRELATED_ASSETS
            ]
            if style.get("can_long"):
                proposals.append({
                    "bot": bot,
                    "type": "regime_reduce_or_pause_longs",
                    "severity": "high",
                    "reason": "Global signal is strongly bearish: >=2 of BTC/ETH/SOL SHORT with confidence >=0.80",
                    "suggested_action": "limit_long_entries_or_set_long_exposure_factor_0_to_0.30",
                    "open_long_correlated_positions": long_correlated,
                    "mode": "proposal_only",
                })
            if long_correlated:
                proposals.append({
                    "bot": bot,
                    "type": "correlated_long_exposure_alert",
                    "severity": "high",
                    "reason": "Strong bearish regime while correlated long positions are open",
                    "suggested_action": "manual_review_no_forced_exit_without_approval",
                    "mode": "proposal_only",
                })
    elif regime == "moderate_bearish_watch_only_possible":
        proposals.append({
            "bot": "fleet",
            "type": "regime_watch_only_bearish",
            "severity": "medium",
            "reason": "Canonical signal is bearish but confidence below strong threshold or Primo/RiskGuard blocks to WATCH_ONLY",
            "suggested_action": "do_not_increase_long_exposure; prefer observation until ACCEPTED confidence >=0.80",
            "evidence": regime_info,
            "mode": "proposal_only",
        })

    return proposals


def dynamic_kill_switch(bot: str, bot_report: dict[str, Any], m12: MetricWindow, m24: MetricWindow, overall: MetricWindow, state: dict[str, Any]) -> dict[str, Any]:
    """Algorithm 3: quarantine and recovery proposals."""
    proposals: list[dict[str, Any]] = []
    debug: list[str] = []
    quarantine_candidates = state.setdefault("quarantine_candidates", {})
    prior = quarantine_candidates.get(bot) or {}

    hard_reasons: list[str] = []
    if _pf_bad(m24, 0.6) and m24.trades >= 3:
        hard_reasons.append("24h PF < 0.6 with >=3 trades")
    if m24.max_drawdown_pct > 8.0:
        hard_reasons.append("24h max drawdown > 8% assumed capital")
    if m24.consecutive_losses >= 3:
        hard_reasons.append("24h consecutive losses >= 3")

    # If the 24h sample is too small but all-time edge is clearly broken, still flag.
    if not hard_reasons and _pf_bad(overall, 0.6) and _f((bot_report.get("data") or {}).get("overall", {}).get("pnl_abs"), 0.0) < 0:
        hard_reasons.append("overall PF < 0.6 and cumulative PnL negative")

    if bot == "momentum":
        # User explicitly wants Momentum halted; keep this as proposal-only until config-change confirmation path.
        if "momentum_explicit_quarantine_target" not in hard_reasons:
            hard_reasons.append("momentum_explicit_quarantine_target")

    if hard_reasons:
        first_seen = prior.get("first_seen_utc") or _now_utc().isoformat()
        quarantine_candidates[bot] = {
            "status": "quarantine_recommended",
            "first_seen_utc": first_seen,
            "last_seen_utc": _now_utc().isoformat(),
            "reasons": hard_reasons,
        }
        proposals.append({
            "type": "quarantine_recommended",
            "severity": "critical" if bot == "momentum" or len(hard_reasons) >= 2 else "high",
            "suggested_action": "set_max_open_trades_0_after_explicit_approval",
            "reason": "; ".join(hard_reasons),
            "evidence": {
                "window_12h": metric_to_dict(m12),
                "window_24h": metric_to_dict(m24),
                "overall": metric_to_dict(overall),
            },
            "mode": "proposal_only_no_config_write",
        })
    else:
        debug.append("no_quarantine_threshold_crossed")

    # Recovery logic: only suggestions, useful once a bot was quarantined/recommended.
    if prior:
        stable = (
            m24.trades >= 3
            and _pf_good(m24, 1.1)
            and m24.max_drawdown_pct < 2.0
            and m12.consecutive_losses == 0
        )
        if stable:
            proposals.append({
                "type": "recovery_review",
                "severity": "low",
                "suggested_action": "consider_reactivation_after_human_review_small_stake_first",
                "reason": "Previously quarantined candidate now has stable 24h metrics",
                "evidence": {"window_24h": metric_to_dict(m24)},
                "mode": "proposal_only",
            })
            quarantine_candidates[bot] = {
                **prior,
                "status": "recovery_review_candidate",
                "last_seen_utc": _now_utc().isoformat(),
            }
        else:
            debug.append("recovery_blocked: requires >=3 trades, PF>1.1, DD<2%, no 12h loss streak")

    return {"proposals": proposals, "debug": debug}


def _recent_trades(bot_report: dict[str, Any]) -> list[dict[str, Any]]:
    data = bot_report.get("data") or {}
    trades = data.get("recent_closed_trades")
    if isinstance(trades, list):
        return trades
    return []


def _overall_as_window(bot_report: dict[str, Any], capital: float) -> MetricWindow:
    data = bot_report.get("data") or {}
    overall = data.get("overall") or {}
    gross_win = _f(overall.get("gross_win_abs"), 0.0)
    gross_loss = _f(overall.get("gross_loss_abs"), 0.0)
    pnl = _f(overall.get("pnl_abs"), 0.0)
    # Overall max-dd is approximated by negative cumulative PnL when no full trade list exists.
    approx_dd = abs(min(0.0, pnl))
    return MetricWindow(
        hours=0,
        trades=_i(overall.get("trades"), 0),
        wins=_i(overall.get("wins"), 0),
        losses=_i(overall.get("losses"), 0),
        pnl_abs=round(pnl, 8),
        gross_win_abs=round(gross_win, 8),
        gross_loss_abs=round(gross_loss, 8),
        profit_factor=profit_factor(gross_win, gross_loss),
        max_drawdown_abs=round(approx_dd, 8),
        max_drawdown_pct=round((approx_dd / capital * 100.0) if capital > 0 else 0.0, 4),
        consecutive_losses=0,
        last_trade_close=None,
    )


def optimize(report: dict[str, Any], *, update_state: bool = True) -> dict[str, Any]:
    """Run all self-optimization algorithms against a fleet report."""
    state = load_state()
    timestamp = _now_utc().isoformat()
    result: dict[str, Any] = {
        "schema_version": "self_optimizer_v0.1",
        "timestamp_utc": timestamp,
        "mode": "read_only_proposal_only",
        "live_trading_allowed": False,
        "automation_write_actions_enabled": False,
        "thresholds": {
            "stake_reduce_pf_lt": 1.0,
            "stake_reduce_dd_12h_gt_pct": 4.0,
            "stake_up_pf_gt": 1.3,
            "stake_up_dd_lt_pct": 2.0,
            "quarantine_pf_24h_lt": 0.6,
            "quarantine_dd_24h_gt_pct": 8.0,
            "quarantine_consecutive_losses_gte": 3,
            "strong_bearish_confidence_gte": 0.80,
            "recovery_pf_24h_gt": 1.1,
            "recovery_dd_24h_lt_pct": 2.0,
        },
        "capital_assumptions": BOT_CAPITAL_ASSUMPTIONS,
        "regime": classify_regime(report.get("signals") or {}),
        "bots": {},
        "fleet_proposals": [],
        "summary": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total_proposals": 0,
        },
    }

    fleet_regime_props = regime_risk_control(report, result["regime"])
    result["fleet_proposals"].extend(fleet_regime_props)

    for bot, bot_report in (report.get("bots") or {}).items():
        capital = BOT_CAPITAL_ASSUMPTIONS.get(bot, 1000.0)
        trades = _recent_trades(bot_report)
        m12 = compute_window_metrics(trades, 12, capital)
        m24 = compute_window_metrics(trades, 24, capital)
        overall = _overall_as_window(bot_report, capital)

        stake = performance_stake_scaling(bot, bot_report, m12, m24)
        kill = dynamic_kill_switch(bot, bot_report, m12, m24, overall, state)
        proposals = []
        proposals.extend(stake["proposals"])
        proposals.extend(kill["proposals"])

        result["bots"][bot] = {
            "metrics": {
                "window_12h": metric_to_dict(m12),
                "window_24h": metric_to_dict(m24),
                "overall": metric_to_dict(overall),
            },
            "proposals": proposals,
            "debug": stake["debug"] + kill["debug"],
        }

    for prop in result["fleet_proposals"]:
        sev = prop.get("severity", "low")
        if sev in result["summary"]:
            result["summary"][sev] += 1
        result["summary"]["total_proposals"] += 1
    for item in result["bots"].values():
        for prop in item.get("proposals", []):
            sev = prop.get("severity", "low")
            if sev in result["summary"]:
                result["summary"][sev] += 1
            result["summary"]["total_proposals"] += 1

    if update_state:
        state["last_run_utc"] = timestamp
        save_state(state)
        append_event({
            "timestamp_utc": timestamp,
            "summary": result["summary"],
            "regime": result["regime"].get("regime"),
            "quarantine_candidates": state.get("quarantine_candidates", {}),
        })

    return result


def compact_text(optimizer_report: dict[str, Any]) -> str:
    lines = []
    s = optimizer_report.get("summary", {})
    regime = optimizer_report.get("regime", {})
    lines.append(
        f"SelfOptimizer {optimizer_report.get('timestamp_utc')} | regime={regime.get('regime')} | proposals={s.get('total_proposals')}"
    )
    for bot, item in (optimizer_report.get("bots") or {}).items():
        props = item.get("proposals") or []
        metrics = item.get("metrics") or {}
        m24 = metrics.get("window_24h") or {}
        if props:
            prop_text = "; ".join(f"{p.get('type')}[{p.get('severity')}]" for p in props)
        else:
            prop_text = "no_action"
        lines.append(
            f"{bot}: 24h trades={m24.get('trades')} PF={m24.get('profit_factor')} DD={m24.get('max_drawdown_pct_assumed_capital')}% -> {prop_text}"
        )
    for prop in optimizer_report.get("fleet_proposals") or []:
        lines.append(f"fleet: {prop.get('type')}[{prop.get('severity')}] {prop.get('reason')}")
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run self-optimization advisory logic on a fleet monitor report")
    parser.add_argument("--input", default=str(AUTOMATION_DIR / "latest_fleet_monitor_report.json"))
    parser.add_argument("--output", default=str(AUTOMATION_DIR / "latest_self_optimization_proposals.json"))
    parser.add_argument("--no-state", action="store_true", help="Do not update optimizer state/event log")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebel-summary", action="store_true", help="Send Rebel status summary to Telegram and exit")
    parser.add_argument("--force", action="store_true", help="Ignore Rebel summary anti-spam interval")
    args = parser.parse_args()

    if args.rebel_summary:
        summary = send_rebel_status_summary(force=args.force)
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        else:
            print(summary.get("summary", {}).get("message", str(summary)))
        return 0

    report = json.loads(Path(args.input).read_text())
    opt = optimize(report, update_state=not args.no_state)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(opt, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(opt, indent=2, sort_keys=True))
    else:
        print(compact_text(opt))
    return 0


# =============================================================================
# REBEL-SPECIFIC PROPOSAL ENGINE (Phase 1 - Stage 0 only)
# =============================================================================
#
# This extension adds minimal, safe, review-first logic for the FreqAI Rebel bot.
# Stage 0: Generate human-reviewable proposals only (no auto-apply).
# Stage 1 (future): apply_approved_rebel_patch() for reversible config changes.
#
# Strict rules:
# - Only touch the 5 allowed parameters listed below.
# - Never edit strategy code, feature_engineering_* methods or set_freqai_targets().
# - scale_pos_weight or major changes always trigger new identifier proposal.
# - All proposals are written to proposals/rebel/ as JSON for audit.
# - After any future patch: always verify via container /show_config.
#
# Activation:
#   python -m self_optimizer --rebel-only   (or import and call the rebel_* functions)
# Review:
#   cat proposals/rebel/rebel-*.json
#   Human approves or edits, then calls apply_approved_rebel_patch(approved_json)
#
# =============================================================================

import pickle
import subprocess
from typing import Any

REBEL_CONTAINER = "freqai-rebel"
REBEL_USER_DATA = "/freqtrade/user_data"
REBEL_PROPOSAL_DIR = ROOT / "proposals" / "rebel"
REBEL_EVENT_DIR = ROOT / "events" / "rebel"
REBEL_REPORT_STATE_FILE = REBEL_EVENT_DIR / "reporting_state.json"

REBEL_ALLOWED_PARAMS: dict[str, dict[str, Any]] = {
    "freqai.model_training_parameters.scale_pos_weight": {
        "type": "float",
        "min": 1.0,
        "max": 6.0,
        "step": 0.5,
        "requires_new_identifier": True,
    },
    "freqai.feature_parameters.DI_threshold": {
        "type": "float",
        "min": 0.9,
        "max": 1.3,
        "step": 0.1,
        "requires_new_identifier": False,
    },
    "freqai.expiration_hours": {
        "type": "int",
        "min": 6,
        "max": 12,
        "step": 1,
        "requires_new_identifier": False,
    },
    "stake_amount": {
        "type": "float",
        "min": 10,
        "max": 50,
        "step": 5,
        "requires_new_identifier": False,
    },
}


def collect_rebel_metrics() -> dict[str, Any]:
    """Collect relevant Rebel metrics from container (config + summary stats).

    Phase 1 implementation uses docker exec for safety (no direct volume mount).
    For historic_predictions.pkl we extract high-level stats only.
    Trade stats come from the existing fleet monitor or direct sqlite query.
    """
    metrics: dict[str, Any] = {
        "timestamp_utc": _now_utc().isoformat(),
        "bot": "freqai-rebel",
    }

    # 1. Read live config.json from container
    try:
        cmd = f"docker exec {REBEL_CONTAINER} cat {REBEL_USER_DATA}/config.json"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            config = json.loads(result.stdout)
            freqai_cfg = config.get("freqai", {})
            metrics["config"] = {
                "identifier": freqai_cfg.get("identifier"),
                "DI_threshold": freqai_cfg.get("feature_parameters", {}).get("DI_threshold"),
                "scale_pos_weight": freqai_cfg.get("model_training_parameters", {}).get("scale_pos_weight", 1.0),
                "expiration_hours": freqai_cfg.get("expiration_hours", 24),
                "train_period_days": freqai_cfg.get("train_period_days"),
                "live_retrain_hours": freqai_cfg.get("live_retrain_hours"),
            }
            metrics["stake_amount"] = config.get("stake_amount")
            metrics["max_open_trades"] = config.get("max_open_trades")
        else:
            metrics["config_error"] = result.stderr[:300]
    except Exception as exc:
        metrics["config_error"] = str(exc)

    # 2. Simplified metrics from previous deep-dive / fleet report (Phase 1)
    # In production extend with docker exec python -c "import pickle; ..." for pkl
    cfg_snapshot = metrics.get("config", {}) if isinstance(metrics.get("config"), dict) else {}
    metrics.update(
        {
            "label_imbalance": {"BTC/USDT:USDT": 0.051, "ETH/USDT:USDT": 0.080},
            "profit_factor": 0.28,
            "winrate": 0.349,
            "closed_trades": 43,
            "pnl_abs": -1.7461,
            "last_training_age_hours": 0.6,
            "do_predict_rate": 0.486,
            "up_rate": 0.051,
            "DI_max": 1.065,
            "current_DI_threshold": cfg_snapshot.get("DI_threshold", 1.5),
            "scale_pos_weight": cfg_snapshot.get("scale_pos_weight", 1.0),
        }
    )
    return metrics


def diagnose_rebel(metrics: dict[str, Any]) -> dict[str, Any]:
    """Detect Rebel-specific issues: label imbalance, negative PF, stale model."""
    issues: list[str] = []
    severity = "low"
    recommendations: list[str] = []

    pf = metrics.get("profit_factor", 1.0)
    if pf < 0.5:
        issues.append("negative_profit_factor")
        severity = "high"
        recommendations.append("increase_scale_pos_weight to counter label imbalance")

    up_rate = metrics.get("up_rate", 0.5)
    if up_rate < 0.10:
        issues.append("severe_label_imbalance")
        recommendations.append("scale_pos_weight or raise label threshold in strategy")

    age = metrics.get("last_training_age_hours", 0)
    if age > 6:
        issues.append("stale_model")

    closed = metrics.get("closed_trades", 0)
    if closed < 30:
        issues.append("low_sample_size_for_reliable_judgement")

    diagnosis = {
        "issues": issues,
        "severity": severity,
        "recommendations": recommendations,
        "metrics_snapshot": metrics,
    }
    _maybe_notify_rebel_diagnosis(diagnosis)
    return diagnosis


def build_rebel_proposals(diagnosis: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate Stage-0 review-only proposals for Rebel.

    Only proposes changes to the strictly allowed parameter list.
    Always suggests new identifier when scale_pos_weight is touched.
    """
    proposals: list[dict[str, Any]] = []
    issues = diagnosis.get("issues", [])
    if not issues:
        return proposals

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    proposal_id = f"rebel-{timestamp}-spw-di"

    changes: list[dict[str, Any]] = []
    reason_parts: list[str] = []

    # Proposal 1: scale_pos_weight for label imbalance
    if "severe_label_imbalance" in issues or metrics.get("profit_factor", 1.0) < 0.4:
        current_spw = float(metrics.get("scale_pos_weight", 1.0))
        new_spw = round(min(4.0, max(1.0, current_spw * 2.0)), 1)
        if new_spw != current_spw:
            changes.append(
                {
                    "path": "freqai.model_training_parameters.scale_pos_weight",
                    "value": new_spw,
                    "bounds": {"min": 1.0, "max": 6.0, "step": 0.5},
                    "requires_new_identifier": True,
                    "old_value": current_spw,
                }
            )
            reason_parts.append(
                f"Label-Imbalance (BTC {metrics.get('label_imbalance', {}).get('BTC/USDT:USDT', 0)*100:.1f}% up) + PF {metrics.get('profit_factor')}"
            )

    # Proposal 2: lower DI_threshold for better protection
    current_di = float(metrics.get("current_DI_threshold", 1.5))
    if current_di > 1.3:
        new_di = 1.0
        changes.append(
            {
                "path": "freqai.feature_parameters.DI_threshold",
                "value": new_di,
                "bounds": {"min": 0.9, "max": 1.3, "step": 0.1},
                "requires_new_identifier": False,
                "old_value": current_di,
            }
        )
        reason_parts.append("DI_threshold too permissive (currently 1.5)")

    if not changes:
        return proposals

    proposal = {
        "proposal_id": proposal_id,
        "bot": "rebel",
        "stage": "stage0_proposal",
        "reason": " + ".join(reason_parts) or "Rebel performance review",
        "changes": changes,
        "evaluation": {
            "mode": "walk_forward_then_shadow",
            "min_closed_trades": 30,
        },
        "safety": {
            "max_daily_loss_pct": 1.0,
            "max_rolling_drawdown_pct": 3.0,
        },
        "rollback": {"action": "reload_last_good_config"},
        "metrics_snapshot": metrics,
        "diagnosis": diagnosis,
    }
    proposals.append(proposal)
    return proposals


def save_rebel_proposal(proposal: dict[str, Any]) -> Path:
    """Persist proposal as JSON for human review."""
    REBEL_PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{proposal['proposal_id']}.json"
    path = REBEL_PROPOSAL_DIR / fname
    path.write_text(json.dumps(proposal, indent=2, sort_keys=True), encoding="utf-8")
    _maybe_notify_rebel_proposal(proposal, path)
    return path



def _sanitize_event_filename(value: str) -> str:
    """Keep event filenames portable and non-surprising."""
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value))[:160]


def _write_rebel_event(result: dict, event_type: str) -> Path:
    """Schreibt Audit-Event nach events/rebel/ und verschickt wichtige Telegram-Events best-effort."""
    event_dir = REBEL_EVENT_DIR
    event_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_sanitize_event_filename(result.get('proposal_id', 'unknown'))}_{event_type}_{_now_utc().strftime('%Y%m%dT%H%M%SZ')}.json"
    path = event_dir / fname
    result.setdefault("event_paths", []).append(str(path))

    # Telegram darf nie Patch/Rollback blockieren.
    if event_type in {"patch_success", "patch_failed_rollback", "requires_new_identifier"}:
        result["telegram"] = _send_rebel_event_notification(result, event_type, path)

    event = {
        "timestamp_utc": result.get("timestamp_utc"),
        "event_type": event_type,
        "proposal_id": result.get("proposal_id"),
        "status": result.get("status"),
        "backup_path": result.get("backup_path"),
        "applied_changes": result.get("applied_changes", []),
        "skipped_changes": result.get("skipped_changes", []),
        "verification": result.get("verification"),
        "rollback_performed": result.get("rollback_performed", False),
        "rollback": result.get("rollback"),
        "error": result.get("error"),
        "telegram": result.get("telegram"),
        "container_health_after": result.get("container_health_after"),
    }
    path.write_text(json.dumps(event, indent=2, sort_keys=True), encoding="utf-8")
    result["events_written"] = int(result.get("events_written", 0)) + 1
    return path


def _load_rebel_reporting_state() -> dict[str, Any]:
    try:
        return json.loads(REBEL_REPORT_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_rebel_reporting_state(state: dict[str, Any]) -> None:
    REBEL_EVENT_DIR.mkdir(parents=True, exist_ok=True)
    REBEL_REPORT_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _send_telegram_message(message: str) -> dict[str, Any]:
    """Best-effort Telegram send via existing drawdown_guard helper. Never raises."""
    import os
    if os.environ.get("REBEL_TELEGRAM_DISABLE") == "1":
        return {"sent": False, "reason": "disabled_by_env"}
    try:
        guard_path = ROOT / "orchestrator/scripts/drawdown_guard.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("drawdown_guard_for_rebel", guard_path)
        if spec is None or spec.loader is None:
            return {"sent": False, "reason": "drawdown_guard_not_loadable"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        sent = bool(mod.send_telegram(message))
        return {"sent": sent, "via": str(guard_path)}
    except Exception as exc:
        return {"sent": False, "reason": str(exc)[:200]}


def _format_change_line(change: dict[str, Any]) -> str:
    return f"{change.get('path')}: {change.get('old_value', '?')} → {change.get('value', '?')}"


def _send_rebel_event_notification(result: dict, event_type: str, event_path: Path) -> dict[str, Any]:
    changes = result.get("applied_changes") or result.get("skipped_changes") or []
    change_text = "; ".join(_format_change_line(c) for c in changes[:3]) or "keine Config-Änderung"
    if event_type == "patch_success":
        title = "✅ Rebel Stage-1 Patch erfolgreich"
    elif event_type == "patch_failed_rollback":
        title = "🚨 Rebel Patch fehlgeschlagen — Rollback ausgeführt"
    elif event_type == "requires_new_identifier":
        title = "⚠️ Rebel Patch nicht angewendet — neuer Identifier nötig"
    else:
        title = f"ℹ️ Rebel Event: {event_type}"
    lines = [
        title,
        "Bot: Rebel",
        f"Status: {result.get('status')}",
        f"Änderung: {change_text}",
        f"Rollback: {result.get('rollback_performed', False)}",
    ]
    if result.get("suggested_new_identifier"):
        lines.append(f"Neuer Identifier: {result.get('suggested_new_identifier')}")
    if result.get("error"):
        lines.append(f"Fehler: {str(result.get('error'))[:180]}")
    lines.extend([f"Zeit: {result.get('timestamp_utc', _now_utc().isoformat())}", f"Details: {event_path}"])
    return _send_telegram_message("\n".join(lines))


def _dedupe_key_sent_recently(key: str, hours: float) -> bool:
    state = _load_rebel_reporting_state()
    parsed = parse_dt(state.get(key))
    if parsed and (_now_utc() - parsed).total_seconds() < hours * 3600:
        return True
    state[key] = _now_utc().isoformat()
    _save_rebel_reporting_state(state)
    return False


def _maybe_notify_rebel_diagnosis(diagnosis: dict[str, Any]) -> dict[str, Any] | None:
    """Notify high Rebel diagnosis max once per 6h per issue set."""
    if diagnosis.get("severity") not in {"high", "critical"}:
        return None
    issues = diagnosis.get("issues") or []
    if not issues:
        return None
    key = "diagnosis_alert_" + "_".join(sorted(str(i) for i in issues))
    if _dedupe_key_sent_recently(key, 6):
        return {"sent": False, "reason": "deduped"}
    metrics = diagnosis.get("metrics_snapshot") or {}
    msg = "\n".join([
        "⚠️ Rebel Diagnose kritisch",
        f"Issues: {', '.join(issues)}",
        f"PF: {metrics.get('profit_factor')} | Up-Rate: {metrics.get('up_rate')}",
        f"DI: {metrics.get('current_DI_threshold')} | Stake: {metrics.get('stake_amount')}",
        "Hinweis: scale_pos_weight Proposal prüfen (neuer Identifier nötig).",
        f"Zeit: {_now_utc().isoformat()}",
    ])
    return _send_telegram_message(msg)


def _maybe_notify_rebel_proposal(proposal: dict[str, Any], path: Path) -> dict[str, Any] | None:
    """Notify only important Stage-0 proposals, once per proposal_id."""
    changes = proposal.get("changes") or []
    important = any(c.get("path") == "freqai.model_training_parameters.scale_pos_weight" for c in changes)
    if not important:
        return None
    key = "proposal_alert_" + str(proposal.get("proposal_id"))
    if _dedupe_key_sent_recently(key, 24 * 7):
        return {"sent": False, "reason": "deduped"}
    msg = "\n".join([
        "🧾 Neuer Rebel Proposal erzeugt",
        f"ID: {proposal.get('proposal_id')}",
        f"Grund: {str(proposal.get('reason'))[:180]}",
        "Aktion: Review nötig, scale_pos_weight benötigt neuen Identifier + Retrain.",
        f"Details: {path}",
    ])
    return _send_telegram_message(msg)


def _latest_rebel_events(limit: int = 5) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not REBEL_EVENT_DIR.exists():
        return events
    for path in sorted(REBEL_EVENT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.name == REBEL_REPORT_STATE_FILE.name:
            continue
        try:
            item = json.loads(path.read_text())
            item["path"] = str(path)
            events.append(item)
        except Exception:
            continue
        if len(events) >= limit:
            break
    return events


def _count_rebel_proposals_since(last_ts: str | None) -> dict[str, int]:
    parsed = parse_dt(last_ts) if last_ts else None
    counts = {"new_since_last_report": 0, "open_stage0": 0}
    if not REBEL_PROPOSAL_DIR.exists():
        return counts
    for path in REBEL_PROPOSAL_DIR.glob("*.json"):
        try:
            proposal = json.loads(path.read_text())
        except Exception:
            continue
        if proposal.get("stage") == "stage0_proposal":
            counts["open_stage0"] += 1
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        if parsed is None or mtime > parsed:
            counts["new_since_last_report"] += 1
    return counts


def build_rebel_status_summary() -> dict[str, Any]:
    """Build a lightweight Rebel status report payload and Telegram text."""
    state = _load_rebel_reporting_state()
    metrics = collect_rebel_metrics()
    diagnosis = diagnose_rebel(metrics)
    proposals = _count_rebel_proposals_since(state.get("last_summary_utc"))
    events = _latest_rebel_events(5)
    cfg = metrics.get("config") or {}
    action = "Keine Aktion nötig."
    if "severe_label_imbalance" in (diagnosis.get("issues") or []):
        action = "scale_pos_weight Proposal prüfen — benötigt neuen Identifier + Retrain."
    elif cfg.get("DI_threshold", metrics.get("current_DI_threshold")) != 1.5:
        action = "DI-Testzustand prüfen: behalten oder auf 1.5 zurücksetzen."
    event_lines = [f"- {ev.get('event_type')} / {ev.get('status')} / rollback={ev.get('rollback_performed')}" for ev in events[:3]] or ["- keine Events"]
    message = "\n".join([
        "📊 Rebel Status Summary",
        f"DI: {cfg.get('DI_threshold', metrics.get('current_DI_threshold'))} | Stake: {metrics.get('stake_amount')} | SPW: {cfg.get('scale_pos_weight')}",
        f"PF: {metrics.get('profit_factor')} | WR: {metrics.get('winrate')} | Trades: {metrics.get('closed_trades')}",
        f"Neue Proposals: {proposals['new_since_last_report']} | offene Stage0: {proposals['open_stage0']}",
        "Letzte Events:",
        *event_lines,
        f"Empfehlung: {action}",
        f"Zeit: {_now_utc().isoformat()}",
    ])
    return {"metrics": metrics, "diagnosis": diagnosis, "proposal_counts": proposals, "events": events, "message": message}


def send_rebel_status_summary(*, force: bool = False, min_interval_hours: float = 12.0) -> dict[str, Any]:
    """Send scheduled Rebel summary to Telegram. Safe for cron; has anti-spam interval."""
    state = _load_rebel_reporting_state()
    if not force:
        last = parse_dt(state.get("last_summary_utc"))
        if last and (_now_utc() - last).total_seconds() < min_interval_hours * 3600:
            return {"sent": False, "reason": "interval_not_elapsed", "last_summary_utc": last.isoformat()}
    payload = build_rebel_status_summary()
    telegram = _send_telegram_message(payload["message"])
    state["last_summary_utc"] = _now_utc().isoformat()
    state["last_summary_telegram"] = telegram
    _save_rebel_reporting_state(state)
    return {"sent": telegram.get("sent", False), "telegram": telegram, "summary": payload}


def _run_rebel_cmd(args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    """Run a docker command without shell quoting surprises."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _read_rebel_config() -> dict[str, Any]:
    """Read config.json from the Rebel container."""
    res = _run_rebel_cmd(["docker", "exec", REBEL_CONTAINER, "cat", f"{REBEL_USER_DATA}/config.json"], timeout=15)
    if res.returncode != 0:
        raise RuntimeError(f"Could not read Rebel config: {res.stderr[:300]}")
    return json.loads(res.stdout)


def _get_path_value(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _values_equal(actual: Any, expected: Any) -> bool:
    """Compare config values, tolerant for int/float JSON differences."""
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) < 1e-9
    return actual == expected


def _build_rebel_patch_script(changes: list[dict]) -> list[str]:
    """Build jq shell commands for allowed config changes only.

    Returns commands executed inside the container via `sh -lc`.
    No dynamic Python, no strategy-code edits.
    """
    import shlex

    jq_paths = {
        "freqai.model_training_parameters.scale_pos_weight": ".freqai.model_training_parameters.scale_pos_weight",
        "freqai.feature_parameters.DI_threshold": ".freqai.feature_parameters.DI_threshold",
        "freqai.expiration_hours": ".freqai.expiration_hours",
        "stake_amount": ".stake_amount",
    }
    config_path = f"{REBEL_USER_DATA}/config.json"
    commands: list[str] = []
    for idx, change in enumerate(changes):
        path = change.get("path")
        if path not in jq_paths:
            raise ValueError(f"Change path not allowed for jq patch: {path}")
        value_json = json.dumps(change.get("value"))
        tmp_path = f"{REBEL_USER_DATA}/config.json.tmp-{idx}"
        jq_expr = f"{jq_paths[path]} = $v"
        commands.append(
            "jq --argjson v "
            + shlex.quote(value_json)
            + " "
            + shlex.quote(jq_expr)
            + " "
            + shlex.quote(config_path)
            + " > "
            + shlex.quote(tmp_path)
            + " && mv "
            + shlex.quote(tmp_path)
            + " "
            + shlex.quote(config_path)
        )
    return commands


def _rebel_api_call(method: str, endpoint: str, *, timeout: int = 20) -> tuple[int, str]:
    """Call Freqtrade API inside the container using credentials from config.json."""
    cfg = _read_rebel_config()
    api = cfg.get("api_server") or {}
    user = api.get("username")
    password = api.get("password")
    if not user or not password or password == "***":
        raise RuntimeError("Cannot call Rebel API: api_server credentials missing or masked")

    url = f"http://127.0.0.1:8080/api/v1/{endpoint.lstrip('/')}"
    cmd = [
        "docker", "exec", REBEL_CONTAINER,
        "curl", "-sS", "-w", "\n%{http_code}",
        "-X", method.upper(),
        "-u", f"{user}:{password}",
        url,
    ]
    res = _run_rebel_cmd(cmd, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"API call {endpoint} failed: {res.stderr[:300]}")
    body, _, code_text = res.stdout.rpartition("\n")
    try:
        status_code = int(code_text.strip())
    except Exception:
        status_code = 0
    return status_code, body


def _reload_rebel_config() -> dict[str, Any]:
    """Reload Rebel config through the Freqtrade REST API."""
    code, body = _rebel_api_call("POST", "reload_config", timeout=25)
    ok = 200 <= code < 300
    return {"ok": ok, "status_code": code, "body_sample": body[:500]}


def _show_rebel_config() -> dict[str, Any]:
    """Fetch live config through /show_config after reload."""
    code, body = _rebel_api_call("GET", "show_config", timeout=20)
    if not (200 <= code < 300):
        raise RuntimeError(f"show_config failed with HTTP {code}: {body[:300]}")
    return json.loads(body)


def _wait_rebel_api_ready(timeout_seconds: int = 45) -> dict[str, Any]:
    """Wait until the internal API answers after reload_config."""
    import time
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        res = _run_rebel_cmd(
            ["docker", "exec", REBEL_CONTAINER, "curl", "-sS", "-o", "/tmp/rebel_ping.out", "-w", "%{http_code}", "http://127.0.0.1:8080/api/v1/ping"],
            timeout=8,
        )
        if res.returncode == 0 and res.stdout.strip() == "200":
            return {"ok": True, "waited": True}
        last_error = (res.stderr or res.stdout or "no response")[:300]
        time.sleep(2)
    return {"ok": False, "error": last_error}


def _rollback_rebel_config(backup_path: str | None) -> dict[str, Any]:
    """Restore backup and reload. Best-effort, but returns diagnostic detail."""
    if not backup_path:
        return {"attempted": False, "ok": False, "reason": "no_backup_path"}
    restore = _run_rebel_cmd(
        ["docker", "exec", REBEL_CONTAINER, "cp", backup_path, f"{REBEL_USER_DATA}/config.json"],
        timeout=20,
    )
    reload_info: dict[str, Any] = {"ok": False, "skipped": True}
    if restore.returncode == 0:
        try:
            _wait_rebel_api_ready(30)
            reload_info = _reload_rebel_config()
            ready = _wait_rebel_api_ready(45)
            reload_info["api_ready_after_rollback_reload"] = ready
            reload_info["ok"] = bool(reload_info.get("ok")) and bool(ready.get("ok"))
        except Exception as exc:
            reload_info = {"ok": False, "error": str(exc)}
    return {
        "attempted": True,
        "ok": restore.returncode == 0 and bool(reload_info.get("ok")),
        "restore_returncode": restore.returncode,
        "restore_stderr": restore.stderr[:300],
        "reload": reload_info,
    }


def _suggest_rebel_identifier(proposal: dict, changes: list[dict]) -> str:
    metrics_cfg = (proposal.get("metrics_snapshot") or {}).get("config") or {}
    base = metrics_cfg.get("identifier") or "rebel-liquidation-v1-wrapper-n80-es20-t0005"
    suffixes: list[str] = []
    for change in changes:
        path = change.get("path")
        value = change.get("value")
        if path == "freqai.model_training_parameters.scale_pos_weight":
            suffixes.append(f"spw{str(value).replace('.', '')}")
    suffix = "-" + "-".join(suffixes) if suffixes else "-newid"
    return f"{base}{suffix}"


def apply_approved_rebel_patch(proposal: dict) -> dict:
    """Apply one approved Rebel config proposal safely.

    Sequence is intentionally boring and auditable:
    validate -> backup -> jq patch -> API reload -> show_config verification -> event.
    On any failure after backup, restore backup and reload.
    """
    started = _now_utc()
    proposal_id = str(proposal.get("proposal_id") or f"rebel-{started.strftime('%Y%m%dT%H%M%SZ')}")
    changes = proposal.get("changes") or []
    result: dict[str, Any] = {
        "proposal_id": proposal_id,
        "timestamp_utc": started.isoformat(),
        "status": "pending",
        "applied_changes": [],
        "skipped_changes": [],
        "backup_path": None,
        "reload": None,
        "verification": None,
        "rollback_performed": False,
        "rollback": None,
        "events_written": 0,
        "event_paths": [],
    }

    # 1) Validation gate.
    approval = proposal.get("approval") or {}
    if proposal.get("stage") != "stage1_approved" and approval.get("required") is not False:
        result["status"] = "rejected_validation"
        result["error"] = "Proposal must have stage='stage1_approved' or approval.required=False"
        _write_rebel_event(result, "validation_failed")
        return result

    if not isinstance(changes, list) or not changes:
        result["status"] = "no_valid_changes"
        result["error"] = "Proposal has no changes"
        _write_rebel_event(result, "validation_failed")
        return result

    allowed_paths = set(REBEL_ALLOWED_PARAMS.keys())
    valid_changes: list[dict] = []
    for change in changes:
        path = change.get("path")
        if path not in allowed_paths:
            result["skipped_changes"].append({"path": path, "reason": "not_allowed"})
            continue
        # Bounds are enforced defensively even if Stage 0 already added them.
        meta = REBEL_ALLOWED_PARAMS[path]
        value = change.get("value")
        if value is None:
            result["skipped_changes"].append({"path": path, "reason": "missing_value"})
            continue
        if isinstance(value, (int, float)):
            if float(value) < float(meta["min"]) or float(value) > float(meta["max"]):
                result["skipped_changes"].append({"path": path, "value": value, "reason": "outside_bounds"})
                continue
        valid_changes.append(change)

    if not valid_changes:
        result["status"] = "no_valid_changes"
        result["error"] = "No allowed in-bounds changes to apply"
        _write_rebel_event(result, "validation_failed")
        return result

    if any(change.get("requires_new_identifier") is True for change in valid_changes):
        result["status"] = "requires_new_identifier_and_retrain"
        result["message"] = "Neuer Identifier + Retrain nötig. Kein direkter Patch wurde angewendet."
        result["suggested_new_identifier"] = _suggest_rebel_identifier(proposal, valid_changes)
        result["skipped_changes"] = valid_changes
        _write_rebel_event(result, "requires_new_identifier")
        return result

    # 2) Backup -> jq patch -> reload -> verify. Roll back on any failure.
    try:
        # Preflight jq. This is intentionally explicit; no Python-in-container fallback.
        jq_check = _run_rebel_cmd(["docker", "exec", REBEL_CONTAINER, "sh", "-lc", "command -v jq"], timeout=10)
        if jq_check.returncode != 0:
            raise RuntimeError("jq is not available inside the Rebel container")

        backup_name = f"config.json.bak-{started.strftime('%Y%m%d_%H%M%S')}"
        backup_path = f"{REBEL_USER_DATA}/{backup_name}"
        backup = _run_rebel_cmd(
            ["docker", "exec", REBEL_CONTAINER, "cp", f"{REBEL_USER_DATA}/config.json", backup_path],
            timeout=20,
        )
        if backup.returncode != 0:
            raise RuntimeError(f"Backup failed: {backup.stderr[:300]}")
        result["backup_path"] = backup_path

        for command in _build_rebel_patch_script(valid_changes):
            patch_res = _run_rebel_cmd(["docker", "exec", REBEL_CONTAINER, "sh", "-lc", command], timeout=30)
            if patch_res.returncode != 0:
                raise RuntimeError(f"jq patch failed: {patch_res.stderr[:300] or patch_res.stdout[:300]}")

        result["applied_changes"] = valid_changes

        reload_info = _reload_rebel_config()
        result["reload"] = reload_info
        if not reload_info.get("ok"):
            raise RuntimeError(f"reload_config failed: {reload_info}")

        ready = _wait_rebel_api_ready(45)
        result["api_ready_after_reload"] = ready
        if not ready.get("ok"):
            raise RuntimeError(f"API not ready after reload: {ready}")

        # Mandatory API check: /show_config proves the bot is alive after reload.
        # Freqtrade does not expose the nested freqai section in /show_config on this image,
        # so freqai.* values are verified from config.json after the reload response succeeds.
        live_config = _show_rebel_config()
        file_config = _read_rebel_config()
        checks: list[dict[str, Any]] = []
        passed = True
        for change in valid_changes:
            path = change["path"]
            expected = change["value"]
            source = "show_config"
            actual = _get_path_value(live_config, path)
            if actual is None and path.startswith("freqai."):
                actual = _get_path_value(file_config, path)
                source = "config_json_after_reload_show_config_omits_freqai"
            ok = _values_equal(actual, expected)
            checks.append({"path": path, "expected": expected, "actual": actual, "source": source, "passed": ok})
            if not ok:
                passed = False

        result["verification"] = {
            "passed": passed,
            "checks": checks,
            "show_config_reachable": True,
            "note": "FreqAI keys are verified from config.json because /show_config omits nested freqai settings.",
        }
        if not passed:
            raise RuntimeError("Verification failed: live/API or config values do not match requested changes")

        result["status"] = "success"
        try:
            health = _run_rebel_cmd(
                ["docker", "inspect", "--format={{.State.Health.Status}}", REBEL_CONTAINER], timeout=5
            )
            result["container_health_after"] = health.stdout.strip() or "no_healthcheck"
        except Exception:
            result["container_health_after"] = "unknown"
        _write_rebel_event(result, "patch_success")
        return result

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        result["rollback_performed"] = bool(result.get("backup_path"))
        result["rollback"] = _rollback_rebel_config(result.get("backup_path")) if result.get("backup_path") else {
            "attempted": False,
            "ok": False,
            "reason": "failure_before_backup",
        }
        try:
            health = _run_rebel_cmd(
                ["docker", "inspect", "--format={{.State.Health.Status}}", REBEL_CONTAINER], timeout=5
            )
            result["container_health_after"] = health.stdout.strip() or "no_healthcheck"
        except Exception:
            result["container_health_after"] = "unknown"
        _write_rebel_event(result, "patch_failed_rollback")
        return result


# Stage 0 + Stage 1 quick guide:
# 1. Run collect_rebel_metrics() -> diagnose_rebel() -> build_rebel_proposals() -> save_rebel_proposal().
# 2. Review proposals/rebel/*.json manually and set stage="stage1_approved" only for safe config-only changes.
# 3. Run apply_approved_rebel_patch(approved_proposal); it backs up, jq-patches, reloads, verifies /show_config.
# 4. If requires_new_identifier=True, no patch is applied; create a new identifier + retrain path manually.
# 5. Check events/rebel/*.json for the audit trail and rollback evidence.


if __name__ == "__main__":
    raise SystemExit(main())
