"""C4 measurement-window scope contract regression tests.

The contract is pure and read-only: raw trade observations are selected before
metrics reach the C4 decision engine.  No runtime, database, or exchange access
is used by these tests.
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import pytest

from si_v2.live.c4_window_scope import (
    C4MeasurementInput,
    C4Trade,
    build_window_scoped_measurement,
)
from si_v2.live.live_canary_measurement_decision import (
    KEEP,
    LIVE_CANARY_MEASUREMENT_BLOCKED,
    LIVE_CANARY_MEASUREMENT_READY,
    run_live_canary_measurement_decision,
)

START = "2026-06-18T12:00:00+00:00"
END = "2026-07-02T12:00:00+00:00"


def _trade(
    trade_id: str,
    opened_at: str,
    closed_at: str | None,
    profit_abs: float = 1.0,
    profit_ratio: float = 0.01,
    notional: float = 100.0,
) -> C4Trade:
    return C4Trade(
        trade_id=trade_id,
        opened_at_utc=opened_at,
        closed_at_utc=closed_at,
        profit_abs=profit_abs,
        profit_ratio=profit_ratio,
        notional=notional,
    )


def _ready_ceremony(repo_root: Path) -> None:
    path = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony" / "live_canary_activation_ceremony.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "status": "LIVE_CANARY_CEREMONY_READY",
                "canary_target": "freqtrade-freqforge-canary",
                "measurement_window": {
                    "duration_days": 14,
                    "metrics": ["win_rate", "max_drawdown"],
                },
            }
        ),
        encoding="utf-8",
    )


def _keep_input() -> C4MeasurementInput:
    pnls = (1.0, 1.0, 1.0, 1.0, -0.1)
    return C4MeasurementInput(
        measurement_start_utc=START,
        measurement_end_utc=END,
        continuation_start_equity=100.0,
        lifetime_start_equity=100.0,
        trades=tuple(
            _trade(
                f"trade-{index}",
                START,
                f"2026-06-{18 + index:02d}T12:00:00Z",
                pnl,
                pnl / 100.0,
            )
            for index, pnl in enumerate(pnls, start=1)
        ),
    )


def test_selects_realized_and_open_at_end_trades_at_inclusive_boundaries() -> None:
    measurement = build_window_scoped_measurement(
        C4MeasurementInput(
            measurement_start_utc=START,
            measurement_end_utc=END,
            continuation_start_equity=100.0,
            lifetime_start_equity=100.0,
            trades=(
                _trade("closed-before", "2026-06-10T00:00:00Z", "2026-06-17T23:59:59Z"),
                _trade("opened-before", "2026-06-10T00:00:00Z", START),
                _trade("inside", START, END),
                _trade("closes-after", "2026-06-20T00:00:00Z", "2026-07-03T00:00:00Z"),
                _trade("still-open", "2026-06-21T00:00:00Z", None),
                _trade("opened-after", "2026-07-03T00:00:00Z", None),
            ),
        )
    )

    assert measurement.included_trade_ids == (
        "opened-before",
        "inside",
        "closes-after",
        "still-open",
    )
    assert measurement.realized_trade_ids == ("opened-before", "inside")
    assert measurement.open_at_window_end_trade_ids == ("closes-after", "still-open")
    assert measurement.excluded_trade_ids == ("closed-before", "opened-after")
    assert measurement.metrics.total_trades == 2
    assert measurement.included_trade_count == 4


@pytest.mark.parametrize(
    ("start", "end", "match"),
    [
        ("", END, "measurement_start_utc"),
        (START, "", "measurement_end_utc"),
        (END, START, "before measurement_end_utc"),
        ("2026-06-18T12:00:00", END, "timezone-aware"),
    ],
)
def test_rejects_missing_ambiguous_or_reversed_boundaries(
    start: str,
    end: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_window_scoped_measurement(
            C4MeasurementInput(
                measurement_start_utc=start,
                measurement_end_utc=end,
                continuation_start_equity=100.0,
                lifetime_start_equity=100.0,
                trades=(),
            )
        )


def test_closed_outside_window_cannot_contaminate_authoritative_metrics() -> None:
    measurement = build_window_scoped_measurement(
        C4MeasurementInput(
            measurement_start_utc=START,
            measurement_end_utc=END,
            continuation_start_equity=100.0,
            lifetime_start_equity=100.0,
            trades=(
                _trade(
                    "lifetime-loss",
                    "2026-06-01T00:00:00Z",
                    "2026-06-10T00:00:00Z",
                    profit_abs=-90.0,
                    profit_ratio=-0.9,
                ),
                _trade("window-win", START, "2026-06-20T00:00:00Z", 2.0, 0.02),
                _trade("window-loss", START, "2026-06-21T00:00:00Z", -1.0, -0.01),
            ),
        )
    )

    assert measurement.metrics.total_trades == 2
    assert measurement.metrics.win_rate == 0.5
    assert measurement.metrics.profit_factor == 2.0
    assert measurement.metrics.avg_profit_per_trade == 0.5
    assert measurement.drawdown_calculations.authoritative_method == "continuation"
    assert measurement.metrics.max_drawdown_pct == 1.0 / 102.0 * 100.0
    assert measurement.drawdown_calculations.lifetime_pct > 80.0


def test_historic_c4_triage_values_remain_rollback_recommended() -> None:
    loss = 3.2338
    continuation_start = loss / 0.7508 - 1.0
    trough_equity = continuation_start + 1.0 - loss
    lifetime_start = trough_equity / (1.0 - 0.8279)

    base = tuple(index - 5.5 for index in range(12))
    sigma = math.sqrt(sum(value * value for value in base) / len(base))
    offset = -0.18 * sigma / math.sqrt(len(base))
    ratios = tuple(value + offset for value in base)

    positive_pnls = (0.1,) * 10
    final_positive = loss * 0.36 - sum(positive_pnls)
    pnls = (*positive_pnls, -loss, final_positive)
    trades = [
        _trade(
            "pre-window",
            "2026-06-01T00:00:00Z",
            "2026-06-17T12:00:00Z",
            continuation_start - lifetime_start,
            0.0,
        )
    ]
    for index, (pnl, ratio) in enumerate(zip(pnls, ratios, strict=True), start=1):
        trades.append(
            _trade(
                f"window-{index}",
                START,
                f"2026-06-{18 + index:02d}T12:00:00Z",
                pnl,
                ratio,
            )
        )

    measurement = build_window_scoped_measurement(
        C4MeasurementInput(
            measurement_start_utc=START,
            measurement_end_utc=END,
            continuation_start_equity=continuation_start,
            lifetime_start_equity=lifetime_start,
            trades=tuple(trades),
        )
    )

    assert round(measurement.drawdown_calculations.lifetime_pct, 2) == 82.79
    assert round(measurement.drawdown_calculations.window_relative_pct, 2) == 323.38
    assert round(measurement.drawdown_calculations.continuation_pct, 2) == 75.08
    assert round(measurement.metrics.sharpe_ratio or 0.0, 2) == -0.18
    assert round(measurement.metrics.win_rate or 0.0, 4) == 0.9167
    assert round(measurement.metrics.profit_factor or 0.0, 2) == 0.36
    assert measurement.metrics.max_drawdown_pct == (measurement.drawdown_calculations.continuation_pct)


def test_public_decision_entrypoint_does_not_accept_unscoped_metrics() -> None:
    parameters = inspect.signature(run_live_canary_measurement_decision).parameters

    assert "metrics" not in parameters
    assert "measurement_input" in parameters


def test_decision_persists_window_scope_and_authoritative_method(
    tmp_path: Path,
) -> None:
    _ready_ceremony(tmp_path)

    result = run_live_canary_measurement_decision(
        repo_root=tmp_path,
        decision_output_dir=tmp_path / "decision",
        now_utc=END,
        measurement_input=_keep_input(),
        data_points_available=5,
    )

    payload = json.loads(Path(result.decision_path).read_text(encoding="utf-8"))
    scope = payload["measurement_scope"]
    assert result.status == LIVE_CANARY_MEASUREMENT_READY
    assert result.decision == KEEP
    assert scope["measurement_start_utc"] == START
    assert scope["measurement_end_utc"] == END
    assert scope["included_trade_count"] == 5
    assert scope["realized_trade_count"] == 5
    assert scope["scope_method"] == "close_in_window_or_open_at_window_end/v1"
    assert scope["drawdown_calculations"]["authoritative_method"] == "continuation"
    assert scope["drawdown_calculations"]["lifetime"]["authoritative"] is False
    assert scope["drawdown_calculations"]["continuation"]["authoritative"] is True
    assert scope["metric_authority"] == {
        "notional_exposure": "open_at_window_end",
        "max_drawdown_pct": "continuation",
        "total_trades": "window_realized",
        "win_rate": "window_realized",
        "profit_factor": "window_realized",
        "sharpe_ratio": "window_realized",
        "daily_loss_count": "window_realized",
        "avg_profit_per_trade": "window_realized",
    }


def test_missing_measurement_input_blocks_instead_of_using_lifetime_data(
    tmp_path: Path,
) -> None:
    _ready_ceremony(tmp_path)

    result = run_live_canary_measurement_decision(
        repo_root=tmp_path,
        decision_output_dir=tmp_path / "decision",
        now_utc=END,
    )

    assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED
    assert any("measurement_window_scope" in reason for reason in result.blocked_reasons)
