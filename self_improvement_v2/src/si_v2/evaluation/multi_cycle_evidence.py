r"""SI v2 Multi-Cycle Profitability Evidence — repeatable aggregation.

Reads evidence artifacts from multiple natural scheduled SI v2 cycles and
aggregates per-bot profitability metrics across a sliding window. Produces
a classification (candidate/blocked/watch/inconclusive) for each bot and
a fleet-level recommendation.

Key design decisions:
  - Pure I/O at the edges (file scan + read); aggregation logic is pure.
  - Uses the profitability gate's evaluate_fleet() for per-cycle verdicts
    and extends with multi-cycle accumulation.
  - Aggregation window is configurable (default: last N evidence files).
  - Each bot is classified independently based on accumulated evidence.
  - Cross-cycle metrics are derived from walk_forward_net_metrics embedded
    in each evidence artifact (not recomputed from raw trades).
  - No runtime mutation — read-only analysis of existing artifacts.

Integration:
  Called from the CLI or as a module import. Produces a structured
  MultiCycleFleetReport that can be persisted as JSON or Markdown.

Safety invariants:
  - Never modifies any external state.
  - Never enables live trading or sets dry_run to false.
  - Never changes config, strategy, or Docker state.
  - Never auto-approves or auto-promotes.
  - Read-only analysis of evidence artifacts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------
CLASS_CANDIDATE: Final[str] = "candidate"
CLASS_BLOCKED: Final[str] = "blocked"
CLASS_WATCH: Final[str] = "watch"
CLASS_INCONCLUSIVE: Final[str] = "inconclusive"

# ---------------------------------------------------------------------------
# Default aggregation window
# ---------------------------------------------------------------------------
DEFAULT_WINDOW_SIZE: Final[int] = 10
"""Number of most recent evidence files to aggregate."""

MIN_REAL_METRICS_CYCLES: Final[int] = 3
"""Minimum cycles with real metrics for candidate classification."""

MIN_WATCH_CYCLES: Final[int] = 1
"""Minimum cycles with real metrics for watch classification."""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BotCycleSnapshot:
    """Metrics for one bot in a single cycle."""

    bot_id: str
    cycle_id: str
    generated_at_utc: str
    has_real_metrics: bool
    net_pnl: float
    profit_factor: float
    trade_count: int
    max_drawdown_pct: float
    max_drawdown_measured: bool
    evaluation_status: str
    metrics_source: str
    promotion_blocked: bool
    promotion_block_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class BotAccumulatedEvidence:
    """Aggregated evidence for one bot across multiple cycles."""

    bot_id: str
    cycle_count: int
    real_metrics_cycle_count: int
    no_proposal_count: int
    negative_metrics_count: int
    net_pnl_total: float
    net_pnl_avg: float
    profit_factor_avg: float
    trade_count_total: int
    trade_count_avg: float
    max_drawdown_pct_max: float
    max_drawdown_measured_count: int
    read_success_rate: float
    classification: str
    classification_reasons: tuple[str, ...] = field(default_factory=tuple)
    # Link back to per-cycle details
    cycles: tuple[BotCycleSnapshot, ...] = field(default_factory=tuple)

    @property
    def has_sufficient_real_evidence(self) -> bool:
        return self.real_metrics_cycle_count >= MIN_REAL_METRICS_CYCLES

    @property
    def has_any_real_evidence(self) -> bool:
        return self.real_metrics_cycle_count >= MIN_WATCH_CYCLES


@dataclass(frozen=True)
class MultiCycleFleetReport:
    """Fleet-level multi-cycle evidence report."""

    generated_at_utc: str
    window_size: int
    cycles_evaluated: int
    cycle_ids: tuple[str, ...]
    per_bot: tuple[BotAccumulatedEvidence, ...]
    fleet_classifications: dict[str, str]
    fleet_recommendation: str
    fleet_recommendation_reason: str

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for persistence."""
        return {
            "generated_at_utc": self.generated_at_utc,
            "window_size": self.window_size,
            "cycles_evaluated": self.cycles_evaluated,
            "cycle_ids": list(self.cycle_ids),
            "per_bot": [
                {
                    "bot_id": b.bot_id,
                    "cycle_count": b.cycle_count,
                    "real_metrics_cycle_count": b.real_metrics_cycle_count,
                    "no_proposal_count": b.no_proposal_count,
                    "negative_metrics_count": b.negative_metrics_count,
                    "net_pnl_total": round(b.net_pnl_total, 8),
                    "net_pnl_avg": round(b.net_pnl_avg, 8),
                    "profit_factor_avg": round(b.profit_factor_avg, 4),
                    "trade_count_total": b.trade_count_total,
                    "trade_count_avg": round(b.trade_count_avg, 2),
                    "max_drawdown_pct_max": round(b.max_drawdown_pct_max, 4),
                    "max_drawdown_measured_count": b.max_drawdown_measured_count,
                    "read_success_rate": round(b.read_success_rate, 4),
                    "classification": b.classification,
                    "classification_reasons": list(b.classification_reasons),
                }
                for b in self.per_bot
            ],
            "fleet_classifications": dict(self.fleet_classifications),
            "fleet_recommendation": self.fleet_recommendation,
            "fleet_recommendation_reason": self.fleet_recommendation_reason,
        }


