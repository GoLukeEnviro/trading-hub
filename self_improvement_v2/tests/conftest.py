"""Shared test fixtures for SI v2 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from si_v2.adapters.dry_run_stub import DryRunStubDocker, DryRunStubFreqtrade
from si_v2.analyze.performance_analyzer import PerformanceAnalyzer
from si_v2.propose.similarity_checker import SimilarityChecker
from si_v2.propose.strategy_mutator import StrategyMutator

# Path to the self_improvement_v2 project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Path to v1 state files for roundtrip tests
V1_STATE_DIR = Path("/home/hermes/projects/trading/var/trading-self-improvement/bot_a")


@pytest.fixture
def docker_stub() -> DryRunStubDocker:
    """Provide a DryRunStubDocker instance."""
    return DryRunStubDocker()


@pytest.fixture
def freqtrade_stub() -> DryRunStubFreqtrade:
    """Provide a DryRunStubFreqtrade instance."""
    return DryRunStubFreqtrade()


@pytest.fixture
def analyzer() -> PerformanceAnalyzer:
    """Provide a PerformanceAnalyzer instance."""
    return PerformanceAnalyzer()


@pytest.fixture
def mutator() -> StrategyMutator:
    """Provide a StrategyMutator instance."""
    return StrategyMutator()


@pytest.fixture
def similarity_checker() -> SimilarityChecker:
    """Provide a SimilarityChecker instance."""
    return SimilarityChecker()
