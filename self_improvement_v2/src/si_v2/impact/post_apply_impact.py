r"""SI v2 Post-Apply Impact Measurement (#278).

Reads dry-run apply plan artifacts and compares pre-/post-apply evidence
windows to determine whether an approved apply plan improved, degraded, or
did not materially change bot performance.

Key design decisions:
  - Pure I/O at the edges (reading apply plans and evidence); comparison
    logic is a pure function.
  - Pre-window: N cycles BEFORE the apply plan timestamp.
  - Post-window: N cycles AFTER the apply plan timestamp.
  - Impact verdicts are deterministic based on metric deltas with tolerance.
  - Artifact-only: writes JSON/Markdown reports to reports/phase2/impact/.
  - No runtime mutation, no config writes, no Docker/Compose/Cron.

Impact verdict rules:
  INSUFFICIENT_POST_APPLY_DATA — no post-apply evidence or insufficient
    real metrics in post window.
  IMPROVED — post-window shows higher total_net_pnl AND equal or better
    profit_factor AND no materially worse drawdown.
  DEGRADED — post-window shows lower total_net_pnl beyond tolerance OR
    worse profit_factor beyond tolerance OR drawdown materially worsens.
  UNCHANGED — metrics are within tolerance on both sides.

Safety invariants:
  - Artifact-only — never reads/writes Freqtrade configs, strategies,
    Docker, compose, cron, or runtime state.
  - Never enables live trading or sets dry_run to false.
  - No credentials printed.
  - Mutation counters remain 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Impact verdict constants
# ---------------------------------------------------------------------------
IMPACT_IMPROVED: Final[str] = "IMPROVED"
IMPACT_DEGRADED: Final[str] = "DEGRADED"
IMPACT_UNCHANGED: Final[str] = "UNCHANGED"
IMPACT_INSUFFICIENT_DATA: Final[str] = "INSUFFICIENT_POST_APPLY_DATA"

# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------
_PNL_TOLERANCE: Final[float] = 0.5
"""Minimum absolute net_pnl change to consider a meaningful improvement/degradation."""

_PROFIT_FACTOR_TOLERANCE: Final[float] = 0.1
"""Minimum profit_factor change to consider meaningful."""

_DRAWDOWN_TOLERANCE: Final[float] = 2.0
"""Maximum drawdown percentage increase before flagging degradation."""

_MIN_POST_TRADES: Final[int] = 3
"""Minimum trades in post window to avoid INSUFFICIENT_DATA."""

_MIN_PRE_TRADES: Final[int] = 3
"""Minimum trades in pre window to consider the baseline reliable."""

_WINDOW_SIZE: Final[int] = 3
"""Number of evidence files to use for pre/post windows."""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowMetrics:
    """Aggregated metrics for a time window (pre or post apply)."""

    total_net_pnl: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    max_drawdown_pct: float = 0.0
    real_metric_cycles: int = 0
    cycle_count: int = 0
    metrics_source: str = "unknown"

    @property
    def has_sufficient_real_data(self) -> bool:
        return (
            self.real_metric_cycles > 0
            and self.total_trades >= _MIN_POST_TRADES
        )

    @property
    def has_sufficient_pre_data(self) -> bool:
        return (
            self.real_metric_cycles > 0
            and self.total_trades >= _MIN_PRE_TRADES
        )


@dataclass(frozen=True)
class ImpactVerdict:
    """Result of comparing pre- and post-apply windows for one bot."""

    apply_plan_id: str
    bot_id: str
    hypothesis: str
    verdict: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    pre_metrics: WindowMetrics = field(default_factory=WindowMetrics)
    post_metrics: WindowMetrics = field(default_factory=WindowMetrics)
    delta_pnl: float = 0.0
    delta_profit_factor: float = 0.0
    delta_drawdown: float = 0.0


@dataclass(frozen=True)
class ImpactReport:
    """Aggregate impact report across all processed apply plans."""

    generated_at_utc: str
    per_plan: tuple[ImpactVerdict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "per_plan": [
                {
                    "apply_plan_id": v.apply_plan_id,
                    "bot_id": v.bot_id,
                    "hypothesis": v.hypothesis,
                    "verdict": v.verdict,
                    "reason_codes": list(v.reason_codes),
                    "pre_metrics": {
                        "total_net_pnl": round(v.pre_metrics.total_net_pnl, 6),
                        "profit_factor": round(v.pre_metrics.profit_factor, 4),
                        "total_trades": v.pre_metrics.total_trades,
                        "max_drawdown_pct": round(v.pre_metrics.max_drawdown_pct, 4),
                        "real_metric_cycles": v.pre_metrics.real_metric_cycles,
                    },
                    "post_metrics": {
                        "total_net_pnl": round(v.post_metrics.total_net_pnl, 6),
                        "profit_factor": round(v.post_metrics.profit_factor, 4),
                        "total_trades": v.post_metrics.total_trades,
                        "max_drawdown_pct": round(v.post_metrics.max_drawdown_pct, 4),
                        "real_metric_cycles": v.post_metrics.real_metric_cycles,
                    },
                    "delta_pnl": round(v.delta_pnl, 6),
                    "delta_profit_factor": round(v.delta_profit_factor, 4),
                    "delta_drawdown": round(v.delta_drawdown, 4),
                }
                for v in self.per_plan
            ],
        }


# ---------------------------------------------------------------------------
# Evidence loading helpers
# ---------------------------------------------------------------------------


def _load_bot_metrics_from_cycle(
    evidence_file: Path,
    bot_id: str,
) -> WindowMetrics | None:
    """Extract walk_forward_net_metrics for one bot from a cycle evidence file."""
    try:
        with open(evidence_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    decisions = data.get("per_bot_decisions") or data.get("per_bot") or []

    for d in decisions:
        if not isinstance(d, dict):
            continue
        if d.get("bot_id") != bot_id:
            continue

        wf = d.get("walk_forward_net_metrics", {})
        if not isinstance(wf, dict):
            return None

        ms = str(wf.get("metrics_source", "unknown") or "unknown")
        is_real = ms not in ("not_applicable", "unknown", "none", "synthetic", "")

        _pnl = wf.get("total_net_pnl", 0.0)
        pnl = float(_pnl) if isinstance(_pnl, (int, float)) else 0.0
        _pf = wf.get("profit_factor", 0.0)
        pf = float(_pf) if isinstance(_pf, (int, float)) else 0.0
        _tr = wf.get("total_trades", 0)
        trades = int(_tr) if isinstance(_tr, (int, float)) else 0
        _dd = wf.get("max_drawdown_pct", 0.0)
        dd = float(_dd) if isinstance(_dd, (int, float)) else 0.0

        return WindowMetrics(
            total_net_pnl=pnl,
            profit_factor=pf,
            total_trades=trades,
            max_drawdown_pct=dd,
            real_metric_cycles=1 if is_real else 0,
            cycle_count=1,
            metrics_source=ms,
        )

    return None


def _aggregate_window(
    evidence_files: list[Path],
    bot_id: str,
) -> WindowMetrics:
    """Aggregate metrics for a bot across a list of evidence files."""
    total_pnl = 0.0
    total_pf = 0.0
    total_trades = 0
    max_dd = 0.0
    real_cycles = 0
    cycles = 0
    sources: set[str] = set()

    for f in evidence_files:
        metrics = _load_bot_metrics_from_cycle(f, bot_id)
        if metrics is None:
            continue
        cycles += 1
        if metrics.real_metric_cycles > 0:
            real_cycles += 1
        total_pnl += metrics.total_net_pnl
        total_pf += metrics.profit_factor
        total_trades += metrics.total_trades
        if metrics.max_drawdown_pct > max_dd:
            max_dd = metrics.max_drawdown_pct
        sources.add(metrics.metrics_source)

    return WindowMetrics(
        total_net_pnl=total_pnl,
        profit_factor=total_pf / max(real_cycles, 1),
        total_trades=total_trades,
        max_drawdown_pct=max_dd,
        real_metric_cycles=real_cycles,
        cycle_count=cycles,
        metrics_source=",".join(sorted(sources)) if sources else "none",
    )


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------


def _select_pre_post_windows(
    evidence_dir: Path,
    plan_timestamp: str,
    bot_id: str,
    *,
    window_size: int = _WINDOW_SIZE,
) -> tuple[list[Path], list[Path]]:
    """Select pre- and post-apply evidence windows.

    Sorts evidence files by the ISO timestamp embedded in their filename
    (not mtime) for deterministic ordering regardless of filesystem.

    Args:
        evidence_dir: Directory containing evidence JSON files.
        plan_timestamp: ISO timestamp of the apply plan generation.
        bot_id: Bot ID (unused in selection, retained for interface).
        window_size: Number of files to include in each window.

    Returns:
        Tuple of (pre_files, post_files) sorted chronologically.
    """
    _ = bot_id  # reserved for future targeted window selection

    # Extract ISO timestamp from filename for sorting
    def _file_sort_key(path: Path) -> str:
        fname = path.stem
        for part in fname.split("_"):
            if part.startswith("20") and len(part) >= 15:
                return part.replace("Z", "").replace("-", "").replace(":", "")
        return fname

    all_files = sorted(evidence_dir.glob("*.json"), key=_file_sort_key)

    # Normalize plan timestamp for comparison
    plan_key = (
        plan_timestamp.replace("Z", "")
        .replace("-", "")
        .replace(":", "")
        .split(".")[0]
    )

    split_idx = len(all_files)
    for i, f in enumerate(all_files):
        fkey = _file_sort_key(f)
        if fkey > plan_key:
            split_idx = i
            break

    pre_files = all_files[max(0, split_idx - window_size):split_idx]
    post_files = all_files[split_idx:split_idx + window_size]

    return (pre_files, post_files)


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------


def _compute_impact_verdict(
    apply_plan: dict[str, object],
    pre: WindowMetrics,
    post: WindowMetrics,
) -> ImpactVerdict:
    """Compare pre and post windows and produce an ImpactVerdict.

    Args:
        apply_plan: The apply plan artifact dict.
        pre: Aggregated metrics from pre-apply window.
        post: Aggregated metrics from post-apply window.

    Returns:
        ImpactVerdict with deterministic classification.
    """
    plan_id = str(apply_plan.get("apply_plan_id", ""))
    bot_id = str(apply_plan.get("bot_id", ""))
    hypothesis = str(apply_plan.get("hypothesis", ""))
    # Mutation check — hard block
    mutation_performed = apply_plan.get("mutation_performed", False)
    if mutation_performed:
        return ImpactVerdict(
            apply_plan_id=plan_id,
            bot_id=bot_id,
            hypothesis=hypothesis,
            verdict=IMPACT_INSUFFICIENT_DATA,
            reason_codes=("unsafe_apply_plan_mutation_performed",),
            pre_metrics=pre,
            post_metrics=post,
        )

    reasons: list[str] = []

    # Check post-apply has sufficient data
    if not post.has_sufficient_real_data:
        return ImpactVerdict(
            apply_plan_id=plan_id,
            bot_id=bot_id,
            hypothesis=hypothesis,
            verdict=IMPACT_INSUFFICIENT_DATA,
            reason_codes=tuple(
                ["insufficient_post_apply_data", *reasons]
            ),
            pre_metrics=pre,
            post_metrics=post,
        )

    # Compute deltas
    delta_pnl = post.total_net_pnl - pre.total_net_pnl
    delta_pf = post.profit_factor - pre.profit_factor
    delta_dd = post.max_drawdown_pct - pre.max_drawdown_pct

    # Decide
    pnl_improved = delta_pnl > _PNL_TOLERANCE
    pnl_degraded = delta_pnl < -_PNL_TOLERANCE
    pf_degraded = delta_pf < -_PROFIT_FACTOR_TOLERANCE
    dd_worsened = delta_dd > _DRAWDOWN_TOLERANCE

    if dd_worsened:
        reasons.append(f"drawdown_increased_by_{delta_dd:.2f}")
        return ImpactVerdict(
            apply_plan_id=plan_id,
            bot_id=bot_id,
            hypothesis=hypothesis,
            verdict=IMPACT_DEGRADED,
            reason_codes=tuple(reasons),
            pre_metrics=pre,
            post_metrics=post,
            delta_pnl=delta_pnl,
            delta_profit_factor=delta_pf,
            delta_drawdown=delta_dd,
        )

    if pnl_improved and not pf_degraded:
        return ImpactVerdict(
            apply_plan_id=plan_id,
            bot_id=bot_id,
            hypothesis=hypothesis,
            verdict=IMPACT_IMPROVED,
            reason_codes=tuple(
                [f"net_pnl_increased_by_{delta_pnl:.4f}", *reasons]
            ),
            pre_metrics=pre,
            post_metrics=post,
            delta_pnl=delta_pnl,
            delta_profit_factor=delta_pf,
            delta_drawdown=delta_dd,
        )

    if pnl_degraded or pf_degraded:
        if pnl_degraded:
            reasons.append(f"net_pnl_decreased_by_{abs(delta_pnl):.4f}")
        if pf_degraded:
            reasons.append(f"profit_factor_decreased_by_{abs(delta_pf):.4f}")
        return ImpactVerdict(
            apply_plan_id=plan_id,
            bot_id=bot_id,
            hypothesis=hypothesis,
            verdict=IMPACT_DEGRADED,
            reason_codes=tuple(reasons),
            pre_metrics=pre,
            post_metrics=post,
            delta_pnl=delta_pnl,
            delta_profit_factor=delta_pf,
            delta_drawdown=delta_dd,
        )

    return ImpactVerdict(
        apply_plan_id=plan_id,
        bot_id=bot_id,
        hypothesis=hypothesis,
        verdict=IMPACT_UNCHANGED,
        reason_codes=("metrics_within_tolerance",),
        pre_metrics=pre,
        post_metrics=post,
        delta_pnl=delta_pnl,
        delta_profit_factor=delta_pf,
        delta_drawdown=delta_dd,
    )


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------


def evaluate_apply_plan_impact(
    apply_plan_path: str | Path,
    evidence_dir: str | Path,
    *,
    window_size: int = _WINDOW_SIZE,
) -> ImpactVerdict:
    """Evaluate the impact of a single apply plan.

    Args:
        apply_plan_path: Path to the apply plan JSON artifact.
        evidence_dir: Directory containing evidence JSON files.
        window_size: Number of files in pre/post windows.

    Returns:
        ImpactVerdict with pre/post comparison.
    """
    with open(apply_plan_path) as f:
        apply_plan = json.load(f)

    bot_id = str(apply_plan.get("bot_id", ""))
    plan_ts = str(apply_plan.get("plan_generated_at_utc", ""))

    ev_dir = Path(evidence_dir)
    pre_files, post_files = _select_pre_post_windows(
        ev_dir, plan_ts, bot_id, window_size=window_size,
    )

    pre = _aggregate_window(pre_files, bot_id)
    post = _aggregate_window(post_files, bot_id)

    return _compute_impact_verdict(apply_plan, pre, post)


def evaluate_all_apply_plans(
    apply_plans_dir: str | Path,
    evidence_dir: str | Path,
    *,
    window_size: int = _WINDOW_SIZE,
) -> ImpactReport:
    """Evaluate impact for all apply plans in a directory.

    Args:
        apply_plans_dir: Directory containing apply plan JSON files.
        evidence_dir: Directory containing evidence JSON files.
        window_size: Number of files in pre/post windows.

    Returns:
        ImpactReport with verdicts for all plans.
    """
    ap_dir = Path(apply_plans_dir)
    ev_dir = Path(evidence_dir)

    plans = sorted(ap_dir.glob("apply_plan_*.json"))
    verdicts: list[ImpactVerdict] = []

    for plan_path in plans:
        try:
            verdict = evaluate_apply_plan_impact(
                plan_path, ev_dir, window_size=window_size,
            )
            verdicts.append(verdict)
        except (json.JSONDecodeError, OSError) as e:
            verdicts.append(ImpactVerdict(
                apply_plan_id=plan_path.stem.replace("apply_plan_", ""),
                bot_id="unknown",
                hypothesis="",
                verdict=IMPACT_INSUFFICIENT_DATA,
                reason_codes=(f"load_error:{e!s}",),
            ))

    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ImpactReport(generated_at_utc=now_utc, per_plan=tuple(verdicts))


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------


def render_impact_markdown(report: ImpactReport) -> str:
    """Render ImpactReport as Markdown."""
    lines: list[str] = []
    lines.append("# SI v2 Post-Apply Impact Report\n")
    lines.append(f"**Generated:** {report.generated_at_utc}  \n")

    if not report.per_plan:
        lines.append("\n_No apply plans processed._\n")
        return "\n".join(lines)

    for v in report.per_plan:
        lines.append(f"## Apply Plan: `{v.apply_plan_id}`\n")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.append(f"| Bot | `{v.bot_id}` |")
        lines.append(f"| Hypothesis | `{v.hypothesis}` |")
        lines.append(f"| Verdict | **{v.verdict}** |")
        if v.reason_codes:
            lines.append(f"| Reasons | `{', '.join(v.reason_codes)}` |")
        lines.append("")
        lines.append("### Pre-Apply Metrics")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Net PnL | {v.pre_metrics.total_net_pnl:.4f} |")
        lines.append(f"| Profit Factor | {v.pre_metrics.profit_factor:.4f} |")
        lines.append(f"| Trades | {v.pre_metrics.total_trades} |")
        lines.append(f"| Max Drawdown | {v.pre_metrics.max_drawdown_pct:.4f}% |")
        lines.append("")
        lines.append("### Post-Apply Metrics")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Net PnL | {v.post_metrics.total_net_pnl:.4f} |")
        lines.append(f"| Profit Factor | {v.post_metrics.profit_factor:.4f} |")
        lines.append(f"| Trades | {v.post_metrics.total_trades} |")
        lines.append(f"| Max Drawdown | {v.post_metrics.max_drawdown_pct:.4f}% |")
        lines.append("")
        lines.append("### Deltas")
        lines.append("| Metric | Delta |")
        lines.append("|---|---|")
        lines.append(f"| Net PnL | {v.delta_pnl:.4f} |")
        lines.append(f"| Profit Factor | {v.delta_profit_factor:.4f} |")
        lines.append(f"| Max Drawdown | {v.delta_drawdown:.4f}% |")
        lines.append("")

    lines.append("---\n")
    lines.append(
        "*Report generated from read-only analysis of apply plan and evidence "
        "artifacts. No runtime state was modified.*\n"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: python -m si_v2.impact.post_apply_impact."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SI v2 Post-Apply Impact Measurement",
    )
    parser.add_argument(
        "--apply-plan",
        type=str,
        default="",
        help="Path to a single apply plan JSON file",
    )
    parser.add_argument(
        "--apply-plans-dir",
        type=str,
        default="",
        help="Directory with apply plan files (evaluates all)",
    )
    parser.add_argument(
        "--evidence-dir",
        type=str,
        default="",
        help="Directory with evidence JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Output directory for impact reports",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of Markdown",
    )
    args = parser.parse_args()

    # Resolve evidence dir
    ev_dir = args.evidence_dir or str(
        Path(__file__).resolve().parents[4]
        / "self_improvement_v2" / "reports" / "phase2" / "evidence"
    )

    # Determine which apply plans to evaluate
    if args.apply_plan:
        verdict = evaluate_apply_plan_impact(args.apply_plan, ev_dir)
        report = ImpactReport(
            generated_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            per_plan=(verdict,),
        )
    elif args.apply_plans_dir:
        report = evaluate_all_apply_plans(args.apply_plans_dir, ev_dir)
    else:
        # Default: read from reports/phase2/apply_plans/
        default_ap_dir = (
            Path(__file__).resolve().parents[4]
            / "self_improvement_v2" / "reports" / "phase2" / "apply_plans"
        )
        if default_ap_dir.is_dir():
            report = evaluate_all_apply_plans(default_ap_dir, ev_dir)
        else:
            print("No apply plan directory found. Use --apply-plan or --apply-plans-dir")
            return

    # Output
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if args.json:
            path = out_dir / f"impact_report_{ts}.json"
            with open(path, "w") as f:
                json.dump(report.to_dict(), f, indent=2, sort_keys=True)
            print(f"Impact report written: {path}")
        else:
            path = out_dir / f"impact_report_{ts}.md"
            md = render_impact_markdown(report)
            with open(path, "w") as f:
                f.write(md)
            print(f"Impact report written: {path}")
    else:
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(render_impact_markdown(report))


if __name__ == "__main__":
    main()
