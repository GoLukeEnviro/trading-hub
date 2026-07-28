"""Hermes Root Executor CLI — production entry point.

Usage:
    python -m hermes_root <action> [options]
    hermes-root <action> [options]

Read-only actions (A0/A1):
    executor_health
    docker_ps [--all] [--format <fmt>]
    docker_inspect --container <name>
    docker_logs --container <name> [--tail <n>]
    docker_images [--all]
    systemctl_status --unit <name>
    systemctl_is_active --unit <name>
    systemctl_is_enabled --unit <name>
    docker_compose_config --file <path> [--file <path2>]
    fs_stat --path <path>
    fs_ls --path <path>
    fs_read --path <path>
    fs_checksum --path <path>
    git_status --repo <path>
    git_branch --repo <path>
    git_log --repo <path> [--n <count>]
    git_tag_list --repo <path>

Mutating actions (A2, requires --approval):
    docker_create --image <img> --name <name> [--cmd <cmd>]
    docker_stop --container <name>
    docker_start --container <name>
    docker_remove --container <name>
    docker_pull --image <img>
    docker_network_create --name <name> [--driver <driver>]
    docker_network_remove --name <name>
    docker_volume_create --name <name>
    docker_volume_remove --name <name>
    docker_exec --container <name> --cmd <cmd>
    systemctl_start --unit <name>
    systemctl_stop --unit <name>
    systemctl_restart --unit <name>
    systemctl_daemon_reload
    systemctl_enable --unit <name>
    systemctl_disable --unit <name>
    fs_write --path <path> --content <content>
    fs_copy --source <path> --dest <path>
    fs_move --source <path> --dest <path>
    fs_remove --path <path>
    fs_mkdir --path <path>
    fs_chmod --mode <mode> --path <path>
    fs_chown --owner <owner> --path <path>
    fs_backup --source <path> --dest <path>
    fs_restore --source <path> --dest <path>
    git_clone --url <url> --dest <path>
    git_fetch --repo <path>
    git_checkout --repo <path> --ref <ref>
    git_merge --repo <path> --ref <ref>
    git_tag_create --repo <path> --tag <name>
    git_tag_delete --repo <path> --tag <name>
    git_clean --repo <path>
    git_reset --repo <path> --ref <ref>
    git_push --repo <path> [--remote <remote>] [--branch <branch>]

R5A compose fleet actions (A2, requires --approval):
    r5a_compose_build [--service <svc>]...
    r5a_compose_up [--service <svc>]...
    r5a_compose_stop [--service <svc>]...
    r5a_compose_down [--service <svc>]...
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
    parser.add_argument("--container", default=None, help="Container name")
    parser.add_argument("--unit", default=None, help="systemd unit name")
    parser.add_argument("--file", action="append", default=None,
                        help="Compose file path (repeat for multiple, max 4)")
    parser.add_argument("--image", default=None, help="Docker image")
    parser.add_argument("--name", default=None, help="Name (container/network/volume)")
    parser.add_argument("--cmd", default=None, help="Command to run")
    parser.add_argument("--service", action="append", default=None,
                        help="Compose service name (repeat for multiple)")
    parser.add_argument("--path", default=None, help="Filesystem path")
    parser.add_argument("--content", default=None, help="File content (for fs_write)")
    parser.add_argument("--source", default=None, help="Source path")
    parser.add_argument("--dest", default=None, help="Destination path")
    parser.add_argument("--mode", default=None, help="File mode (for fs_chmod)")
    parser.add_argument("--owner", default=None, help="Owner (for fs_chown)")
    parser.add_argument("--repo", default=None, help="Git repository path")
    parser.add_argument("--url", default=None, help="Git remote URL")
    parser.add_argument("--ref", default=None, help="Git ref (branch/tag/commit)")
    parser.add_argument("--tag", default=None, help="Git tag name")
    parser.add_argument("--remote", default=None, help="Git remote name")
    parser.add_argument("--branch", default=None, help="Git branch name")
    parser.add_argument("--tail", type=int, default=100, help="Log tail lines")
    parser.add_argument("--driver", default=None, help="Network driver")
    parser.add_argument("--n", type=int, default=10, help="Git log count")
    parser.add_argument("--all", dest="all_flag", action="store_true",
                        help="Show all (containers/images)")
    parser.add_argument("--format", default=None, help="Output format (for docker_ps)")

    return parser


def _build_argv(action: str, args: argparse.Namespace) -> list[str]:
    """Build the resource-specific argv *extras* for the given action.

    The daemon's action registry (hermes_root.actions.build_argv) owns the
    fixed base command for every action and appends these extras itself.
    The client must send only the extras, never the base command tokens again.
    """
    if action == "executor_health":
        return []

    # Docker read-only
    if action == "docker_ps":
        extras = []
        if args.all_flag:
            extras.append("-a")
        if args.format:
            extras.extend(["--format", args.format])
        return extras

    if action == "docker_inspect":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_inspect")
        return [container]

    if action == "docker_logs":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_logs")
        return [container]

    if action == "docker_images":
        extras = []
        if args.all_flag:
            extras.append("--all")
        return extras

    if action == "docker_compose_config":
        compose_files = args.file
        if not compose_files:
            raise ValueError("--file is required for docker_compose_config")
        if len(compose_files) > 4:
            raise ValueError("at most 4 --file arguments are allowed")
        return list(compose_files)

    # Docker mutating
    if action == "docker_create":
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

    if action == "docker_stop":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_stop")
        return [container]

    if action == "docker_start":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_start")
        return [container]

    if action == "docker_remove":
        container = args.container
        if not container:
            raise ValueError("--container is required for docker_remove")
        return [container]

    if action == "docker_pull":
        image = args.image
        if not image:
            raise ValueError("--image is required for docker_pull")
        return [image]

    if action == "docker_network_create":
        name = args.name
        if not name:
            raise ValueError("--name is required for docker_network_create")
        extras = []
        if args.driver:
            extras.extend(["--driver", args.driver])
        extras.append(name)
        return extras

    if action == "docker_network_remove":
        name = args.name
        if not name:
            raise ValueError("--name is required for docker_network_remove")
        return [name]

    if action == "docker_volume_create":
        name = args.name
        if not name:
            raise ValueError("--name is required for docker_volume_create")
        return [name]

    if action == "docker_volume_remove":
        name = args.name
        if not name:
            raise ValueError("--name is required for docker_volume_remove")
        return [name]

    if action == "docker_exec":
        container = args.container
        cmd = args.cmd
        if not container:
            raise ValueError("--container is required for docker_exec")
        if not cmd:
            raise ValueError("--cmd is required for docker_exec")
        return [container, *cmd.split()]

    # systemd read-only
    if action in ("systemctl_status", "systemctl_is_active", "systemctl_is_enabled"):
        unit = args.unit
        if not unit:
            raise ValueError(f"--unit is required for {action}")
        return [unit]

    # systemd mutating
    if action in ("systemctl_start", "systemctl_stop", "systemctl_restart",
                  "systemctl_enable", "systemctl_disable"):
        unit = args.unit
        if not unit:
            raise ValueError(f"--unit is required for {action}")
        return [unit]

    if action == "systemctl_daemon_reload":
        return []

    # R5A compose
    if action in ("r5a_compose_build", "r5a_compose_up",
                  "r5a_compose_stop", "r5a_compose_down"):
        return args.service if args.service else []

    # Filesystem read-only
    if action in ("fs_stat", "fs_ls", "fs_read", "fs_checksum"):
        path = args.path
        if not path:
            raise ValueError(f"--path is required for {action}")
        return [path]

    # Filesystem mutating
    if action == "fs_write":
        path = args.path
        content = args.content
        if not path:
            raise ValueError("--path is required for fs_write")
        if content is None:
            raise ValueError("--content is required for fs_write")
        return [path, content]

    if action in ("fs_copy", "fs_move", "fs_backup", "fs_restore"):
        source = args.source
        dest = args.dest
        if not source:
            raise ValueError(f"--source is required for {action}")
        if not dest:
            raise ValueError(f"--dest is required for {action}")
        return [source, dest]

    if action == "fs_remove":
        path = args.path
        if not path:
            raise ValueError("--path is required for fs_remove")
        return [path]

    if action == "fs_mkdir":
        path = args.path
        if not path:
            raise ValueError("--path is required for fs_mkdir")
        return [path]

    if action == "fs_chmod":
        mode = args.mode
        path = args.path
        if not mode:
            raise ValueError("--mode is required for fs_chmod")
        if not path:
            raise ValueError("--path is required for fs_chmod")
        return [mode, path]

    if action == "fs_chown":
        owner = args.owner
        path = args.path
        if not owner:
            raise ValueError("--owner is required for fs_chown")
        if not path:
            raise ValueError("--path is required for fs_chown")
        return [owner, path]

    # Git read-only
    if action in ("git_status", "git_branch", "git_tag_list"):
        repo = args.repo
        if not repo:
            raise ValueError(f"--repo is required for {action}")
        return [repo]

    if action == "git_log":
        repo = args.repo
        if not repo:
            raise ValueError("--repo is required for git_log")
        return [repo, str(args.n)]

    # Git mutating
    if action == "git_clone":
        url = args.url
        dest = args.dest
        if not url:
            raise ValueError("--url is required for git_clone")
        if not dest:
            raise ValueError("--dest is required for git_clone")
        return [url, dest]

    if action in ("git_fetch", "git_clean"):
        repo = args.repo
        if not repo:
            raise ValueError(f"--repo is required for {action}")
        return [repo]

    if action in ("git_checkout", "git_merge", "git_reset"):
        repo = args.repo
        ref = args.ref
        if not repo:
            raise ValueError(f"--repo is required for {action}")
        if not ref:
            raise ValueError(f"--ref is required for {action}")
        return [repo, ref]

    if action in ("git_tag_create", "git_tag_delete"):
        repo = args.repo
        tag = args.tag
        if not repo:
            raise ValueError(f"--repo is required for {action}")
        if not tag:
            raise ValueError(f"--tag is required for {action}")
        return [repo, tag]

    if action == "git_push":
        repo = args.repo
        if not repo:
            raise ValueError("--repo is required for git_push")
        extras = [repo]
        if args.remote:
            extras.append(args.remote)
        if args.branch:
            extras.append(args.branch)
        return extras

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
