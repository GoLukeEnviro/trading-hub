"""Tests for SI v2 Post-Apply Impact Measurement (#278).

Covers verdict computation, window selection, aggregation, and output
format for all four bots with synthetic fixture data.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from si_v2.impact.post_apply_impact import (
    IMPACT_DEGRADED,
    IMPACT_IMPROVED,
    IMPACT_INSUFFICIENT_DATA,
    IMPACT_UNCHANGED,
    WindowMetrics,
    _aggregate_window,
    _compute_impact_verdict,
    _load_bot_metrics_from_cycle,
    evaluate_apply_plan_impact,
    render_impact_markdown,
)

# ---------------------------------------------------------------------------
# Helpers: build synthetic evidence files
# ---------------------------------------------------------------------------


def _make_evidence(
    directory: Path,
    cycle_id: str,
    bot_metrics: dict[str, dict[str, object]],
) -> Path:
    """Create a synthetic evidence file for testing."""
    decisions = []
    for bot_id, metrics in bot_metrics.items():
        wf = {
            "total_net_pnl": metrics.get("net_pnl", 0.0),
            "profit_factor": metrics.get("pf", 1.0),
            "total_trades": metrics.get("trades", 0),
            "max_drawdown_pct": metrics.get("dd", 0.0),
            "metrics_source": metrics.get("source", "walk_forward_net_metrics"),
            "evaluation_status": metrics.get("eval", "PASS_REVIEW"),
        }
        decisions.append({
            "bot_id": bot_id,
            "walk_forward_net_metrics": wf,
        })

    data = {
        "cycle_id": cycle_id,
        "generated_at_utc": f"2026-06-{cycle_id}",
        "per_bot_decisions": decisions,
    }

    path = directory / f"active_cycle_{cycle_id}.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _make_apply_plan(
    directory: Path,
    plan_id: str,
    bot_id: str = "freqtrade-freqforge",
    hypothesis: str = "reinforce_profitable_pair_cluster_v1",
    mutation_performed: bool = False,
) -> Path:
    """Create a synthetic apply plan file for testing."""
    plan = {
        "apply_plan_id": plan_id,
        "bot_id": bot_id,
        "candidate_sha256": "test1234",
        "hypothesis": hypothesis,
        "source_evidence_cycle": "pre-cycle",
        "plan_generated_at_utc": "2026-06-22T06:00:00Z",
        "approved_by": "test",
        "approved_at_utc": "2026-06-22T05:59:00Z",
        "parameter_overlay": {},
        "safety_verdict": "APPLY_PLAN_CREATED",
        "safety_reasons": ["dry_run_apply_only"],
        "mutation_performed": mutation_performed,
        "mutation_type": "none" if not mutation_performed else "config_write",
    }
    path = directory / f"apply_plan_{plan_id}.json"
    with open(path, "w") as f:
        json.dump(plan, f)
    return path


# ---------------------------------------------------------------------------
# Fixture setup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fixtures:
    tmp: Path
    evidence: Path
    apply_plans: Path


def _build_fixtures() -> Fixtures:
    """Build a temp directory with evidence + apply plan fixtures."""
    tmp = Path(tempfile.mkdtemp(prefix="si_v2_test_impact_"))
    ev = tmp / "evidence"
    ap = tmp / "apply_plans"
    ev.mkdir()
    ap.mkdir()

    # Pre-apply evidence (2 files, bot with positive metrics)
    _make_evidence(ev, "20260622T040000Z", {
        "freqtrade-freqforge": {"net_pnl": 10.0, "pf": 2.0, "trades": 15, "dd": 5.0},
        "freqtrade-regime-hybrid": {"net_pnl": -3.0, "pf": 0.8, "trades": 8, "dd": 10.0},
    })
    _make_evidence(ev, "20260622T050000Z", {
        "freqtrade-freqforge": {"net_pnl": 12.0, "pf": 2.2, "trades": 18, "dd": 4.0},
        "freqtrade-regime-hybrid": {"net_pnl": -2.0, "pf": 0.9, "trades": 6, "dd": 8.0},
    })
    # One file with not_applicable source (no real metrics)
    _make_evidence(ev, "20260622T055000Z", {
        "freqtrade-freqforge": {"net_pnl": 0.0, "pf": 0.0, "trades": 0, "dd": 0.0,
                                 "source": "not_applicable", "eval": "NOT_APPLICABLE"},
    })

    # Apply plan at 06:00
    _make_apply_plan(ap, "test001", bot_id="freqtrade-freqforge")

    # Post-apply evidence (2 files, improved metrics)
    _make_evidence(ev, "20260622T070000Z", {
        "freqtrade-freqforge": {"net_pnl": 15.0, "pf": 2.5, "trades": 20, "dd": 3.0},
    })
    _make_evidence(ev, "20260622T080000Z", {
        "freqtrade-freqforge": {"net_pnl": 18.0, "pf": 2.8, "trades": 22, "dd": 2.0},
    })

    return Fixtures(tmp=tmp, evidence=ev, apply_plans=ap)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadMetrics:
    def test_loads_metrics_for_matching_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "evidence"
            ev.mkdir()
            _make_evidence(ev, "20260622T040000Z", {
                "freqtrade-freqforge": {"net_pnl": 10.0, "pf": 2.0, "trades": 15, "dd": 5.0},
            })
            f = next(ev.glob("*.json"))
            metrics = _load_bot_metrics_from_cycle(f, "freqtrade-freqforge")
            assert metrics is not None
            assert metrics.total_net_pnl == 10.0
            assert metrics.profit_factor == 2.0
            assert metrics.total_trades == 15
            assert metrics.max_drawdown_pct == 5.0

    def test_returns_none_for_missing_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "evidence"
            ev.mkdir()
            _make_evidence(ev, "20260622T040000Z", {
                "freqtrade-freqforge": {"net_pnl": 10.0, "pf": 2.0, "trades": 15, "dd": 5.0},
            })
            f = next(ev.glob("*.json"))
            metrics = _load_bot_metrics_from_cycle(f, "nonexistent-bot")
            assert metrics is None


class TestAggregateWindow:
    def test_aggregates_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "evidence"
            ev.mkdir()
            _make_evidence(ev, "20260622T040000Z", {
                "freqtrade-freqforge": {"net_pnl": 10.0, "pf": 2.0, "trades": 15, "dd": 5.0},
            })
            _make_evidence(ev, "20260622T050000Z", {
                "freqtrade-freqforge": {"net_pnl": 12.0, "pf": 2.2, "trades": 18, "dd": 4.0},
            })
            files = sorted(ev.glob("*.json"))
            win = _aggregate_window(files, "freqtrade-freqforge")
            assert win.cycle_count == 2
            assert win.real_metric_cycles == 2
            assert win.total_net_pnl == 22.0  # 10 + 12
            assert win.total_trades == 33  # 15 + 18


class TestVerdictComputation:
    def test_improved(self) -> None:
        ap = {"apply_plan_id": "t1", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=15.0, profit_factor=2.5, total_trades=20,
                             max_drawdown_pct=3.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_IMPROVED

    def test_degraded(self) -> None:
        ap = {"apply_plan_id": "t2", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=-3.0, profit_factor=0.5, total_trades=8,
                             max_drawdown_pct=12.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_DEGRADED

    def test_unchanged(self) -> None:
        ap = {"apply_plan_id": "t3", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=10.2, profit_factor=2.02, total_trades=16,
                             max_drawdown_pct=5.1, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_UNCHANGED

    def test_insufficient_data(self) -> None:
        ap = {"apply_plan_id": "t4", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=0.0, profit_factor=0.0, total_trades=0,
                             max_drawdown_pct=0.0, real_metric_cycles=0, cycle_count=0)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_INSUFFICIENT_DATA

    def test_drawdown_worsens_despite_pnl_improvement(self) -> None:
        """PNL improved but drawdown got much worse -> degraded."""
        ap = {"apply_plan_id": "t5", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=20.0, profit_factor=2.5, total_trades=20,
                             max_drawdown_pct=25.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_DEGRADED
        assert any("drawdown" in r for r in v.reason_codes)

    def test_mutation_performed_hard_block(self) -> None:
        """mutation_performed=True hard blocks impact measurement."""
        ap = {"apply_plan_id": "t6", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": True}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=15.0, profit_factor=2.5, total_trades=20,
                             max_drawdown_pct=3.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_INSUFFICIENT_DATA
        assert "unsafe_apply_plan_mutation_performed" in v.reason_codes
        assert v.verdict != IMPACT_IMPROVED

    def test_metrics_within_tolerance(self) -> None:
        ap = {"apply_plan_id": "t7", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        # Very small change — within tolerance
        post = WindowMetrics(total_net_pnl=10.3, profit_factor=2.05, total_trades=16,
                             max_drawdown_pct=5.2, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        assert v.verdict == IMPACT_UNCHANGED


class TestEndToEnd:
    def test_improved_e2e(self) -> None:
        fx = _build_fixtures()
        plan_path = fx.apply_plans / "apply_plan_test001.json"
        verdict = evaluate_apply_plan_impact(plan_path, fx.evidence)
        assert verdict.verdict == IMPACT_IMPROVED
        assert verdict.bot_id == "freqtrade-freqforge"

    def test_markdown_rendering(self) -> None:
        from si_v2.impact.post_apply_impact import ImpactReport
        ap = {"apply_plan_id": "t1", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=15.0, profit_factor=2.5, total_trades=20,
                             max_drawdown_pct=3.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        report = ImpactReport(generated_at_utc="test", per_plan=(v,))
        md = render_impact_markdown(report)
        assert "IMPROVED" in md
        assert "Pre-Apply Metrics" in md
        assert "Post-Apply Metrics" in md
        assert "Deltas" in md


class TestJsonShape:
    def test_to_dict_contains_all_fields(self) -> None:
        from si_v2.impact.post_apply_impact import ImpactReport
        ap = {"apply_plan_id": "t1", "bot_id": "test", "hypothesis": "h1",
              "mutation_performed": False}
        pre = WindowMetrics(total_net_pnl=10.0, profit_factor=2.0, total_trades=15,
                            max_drawdown_pct=5.0, real_metric_cycles=2, cycle_count=2)
        post = WindowMetrics(total_net_pnl=15.0, profit_factor=2.5, total_trades=20,
                             max_drawdown_pct=3.0, real_metric_cycles=2, cycle_count=2)
        v = _compute_impact_verdict(ap, pre, post)
        report = ImpactReport(generated_at_utc="test", per_plan=(v,))
        d = report.to_dict()
        assert "generated_at_utc" in d
        assert "per_plan" in d
        per_plan_raw = d["per_plan"]
        assert isinstance(per_plan_raw, list)
        assert len(per_plan_raw) == 1
        entry = per_plan_raw[0]
        assert isinstance(entry, dict)
        assert "apply_plan_id" in entry
        assert "verdict" in entry
        assert "pre_metrics" in entry
        assert "post_metrics" in entry
        assert "delta_pnl" in entry
        # Round-trip through JSON
        serialized = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["per_plan"][0]["verdict"] == IMPACT_IMPROVED
