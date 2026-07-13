"""Execution-class gates (A0-A3) for the root-executor daemon.

Server-side and authoritative: client-side validation (hermes_root.validate) is
defense-in-depth only and never a substitute for this check.
"""

from __future__ import annotations

APPROVED_MARKER = "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION"
APPROVED_R5A_MARKER = "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT"
APPROVED_MARKERS = frozenset({APPROVED_MARKER, APPROVED_R5A_MARKER})
VALID_CLASSES = frozenset({"A0", "A1", "A2", "A3"})


def evaluate_gate(
    *,
    execution_class: str,
    is_mutating: bool,
    approval_reference: str | None,
    issue_number: int | None,
    task_name: str | None,
    kill_switch_active: bool,
) -> tuple[bool, str | None]:
    """Return (allowed, reason_if_blocked)."""
    if kill_switch_active:
        return False, "emergency_disable_switch_active"

    if execution_class not in VALID_CLASSES:
        return False, "invalid_execution_class"

    if execution_class == "A3":
        return False, "a3_never_authorized"

    if not is_mutating:
        return True, None

    if execution_class in ("A0", "A1"):
        return False, "mutation_not_authorized_for_class"

    # A2 mutating: allowlisted action (checked upstream by actions.build_argv),
    # exact approval marker (one of the APPROVED_MARKERS set), and
    # issue/task context required.
    if approval_reference not in APPROVED_MARKERS:
        return False, "approval_reference_missing_or_invalid"
    if issue_number is None:
        return False, "issue_context_missing"
    if not task_name:
        return False, "task_context_missing"
    return True, None
