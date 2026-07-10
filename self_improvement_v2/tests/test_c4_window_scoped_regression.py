"""Regression test for window-scoped C4 measurement input.

Verifies that the C4 measurement engine correctly reports window-scoped
trade counts alongside lifetime totals, preventing the data-scope mismatch
identified in the 2026-07-03 triage (Lifetime 82.79% vs Window 75.08%).

Safety invariants:
- No C4 execution
- No Canary restart
- No decision override
- Measurement code change only
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.live.live_canary_measurement_decision import (
    CanaryMetrics,
    run_live_canary_measurement_decision,
)


def _make_c3_ceremony_ready(repo_root: Path) -> None:
    """Write a synthetic C3 ceremony artifact with READY status."""
    ceremony_dir = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony"
    ceremony_dir.mkdir(parents=True, exist_ok=True)
    ceremony_file = ceremony_dir / "live_canary_activation_ceremony.json"
    ceremony_data = {
        "event": "live_canary_activation_ceremony_result",
        "status": "LIVE_CANARY_CEREMONY_READY",
        "canary_target": "freqtrade-freqforge-canary",
        "checks": [],
        "blocked_reasons": [],
        "snapshots": [],
        "measurement_window": {
            "duration_days": 14,
            "metrics": [
                "total_trades", "win_rate", "profit_factor",
                "sharpe_ratio", "max_drawdown", "daily_loss_count",
            ],
            "comparison_baseline": "Dry-run performance over the 14 days prior to activation",
            "evaluation_gate": "Post-activation T0/T1/T2/T3 measurement evaluations",
            "decision_outcomes": ["KEEP", "EXTEND", "ROLLBACK"],
        },
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    ceremony_file.write_text(json.dumps(ceremony_data, indent=2))


class TestWindowScopedC4:
    """Regression tests for window-scoped C4 measurement input."""

    def test_window_trade_count_in_decision_payload(
        self, tmp_path: Path,
    ) -> None:
        """Verify window_trade_count appears in the decision payload."""
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.6,
            max_drawdown_pct=75.08,
            daily_loss_count=2,
            avg_profit_per_trade=0.01,
            notional_exposure=1000.0,
            window_trade_count=7,
        )
        run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision",
            now_utc="2026-07-10T12:00:00+00:00",
            metrics=metrics,
            data_points_available=5,
        )
        # Read the decision payload
        decision_path = tmp_path / "decision" / "live_canary_measurement_decision.json"
        assert decision_path.exists()
        payload = json.loads(decision_path.read_text())
        assert payload["window_trade_count"] == 7
        assert payload["total_trades_observed"] == 10

    def test_window_trade_count_defaults_to_none(
        self, tmp_path: Path,
    ) -> None:
        """Verify backward compatibility: window_trade_count is None when not set."""
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.6,
            max_drawdown_pct=75.08,
            daily_loss_count=2,
            avg_profit_per_trade=0.01,
            notional_exposure=1000.0,
        )
        run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision",
            now_utc="2026-07-10T12:00:00+00:00",
            metrics=metrics,
            data_points_available=5,
        )
        decision_path = tmp_path / "decision" / "live_canary_measurement_decision.json"
        payload = json.loads(decision_path.read_text())
        assert payload["window_trade_count"] is None

    def test_window_trade_count_in_metrics_to_dict(
        self,
    ) -> None:
        """Verify CanaryMetrics.to_dict includes window_trade_count."""
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.6,
            max_drawdown_pct=75.08,
            daily_loss_count=2,
            avg_profit_per_trade=0.01,
            notional_exposure=1000.0,
            window_trade_count=7,
        )
        d = metrics.to_dict()
        assert d["window_trade_count"] == 7
        assert d["total_trades"] == 10

    def test_window_trade_count_omitted_when_none(
        self,
    ) -> None:
        """Verify window_trade_count is None in dict when not provided."""
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.6,
            max_drawdown_pct=75.08,
            daily_loss_count=2,
            avg_profit_per_trade=0.01,
            notional_exposure=1000.0,
        )
        d = metrics.to_dict()
        assert d["window_trade_count"] is None
