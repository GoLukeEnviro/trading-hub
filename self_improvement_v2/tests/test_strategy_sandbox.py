"""Tests for Phase I: Strategy Mutation Sandbox.

Covers schemas, path guard, sandbox creation, AST-based mutation,
validation chain, and live-path safety.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from si_v2.propose.strategy_adapter.mutator import StrategyMutator
from si_v2.propose.strategy_adapter.path_guard import SandboxPathGuard
from si_v2.propose.strategy_adapter.sandbox import StrategySandbox
from si_v2.propose.strategy_adapter.schema import (
    StrategyMutationPlan,
    StrategyMutationRequest,
    StrategyMutationResult,
    StrategyParameterName,
)
from si_v2.propose.strategy_adapter.validator import StrategySandboxValidator

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "strategies"
SIMPLE_STRATEGY = FIXTURES_DIR / "simple_strategy.py"
MISSING_PARAM_STRATEGY = FIXTURES_DIR / "missing_param_strategy.py"
AMBIGUOUS_STRATEGY = FIXTURES_DIR / "ambiguous_strategy.py"
INVALID_PYTHON_STRATEGY = FIXTURES_DIR / "invalid_python_strategy.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─── I1: Schema Tests ────────────────────────────────────────────────────────


class TestStrategyMutationSchemas:
    """Test StrategyParameterName enum and all Pydantic models."""

    def test_enum_values(self) -> None:
        """Verify enum members match expected strings."""
        assert StrategyParameterName.RSI_PERIOD.value == "rsi_period"
        assert StrategyParameterName.COOLDOWN_CANDLES.value == "cooldown_candles"

    def test_enum_from_string(self) -> None:
        """Verify enum can be constructed from string."""
        assert StrategyParameterName("rsi_period") == StrategyParameterName.RSI_PERIOD
        assert StrategyParameterName("cooldown_candles") == StrategyParameterName.COOLDOWN_CANDLES

    def test_mutation_request_creation(self) -> None:
        """Verify StrategyMutationRequest model creation and validation."""
        request = StrategyMutationRequest(
            bot_id="test_bot",
            strategy_name="TestStrategy",
            source_path=Path("/tmp/source.py"),
            sandbox_root=Path("/tmp/sandbox"),
            parameter_changes={StrategyParameterName.RSI_PERIOD: 14},
            candidate_sha="abc123def456",
        )
        assert request.bot_id == "test_bot"
        assert request.strategy_name == "TestStrategy"
        assert request.parameter_changes[StrategyParameterName.RSI_PERIOD] == 14

    def test_mutation_request_empty_changes(self) -> None:
        """Verify empty parameter_changes is allowed."""
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="Test",
            source_path=Path("/tmp/s.py"),
            sandbox_root=Path("/tmp"),
            parameter_changes={},
            candidate_sha="sha",
        )
        assert request.parameter_changes == {}

    def test_mutation_plan_defaults(self) -> None:
        """Verify StrategyMutationPlan default values."""
        plan = StrategyMutationPlan(
            source_path=Path("/src.py"),
            sandbox_path=Path("/sand.py"),
            backup_path=Path("/bak.py"),
        )
        assert plan.diff_preview == ""
        assert plan.changed_parameters == []
        assert plan.validation_status == "pending"

    def test_mutation_result_fields(self) -> None:
        """Verify StrategyMutationResult model fields."""
        result = StrategyMutationResult(status="ok")
        assert result.status == "ok"
        assert result.reason == ""
        assert result.plan is None
        assert result.compile_error is None
        assert result.diff_text == ""


# ─── I2: Path Guard Tests ────────────────────────────────────────────────────


class TestSandboxPathGuard:
    """Test SandboxPathGuard methods — allowed, blocked, traversal, symlink."""

    def test_allowed_path_inside_sandbox(self, tmp_path: Path) -> None:
        """Verify a normal path inside sandbox resolves successfully."""
        guard = SandboxPathGuard()
        inner = tmp_path / "inner" / "file.py"
        inner.parent.mkdir(parents=True)
        inner.touch()
        resolved = guard.resolve_sandbox_path(inner, tmp_path)
        assert resolved == inner.resolve()

    def test_traversal_rejected(self, tmp_path: Path) -> None:
        """Verify path traversal outside sandbox raises ValueError."""
        guard = SandboxPathGuard()
        # Create a subdir under tmp, then try to traverse out
        sub = tmp_path / "sub"
        sub.mkdir()
        # /tmp/path/sub/../../etc/passwd
        traversal = sub / ".." / ".." / "etc" / "passwd"
        with pytest.raises(ValueError, match="outside sandbox root"):
            guard.resolve_sandbox_path(traversal, sub)

    def test_live_path_flagged(self) -> None:
        """Verify is_live_strategy_path detects live paths."""
        guard = SandboxPathGuard()
        assert guard.is_live_strategy_path(Path("/home/user_data/strategies/MyStrategy.py"))
        assert guard.is_live_strategy_path(Path("/opt/freqtrade/strategies/MyStrategy.py"))
        assert not guard.is_live_strategy_path(Path("/tmp/sandbox/strategy.py"))
        assert not guard.is_live_strategy_path(Path("/home/user_data/other/file.py"))

    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        """Verify symlink that points outside sandbox is rejected."""
        guard = SandboxPathGuard()
        # Create a file outside sandbox
        outside = tmp_path / "outside_file.py"
        outside.touch()

        # Create a symlink inside sandbox that points outside
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        link = sandbox / "escape_link.py"
        link.symlink_to(outside)

        with pytest.raises(ValueError, match="outside sandbox root"):
            guard.resolve_sandbox_path(link, sandbox)

    def test_assert_sandbox_path_live_path(self, tmp_path: Path) -> None:
        """Verify assert_sandbox_path raises on live strategy paths."""
        guard = SandboxPathGuard()
        live = tmp_path / "user_data" / "strategies" / "live.py"
        live.parent.mkdir(parents=True)
        live.touch()
        with pytest.raises(ValueError, match="live strategy path"):
            guard.assert_sandbox_path(live, tmp_path)

    def test_assert_sandbox_path_valid(self, tmp_path: Path) -> None:
        """Verify assert_sandbox_path passes for valid paths."""
        guard = SandboxPathGuard()
        valid = tmp_path / "sandbox" / "valid.py"
        valid.parent.mkdir(parents=True)
        valid.touch()
        # Should not raise
        guard.assert_sandbox_path(valid, tmp_path)


# ─── I3: Sandbox Tests ───────────────────────────────────────────────────────


class TestStrategySandbox:
    """Test StrategySandbox.create() — source unchanged, backup created."""

    def test_create_basic(self, tmp_path: Path) -> None:
        """Verify sandbox copy and backup are created, source unchanged."""
        sandbox = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="test_bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="testsha12345678",
        )
        source_checksum = SIMPLE_STRATEGY.stat().st_mtime_ns

        plan = sandbox.create(request)

        assert plan.source_path == SIMPLE_STRATEGY.resolve()
        assert plan.sandbox_path.exists()
        assert plan.backup_path.exists()
        # Source unchanged
        assert SIMPLE_STRATEGY.stat().st_mtime_ns == source_checksum

    def test_source_unchanged(self, tmp_path: Path) -> None:
        """Verify source strategy file is never modified."""
        original_content = SIMPLE_STRATEGY.read_bytes()
        sandbox = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.COOLDOWN_CANDLES: 10},
            candidate_sha="sha00001111",
        )
        sandbox.create(request)
        assert SIMPLE_STRATEGY.read_bytes() == original_content

    def test_backup_byte_identical(self, tmp_path: Path) -> None:
        """Verify backup is byte-identical to source."""
        sandbox = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="hash1234abcd",
        )
        plan = sandbox.create(request)
        assert plan.backup_path.read_bytes() == SIMPLE_STRATEGY.read_bytes()

    def test_sandbox_copy_created(self, tmp_path: Path) -> None:
        """Verify sandbox copy file is created and readable."""
        sandbox = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={},
            candidate_sha="testabcdef01",
        )
        plan = sandbox.create(request)
        assert plan.sandbox_path.is_file()
        content = plan.sandbox_path.read_text(encoding="utf-8")
        assert "class TestStrategy" in content

    def test_backup_exists_new_timestamped(self, tmp_path: Path) -> None:
        """Verify if backup exists, a timestamped version is created instead."""
        sandbox = StrategySandbox()
        # Use a sha where first 8 chars are distinct
        candidate_sha = "deadbeef12345678"
        short_sha = candidate_sha[:8]  # "deadbeef"

        # Create a pre-existing backup with the same short name
        existing_backup = tmp_path / f"backup_SimpleStrategy_{short_sha}.py"
        existing_backup.write_text("dummy content")

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={},
            candidate_sha=candidate_sha,
        )
        plan = sandbox.create(request)

        # Should have created a timestamped backup
        assert str(plan.backup_path.name).startswith(f"backup_SimpleStrategy_{short_sha}_")
        assert plan.backup_path.exists()
        # Verify the timestamped backup has the correct content
        assert plan.backup_path.read_bytes() == SIMPLE_STRATEGY.read_bytes()


# ─── I4: Mutator Tests ───────────────────────────────────────────────────────


class TestStrategyMutator:
    """Test StrategyMutator.apply() — single, both, missing, ambiguous, range."""

    def test_single_parameter_change(self, tmp_path: Path) -> None:
        """Verify changing rsi_period produces correct diff and value."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="mutatortest01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 21})

        assert StrategyParameterName.RSI_PERIOD in plan.changed_parameters
        assert "21" in plan.diff_preview or "rsi_period" in plan.diff_preview
        # Verify the actual file was modified
        content = plan.sandbox_path.read_text(encoding="utf-8")
        assert "rsi_period = 21" in content or "rsi_period=21" in content

    def test_both_parameters_changed(self, tmp_path: Path) -> None:
        """Verify changing both parameters works correctly."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={
                StrategyParameterName.RSI_PERIOD: 14,
                StrategyParameterName.COOLDOWN_CANDLES: 10,
            },
            candidate_sha="bothparams01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(
            plan,
            {
                StrategyParameterName.RSI_PERIOD: 14,
                StrategyParameterName.COOLDOWN_CANDLES: 10,
            },
        )

        assert StrategyParameterName.RSI_PERIOD in plan.changed_parameters
        assert StrategyParameterName.COOLDOWN_CANDLES in plan.changed_parameters
        content = plan.sandbox_path.read_text(encoding="utf-8")
        assert "rsi_period = 14" in content or "rsi_period=14" in content
        assert "cooldown_candles = 10" in content or "cooldown_candles=10" in content

    def test_missing_parameter_fail_closed(self, tmp_path: Path) -> None:
        """Verify that a missing parameter gets added rather than failing open."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="MissingParam",
            source_path=MISSING_PARAM_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.COOLDOWN_CANDLES: 10},
            candidate_sha="missingparam01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(
            plan,
            {StrategyParameterName.COOLDOWN_CANDLES: 10},
        )

        assert StrategyParameterName.COOLDOWN_CANDLES in plan.changed_parameters
        content = plan.sandbox_path.read_text(encoding="utf-8")
        assert "cooldown_candles" in content
        assert "10" in content

    def test_ambiguous_duplicates_rejected(self, tmp_path: Path) -> None:
        """Verify ambiguous (duplicate) rsi_period assignments raise ValueError."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="Ambiguous",
            source_path=AMBIGUOUS_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 14},
            candidate_sha="ambigtest01",
        )
        plan = sandbox_mgr.create(request)

        with pytest.raises(ValueError, match=r"Ambiguous assignment|ambiguous"):
            mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 14})

    def test_invalid_range_rejected(self, tmp_path: Path) -> None:
        """Verify out-of-range rsi_period value raises ValueError."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 99},
            candidate_sha="rangecheck01",
        )
        plan = sandbox_mgr.create(request)

        with pytest.raises(ValueError, match="outside allowed range"):
            mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 99})

    def test_invalid_range_cooldown(self, tmp_path: Path) -> None:
        """Verify out-of-range cooldown_candles value raises ValueError."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.COOLDOWN_CANDLES: -1},
            candidate_sha="rangecheck02",
        )
        plan = sandbox_mgr.create(request)

        with pytest.raises(ValueError, match="outside allowed range"):
            mutator.apply(plan, {StrategyParameterName.COOLDOWN_CANDLES: -1})


# ─── I5: Validator Tests ──────────────────────────────────────────────────────


class TestStrategySandboxValidator:
    """Test StrategySandboxValidator.validate() — full chain, compile, backup."""

    def test_full_validation_chain_passes(self, tmp_path: Path) -> None:
        """Verify valid mutation passes all checks."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        validator = StrategySandboxValidator()

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="validchain01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 21})
        result = validator.validate(plan)

        assert result.status == "ok"
        assert result.reason == "All validation checks passed"
        assert result.plan is not None
        assert result.plan.validation_status == "passed"

    def test_invalid_python_fails(self, tmp_path: Path) -> None:
        """Verify invalid Python syntax causes validation failure."""
        sandbox_mgr = StrategySandbox()

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="InvalidPython",
            source_path=INVALID_PYTHON_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 14},
            candidate_sha="invalidpy01",
        )
        plan = sandbox_mgr.create(request)

        # Try to mutate — should fail because the file has syntax errors
        mutator = StrategyMutator()
        with pytest.raises(ValueError, match="syntax error"):
            mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 14})

    def test_backup_missing_fails(self, tmp_path: Path) -> None:
        """Verify missing backup file causes validation failure."""
        validator = StrategySandboxValidator()
        plan = StrategyMutationPlan(
            source_path=SIMPLE_STRATEGY,
            sandbox_path=tmp_path / "sandbox_test.py",
            backup_path=tmp_path / "nonexistent_backup.py",
            changed_parameters=[StrategyParameterName.RSI_PERIOD],
        )
        # Create sandbox file so it exists
        plan.sandbox_path.write_text("rsi_period = 21\n")

        result = validator.validate(plan)
        assert result.status == "failed"
        assert "Backup file not found" in result.reason

    def test_compile_error_detected(self, tmp_path: Path) -> None:
        """Verify broken Python in sandbox copy is caught by compile check."""
        mutator = StrategyMutator()
        sandbox_mgr = StrategySandbox()
        validator = StrategySandboxValidator()

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="compileerr01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 21})

        # Corrupt sandbox copy
        plan.sandbox_path.write_text("this is definitely not valid python ==", encoding="utf-8")
        plan.diff_preview = "corrupted"

        result = validator.validate(plan)
        assert result.status == "failed"
        assert result.compile_error is not None


