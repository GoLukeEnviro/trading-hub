"""Deterministic renderers for Validation Matrix output."""

from __future__ import annotations

import json

from si_v2.validation.models import (
    ValidationGateStatus,
    ValidationMatrixResult,
)


def render_validation_matrix_json(result: ValidationMatrixResult) -> str:
    """Deterministic JSON rendering (sorted keys)."""
    data = {
        "matrix_version": result.matrix_version,
        "policy_version": result.policy_version,
        "episode_schema_version": result.episode_schema_version,
        "overall_verdict": result.overall_verdict.value,
        "matrix_fingerprint": result.matrix_fingerprint,
        "gates": [
            {
                "gate_id": g.gate_id,
                "status": g.status.value,
                "severity": g.severity.value,
                "reason": g.reason,
                "evidence": [
                    {"key": e.key, "value": e.value, "detail": e.detail}
                    for e in g.evidence
                ],
            }
            for g in result.gates
        ],
    }
    return json.dumps(data, indent=2, sort_keys=True)


def render_validation_matrix_markdown(result: ValidationMatrixResult) -> str:
    """Deterministic Markdown rendering."""
    lines: list[str] = []
    lines.append("# Validation Gate Matrix Report")
    lines.append("")
    lines.append(f"- **Overall Verdict:** {result.overall_verdict.value}")
    lines.append(f"- **Matrix Version:** {result.matrix_version}")
    lines.append(f"- **Policy Version:** {result.policy_version}")
    lines.append(f"- **Episode Schema Version:** {result.episode_schema_version}")
    lines.append(f"- **Fingerprint:** `{result.matrix_fingerprint[:16]}...`")
    lines.append("")

    lines.append("## Gates")
    lines.append("")
    lines.append("| Gate | Status | Severity | Reason |")
    lines.append("|------|--------|----------|--------|")

    for gate in result.gates:
        icon = {
            ValidationGateStatus.PASS: "✅",
            ValidationGateStatus.FAIL: "❌",
            ValidationGateStatus.DEFER: "⚠️",
            ValidationGateStatus.NOT_APPLICABLE: "-",
        }.get(gate.status, "❓")
        lines.append(
            f"| {gate.gate_id} | {icon} {gate.status.value} "
            f"| {gate.severity.value} | {gate.reason} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Validation Gate Matrix — deterministic offline evaluation. "
        "PASS means ready for human review only; never execution authority.*"
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "render_validation_matrix_json",
    "render_validation_matrix_markdown",
]
