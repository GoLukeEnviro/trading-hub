"""Evidence Input Pipeline — Phase 2 closed-loop proposal layer.

Connectors that read trade attribution data from the source_regime_stats
SQLite cache and produce evidence bundles for downstream proposal/validation.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """Configuration for the evidence input pipeline.

    Attributes:
        db_path: Path to the source_regime_stats SQLite cache.
        source_filter: Optional source ID filter (e.g. "ai-hedge-fund-crypto").
        regime_filter: Optional regime filter (e.g. "bullish").
        since: Optional datetime filter — only evidence collected at or
            after this time is included.
    """

    db_path: Path
    source_filter: str | None = None
    regime_filter: str | None = None
    since: datetime | None = None


@dataclass
class PipelineEvidence:
    """A single evidence bundle item produced by the pipeline.

    Attributes:
        source: Signal source identifier.
        regime: Market regime label.
        total_trades: Total unique trades for this source+regime group.
        winning_trades: Number of winning trades.
        total_profit_pct: Cumulative weighted return as a percentage.
        avg_profit_pct: Average raw return per trade as a percentage.
        win_rate_pct: Win rate as a percentage (0-100).
        collected_at: UTC timestamp when this evidence was produced.
    """

    source: str
    regime: str
    total_trades: int
    winning_trades: int
    total_profit_pct: float
    avg_profit_pct: float
    win_rate_pct: float
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PipelineResult:
    """The result of running the evidence pipeline.

    Attributes:
        evidence_bundles: List of evidence items produced.
        config: The configuration used for this run.
        total_sources: Number of unique sources found.
        errors: Non-fatal error messages collected during pipeline execution.
    """

    evidence_bundles: list[PipelineEvidence]
    config: PipelineConfig
    total_sources: int
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AttributionCacheConnector
# ---------------------------------------------------------------------------


class AttributionCacheConnector:
    """Read-only connector to the source_regime_stats SQLite cache.

    This connector queries the ``source_regime_stats`` table and returns
    typed row data.  It never writes to or modifies the cache database.

    The table is expected to have this schema (defined in
    ``si_v2.source_regime_stats.db``):

    .. code-block:: sql

        CREATE TABLE source_regime_stats (
            source_id                TEXT NOT NULL,
            strategy_or_model_id     TEXT,
            pair                     TEXT NOT NULL,
            timeframe                TEXT NOT NULL,
            regime                   TEXT NOT NULL,
            confidence_bucket        TEXT NOT NULL,
            unique_trade_count       INTEGER NOT NULL DEFAULT 0,
            win_count                INTEGER NOT NULL DEFAULT 0,
            loss_count               INTEGER NOT NULL DEFAULT 0,
            breakeven_count          INTEGER NOT NULL DEFAULT 0,
            win_rate                 REAL NOT NULL DEFAULT 0.0,
            average_raw_return       REAL NOT NULL DEFAULT 0.0,
            average_weighted_return  REAL NOT NULL DEFAULT 0.0,
            cumulative_weighted_return REAL NOT NULL DEFAULT 0.0,
            ...
            PRIMARY KEY (source_id, strategy_or_model_id, pair,
                         timeframe, regime, confidence_bucket)
        );
    """

    _QUERY = """
        SELECT
            source_id,
            regime,
            unique_trade_count,
            win_count,
            cumulative_weighted_return,
            average_raw_return,
            win_rate
        FROM source_regime_stats
        WHERE 1=1
    """
    _SOURCE_FILTER = " AND source_id = ?"
    _REGIME_FILTER = " AND regime = ?"

    def __init__(self, db_path: str | Path) -> None:
        """Initialise the connector.

        Args:
            db_path: Path to the SQLite cache database.

        Raises:
            FileNotFoundError: If *db_path* does not exist.
        """
        self._db_path = Path(db_path)
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Cache database not found: {self._db_path}"
            )

    def read_rows(
        self,
        source_filter: str | None = None,
        regime_filter: str | None = None,
    ) -> Iterator[dict[str, object]]:
        """Yield rows from the source_regime_stats table as dicts.

        Applies optional source and/or regime filters.  The caller owns
        the connection lifecycle — each call opens, iterates, and closes.

        Args:
            source_filter: If given, only rows matching this source_id.
            regime_filter: If given, only rows matching this regime.

        Yields:
            dict[str, object]: Each row with keys matching the SELECT
                columns above.
        """
        query = self._QUERY
        params: list[str] = []

        if source_filter is not None:
            query += self._SOURCE_FILTER
            params.append(source_filter)
        if regime_filter is not None:
            query += self._REGIME_FILTER
            params.append(regime_filter)

        query += " ORDER BY source_id, regime"

        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            for row in cursor:
                yield dict(row)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# EvidencePipeline
# ---------------------------------------------------------------------------


class EvidencePipeline:
    """Orchestrates reading attribution data from the SQLite cache and
    producing evidence bundles for downstream consumption.
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Initialise the pipeline.

        Args:
            config: Pipeline configuration (db path, filters, etc.).
        """
        self._config = config

    @property
    def config(self) -> PipelineConfig:
        """Return the pipeline configuration."""
        return self._config

    def run(self) -> PipelineResult:
        """Execute the pipeline.

        Opens the cache database in read-only mode, queries
        ``source_regime_stats``, applies any configured filters, and
        builds a ``PipelineResult``.

        Returns:
            PipelineResult: Evidence bundles and execution metadata.
                Never raises on recoverable failures — errors are
                collected in the ``errors`` list.
        """
        errors: list[str] = []
        evidence_items: list[PipelineEvidence] = []
        sources_seen: set[str] = set()

        # ── Validate DB path exists ───────────────────────────────────
        db_path = self._config.db_path
        if not db_path.exists():
            errors.append(f"Cache database not found: {db_path}")
            return PipelineResult(
                evidence_bundles=[],
                config=self._config,
                total_sources=0,
                errors=errors,
            )

        # ── Open connection and read ──────────────────────────────────
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            errors.append(f"Cannot open cache database: {exc}")
            return PipelineResult(
                evidence_bundles=[],
                config=self._config,
                total_sources=0,
                errors=errors,
            )

        try:
            # Build the query with optional filters
            query = self._QUERY
            params: list[str] = []

            if self._config.source_filter is not None:
                query += " AND source_id = ?"
                params.append(self._config.source_filter)
            if self._config.regime_filter is not None:
                query += " AND regime = ?"
                params.append(self._config.regime_filter)

            query += " ORDER BY source_id, regime"

            cursor = conn.execute(query, params)

            rows = cursor.fetchall()
            if not rows:
                # Empty table is not an error — return zero counts
                return PipelineResult(
                    evidence_bundles=[],
                    config=self._config,
                    total_sources=0,
                    errors=errors,
                )

            for row in rows:
                source = str(row["source_id"])
                regime = str(row["regime"])
                total_trades = int(row["unique_trade_count"])
                winning_trades = int(row["win_count"])
                total_profit_pct = float(row["cumulative_weighted_return"])
                avg_profit_pct = float(row["average_raw_return"])
                win_rate_pct = float(row["win_rate"])

                sources_seen.add(source)

                evidence_items.append(
                    PipelineEvidence(
                        source=source,
                        regime=regime,
                        total_trades=total_trades,
                        winning_trades=winning_trades,
                        total_profit_pct=total_profit_pct,
                        avg_profit_pct=avg_profit_pct,
                        win_rate_pct=win_rate_pct,
                    )
                )

        except sqlite3.DatabaseError as exc:
            errors.append(f"Database error during query: {exc}")
            return PipelineResult(
                evidence_bundles=[],
                config=self._config,
                total_sources=0,
                errors=errors,
            )
        finally:
            conn.close()

        return PipelineResult(
            evidence_bundles=evidence_items,
            config=self._config,
            total_sources=len(sources_seen),
            errors=errors,
        )

    # Shared query — duplicated from AttributionCacheConnector for
    # self-contained operation.
    _QUERY = """
        SELECT
            source_id,
            regime,
            unique_trade_count,
            win_count,
            cumulative_weighted_return,
            average_raw_return,
            win_rate
        FROM source_regime_stats
        WHERE 1=1
    """