# ─── I6: Live Path Safety ─────────────────────────────────────────────────────


class TestLivePathSafety:
    """Verify no source code references live strategy write paths.

    Note: path_guard.py is exempted because it contains the detection
    strings intentionally for safety-check purposes.
    """

    def _iter_src_files(self) -> list[Path]:
        """Iterate over all .py files in src/si_v2, excluding path_guard."""
        files: list[Path] = []
        src_dir = PROJECT_ROOT / "src" / "si_v2"
        for root, _dirs, fnames in os.walk(src_dir):
            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(root) / fname
                # path_guard is exempt — it contains detection strings intentionally
                if "path_guard" in fpath.name:
                    continue
                files.append(fpath)
        return files

    def test_no_user_data_strategies_in_src(self) -> None:
        """Verify src/si_v2 has no references to user_data/strategies."""
        for fpath in self._iter_src_files():
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            assert "user_data/strategies" not in content, f"Found user_data/strategies in {fpath}"

    def test_no_freqtrade_strategies_in_src(self) -> None:
        """Verify src/si_v2 has no references to freqtrade/strategies."""
        for fpath in self._iter_src_files():
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            assert "freqtrade/strategies" not in content, f"Found freqtrade/strategies in {fpath}"


# ─── I7: Integration / Edge Cases ─────────────────────────────────────────────


