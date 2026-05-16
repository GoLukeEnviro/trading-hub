#!/usr/bin/env python3
"""
Momentum Strategy Optimization Loop
=====================================
Hermes-orchestrierter Loop: Claude Code schreibt Strategy → Hermes startet Backtest →
Analyse → bei FAIL: Claude Code bekommt Ergebnisse + "fix es" → naechste Iteration.

Quality Gates (muessen BEIDE erfuellt sein):
  - Winrate >= 55%
  - Total Profit > 0 USDT

Max Iterationen: 5
Start: v3.1 (52.7% WR, -$50.00)
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# === CONFIG ===
MAX_ITERATIONS = 5
BASE_STRATEGY = "momentum_bg15_v3_1"  # start from this (lowercase filename!)
STRATEGY_DIR = "/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/strategies"
CONTAINER = "freqtrade-regime-hybrid"
BACKTEST_CONFIG = "/freqtrade/user_data/momentum_v2_backtest.json"
TIMERANGE = "20250401-20260511"
TIMEFRAME = "15m"
STRATEGY_CLASS = "MomentumBG15_v3_1"  # class name inside the file (CamelCase)

# Claude Code env
CLAUDE_ENV = {
    "PATH": f"{os.path.expanduser('~')}/.local/bin:{os.environ.get('PATH', '')}",
    "ANTHROPIC_AUTH_TOKEN": "17bee5a8f43f4b2884ba9bb9f2fdf1cc.tPvdmTjJpFOiNACq",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_TEMPERATURE": "0.3",
    "ANTHROPIC_TOP_P": "0.9",
}

# Quality gates
MIN_WINRATE = 55.0
MIN_PROFIT_USDT = 0.0

# === SHARED NOTES FILE (context between iterations) ===
NOTES_FILE = Path(STRATEGY_DIR) / "OPTIMIZATION_NOTES.md"


LOG_FILE = Path(STRATEGY_DIR) / "optimization_log.txt"


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def write_notes(content):
    """Write shared notes for cross-iteration context."""
    NOTES_FILE.write_text(content)
    log(f"Notes updated: {NOTES_FILE}")


def run_cmd(cmd, timeout=300, env_extra=None):
    """Run a shell command and return output."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, env=env
    )
    return result.stdout + result.stderr, result.returncode


def call_claude_code(prompt, workdir, max_turns=15):
    """Call Claude Code in print mode."""
    log("Calling Claude Code...")
    cmd = (
        f'cd {workdir} && claude -p {shell_quote(prompt)} '
        f'--allowedTools "Read,Write,Edit,Bash" '
        f'--max-turns {max_turns} '
        f'--model glm-5.1 '
        f'--output-format json'
    )
    log(f"CMD: claude -p ... (prompt {len(prompt)} chars)")
    output, rc = run_cmd(cmd, timeout=600, env_extra=CLAUDE_ENV)
    log(f"Claude Code returned: rc={rc}, output_len={len(output)}")
    if rc != 0:
        log(f"Claude Code error (rc={rc}): {output[:500]}")
        return None

    # Parse JSON output
    try:
        data = json.loads(output)
        result_text = data.get("result", output)
        session_id = data.get("session_id", "unknown")
        cost = data.get("total_cost_usd", 0)
        log(f"Claude Code done. Session: {session_id[:12]}... Cost: ${cost:.4f}")
        return result_text
    except json.JSONDecodeError:
        # Not JSON, return raw
        log(f"Claude Code done (raw output, {len(output)} chars)")
        return output


def shell_quote(s):
    """Quote a string for shell use."""
    import shlex
    return shlex.quote(s)


def run_backtest(strategy_name):
    """Run backtest in Docker container, return parsed results."""
    log(f"Running backtest: {strategy_name}...")

    # Clean pycache
    run_cmd(f"docker exec {CONTAINER} rm -rf /freqtrade/user_data/strategies/__pycache__/", timeout=10)

    # Run backtest
    cmd = (
        f'docker exec {CONTAINER} freqtrade backtesting '
        f'--config {BACKTEST_CONFIG} '
        f'--strategy {strategy_name} '
        f'--strategy-path /freqtrade/user_data/strategies '
        f'--timeframe {TIMEFRAME} '
        f'--timerange {TIMERANGE} 2>&1'
    )
    output, rc = run_cmd(cmd, timeout=300)

    if rc != 0 and "error" in output.lower():
        log(f"Backtest error: {output[:500]}")
        return None

    return parse_backtest_output(output)


