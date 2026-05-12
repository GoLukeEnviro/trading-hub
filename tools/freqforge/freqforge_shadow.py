#!/usr/bin/env python3
"""
FreqForge v0.1 — Shadow Signal Evaluator Main Loop

Reads Freqtrade dry-run trade state via docker exec sqlite3,
compares with ai-hedge-fund-crypto signal, applies deterministic rules,
logs decisions to append-only JSONL.

Usage:
    python3 tools/freqforge/freqforge_shadow.py              # single poll
    python3 tools/freqforge/freqforge_shadow.py --report     # poll + generate report
    python3 tools/freqforge/freqforge_shadow.py --report-only # report from existing JSONL
"""

import json
import sys
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from freqforge_config import (
    BOTS, BotDef, VAR_DIR, DECISIONS_JSONL, STATE_FILE,
    SIGNAL_FILE, ensure_dirs, normalize_pair,
    DECISION_APPROVE, DECISION_VETO, DECISION_UNCERTAIN,
    DECISION_REDUCE_SIZE, DECISION_FALSE_NEGATIVE,
    DECISION_VETO_HELPED, DECISION_MISSED_RISK,
)
from freqforge_rules import (
    SignalData, SignalDeck, RuleResult,
    evaluate_entry, evaluate_open_risk, evaluate_exit,
)


# ── SQLite Queries ───────────────────────────────────────────

SQL_ALL_TRADES = """
SELECT
    id, pair, stake_amount, open_rate, close_rate,
    open_date, close_date, close_profit, close_profit_abs,
    is_open, enter_tag, exit_reason, amount,
    CASE WHEN amount > 0 AND open_rate > 0 THEN 'long' ELSE 'short' END as direction
FROM trades
ORDER BY id
"""

SQL_OPEN_TRADES = """
SELECT
    id, pair, stake_amount, open_rate,
    open_date, is_open, enter_tag, amount,
    CASE WHEN amount > 0 AND open_rate > 0 THEN 'long' ELSE 'short' END as direction
FROM trades WHERE is_open = 1
ORDER BY id
"""

SQL_CLOSED_TRADES = """
SELECT
    id, pair, stake_amount, open_rate, close_rate,
    open_date, close_date, close_profit, close_profit_abs,
    is_open, exit_reason, amount,
    CASE WHEN amount > 0 AND open_rate > 0 THEN 'long' ELSE 'short' END as direction
FROM trades WHERE is_open = 0
ORDER BY id
"""


# ── Docker Exec Helper ───────────────────────────────────────

