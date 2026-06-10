"""Real Freqtrade adapter prototype — gated behind SI_V2_ENABLE_REAL_ADAPTERS.

Extends RealFreqtradeAdapterBase and implements the FreqtradeAdapter
protocol with actual Docker-exec-based Freqtrade CLI calls.
Instantiation requires SI_V2_ENABLE_REAL_ADAPTERS=1 in the environment.
"""

from __future__ import annotations

import subprocess
import time

from si_v2.adapters.audit import AdapterAuditSink
from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig
from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter
from si_v2.adapters.real_base import RealFreqtradeAdapterBase
from si_v2.state.schemas import MutationOverlay

# Timeouts
_CONFIG_TIMEOUT: int = 30
_TRADE_HISTORY_TIMEOUT: int = 30
_BACKTEST_TIMEOUT: int = 300

# Bot-to-container mapping (from Phase M.2 probe evidence)
_BOT_CONTAINERS: dict[str, str] = {
    "freqforge": "trading-freqtrade-freqforge-1",
    "regime-hybrid": "trading-freqtrade-regime-hybrid-1",
    "freqforge-canary": "trading-freqtrade-freqforge-canary-1",
    "freqai-rebel": "trading-freqai-rebel-1",
}


def _resolve_container(bot_id: str) -> str:
    """Resolve a bot_id to its Docker container name.

    Args:
        bot_id: Bot identifier.

    Returns:
        Docker container name.

    Raises:
        ValueError: If the bot_id is unknown.
    """
    container = _BOT_CONTAINERS.get(bot_id)
    if container is None:
        raise ValueError(f"Unknown bot_id: {bot_id!r}. Known: {list(_BOT_CONTAINERS)}")
    return container