def parse_backtest_output(output):
    """Parse freqtrade backtest output into structured data."""
    result = {
        "raw": output,
        "trades": 0, "winrate": 0.0, "total_profit_usdt": 0.0,
        "total_profit_pct": 0.0, "sharpe": 0.0, "drawdown_pct": 0.0,
        "profit_factor": 0.0, "sqn": 0.0,
        "per_pair": {}, "exit_reasons": {}, "long_short": {},
        "pass": False, "reason": ""
    }

    # Strategy summary line
    m = re.search(r'TOTAL.*?│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│.*?│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)', output)
    if m:
        result["trades"] = int(m.group(1))
        result["total_profit_pct"] = float(m.group(2))
        result["total_profit_usdt"] = float(m.group(3))
        result["winrate"] = float(m.group(7))

    # Summary metrics
    for pattern, key in [
        (r'Sharpe.*?│\s*([-\d.]+)', "sharpe"),
        (r'Profit factor.*?│\s*([-\d.]+)', "profit_factor"),
        (r'SQN.*?│\s*([-\d.]+)', "sqn"),
        (r'Absolute drawdown.*?│\s*[\d.]+\s*USDT\s*\(([\d.]+)%\)', "drawdown_pct"),
    ]:
        m = re.search(pattern, output)
        if m:
            result[key] = float(m.group(1))

    # Per-pair results
    pair_pattern = r'│\s*([A-Z]+/USDT:USDT)\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│.*?│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)'
    for m in re.finditer(pair_pattern, output):
        pair = m.group(1)
        result["per_pair"][pair] = {
            "trades": int(m.group(2)),
            "avg_profit_pct": float(m.group(3)),
            "total_profit_usdt": float(m.group(4)),
            "total_profit_pct": float(m.group(5)),
            "wins": int(m.group(6)),
            "losses": int(m.group(7)),
            "winrate": float(m.group(8)),
        }

    # Exit reasons
    exit_pattern = r'│\s*(roi|stop_loss|exit_signal|trailing_stop_loss)\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│'
    for m in re.finditer(exit_pattern, output, re.IGNORECASE):
        reason = m.group(1).strip()
        result["exit_reasons"][reason] = {
            "count": int(m.group(2)),
            "avg_profit_pct": float(m.group(3)),
            "total_profit_usdt": float(m.group(4)),
        }

    # Long/Short
    ls_pattern = r'Long\s*/\s*Short\s*trades.*?│\s*(\d+)\s*/\s*(\d+)'
    m = re.search(ls_pattern, output)
    if m:
        result["long_short"] = {"long": int(m.group(1)), "short": int(m.group(2))}

    # Quality gate
    gates = []
    if result["winrate"] < MIN_WINRATE:
        gates.append(f"WR {result['winrate']:.1f}% < {MIN_WINRATE}%")
    if result["total_profit_usdt"] < MIN_PROFIT_USDT:
        gates.append(f"Profit ${result['total_profit_usdt']:.2f} < ${MIN_PROFIT_USDT}")

    if not gates:
        result["pass"] = True
        result["reason"] = f"PASS: WR={result['winrate']:.1f}%, Profit=${result['total_profit_usdt']:.2f}"
    else:
        result["pass"] = False
        result["reason"] = f"FAIL: {', '.join(gates)}"

    return result


