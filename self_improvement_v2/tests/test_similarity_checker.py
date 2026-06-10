"""Test similarity checker: distance computation and similarity detection."""

from __future__ import annotations

from si_v2.propose.similarity_checker import SimilarityChecker


class TestSimilarityChecker:
    """Tests for the SimilarityChecker class."""

    def test_identical_params_distance_zero(self, similarity_checker: SimilarityChecker) -> None:
        """Identical parameter sets should have distance 0."""
        params = {"rsi_period": 14, "stoploss_pct": -0.02}
        distance = similarity_checker.compute_distance(params, params)
        assert distance == 0.0

    def test_different_params_distance_positive(self, similarity_checker: SimilarityChecker) -> None:
        """Different parameter sets should have distance > 0."""
        params_a = {"rsi_period": 14, "stoploss_pct": -0.02}
        params_b = {"rsi_period": 30, "stoploss_pct": -0.10}
        distance = similarity_checker.compute_distance(params_a, params_b)
        assert distance > 0.0

    def test_symmetric_distance(self, similarity_checker: SimilarityChecker) -> None:
        """Distance should be symmetric: d(a,b) == d(b,a)."""
        params_a = {"rsi_period": 14, "stoploss_pct": -0.02}
        params_b = {"rsi_period": 30, "stoploss_pct": -0.10}
        d1 = similarity_checker.compute_distance(params_a, params_b)
        d2 = similarity_checker.compute_distance(params_b, params_a)
        assert abs(d1 - d2) < 1e-10

    def test_empty_params_both(self, similarity_checker: SimilarityChecker) -> None:
        """Two empty param sets should have distance 0."""
        distance = similarity_checker.compute_distance({}, {})
        assert distance == 0.0

    def test_one_empty_returns_max(self, similarity_checker: SimilarityChecker) -> None:
        """One empty and one non-empty should have distance > 0."""
        params = {"rsi_period": 14}
        distance = similarity_checker.compute_distance(params, {})
        assert distance > 0.0

    def test_is_too_similar_identical(self, similarity_checker: SimilarityChecker) -> None:
        """Identical candidate to history entry should be too similar."""
        candidate = {"rsi_period": 14, "stoploss_pct": -0.02}
        history = [{"rsi_period": 14, "stoploss_pct": -0.02}]
        assert similarity_checker.is_too_similar(candidate, history) is True

    def test_is_too_similar_different(self, similarity_checker: SimilarityChecker) -> None:
        """Very different candidate should not be too similar."""
        candidate = {"rsi_period": 50, "stoploss_pct": -0.5}
        history = [{"rsi_period": 2, "stoploss_pct": -0.001}]
        assert similarity_checker.is_too_similar(candidate, history) is False

    def test_is_too_similar_empty_history(self, similarity_checker: SimilarityChecker) -> None:
        """Empty history means no similarity found."""
        candidate = {"rsi_period": 14}
        assert similarity_checker.is_too_similar(candidate, []) is False

    def test_is_too_similar_custom_threshold(self, similarity_checker: SimilarityChecker) -> None:
        """Custom threshold affects similarity detection."""
        candidate = {"rsi_period": 14, "stoploss_pct": -0.02}
        history = [{"rsi_period": 15, "stoploss_pct": -0.021}]
        # With very strict threshold
        assert similarity_checker.is_too_similar(candidate, history, threshold=0.001) is False
        # With very loose threshold
        assert similarity_checker.is_too_similar(candidate, history, threshold=1.0) is True