class TestStrategyMutationIntegration:
    """Integration tests combining sandbox + mutator + validator."""

    def test_full_roundtrip_simple_strategy(self, tmp_path: Path) -> None:
        """Run full create → mutate → validate cycle on simple strategy."""
        sandbox_mgr = StrategySandbox()
        mutator = StrategyMutator()
        validator = StrategySandboxValidator()

        request = StrategyMutationRequest(
            bot_id="integration_bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={
                StrategyParameterName.RSI_PERIOD: 30,
                StrategyParameterName.COOLDOWN_CANDLES: 15,
            },
            candidate_sha="integration01",
        )
        plan = sandbox_mgr.create(request)
        plan = mutator.apply(
            plan,
            {
                StrategyParameterName.RSI_PERIOD: 30,
                StrategyParameterName.COOLDOWN_CANDLES: 15,
            },
        )
        result = validator.validate(plan)

        assert result.status == "ok"
        assert result.diff_text != ""
        # Verify actual values in sandbox copy
        content = plan.sandbox_path.read_text(encoding="utf-8")
        assert "30" in content or "rsi_period = 30" in content or "rsi_period=30" in content
        assert "15" in content or "cooldown_candles = 15" in content or "cooldown_candles=15" in content

    def test_sandbox_path_guard_integration(self, tmp_path: Path) -> None:
        """Verify sandbox refuses to copy from a live strategy path."""
        sandbox_mgr = StrategySandbox()

        # Create a file that looks like a live strategy path
        live_path = tmp_path / "user_data" / "strategies" / "LiveStrategy.py"
        live_path.parent.mkdir(parents=True)
        live_path.write_text("rsi_period = 14\n")

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="LiveStrategy",
            source_path=live_path,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 21},
            candidate_sha="liveguard01",
        )

        with pytest.raises(ValueError, match="live strategy path"):
            sandbox_mgr.create(request)

    def test_backup_preserves_original(self, tmp_path: Path) -> None:
        """Verify backup stays byte-identical even after mutation."""
        sandbox_mgr = StrategySandbox()
        mutator = StrategyMutator()

        request = StrategyMutationRequest(
            bot_id="bot",
            strategy_name="SimpleStrategy",
            source_path=SIMPLE_STRATEGY,
            sandbox_root=tmp_path,
            parameter_changes={StrategyParameterName.RSI_PERIOD: 14},
            candidate_sha="backupint01",
        )
        plan = sandbox_mgr.create(request)
        original_backup = plan.backup_path.read_bytes()

        plan = mutator.apply(plan, {StrategyParameterName.RSI_PERIOD: 42})

        # Backup must remain unchanged
        assert plan.backup_path.read_bytes() == original_backup
