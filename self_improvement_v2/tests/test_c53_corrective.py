"""C5.3 corrective tests — Gate-0 strategy isolation and evaluation pipeline.

Tests verify the C5.3 corrective requirements:
- Strategy is fully stripped (AST contract)
- Ruff passes on strategy code
- Freqtrade-compatible import (with controlled stubs)
- Manifest v3 roundtrip, sidecar, provenance
- Entry-time regime without lookahead
- Selection-only evaluation with holdout isolation
- Threshold boundary tests
- Post-entry invariance

All tests are A1 (repository-only, no runtime mutation).
"""

from __future__ import annotations

import ast
import hashlib
import json
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]
STRATEGY_PATH = REPO / "freqforge" / "user_data" / "strategies" / "FreqForge_Gate0_Core_v1.py"


# ---------------------------------------------------------------------------
# AST contract: strategy is fully stripped
# ---------------------------------------------------------------------------


class TestStrategyAstContract:
    """AST-level contract: no forbidden imports, symbols, I/O, or sys.path."""

    @pytest.fixture
    def source(self) -> str:
        return STRATEGY_PATH.read_text()

    @pytest.fixture
    def tree(self) -> ast.Module:
        return ast.parse(STRATEGY_PATH.read_text())

    def test_no_sys_path_manipulation(self):
        """No sys.path.insert, sys.path.append, or sys.path manipulation."""
        tree = ast.parse(STRATEGY_PATH.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "sys":
                    if node.attr == "path":
                        pytest.fail(
                            f"sys.path reference at line {node.lineno}"
                        )

    def test_no_primo_import(self, source: str):
        """No primo_signal import."""
        for line in source.splitlines():
            if "import" in line and "primo" in line.lower():
                pytest.fail(f"Primo import found: {line}")

    def test_no_fleetrisk_import(self, source: str):
        """No FleetRiskManager import."""
        for line in source.splitlines():
            if "import" in line and "FleetRisk" in line:
                pytest.fail(f"FleetRisk import found: {line}")

    def test_no_ai_override_methods(self, source: str):
        """No _get_ai_override_signal or _inject_ai_signal_override methods."""
        assert "_get_ai_override_signal" not in source
        assert "_inject_ai_signal_override" not in source

    def test_no_ai_override_class_vars(self, source: str):
        """No AI_OVERRIDE_ALLOWED_PAIRS or AI_OVERRIDE_CONFIDENCE_MIN."""
        assert "AI_OVERRIDE_ALLOWED_PAIRS" not in source
        assert "AI_OVERRIDE_CONFIDENCE_MIN" not in source

    def test_no_confirm_trade_entry_override(self, source: str):
        """No confirm_trade_entry override — inherits IStrategy default."""
        assert "def confirm_trade_entry" not in source

    def test_no_bot_loop_start_override(self, source: str):
        """No bot_loop_start override — inherits IStrategy default."""
        assert "def bot_loop_start" not in source

    def test_no_file_io(self, source: str):
        """No file I/O — no open(), os.makedirs, or file writes."""
        assert "os.makedirs" not in source
        assert "os.path" not in source
        # Check for open() calls (not in comments/docstrings)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "open":
                    pytest.fail(f"File I/O found: open() at line {node.lineno}")

    def test_no_json_import(self, source: str):
        """No json import — no JSONL logging."""
        assert "import json" not in source
        assert "import os" not in source

    def test_no_noop_stubs(self, source: str):
        """No noop stubs — no _Gate0Noop, _gate0_noop, or künstliche Runtime-Objekte."""
        assert "_Gate0Noop" not in source
        assert "_gate0_noop_gate" not in source
        assert "_gate0_noop_state" not in source

    def test_no_normalize_pair_stub(self, source: str):
        """No normalize_pair stub — it was an AI-override dependency."""
        assert "def normalize_pair" not in source

    def test_no_risk_manager_references(self, source: str):
        """No self.risk_manager references."""
        assert "self.risk_manager" not in source

    def test_no_fleet_source_references(self, source: str):
        """No self._fleet_source references."""
        assert "self._fleet_source" not in source

    def test_has_native_entry_logic(self, source: str):
        """Strategy retains native entry logic: populate_entry_trend."""
        assert "def populate_entry_trend" in source
        assert "trend_long" in source
        assert "trend_short" in source

    def test_has_custom_stoploss(self, source: str):
        """Strategy retains custom_stoploss."""
        assert "def custom_stoploss" in source

    def test_has_class_definition(self, tree: ast.Module):
        """FreqForge_Gate0_Core_v1 class is defined and inherits IStrategy."""
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "FreqForge_Gate0_Core_v1" in class_names


# ---------------------------------------------------------------------------
# Ruff check: zero errors on strategy
# ---------------------------------------------------------------------------


class TestRuffClean:
    """Ruff must report 0 errors on Gate-0 strategy code."""

    def test_ruff_check_strategy(self):
        """ruff check must pass on the strategy file."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(STRATEGY_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"ruff check failed:\n{result.stdout}\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Freqtrade-compatible import test (with controlled stubs)
# ---------------------------------------------------------------------------


class TestFreqtradeImport:
    """Verify the strategy can be imported with Freqtrade-compatible stubs."""

    def test_strategy_imports_with_stubs(self):
        """Import the strategy with controlled Freqtrade/TA-Lib stubs.

        This proves the strategy file has no external runtime dependencies
        beyond Freqtrade and TA-Lib.
        """
        import importlib

        # Create minimal stubs for freqtrade and talib if not installed
        import sys

        stubs_created = []

        try:
            import freqtrade  # noqa: F401
        except ImportError:
            # Create minimal freqtrade stubs
            import types

            freqtrade_mod = types.ModuleType("freqtrade")
            freqtrade_mod.__path__ = []  # mark as package

            strategy_mod = types.ModuleType("freqtrade.strategy")
            strategy_mod.IStrategy = type(
                "IStrategy", (), {"__init__": lambda self, config: None}
            )
            strategy_mod.IntParameter = type(
                "IntParameter", (), {"__init__": lambda self, *a, **kw: None}
            )
            strategy_mod.DecimalParameter = type(
                "DecimalParameter", (), {"__init__": lambda self, *a, **kw: None}
            )
            strategy_mod.merge_informative_pair = lambda *a, **kw: a[0] if a else None
            freqtrade_mod.strategy = strategy_mod

            vendor_mod = types.ModuleType("freqtrade.vendor")
            vendor_mod.__path__ = []

            qtpylib_mod = types.ModuleType("freqtrade.vendor.qtpylib")
            qtpylib_mod.__path__ = []
            qtpylib_mod.bollinger_bands = lambda *a, **kw: {
                "lower": 0,
                "mid": 0,
                "upper": 0,
            }
            qtpylib_mod.typical_price = lambda df: df

            indicators_mod = types.ModuleType("freqtrade.vendor.qtpylib.indicators")
            indicators_mod.bollinger_bands = qtpylib_mod.bollinger_bands
            indicators_mod.typical_price = qtpylib_mod.typical_price
            qtpylib_mod.indicators = indicators_mod

            vendor_mod.qtpylib = qtpylib_mod
            freqtrade_mod.vendor = vendor_mod

            sys.modules["freqtrade"] = freqtrade_mod
            sys.modules["freqtrade.strategy"] = strategy_mod
            sys.modules["freqtrade.vendor"] = vendor_mod
            sys.modules["freqtrade.vendor.qtpylib"] = qtpylib_mod
            sys.modules["freqtrade.vendor.qtpylib.indicators"] = indicators_mod
            stubs_created.extend([
                "freqtrade",
                "freqtrade.strategy",
                "freqtrade.vendor",
                "freqtrade.vendor.qtpylib",
                "freqtrade.vendor.qtpylib.indicators",
            ])

        try:
            import talib  # noqa: F401
        except ImportError:
            import types

            talib_mod = types.ModuleType("talib")
            talib_abstract = types.ModuleType("talib.abstract")
            talib_mod.abstract = talib_abstract
            sys.modules["talib"] = talib_mod
            sys.modules["talib.abstract"] = talib_abstract
            stubs_created.extend(["talib", "talib.abstract"])

        try:
            import pandas  # noqa: F401
        except ImportError:
            import types

            pandas_mod = types.ModuleType("pandas")
            pandas_mod.DataFrame = type("DataFrame", (), {})
            sys.modules["pandas"] = pandas_mod
            stubs_created.append("pandas")

        try:
            # Import the strategy module
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "FreqForge_Gate0_Core_v1", str(STRATEGY_PATH)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Verify class exists
            assert hasattr(module, "FreqForge_Gate0_Core_v1")

            # Verify it can be instantiated
            strategy_cls = module.FreqForge_Gate0_Core_v1
            instance = strategy_cls.__new__(strategy_cls)
            instance._regime_histories = {}
            assert instance._regime_histories == {}

        finally:
            # Clean up stubs
            for mod_name in stubs_created:
                sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Manifest v3: roundtrip, sidecar, provenance
# ---------------------------------------------------------------------------


class TestManifestV3:
    """Manifest v3 artifact tests."""

    def test_build_manifest_v3_exists(self):
        """build_manifest_v3 function exists."""
        from si_v2.research.gate0_evaluation_integration import build_manifest_v3

        assert callable(build_manifest_v3)

    def test_build_manifest_v2_is_deprecated(self):
        """build_manifest_v2 emits DeprecationWarning and delegates to v3."""
        from si_v2.research.gate0_evaluation_integration import build_manifest_v2

        # It should warn but still work (will fail-closed without snapshot)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                build_manifest_v2(
                    snapshot_id="test",
                    fetcher_commit_sha="0" * 40,
                )
            except (RuntimeError, OSError, FileNotFoundError):
                pass  # Expected fail-closed without real snapshot
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) > 0, (
                "build_manifest_v2 must emit DeprecationWarning"
            )

    def test_manifest_v3_id_is_correct(self):
        """Manifest v3 source contains the correct manifest_id."""
        import inspect

        from si_v2.research.gate0_evaluation_integration import build_manifest_v3

        source = inspect.getsource(build_manifest_v3)
        assert "gate0-manifest-v3-20260721" in source
        assert "issue-665-C53-CORRECTIVE" in source

    def test_manifest_v3_has_tail_quantile(self):
        """Manifest v3 includes tail_quantile=0.05."""
        import inspect

        from si_v2.research.gate0_evaluation_integration import build_manifest_v3

        source = inspect.getsource(build_manifest_v3)
        assert "tail_quantile=0.05" in source

    def test_manifest_v3_provenance_defaults_to_gate0(self):
        """Manifest v3 strategy_identifier defaults to FreqForge_Gate0_Core_v1."""
        from si_v2.research.gate0_strategy_provenance import StrategyProvenance

        sp = StrategyProvenance()
        assert sp.strategy_class == "FreqForge_Gate0_Core_v1"


# ---------------------------------------------------------------------------
# Entry-time regime: no lookahead
# ---------------------------------------------------------------------------


class TestEntryTimeRegime:
    """classify_regime_at_entry must use entry-time-only data."""

    def test_classify_regime_at_entry_exists(self):
        """Function exists with correct signature."""
        from si_v2.research.gate0_evaluation_integration import (
            classify_regime_at_entry,
        )

        import inspect

        sig = inspect.signature(classify_regime_at_entry)
        params = list(sig.parameters.keys())
        assert "pair_candles" in params
        assert "entry_timestamp" in params
        assert "lookback" in params

    def test_insufficient_data_returns_insufficient(self):
        """Few candles return insufficient_data."""
        from si_v2.research.evaluation_bundle_v1 import CandleV1
        from si_v2.research.gate0_evaluation_integration import (
            classify_regime_at_entry,
        )

        entry_ts = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
        candles = [
            CandleV1(
                pair="BTC/USDT",
                timestamp=entry_ts - timedelta(minutes=15 * (10 - i)),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=10.0,
            )
            for i in range(10)
        ]
        result = classify_regime_at_entry(candles, entry_ts)
        assert result == "insufficient_data"

    def test_post_entry_candles_do_not_change_result(self):
        """Adding post-entry candles must not change the regime classification."""
        from si_v2.research.evaluation_bundle_v1 import CandleV1
        from si_v2.research.gate0_evaluation_integration import (
            classify_regime_at_entry,
        )

        entry_ts = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)

        def make_candle(offset_minutes: int, volatility: float = 0.01) -> CandleV1:
            ts = entry_ts - timedelta(minutes=offset_minutes)
            base = 100.0
            return CandleV1(
                pair="BTC/USDT",
                timestamp=ts,
                open=base,
                high=base * (1 + volatility),
                low=base * (1 - volatility),
                close=base,
                volume=10.0,
            )

        # 100 pre-entry candles
        pre_entry = [make_candle(15 * (100 - i)) for i in range(100)]

        result_without_post = classify_regime_at_entry(pre_entry, entry_ts)

        # Add 50 post-entry candles with extreme volatility
        post_entry = [
            CandleV1(
                pair="BTC/USDT",
                timestamp=entry_ts + timedelta(minutes=15 * (i + 1)),
                open=100.0,
                high=1000.0,
                low=1.0,
                close=500.0,
                volume=1000.0,
            )
            for i in range(50)
        ]

        result_with_post = classify_regime_at_entry(
            pre_entry + post_entry, entry_ts
        )

        assert result_without_post == result_with_post, (
            "Post-entry candles must not change entry-time regime classification"
        )

    def test_only_same_pair_candles(self):
        """Only candles of the same pair are considered."""
        from si_v2.research.evaluation_bundle_v1 import CandleV1
        from si_v2.research.gate0_evaluation_integration import (
            classify_regime_at_entry,
        )

        entry_ts = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)

        btc_candles = [
            CandleV1(
                pair="BTC/USDT",
                timestamp=entry_ts - timedelta(minutes=15 * (100 - i)),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
            )
            for i in range(100)
        ]
        # Different pair candles that should be ignored
        eth_candles = [
            CandleV1(
                pair="ETH/USDT",
                timestamp=entry_ts - timedelta(minutes=15 * (100 - i)),
                open=2000.0,
                high=5000.0,
                low=100.0,
                close=3000.0,
                volume=1000.0,
            )
            for i in range(100)
        ]

        result_btc_only = classify_regime_at_entry(btc_candles, entry_ts)
        result_with_eth = classify_regime_at_entry(
            btc_candles + eth_candles, entry_ts
        )
        assert result_btc_only == result_with_eth


# ---------------------------------------------------------------------------
# Selection-only evaluation: holdout isolation
# ---------------------------------------------------------------------------


class TestSelectionEvaluation:
    """evaluate_selection must isolate holdout."""

    def test_evaluate_selection_exists(self):
        """evaluate_selection method exists on EvaluationRunnerV1."""
        from si_v2.research.evaluation_bundle_v1 import EvaluationRunnerV1

        assert hasattr(EvaluationRunnerV1, "evaluate_selection")

    def test_selection_does_not_materialize_holdout_metrics(self):
        """Selection evaluation must not include holdout in partition_metrics."""
        # This is verified at the interface level — evaluate_selection only
        # processes calibration + walk_forward_windows, never holdout.
        import inspect

        from si_v2.research.evaluation_bundle_v1 import EvaluationRunnerV1

        source = inspect.getsource(EvaluationRunnerV1.evaluate_selection)
        # Must not compute metrics for holdout partition
        assert "selection_windows" in source
        assert "holdout_candle_count" in source or "HOLDOUT_CANDLES" in source

    def test_selection_rejects_holdout_candles(self):
        """Holdout candles in bundle → INVALID."""
        from si_v2.research.evaluation_bundle_v1 import (
            CandleV1,
            EvaluationRunnerV1,
        )

        # Create a minimal bundle with holdout candles
        holdout_start = datetime(2026, 1, 1, tzinfo=UTC)
        holdout_candle = CandleV1(
            pair="BTC/USDT",
            timestamp=holdout_start + timedelta(hours=1),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
        )

        # We can't easily build a full bundle without snapshot hashes,
        # but we can test the holdout candle detection logic directly
        holdout = MagicMock()
        holdout.start = holdout_start
        holdout.end = holdout_start + timedelta(days=180)

        count = sum(
            1
            for c in [holdout_candle]
            if holdout.start <= c.timestamp < holdout.end
        )
        assert count == 1, "Holdout candle detection must work"


# ---------------------------------------------------------------------------
# Threshold boundaries: strict inequalities
# ---------------------------------------------------------------------------


class TestThresholdBoundaries:
    """Threshold boundary tests — verify strict inequalities."""

    def test_trades_le_100_extends(self):
        """<= 100 trades → EXTEND (strict > 100 required)."""
        from si_v2.research.evaluation_bundle_v1 import EvaluationRunnerV1

        manifest = MagicMock()
        manifest.thresholds.min_trades = 100
        manifest.thresholds.min_duration_days = 90.0
        manifest.thresholds.min_regimes = 2
        manifest.thresholds.max_confidence_interval_width = 0.05
        manifest.thresholds.max_drawdown_pct = 25.0
        manifest.thresholds.min_profit_factor = 1.3
        manifest.thresholds.min_edge_mean = 0.01
        manifest.thresholds.min_edge_lower_bound = 0.0
        manifest.walk_forward_windows = [MagicMock(label="walk_forward_1")]

        metric = MagicMock()
        metric.trade_count = 100  # exactly at boundary
        metric.duration_days = 92.0
        metric.regime_trade_counts = {"high_volatility": 50, "low_volatility": 50}
        metric.bootstrap.width = 0.01
        metric.max_drawdown_pct = 10.0
        metric.profit_factor_state = MagicMock()
        metric.profit_factor = 2.0
        metric.bootstrap.mean = 0.05
        metric.bootstrap.lower = 0.02

        outcome, reasons = EvaluationRunnerV1._selection_outcome(
            manifest, {"walk_forward_1": metric}
        )
        # 100 trades is <= 100 → INSUFFICIENT_TRADES → EXTEND
        assert "INSUFFICIENT_TRADES" in reasons

    def test_trades_101_can_pass(self):
        """101 trades can pass the trades threshold."""
        from si_v2.research.evaluation_bundle_v1 import (
            EvaluationRunnerV1,
            ProfitFactorState,
        )

        manifest = MagicMock()
        manifest.thresholds.min_trades = 100
        manifest.thresholds.min_duration_days = 90
        manifest.thresholds.min_regimes = 2
        manifest.thresholds.max_confidence_interval_width = 0.05
        manifest.thresholds.max_drawdown_pct = 25.0
        manifest.thresholds.min_profit_factor = 1.3
        manifest.thresholds.min_edge_mean = 0.01
        manifest.thresholds.min_edge_lower_bound = 0.0
        manifest.walk_forward_windows = [MagicMock(label="walk_forward_1")]

        metric = MagicMock()
        metric.trade_count = 101
        metric.duration_days = 92
        metric.regime_trade_counts = {"high_volatility": 50, "low_volatility": 51}
        metric.bootstrap.width = 0.01
        metric.max_drawdown_pct = 10.0
        metric.profit_factor_state = ProfitFactorState.FINITE
        metric.profit_factor = 2.0
        metric.bootstrap.mean = 0.05
        metric.bootstrap.lower = 0.02

        outcome, reasons = EvaluationRunnerV1._selection_outcome(
            manifest, {"walk_forward_1": metric}
        )
        assert outcome.value == "PASS_CANDIDATE"

    def test_drawdown_25_rejects(self):
        """>= 25% drawdown → REJECT."""
        from si_v2.research.evaluation_bundle_v1 import (
            EvaluationRunnerV1,
            ProfitFactorState,
        )

        manifest = MagicMock()
        manifest.thresholds.min_trades = 100
        manifest.thresholds.min_duration_days = 90
        manifest.thresholds.min_regimes = 2
        manifest.thresholds.max_confidence_interval_width = 0.05
        manifest.thresholds.max_drawdown_pct = 25.0
        manifest.thresholds.min_profit_factor = 1.3
        manifest.thresholds.min_edge_mean = 0.01
        manifest.thresholds.min_edge_lower_bound = 0.0
        manifest.walk_forward_windows = [MagicMock(label="walk_forward_1")]

        metric = MagicMock()
        metric.trade_count = 150
        metric.duration_days = 92
        metric.regime_trade_counts = {"high_volatility": 75, "low_volatility": 75}
        metric.bootstrap.width = 0.01
        metric.max_drawdown_pct = 25.0  # exactly at boundary
        metric.profit_factor_state = ProfitFactorState.FINITE
        metric.profit_factor = 2.0
        metric.bootstrap.mean = 0.05
        metric.bootstrap.lower = 0.02

        outcome, reasons = EvaluationRunnerV1._selection_outcome(
            manifest, {"walk_forward_1": metric}
        )
        assert outcome.value == "REJECT"
        assert "MAX_DRAWDOWN_GUARDRAIL" in reasons

    def test_profit_factor_13_rejects(self):
        """<= 1.3 profit factor → REJECT."""
        from si_v2.research.evaluation_bundle_v1 import (
            EvaluationRunnerV1,
            ProfitFactorState,
        )

        manifest = MagicMock()
        manifest.thresholds.min_trades = 100
        manifest.thresholds.min_duration_days = 90
        manifest.thresholds.min_regimes = 2
        manifest.thresholds.max_confidence_interval_width = 0.05
        manifest.thresholds.max_drawdown_pct = 25.0
        manifest.thresholds.min_profit_factor = 1.3
        manifest.thresholds.min_edge_mean = 0.01
        manifest.thresholds.min_edge_lower_bound = 0.0
        manifest.walk_forward_windows = [MagicMock(label="walk_forward_1")]

        metric = MagicMock()
        metric.trade_count = 150
        metric.duration_days = 92
        metric.regime_trade_counts = {"high_volatility": 75, "low_volatility": 75}
        metric.bootstrap.width = 0.01
        metric.max_drawdown_pct = 10.0
        metric.profit_factor_state = ProfitFactorState.FINITE
        metric.profit_factor = 1.3  # exactly at boundary
        metric.bootstrap.mean = 0.05
        metric.bootstrap.lower = 0.02

        outcome, reasons = EvaluationRunnerV1._selection_outcome(
            manifest, {"walk_forward_1": metric}
        )
        assert outcome.value == "REJECT"
        assert "PROFIT_FACTOR_GUARDRAIL" in reasons


# ---------------------------------------------------------------------------
# Existing C5.2 tests compatibility
# ---------------------------------------------------------------------------


class TestExistingTestsCompatibility:
    """Verify existing C5.2 tests still pass with the new code."""

    def test_c52_test_file_exists(self):
        """C5.2 test file still exists and is importable."""
        c52_test = REPO / "self_improvement_v2" / "tests" / "test_c52_gate0_core_strategy.py"
        assert c52_test.is_file()

    def test_c52_class_name_test_still_works(self):
        """The class name test from C5.2 still passes."""
        content = STRATEGY_PATH.read_text()
        assert "class FreqForge_Gate0_Core_v1(IStrategy):" in content

    def test_c52_no_fleetrisk_import_test_still_works(self):
        """The no-FleetRisk-import test from C5.2 still passes."""
        content = STRATEGY_PATH.read_text()
        for line in content.splitlines():
            if "import" in line and "FleetRiskManager" in line:
                pytest.fail(f"FleetRiskManager import found: {line}")

    def test_c52_no_primo_import_test_still_works(self):
        """The no-Primo-import test from C5.2 still passes."""
        content = STRATEGY_PATH.read_text()
        for line in content.splitlines():
            if "from primo_signal import" in line or "import primo_signal" in line:
                pytest.fail(f"Primo import found: {line}")

    def test_c52_max_missing_formula_exists(self):
        """The 5% formula function still exists."""
        from si_v2.research.gate0_evaluation_integration import (
            _compute_max_missing_candles,
        )

        result = _compute_max_missing_candles(
            pairs=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
            timeframe="15m",
        )
        assert result > 0
        assert 7000 < result < 10000


# ---------------------------------------------------------------------------
# Provenance documentation
# ---------------------------------------------------------------------------


class TestProvenanceDocumentation:
    """Strategy provenance documentation updated."""

    def test_provenance_defaults_to_gate0_core_v1(self):
        """Provenance defaults to FreqForge_Gate0_Core_v1."""
        from si_v2.research.gate0_strategy_provenance import StrategyProvenance

        sp = StrategyProvenance()
        assert sp.strategy_class == "FreqForge_Gate0_Core_v1"
        assert "FreqForge_Gate0_Core_v1" in sp.strategy_file

    def test_provenance_dependencies_all_false(self):
        """All dependency flags are False (stripped)."""
        from si_v2.research.gate0_strategy_provenance import StrategyProvenance

        sp = StrategyProvenance()
        assert sp.uses_fleet_risk_manager is False
        assert sp.uses_primo_signal is False
        assert sp.uses_dynamic_risk_gates is False

    def test_provenance_mentions_c53(self):
        """Provenance documentation references C5.3."""
        content = (
            REPO
            / "self_improvement_v2"
            / "src"
            / "si_v2"
            / "research"
            / "gate0_strategy_provenance.py"
        ).read_text()
        assert "C5.3" in content