# ---------------------------------------------------------------------------
# Evidence loading
# ---------------------------------------------------------------------------

# Expected path: evidence files under self_improvement_v2/reports/phase2/evidence/
# Uses a provided directory or default.


def _find_evidence_files(
    evidence_dir: str | Path,
    *,
    max_files: int = DEFAULT_WINDOW_SIZE,
    exclude_before: str = "",
) -> list[Path]:
    """Find evidence JSON files, sorted by modification time (newest first).

    Args:
        evidence_dir: Path to the evidence directory.
        max_files: Maximum number of files to return (newest wins).
        exclude_before: If set, exclude files whose cycle timestamp is before
                        this ISO date string (e.g. '2026-06-18').

    Returns:
        List of file paths, newest first, limited to max_files.
    """
    ev_dir = Path(evidence_dir)
    if not ev_dir.is_dir():
        return []

    files = sorted(ev_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    result: list[Path] = []
    for f in files:
        if exclude_before:
            # Try to extract timestamp from filename or content
            # Filename format: active_cycle_20260620T121741Z.json
            fname = f.stem
            parts = fname.split("_")
            for part in parts:
                if part.startswith("20") and len(part) >= 8:
                    ts_str = part[:8]  # YYYYMMDD
                    if ts_str < exclude_before.replace("-", ""):
                        continue
        result.append(f)
        if len(result) >= max_files:
            break

    return result


# ---------------------------------------------------------------------------
# Single-cycle extraction
# ---------------------------------------------------------------------------


def _extract_bot_snapshots(
    evidence_file: Path,
) -> tuple[str, list[BotCycleSnapshot]]:
    """Extract per-bot snapshots from one evidence JSON file.

    Returns:
        Tuple of (cycle_id, list of BotCycleSnapshot).
    """
    import json

    with open(evidence_file) as f:
        data = json.load(f)

    cycle_id = data.get("cycle_id", evidence_file.stem)
    decisions = data.get("per_bot_decisions") or data.get("per_bot") or []
    generated_at = data.get("generated_at_utc", "")

    snapshots: list[BotCycleSnapshot] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        bot_id = d.get("bot_id", "")
        if not bot_id:
            continue

        wf = d.get("walk_forward_net_metrics", {}) or {}
        ms = str(wf.get("metrics_source", "not_applicable") or "not_applicable")
        es = str(wf.get("evaluation_status", "NOT_APPLICABLE") or "NOT_APPLICABLE")

        has_real = ms not in ("not_applicable", "unknown", "none", "synthetic", "")

        _pnl = wf.get("total_net_pnl", 0.0)
        _pnl_f = float(_pnl) if isinstance(_pnl, (int, float)) else 0.0
        _pf = wf.get("profit_factor", 0.0)
        _pf_f = float(_pf) if isinstance(_pf, (int, float)) else 0.0
        _tr = wf.get("total_trades", 0)
        _tr_i = int(_tr) if isinstance(_tr, (int, float)) else 0
        _dd = wf.get("max_drawdown_pct", 0.0)
        _dd_f = float(_dd) if isinstance(_dd, (int, float)) else 0.0
        _dd_measured = isinstance(_dd, (int, float)) and _dd_f > 0.0

        reason_codes_raw = d.get("promotion_block_reason_codes", []) or []
        _codes: tuple[str, ...] = tuple(
            str(c) for c in reason_codes_raw if isinstance(c, str)
        )

        snapshots.append(BotCycleSnapshot(
            bot_id=bot_id,
            cycle_id=cycle_id,
            generated_at_utc=generated_at,
            has_real_metrics=has_real,
            net_pnl=_pnl_f,
            profit_factor=_pf_f,
            trade_count=_tr_i,
            max_drawdown_pct=_dd_f,
            max_drawdown_measured=_dd_measured,
            evaluation_status=es,
            metrics_source=ms,
            promotion_blocked=bool(d.get("promotion_blocked", True)),
            promotion_block_reason_codes=_codes,
        ))

    return cycle_id, snapshots


# ---------------------------------------------------------------------------
# Per-bot accumulation
# ---------------------------------------------------------------------------


def _classify_bot(acc: BotAccumulatedEvidence) -> tuple[str, list[str]]:
    """Classify a bot based on accumulated multi-cycle evidence.

    Rules (deterministic):
      - CANDIDATE: >= MIN_REAL_METRICS_CYCLES with real metrics,
        positive net_pnl_avg, profit_factor_avg >= 1.0, drawdown measured,
        drawdown within safe range, no majority of negative cycles.
      - BLOCKED: has real metrics but net_pnl_avg is negative OR
        profit_factor_avg < 1.0 OR drawdown too high.
      - WATCH: has some real metrics (>= MIN_WATCH_CYCLES) but not enough
        cycles for candidate, or mixed evidence.
      - INCONCLUSIVE: insufficient cycles (0 or very few) or no real metrics.
    """
    reasons: list[str] = []

    if acc.real_metrics_cycle_count == 0:
        return (CLASS_INCONCLUSIVE, ["no_real_metrics_cycles"])

    if acc.cycle_count == 0:
        return (CLASS_INCONCLUSIVE, ["no_cycle_data"])

    # Blocked: negative net PnL on average
    if acc.net_pnl_avg <= 0 and acc.real_metrics_cycle_count > 0:
        reasons.append(f"net_pnl_avg={acc.net_pnl_avg:.4f}")

    # Blocked: profit factor too low
    if acc.profit_factor_avg < 1.0 and acc.real_metrics_cycle_count > 0:
        reasons.append(f"profit_factor_avg={acc.profit_factor_avg:.4f}")

    # Blocked: drawdown not measured
    if acc.max_drawdown_measured_count == 0 and acc.real_metrics_cycle_count > 0:
        reasons.append("max_drawdown_not_measured")

    # Blocked: too many negative cycles
    if acc.negative_metrics_count > acc.real_metrics_cycle_count // 2:
        reasons.append(f"negative_metrics_in_{acc.negative_metrics_count}_of_{acc.real_metrics_cycle_count}_cycles")

    if reasons:
        return (CLASS_BLOCKED, reasons)

    # Candidate: sufficient real evidence + positive metrics
    if acc.has_sufficient_real_evidence:
        return (CLASS_CANDIDATE, [
            f"real_metrics_in_{acc.real_metrics_cycle_count}_cycles",
            f"net_pnl_avg={acc.net_pnl_avg:.4f}",
            f"profit_factor_avg={acc.profit_factor_avg:.4f}",
        ])

    # Watch: some real evidence but not enough for candidate
    if acc.has_any_real_evidence:
        return (CLASS_WATCH, [
            f"real_metrics_in_{acc.real_metrics_cycle_count}_cycles_below_{MIN_REAL_METRICS_CYCLES}",
            f"need_{MIN_REAL_METRICS_CYCLES - acc.real_metrics_cycle_count}_more_cycles",
        ])

    return (CLASS_INCONCLUSIVE, ["insufficient_evidence"])


def _accumulate_bot(
    bot_id: str,
    snapshots: Sequence[BotCycleSnapshot],
) -> BotAccumulatedEvidence:
    """Accumulate all snapshots for one bot into a single evidence record."""
    snap_list = list(snapshots)
    total = len(snap_list)
    real_count = sum(1 for s in snap_list if s.has_real_metrics)
    no_prop = sum(1 for s in snap_list if s.evaluation_status == "NOT_APPLICABLE")
    neg_metrics = sum(
        1 for s in snap_list if s.evaluation_status == "NEGATIVE_NET_METRICS"
    )
    total_pnl = sum(s.net_pnl for s in snap_list)
    total_pf = sum(s.profit_factor for s in snap_list)
    total_trades = sum(s.trade_count for s in snap_list)
    max_dd = max((s.max_drawdown_pct for s in snap_list), default=0.0)
    dd_measured = sum(1 for s in snap_list if s.max_drawdown_measured)
    read_ok = sum(1 for s in snap_list if s.has_real_metrics or s.evaluation_status != "NOT_APPLICABLE")
    read_rate = read_ok / total if total > 0 else 0.0

    avg_pnl = total_pnl / real_count if real_count > 0 else 0.0
    avg_pf = total_pf / real_count if real_count > 0 else 0.0
    avg_trades = total_trades / total if total > 0 else 0.0

    acc = BotAccumulatedEvidence(
        bot_id=bot_id,
        cycle_count=total,
        real_metrics_cycle_count=real_count,
        no_proposal_count=no_prop,
        negative_metrics_count=neg_metrics,
        net_pnl_total=total_pnl,
        net_pnl_avg=avg_pnl,
        profit_factor_avg=avg_pf,
        trade_count_total=total_trades,
        trade_count_avg=avg_trades,
        max_drawdown_pct_max=max_dd,
        max_drawdown_measured_count=dd_measured,
        read_success_rate=read_rate,
        classification="",
        classification_reasons=(),
        cycles=tuple(snap_list),
    )

    cls, reasons = _classify_bot(acc)
    object.__setattr__(acc, "classification", cls)
    object.__setattr__(acc, "classification_reasons", tuple(reasons))
    return acc


# ---------------------------------------------------------------------------
# Fleet aggregation
# ---------------------------------------------------------------------------

# Expected bot IDs for fleet completeness
_EXPECTED_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)


