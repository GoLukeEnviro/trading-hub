"""Explicit action registry / argv builders for the hermes-root-executor.v1 protocol.

Action names are the canonical set already shipped in hermes_root.schema
(READONLY_ACTIONS / MUTATING_ACTIONS), the same set the production CLI
(hermes_root.__main__) uses. No generic shell execution: every action has its
own builder that validates its arguments and returns a subprocess argv list.
"""

from __future__ import annotations

from hermes_root.schema import ALL_ACTIONS, MUTATING_ACTIONS


class ActionError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def is_mutating(action: str) -> bool:
    return action in MUTATING_ACTIONS


def build_argv(action: str, argv: list[str]) -> list[str]:
    """Validate argv for the given action and return the subprocess argv to run."""
    if action not in ALL_ACTIONS:
        raise ActionError("unknown_action")

    if action == "executor_health":
        return []

    if action == "docker_ps":
        return ["docker", "ps", *argv]

    if action == "docker_inspect":
        _require_argv_len(argv, 1)
        return ["docker", "inspect", argv[0]]

    if action == "docker_compose_config":
        return ["docker", "compose", "config", *argv]

    if action == "systemctl_status":
        _require_argv_len(argv, 1)
        return ["systemctl", "status", argv[0]]

    if action == "docker_create":
        if len(argv) < 1:
            raise ActionError("invalid_argv_for_action")
        return ["docker", "create", *argv]

    if action == "docker_stop":
        _require_argv_len(argv, 1)
        return ["docker", "stop", argv[0]]

    if action == "docker_remove":
        _require_argv_len(argv, 1)
        return ["docker", "rm", argv[0]]

    if action == "systemctl_restart":
        _require_argv_len(argv, 1)
        return ["systemctl", "restart", argv[0]]

    raise ActionError("unknown_action")


def _require_argv_len(argv: list[str], expected: int) -> None:
    if len(argv) != expected:
        raise ActionError("invalid_argv_for_action")
