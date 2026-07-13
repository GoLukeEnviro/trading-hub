"""Hermes Root Executor CLI — production entry point.

Usage:
    python -m hermes_root <action> [options]
    hermes-root <action> [options]

Read-only actions (A0/A1):
    executor_health
    docker_ps
    docker_inspect --container <name>
    systemctl_status --unit <name>
    docker_compose_config --file <path>

Mutating actions (A2, requires --approval):
    docker_create --image <img> --name <name> [--cmd <cmd>]
    docker_stop --container <name>
    docker_remove --container <name>
    systemctl_restart --unit <name>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import Optional

from hermes_root import (
    DEFAULT_SOCKET_PATH,
    DEFAULT_TIMEOUT,
    MUTATING_ACTIONS,
    READONLY_ACTIONS,
    ExecutorRequest,
    send_request,
    validate_request,
    ValidationError,
    ExecutorClientError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-root",
        description="Hermes Root Executor — bounded runtime control client",
    )
    parser.add_argument(
        "action",
        help="Action to execute (e.g., executor_health, docker_ps, docker_create)",
    )
    parser.add_argument(
        "--socket",
        default=os.environ.get(
            "HERMES_ROOT_SOCKET", DEFAULT_SOCKET_PATH
        ),
        help=f"Path to executor socket (default: {DEFAULT_SOCKET_PATH})",
    )
    parser.add_argument(
        "--correlation-id",
        default=None,
        help="Correlation ID for audit tracing (auto-generated if omitted)",
    )
    parser.add_argument(
        "--issue", type=int, default=531,
        help="Issue number (default: 531)",
    )
    parser.add_argument(
        "--task", default="H3B",
        help="Task name (default: H3B)",
    )
    parser.add_argument(
        "--class", dest="execution_class", default="A1",
        choices=["A0", "A1", "A2", "A3"],
        help="Execution class (default: A1)",
    )
    parser.add_argument(
        "--resource-key", default=None,
        help="Resource key for locking (auto-derived from action if omitted)",
    )
    parser.add_argument(
        "--cwd", default="/",
        help="Working directory for the command (default: /)",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Command timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--approval", dest="approval_reference", default=None,
        help="Approval reference (required for A2 mutating actions)",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output raw JSON response",
    )

    # Action-specific arguments
    parser.add_argument(
        "--container", default=None,
        help="Container name (for docker_inspect, docker_stop, docker_remove)",
    )
    parser.add_argument(
        "--unit", default=None,
        help="systemd unit name (for systemctl_status, systemctl_restart)",
    )
    parser.add_argument(
        "--file", default=None,
        help="Compose file path (for docker_compose_config)",
    )
    parser.add_argument(
        "--image", default=None,
        help="Docker image (for docker_create)",
    )
    parser.add_argument(
        "--name", default=None,
        help="Container name (for docker_create)",
    )
    parser.add_argument(
        "--cmd", default=None,
        help="Command to run in container (for docker_create)",
    )

    return parser


def _build_argv(action: str, args: argparse.Namespace) -> list[str]:
    """Build the resource-specific argv *extras* for the given action.

    The daemon's action registry (hermes_root.actions.build_argv) owns the
    fixed base command for every action and appends these extras itself
    (e.g. docker_ps -> ["docker", "ps", *extras]). The client must send
    only the extras, never the base command tokens again, or the daemon
    ends up running a duplicated/invalid command (e.g. "docker ps docker
    ps") or rejecting the request outright (actions requiring exactly one
    extra argument, like docker_inspect, reject anything longer).
    """
    if action == "executor_health":
        return []
    elif action == "docker_ps":
        return []
    elif action == "docker_inspect":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_inspect")
        return [container]
    elif action == "systemctl_status":
        unit = args.unit
        if not unit:
            raise ValueError("--unit is required for systemctl_status")
        return [unit]
    elif action == "docker_compose_config":
        compose_file = args.file
        if not compose_file:
            raise ValueError("--file is required for docker_compose_config")
        return [compose_file]
    elif action == "docker_create":
        image = args.image
        name = args.name
        if not image:
            raise ValueError("--image is required for docker_create")
        if not name:
            raise ValueError("--name is required for docker_create")
        extras = ["--name", name, image]
        if args.cmd:
            extras.append(args.cmd)
        return extras
    elif action == "docker_stop":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_stop")
        return [container]
    elif action == "docker_remove":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_remove")
        return [container]
    elif action == "systemctl_restart":
        unit = args.unit
        if not unit:
            raise ValueError("--unit is required for systemctl_restart")
        return [unit]
    else:
        raise ValueError(f"Unknown action: {action}")


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point. Returns exit code (0 = success, non-zero = error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    action = args.action

    # Determine execution class from action type
    if action in MUTATING_ACTIONS:
        if args.execution_class == "A1":
            args.execution_class = "A2"
    elif action in READONLY_ACTIONS:
        if args.execution_class not in ("A0", "A1"):
            args.execution_class = "A1"

    # Build argv
    try:
        argv_list = _build_argv(action, args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Build request
    request_id = "h3b-" + uuid.uuid4().hex[:12]
    correlation_id = args.correlation_id or ("h3b-" + uuid.uuid4().hex[:12])
    resource_key = args.resource_key or f"h3b:{action}"

    request = ExecutorRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        issue_number=args.issue,
        task_name=args.task,
        execution_class=args.execution_class,
        resource_key=resource_key,
        action=action,
        argv=argv_list,
        cwd=args.cwd,
        timeout=args.timeout,
        approval_reference=args.approval_reference,
    )

    # Validate
    try:
        validate_request(request)
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        return 2

    # Send
    try:
        response = send_request(args.socket, request)
    except ExecutorClientError as e:
        print(f"Executor error: {e}", file=sys.stderr)
        return 3

    # Output
    if args.json_output:
        print(json.dumps({
            "schema_version": response.schema_version,
            "request_id": response.request_id,
            "correlation_id": response.correlation_id,
            "decision": response.decision,
            "reason": response.reason,
            "returncode": response.returncode,
            "stdout": response.stdout,
            "stderr": response.stderr,
            "resource_key": response.resource_key,
            "action": response.action,
            "execution_class": response.execution_class,
            "audit_id": response.audit_id,
            "duration_ms": response.duration_ms,
        }, indent=2))
    else:
        print(f"decision: {response.decision}")
        print(f"reason: {response.reason}")
        if response.action:
            print(f"action: {response.action}")
        if response.execution_class:
            print(f"execution_class: {response.execution_class}")
        if response.returncode is not None:
            print(f"returncode: {response.returncode}")
        if response.stdout:
            print(f"stdout: {response.stdout}")
        if response.stderr:
            print(f"stderr: {response.stderr}")
        if response.audit_id:
            print(f"audit_id: {response.audit_id}")
        print(f"correlation_id: {response.correlation_id}")

    if response.is_allowed:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