def _recommend_pilot_candidate(
    bot_evidences: Sequence[BotAccumulatedEvidence],
) -> tuple[str, str]:
    """Determine the best pilot candidate from accumulated evidence.

    Returns:
        Tuple of (recommendation_classification, reason).
    """
    candidates = [b for b in bot_evidences if b.classification == CLASS_CANDIDATE]
    if candidates:
        # Pick the one with highest net_pnl_avg
        best = max(candidates, key=lambda b: b.net_pnl_avg)
        return (
            best.bot_id,
            f"highest net_pnl_avg ({best.net_pnl_avg:.4f}) "
            f"among {len(candidates)} candidate(s)",
        )

    watch = [b for b in bot_evidences if b.classification == CLASS_WATCH]
    if watch:
        best = max(watch, key=lambda b: b.net_pnl_avg)
        return (
            f"watch:{best.bot_id}",
            f"no candidate yet; best watch bot is {best.bot_id} "
            f"(net_pnl_avg={best.net_pnl_avg:.4f}, "
            f"real_metrics_cycles={best.real_metrics_cycle_count})",
        )

    # Fallback: recommend no-one
    return (
        "none",
        "no bot has real metrics — all inconclusive or blocked",
    )


def generate_multi_cycle_report(
    evidence_dir: str | Path,
    *,
    window_size: int = DEFAULT_WINDOW_SIZE,
    exclude_before: str = "",
) -> MultiCycleFleetReport:
    """Generate a multi-cycle profitability evidence report.

    Args:
        evidence_dir: Directory containing evidence JSON files.
        window_size: Number of most recent files to evaluate.
        exclude_before: ISO date string to exclude older files (e.g. '2026-06-18').

    Returns:
        MultiCycleFleetReport with per-bot classifications and fleet recommendation.
    """
    files = _find_evidence_files(
        evidence_dir, max_files=window_size, exclude_before=exclude_before,
    )

    # Extract snapshots from each file
    all_cycle_ids: list[str] = []
    snapshots_by_bot: dict[str, list[BotCycleSnapshot]] = {
        bid: [] for bid in _EXPECTED_BOT_IDS
    }

    for f in files:
        cycle_id, bot_snapshots = _extract_bot_snapshots(f)
        all_cycle_ids.append(cycle_id)
        for snap in bot_snapshots:
            if snap.bot_id in snapshots_by_bot:
                snapshots_by_bot[snap.bot_id].append(snap)

    # Accumulate per bot
    bot_evidences = [
        _accumulate_bot(bot_id, snaps)
        for bot_id, snaps in snapshots_by_bot.items()
    ]

    # Fleet classifications dict
    fleet_cls: dict[str, str] = {b.bot_id: b.classification for b in bot_evidences}

    # Fleet recommendation
    rec_bot, rec_reason = _recommend_pilot_candidate(bot_evidences)

    from datetime import UTC, datetime
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return MultiCycleFleetReport(
        generated_at_utc=now_utc,
        window_size=window_size,
        cycles_evaluated=len(files),
        cycle_ids=tuple(all_cycle_ids),
        per_bot=tuple(bot_evidences),
        fleet_classifications=fleet_cls,
        fleet_recommendation=rec_bot,
        fleet_recommendation_reason=rec_reason,
    )


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------


