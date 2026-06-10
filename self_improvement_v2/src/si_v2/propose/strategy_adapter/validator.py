"""Validation chain for sandbox strategy mutations.

Validates backup existence, diff presence, Python compilation,
and parameter value ranges.
"""

from __future__ import annotations

import difflib
import py_compile
import tempfile
from pathlib import Path

from si_v2.propose.strategy_adapter.schema import (
    StrategyMutationPlan,
    StrategyMutationResult,
    StrategyParameterName,
)

# Allowed value ranges for each mutable parameter
_PARAMETER_RANGES: dict[str, tuple[int, int]] = {
    "rsi_period": (2, 50),
    "cooldown_candles": (0, 100),
}


class StrategySandboxValidator:
    """Validates sandbox mutations through a multi-step safety chain.

    Checks performed:
    1. Backup file exists at backup_path
    2. Diff exists and is non-empty (if parameters were changed)
    3. Python compile check on sandbox copy
    4. Parameter value ranges are valid
    """

    def validate(self, plan: StrategyMutationPlan) -> StrategyMutationResult:
        """Run the full validation chain against a mutation plan.

        Args:
            plan: The mutation plan to validate.

        Returns:
            StrategyMutationResult with status 'ok' or 'failed' and
            detailed reason for failure.
        """
        # Check 1: backup exists
        if not plan.backup_path.is_file():
            return StrategyMutationResult(
                status="failed",
                reason=f"Backup file not found at {plan.backup_path}",
                plan=plan,
            )

        # Check 2: diff exists and is non-empty (if parameters changed)
        if plan.changed_parameters:
            if not plan.diff_preview.strip():
                # Generate diff from scratch to check
                if plan.backup_path.is_file() and plan.sandbox_path.is_file():
                    backup_text = plan.backup_path.read_text(encoding="utf-8")
                    sandbox_text = plan.sandbox_path.read_text(encoding="utf-8")
                    diff = difflib.unified_diff(
                        backup_text.splitlines(keepends=True),
                        sandbox_text.splitlines(keepends=True),
                        fromfile=str(plan.backup_path),
                        tofile=str(plan.sandbox_path),
                    )
                    diff_text = "".join(diff)
                    if not diff_text.strip():
                        return StrategyMutationResult(
                            status="failed",
                            reason="Parameters changed but no diff detected between backup and sandbox copy",
                            plan=plan,
                        )
                else:
                    return StrategyMutationResult(
                        status="failed",
                        reason="Parameters changed but diff_preview is empty and files are missing",
                        plan=plan,
                    )

            # Check 4: parameter ranges are valid
            range_errors = self._validate_parameter_ranges(plan)
            if range_errors:
                return StrategyMutationResult(
                    status="failed",
                    reason=range_errors,
                    plan=plan,
                )

        # Check 3: Python compile check
        compile_error = self._check_compile(plan.sandbox_path)
        if compile_error is not None:
            return StrategyMutationResult(
                status="failed",
                reason="Sandbox copy failed Python compile check",
                plan=plan,
                compile_error=compile_error,
                diff_text=self._read_diff(plan),
            )

        # Build diff text for successful result
        diff_text = self._read_diff(plan)

        plan.validation_status = "passed"
        return StrategyMutationResult(
            status="ok",
            reason="All validation checks passed",
            plan=plan,
            diff_text=diff_text,
        )

    def _check_compile(self, path: Path) -> str | None:
        """Run Python compile check on a file.

        Args:
            path: Path to the Python file to compile-check.

        Returns:
            Error message string if compilation fails, None if it succeeds.
        """
        try:
            # Write to a temp file for py_compile
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(path.read_text(encoding="utf-8"))
            try:
                py_compile.compile(str(tmp_path), doraise=True)
            except py_compile.PyCompileError as exc:
                return str(exc)
            finally:
                tmp_path.unlink(missing_ok=True)
        except OSError as exc:
            return f"File read error: {exc}"

        return None

    def _validate_parameter_ranges(self, plan: StrategyMutationPlan) -> str | None:
        """Validate that changed parameters are within allowed ranges.

        Args:
            plan: The mutation plan with changed parameters.

        Returns:
            Error string if any parameter is out of range, None otherwise.
        """
        # Read the sandbox copy to find actual values
        try:
            source = plan.sandbox_path.read_text(encoding="utf-8")
        except OSError:
            return "Cannot read sandbox copy for range validation"

        for param in plan.changed_parameters:
            param_name = param.value if isinstance(param, StrategyParameterName) else param
            if param_name not in _PARAMETER_RANGES:
                return f"Unknown parameter '{param_name}' in changed parameters"
            lo, hi = _PARAMETER_RANGES[param_name]
            value = self._extract_value_from_source(source, param_name)
            if value is not None and not lo <= value <= hi:
                return f"Parameter '{param_name}' has value {value} outside allowed range [{lo}, {hi}]"

        return None

    @staticmethod
    def _extract_value_from_source(source: str, param_name: str) -> int | None:
        """Extract an integer value for a parameter from source text.

        Uses simple regex-free line scanning to find assignment values.

        Args:
            source: Source code text.
            param_name: Parameter name to find.

        Returns:
            Integer value if found, None otherwise.
        """
        import ast as _ast

        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return None

        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, _ast.Name)
                        and target.id == param_name
                        and isinstance(node.value, _ast.Constant)
                        and isinstance(node.value.value, int)
                    ):
                        return node.value.value
        return None

    @staticmethod
    def _read_diff(plan: StrategyMutationPlan) -> str:
        """Read the diff between backup and sandbox copy.

        Args:
            plan: The mutation plan.

        Returns:
            Unified diff text or empty string if unavailable.
        """
        if plan.diff_preview:
            return plan.diff_preview
        try:
            backup_text = plan.backup_path.read_text(encoding="utf-8")
            sandbox_text = plan.sandbox_path.read_text(encoding="utf-8")
            diff = difflib.unified_diff(
                backup_text.splitlines(keepends=True),
                sandbox_text.splitlines(keepends=True),
                fromfile=str(plan.backup_path),
                tofile=str(plan.sandbox_path),
            )
            return "".join(diff)
        except OSError:
            return ""
