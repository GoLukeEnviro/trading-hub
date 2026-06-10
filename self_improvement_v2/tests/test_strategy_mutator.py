"""Test strategy mutator: candidate generation and guard enforcement."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.propose.strategy_mutator import StrategyMutator
from si_v2.state.schemas import AnalysisResult, WindowStats


def _make_analysis(decision: str, pnl: float = 0.0, trades: int = 10) -> AnalysisResult:
    """Create a test AnalysisResult with specified decision."""
    return AnalysisResult(
        bot_id="bot_a",
        bot_name="Bot A",
        decision=decision,
        ts=datetime.now(UTC),
        windows={
            "12h": WindowStats(
                trades=trades,
                wins=max(1, trades // 2),
                losses=max(1, trades // 3),
                pnl_abs=pnl,
            ),
        },
    )


class TestStrategyMutator:
    """Tests for the StrategyMutator class."""

    def test_returns_none_for_hold_decision(self, mutator: StrategyMutator) -> None:
        """build_candidate returns None when decision is 'hold'."""
        analysis = _make_analysis("hold")
        result = mutator.build_candidate("bot_a", analysis, [])
        assert result is None

    def test_returns_candidate_for_mutate(self, mutator: StrategyMutator) -> None:
        """build_candidate returns a MutationCandidate for 'mutate' decision with negative pnl."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        result = mutator.build_candidate("bot_a", analysis, [])
        assert result is not None
        assert result.bot_id == "bot_a"
        assert result.candidate_sha256  # Non-empty hash

    def test_candidate_has_proposal_only_mode(self, mutator: StrategyMutator) -> None:
        """Candidate always has proposal_only base_mode."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        result = mutator.build_candidate("bot_a", analysis, [])
        assert result is not None
        assert result.base_mode == "proposal_only"

    def test_candidate_has_safe_policy(self, mutator: StrategyMutator) -> None:
        """Candidate always has safe_parameter_overlay_only policy."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        result = mutator.build_candidate("bot_a", analysis, [])
        assert result is not None
        assert result.mutation_policy == "safe_parameter_overlay_only"

    def test_guard_candidate_enforced(self, mutator: StrategyMutator) -> None:
        """Parameters in candidate must pass guard_candidate check."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        result = mutator.build_candidate("bot_a", analysis, [])
        if result is not None:
            from si_v2.propose.safe_parameters import guard_candidate

            assert guard_candidate(result.parameters) is True

    def test_candidate_requires_backtest(self, mutator: StrategyMutator) -> None:
        """Candidate should require backtest validation."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        result = mutator.build_candidate("bot_a", analysis, [])
        assert result is not None
        assert result.requires_backtest is True

    def test_candidate_sha256_is_deterministic(self, mutator: StrategyMutator) -> None:
        """Same parameters produce the same SHA256 hash."""
        analysis = _make_analysis("mutate", pnl=-50.0, trades=10)
        r1 = mutator.build_candidate("bot_a", analysis, [])
        r2 = mutator.build_candidate("bot_a", analysis, [])
        assert r1 is not None
        assert r2 is not None
        assert r1.candidate_sha256 == r2.candidate_sha256
