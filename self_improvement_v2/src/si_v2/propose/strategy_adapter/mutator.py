"""AST-based strategy mutation engine — mutates strategy source files in sandbox.

Uses Python's ast module to precisely find and replace parameter assignments
for rsi_period and cooldown_candles. Fails closed if a target parameter is
missing from the strategy file.
"""

from __future__ import annotations

import ast
import difflib

from si_v2.propose.strategy_adapter.schema import (
    StrategyMutationPlan,
    StrategyParameterName,
)

# Allowed value ranges for each mutable parameter
_PARAMETER_RANGES: dict[str, tuple[int, int]] = {
    "rsi_period": (2, 50),
    "cooldown_candles": (0, 100),
}


class StrategyMutator:
    """Applies AST-based parameter mutations to sandbox strategy copies.

    This is distinct from propose.strategy_mutator (which builds
    MutationCandidate objects). This class mutates actual Python source
    files via AST transformation.
    """

    def apply(
        self,
        plan: StrategyMutationPlan,
        changes: dict[StrategyParameterName, int],
    ) -> StrategyMutationPlan:
        """Apply parameter changes to the sandbox copy using AST mutation.

        Args:
            plan: The mutation plan with sandbox and backup paths.
            changes: Mapping of parameter names to new integer values.

        Returns:
            The updated plan with diff_preview and changed_parameters populated.

        Raises:
            ValueError: If parameter values are out of range, or if
                the strategy file has ambiguous assignments.
        """
        # Validate ranges first
        for param, value in changes.items():
            self._validate_range(param, value)

        source = plan.sandbox_path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            plan.validation_status = "failed"
            raise ValueError(f"Strategy file has syntax errors: {exc}") from exc

        changed_parameters: list[str] = []

        # Phase 1: Count all occurrences of each target parameter
        param_names: set[str] = set()
        for param in changes:
            param_name = param.value if isinstance(param, StrategyParameterName) else param
            param_names.add(param_name)

        found_counts: dict[str, int] = {name: 0 for name in param_names}
        found_nodes: dict[str, list[ast.Assign]] = {name: [] for name in param_names}

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in param_names:
                        found_counts[target.id] += 1
                        found_nodes[target.id].append(node)

        # Phase 2: Check for ambiguous (multiple) assignments
        for param_name, count in found_counts.items():
            if count > 1:
                raise ValueError(f"Ambiguous assignment for '{param_name}': found {count} occurrences in strategy file")

        # Phase 3: Replace values for single-occurrence params
        for param_name in list(param_names):
            if found_counts[param_name] == 1:
                node = found_nodes[param_name][0]
                new_value = changes[StrategyParameterName(param_name)]
                node.value = ast.Constant(value=new_value)
                changed_parameters.append(param_name)
                param_names.discard(param_name)

        # Phase 4: Missing parameters — FAIL CLOSED
        missing = list(param_names)
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(
                f"Missing required parameter(s) in strategy file: {missing_str}. "
                f"Strategy mutation requires all target parameters to exist in the source file."
            )

        # Write the mutated AST back
        mutated_source = ast.unparse(tree)
        plan.sandbox_path.write_text(mutated_source, encoding="utf-8")

        # Generate unified diff
        backup_text = plan.backup_path.read_text(encoding="utf-8")
        diff = difflib.unified_diff(
            backup_text.splitlines(keepends=True),
            mutated_source.splitlines(keepends=True),
            fromfile=str(plan.backup_path),
            tofile=str(plan.sandbox_path),
        )
        plan.diff_preview = "".join(diff)
        plan.changed_parameters = [StrategyParameterName(name) for name in changed_parameters]
        plan.validation_status = "pending"

        return plan

    def _validate_range(self, param: StrategyParameterName, value: int) -> None:
        """Validate that a parameter value is within its allowed range.

        Args:
            param: The parameter name.
            value: The proposed new value.

        Raises:
            ValueError: If the value is outside the allowed range.
        """
        param_name = param.value if isinstance(param, StrategyParameterName) else param
        if param_name not in _PARAMETER_RANGES:
            raise ValueError(f"Unknown parameter '{param_name}'")

        lo, hi = _PARAMETER_RANGES[param_name]
        if not lo <= value <= hi:
            raise ValueError(f"Value {value} for '{param_name}' is outside allowed range [{lo}, {hi}]")
