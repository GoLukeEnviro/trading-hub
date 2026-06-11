"""AttributionReportBuilder — builds attribution reports from source_regime_stats SQLite cache.

Reads the derived cache and produces structured AttributionReport output with
period filtering, sample-count awareness, deterministic rankings, and safety
sanitization.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .models import (
    AttributionReport,
    ReportRequest,
    ReportSection,
    ReportWarning,
    ReportWarningType,
    WarningSeverity,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

QUERY_STATS_BY_SOURCE = """
SELECT
    source_id,
    SUM(unique_trade_count) AS total_trades,
    SUM(source_contribution_count) AS total_contributions,
    SUM(win_count) AS total_wins,
    SUM(loss_count) AS total_losses,
    SUM(breakeven_count) AS total_breakevens,
    CASE WHEN SUM(win_count + loss_count) > 0
        THEN CAST(SUM(win_count) AS REAL) / SUM(win_count + loss_count)
        ELSE 0.0
    END AS overall_win_rate,
    AVG(expectancy) AS avg_expectancy,
    SUM(cumulative_weighted_return) AS total_cumulative_return,
    MAX(drawdown_proxy) AS max_drawdown,
    AVG(average_source_confidence) AS avg_source_confidence,
    AVG(average_regime_confidence) AS avg_regime_confidence,
    MAX(evidence_max_closed_at) AS latest_evidence_time
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY source_id
ORDER BY source_id
"""

QUERY_STATS_BY_REGIME = """
SELECT
    regime,
    SUM(unique_trade_count) AS total_trades,
    SUM(source_contribution_count) AS total_contributions,
    SUM(win_count) AS total_wins,
    SUM(loss_count) AS total_losses,
    SUM(breakeven_count) AS total_breakevens,
    CASE WHEN SUM(win_count + loss_count) > 0
        THEN CAST(SUM(win_count) AS REAL) / SUM(win_count + loss_count)
        ELSE 0.0
    END AS overall_win_rate,
    AVG(expectancy) AS avg_expectancy,
    SUM(cumulative_weighted_return) AS total_cumulative_return,
    MAX(drawdown_proxy) AS max_drawdown
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY regime
ORDER BY regime
"""

QUERY_STATS_SOURCE_REGIME_MATRIX = """
SELECT
    source_id,
    regime,
    SUM(unique_trade_count) AS total_trades,
    SUM(source_contribution_count) AS total_contributions,
    SUM(win_count) AS total_wins,
    SUM(loss_count) AS total_losses,
    SUM(cumulative_weighted_return) AS total_cumulative_return
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY source_id, regime
ORDER BY source_id, regime
"""

QUERY_STATS_BY_PAIR_TIMEFRAME = """
SELECT
    pair,
    timeframe,
    SUM(unique_trade_count) AS total_trades,
    SUM(source_contribution_count) AS total_contributions,
    SUM(win_count) AS total_wins,
    SUM(loss_count) AS total_losses,
    CASE WHEN SUM(win_count + loss_count) > 0
        THEN CAST(SUM(win_count) AS REAL) / SUM(win_count + loss_count)
        ELSE 0.0
    END AS overall_win_rate,
    AVG(expectancy) AS avg_expectancy,
    SUM(cumulative_weighted_return) AS total_cumulative_return
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY pair, timeframe
ORDER BY pair, timeframe
"""

QUERY_STATS_BY_CONFIDENCE_BUCKET = """
SELECT
    confidence_bucket,
    SUM(unique_trade_count) AS total_trades,
    SUM(source_contribution_count) AS total_contributions,
    SUM(win_count) AS total_wins,
    SUM(loss_count) AS total_losses,
    CASE WHEN SUM(win_count + loss_count) > 0
        THEN CAST(SUM(win_count) AS REAL) / SUM(win_count + loss_count)
        ELSE 0.0
    END AS overall_win_rate,
    AVG(average_regime_confidence) AS avg_regime_confidence,
    AVG(expectancy) AS avg_expectancy
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY confidence_bucket
ORDER BY confidence_bucket
"""

QUERY_ALL_STATS = """
SELECT
    source_id,
    strategy_or_model_id,
    pair,
    timeframe,
    regime,
    confidence_bucket,
    unique_trade_count,
    source_contribution_count,
    win_count,
    loss_count,
    breakeven_count,
    win_rate,
    average_raw_return,
    average_weighted_return,
    expectancy,
    cumulative_weighted_return,
    drawdown_proxy,
    average_source_confidence,
    average_regime_confidence,
    evidence_max_closed_at
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
ORDER BY source_id, regime, pair, timeframe
"""

QUERY_METADATA = """
SELECT source_fingerprint, cache_schema_version, fact_schema_version,
       build_mode, last_evidence_time, operation_timestamp
