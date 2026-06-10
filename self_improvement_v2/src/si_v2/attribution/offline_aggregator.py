"""Offline attribution aggregator skeleton.

Loads source-regime stats fixture data and aggregates by source and regime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AttributionRow:
    source_id: str
    regime_label: str
    sample_count: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_confidence: float


@dataclass
class AttributionSummary:
    rows: list[AttributionRow] = field(default_factory=list)
    total_samples: int = 0
    overall_win_rate: float = 0.0
    source_count: int = 0
    status: str = "ok"
    errors: list[str] = field(default_factory=list)


class OfflineAttributionAggregator:
    """Aggregate source-regime stats from fixture data."""

    def __init__(
        self,
        stats_dir: Path | None = None,
    ) -> None:
        self._stats_dir = stats_dir or Path(
            "self_improvement_v2/fixtures/source-regime-stats"
        )

    def aggregate(self) -> AttributionSummary:
        """Load and aggregate all stats fixtures."""
        if not self._stats_dir.exists():
            return AttributionSummary(
                status="degraded",
                errors=[f"Stats dir not found: {self._stats_dir}"],
            )

        rows: list[AttributionRow] = []
        total_samples = 0
        total_wins = 0

        for f in sorted(self._stats_dir.glob("*.json")):
            try:
                with open(f) as fp:
                    data = dict(json.load(fp))
            except (json.JSONDecodeError, OSError) as e:
                return AttributionSummary(
                    status="degraded",
                    errors=[f"Failed to load {f.name}: {e}"],
                )

            source = str(data.get("source_id", "unknown"))
            regime = str(data.get("regime_label", "unknown"))
            samples = int(data.get("sample_count", 0))
            wins = int(data.get("win_count", 0))
            losses = int(data.get("loss_count", 0))

            win_rate = wins / samples if samples > 0 else 0.0
            avg_conf = 0.0
            summary = data.get("summary", {})
            if isinstance(summary, dict):
                avg_conf = float(
                    summary.get("avg_confidence", 0.0)
                )

            rows.append(
                AttributionRow(
                    source_id=source,
                    regime_label=regime,
                    sample_count=samples,
                    win_count=wins,
                    loss_count=losses,
                    win_rate=round(win_rate, 3),
                    avg_confidence=round(avg_conf, 3),
                )
            )
            total_samples += samples
            total_wins += wins

        overall_win_rate = (
            round(total_wins / total_samples, 3)
            if total_samples > 0
            else 0.0
        )

        return AttributionSummary(
            rows=rows,
            total_samples=total_samples,
            overall_win_rate=overall_win_rate,
            source_count=len(rows),
            status="ok",
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize summary to dict for JSON output."""
        summary = self.aggregate()
        return {
            "status": summary.status,
            "total_samples": summary.total_samples,
            "overall_win_rate": summary.overall_win_rate,
            "source_count": summary.source_count,
            "rows": [
                {
                    "source_id": r.source_id,
                    "regime_label": r.regime_label,
                    "sample_count": r.sample_count,
                    "win_count": r.win_count,
                    "loss_count": r.loss_count,
                    "win_rate": r.win_rate,
                    "avg_confidence": r.avg_confidence,
                }
                for r in summary.rows
            ],
            "errors": summary.errors,
        }

    def generate_markdown(self) -> str:
        """Generate deterministic Markdown report."""
        summary = self.aggregate()
        lines: list[str] = []
        lines.append("# Offline Attribution Summary")
        lines.append("")
        if summary.errors:
            lines.append(f"**Status:** {summary.status}")
            lines.append("")
            for e in summary.errors:
                lines.append(f"- ❌ {e}")
            return "\n".join(lines)

        lines.append(f"**Overall Win Rate:** {summary.overall_win_rate:.1%}")
        lines.append(f"**Total Samples:** {summary.total_samples}")
        lines.append(f"**Source-Regime Combinations:** {summary.source_count}")
        lines.append("")
        lines.append("| Source | Regime | Samples | Wins | Losses | Win Rate | Avg Conf |")
        lines.append("|--------|--------|---------|------|--------|----------|----------|")
        for r in summary.rows:
            lines.append(
                f"| {r.source_id} "
                f"| {r.regime_label} "
                f"| {r.sample_count} "
                f"| {r.win_count} "
                f"| {r.loss_count} "
                f"| {r.win_rate:.1%} "
                f"| {r.avg_confidence:.2f} |"
            )
        return "\n".join(lines)
