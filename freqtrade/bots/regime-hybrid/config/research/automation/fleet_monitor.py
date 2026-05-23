#!/usr/bin/env python3
"""Research Fleet Monitor / Self-Optimization Advisor v0.2.

Read-only central monitor for the 72h dry-run hardening sprint.

What it does:
- Reads Freqtrade dry-run SQLite DBs via docker exec.
- Reads ai-hedge canonical signal and Regime-Hybrid historical archive metadata.
- Exports recent closed trades needed for rolling 12h/24h metrics.
- Runs the proposal-only self_optimizer layer.

What it deliberately does NOT do:
- No live trading.
- No dry_run=false changes.
- No config mutation.
- No automatic bot pause/restart/stake write.

The output is advisory. Human approval is required before any action that changes
bot configs, strategy files, containers, or position state.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("/home/hermes/projects/trading")
AUTOMATION_DIR = ROOT / "freqtrade/bots/regime-hybrid/config/research/automation"
DEFAULT_OPT_OUTPUT = AUTOMATION_DIR / "latest_self_optimization_proposals.json"

# Allow direct execution without installing this research module.
sys.path.insert(0, str(AUTOMATION_DIR))
try:
    import self_optimizer
except Exception:  # pragma: no cover - reported in JSON at runtime
    self_optimizer = None  # type: ignore[assignment]

BOT_SPECS: dict[str, dict[str, Any]] = {
    "freqforge-main": {
        "container": "freqtrade-freqforge",
        "role": "candidate_core",
        "db_paths": [
            "/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite",
            "/freqtrade/tradesv3.dryrun.sqlite",
        ],
    },
    "regime-hybrid": {
        "container": "freqtrade-regime-hybrid",
        "role": "research_candidate_v3_pending",
        "db_paths": ["/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite"],
    },
    "momentum": {
        "container": "freqtrade-momentum",
        "role": "weak_quarantine_candidate",
        "db_paths": [
            "/freqtrade/tradesv3.dryrun.sqlite",
            "/freqtrade/user_data/tradesv3.momentum.dryrun.sqlite",
        ],
    },
    "freqforge-canary": {
        "container": "freqtrade-freqforge-canary",
        "role": "top_candidate_canary",
        "db_paths": ["/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"],
    },
    "freqai-rebel": {
        "container": "freqai-rebel",
        "role": "ml_high_uncertainty",
        "db_paths": [
            "/freqtrade/tradesv3.dryrun.sqlite",
            "/freqtrade/user_data/tradesv3.dryrun.sqlite",
        ],
    },
}

DB_QUERY = r'''
import sqlite3, json, sys
path = sys.argv[1]
try:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("select name from sqlite_master where type='table' and name='trades'")
    if not cur.fetchone():
        print(json.dumps({'error': 'no_trades_table', 'path': path}))
        sys.exit(0)

    cur.execute("PRAGMA table_info(trades)")
    columns = {row['name'] for row in cur.fetchall()}
    has_is_short = 'is_short' in columns
    has_enter_tag = 'enter_tag' in columns
    has_exit_reason = 'exit_reason' in columns
    has_stake_amount = 'stake_amount' in columns

    cur.execute("""
        select count(*) total,
               coalesce(sum(case when is_open=0 then 1 else 0 end),0) closed,
               coalesce(sum(case when is_open=1 then 1 else 0 end),0) open
        from trades
    """)
    res = {'path': path, **dict(cur.fetchone())}

    cur.execute("""
        select count(*) trades,
               coalesce(sum(close_profit_abs),0) pnl_abs,
               coalesce(sum(case when close_profit_abs > 0 then close_profit_abs else 0 end),0) gross_win_abs,
               abs(coalesce(sum(case when close_profit_abs < 0 then close_profit_abs else 0 end),0)) gross_loss_abs,
               coalesce(sum(case when close_profit > 0 then 1 else 0 end),0) wins,
               coalesce(sum(case when close_profit < 0 then 1 else 0 end),0) losses,
               avg(case when close_profit > 0 then close_profit_abs end) avg_win_abs,
               avg(case when close_profit < 0 then close_profit_abs end) avg_loss_abs
        from trades where is_open=0
    """)
    res['overall'] = dict(cur.fetchone())

    def window_stats(hours):
        cur.execute(f"""
            select count(*) trades,
                   coalesce(sum(close_profit_abs),0) pnl_abs,
                   coalesce(sum(case when close_profit_abs > 0 then close_profit_abs else 0 end),0) gross_win_abs,
                   abs(coalesce(sum(case when close_profit_abs < 0 then close_profit_abs else 0 end),0)) gross_loss_abs,
                   coalesce(sum(case when close_profit > 0 then 1 else 0 end),0) wins,
                   coalesce(sum(case when close_profit < 0 then 1 else 0 end),0) losses
            from trades where is_open=0 and close_date > datetime('now','-{int(hours)} hours')
        """)
        return dict(cur.fetchone())

    res['last12h'] = window_stats(12)
    res['last24h'] = window_stats(24)

    is_short_expr = 'is_short' if has_is_short else '0 as is_short'
    enter_tag_expr = 'enter_tag' if has_enter_tag else "'' as enter_tag"
    exit_reason_expr = 'exit_reason' if has_exit_reason else "'' as exit_reason"
    stake_expr = 'stake_amount' if has_stake_amount else '0 as stake_amount'

    cur.execute(f"""
        select id, pair, {is_short_expr}, {stake_expr}, open_rate, open_date, {enter_tag_expr}
        from trades where is_open=1 order by open_date desc limit 20
    """)
    res['open_trades'] = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        select id, pair, {is_short_expr}, {stake_expr}, open_rate, close_rate,
               open_date, close_date, close_profit, close_profit_abs,
               {enter_tag_expr}, {exit_reason_expr}
        from trades
        where is_open=0 and close_date > datetime('now','-24 hours')
        order by close_date asc
        limit 300
    """)
    res['recent_closed_trades'] = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        select id, pair, {is_short_expr}, {stake_expr}, open_rate, close_rate,
               open_date, close_date, close_profit, close_profit_abs,
               {enter_tag_expr}, {exit_reason_expr}
        from trades
        where is_open=0
        order by close_date desc
        limit 300
    """)
    res['last_closed_trades'] = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        select {exit_reason_expr}, count(*) n, coalesce(sum(close_profit_abs),0) pnl_abs,
               coalesce(sum(case when close_profit > 0 then 1 else 0 end),0) wins
        from trades where is_open=0 group by {exit_reason_expr} order by pnl_abs asc
    """)
    res['exit_breakdown'] = [dict(r) for r in cur.fetchall()]
    print(json.dumps(res, default=str))