def format_results_for_claude(bt, iteration):
    """Format backtest results as context for Claude Code."""
    lines = [
        f"# Backtest Results — Iteration {iteration}",
        f"Strategy: MomentumBG15_v3_1 (iteration {iteration})",
        f"Timerange: {TIMERANGE} | Timeframe: {TIMEFRAME}",
        "",
        f"## Overall: {'PASS' if bt['pass'] else 'FAIL'}",
        f"- Trades: {bt['trades']}",
        f"- Winrate: {bt['winrate']:.1f}%",
        f"- Total Profit: ${bt['total_profit_usdt']:.2f} ({bt['total_profit_pct']:.2f}%)",
        f"- Sharpe: {bt['sharpe']:.2f}",
        f"- Profit Factor: {bt['profit_factor']:.2f}",
        f"- SQN: {bt['sqn']:.2f}",
        f"- Drawdown: {bt['drawdown_pct']:.2f}%",
        "",
        "## Per-Pair Results:",
    ]

    for pair, data in sorted(bt["per_pair"].items(), key=lambda x: x[1]["total_profit_usdt"], reverse=True):
        marker = "✓" if data["total_profit_usdt"] > 0 else "✗"
        lines.append(f"  {marker} {pair}: {data['trades']}t | {data['winrate']:.1f}% WR | ${data['total_profit_usdt']:.2f}")

    if bt["exit_reasons"]:
        lines.append("")
        lines.append("## Exit Reasons:")
        for reason, data in bt["exit_reasons"].items():
            lines.append(f"  {reason}: {data['count']}t, avg {data['avg_profit_pct']:+.2f}%, total ${data['total_profit_usdt']:.2f}")

    if bt["long_short"]:
        lines.append(f"\nLong/Short: {bt['long_short'].get('long', 0)}/{bt['long_short'].get('short', 0)}")

    lines.append(f"\n## Quality Gate: {bt['reason']}")

    return "\n".join(lines)


def copy_strategy_to_container(filename):
    """Copy strategy file into Docker container."""
    host_path = Path(STRATEGY_DIR) / filename
    container_path = f"/freqtrade/user_data/strategies/{filename}"
    cmd = f"docker cp {host_path} {CONTAINER}:{container_path}"
    output, rc = run_cmd(cmd, timeout=10)
    if rc != 0:
        log(f"Copy error: {output}")
        return False
    log(f"Copied {filename} to container")
    return True


