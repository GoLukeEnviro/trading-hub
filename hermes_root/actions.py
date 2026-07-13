"""Explicit action registry / argv builders for the hermes-root-executor.v1 protocol.

Action names are the canonical set already shipped in hermes_root.schema
(READONLY_ACTIONS / MUTATING_ACTIONS), the same set the production CLI
(hermes_root.__main__) uses. No generic shell execution: every action has its
own builder that validates its arguments and returns a subprocess argv list.
"""

from __future__ import annotations

import os

from hermes_root.schema import ALL_ACTIONS, MUTATING_ACTIONS

# Compose files may only be referenced under these host directory roots
# (resolved, symlink-following) — prevents docker_compose_config from being
# used to read or execute against arbitrary host paths.
ALLOWED_COMPOSE_STACK_ROOTS = ("/opt/stacks",)
MAX_COMPOSE_FILES = 4


class ActionError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _validate_compose_file(path: str) -> str:
    """Validate a single docker-compose file path.

    Requires: absolute path, no ".." components, resolves (following
    symlinks) to an existing regular file inside an allowlisted stack root.
    Returns the resolved, validated path — never trusts the raw input past
    this point. Raises ActionError with a specific reason on any violation.
    """
    if not path.startswith("/"):
        raise ActionError("compose_file_not_absolute")
    if ".." in path.split("/"):
        raise ActionError("compose_file_path_traversal")

    resolved = os.path.realpath(path)

    if not any(
        resolved == root or resolved.startswith(root + "/")
        for root in ALLOWED_COMPOSE_STACK_ROOTS
    ):
        raise ActionError("compose_file_outside_allowlisted_root")

    if not os.path.isfile(resolved):
        raise ActionError("compose_file_not_found")

    return resolved


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
        # docker compose's -f/--file flag is a top-level flag and must
        # precede the "config" subcommand (docker compose -f <path> config);
        # it is not accepted after the subcommand, and repeats to layer
        # multiple compose files (base + override). Each file is validated
        # and resolved independently — we build the -f flags ourselves
        # rather than trusting client-supplied flag tokens.
        #
        # --quiet: this action validates a compose configuration, it does
        # not export it. "config" without --quiet renders the fully
        # resolved document, including plaintext environment values (e.g.
        # secrets injected via the compose file's `environment:` section) —
        # data the executor has no business reading out at all, redaction
        # notwithstanding. --quiet performs the same parse/merge/validate
        # and reports errors via a non-zero exit code, but prints nothing
        # on success.
        if not (1 <= len(argv) <= MAX_COMPOSE_FILES):
            raise ActionError("invalid_argv_for_action")
        cmd = ["docker", "compose"]
        for raw_path in argv:
            cmd.extend(["-f", _validate_compose_file(raw_path)])
        cmd.extend(["config", "--quiet"])
        return cmd

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
