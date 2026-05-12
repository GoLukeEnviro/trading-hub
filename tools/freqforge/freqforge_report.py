"""
FreqForge v0.1 — Markdown Report Generator

Reads shadow_decisions.jsonl and generates a structured markdown report.
Also copies JSONL to docs/context/ for archival.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from freqforge_config import (
    DECISIONS_JSONL, STATE_FILE, REPORT_MD, REPORT_DECISIONS,
    REPORT_DIR, VAR_DIR, SNAPSHOTS_DIR, BOTS, ensure_dirs,
)
from freqforge_rules import RULE_REGISTRY


def load_decisions() -> list[dict]:
    """Load all entries from the JSONL decision log."""
    if not DECISIONS_JSONL.exists():
        return []
    events = []
    with open(DECISIONS_JSONL) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def mask_secrets(val: str) -> str:
    """Mask token-like strings for display."""
    if not val:
        return val
    if len(val) > 8:
        return val[:4] + "***" + val[-4:]
    return "***"


def summarize_by_type(events: list[dict]) -> dict:
    """Group events by event_type."""
    by_type = defaultdict(list)
    for e in events:
        by_type[e.get("event_type", "unknown")].append(e)
    return dict(by_type)


def summarize_decisions(events: list[dict]) -> dict:
    """Count decisions by type."""
    counts = defaultdict(int)
    for e in events:
        counts[e.get("freqforge_decision", "unknown")] += 1
    return dict(counts)


def summarize_rules(events: list[dict]) -> dict:
    """Count how often each reason_code fired."""
    code_counts = defaultdict(int)
    for e in events:
        for code in e.get("reason_codes", []):
            code_counts[code] += 1
    return dict(sorted(code_counts.items(), key=lambda x: -x[1]))


def bot_status_table(events: list[dict]) -> list[dict]:
    """Build per-bot status rows."""
    by_bot = defaultdict(lambda: {"entries": 0, "exits": 0, "open_risk": 0, "errors": 0})
    for e in events:
        bot = e.get("bot_name", "unknown")
        t = e.get("event_type", "unknown")
        if t == "entry":
            by_bot[bot]["entries"] += 1
        elif t == "exit_review":
            by_bot[bot]["exits"] += 1
        elif t == "open_risk":
            by_bot[bot]["open_risk"] += 1
        elif t in ("poll_error", "poll_exception", "signal_missing"):
            by_bot[bot]["errors"] += 1

    rows = []
    for bot, counts in sorted(by_bot.items()):
        # Map container name to friendly name
        friendly = next((b.name for b in BOTS.values() if b.container == bot), bot)
        rows.append({
            "bot": friendly,
            "container": bot,
            "entries": counts["entries"],
            "exits_reviewed": counts["exits"],
            "open_risk_flags": counts["open_risk"],
            "errors": counts["errors"],
        })
    return rows


def example_events(events: list[dict], decision: str, n: int = 3) -> list[dict]:
    """Return N example events for a given decision type."""
    examples = [e for e in events if e.get("freqforge_decision") == decision]
    return examples[:n]


def generate_report(events: list[dict] | None = None) -> str:
    """Generate the full markdown report."""
    if events is None:
        events = load_decisions()

    ensure_dirs()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(events)

    if total == 0:
        return f"# FreqForge Shadow Signal Evaluator — Report\n\n_Generated: {now}_\n\n**No shadow decisions recorded yet.** Run `freqforge_shadow.py` first.\n"

    # ── Decision Distribution ────────────────────────────────
    by_type = summarize_by_type(events)
    by_decision = summarize_decisions(events)

    # ── Bot Status ────────────────────────────────────────────
    bot_rows = bot_status_table(events)

    # ── Rule Frequency ────────────────────────────────────────
    rule_counts = summarize_rules(events)

    # ── Examples ──────────────────────────────────────────────
    veto_examples = example_events(events, "veto")
    uncertain_examples = example_events(events, "uncertain")
    reduce_examples = example_events(events, "reduce_size")
    missed_risk_examples = example_events(events, "missed_risk")
    false_neg_examples = example_events(events, "false_negative_review")

    # ── Write JSONL to docs/context ──────────────────────────
    if REPORT_DECISIONS.parent.exists() or REPORT_DECISIONS.parent.name == "context":
        with open(REPORT_DECISIONS, "w") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ── Assemble Markdown ─────────────────────────────────────
    lines = []
    lines.append(f"# FreqForge Shadow Signal Evaluator — v0.1 Report")
    lines.append(f"_Generated: {now} UTC_")
    lines.append("")

    # Executive Summary
    lines.append("## 1. Executive Summary")
    lines.append("")
    total_entries = len(by_type.get("entry", []))
    total_exit_reviews = len(by_type.get("exit_review", []))
    total_open_risk = len(by_type.get("open_risk", []))
    total_errors = sum(1 for e in events if e.get("event_type") in ("poll_error", "poll_exception"))
    veto_count = by_decision.get("veto", 0)
    uncertain_count = by_decision.get("uncertain", 0)
    reduce_count = by_decision.get("reduce_size", 0)
    lines.append(f"- **Total shadow events:** {total}")
    lines.append(f"  - New entries evaluated: {total_entries}")
    lines.append(f"  - Exit reviews: {total_exit_reviews}")
    lines.append(f"  - Open risk flags: {total_open_risk}")
    lines.append(f"  - Errors: {total_errors}")
    lines.append(f"- **Decision distribution:**")
    lines.append(f"  - `approve`: {by_decision.get('approve', 0)}")
    lines.append(f"  - `veto`: {veto_count}")
    lines.append(f"  - `uncertain`: {uncertain_count}")
    lines.append(f"  - `reduce_size`: {reduce_count}")
    lines.append(f"  - `missed_risk`: {by_decision.get('missed_risk', 0)}")
    lines.append(f"  - `false_negative_review`: {by_decision.get('false_negative_review', 0)}")
    lines.append("")
    lines.append("> **Shadow Mode: Active.** No trades were placed, modified, or cancelled by FreqForge v0.1.")
    lines.append("")

    # Container/Bot Status
    lines.append("## 2. Container & Bot Status")
    lines.append("")
    if bot_rows:
        lines.append("| Bot | Container | Entries | Exits Reviewed | Open Risk Flags | Errors |")
        lines.append("|-----|-----------|---------|----------------|-----------------|--------|")
        for r in bot_rows:
            lines.append(
                f"| {r['bot']} | `{r['container']}` | {r['entries']} | "
                f"{r['exits_reviewed']} | {r['open_risk_flags']} | {r['errors']} |"
            )
    else:
        lines.append("_No bot data yet._")
    lines.append("")

    # Decision Distribution
    lines.append("## 3. Decision Distribution")
    lines.append("")
    if by_decision:
        lines.append("| Decision | Count |")
        lines.append("|----------|-------|")
        for dec, cnt in sorted(by_decision.items(), key=lambda x: -x[1]):
            lines.append(f"| `{dec}` | {cnt} |")
    else:
        lines.append("_No decisions yet._")
    lines.append("")

    # Rule Frequency
    lines.append("## 4. Rule Trigger Frequency")
    lines.append("")
    if rule_counts:
        lines.append("| Code | Rule | Count |")
        lines.append("|------|------|-------|")
        for code, cnt in rule_counts.items():
            rule_text = RULE_REGISTRY.get(code, "Unknown rule")
            lines.append(f"| `{code}` | {rule_text} | {cnt} |")
    else:
        lines.append("_No rules triggered yet._")
    lines.append("")

    # Examples
    def render_example(e: dict) -> str:
        codes = ", ".join(f"`{c}`" for c in e.get("reason_codes", []))
        return (
            f"- **Pair:** `{e.get('pair', '')}` | **Bot:** {e.get('bot_name', '')} | "
            f"**Decision:** `{e.get('freqforge_decision', '')}`\n"
            f"  - Signal: conf={e.get('signal_confidence')} bias={e.get('signal_bias')} "
            f"rec={e.get('signal_recommendation')}\n"
            f"  - Reason: {e.get('natural_language_reason', '')}\n"
            f"  - Triggered: {codes}"
        )

    if veto_examples:
        lines.append("## 5. Veto Examples")
        lines.append("")
        for e in veto_examples:
            lines.append(render_example(e))
        lines.append("")

    if uncertain_examples:
        lines.append("## 6. Uncertain Examples")
        lines.append("")
        for e in uncertain_examples[:3]:
            lines.append(render_example(e))
        lines.append("")

    if reduce_examples:
        lines.append("## 7. Reduce Size Examples")
        lines.append("")
        for e in reduce_examples:
            lines.append(render_example(e))
        lines.append("")

    if missed_risk_examples or false_neg_examples:
        lines.append("## 8. Exit Review — Notable Cases")
        lines.append("")
        if missed_risk_examples:
            lines.append(f"### 8.1 Missed Risk ({len(missed_risk_examples)} cases)")
            lines.append("")
            lines.append("Trades that lost despite shadow approval — rules may need tightening.")
            lines.append("")
            for e in missed_risk_examples[:3]:
                pnl = e.get("close_profit")
                pnl_str = f"{pnl*100:+.2f}%" if pnl is not None else "unknown"
                lines.append(
                    f"- **{e.get('pair', '')}** on {e.get('bot_name', '')} "
                    f"closed {pnl_str}. "
                    f"Shadow had `{e.get('entry_shadow_decision', 'N/A')}` at entry."
                )
            lines.append("")
        if false_neg_examples:
            lines.append(f"### 8.2 False Negatives ({len(false_neg_examples)} cases)")
            lines.append("")
            lines.append("Trades that won despite shadow veto/uncertain — rules may be too strict.")
            lines.append("")
            for e in false_neg_examples[:3]:
                pnl = e.get("close_profit")
                pnl_str = f"{pnl*100:+.2f}%" if pnl is not None else "unknown"
                lines.append(
                    f"- **{e.get('pair', '')}** on {e.get('bot_name', '')} "
                    f"closed {pnl_str}. Shadow was `{e.get('freqforge_decision', '')}`."
                )
            lines.append("")

    # Risk Assessment
    lines.append("## 9. Risk Assessment")
    lines.append("")
    high_risk = veto_count > total * 0.5 and total > 5
    if high_risk:
        lines.append("⚠️ **Elevated veto rate detected.** More than 50% of signals are vetoed. "
                    "Review rule thresholds and signal quality.")
    elif veto_count > 0:
        lines.append("✅ **Veto rate within expected range.** Shadow layer is functioning correctly.")
    else:
        lines.append("ℹ️ **No vetoes yet.** Signal quality and rule calibration ongoing.")
    lines.append("")

    # Limitations
    lines.append("## 10. Limitations & Known Gaps")
    lines.append("")
    lines.append("| Limitation | Description |")
    lines.append("|------------|-------------|")
    lines.append("| No current price feed | Open trade PnL is estimated (0.0%) — requires market data API for real-time PnL |")
    lines.append("| SQLite polling interval | Events detected on next poll run; brief window between entry and evaluation |")
    lines.append("| Entry timing | Entry decision made after trade is already open (shadow only, not predictive) |")
    lines.append("| Rule granularity | E1/E2 produce identical `uncertain` — rules are descriptive, not yet weighted |")
    lines.append("| RSI/Momentum bots | DB paths may differ from mapped paths — verify on first smoke test |")
    lines.append("")

    # Files
    lines.append("## 11. Output Files")
    lines.append("")
    lines.append(f"- **Decision log (append-only):** `{DECISIONS_JSONL}`")
    lines.append(f"- **State file:** `{STATE_FILE}`")
    lines.append(f"- **Snapshots:** `{SNAPSHOTS_DIR}/`")
    lines.append(f"- **This report:** `{REPORT_MD}`")
    lines.append(f"- **Archived decisions:** `{REPORT_DECISIONS}`")
    lines.append("")

    # Recommendation
    lines.append("## 12. Recommendation")
    lines.append("")
    lines.append("FreqForge v0.1 is functioning as a **passive shadow evaluator**.")
    if total < 10:
        lines.append("Collect more samples before drawing conclusions. Run the 12-hour observation plan.")
    else:
        if by_decision.get("missed_risk", 0) > by_decision.get("false_negative_review", 0):
            lines.append("⚠️ More missed risks than false negatives — rules may be too lenient.")
        elif by_decision.get("false_negative_review", 0) > by_decision.get("missed_risk", 0):
            lines.append("⚠️ More false negatives than missed risks — rules may be too strict.")
        else:
            lines.append("✅ Rule calibration appears balanced. Continue observation.")
    lines.append("")
    lines.append("**Next steps:**")
    lines.append("1. Run 12-hour observation plan (Phase 4)")
    lines.append("2. Calibrate PnL calculation (requires market price feed)")
    lines.append("3. Add cron scheduling for automated polling")
    lines.append("4. Review RSI/Momentum DB paths after first poll")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_report()
    print(report)
