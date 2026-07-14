"""SI v2 Fleet Drawdown Guard — HWM and daily drawdown protection.

This module implements the minimal fleet drawdown guard with two independent
clocks:

1. High-water-mark (HWM) fleet drawdown — tracks the peak equity and triggers
   HALT_NEW when drawdown from the peak exceeds the configured threshold.
2. Calendar-day loss/drawdown — tracks the day's starting equity and triggers
   HALT_NEW when the day's loss exceeds the configured threshold.

Design principles
-----------------
- Pure and deterministic: no exchange I/O, no REST calls, no config mutation.
- Fail closed when required state is corrupt, stale, or unavailable.
- HWM and daily limits are independent; a day reset must not reset HWM protection.
- Never auto-clear an HWM breach solely because a new day starts.
- Trigger processing is idempotent.
- Uses the existing kill_switch.py for triggering HALT_NEW.
- State persistence via JSON file (atomic writes, same pattern as kill_switch).

Usage
-----
    from si_v2.risk.fleet_drawdown_guard import FleetDrawdownGuard

    guard = FleetDrawdownGuard(
        hwm_drawdown_pct=Decimal("25.0"),   # 25% HWM drawdown threshold
        daily_loss_pct=Decimal("10.0"),      # 10% daily loss threshold
    )

    # Called each tick with current equity
    result = guard.evaluate(equity=Decimal("95000"), timestamp=now)
    if result.triggered:
        # HALT_NEW was set
        print(result.reason)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger("fleet_drawdown_guard")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STATE_FILE = "var/fleet_drawdown_state.json"

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawdownEvaluation:
    """Result of a single drawdown evaluation tick.

    Attributes
    ----------
    triggered: Whether HALT_NEW was triggered by this evaluation.
    reason: Human-readable reason for the trigger, or empty string.
    hwm_drawdown_pct: Current drawdown from HWM as a percentage (0 = at HWM).
    daily_drawdown_pct: Current drawdown from day start as a percentage.
    hwm_equity: The current high-water-mark equity value.
    day_start_equity: The equity at the start of the current trading day.
    current_equity: The equity value that was evaluated.
    """

    triggered: bool = False
    reason: str = ""
    hwm_drawdown_pct: Decimal = Decimal("0")
    daily_drawdown_pct: Decimal = Decimal("0")
    hwm_equity: Decimal = Decimal("0")
    day_start_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


@dataclass
class DrawdownState:
    """Persistent state for the fleet drawdown guard."""

    hwm_equity: Decimal = Decimal("0")
    hwm_timestamp: str = ""
    day_start_equity: Decimal = Decimal("0")
    day_date: str = ""
    last_equity: Decimal = Decimal("0")
    last_update: str = ""
    hwm_breach_triggered: bool = False
    daily_breach_triggered: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "hwm_equity": str(self.hwm_equity),
            "hwm_timestamp": self.hwm_timestamp,
            "day_start_equity": str(self.day_start_equity),
            "day_date": self.day_date,
            "last_equity": str(self.last_equity),
            "last_update": self.last_update,
            "hwm_breach_triggered": self.hwm_breach_triggered,
            "daily_breach_triggered": self.daily_breach_triggered,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DrawdownState:
        return cls(
            hwm_equity=Decimal(data.get("hwm_equity", "0")),
            hwm_timestamp=data.get("hwm_timestamp", ""),
            day_start_equity=Decimal(data.get("day_start_equity", "0")),
            day_date=data.get("day_date", ""),
            last_equity=Decimal(data.get("last_equity", "0")),
            last_update=data.get("last_update", ""),
            hwm_breach_triggered=data.get("hwm_breach_triggered", False),
            daily_breach_triggered=data.get("daily_breach_triggered", False),
        )


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class FleetDrawdownGuard:
    """Fleet-wide drawdown guard with HWM and daily loss protection.

    Parameters
    ----------
    hwm_drawdown_pct: Maximum allowed drawdown from the high-water mark
        as a percentage (e.g. 25.0 = 25%). Triggers HALT_NEW when exceeded.
    daily_loss_pct: Maximum allowed loss in a single calendar day as a
        percentage (e.g. 10.0 = 10%). Triggers HALT_NEW when exceeded.
    state_file: Path to the persistent state JSON file.
    kill_switch_path: Optional override for the kill switch state file path.
        If None, uses the default kill_switch.py resolution.
    """

    def __init__(
        self,
        hwm_drawdown_pct: Decimal = Decimal("25.0"),
        daily_loss_pct: Decimal = Decimal("10.0"),
        state_file: str | Path = DEFAULT_STATE_FILE,
        kill_switch_path: Path | None = None,
    ) -> None:
        self._hwm_drawdown_pct = hwm_drawdown_pct
        self._daily_loss_pct = daily_loss_pct
        self._state_file = Path(state_file)
        self._kill_switch_path = kill_switch_path
        self._state = DrawdownState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        equity: Decimal,
        timestamp: datetime | None = None,
    ) -> DrawdownEvaluation:
        """Evaluate current equity against HWM and daily drawdown thresholds.

        Parameters
        ----------
        equity: Current fleet equity value.
        timestamp: Current timestamp. Defaults to UTC now.

        Returns
        -------
        DrawdownEvaluation with trigger status and metrics.
        """
        if timestamp is None:
            timestamp = datetime.now(tz=UTC)

        if equity <= 0:
            return DrawdownEvaluation(
                triggered=True,
                reason=f"Non-positive equity: {equity}",
                current_equity=equity,
            )

        # Load persisted state
        self._load_state()

        # Detect day boundary
        today = timestamp.strftime("%Y-%m-%d")
        is_new_day = today != self._state.day_date

        if is_new_day:
            # New day: reset daily tracking, but NOT HWM
            self._state.day_start_equity = equity
            self._state.day_date = today
            self._state.daily_breach_triggered = False
            logger.info(
                "fleet_drawdown_guard: new day %s — day_start_equity=%s",
                today,
                equity,
            )

        # Initialize HWM on first tick
        if self._state.hwm_equity <= 0:
            self._state.hwm_equity = equity
            self._state.hwm_timestamp = timestamp.isoformat()
            self._state.day_start_equity = equity
            self._state.day_date = today
            self._state.last_equity = equity
            self._state.last_update = timestamp.isoformat()
            self._save_state()
            return DrawdownEvaluation(
                triggered=False,
                reason="Initialized",
                current_equity=equity,
                hwm_equity=equity,
                day_start_equity=equity,
            )

        # Update HWM if equity is higher
        if equity > self._state.hwm_equity:
            self._state.hwm_equity = equity
            self._state.hwm_timestamp = timestamp.isoformat()
            # A new HWM clears the HWM breach flag
            self._state.hwm_breach_triggered = False
            logger.info(
                "fleet_drawdown_guard: new HWM %s at %s",
                equity,
                timestamp.isoformat(),
            )

        # Calculate drawdown percentages
        hwm_drawdown_pct = self._calc_drawdown_pct(equity, self._state.hwm_equity)
        daily_drawdown_pct = self._calc_drawdown_pct(
            equity, self._state.day_start_equity
        )

        # Check HWM drawdown threshold
        hwm_breach = (
            not self._state.hwm_breach_triggered
            and hwm_drawdown_pct >= self._hwm_drawdown_pct
        )

        # Check daily loss threshold
        daily_breach = (
            not self._state.daily_breach_triggered
            and daily_drawdown_pct >= self._daily_loss_pct
        )

        triggered = hwm_breach or daily_breach
        reason_parts: list[str] = []

        if hwm_breach:
            self._state.hwm_breach_triggered = True
            reason_parts.append(
                f"HWM drawdown {hwm_drawdown_pct:.2f}% >= {self._hwm_drawdown_pct}% "
                f"(HWM={self._state.hwm_equity}, equity={equity})"
            )

        if daily_breach:
            self._state.daily_breach_triggered = True
            reason_parts.append(
                f"Daily drawdown {daily_drawdown_pct:.2f}% >= {self._daily_loss_pct}% "
                f"(day_start={self._state.day_start_equity}, equity={equity})"
            )

        if triggered:
            reason = "; ".join(reason_parts)
            logger.warning("fleet_drawdown_guard: TRIGGERED — %s", reason)
            self._set_halt_new(reason)

        # Update last values
        self._state.last_equity = equity
        self._state.last_update = timestamp.isoformat()
        self._save_state()

        return DrawdownEvaluation(
            triggered=triggered,
            reason="; ".join(reason_parts) if reason_parts else "",
            hwm_drawdown_pct=hwm_drawdown_pct,
            daily_drawdown_pct=daily_drawdown_pct,
            hwm_equity=self._state.hwm_equity,
            day_start_equity=self._state.day_start_equity,
            current_equity=equity,
        )

    def reset(self) -> None:
        """Reset all state. Useful for testing or manual recovery."""
        self._state = DrawdownState()
        self._save_state()
        logger.info("fleet_drawdown_guard: state reset")

    def load_state(self) -> DrawdownState:
        """Load and return the current persisted state."""
        self._load_state()
        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load state from the state file. Fail closed on corruption."""
        if not self._state_file.exists():
            self._state = DrawdownState()
            return

        try:
            raw = self._state_file.read_text(encoding="utf-8").strip()
            if not raw:
                self._state = DrawdownState()
                return
            data = json.loads(raw)
            self._state = DrawdownState.from_dict(data)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.error(
                "fleet_drawdown_guard: corrupt state file %s — %s. "
                "Failing closed with fresh state.",
                self._state_file,
                exc,
            )
            self._state = DrawdownState()

    def _save_state(self) -> None:
        """Atomically write state to the state file."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._state.to_dict(), indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._state_file)

    def _set_halt_new(self, reason: str) -> None:
        """Set the kill switch to HALT_NEW via the existing kill_switch module."""
        try:
            import importlib

            ks = importlib.import_module("freqtrade.shared.kill_switch")
            ks.set_kill_mode(
                mode=ks.MODE_HALT_NEW,
                reason=reason,
                triggered_by="drawdown_guard",
                path=self._kill_switch_path,
            )
        except ImportError:
            logger.error(
                "fleet_drawdown_guard: cannot import kill_switch — "
                "HALT_NEW not set. Reason: %s",
                reason,
            )
        except Exception as exc:
            logger.error(
                "fleet_drawdown_guard: failed to set HALT_NEW — %s. Reason: %s",
                exc,
                reason,
            )

    @staticmethod
    def _calc_drawdown_pct(current: Decimal, reference: Decimal) -> Decimal:
        """Calculate drawdown percentage from reference to current.

        Returns 0 if reference is zero or negative.
        """
        if reference <= 0:
            return Decimal("0")
        if current >= reference:
            return Decimal("0")
        return ((reference - current) / reference) * Decimal("100")