def docker_exec_sqlite(container: str, db_path: str, sql: str) -> Optional[List[Dict]]:
    """Execute SQLite query inside a container via docker exec.
    
    Returns list of dicts or None on error.
    """
    cmd = [
        "docker", "exec", container,
        "sqlite3", "-json", db_path, sql
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        output = result.stdout.strip()
        if not output or output == "[]":
            return []
        return json.loads(output)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return None


def docker_exec_sqlite_raw(container: str, db_path: str, sql: str) -> str:
    """Execute SQLite query, return raw stdout (for simple counts)."""
    cmd = [
        "docker", "exec", container,
        "sqlite3", db_path, sql
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""


# ── Signal File Reader ───────────────────────────────────────

def load_signal_deck() -> Optional[SignalDeck]:
    """Load and parse the ai-hedge-fund-crypto signal file."""
    if not SIGNAL_FILE.exists():
        return None
    try:
        with open(SIGNAL_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    pairs = {}
    for pair_key, pair_data in data.get("pairs", {}).items():
        pairs[pair_key] = SignalData(
            pair=pair_key,
            bias=pair_data.get("bias", "neutral"),
            confidence=pair_data.get("confidence", 0.0),
            recommendation=pair_data.get("recommendation", "observe"),
            action=pair_data.get("action", "hold"),
            reason=pair_data.get("reason", ""),
        )

    return SignalDeck(
        pairs=pairs,
        global_risk_mode=data.get("global_risk_mode", "neutral"),
    )


# ── State Management ─────────────────────────────────────────

def load_state() -> Dict:
    """Load previous poll state (known trade IDs)."""
    if not STATE_FILE.exists():
        return {"known_open_ids": {}, "known_closed_ids": {}, "entry_decisions": {}}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"known_open_ids": {}, "known_closed_ids": {}, "entry_decisions": {}}


def save_state(state: Dict):
    """Persist current state for change detection."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── JSONL Logger ─────────────────────────────────────────────

def append_decision(event: Dict):
    """Append one decision event to the JSONL log."""
    DECISIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(DECISIONS_JSONL, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Core Poll Logic ──────────────────────────────────────────

def build_event(
    bot_key: str,
    bot: BotDef,
    trade: Dict,
    event_type: str,
    decision: str,
    reason_codes: List[str],
    reason_text: str,
    signal: Optional[SignalData],
    signal_deck: SignalDeck,
    extra: Optional[Dict] = None,
) -> Dict:
    """Build a JSONL event record."""
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "timestamp_utc": now,
        "event_id": f"{bot_key}_{event_type}_{trade.get('id', 'unknown')}",
        "bot_name": bot.container,
        "pair": trade.get("pair", ""),
        "timeframe": bot.timeframe,
        "side": trade.get("direction", "unknown"),
        "event_type": event_type,
        "strategy_name": bot.strategy,
        "price": trade.get("open_rate") or trade.get("close_rate"),
        "stake_amount": trade.get("stake_amount"),
        "signal_confidence": signal.confidence if signal else None,
        "signal_bias": signal.bias if signal else None,
        "signal_recommendation": signal.recommendation if signal else None,
        "global_risk_mode": signal_deck.global_risk_mode,
        "freqforge_decision": decision,
        "reason_codes": reason_codes,
        "natural_language_reason": reason_text,
        "no_action_taken": True,
        "shadow_mode": True,
    }
    if extra:
        event.update(extra)
    return event


def count_fleet_open(state: Dict) -> int:
    """Count total open trades across fleet from state."""
    return sum(state.get("known_open_ids", {}).values())


def poll_bot(bot_key: str, bot: BotDef, state: Dict,
             signal_deck: SignalDeck, events: List[Dict]) -> int:
    """Poll one bot, detect changes, evaluate rules, log decisions.
    
    Returns number of new events generated.
    """
    new_events = 0

    # Query all trades from bot
    all_trades = docker_exec_sqlite(bot.container, bot.db_path, SQL_ALL_TRADES)
    if all_trades is None:
        # DB error — log and skip
        append_decision({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_id": f"{bot_key}_poll_error",
            "bot_name": bot.container,
            "event_type": "poll_error",
            "freqforge_decision": "uncertain",
            "reason_codes": ["DB_ERROR"],
            "natural_language_reason": f"Could not query {bot.container} SQLite",
            "no_action_taken": True,
            "shadow_mode": True,
        })
        return 0

    known_open = state.get("known_open_ids", {})
    known_closed = state.get("known_closed_ids", {})
    entry_decisions = state.get("entry_decisions", {})

    # Index trades
    open_trades = {t["id"]: t for t in all_trades if t.get("is_open") == 1}
    closed_trades = {t["id"]: t for t in all_trades if t.get("is_open") == 0}

    bot_open_key = f"{bot_key}"
    prev_open_count = known_open.get(bot_open_key, 0)
    prev_closed_count = known_closed.get(bot_open_key, 0)

    # ── Detect NEW entries ───────────────────────────────────
    for tid, trade in open_trades.items():
        entry_key = f"{bot_key}_{tid}"
        if entry_key not in entry_decisions:
            # New trade — evaluate entry rules
            pair = trade.get("pair", "")
            side = trade.get("direction", "long")
            signal = signal_deck.get_signal(pair)

            result = evaluate_entry(
                trade_pair=pair,
                trade_side=side,
                signal=signal,
                signal_deck=signal_deck,
            )

            event = build_event(
                bot_key, bot, trade, "entry",
                result.decision, result.reason_codes, result.reason_text,
                signal, signal_deck,
            )
            append_decision(event)
            events.append(event)
            new_events += 1

            # Store entry decision for later exit review
            entry_decisions[entry_key] = {
                "decision": result.decision,
                "reason_codes": result.reason_codes,
                "timestamp_utc": event["timestamp_utc"],
            }

    # ── Evaluate OPEN risk for all current open trades ───────
    fleet_open = sum(1 for _ in open_trades.values()) + count_fleet_open(state)
    # More accurate: count all open across fleet from all_trades
    total_fleet_open = 0
    for bk, b in BOTS.items():
        if bk == bot_key:
            total_fleet_open += len(open_trades)
        else:
            total_fleet_open += known_open.get(bk, 0)

    for tid, trade in open_trades.items():
        pair = trade.get("pair", "")
        side = trade.get("direction", "long")
        signal = signal_deck.get_signal(pair)

        # Estimate PnL (rough — we don't have current price from SQLite alone)
        # For open trades, we can't calculate exact PnL without current market price
        # So we set pnl_pct to 0.0 and note it as estimated
        pnl_pct = 0.0  # Would need current price to calculate

        # Estimate duration in candles
        open_date_str = trade.get("open_date", "")
        candles = 0
        if open_date_str:
            try:
                open_dt = datetime.fromisoformat(open_date_str.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - open_dt
                candles = int(delta.total_seconds() / (15 * 60))  # 15m candles
            except (ValueError, TypeError):
                candles = 999

        result = evaluate_open_risk(
            trade_pair=pair,
            trade_side=side,
            pnl_pct=pnl_pct,
            open_duration_candles=candles,
            fleet_open_count=total_fleet_open,
            signal=signal,
            signal_deck=signal_deck,
        )

        # Only log open_risk events if there's a non-approve finding
        if result.decision != DECISION_APPROVE:
            event = build_event(
                bot_key, bot, trade, "open_risk",
                result.decision, result.reason_codes, result.reason_text,
                signal, signal_deck,
                {"open_duration_candles": candles, "pnl_pct_estimated": pnl_pct},
            )
            append_decision(event)
            events.append(event)
            new_events += 1

    # ── Detect NEW exits (post-hoc review) ───────────────────
    for tid, trade in closed_trades.items():
        entry_key = f"{bot_key}_{tid}"
        close_profit = trade.get("close_profit")
        was_known = entry_key in entry_decisions

        # Check if we already reviewed this exit
        exit_review_key = f"exit_reviewed_{entry_key}"
        if exit_review_key in entry_decisions:
            continue

        if close_profit is not None and was_known:
            prior = entry_decisions[entry_key]
            result = evaluate_exit(
                trade_pair=trade.get("pair", ""),
                close_profit=close_profit,
                entry_shadow_decision=prior.get("decision"),
                entry_shadow_codes=prior.get("reason_codes", []),
            )

            event = build_event(
                bot_key, bot, trade, "exit_review",
                result.decision, result.reason_codes, result.reason_text,
                signal_deck.get_signal(trade.get("pair", "")),
                signal_deck,
                {
                    "close_profit": close_profit,
                    "close_profit_abs": trade.get("close_profit_abs"),
                    "exit_reason": trade.get("exit_reason"),
                    "entry_shadow_decision": prior.get("decision"),
                },
            )
            append_decision(event)
            events.append(event)
            new_events += 1

            # Mark as reviewed
            entry_decisions[exit_review_key] = True

    # ── Update state ─────────────────────────────────────────
    known_open[bot_open_key] = len(open_trades)
    known_closed[bot_open_key] = len(closed_trades)

    state["known_open_ids"] = known_open
    state["known_closed_ids"] = known_closed
    state["entry_decisions"] = entry_decisions

    return new_events


# ── Main Entry Point ─────────────────────────────────────────

def run_poll() -> Dict:
    """Execute one complete poll cycle across all bots.
    
    Returns summary dict with counts.
    """
    ensure_dirs()
    
    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "poll_timestamp_utc": now,
        "bots_polled": 0,
        "bots_errors": 0,
        "new_events": 0,
        "events": [],
    }

    # Load signal deck
    signal_deck = load_signal_deck()
    if signal_deck is None:
        append_decision({
            "timestamp_utc": now,
            "event_id": "global_signal_missing",
            "event_type": "signal_missing",
            "freqforge_decision": "uncertain",
            "reason_codes": ["NO_SIGNAL_FILE"],
            "natural_language_reason": f"Signal file not found or unreadable: {SIGNAL_FILE}",
            "no_action_taken": True,
            "shadow_mode": True,
        })
        # Continue with empty signal deck
        signal_deck = SignalDeck(pairs={}, global_risk_mode="neutral")

    # Load state
    state = load_state()
    state.setdefault("known_open_ids", {})
    state.setdefault("known_closed_ids", {})
    state.setdefault("entry_decisions", {})

    # Poll each bot
    for bot_key, bot in BOTS.items():
        try:
            n = poll_bot(bot_key, bot, state, signal_deck, summary["events"])
            summary["new_events"] += n
            summary["bots_polled"] += 1
        except Exception as e:
            summary["bots_errors"] += 1
            append_decision({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event_id": f"{bot_key}_exception",
                "bot_name": bot.container,
                "event_type": "poll_exception",
                "freqforge_decision": "uncertain",
                "reason_codes": ["EXCEPTION"],
                "natural_language_reason": f"Unexpected error: {str(e)[:200]}",
                "no_action_taken": True,
                "shadow_mode": True,
            })

    # Save state
    save_state(state)

    # Append poll summary marker
    summary["signal_deck_pairs"] = list(signal_deck.pairs.keys()) if signal_deck else []
    summary["signal_global_risk_mode"] = signal_deck.global_risk_mode if signal_deck else "unknown"

    return summary


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    report_only = "--report-only" in args
    do_report = "--report" in args or report_only

    if report_only:
        from freqforge_report import generate_report
        report = generate_report()
        print(report)
    else:
        summary = run_poll()
        print(json.dumps(summary, indent=2, ensure_ascii=False))

        if do_report:
            from freqforge_report import generate_report
            report = generate_report()
            print("\n" + "="*60)
            print(report)
