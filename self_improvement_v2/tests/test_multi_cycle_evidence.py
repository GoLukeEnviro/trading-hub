"""Tests for the SI v2 Multi-Cycle Profitability Evidence (#284).

Covers evidence loading, per-bot accumulation, classification, and
fleet-level recommendation logic.

Uses synthetic fixture data to avoid dependence on real evidence files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Final

from si_v2.evaluation.multi_cycle_evidence import (
    CLASS_BLOCKED,
    CLASS_CANDIDATE,
    CLASS_INCONCLUSIVE,
    CLASS_WATCH,
    MIN_REAL_METRICS_CYCLES,
    BotAccumulatedEvidence,
    BotCycleSnapshot,
    _accumulate_bot,
    _classify_bot,
    _extract_bot_snapshots,
    _find_evidence_files,
    _recommend_pilot_candidate,
    generate_multi_cycle_report,
    render_markdown_report,
)

# ---------------------------------------------------------------------------
# Fixtures: build synthetic evidence files
# ---------------------------------------------------------------------------

_BOT_IDS: Final[tuple[str, ...]] = (
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
)


def _make_evidence_file(
    directory: Path,
    cycle_id: str,
    bot_metrics: dict[str, dict[str, object]],
    *,
    profitability_verdict: str = "blocked",
) -> Path:
    """Create a synthetic evidence JSON file."""
    decisions = []
    for bot_id, metrics in bot_metrics.items():
        wf = {
            "total_net_pnl": metrics.get("net_pnl", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "total_trades": metrics.get("trades", 0),
            "max_drawdown_pct": metrics.get("drawdown", 0.0),
            "metrics_source": metrics.get("source", "not_applicable"),
            "evaluation_status": metrics.get("eval_status", "NOT_APPLICABLE"),
            "promotion_blocked": metrics.get("blocked", True),
            "promotion_block_reason_codes": metrics.get("reason_codes", []),
        }
        decisions.append({
            "bot_id": bot_id,
            "walk_forward_net_metrics": wf,
            "promotion_blocked": wf["promotion_blocked"],
            "promotion_block_reason_codes": wf["promotion_block_reason_codes"],
        })

    data = {
        "cycle_id": cycle_id,
        "generated_at_utc": f"2026-06-{cycle_id}",
        "per_bot_decisions": decisions,
        "profitability_gate": {"verdict": profitability_verdict},
    }

    path = directory / f"active_cycle_{cycle_id}.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _build_fixture_dir() -> Path:
    """Build a temp directory with synthetic evidence files."""
    tmp = Path(tempfile.mkdtemp(prefix="si_v2_test_evidence_"))

    # Cycle 1: all 4 bots with real positive metrics (candidate material)
    _make_evidence_file(tmp, "20260620T000000Z", {
        "freqtrade-freqforge": {"net_pnl": 10.0, "profit_factor": 2.0, "trades": 15,
                                "drawdown": 5.0, "source": "walk_forward_net_metrics",
                                "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-regime-hybrid": {"net_pnl": 3.0, "profit_factor": 1.2, "trades": 10,
                                    "drawdown": 8.0, "source": "walk_forward_net_metrics",
                                    "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-freqforge-canary": {"net_pnl": 8.0, "profit_factor": 1.8, "trades": 12,
                                        "drawdown": 4.0, "source": "walk_forward_net_metrics",
                                        "eval_status": "PASS_REVIEW", "blocked": False},
        "freqai-rebel": {"net_pnl": 5.0, "profit_factor": 1.5, "trades": 10,
                         "drawdown": 3.0, "source": "walk_forward_net_metrics",
                         "eval_status": "PASS_REVIEW", "blocked": False},
    }, profitability_verdict="candidate")

    # Cycle 2: all positive again
    _make_evidence_file(tmp, "20260620T060000Z", {
        "freqtrade-freqforge": {"net_pnl": 8.0, "profit_factor": 1.8, "trades": 12,
                                "drawdown": 4.0, "source": "walk_forward_net_metrics",
                                "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-regime-hybrid": {"net_pnl": 2.0, "profit_factor": 1.1, "trades": 8,
                                    "drawdown": 6.0, "source": "walk_forward_net_metrics",
                                    "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-freqforge-canary": {"net_pnl": 6.0, "profit_factor": 1.6, "trades": 10,
                                        "drawdown": 3.0, "source": "walk_forward_net_metrics",
                                        "eval_status": "PASS_REVIEW", "blocked": False},
        "freqai-rebel": {"net_pnl": 4.0, "profit_factor": 1.4, "trades": 8,
                         "drawdown": 2.0, "source": "walk_forward_net_metrics",
                         "eval_status": "PASS_REVIEW", "blocked": False},
    }, profitability_verdict="candidate")

    # Cycle 3: all positive again — enough for candidate
    _make_evidence_file(tmp, "20260620T120000Z", {
        "freqtrade-freqforge": {"net_pnl": 12.0, "profit_factor": 2.2, "trades": 18,
                                "drawdown": 3.0, "source": "walk_forward_net_metrics",
                                "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-regime-hybrid": {"net_pnl": 1.0, "profit_factor": 1.05, "trades": 6,
                                    "drawdown": 5.0, "source": "walk_forward_net_metrics",
                                    "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-freqforge-canary": {"net_pnl": 10.0, "profit_factor": 2.0, "trades": 14,
                                        "drawdown": 2.0, "source": "walk_forward_net_metrics",
                                        "eval_status": "PASS_REVIEW", "blocked": False},
        "freqai-rebel": {"net_pnl": 6.0, "profit_factor": 1.6, "trades": 12,
                         "drawdown": 2.5, "source": "walk_forward_net_metrics",
                         "eval_status": "PASS_REVIEW", "blocked": False},
    }, profitability_verdict="candidate")

    # Cycle 4: mixed — regime-hybrid goes deeply negative
    _make_evidence_file(tmp, "20260620T180000Z", {
        "freqtrade-freqforge": {"net_pnl": 5.0, "profit_factor": 1.5, "trades": 10,
                                "drawdown": 6.0, "source": "walk_forward_net_metrics",
                                "eval_status": "PASS_REVIEW", "blocked": False},
        "freqtrade-regime-hybrid": {"net_pnl": -15.0, "profit_factor": 0.4, "trades": 8,
                                    "drawdown": 20.0, "source": "walk_forward_net_metrics",
                                    "eval_status": "NEGATIVE_NET_METRICS", "blocked": True,
                                    "reason_codes": ["negative_net_pnl", "high_drawdown"]},
        "freqtrade-freqforge-canary": {"net_pnl": 2.0, "profit_factor": 1.2, "trades": 5,
                                        "drawdown": 2.0, "source": "walk_forward_net_metrics",
                                        "eval_status": "PASS_REVIEW", "blocked": False},
        "freqai-rebel": {"net_pnl": 1.0, "profit_factor": 1.1, "trades": 7,
                         "drawdown": 3.0, "source": "walk_forward_net_metrics",
                         "eval_status": "PASS_REVIEW", "blocked": False},
    }, profitability_verdict="blocked")

    # Cycle 5: regime-hybrid still negative, some bots have no proposal
    _make_evidence_file(tmp, "20260621T000000Z", {
        "freqtrade-freqforge": {"net_pnl": 0.0, "profit_factor": 0.0, "trades": 0,
                                "drawdown": 0.0, "source": "not_applicable",
                                "eval_status": "NOT_APPLICABLE", "blocked": True,
                                "reason_codes": ["no_proposal"]},
        "freqtrade-regime-hybrid": {"net_pnl": -12.0, "profit_factor": 0.5, "trades": 6,
                                    "drawdown": 18.0, "source": "walk_forward_net_metrics",
                                    "eval_status": "NEGATIVE_NET_METRICS", "blocked": True,
                                    "reason_codes": ["negative_net_pnl"]},
        "freqtrade-freqforge-canary": {"net_pnl": 0.0, "profit_factor": 0.0, "trades": 0,
                                        "drawdown": 0.0, "source": "not_applicable",
                                        "eval_status": "NOT_APPLICABLE", "blocked": True,
                                        "reason_codes": ["no_proposal"]},
        "freqai-rebel": {"net_pnl": 0.5, "profit_factor": 1.05, "trades": 5,
                         "drawdown": 2.0, "source": "walk_forward_net_metrics",
                         "eval_status": "PASS_REVIEW", "blocked": False},
    }, profitability_verdict="blocked")

    return tmp


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_FIXTURE_DIR: Path | None = None


def _get_fixture_dir() -> Path:
    global _FIXTURE_DIR
    if _FIXTURE_DIR is None:
        _FIXTURE_DIR = _build_fixture_dir()
    return _FIXTURE_DIR


# ---------------------------------------------------------------------------
# Evidence file discovery
# ---------------------------------------------------------------------------


class TestFindEvidenceFiles:
    def test_finds_recent_files(self) -> None:
        d = _get_fixture_dir()
        files = _find_evidence_files(d, max_files=3)
        assert len(files) == 3
        assert all(f.suffix == ".json" for f in files)

    def test_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = _find_evidence_files(tmp)
            assert files == []


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------


class TestExtractSnapshots:
    def test_extracts_all_bots(self) -> None:
        d = _get_fixture_dir()
        cycle_id, snapshots = _extract_bot_snapshots(
            d / "active_cycle_20260620T000000Z.json"
        )
        assert cycle_id == "20260620T000000Z"
        assert len(snapshots) == 4
        assert all(s.has_real_metrics for s in snapshots)
        assert all(s.bot_id in _BOT_IDS for s in snapshots)

    def test_extracts_no_proposal(self) -> None:
        d = _get_fixture_dir()
        _, snapshots = _extract_bot_snapshots(
            d / "active_cycle_20260621T000000Z.json"
        )
        ff = next(s for s in snapshots if s.bot_id == "freqtrade-freqforge")
        assert ff.has_real_metrics is False
        assert ff.metrics_source == "not_applicable"
        assert ff.evaluation_status == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Per-bot classification
# ---------------------------------------------------------------------------


class TestClassifyBot:
    def test_candidate_sufficient_real_evidence(self) -> None:
        """Bot with >= MIN_REAL_METRICS_CYCLES real cycles and positive metrics."""
        acc = BotAccumulatedEvidence(
            bot_id="test-bot",
            cycle_count=5,
            real_metrics_cycle_count=MIN_REAL_METRICS_CYCLES,
            no_proposal_count=0,
            negative_metrics_count=0,
            net_pnl_total=30.0,
            net_pnl_avg=10.0,
            profit_factor_avg=2.0,
            trade_count_total=30,
            trade_count_avg=6.0,
            max_drawdown_pct_max=5.0,
            max_drawdown_measured_count=MIN_REAL_METRICS_CYCLES,
            read_success_rate=1.0,
            classification="",
        )
        cls_reasons = _classify_bot(acc)
        assert cls_reasons[0] == CLASS_CANDIDATE

    def test_blocked_negative_pnl(self) -> None:
        acc = BotAccumulatedEvidence(
            bot_id="test-bot",
            cycle_count=5,
            real_metrics_cycle_count=5,
            no_proposal_count=0,
            negative_metrics_count=5,
            net_pnl_total=-10.0,
            net_pnl_avg=-2.0,
            profit_factor_avg=0.5,
            trade_count_total=50,
            trade_count_avg=10.0,
            max_drawdown_pct_max=8.0,
            max_drawdown_measured_count=5,
            read_success_rate=1.0,
            classification="",
        )
        cls_reasons = _classify_bot(acc)
        assert cls_reasons[0] == CLASS_BLOCKED
        assert any("net_pnl_avg" in r for r in cls_reasons[1])

    def test_watch_partial_evidence(self) -> None:
        """Bot with 1 real metrics cycle but not enough for candidate."""
        acc = BotAccumulatedEvidence(
            bot_id="test-bot",
            cycle_count=3,
            real_metrics_cycle_count=1,
            no_proposal_count=2,
            negative_metrics_count=0,
            net_pnl_total=5.0,
            net_pnl_avg=5.0,
            profit_factor_avg=1.5,
            trade_count_total=10,
            trade_count_avg=3.33,
            max_drawdown_pct_max=4.0,
            max_drawdown_measured_count=1,
            read_success_rate=0.33,
            classification="",
        )
        cls_reasons = _classify_bot(acc)
        assert cls_reasons[0] == CLASS_WATCH
        assert any("below" in r for r in cls_reasons[1])

    def test_inconclusive_no_real_metrics(self) -> None:
        acc = BotAccumulatedEvidence(
            bot_id="test-bot",
            cycle_count=8,
            real_metrics_cycle_count=0,
            no_proposal_count=8,
            negative_metrics_count=0,
            net_pnl_total=0.0,
            net_pnl_avg=0.0,
            profit_factor_avg=0.0,
            trade_count_total=0,
            trade_count_avg=0.0,
            max_drawdown_pct_max=0.0,
            max_drawdown_measured_count=0,
            read_success_rate=0.0,
            classification="",
        )
        cls_reasons = _classify_bot(acc)
        assert cls_reasons[0] == CLASS_INCONCLUSIVE
        assert "no_real_metrics_cycles" in cls_reasons[1]


# ---------------------------------------------------------------------------
# Full multi-cycle report (using fixtures)
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_report_with_fixtures(self) -> None:
        d = _get_fixture_dir()
        report = generate_multi_cycle_report(d, window_size=5)
        assert report.cycles_evaluated == 5
        assert len(report.per_bot) == 4
        assert all(b.bot_id in _BOT_IDS for b in report.per_bot)
        assert report.fleet_recommendation != ""

    def test_report_classifications(self) -> None:
        """With 3 positive cycles + 2 mixed, evaluate all bots."""
        d = _get_fixture_dir()
        report = generate_multi_cycle_report(d, window_size=5)
        cls = report.fleet_classifications

        # FreqForge: 4 real metrics cycles (1 no-proposal), all positive -> candidate
        assert cls.get("freqtrade-freqforge") == CLASS_CANDIDATE

        # Regime-Hybrid: 5 real metrics, avg PnL negative -> blocked
        assert cls.get("freqtrade-regime-hybrid") == CLASS_BLOCKED

        # FreqForge-Canary: 4 real metrics cycles (1 no-proposal), all positive -> candidate
        candidate = cls.get("freqtrade-freqforge-canary")
        assert candidate == CLASS_CANDIDATE, f"Expected CANDIDATE, got {candidate}"

        # FreqAI-Rebel: 5 real metrics, all positive -> candidate
        assert cls.get("freqai-rebel") == CLASS_CANDIDATE

    def test_report_serializable(self) -> None:
        d = _get_fixture_dir()
        report = generate_multi_cycle_report(d, window_size=3)
        d_out = report.to_dict()
        serialized = json.dumps(d_out, ensure_ascii=False)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["cycles_evaluated"] == 3

    def test_render_markdown(self) -> None:
        d = _get_fixture_dir()
        report = generate_multi_cycle_report(d, window_size=3)
        md = render_markdown_report(report)
        assert "## Per-Bot Accumulated Evidence" in md
        assert "## Fleet Recommendation" in md
        assert "## Missing Evidence" in md


# ---------------------------------------------------------------------------
# Fleet recommendation
# ---------------------------------------------------------------------------


class TestRecommendation:
    def test_picks_best_candidate(self) -> None:
        bots = [
            BotAccumulatedEvidence(
                bot_id="bot-a", cycle_count=5, real_metrics_cycle_count=5,
                no_proposal_count=0, negative_metrics_count=0,
                net_pnl_total=50.0, net_pnl_avg=10.0,
                profit_factor_avg=2.0, trade_count_total=50, trade_count_avg=10.0,
                max_drawdown_pct_max=5.0, max_drawdown_measured_count=5,
                read_success_rate=1.0, classification=CLASS_CANDIDATE,
            ),
            BotAccumulatedEvidence(
                bot_id="bot-b", cycle_count=5, real_metrics_cycle_count=5,
                no_proposal_count=0, negative_metrics_count=0,
                net_pnl_total=25.0, net_pnl_avg=5.0,
                profit_factor_avg=1.5, trade_count_total=40, trade_count_avg=8.0,
                max_drawdown_pct_max=3.0, max_drawdown_measured_count=5,
                read_success_rate=1.0, classification=CLASS_CANDIDATE,
            ),
        ]
        rec = _recommend_pilot_candidate(bots)
        assert rec[0] == "bot-a"

    def test_no_candidate_falls_back_to_watch(self) -> None:
        bots = [
            BotAccumulatedEvidence(
                bot_id="bot-a", cycle_count=5, real_metrics_cycle_count=5,
                no_proposal_count=0, negative_metrics_count=0,
                net_pnl_total=50.0, net_pnl_avg=10.0,
                profit_factor_avg=2.0, trade_count_total=50, trade_count_avg=10.0,
                max_drawdown_pct_max=5.0, max_drawdown_measured_count=5,
                read_success_rate=1.0, classification=CLASS_WATCH,
            ),
        ]
        rec = _recommend_pilot_candidate(bots)
        assert rec[0].startswith("watch:")

    def test_all_inconclusive_returns_none(self) -> None:
        bots = [
            BotAccumulatedEvidence(
                bot_id="bot-a", cycle_count=5, real_metrics_cycle_count=0,
                no_proposal_count=5, negative_metrics_count=0,
                net_pnl_total=0.0, net_pnl_avg=0.0,
                profit_factor_avg=0.0, trade_count_total=0, trade_count_avg=0.0,
                max_drawdown_pct_max=0.0, max_drawdown_measured_count=0,
                read_success_rate=0.0, classification=CLASS_INCONCLUSIVE,
            ),
        ]
        rec = _recommend_pilot_candidate(bots)
        assert rec[0] == "none"


# ---------------------------------------------------------------------------
# Accumulation logic
# ---------------------------------------------------------------------------


class TestAccumulate:
    def test_single_cycle(self) -> None:
        snaps = [
            BotCycleSnapshot(
                bot_id="test", cycle_id="c1", generated_at_utc="2026-06-20T00:00:00Z",
                has_real_metrics=True, net_pnl=10.0, profit_factor=2.0,
                trade_count=10, max_drawdown_pct=5.0, max_drawdown_measured=True,
                evaluation_status="PASS_REVIEW", metrics_source="walk_forward_net_metrics",
                promotion_blocked=False, promotion_block_reason_codes=(),
            ),
        ]
        acc = _accumulate_bot("test", snaps)
        assert acc.cycle_count == 1
        assert acc.real_metrics_cycle_count == 1
        assert acc.net_pnl_total == 10.0
        assert acc.net_pnl_avg == 10.0

    def test_multiple_cycles_with_mixed_metrics(self) -> None:
        snaps = [
            BotCycleSnapshot(
                bot_id="test", cycle_id="c1", generated_at_utc="a",
                has_real_metrics=True, net_pnl=10.0, profit_factor=2.0,
                trade_count=10, max_drawdown_pct=5.0, max_drawdown_measured=True,
                evaluation_status="PASS_REVIEW", metrics_source="walk_forward_net_metrics",
                promotion_blocked=False, promotion_block_reason_codes=(),
            ),
            BotCycleSnapshot(
                bot_id="test", cycle_id="c2", generated_at_utc="b",
                has_real_metrics=True, net_pnl=-3.0, profit_factor=0.5,
                trade_count=5, max_drawdown_pct=8.0, max_drawdown_measured=True,
                evaluation_status="NEGATIVE_NET_METRICS",
                metrics_source="walk_forward_net_metrics",
                promotion_blocked=True,
                promotion_block_reason_codes=("negative_net_pnl",),
            ),
            BotCycleSnapshot(
                bot_id="test", cycle_id="c3", generated_at_utc="c",
                has_real_metrics=False, net_pnl=0.0, profit_factor=0.0,
                trade_count=0, max_drawdown_pct=0.0, max_drawdown_measured=False,
                evaluation_status="NOT_APPLICABLE", metrics_source="not_applicable",
                promotion_blocked=True,
                promotion_block_reason_codes=("no_proposal",),
            ),
        ]
        acc = _accumulate_bot("test", snaps)
        assert acc.cycle_count == 3
        assert acc.real_metrics_cycle_count == 2
        assert acc.no_proposal_count == 1
        assert acc.negative_metrics_count == 1
        assert acc.net_pnl_total == 7.0
        assert acc.net_pnl_avg == 3.5


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


class TestOutputShape:
    def test_report_to_dict_has_all_keys(self) -> None:
        d = _get_fixture_dir()
        report = generate_multi_cycle_report(d, window_size=3)
        out = report.to_dict()
        assert "generated_at_utc" in out
        assert "window_size" in out
        assert "cycles_evaluated" in out
        assert "per_bot" in out
        assert "fleet_classifications" in out
        assert "fleet_recommendation" in out
        per_bot_raw = out.get("per_bot", [])
        assert isinstance(per_bot_raw, list)
        for bot_entry in per_bot_raw:
            assert isinstance(bot_entry, dict)
            assert "bot_id" in bot_entry
            assert "classification" in bot_entry
            assert "net_pnl_total" in bot_entry
            assert "profit_factor_avg" in bot_entry
            assert "trade_count_total" in bot_entry
            assert "max_drawdown_pct_max" in bot_entry
