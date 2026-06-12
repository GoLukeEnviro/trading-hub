"""Validation Gate Matrix builder (issue #65).

Runs all registered gates against a ``ValidationMatrixRequest`` in
stable registry order, computes the overall verdict, and produces a
deterministic ``ValidationMatrixResult``.
"""

from __future__ import annotations

from collections.abc import Callable

from si_v2.validation.gates import (
    GATE_REGISTRY,
    get_evaluator,
)
from si_v2.validation.models import (
    VALIDATION_MATRIX_VERSION,
    ValidationGateResult,
    ValidationGateSeverity,
    ValidationGateStatus,
    ValidationMatrixRequest,
    ValidationMatrixResult,
    compute_matrix_fingerprint,
)


def run_validation_matrix(
    request: ValidationMatrixRequest,
) -> ValidationMatrixResult:
    """Run all registered validation gates against the request.

    Evaluates gates in stable registry order. Short-circuits on the
    first HARD FAIL. Returns a deterministic ``ValidationMatrixResult``.

    Args:
        request: The typed validation matrix request.

    Returns:
        A typed ``ValidationMatrixResult`` with per-gate results.
    """
    results: list[ValidationGateResult] = []

    for gate_def in GATE_REGISTRY:
        evaluator: Callable[[ValidationMatrixRequest], ValidationGateResult] = get_evaluator(
            gate_def.gate_id
        )
        result = evaluator(request)
        results.append(result)

        # Short-circuit on first HARD FAIL
        if result.is_blocking:
            # Fill remaining gates as NOT_APPLICABLE
            for remaining in GATE_REGISTRY[len(results):]:
                results.append(
                    ValidationGateResult(
                        gate_id=remaining.gate_id,
                        status=ValidationGateStatus.NOT_APPLICABLE,
                        severity=remaining.severity,
                        reason="Skipped due to prior HARD FAIL",
                    )
                )
            break

    overall = _compute_overall_verdict(results)
    matrix_result = ValidationMatrixResult(
        matrix_version=VALIDATION_MATRIX_VERSION,
        policy_version=request.policy_version,
        episode_schema_version=request.episode_schema_version,
        overall_verdict=overall,
        gates=tuple(results),
        matrix_fingerprint="0" * 64,  # placeholder, updated below
    )
    # Compute deterministic fingerprint
    fp = compute_matrix_fingerprint(matrix_result)
    matrix_result.matrix_fingerprint = fp
    return matrix_result


def _compute_overall_verdict(
    results: list[ValidationGateResult],
) -> ValidationGateStatus:
    """Compute overall verdict from per-gate results.

    - Any HARD FAIL => FAIL
    - No HARD FAIL, any DEFER => DEFER
    - All PASS or NOT_APPLICABLE => PASS
    """
    has_fail = any(
        r.status == ValidationGateStatus.FAIL and r.severity == ValidationGateSeverity.HARD
        for r in results
    )
    has_defer = any(r.status == ValidationGateStatus.DEFER for r in results)

    if has_fail:
        return ValidationGateStatus.FAIL
    if has_defer:
        return ValidationGateStatus.DEFER
    return ValidationGateStatus.PASS


__all__ = [
    "run_validation_matrix",
]