except Exception as exc:
    print(json.dumps({'error': str(exc), 'path': path}))
'''


def run(cmd: str, timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"rc": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    except Exception as exc:
        return {"rc": 999, "stdout": "", "stderr": str(exc)}


def docker_query_db(container: str, db_paths: list[str]) -> dict[str, Any]:
    encoded = base64.b64encode(DB_QUERY.encode()).decode()
    attempts = []
    for db_path in db_paths:
        cmd = f"echo {encoded} | base64 -d | docker exec -i {container} python3 - {db_path}"
        result = run(cmd, timeout=20)
        attempts.append({"db_path": db_path, "rc": result["rc"], "stderr": result["stderr"][:200]})
        if result["rc"] != 0 or not result["stdout"]:
            continue
        try:
            data = json.loads(result["stdout"].splitlines()[-1])
        except Exception as exc:
            attempts[-1]["parse_error"] = str(exc)
            continue
        if "error" not in data:
            data["selected_db"] = db_path
            return data
        attempts[-1]["db_error"] = data.get("error")
    return {"error": "no_working_db", "attempts": attempts}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def signal_snapshot() -> dict[str, Any]:
    canonical = ROOT / "ai-hedge-fund-crypto/output/hermes_signal.json"
    primo = ROOT / "freqtrade/shared/primo_signal_state.json"
    archive = ROOT / "freqtrade/bots/regime-hybrid/user_data/signals/historical_signals.jsonl"
    out: dict[str, Any] = {}
    now = time.time()
    for key, path in {"canonical": canonical, "primo_state": primo}.items():
        item = {"path": str(path), "exists": path.exists()}
        if path.exists():
            item["mtime_age_min"] = round((now - path.stat().st_mtime) / 60, 2)
            data = read_json(path)
            item["timestamp_utc"] = data.get("timestamp_utc") or data.get("generated_at")
            item["fresh"] = data.get("fresh")
            item["pairs"] = data.get("pairs") or {}
        out[key] = item
    arch = {"path": str(archive), "exists": archive.exists()}
    if archive.exists():
        lines = [ln for ln in archive.read_text().splitlines() if ln.strip()]
        arch["records"] = len(lines)
        arch["size_bytes"] = archive.stat().st_size
        if lines:
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            arch["first_ts"] = first.get("timestamp_utc")
            arch["last_ts"] = last.get("timestamp_utc")
            arch["last_pairs"] = len((last.get("data") or {}).get("pairs") or {})
            arch["last_fresh"] = (last.get("data") or {}).get("fresh")
            arch["last_data"] = last.get("data") or {}
    out["historical_archive"] = arch
    return out


def _profit_factor(overall: dict[str, Any]) -> float:
    gross_win = float(overall.get("gross_win_abs") or 0.0)
    gross_loss = float(overall.get("gross_loss_abs") or 0.0)
    if gross_loss > 0:
        return gross_win / gross_loss
    if gross_win > 0:
        return 999.0
    return 0.0


def bot_decision(label: str, spec: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data:
        return {"verdict": "ERROR", "risk": "high", "proposals": ["inspect_db_path_or_container"]}
    overall = data.get("overall") or {}
    last24 = data.get("last24h") or {}
    trades = int(overall.get("trades") or 0)
    wins = int(overall.get("wins") or 0)
    pnl = float(overall.get("pnl_abs") or 0.0)
    pf = _profit_factor(overall)
    wr = wins / trades if trades else 0.0
    last24_pnl = float(last24.get("pnl_abs") or 0.0)
    open_count = int(data.get("open") or 0)

    proposals: list[str] = []
    risk = "medium"
    verdict = "WATCH"

    if label in {"freqforge-canary", "freqforge-main"} and pnl > 0 and pf > 1.2 and wr > 0.75:
        verdict = "TOP_CANDIDATE"
        risk = "medium" if open_count else "low"
        proposals.append("keep_running_dry_run_observe_open_risk")
    if label == "regime-hybrid":
        verdict = "RESEARCH_REBUILD_REQUIRED"
        risk = "medium"
        proposals.append("use_v3_research_loader_not_old_live_strategy")
    if pnl < 0 or pf < 1.0:
        verdict = "UNDERPERFORMING"
        risk = "high" if pnl < -5 or pf < 0.75 else "medium"
        proposals.append("reduce_stake_or_pause_entries_pending_approval")
    if last24_pnl < -0.5:
        proposals.append("last24h_loss_alert_review_now")
    if label == "momentum" and pnl < 0:
        proposals.append("candidate_kill_switch_max_open_trades_0_if_user_approves")
    if label == "freqai-rebel" and wr < 0.4:
        proposals.append("ml_quality_gate_check_predictions_pkl_before_any_live")
    if trades < 20:
        proposals.append("insufficient_sample_size_do_not_promote_live")
    if open_count:
        proposals.append("monitor_open_positions_no_forced_exit_without_approval")

    return {
        "verdict": verdict,
        "risk": risk,
        "profit_factor": round(pf, 4) if pf != 999.0 else "inf",
        "winrate_pct": round(wr * 100, 2),
        "proposals": sorted(set(proposals)),
    }


def collect(*, run_optimizer: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "fleet_monitor_research_v0.2",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "read_only_advisory",
        "live_trading_allowed": False,
        "signals": signal_snapshot(),
        "bots": {},
    }
    for label, spec in BOT_SPECS.items():
        data = docker_query_db(spec["container"], spec["db_paths"])
        decision = bot_decision(label, spec, data)
        report["bots"][label] = {
            "container": spec["container"],
            "role": spec["role"],
            "data": data,
            "decision": decision,
        }

    if run_optimizer:
        if self_optimizer is None:
            report["self_optimizer_error"] = "self_optimizer import failed"
        else:
            try:
                report["self_optimizer"] = self_optimizer.optimize(report, update_state=True)
            except Exception as exc:
                report["self_optimizer_error"] = str(exc)
    return report


def compact_text(report: dict[str, Any]) -> str:
    lines = []
    lines.append(f"Fleet Monitor {report['timestamp_utc']} | mode={report['mode']} | schema={report.get('schema_version')}")
    sig = report.get("signals", {})
    canonical = sig.get("canonical", {})
    primo = sig.get("primo_state", {})
    archive = sig.get("historical_archive", {})
    lines.append(
        f"Signal: canonical_age={canonical.get('mtime_age_min')}m pairs={len(canonical.get('pairs') or {})} | "
        f"primo_age={primo.get('mtime_age_min')}m fresh={primo.get('fresh')} | archive_records={archive.get('records')}"
    )
    if report.get("self_optimizer"):
        opt = report["self_optimizer"]
        lines.append(
            f"SelfOpt: regime={opt.get('regime', {}).get('regime')} | proposals={opt.get('summary', {}).get('total_proposals')} "
            f"(crit={opt.get('summary', {}).get('critical')}, high={opt.get('summary', {}).get('high')}, med={opt.get('summary', {}).get('medium')})"
        )
    elif report.get("self_optimizer_error"):
        lines.append(f"SelfOpt: ERROR {report.get('self_optimizer_error')}")

    lines.append("Bot | Closed | Open | PnL | 24h Trades | 24h PnL | WR | PF | Verdict | SelfOpt")
    lines.append("---|---:|---:|---:|---:|---:|---:|---:|---|---")
    opt_bots = ((report.get("self_optimizer") or {}).get("bots") or {})
    for label, item in report["bots"].items():
        data = item["data"]
        decision = item["decision"]
        if "error" in data:
            lines.append(f"{label} | ERR | ERR | ERR | ERR | ERR | ERR | ERR | {decision['verdict']} | inspect")
            continue
        overall = data.get("overall") or {}
        last24 = data.get("last24h") or {}
        opt_item = opt_bots.get(label) or {}
        prop_types = [p.get("type") for p in (opt_item.get("proposals") or [])]
        selfopt_text = ";".join(prop_types) if prop_types else "no_action"
        lines.append(
            f"{label} | {data.get('closed')} | {data.get('open')} | {float(overall.get('pnl_abs') or 0):.4f} | "
            f"{last24.get('trades')} | {float(last24.get('pnl_abs') or 0):.4f} | "
            f"{decision.get('winrate_pct')}% | {decision.get('profit_factor')} | {decision['verdict']} | {selfopt_text}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Research fleet monitor / advisory self-optimization layer")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument("--output", help="Optional path to write JSON report")
    parser.add_argument("--optimization-output", default=str(DEFAULT_OPT_OUTPUT), help="Path to write self-optimization proposals JSON")
    parser.add_argument("--no-optimizer", action="store_true", help="Skip self_optimizer integration")
    args = parser.parse_args()

    report = collect(run_optimizer=not args.no_optimizer)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if report.get("self_optimizer") and args.optimization_output:
        opt_out = Path(args.optimization_output)
        opt_out.parent.mkdir(parents=True, exist_ok=True)
        opt_out.write_text(json.dumps(report["self_optimizer"], indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(compact_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