class RealFreqtradeAdapter(RealFreqtradeAdapterBase, FreqtradeAdapter):
    """Concrete read-only Freqtrade adapter using Docker CLI.

    Requires ``SI_V2_ENABLE_REAL_ADAPTERS=1`` to instantiate.
    All methods are read-only: config read, trade history, backtest.

    Args:
        audit_sink: Where audit events are recorded.
        call_budget: Optional sliding-window rate limiter.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
    ) -> None:
        # Default budget: 10 calls/min (matching #20 contract)
        if call_budget is None:
            call_budget = CallBudgetChecker(
                CallBudgetConfig(
                    max_calls=10,
                    window_seconds=60.0,
                    component_name="RealFreqtradeAdapter",
                )
            )
        super().__init__(audit_sink, call_budget)

    # ── Private helpers ────────────────────────────────────────────────────

    def _exec_freqtrade(
        self,
        container: str,
        freqtrade_args: list[str],
        timeout: int,
    ) -> str:
        """Run ``freqtrade <args>`` inside *container* and return stdout.

        Args:
            container: Docker container name.
            freqtrade_args: Arguments to pass to the ``freqtrade`` binary.
            timeout: Max seconds to wait.

        Returns:
            Command stdout as a string.

        Raises:
            RuntimeError: If the command fails or the bot is unreachable.
            TimeoutError: If the command exceeds *timeout*.
        """
        cmd = ["docker", "exec", container, "freqtrade", *freqtrade_args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                raise RuntimeError(
                    f"freqtrade command failed in {container}: {err}"
                )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"freqtrade command timed out after {timeout}s in {container}"
            ) from None

    # ── Protocol implementation ────────────────────────────────────────────

    def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
        """Read the current Freqtrade configuration for a bot.

        Args:
            bot_id: Bot identifier (e.g. ``'freqforge'``, ``'regime-hybrid'``).

        Returns:
            Configuration dictionary with secret keys removed.

        Raises:
            RuntimeError: If config cannot be read.
            ValueError: If bot_id is unknown.
        """
        start = time.monotonic()
        method = "read_config"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            raise RuntimeError(f"Call budget exhausted for {method}")

        container = _resolve_container(bot_id)
        try:
            raw = self._exec_freqtrade(
                container, ["show-config", "--no-default"], _CONFIG_TIMEOUT
            )
        except (RuntimeError, TimeoutError) as exc:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method, False, str(exc), duration_ms=duration, error=type(exc).__name__
            )
            raise

        duration = (time.monotonic() - start) * 1000.0
        self._record_audit(method, True, "ok", duration_ms=duration)

        # Parse JSON output and remove secret keys
        import json

        try:
            config: dict[str, str | int | float | bool] = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._record_audit(
                method, False, f"json parse error: {exc}", duration_ms=duration
            )
            raise RuntimeError(f"Failed to parse config for {bot_id}: {exc}") from exc

        # Remove secret-containing keys
        for secret_key in ("api_key", "secret", "password", "token", "TELEGRAM_TOKEN"):
            config.pop(secret_key, None)
            config.pop(secret_key.lower(), None)
            config.pop(secret_key.upper(), None)

        return config

    def get_trade_history(
        self, bot_id: str, limit: int = 100
    ) -> list[dict[str, str | int | float]]:
        """Get recent trade history for a bot.

        Args:
            bot_id: Bot identifier.
            limit: Maximum number of trades to return.

        Returns:
            List of trade record dictionaries.

        Raises:
            RuntimeError: If trade history cannot be read.
            ValueError: If bot_id is unknown.
        """
        start = time.monotonic()
        method = "get_trade_history"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            raise RuntimeError(f"Call budget exhausted for {method}")

        container = _resolve_container(bot_id)
        try:
            raw = self._exec_freqtrade(
                container,
                ["trade-history", "--limit", str(limit), "--json"],
                _TRADE_HISTORY_TIMEOUT,
            )
        except (RuntimeError, TimeoutError) as exc:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method, False, str(exc), duration_ms=duration, error=type(exc).__name__
            )
            raise

        duration = (time.monotonic() - start) * 1000.0
        self._record_audit(method, True, f"{limit} trades", duration_ms=duration)

        import json

        try:
            trades: list[dict[str, str | int | float]] = json.loads(raw)
            return trades
        except json.JSONDecodeError as exc:
            self._record_audit(
                method, False, f"json parse error: {exc}", duration_ms=duration
            )
            raise RuntimeError(
                f"Failed to parse trade history for {bot_id}: {exc}"
            ) from exc

    def run_backtest(
        self, bot_id: str, overlay: MutationOverlay
    ) -> dict[str, str | int | float]:
        """Run a backtest inside the bot container with overlay params.

        Args:
            bot_id: Bot identifier.
            overlay: Mutation overlay parameters to backtest.

        Returns:
            Backtest result dictionary.

        Raises:
            RuntimeError: If backtest fails.
            ValueError: If bot_id is unknown.
        """
        start = time.monotonic()
        method = "run_backtest"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            raise RuntimeError(f"Call budget exhausted for {method}")

        container = _resolve_container(bot_id)

        # Build backtest command with overlay parameters
        # Freqtrade backtest uses: freqtrade backtesting --export trades
        timerange = getattr(overlay, "timerange", None)
        bt_args = [
            "backtesting",
            "--export",
            "trades",
        ]
        if timerange:
            bt_args.extend(["--timerange", str(timerange)])

        try:
            raw = self._exec_freqtrade(container, bt_args, _BACKTEST_TIMEOUT)
        except (RuntimeError, TimeoutError) as exc:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method, False, str(exc), duration_ms=duration, error=type(exc).__name__
            )
            raise

        duration = (time.monotonic() - start) * 1000.0
        self._record_audit(method, True, "ok", duration_ms=duration)

        import json

        # Freqtrade backtest output is a JSON report
        try:
            result: dict[str, str | int | float] = json.loads(raw)
            return result
        except json.JSONDecodeError:
            # Freqtrade may output non-JSON for the summary
            return {"raw_output": raw.strip(), "bot_id": bot_id}
