"""FleetRiskManager — shared fleet-wide risk state, drawdown and correlation guard.

The manager persists a shared JSON state in the mounted /freqtrade/shared tree so
all bot containers can read the same exposure picture without hard shutdowns.

Design goals:
- central, shared fleet state
- dynamic exposure reduction instead of binary quarantine
- cluster-level win/loss awareness
- correlation-aware throttling when highly correlated pairs are already open
- dry-run friendly, side-effect free outside the shared JSON state file
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Backtest gate bypass ──────────────────────────────────────────────
# Set BACKTEST_GATES=false to disable all gate logic for backtesting.
BACKTEST_GATES = os.environ.get("BACKTEST_GATES", "true").lower() not in ("false", "0", "no")

# ── Canonical signal gate policy (single source of truth) ──────────────
# All consumers MUST import these instead of defining local copies.
CONFIDENCE_MIN: float = 0.65        # minimum AI confidence to accept signal
STALENESS_MINUTES: float = 30.0     # max signal age before stale/rejected
# ──────────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_pair(pair: Optional[str]) -> str:
    if not pair:
        return ""
    return str(pair).strip().upper()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    return str(value)


class FleetRiskManager:
    def __init__(
        self,
        state_file: Optional[str] = None,
        correlation_file: Optional[str] = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent
        self.state_file = str(
            Path(state_file) if state_file else base_dir / "fleet_risk_state.json"
        )
        self.correlation_file = str(
            Path(correlation_file) if correlation_file else base_dir / "fleet_correlation_matrix.json"
        )

        self.clusters = {
            "major": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
            "layer1_alts": ["AVAX/USDT:USDT", "NEAR/USDT:USDT", "APT/USDT:USDT"],
            "l2": ["ARB/USDT:USDT", "OP/USDT:USDT"],
            "other": [],
        }
        self.max_per_cluster = 2
        self.max_total_exposure = 6

        # Conservative drawdown ladder.
        self.dd_warning = 0.04
        self.dd_reduce = 0.08
        self.dd_pause = 0.12
        self.dd_emergency = 0.18

        self.portfolio_peak: Optional[float] = None
        self.current_equity: Optional[float] = None
        self.current_drawdown: float = 0.0
        try:
            self.state = self.refresh_from_disk()
        except Exception as e:
            logger.warning(
                "FleetRiskManager: refresh_from_disk failed (%s: %s). "
                "Falling back to default state.",
                type(e).__name__, e,
            )
            self.state = self._default_state()

    # ---------------------------------------------------------------------
    # State primitives
    # ---------------------------------------------------------------------

    def _default_state(self) -> Dict[str, Any]:
        return {
            "portfolio": {
                "peak_equity": None,
                "current_equity": None,
                "current_drawdown": 0.0,
                "updated_at": None,
                "sources": {},
            },
            "open_trades": [],
            "trade_history": [],
            "last_update": None,
        }

    def _load_state(self) -> Dict[str, Any]:
        path = Path(self.state_file)
        if not path.exists():
            return self._default_state()

        try:
            with path.open("r", encoding="utf-8") as handle:
                fcntl.flock(handle, fcntl.LOCK_SH)
                raw = handle.read()
        except Exception as exc:
            logger.debug("FleetRiskManager: state load fallback for %s (%s)", path, exc)
            return self._default_state()

        if not raw.strip():
            return self._default_state()

        try:
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("FleetRiskManager: invalid state JSON in %s (%s)", path, exc)
            return self._default_state()

        if not isinstance(data, dict):
            return self._default_state()

        # Backward-compatible normalization.
        portfolio = data.get("portfolio")
        if not isinstance(portfolio, dict):
            portfolio = {}
        portfolio.setdefault("peak_equity", None)
        portfolio.setdefault("current_equity", None)
        portfolio.setdefault("current_drawdown", 0.0)
        portfolio.setdefault("updated_at", None)
        sources = portfolio.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        portfolio["sources"] = sources
        data["portfolio"] = portfolio
        if not isinstance(data.get("open_trades"), list):
            data["open_trades"] = []
        if not isinstance(data.get("trade_history"), list):
            data["trade_history"] = []
        return data

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = Path(self.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        portfolio = state.setdefault("portfolio", {})
        sources = portfolio.setdefault("sources", {})
        source_equities = [
            _safe_float(entry.get("current_equity"), 0.0)
            for entry in sources.values()
            if isinstance(entry, dict) and entry.get("current_equity") is not None
        ]
        current = sum(source_equities) if source_equities else portfolio.get("current_equity")
        peak = portfolio.get("peak_equity")
        if current is not None:
            portfolio["current_equity"] = current
        if current is not None and (peak is None or _safe_float(current) > _safe_float(peak)):
            peak = current
            portfolio["peak_equity"] = peak
        if current is not None and peak is not None and _safe_float(peak) > 0:
            portfolio["current_drawdown"] = max(0.0, (_safe_float(peak) - _safe_float(current)) / _safe_float(peak))
            self.portfolio_peak = _safe_float(peak)
            self.current_equity = _safe_float(current)
            self.current_drawdown = _safe_float(portfolio["current_drawdown"], 0.0)
        state["last_update"] = _utc_now()
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.tmp-",
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
                os.fchmod(handle.fileno(), 0o664)
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                os.chmod(path, 0o664)
            except Exception:
                pass
        except Exception as exc:
            logger.error("FleetRiskManager: failed to save state %s (%s)", path, exc)
            try:
                if tmp_path is not None and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    @contextmanager
    def _state_write_lock(self):
        """Serialize writers across containers that share the same state file."""
        path = Path(self.state_file)
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_path.touch(exist_ok=True)
            os.chmod(lock_path, 0o664)
        except Exception:
            pass
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def refresh_from_disk(self) -> Dict[str, Any]:
        state = self._load_state()
        portfolio = state.setdefault("portfolio", {})
        sources = portfolio.setdefault("sources", {})

        peak = portfolio.get("peak_equity")
        current = portfolio.get("current_equity")
        try:
            if current is None:
                source_equities = [
                    _safe_float(entry.get("current_equity"), 0.0)
                    for entry in sources.values()
                    if isinstance(entry, dict) and entry.get("current_equity") is not None
                ]
                if source_equities:
                    current = sum(source_equities)
            if current is not None and peak is None:
                peak = current
            if peak is not None and current is not None and _safe_float(peak) > 0:
                peak_f = _safe_float(peak)
                current_f = _safe_float(current)
                drawdown = max(0.0, (peak_f - current_f) / peak_f)
                portfolio["peak_equity"] = peak_f
                portfolio["current_equity"] = current_f
                portfolio["current_drawdown"] = drawdown
                self.portfolio_peak = peak_f
                self.current_equity = current_f
                self.current_drawdown = drawdown
            else:
                self.portfolio_peak = _safe_float(peak) if peak is not None else None
                self.current_equity = _safe_float(current) if current is not None else None
                self.current_drawdown = _safe_float(portfolio.get("current_drawdown"), 0.0)
        except Exception as exc:
            logger.debug("FleetRiskManager: portfolio refresh fallback (%s)", exc)
            self.portfolio_peak = _safe_float(peak) if peak is not None else None
            self.current_equity = _safe_float(current) if current is not None else None
            self.current_drawdown = _safe_float(portfolio.get("current_drawdown"), 0.0)

        return state

    def _apply_global_equity(self, state: Dict[str, Any], current_equity: float) -> None:
        portfolio = state.setdefault("portfolio", {})
        peak = portfolio.get("peak_equity")
        current_f = _safe_float(current_equity)
        if peak is None or current_f > _safe_float(peak):
            peak = current_f
        peak_f = _safe_float(peak)
        drawdown = 0.0 if peak_f <= 0 else max(0.0, (peak_f - current_f) / peak_f)
        portfolio.update(
            {
                "peak_equity": peak_f,
                "current_equity": current_f,
                "current_drawdown": drawdown,
                "updated_at": _utc_now(),
            }
        )
        self.portfolio_peak = peak_f
        self.current_equity = current_f
        self.current_drawdown = drawdown

    def _apply_source_equity(self, state: Dict[str, Any], source: str, current_equity: float) -> None:
        portfolio = state.setdefault("portfolio", {})
        sources = portfolio.setdefault("sources", {})
        current_f = _safe_float(current_equity)
        entry = sources.get(source, {})
        if not isinstance(entry, dict):
            entry = {}
        peak = entry.get("peak_equity")
        if peak is None or current_f > _safe_float(peak):
            peak = current_f
        entry.update(
            {
                "current_equity": current_f,
                "peak_equity": _safe_float(peak),
                "updated_at": _utc_now(),
            }
        )
        sources[source] = entry
        portfolio["sources"] = sources

    def update_portfolio_equity(self, current_equity: float) -> None:
        with self._state_write_lock():
            state = self._load_state()
            self._apply_global_equity(state, current_equity)
            self._save_state(state)

    def update_source_equity(self, source: str, current_equity: float) -> None:
        with self._state_write_lock():
            state = self._load_state()
            self._apply_source_equity(state, str(source or "global"), current_equity)
            self._save_state(state)

    # ---------------------------------------------------------------------
    # Normalization helpers
    # ---------------------------------------------------------------------

    def _get_cluster(self, pair: str) -> str:
        pair_norm = _normalize_pair(pair)
        for name, pairs in self.clusters.items():
            if pair_norm in pairs:
                return name
        return "other"

    def _make_trade_key(
        self,
        source: str,
        trade_id: Optional[Any],
        pair: Optional[str],
        timestamp: Optional[Any] = None,
    ) -> str:
        source_norm = str(source or "global")
        if trade_id is not None:
            return f"{source_norm}:{trade_id}"
        pair_norm = _normalize_pair(pair)
        stamp = _as_iso(timestamp) or _utc_now()
        return f"{source_norm}:{pair_norm}:{stamp}"

    def _trade_direction_from_any(self, trade: Any) -> str:
        if isinstance(trade, dict):
            direction = trade.get("direction")
            if direction:
                return str(direction).lower()
            if trade.get("is_short") is not None:
                return "short" if bool(trade.get("is_short")) else "long"
            side = trade.get("side")
            if side:
                return str(side).lower()
        else:
            if getattr(trade, "is_short", None) is not None:
                return "short" if bool(getattr(trade, "is_short")) else "long"
            side = getattr(trade, "trade_direction", None)
            if side:
                return str(side).lower()
        return "long"

    def _trade_id_from_any(self, trade: Any) -> Optional[Any]:
        if isinstance(trade, dict):
            return trade.get("trade_id", trade.get("id"))
        return getattr(trade, "id", None)

    def _trade_pair_from_any(self, trade: Any) -> str:
        if isinstance(trade, dict):
            return _normalize_pair(trade.get("pair"))
        return _normalize_pair(getattr(trade, "pair", None))

    def _trade_stake_from_any(self, trade: Any) -> float:
        if isinstance(trade, dict):
            for key in ("stake_amount", "stake", "open_trade_value"):
                if trade.get(key) is not None:
                    return _safe_float(trade.get(key))
            return 0.0
        return _safe_float(getattr(trade, "stake_amount", None), 0.0)

    def _trade_profit_from_any(self, trade: Any) -> float:
        if isinstance(trade, dict):
            for key in ("profit_pct", "close_profit", "realized_profit", "profit_abs", "close_profit_abs"):
                if trade.get(key) is not None:
                    return _safe_float(trade.get(key))
            return 0.0
        for attr in ("close_profit", "realized_profit", "close_profit_abs"):
            value = getattr(trade, attr, None)
            if value is not None:
                return _safe_float(value)
        return 0.0

    def _trade_opened_at(self, trade: Any) -> Optional[str]:
        if isinstance(trade, dict):
            for key in ("opened_at", "open_date", "date"):
                if trade.get(key) is not None:
                    return _as_iso(trade.get(key))
            return None
        return _as_iso(getattr(trade, "open_date", None) or getattr(trade, "open_date_utc", None))

    def _trade_closed_at(self, trade: Any) -> Optional[str]:
        if isinstance(trade, dict):
            for key in ("closed_at", "close_date", "date"):
                if trade.get(key) is not None:
                    return _as_iso(trade.get(key))
            return None
        return _as_iso(getattr(trade, "close_date", None) or getattr(trade, "close_date_utc", None))

    def _normalize_open_trade(self, trade: Any, source: str) -> Dict[str, Any]:
        trade_id = self._trade_id_from_any(trade)
        pair = self._trade_pair_from_any(trade)
        direction = self._trade_direction_from_any(trade)
        opened_at = self._trade_opened_at(trade)
        trade_key = self._make_trade_key(source, trade_id, pair, opened_at)
        return {
            "trade_key": trade_key,
            "trade_id": trade_id,
            "source": str(source or "global"),
            "pair": pair,
            "cluster": self._get_cluster(pair),
            "direction": direction,
            "stake": self._trade_stake_from_any(trade),
            "opened_at": opened_at,
        }

    def _normalize_closed_trade(self, trade: Any, source: str) -> Dict[str, Any]:
        trade_id = self._trade_id_from_any(trade)
        pair = self._trade_pair_from_any(trade)
        direction = self._trade_direction_from_any(trade)
        closed_at = self._trade_closed_at(trade) or self._trade_opened_at(trade)
        profit_pct = self._trade_profit_from_any(trade)
        trade_key = self._make_trade_key(source, trade_id, pair, closed_at)
        profit_abs = None
        if isinstance(trade, dict):
            for key in ("profit_abs", "close_profit_abs", "realized_profit"):
                if trade.get(key) is not None:
                    profit_abs = _safe_float(trade.get(key))
                    break
        else:
            for attr in ("close_profit_abs", "realized_profit"):
                value = getattr(trade, attr, None)
                if value is not None:
                    profit_abs = _safe_float(value)
                    break
        return {
            "trade_key": trade_key,
            "trade_id": trade_id,
            "source": str(source or "global"),
            "pair": pair,
            "cluster": self._get_cluster(pair),
            "direction": direction,
            "profit_pct": profit_pct,
            "profit_abs": profit_abs,
            "is_win": profit_pct > 0,
            "closed_at": closed_at,
        }

    # ---------------------------------------------------------------------
    # Trade state sync
    # ---------------------------------------------------------------------

    def register_open_trade(
        self,
        pair: str,
        direction: str,
        stake: float = 0.0,
        source: str = "global",
        trade_id: Optional[Any] = None,
        opened_at: Optional[Any] = None,
    ) -> str:
        with self._state_write_lock():
            state = self._load_state()
            open_records = {
                entry.get("trade_key"): entry
                for entry in state.get("open_trades", [])
                if isinstance(entry, dict) and entry.get("trade_key")
            }
            pair_norm = _normalize_pair(pair)
            trade_key = self._make_trade_key(source, trade_id, pair_norm, opened_at)
            open_records[trade_key] = {
                "trade_key": trade_key,
                "trade_id": trade_id,
                "source": str(source or "global"),
                "pair": pair_norm,
                "cluster": self._get_cluster(pair_norm),
                "direction": str(direction or "long").lower(),
                "stake": _safe_float(stake),
                "opened_at": _as_iso(opened_at) or _utc_now(),
            }
            state["open_trades"] = list(open_records.values())
            self._save_state(state)
        return trade_key

    def unregister_closed_trade(
        self,
        pair: Optional[str] = None,
        source: str = "global",
        trade_id: Optional[Any] = None,
        trade_key: Optional[str] = None,
    ) -> None:
        with self._state_write_lock():
            state = self._load_state()
            pair_norm = _normalize_pair(pair)
            source_norm = str(source or "global")
            if trade_key is None and trade_id is not None:
                trade_key = self._make_trade_key(source_norm, trade_id, pair_norm or pair, None)
            filtered = []
            for entry in state.get("open_trades", []):
                if not isinstance(entry, dict):
                    continue
                if trade_key is not None and entry.get("trade_key") == trade_key:
                    continue
                if trade_key is None and entry.get("source") == source_norm:
                    if trade_id is not None and entry.get("trade_id") == trade_id:
                        continue
                    if pair_norm and entry.get("pair") == pair_norm:
                        continue
                filtered.append(entry)
            state["open_trades"] = filtered
            self._save_state(state)

    def log_trade_result(
        self,
        pair: str,
        profit_pct: float,
        direction: str,
        source: str = "global",
        trade_id: Optional[Any] = None,
        profit_abs: Optional[float] = None,
        closed_at: Optional[Any] = None,
    ) -> str:
        with self._state_write_lock():
            state = self._load_state()
            history = {
                entry.get("trade_key"): entry
                for entry in state.get("trade_history", [])
                if isinstance(entry, dict) and entry.get("trade_key")
            }
            pair_norm = _normalize_pair(pair)
            trade_key = self._make_trade_key(source, trade_id, pair_norm, closed_at)
            profit_f = _safe_float(profit_pct)
            history[trade_key] = {
                "trade_key": trade_key,
                "trade_id": trade_id,
                "source": str(source or "global"),
                "pair": pair_norm,
                "cluster": self._get_cluster(pair_norm),
                "direction": str(direction or "long").lower(),
                "profit_pct": profit_f,
                "profit_abs": _safe_float(profit_abs) if profit_abs is not None else None,
                "is_win": profit_f > 0,
                "closed_at": _as_iso(closed_at) or _utc_now(),
            }
            ordered = sorted(
                history.values(),
                key=lambda item: item.get("closed_at") or item.get("opened_at") or "",
            )
            state["trade_history"] = ordered[-300:]
            self._save_state(state)
        return trade_key

    def sync_trade_state(
        self,
        source: str,
        open_trades: Iterable[Any],
        closed_trades: Iterable[Any],
        current_equity: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._state_write_lock():
            source_norm = str(source or "global")
            open_records = [self._normalize_open_trade(trade, source_norm) for trade in open_trades]
            closed_records = [self._normalize_closed_trade(trade, source_norm) for trade in closed_trades]

            state = self._load_state()
            open_map = {
                entry.get("trade_key"): entry
                for entry in state.get("open_trades", [])
                if isinstance(entry, dict) and entry.get("trade_key") and entry.get("source") != source_norm
            }
            for record in open_records:
                open_map[record["trade_key"]] = record
            state["open_trades"] = list(open_map.values())

            history_map = {
                entry.get("trade_key"): entry
                for entry in state.get("trade_history", [])
                if isinstance(entry, dict) and entry.get("trade_key")
            }
            for record in closed_records:
                history_map[record["trade_key"]] = record
            ordered_history = sorted(
                history_map.values(),
                key=lambda item: item.get("closed_at") or item.get("opened_at") or "",
            )
            state["trade_history"] = ordered_history[-300:]

            if current_equity is not None:
                self._apply_global_equity(state, current_equity)

            self._save_state(state)
        return state

    # ---------------------------------------------------------------------
    # Risk logic
    # ---------------------------------------------------------------------

    def get_drawdown_level(self) -> str:
        dd = _safe_float(self.current_drawdown, 0.0)
        if dd >= self.dd_emergency:
            return "emergency"
        if dd >= self.dd_pause:
            return "pause"
        if dd >= self.dd_reduce:
            return "reduce"
        if dd >= self.dd_warning:
            return "warning"
        return "normal"

    def get_exposure_multiplier(self) -> float:
        level = self.get_drawdown_level()
        return {
            "emergency": 0.0,
            "pause": 0.2,
            "reduce": 0.5,
            "warning": 0.75,
            "normal": 1.0,
        }[level]

    def get_cluster_stats(self, cluster: str, lookback: int = 25) -> Dict[str, float]:
        state = self.refresh_from_disk()
        hist = [
            entry
            for entry in state.get("trade_history", [])
            if isinstance(entry, dict) and entry.get("cluster") == cluster
        ][-lookback:]
        if not hist:
            return {"winrate": 0.5, "pnl": 0.0, "count": 0.0}
        wins = sum(1 for entry in hist if bool(entry.get("is_win")))
        pnl = sum(_safe_float(entry.get("profit_pct"), 0.0) for entry in hist)
        return {
            "winrate": wins / len(hist),
            "pnl": pnl,
            "count": float(len(hist)),
        }

    def get_recent_winrate(self, cluster: str, lookback: int = 25) -> float:
        return float(self.get_cluster_stats(cluster, lookback=lookback)["winrate"])

    def get_recent_cluster_pnl(self, cluster: str, lookback: int = 25) -> float:
        return float(self.get_cluster_stats(cluster, lookback=lookback)["pnl"])

    def get_cluster_penalty(self, cluster: str) -> float:
        level = self.get_drawdown_level()
        if level in {"reduce", "pause", "emergency"}:
            return 0.5 if level == "reduce" else 0.0

        stats = self.get_cluster_stats(cluster)
        winrate = _safe_float(stats.get("winrate"), 0.5)
        pnl = _safe_float(stats.get("pnl"), 0.0)

        if stats.get("count", 0.0) == 0.0:
            return 1.0
        if winrate < 0.30 or pnl < -0.03:
            return 0.25
        if winrate < 0.42 or pnl < 0.0:
            return 0.5
        return 1.0

    def should_reduce_exposure(self, cluster: str) -> bool:
        return self.get_cluster_penalty(cluster) < 1.0

    def _load_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        path = Path(self.correlation_file)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("FleetRiskManager: correlation load fallback for %s (%s)", path, exc)
            return {}

        matrix = data.get("matrix") if isinstance(data, dict) else None
        if matrix is None and isinstance(data, dict):
            matrix = data.get("correlation_matrix") or data
        if not isinstance(matrix, dict):
            return {}
        normalized: Dict[str, Dict[str, float]] = {}
        for left, right_map in matrix.items():
            if not isinstance(right_map, dict):
                continue
            normalized[_normalize_pair(left)] = {
                _normalize_pair(right): _safe_float(value)
                for right, value in right_map.items()
            }
        return normalized

    def _lookup_correlation(
        self,
        matrix: Dict[str, Dict[str, float]],
        left: str,
        right: str,
    ) -> Optional[float]:
        left_norm = _normalize_pair(left)
        right_norm = _normalize_pair(right)
        if not left_norm or not right_norm:
            return None
        for a, b in ((left_norm, right_norm), (right_norm, left_norm)):
            if a in matrix and b in matrix[a]:
                return _safe_float(matrix[a][b])
        # Also allow alias without settle suffix when matrix uses base/quote only.
        left_alias = left_norm.split(":", 1)[0]
        right_alias = right_norm.split(":", 1)[0]
        for a, b in ((left_alias, right_alias), (right_alias, left_alias)):
            if a in matrix and b in matrix[a]:
                return _safe_float(matrix[a][b])
        return None

    def get_correlation_multiplier(
        self,
        pair: str,
        direction: str,
        open_trades: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> float:
        matrix = self._load_correlation_matrix()
        if not matrix:
            return 1.0

        if open_trades is None:
            state = self.refresh_from_disk()
            open_trades = state.get("open_trades", [])

        pair_norm = _normalize_pair(pair)
        direction_norm = str(direction or "long").lower()
        penalty = 1.0
        for entry in open_trades or []:
            if not isinstance(entry, dict):
                continue
            other_pair = _normalize_pair(entry.get("pair"))
            if not other_pair or other_pair == pair_norm:
                continue
            corr = self._lookup_correlation(matrix, pair_norm, other_pair)
            if corr is None:
                continue
            corr_abs = abs(_safe_float(corr))
            same_direction = str(entry.get("direction", "")).lower() == direction_norm
            if corr_abs >= 0.95:
                candidate = 0.25 if same_direction else 0.5
            elif corr_abs >= 0.85:
                candidate = 0.5 if same_direction else 0.75
            elif corr_abs >= 0.75:
                candidate = 0.75 if same_direction else 0.85
            else:
                candidate = 1.0
            penalty = min(penalty, candidate)
        return penalty

    MAX_DIRECTIONAL_BIAS = 0.70  # Max 70% Long oder Short im gesamten Fleet

    def _check_direction_bias(self, pending_direction: str) -> Tuple[bool, str]:
        """Blockiert wenn >70% aller offenen Trades in eine Direction."""
        state = getattr(self, "state", None) or self._default_state()
        open_trades = [t for t in state.get("open_trades", []) if isinstance(t, dict)]
        if len(open_trades) < 2:
            return True, "OK — zu wenige Trades für Bias-Check"

        total = len(open_trades)
        shorts = sum(1 for t in open_trades
                     if str(t.get("direction", "")).lower() in ("short", "sell"))
        longs = total - shorts
        pending = pending_direction.lower()

        if pending in ("short", "sell"):
            projected_shorts = shorts + 1
            projected_ratio = projected_shorts / (total + 1)
            if projected_ratio > self.MAX_DIRECTIONAL_BIAS:
                return (False,
                        f"SHORT-Bias blockiert: {projected_ratio:.0%} würde "
                        f">{self.MAX_DIRECTIONAL_BIAS:.0%} erreichen "
                        f"(aktuell: {shorts}/{total} Short)")
        elif pending in ("long", "buy"):
            projected_longs = longs + 1
            projected_ratio = projected_longs / (total + 1)
            if projected_ratio > self.MAX_DIRECTIONAL_BIAS:
                return (False,
                        f"LONG-Bias blockiert: {projected_ratio:.0%} würde "
                        f">{self.MAX_DIRECTIONAL_BIAS:.0%} erreichen "
                        f"(aktuell: {longs}/{total} Long)")

        return True, f"OK — Direction-Balance: {longs}L / {shorts}S"

    def check_entry_allowed(self, pair: str, direction: str) -> Tuple[bool, str]:
        if not BACKTEST_GATES:
            return True, "OK (gates bypassed)"
        state = self.refresh_from_disk()
        pair_norm = _normalize_pair(pair)
        direction_norm = str(direction or "long").lower()
        if not pair_norm:
            return True, "OK"

        cluster = self._get_cluster(pair_norm)
        drawdown_level = self.get_drawdown_level()
        if drawdown_level == "emergency":
            return False, f"EMERGENCY DRAWDOWN ({self.current_drawdown:.1%})"
        if drawdown_level == "pause":
            return False, f"Drawdown-Pause ({self.current_drawdown:.1%}) – keine neuen Entries"

        # ── Direction-Bias Gate (FIX P2-B 2026-06-05) ────
        bias_ok, bias_reason = self._check_direction_bias(direction_norm)
        if not bias_ok:
            logger.warning("Direction-Bias Gate: %s", bias_reason)
            return False, bias_reason
        # ─────────────────────────────────────────────────

        same_direction_cluster = [
            t for t in state.get("open_trades", [])
            if isinstance(t, dict)
            and t.get("cluster") == cluster
            and str(t.get("direction", "")).lower() == direction_norm
        ]
        open_total = [t for t in state.get("open_trades", []) if isinstance(t, dict)]

        drawdown_mult = self.get_exposure_multiplier()
        cluster_mult = self.get_cluster_penalty(cluster)
        corr_mult = self.get_correlation_multiplier(pair_norm, direction_norm, open_total)
        effective_mult = min(1.0, drawdown_mult * cluster_mult * corr_mult)

        eff_cluster_limit = max(1, int(self.max_per_cluster * effective_mult))
        eff_global_limit = max(1, int(self.max_total_exposure * effective_mult))

        if len(same_direction_cluster) >= eff_cluster_limit:
            stats = self.get_cluster_stats(cluster)
            return (
                False,
                (
                    f"Cluster-Limit {cluster} {direction_norm} "
                    f"({len(same_direction_cluster)}/{eff_cluster_limit}) | "
                    f"winrate={stats.get('winrate', 0.0):.2f} pnl={stats.get('pnl', 0.0):.4f} "
                    f"mult={effective_mult:.2f} corr={corr_mult:.2f}"
                ),
            )

        if len(open_total) >= eff_global_limit:
            return (
                False,
                (
                    f"Globales Exposure-Limit erreicht ({len(open_total)}/{eff_global_limit}) | "
                    f"dd={self.current_drawdown:.1%} mult={effective_mult:.2f}"
                ),
            )

        if corr_mult < 1.0:
            stats = self.get_cluster_stats(cluster)
            return (
                True,
                (
                    f"OK | correlation_throttle mult={effective_mult:.2f} corr={corr_mult:.2f} "
                    f"cluster_winrate={stats.get('winrate', 0.0):.2f}"
                ),
            )

        return True, "OK"

    # ---------------------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------------------

    def summarize_state(self) -> Dict[str, Any]:
        state = self.refresh_from_disk()
        portfolio = state.get("portfolio", {})
        return {
            "current_equity": portfolio.get("current_equity"),
            "peak_equity": portfolio.get("peak_equity"),
            "current_drawdown": portfolio.get("current_drawdown"),
            "drawdown_level": self.get_drawdown_level(),
            "open_trades": len(state.get("open_trades", [])),
            "trade_history": len(state.get("trade_history", [])),
        }