FROM cache_metadata
WHERE id = 1
"""

QUERY_FACTS_FOR_REGIME_WARN = """
SELECT COUNT(*) as cnt
FROM attribution_facts
WHERE regime = 'unknown'
  AND (? IS NULL OR closed_at >= ?)
  AND (? IS NULL OR closed_at <= ?)
"""

QUERY_ALL_FACTS_COUNT = """
SELECT COUNT(*) as cnt
FROM attribution_facts
WHERE (? IS NULL OR closed_at >= ?)
  AND (? IS NULL OR closed_at <= ?)
"""

QUERY_NEGATIVE_EXPECTANCY = """
SELECT source_id, AVG(expectancy) AS avg_expectancy
FROM source_regime_stats
WHERE (? IS NULL OR evidence_max_closed_at >= ?)
  AND (? IS NULL OR evidence_max_closed_at <= ?)
GROUP BY source_id
HAVING avg_expectancy < 0
ORDER BY source_id
"""

# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class AttributionReportBuilder:
    """Builds attribution reports from a source_regime_stats SQLite cache.

    The builder queries the derived cache tables, applies period filtering via
    ``evidence_max_closed_at`` / ``closed_at``, generates deterministic
    rankings with sample-count awareness, and produces no trading
    recommendations.
    """

    def __init__(self, min_sample_count: int = 5) -> None:
        self._min_sample_count = min_sample_count

    def build(self, request: ReportRequest) -> AttributionReport:
        """Build a complete attribution report from the request.

        Args:
            request: Report request with DB path, period, and settings.

        Returns:
            Fully populated AttributionReport.

        Raises:
            FileNotFoundError: If the source DB does not exist.
            sqlite3.Error: On query failure.
        """
        db_path = Path(request.source_regime_stats_db_path)
        if not db_path.exists():
            msg = f"Source database not found: {db_path}"
            raise FileNotFoundError(msg)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            warnings: list[ReportWarning] = []
            sections: list[ReportSection] = []

            # Metadata
            metadata = self._query_metadata(conn)

            # Evidence quality overview
            sections.append(self._build_evidence_overview(conn, request, warnings))

            # Performance by source (with ranking)
            sections.append(
                self._build_performance_by_source(conn, request, warnings)
            )

            # Performance by regime
            sections.append(self._build_performance_by_regime(conn, request))

            # Source x Regime matrix
            sections.append(self._build_source_regime_matrix(conn, request))

            # Pair / timeframe splits
            sections.append(self._build_pair_timeframe_splits(conn, request))

            # Confidence bucket analysis
            sections.append(
                self._build_confidence_bucket_analysis(conn, request)
            )

            # UNKNOWN regime warnings
            sections.append(
                self._build_unknown_regime_warning(conn, request, warnings)
            )

            # Negative expectancy warnings
            sections.append(
                self._build_negative_expectancy_warning(
                    conn, request, warnings
                )
            )

            # Statistical limitations
            sections.append(
                self._build_statistical_limitations(
                    conn, request, warnings
                )
            )

            # Generate report ID
            id_raw = (
                f"{metadata.get('source_fingerprint', '')}:"
                f"{request.generated_at.isoformat()}"
            )
            report_id = hashlib.sha256(id_raw.encode("utf-8")).hexdigest()[:16]

            report = AttributionReport(
                report_id=report_id,
                schema_version=SCHEMA_VERSION,
                source_fingerprint=metadata.get("source_fingerprint", ""),
                period_start=request.period_start,
                period_end=request.period_end,
                generated_at=request.generated_at,
                sections=sections,
                warnings=warnings,
            )

        finally:
            conn.close()

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_md(text: str) -> str:
        """Escape special Markdown characters in user-supplied identifiers."""
        # Escape pipe, backslash, angle brackets, underscores, asterisks
        # that could break table formatting or be interpreted as markers.
        replacements = [
            ("\\", "\\\\"),
            ("|", "\\|"),
            ("<", "&lt;"),
            (">", "&gt;"),
            ("_", "\\_"),
            ("*", "\\*"),
            ("`", "\\`"),
            ("[", "\\["),
            ("]", "\\]"),
            ("(", "\\("),
            (")", "\\)"),
        ]
        result = text
        for old, new in replacements:
            result = result.replace(old, new)
        return result

    @staticmethod
    def _sanitize_row_dict(
        row: dict[str, object],
    ) -> dict[str, object]:
        """Remove secrets, raw ledger, and sensitive fields from a row dict."""
        sensitive_prefixes = (
            "api_",
            "secret",
            "password",
            "token",
            "key",
            "private",
        )
        return {
            k: v
            for k, v in row.items()
            if not any(k.lower().startswith(p) for p in sensitive_prefixes)
        }

    def _query_with_period(
        self,
        conn: sqlite3.Connection,
        query: str,
        request: ReportRequest,
    ) -> list[dict[str, object]]:
        """Execute a query with period filtering parameters."""
        period_start_iso = (
            request.period_start.isoformat() if request.period_start else None
        )
        period_end_iso = (
            request.period_end.isoformat() if request.period_end else None
        )
        cursor = conn.execute(
            query,
            (
                period_start_iso,
                period_start_iso,
                period_end_iso,
                period_end_iso,
            ),
        )
        return [dict(row) for row in cursor.fetchall()]

    def _query_metadata(
        self, conn: sqlite3.Connection
    ) -> dict[str, str]:
        """Query cache metadata row."""
        cursor = conn.execute(QUERY_METADATA)
        row = cursor.fetchone()
        if row is None:
            return {}
        return dict(row)

    def _total_fact_count(
        self, conn: sqlite3.Connection, request: ReportRequest
    ) -> int:
        """Get total number of facts in the cache (with period filter)."""
        period_start_iso = (
            request.period_start.isoformat() if request.period_start else None
        )
        period_end_iso = (
            request.period_end.isoformat() if request.period_end else None
        )
        cursor = conn.execute(
            QUERY_ALL_FACTS_COUNT,
            (period_start_iso, period_start_iso, period_end_iso, period_end_iso),
        )
        row = cursor.fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_evidence_overview(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
        warnings: list[ReportWarning],
    ) -> ReportSection:
        """Build the evidence quality overview section."""
        metadata = self._query_metadata(conn)
        total_facts = self._total_fact_count(conn, request)

        all_rows = self._query_with_period(conn, QUERY_ALL_STATS, request)
        total_stats_rows = len(all_rows)
        unique_sources = len(
            {r["source_id"] for r in all_rows if r.get("source_id")}
        )
        unique_regimes = len(
            {r["regime"] for r in all_rows if r.get("regime")}
        )
        unique_pairs = len(
            {r["pair"] for r in all_rows if r.get("pair")}
        )

        lines: list[str] = []
        lines.append(f"- **Cache schema version:** {metadata.get('cache_schema_version', 'N/A')}")
        lines.append(f"- **Fact schema version:** {metadata.get('fact_schema_version', 'N/A')}")
        lines.append(f"- **Source fingerprint:** `{metadata.get('source_fingerprint', 'N/A')[:16]}...`")
        lines.append(f"- **Build mode:** {metadata.get('build_mode', 'N/A')}")
        lines.append(f"- **Total attribution facts (period):** {total_facts}")
        lines.append(f"- **Source-regime statistic rows:** {total_stats_rows}")
        lines.append(f"- **Unique sources:** {unique_sources}")
        lines.append(f"- **Unique regimes:** {unique_regimes}")
        lines.append(f"- **Unique pairs:** {unique_pairs}")
        lines.append(f"- **Generated at:** {request.generated_at.isoformat()}")

        if total_facts == 0:
            warnings.append(
                ReportWarning(
                    type=ReportWarningType.UNSUFFICIENT_DATA,
                    message=(
                        "No attribution facts found in the reporting period. "
                        "Report sections will be empty."
                    ),
                    severity=WarningSeverity.WARNING,
                )
            )

        data: dict[str, object] = {
            "total_facts": total_facts,
            "total_stats_rows": total_stats_rows,
            "unique_sources": unique_sources,
            "unique_regimes": unique_regimes,
            "unique_pairs": unique_pairs,
            "cache_schema_version": metadata.get("cache_schema_version", ""),
            "fact_schema_version": metadata.get("fact_schema_version", ""),
            "source_fingerprint": metadata.get("source_fingerprint", ""),
            "build_mode": metadata.get("build_mode", ""),
        }

        return ReportSection(
            title="Evidence Quality Overview",
            content="\n".join(lines),
            data=data,
        )

    def _build_performance_by_source(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
        warnings: list[ReportWarning],
    ) -> ReportSection:
        """Build performance-by-source ranking with sample-count guard.

        Ranking rules:
        - Only sources with >= min_sample_count are ranked.
        - Sources below the threshold appear in an "insufficient evidence" group.
        - Sorting is by expectancy descending, then by source_id ascending
          for deterministic tie-breaking.
        - Sample count displayed beside every entry.
        """
        rows = self._query_with_period(conn, QUERY_STATS_BY_SOURCE, request)

        # Classify
        ranked: list[dict[str, object]] = []
        insufficient: list[dict[str, object]] = []

        for r in rows:
            r["total_trades"] = int(r.get("total_trades", 0))  # type: ignore[arg-type]
            r["total_contributions"] = int(r.get("total_contributions", 0))  # type: ignore[arg-type]
            r["total_wins"] = int(r.get("total_wins", 0))  # type: ignore[arg-type]
            r["total_losses"] = int(r.get("total_losses", 0))  # type: ignore[arg-type]
            r["total_breakevens"] = int(r.get("total_breakevens", 0))  # type: ignore[arg-type]
            r["overall_win_rate"] = float(r.get("overall_win_rate", 0.0))
            r["avg_expectancy"] = float(r.get("avg_expectancy", 0.0))
            r["total_cumulative_return"] = float(
                r.get("total_cumulative_return", 0.0)
            )
            r["max_drawdown"] = float(r.get("max_drawdown", 0.0))
            r["avg_source_confidence"] = float(
                r.get("avg_source_confidence", 0.0)
            )
            r["avg_regime_confidence"] = float(
                r.get("avg_regime_confidence", 0.0)
            )

            if int(r["total_trades"]) >= self._min_sample_count:
                ranked.append(r)
            else:
                insufficient.append(r)

            # Warn for low-sample sources
            if int(r["total_trades"]) < self._min_sample_count:
                warnings.append(
                    ReportWarning(
                        type=ReportWarningType.LOW_SAMPLE,
                        message=(
                            f"Source '{r.get('source_id', '?')!s}' has "
                            f"only {r['total_trades']} trades "
                            f"(minimum {self._min_sample_count} required). "
                            "Excluded from ranking."
                        ),
                        severity=WarningSeverity.INFO,
                    )
                )

        # Deterministic sorting: expectancy desc, source_id asc
        ranked.sort(
            key=lambda r: (
                -float(r.get("avg_expectancy", 0.0)),
                str(r.get("source_id", "")),
            )
        )
        insufficient.sort(key=lambda r: str(r.get("source_id", "")))

        lines: list[str] = []
        lines.append(
            "| Rank | Source | Trades | Wins | Losses | "
            "Win Rate | Expectancy | Cum Return | Drawdown | Avg Conf |"
        )
        lines.append(
            "|------|--------|--------|------|--------|"
            "----------|------------|------------|----------|----------|"
        )

        for idx, r in enumerate(ranked, start=1):
            src = self._escape_md(str(r.get("source_id", "?")))
            trades = r["total_trades"]
            wins = r["total_wins"]
            losses = r["total_losses"]
            wr = r["overall_win_rate"]
            exp = r["avg_expectancy"]
            cum = r["total_cumulative_return"]
            dd = r["max_drawdown"]
            conf = r["avg_source_confidence"]

            lines.append(
                f"| {idx} | {src} | {trades} | {wins} | {losses} | "
                f"{wr:.1%} | {exp:.6f} | {cum:.6f} | {dd:.6f} | {conf:.3f} |"
            )

        if insufficient:
            lines.append("")
            lines.append("### Insufficient Evidence (excluded from ranking)")
            lines.append("")
            lines.append(
                "| Source | Trades | Wins | Losses | "
                "Win Rate | Expectancy | Conf |"
            )
            lines.append(
                "|--------|--------|------|--------|"
                "----------|------------|------|"
            )
            for r in insufficient:
                src = self._escape_md(str(r.get("source_id", "?")))
                trades = r["total_trades"]
                wins = r["total_wins"]
                losses = r["total_losses"]
                wr = r["overall_win_rate"]
                exp = r["avg_expectancy"]
                conf = r["avg_source_confidence"]
                lines.append(
                    f"| {src} | {trades} | {wins} | {losses} | "
                    f"{wr:.1%} | {exp:.6f} | {conf:.3f} |"
                )

        if not ranked and not insufficient:
            lines.append("*No source data available.*")

        data: dict[str, object] = {
            "min_sample_count": self._min_sample_count,
            "ranked": [
                {
                    "source_id": r.get("source_id", ""),
                    "total_trades": r["total_trades"],
                    "win_count": r["total_wins"],
                    "loss_count": r["total_losses"],
                    "breakeven_count": r["total_breakevens"],
                    "win_rate": r["overall_win_rate"],
                    "expectancy": r["avg_expectancy"],
                    "cumulative_return": r["total_cumulative_return"],
                    "drawdown": r["max_drawdown"],
                    "avg_confidence": r["avg_source_confidence"],
                }
                for r in ranked
            ],
            "insufficient_evidence": [
                {
                    "source_id": r.get("source_id", ""),
                    "total_trades": r["total_trades"],
                    "win_count": r["total_wins"],
                    "loss_count": r["total_losses"],
                    "breakeven_count": r["total_breakevens"],
                    "win_rate": r["overall_win_rate"],
                    "expectancy": r["avg_expectancy"],
                }
                for r in insufficient
            ],
        }

        return ReportSection(
            title="Performance by Source",
            content="\n".join(lines),
            data=data,
        )

    def _build_performance_by_regime(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
    ) -> ReportSection:
        """Build performance summary grouped by market regime."""
        rows = self._query_with_period(conn, QUERY_STATS_BY_REGIME, request)

        for r in rows:
            r["total_trades"] = int(r.get("total_trades", 0))
            r["total_wins"] = int(r.get("total_wins", 0))
            r["total_losses"] = int(r.get("total_losses", 0))
            r["overall_win_rate"] = float(r.get("overall_win_rate", 0.0))
            r["avg_expectancy"] = float(r.get("avg_expectancy", 0.0))
            r["total_cumulative_return"] = float(
                r.get("total_cumulative_return", 0.0)
            )
            r["max_drawdown"] = float(r.get("max_drawdown", 0.0))

        lines: list[str] = []
        lines.append(
            "| Regime | Trades | Wins | Losses | "
            "Win Rate | Expectancy | Cum Return | Drawdown |"
        )
        lines.append(
            "|--------|--------|------|--------|"
            "----------|------------|------------|----------|"
        )
        for r in rows:
            regime = self._escape_md(str(r.get("regime", "?")))
            trades = r["total_trades"]
            wins = r["total_wins"]
            losses = r["total_losses"]
            wr = r["overall_win_rate"]
            exp = r["avg_expectancy"]
            cum = r["total_cumulative_return"]
            dd = r["max_drawdown"]
            lines.append(
                f"| {regime} | {trades} | {wins} | {losses} | "
                f"{wr:.1%} | {exp:.6f} | {cum:.6f} | {dd:.6f} |"
            )

        if not rows:
            lines.append("*No regime data available.*")

        data: dict[str, object] = {
            "regimes": [
                {
                    "regime": r.get("regime", ""),
                    "total_trades": r["total_trades"],
                    "win_count": r["total_wins"],
                    "loss_count": r["total_losses"],
                    "win_rate": r["overall_win_rate"],
                    "expectancy": r["avg_expectancy"],
                    "cumulative_return": r["total_cumulative_return"],
                    "drawdown": r["max_drawdown"],
                }
                for r in rows
            ]
        }

        return ReportSection(
            title="Performance by Regime",
            content="\n".join(lines),
            data=data,
        )

    def _build_source_regime_matrix(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
    ) -> ReportSection:
        """Build the source x regime performance matrix."""
        rows = self._query_with_period(
            conn, QUERY_STATS_SOURCE_REGIME_MATRIX, request
        )

        for r in rows:
            r["total_trades"] = int(r.get("total_trades", 0))
            r["total_wins"] = int(r.get("total_wins", 0))
            r["total_losses"] = int(r.get("total_losses", 0))
            r["total_cumulative_return"] = float(
                r.get("total_cumulative_return", 0.0)
            )

        # Collect unique sources and regimes for header
        sources: list[str] = sorted(
            {str(r["source_id"]) for r in rows if r.get("source_id")}
        )
        regimes: list[str] = sorted(
            {str(r["regime"]) for r in rows if r.get("regime")}
        )

        # Build lookup
        lookup: dict[tuple[str, str], dict[str, object]] = {}
        for r in rows:
            key = (str(r["source_id"]), str(r["regime"]))
            lookup[key] = r

        lines: list[str] = []

        # Build a table: rows = sources, columns = regimes
        header_cells = ["Source"] + [self._escape_md(r) for r in regimes]
        lines.append("| " + " | ".join(header_cells) + " |")
        lines.append(
            "|" + "|".join("------" for _ in range(len(header_cells))) + "|"
        )

        for src in sources:
            cells: list[str] = [self._escape_md(src)]
            for reg in regimes:
                r = lookup.get((src, reg))
                if r is not None:
                    cum = float(r.get("total_cumulative_return", 0.0))
                    trades = int(r.get("total_trades", 0))
                    cells.append(f"{cum:.4f} ({trades})")
                else:
                    cells.append("—")
            lines.append("| " + " | ".join(cells) + " |")

        if not rows:
            lines.append("*No source-regime matrix data available.*")

        matrix_data: list[dict[str, object]] = []
        for r in rows:
            matrix_data.append(
                {
                    "source_id": r.get("source_id", ""),
                    "regime": r.get("regime", ""),
                    "total_trades": r["total_trades"],
                    "total_wins": r["total_wins"],
                    "total_losses": r["total_losses"],
                    "cumulative_return": r["total_cumulative_return"],
                }
            )

        data: dict[str, object] = {
            "sources": sources,
            "regimes": regimes,
            "matrix": matrix_data,
        }

        return ReportSection(
            title="Source x Regime Matrix",
            content="\n".join(lines),
            data=data,
        )

    def _build_pair_timeframe_splits(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
    ) -> ReportSection:
        """Build performance grouped by pair and timeframe."""
        rows = self._query_with_period(
            conn, QUERY_STATS_BY_PAIR_TIMEFRAME, request
        )

        for r in rows:
            r["total_trades"] = int(r.get("total_trades", 0))
            r["total_wins"] = int(r.get("total_wins", 0))
            r["total_losses"] = int(r.get("total_losses", 0))
            r["overall_win_rate"] = float(r.get("overall_win_rate", 0.0))
            r["avg_expectancy"] = float(r.get("avg_expectancy", 0.0))
            r["total_cumulative_return"] = float(
                r.get("total_cumulative_return", 0.0)
            )

        lines: list[str] = []
        lines.append(
            "| Pair | Timeframe | Trades | Wins | Losses | "
            "Win Rate | Expectancy | Cum Return |"
        )
        lines.append(
            "|------|-----------|--------|------|--------|"
            "----------|------------|------------|"
        )
        for r in rows:
            pair = self._escape_md(str(r.get("pair", "?")))
            tf = self._escape_md(str(r.get("timeframe", "?")))
            trades = r["total_trades"]
            wins = r["total_wins"]
            losses = r["total_losses"]
            wr = r["overall_win_rate"]
            exp = r["avg_expectancy"]
            cum = r["total_cumulative_return"]
            lines.append(
                f"| {pair} | {tf} | {trades} | {wins} | {losses} | "
                f"{wr:.1%} | {exp:.6f} | {cum:.6f} |"
            )

        if not rows:
            lines.append("*No pair/timeframe data available.*")

        data: dict[str, object] = {
            "splits": [
                {
                    "pair": r.get("pair", ""),
                    "timeframe": r.get("timeframe", ""),
                    "total_trades": r["total_trades"],
                    "win_count": r["total_wins"],
                    "loss_count": r["total_losses"],
                    "win_rate": r["overall_win_rate"],
                    "expectancy": r["avg_expectancy"],
                    "cumulative_return": r["total_cumulative_return"],
                }
                for r in rows
            ]
        }

        return ReportSection(
            title="Pair / Timeframe Splits",
            content="\n".join(lines),
            data=data,
        )

    def _build_confidence_bucket_analysis(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
    ) -> ReportSection:
        """Build confidence bucket analysis.

        Warnings are generated for confidence buckets with low sample counts
        and for buckets where expectancy is negative.
        """
        rows = self._query_with_period(
            conn, QUERY_STATS_BY_CONFIDENCE_BUCKET, request
        )

        for r in rows:
            r["total_trades"] = int(r.get("total_trades", 0))
            r["total_wins"] = int(r.get("total_wins", 0))
            r["total_losses"] = int(r.get("total_losses", 0))
            r["overall_win_rate"] = float(r.get("overall_win_rate", 0.0))
            r["avg_regime_confidence"] = float(
                r.get("avg_regime_confidence", 0.0)
            )
            r["avg_expectancy"] = float(r.get("avg_expectancy", 0.0))

        lines: list[str] = []
        lines.append(
            "| Confidence Bucket | Trades | Wins | Losses | "
            "Win Rate | Avg Regime Conf | Avg Expectancy |"
        )
        lines.append(
            "|--------------------|--------|------|--------|"
            "----------|-----------------|----------------|"
        )
        for r in rows:
            bucket = self._escape_md(str(r.get("confidence_bucket", "?")))
            trades = r["total_trades"]
            wins = r["total_wins"]
            losses = r["total_losses"]
            wr = r["overall_win_rate"]
            conf = r["avg_regime_confidence"]
            exp = r["avg_expectancy"]
            lines.append(
                f"| {bucket} | {trades} | {wins} | {losses} | "
                f"{wr:.1%} | {conf:.3f} | {exp:.6f} |"
            )

        if not rows:
            lines.append("*No confidence bucket data available.*")

        data: dict[str, object] = {
            "buckets": [
                {
                    "confidence_bucket": r.get("confidence_bucket", ""),
                    "total_trades": r["total_trades"],
                    "win_count": r["total_wins"],
                    "loss_count": r["total_losses"],
                    "win_rate": r["overall_win_rate"],
                    "avg_regime_confidence": r["avg_regime_confidence"],
                    "avg_expectancy": r["avg_expectancy"],
                }
                for r in rows
            ]
        }

        return ReportSection(
            title="Confidence-Bucket Analysis",
            content="\n".join(lines),
            data=data,
        )

    def _build_unknown_regime_warning(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
        warnings: list[ReportWarning],
    ) -> ReportSection:
        """Build UNKNOWN regime warning section."""
        period_start_iso = (
            request.period_start.isoformat() if request.period_start else None
        )
        period_end_iso = (
            request.period_end.isoformat() if request.period_end else None
        )

        cursor = conn.execute(
            QUERY_FACTS_FOR_REGIME_WARN,
            (
                period_start_iso,
                period_start_iso,
                period_end_iso,
                period_end_iso,
            ),
        )
        row = cursor.fetchone()
        unknown_count = row["cnt"] if row else 0

        total_all = self._total_fact_count(conn, request)

        lines: list[str] = []
        if unknown_count > 0:
            pct = (unknown_count / total_all * 100) if total_all > 0 else 0.0
            lines.append(
                f"A total of **{unknown_count}** fact(s) ({pct:.1f}%) "
                "are classified under the **UNKNOWN** regime — "
                "indicating insufficient data for regime classification."
            )
            lines.append("")
            lines.append(
                "These facts may degrade the reliability of per-regime "
                "aggregates and should be interpreted with caution."
            )
            warnings.append(
                ReportWarning(
                    type=ReportWarningType.UNKNOWN_REGIME,
                    message=(
                        f"{unknown_count} attribution fact(s) ({pct:.1f}%) "
                        "are under UNKNOWN regime."
                    ),
                    severity=WarningSeverity.WARNING,
                )
            )
        else:
            lines.append("No facts with UNKNOWN regime classification found.")

        data: dict[str, object] = {
            "unknown_fact_count": unknown_count,
            "total_fact_count": total_all,
            "unknown_pct": round(
                (unknown_count / total_all * 100) if total_all > 0 else 0.0, 2
            ),
        }

        return ReportSection(
            title="UNKNOWN Regime Warnings",
            content="\n".join(lines),
            data=data,
        )

    def _build_negative_expectancy_warning(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
        warnings: list[ReportWarning],
    ) -> ReportSection:
        """Build negative / flat expectancy warning section."""
        rows = self._query_with_period(
            conn, QUERY_NEGATIVE_EXPECTANCY, request
        )

        lines: list[str] = []
        for r in rows:
            src = str(r.get("source_id", "?"))
            exp = float(r.get("avg_expectancy", 0.0))
            warnings.append(
                ReportWarning(
                    type=ReportWarningType.NEGATIVE_EXPECTANCY,
                    message=(
                        f"Source '{src}' has negative expectancy "
                        f"({exp:.6f})."
                    ),
                    severity=WarningSeverity.WARNING,
                )
            )

        if rows:
            lines.append(
                "The following sources exhibit **negative expectancy**, "
                "meaning their average weighted return is below zero:"
            )
            lines.append("")
            for r in rows:
                src = self._escape_md(str(r.get("source_id", "?")))
                exp = float(r.get("avg_expectancy", 0.0))
                lines.append(f"- **{src}**: expectancy = {exp:.6f}")
        else:
            lines.append("No sources with negative expectancy detected.")

        data: dict[str, object] = {
            "negative_expectancy_sources": [
                {
                    "source_id": r.get("source_id", ""),
                    "avg_expectancy": float(r.get("avg_expectancy", 0.0)),
                }
                for r in rows
            ]
        }

        return ReportSection(
            title="Negative / Flat Expectancy Warnings",
            content="\n".join(lines),
            data=data,
        )

    def _build_statistical_limitations(
        self,
        conn: sqlite3.Connection,
        request: ReportRequest,
        warnings: list[ReportWarning],
    ) -> ReportSection:
        """Build statistical limitations section with warnings."""
        total_facts = self._total_fact_count(conn, request)
        all_rows = self._query_with_period(conn, QUERY_ALL_STATS, request)

        low_sample_count = sum(
            1
            for r in all_rows
            if int(r.get("unique_trade_count", 0)) < self._min_sample_count
        )
        high_drawdown_count = 0
        for r in all_rows:
            dd = float(r.get("drawdown_proxy", 0.0))
            if dd > 0.3:  # 30% drawdown threshold
                high_drawdown_count += 1

        lines: list[str] = []
        lines.append(
            "This report is generated from the `source_regime_stats` "
            "derived cache and is subject to the following limitations:"
        )
        lines.append("")
        lines.append(
            f"- **Minimum sample count:** {self._min_sample_count} trades "
            "required for ranking inclusion."
        )
        lines.append(
            f"- **Low-sample rows:** {low_sample_count} dimension-group row(s) "
            f"have fewer than {self._min_sample_count} trades and are excluded "
            "from rankings."
        )
        lines.append(
            f"- **Period filter:** "
            f"{request.period_start.isoformat() if request.period_start else 'none'} → "
            f"{request.period_end.isoformat() if request.period_end else 'none'}"
        )
        lines.append(
            "- **No trading decisions:** This report provides informational "
            "metrics only — no trading, weight, or allocation recommendations "
            "are made."
        )
        lines.append(
            "- **No raw ledger data:** All metrics are aggregated; no raw "
            "trade records are exposed."
        )
        lines.append(
            "- **Drawdown is a proxy:** Based on time-ordered weighted returns "
            "within dimension groups, not full portfolio drawdown."
        )

        if high_drawdown_count > 0:
            lines.append("")
            lines.append(
                f"⚠️ **{high_drawdown_count}** dimension-group row(s) exhibit "
                "drawdown proxy exceeding 30%. "
            )
            for r in all_rows:
                dd = float(r.get("drawdown_proxy", 0.0))
                if dd > 0.3:
                    dd_val = dd
                    src = str(r.get("source_id", "?"))
                    reg = str(r.get("regime", "?"))
                    lines.append(
                        f"  - {self._escape_md(src)} / "
                        f"{self._escape_md(reg)}: "
                        f"drawdown = {dd_val:.2%}"
                    )
                    warnings.append(
                        ReportWarning(
                            type=ReportWarningType.DRAWDOWN,
                            message=(
                                f"High drawdown ({dd_val:.2%}) for "
                                f"source '{src}' under regime '{reg}'."
                            ),
                            severity=WarningSeverity.WARNING,
                        )
                    )

        data: dict[str, object] = {
            "total_facts": total_facts,
            "min_sample_count": self._min_sample_count,
            "low_sample_rows": low_sample_count,
            "high_drawdown_rows": high_drawdown_count,
            "period_start": (
                request.period_start.isoformat()
                if request.period_start
                else None
            ),
            "period_end": (
                request.period_end.isoformat()
                if request.period_end
                else None
            ),
        }

        return ReportSection(
            title="Statistical Limitations",
            content="\n".join(lines),
            data=data,
        )