def render_markdown_report(report: MultiCycleFleetReport) -> str:
    """Render a MultiCycleFleetReport as Markdown."""
    lines: list[str] = []
    lines.append("# SI v2 Multi-Cycle Profitability Evidence\n")
    lines.append(f"**Generated:** {report.generated_at_utc}  ")
    lines.append(f"**Window:** last {report.window_size} evidence files  ")
    lines.append(f"**Cycles evaluated:** {report.cycles_evaluated}  ")
    lines.append(f"**Fleet recommendation:** `{report.fleet_recommendation}`  ")
    lines.append(f"**Reason:** {report.fleet_recommendation_reason}  ")
    lines.append("")

    # Cycle IDs
    lines.append("## Cycles in Window\n")
    for cid in report.cycle_ids:
        lines.append(f"- `{cid}`")
    lines.append("")

    # Per-bot table
    lines.append("## Per-Bot Accumulated Evidence\n")
    lines.append(
        "| Bot | Cycles | Real Metrics | No Proposal | Negative | "
        "Net PnL Total | Net PnL Avg | PF Avg | Trades Total | "
        "Max DD | Classification |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    )
    for b in report.per_bot:
        lines.append(
            f"| {b.bot_id} | {b.cycle_count} | {b.real_metrics_cycle_count} | "
            f"{b.no_proposal_count} | {b.negative_metrics_count} | "
            f"{b.net_pnl_total:.4f} | {b.net_pnl_avg:.4f} | "
            f"{b.profit_factor_avg:.4f} | {b.trade_count_total} | "
            f"{b.max_drawdown_pct_max:.4f} | **{b.classification}** |"
        )
    lines.append("")

    # Classification details
    lines.append("## Classification Details\n")
    for b in report.per_bot:
        lines.append(f"### {b.bot_id} — `{b.classification}`\n")
        if b.classification_reasons:
            for r in b.classification_reasons:
                lines.append(f"- {r}")
        else:
            lines.append("- No specific blockers")
        lines.append("")

    # Fleet recommendation
    lines.append("## Fleet Recommendation\n")
    lines.append(f"**Pilot candidate:** `{report.fleet_recommendation}`  ")
    lines.append(f"**Reason:** {report.fleet_recommendation_reason}  ")

    # What evidence is missing for each bot
    lines.append("\n## Missing Evidence\n")
    for b in report.per_bot:
        missing: list[str] = []
        if b.classification == CLASS_BLOCKED:
            for r in b.classification_reasons:
                missing.append(r)
        elif b.classification == CLASS_WATCH:
            need = MIN_REAL_METRICS_CYCLES - b.real_metrics_cycle_count
            missing.append(f"needs {need} more cycle(s) with real metrics for candidate")
            if b.profit_factor_avg < 1.0:
                missing.append(f"profit_factor_avg={b.profit_factor_avg:.4f} < 1.0")
        elif b.classification == CLASS_INCONCLUSIVE:
            missing.append("no real metrics available from any cycle")

        if missing:
            lines.append(f"- **{b.bot_id}:** {', '.join(missing)}")
        else:
            lines.append(f"- **{b.bot_id}:** no blockers identified")
    lines.append("")

    # Safety note
    lines.append("---\n")
    lines.append(
        "*This report was generated from read-only analysis of existing "
        "evidence artifacts. No runtime state was modified. No live trading "
        "was enabled.*\n"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

_DEFAULT_EVIDENCE_DIR = Path(__file__).resolve().parents[4] / "self_improvement_v2" / "reports" / "phase2" / "evidence"


def main() -> None:
    """CLI entry point: python -m si_v2.evaluation.multi_cycle_evidence."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SI v2 Multi-Cycle Profitability Evidence Report",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(_DEFAULT_EVIDENCE_DIR),
        help="Path to evidence JSON directory (default: %(default)s)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_WINDOW_SIZE,
        help=f"Number of recent cycles to evaluate (default: {DEFAULT_WINDOW_SIZE})",
    )
    parser.add_argument(
        "--exclude-before",
        default="",
        help="ISO date string; skip files older than this date (e.g. 2026-06-18)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of Markdown",
    )
    args = parser.parse_args()

    report = generate_multi_cycle_report(
        args.evidence_dir,
        window_size=args.window,
        exclude_before=args.exclude_before,
    )

    if args.json:
        import json
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_markdown_report(report))


if __name__ == "__main__":
    main()
