"""Rainbow signal-to-trade attribution producer.

Creates AttributionInput records for closed dry-run trades where a
validated, fresh Rainbow signal existed for the pair/time window.

Safety invariants:
- Attribution is evidence only, never execution authority.
- No fake/default credit when no valid signal existed.
- Contribution weights sum to 1.0.
- Read-only regarding live trading gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from si_v2.attribution.models import (
    AttributionInput,
    RegimeLabel,
    SignalContribution,
)

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]
Envelope = dict[str, object]


@dataclass
class RainbowAttributionProducerConfig:
    """Configuration for the Rainbow attribution producer."""

    max_signal_age_seconds: float = 3600.0
    """Maximum age of a signal to be considered fresh for attribution."""

    default_contribution_weight: float = 1.0
    """Default weight when Rainbow is the only signal source."""

    default_source_confidence: float | None = None
    """Default source confidence when the signal doesn't provide one."""


@dataclass
class RainbowAttributionResult:
    """Result of producing attribution inputs from signals + trades."""

    inputs: list[AttributionInput] = field(default_factory=list)
    """Produced attribution inputs, one per matched trade."""

    skipped_trades: list[str] = field(default_factory=list)
    """Trade IDs skipped because no fresh Rainbow signal was found."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors encountered during processing."""

    matched_count: int = 0
    """Number of trades with a matching fresh signal."""


class RainbowAttributionProducer:
    """Produce AttributionInput records from Rainbow signals and closed trades.

    For each closed dry-run trade, the producer looks for a validated,
    fresh Rainbow signal for the same pair within the decision window.
    If found, an AttributionInput with SignalContribution(source_id="rainbow:*")
    is created.
    """

    def __init__(
        self,
        config: RainbowAttributionProducerConfig | None = None,
    ) -> None:
        self._config = config or RainbowAttributionProducerConfig()

    def produce(
        self,
        signals: list[Envelope],
        trades: list[dict[str, object]],
        now: datetime | None = None,
    ) -> RainbowAttributionResult:
        """Produce attribution inputs from signals and closed trades.

        Args:
            signals: Validated Rainbow signal envelopes.
            trades: Closed dry-run trade records. Each must have:
                - trade_id (str)
                - pair (str)
                - close_time (str, ISO-8601)
                - realized_return (float)
                - timeframe (str, optional, default "1h")
            now: Current time for freshness checks. Defaults to UTC now.

        Returns:
            RainbowAttributionResult with produced inputs and diagnostics.
        """
        if now is None:
            now = datetime.now(UTC)

        result = RainbowAttributionResult()

        # Index signals by pair for efficient lookup
        signals_by_pair: dict[str, list[Envelope]] = {}
        for signal in signals:
            pair = self._extract_pair(signal)
            if pair:
                signals_by_pair.setdefault(pair, []).append(signal)

        for trade in trades:
            trade_id = self._safe_str(trade, "trade_id")
            pair = self._safe_str(trade, "pair")
            close_time_str = self._safe_str(trade, "close_time")
            realized_return = self._safe_float(trade, "realized_return")
            timeframe = self._safe_str(trade, "timeframe") or "1h"

            if not trade_id or not pair or not close_time_str or realized_return is None:
                result.errors.append(
                    f"Trade missing required fields: trade_id={trade_id}, "
                    f"pair={pair}, close_time={close_time_str}, "
                    f"realized_return={realized_return}"
                )
                continue

            # Parse close time
            try:
                close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                result.errors.append(
                    f"Trade {trade_id}: invalid close_time: {close_time_str}"
                )
                continue

            # Find a fresh signal for this pair
            matching_signal = self._find_fresh_signal(
                pair, signals_by_pair.get(pair, []), close_time, now
            )

            if matching_signal is None:
                result.skipped_trades.append(trade_id)
                continue

            # Extract signal metadata for the contribution
            source_id = self._safe_str(matching_signal, "source_id") or "rainbow:unknown"
            source_confidence = self._safe_float(matching_signal, "confidence")
            if source_confidence is None:
                source_confidence = self._config.default_source_confidence

            # Determine regime from signal direction
            direction = self._safe_str(matching_signal, "direction")
            regime = self._direction_to_regime(direction)

            # Create the attribution input
            attribution_input = AttributionInput(
                trade_id=trade_id,
                source_event_id=source_id,
                pair=pair,
                timeframe=timeframe,
                closed_at=close_time,
                realized_return=realized_return,
                regime=regime,
                regime_confidence=0.5,  # neutral default for signal-based regime
                signal_contributions=[
                    SignalContribution(
                        source_id=source_id,
                        contribution_weight=self._config.default_contribution_weight,
                        source_confidence=source_confidence,
                        model_or_strategy_id=self._safe_str(
                            matching_signal, "strategy_id"
                        ),
                    ),
                ],
            )

            result.inputs.append(attribution_input)
            result.matched_count += 1

        return result

    def _find_fresh_signal(
        self,
        pair: str,
        signals: list[Envelope],
        trade_close_time: datetime,
        now: datetime,
    ) -> Envelope | None:
        """Find the freshest valid signal for a pair within the decision window.

        A signal is considered fresh if its timestamp is within
        max_signal_age_seconds of the trade close time.
        """
        max_age = timedelta(seconds=self._config.max_signal_age_seconds)
        window_start = trade_close_time - max_age

        fresh_signals: list[tuple[datetime, Envelope]] = []
        for signal in signals:
            ts_str = self._safe_str(signal, "timestamp_utc")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Signal must be within the decision window before trade close
            if window_start <= ts <= trade_close_time:
                fresh_signals.append((ts, signal))

        if not fresh_signals:
            return None

        # Return the most recent signal
        fresh_signals.sort(key=lambda x: x[0], reverse=True)
        return fresh_signals[0][1]

    @staticmethod
    def _extract_pair(signal: Envelope) -> str | None:
        """Extract the trading pair from a signal envelope."""
        symbol = signal.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            return symbol.strip()
        return None

    @staticmethod
    def _direction_to_regime(direction: str | None) -> RegimeLabel:
        """Map a signal direction to a regime label."""
        if direction is None:
            return RegimeLabel.UNKNOWN
        mapping = {
            "long": RegimeLabel.BULLISH,
            "short": RegimeLabel.BEARISH,
            "flat": RegimeLabel.NEUTRAL,
            "no_signal": RegimeLabel.NEUTRAL,
        }
        return mapping.get(direction.lower(), RegimeLabel.UNKNOWN)

    @staticmethod
    def _safe_str(d: dict[str, object], key: str) -> str | None:
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    @staticmethod
    def _safe_float(d: dict[str, object], key: str) -> float | None:
        val = d.get(key)
        if isinstance(val, (int, float)):
            return float(val)
        return None