def main():
    log("=" * 60)
    log("  MOMENTUM STRATEGY OPTIMIZATION LOOP")
    log(f"  Target: WR>={MIN_WINRATE}% AND Profit>${MIN_PROFIT_USDT}")
    log(f"  Max iterations: {MAX_ITERATIONS}")
    log("=" * 60)

    # Read the base strategy
    base_file = Path(STRATEGY_DIR) / f"{BASE_STRATEGY}.py"
    if not base_file.exists():
        log(f"ERROR: Base strategy not found: {base_file}")
        sys.exit(1)

    base_code = base_file.read_text()

    # Initialize shared notes
    initial_notes = f"""# Strategy Optimization Notes
## Starting Point: {BASE_STRATEGY}
- v3.1: 93t | 52.7% WR | -$50.00 | SL -3.0% | EMA200 trend filter
- Known profitable pairs: NEAR, AAVE, ETH, ATOM
- Known losing pairs: SOL, AVAX, ARB, OP, BTC, APT
- Problem: 6/10 pairs eat all profits from 4/10 profitable pairs
- ROI exits are 100% profitable, stoploss exits are 100% losing
"""
    write_notes(initial_notes)

    # Strategy filename stays the same — we overwrite each iteration
    strategy_filename = f"{BASE_STRATEGY}.py"
    strategy_class = STRATEGY_CLASS

    best_result = None
    best_iteration = 0

    for i in range(1, MAX_ITERATIONS + 1):
        log(f"\n{'='*60}")
        log(f"  ITERATION {i}/{MAX_ITERATIONS}")
        log(f"{'='*60}")

        # === STEP 1: Claude Code modifies strategy ===
        if i == 1:
            # First iteration: reduce pairs to profitable ones
            prompt = f"""Read the file {strategy_filename} in the current directory and create an improved version.

BACKTEST CONTEXT (what we know from previous runs):
{initial_notes}

YOUR TASK for iteration {i}:
Based on the backtest data, the biggest lever is PAIR SELECTION. 4/10 pairs are profitable (NEAR +$9.28, AAVE +$5.85, ETH +$1.88, ATOM +$1.76) while 6/10 are losing (AVAX -$17.50, SOL -$14.69, OP -$10.88, ARB -$9.64).

Make WHATEVER changes you think will make this strategy profitable. Options include but are not limited to:
1. Remove losing pairs from exchange whitelist (if configurable in strategy)
2. Add ADX > 20 filter to reduce weak-trend entries
3. Adjust ROI table for faster exits
4. Add volume filter
5. Change RSI thresholds
6. Any combination of the above

IMPORTANT RULES:
- Keep class name as {strategy_class}
- Keep FleetGuard and PrimoGate imports
- Keep EMA200 trend confirmation (it works!)
- Keep SL at -3.0% (it improved WR from 41.5% to 52.7%)
- The backtest config uses 10 pairs — you CANNOT change the pair list from the strategy side. Instead, make the ENTRY LOGIC smarter to reject bad pairs.
- Write the result to the SAME file: {strategy_filename}
- Update the docstring with your changes as CHANGE 6, CHANGE 7, etc.
- Also update the file {NOTES_FILE.name} with what you changed and why"""
        else:
            # Subsequent iterations: fix based on backtest results
            prompt = f"""Read {strategy_filename} and the notes file {NOTES_FILE.name}.

PREVIOUS BACKTEST RESULTS (iteration {i-1}):
{format_results_for_claude(prev_result, i-1)}

This strategy is still FAILING. Analyze WHY and make targeted changes.

Focus on the biggest levers:
- If specific pairs are losing badly → add filters to avoid trading them (e.g., skip pairs with ATR below/above threshold, or add pair-specific logic)
- If stoploss is still the main loss driver → consider adding a confirmation indicator before entry
- If WR is close to target but R/R is bad → adjust ROI table

IMPORTANT:
- Keep class name as {strategy_class}
- Keep FleetGuard, PrimoGate, EMA200 trend filter
- Document changes in docstring and update {NOTES_FILE.name}
- Write to {strategy_filename}"""

        claude_result = call_claude_code(prompt, STRATEGY_DIR, max_turns=20)

        if not claude_result:
            log("Claude Code failed, skipping iteration")
            continue

        log(f"Claude Code response: {claude_result[:300]}...")

        # === STEP 2: Copy to container and backtest ===
        if not copy_strategy_to_container(strategy_filename):
            log("Copy failed, skipping iteration")
            continue

        bt = run_backtest(strategy_class)

        if not bt:
            log("Backtest failed to parse")
            prev_result = {"trades": 0, "winrate": 0, "total_profit_usdt": -999, "pass": False,
                          "reason": "Backtest failed", "per_pair": {}, "exit_reasons": {},
                          "long_short": {}, "sharpe": 0, "profit_factor": 0, "sqn": 0, "drawdown_pct": 0}
            continue

        # === STEP 3: Evaluate ===
        log(f"\n  RESULT: {bt['trades']}t | {bt['winrate']:.1f}% WR | ${bt['total_profit_usdt']:.2f} | {bt['reason']}")

        # Track best result
        if best_result is None or bt['total_profit_usdt'] > best_result['total_profit_usdt']:
            best_result = bt
            best_iteration = i
            log(f"  NEW BEST (iteration {i})!")

        # Print per-pair summary
        for pair, data in sorted(bt["per_pair"].items(), key=lambda x: x[1]["total_profit_usdt"], reverse=True):
            marker = "✓" if data["total_profit_usdt"] > 0 else "✗"
            log(f"    {marker} {pair}: {data['trades']}t | {data['winrate']:.1f}% WR | ${data['total_profit_usdt']:.2f}")

        # Check quality gate
        if bt["pass"]:
            log(f"\n  *** QUALITY GATE PASSED at iteration {i}! ***")
            log(f"  WR: {bt['winrate']:.1f}% | Profit: ${bt['total_profit_usdt']:.2f}")
            break

        prev_result = bt
        log(f"  Gate not met. Continuing to iteration {i+1}...")

    # === FINAL REPORT ===
    log(f"\n{'='*60}")
    log(f"  OPTIMIZATION LOOP COMPLETE")
    log(f"{'='*60}")
    if best_result:
        log(f"  Best iteration: {best_iteration}")
        log(f"  {best_result['trades']}t | {best_result['winrate']:.1f}% WR | ${best_result['total_profit_usdt']:.2f}")
        log(f"  Sharpe: {best_result['sharpe']:.2f} | PF: {best_result['profit_factor']:.2f}")
        log(f"  Gate: {best_result['reason']}")
    else:
        log(f"  No valid results obtained")


if __name__ == "__main__":
    from shlex import quote as shell_quote_builtin
    shell_quote = shell_quote_builtin
    main()
