"""Explicit action registry / argv builders for the hermes-root-executor.v1 protocol.

Action names are the canonical set already shipped in hermes_root.schema
(READONLY_ACTIONS / MUTATING_ACTIONS), the same set the production CLI
(hermes_root.__main__) uses. No generic shell execution: every action has its
own builder that validates its arguments and returns a subprocess argv list.
"""

from __future__ import annotations

import os
import shlex

from hermes_root.schema import ALL_ACTIONS, MUTATING_ACTIONS

# Compose files may only be referenced under these host directory roots
# (resolved, symlink-following) — prevents docker_compose_config from being
# used to read or execute against arbitrary host paths.
ALLOWED_COMPOSE_STACK_ROOTS = ("/opt/stacks", "/opt/data/projects")
MAX_COMPOSE_FILES = 4

# R5A HermesTrader dry-run deployment (Issue #527)
# The canonical compose file and project are hardcoded — the client
# cannot select an arbitrary compose file, project, or profile.
R5A_CANONICAL_COMPOSE_FILE = (
    "/opt/data/projects/trading-hub/docker-compose.hermestrader-dryrun.yml"
)
R5A_CANONICAL_PROJECT = "hermestrader-dryrun"

# The five default (non-rebel-profile) services from the canonical compose.
# Client-supplied service names are validated against this allowlist only.
# freqai-rebel is explicitly excluded (profiles: ["rebel"]).
R5A_SERVICE_ALLOWLIST = frozenset({
    "freqtrade-freqforge",
    "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid",
    "freqtrade-webserver",
    "rainbow",
})

# Rebel service name — explicitly blocked even if present in the allowlist
R5A_REBEL_SERVICE = "freqai-rebel"

# Allowlisted filesystem roots for read-only fs_* actions
FS_READ_ROOTS = (
    "/opt/data/projects/trading-hub",
    "/opt/data/hermes",
    "/opt/data/state",
    "/opt/data/gate0-snapshot",
    "/etc/hermes-root-executor",
    "/run/hermes-root-executor",
    "/tmp",
)

# Allowlisted filesystem roots for mutating fs_* actions (write, mkdir, chmod, etc.)
FS_WRITE_ROOTS = (
    "/opt/data/projects/trading-hub",
    "/opt/data/hermes",
    "/opt/data/state",
    "/opt/data/gate0-snapshot",
    "/opt/data/backups",
    "/tmp",
)

# Allowlisted git repos for git_* actions
GIT_REPO_ROOTS = (
    "/opt/data/projects/trading-hub",
    "/opt/data/projects/ai4trade-bot",
)


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


def _validate_r5a_services(services: list[str]) -> None:
    """Validate that every service name is in the allowlist and not rebel.

    Raises ActionError with a specific reason on violation (invalid_service,
    rebel_blocked). Empty list = all five default services.
    """
    for svc in services:
        if svc == R5A_REBEL_SERVICE:
            raise ActionError("rebel_blocked")
        if svc not in R5A_SERVICE_ALLOWLIST:
            raise ActionError("invalid_service")


def _build_r5a_compose_cmd(subcommand: str, services: list[str]) -> list[str]:
    """Build the docker compose command for an R5A action.

    Validates the hardcoded canonical compose file on every call, builds
    the common prefix (file + project), appends subcommand and optional
    service filter. The caller is responsible for any subcommand-specific
    flags (e.g. -d for up, --no-start for build).
    """
    _validate_compose_file(R5A_CANONICAL_COMPOSE_FILE)
    _validate_r5a_services(services)
    cmd = [
        "docker", "compose",
        "-f", R5A_CANONICAL_COMPOSE_FILE,
        "-p", R5A_CANONICAL_PROJECT,
        subcommand,
    ]
    if services:
        cmd.extend(services)
    return cmd


def _validate_fs_read_path(path: str) -> str:
    """Validate a filesystem path for read-only access.

    Returns the resolved path. Raises ActionError on traversal or
    non-allowlisted path.
    """
    if not path.startswith("/"):
        raise ActionError("fs_path_not_absolute")
    if ".." in path.split("/"):
        raise ActionError("fs_path_traversal")
    resolved = os.path.realpath(path)
    if not any(
        resolved == root or resolved.startswith(root + "/")
        for root in FS_READ_ROOTS
    ):
        raise ActionError("fs_path_outside_allowlisted_root")
    return resolved


def _validate_fs_write_path(path: str) -> str:
    """Validate a filesystem path for write access.

    Returns the resolved path. Raises ActionError on traversal or
    non-allowlisted path.
    """
    if not path.startswith("/"):
        raise ActionError("fs_path_not_absolute")
    if ".." in path.split("/"):
        raise ActionError("fs_path_traversal")
    # For write paths, we resolve the parent directory to check the root
    parent = os.path.dirname(path)
    if not parent:
        parent = "/"
    resolved_parent = os.path.realpath(parent)
    if not any(
        resolved_parent == root or resolved_parent.startswith(root + "/")
        for root in FS_WRITE_ROOTS
    ):
        raise ActionError("fs_path_outside_allowlisted_root")
    return os.path.realpath(path) if os.path.exists(path) else path


def _validate_git_repo(path: str) -> str:
    """Validate a git repository path.

    Returns the resolved path. Raises ActionError on traversal or
    non-allowlisted repo root.
    """
    if not path.startswith("/"):
        raise ActionError("git_repo_not_absolute")
    if ".." in path.split("/"):
        raise ActionError("git_repo_traversal")
    resolved = os.path.realpath(path)
    if not any(
        resolved == root or resolved.startswith(root + "/")
        for root in GIT_REPO_ROOTS
    ):
        raise ActionError("git_repo_outside_allowlisted_root")
    return resolved


def is_mutating(action: str) -> bool:
    return action in MUTATING_ACTIONS


def build_argv(action: str, argv: list[str]) -> list[str]:
    """Validate argv for the given action and return the subprocess argv to run."""
    if action not in ALL_ACTIONS:
        raise ActionError("unknown_action")

    if action == "executor_health":
        return []

    # ------------------------------------------------------------------
    # Docker read-only
    # ------------------------------------------------------------------
    if action == "docker_ps":
        return ["docker", "ps", *argv]

    if action == "docker_inspect":
        _require_argv_len(argv, 1)
        return ["docker", "inspect", argv[0]]

    if action == "docker_logs":
        _require_argv_len(argv, 1)
        return ["docker", "logs", "--tail", "100", *argv[1:], argv[0]]

    if action == "docker_images":
        return ["docker", "images", *argv]

    if action == "docker_compose_config":
        if not (1 <= len(argv) <= MAX_COMPOSE_FILES):
            raise ActionError("invalid_argv_for_action")
        cmd = ["docker", "compose"]
        for raw_path in argv:
            cmd.extend(["-f", _validate_compose_file(raw_path)])
        cmd.extend(["config", "--quiet"])
        return cmd

    # ------------------------------------------------------------------
    # Docker mutating
    # ------------------------------------------------------------------
    if action == "docker_create":
        if len(argv) < 1:
            raise ActionError("invalid_argv_for_action")
        return ["docker", "create", *argv]

    if action == "docker_stop":
        _require_argv_len(argv, 1)
        return ["docker", "stop", argv[0]]

    if action == "docker_start":
        _require_argv_len(argv, 1)
        return ["docker", "start", argv[0]]

    if action == "docker_remove":
        _require_argv_len(argv, 1)
        return ["docker", "rm", argv[0]]

    if action == "docker_pull":
        _require_argv_len(argv, 1)
        return ["docker", "pull", argv[0]]

    if action == "docker_network_create":
        _require_argv_len(argv, 1)
        return ["docker", "network", "create", *argv]

    if action == "docker_network_remove":
        _require_argv_len(argv, 1)
        return ["docker", "network", "rm", *argv]

    if action == "docker_volume_create":
        _require_argv_len(argv, 1)
        return ["docker", "volume", "create", *argv]

    if action == "docker_volume_remove":
        _require_argv_len(argv, 1)
        return ["docker", "volume", "rm", *argv]

    if action == "docker_exec":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        return ["docker", "exec", *argv]

    # ------------------------------------------------------------------
    # systemd read-only
    # ------------------------------------------------------------------
    if action == "systemctl_status":
        _require_argv_len(argv, 1)
        return ["systemctl", "status", argv[0]]

    if action == "systemctl_is_active":
        _require_argv_len(argv, 1)
        return ["systemctl", "is-active", argv[0]]

    if action == "systemctl_is_enabled":
        _require_argv_len(argv, 1)
        return ["systemctl", "is-enabled", argv[0]]

    # ------------------------------------------------------------------
    # systemd mutating
    # ------------------------------------------------------------------
    if action == "systemctl_start":
        _require_argv_len(argv, 1)
        return ["systemctl", "start", argv[0]]

    if action == "systemctl_stop":
        _require_argv_len(argv, 1)
        return ["systemctl", "stop", argv[0]]

    if action == "systemctl_restart":
        _require_argv_len(argv, 1)
        return ["systemctl", "restart", argv[0]]

    if action == "systemctl_daemon_reload":
        if argv:
            raise ActionError("invalid_argv_for_action")
        return ["systemctl", "daemon-reload"]

    if action == "systemctl_enable":
        _require_argv_len(argv, 1)
        return ["systemctl", "enable", argv[0]]

    if action == "systemctl_disable":
        _require_argv_len(argv, 1)
        return ["systemctl", "disable", argv[0]]

    # ------------------------------------------------------------------
    # R5A compose fleet
    # ------------------------------------------------------------------
    if action == "r5a_compose_build":
        return _build_r5a_compose_cmd("build", argv)

    if action == "r5a_compose_up":
        return _build_r5a_compose_cmd("up", argv) + ["-d"]

    if action == "r5a_compose_stop":
        return _build_r5a_compose_cmd("stop", argv)

    if action == "r5a_compose_down":
        if "-v" in argv or "--volumes" in argv:
            raise ActionError("down_volumes_flag_blocked")
        return _build_r5a_compose_cmd("down", argv)

    # ------------------------------------------------------------------
    # Filesystem read-only
    # ------------------------------------------------------------------
    if action == "fs_stat":
        _require_argv_len(argv, 1)
        _validate_fs_read_path(argv[0])
        return ["stat", argv[0]]

    if action == "fs_ls":
        _require_argv_len(argv, 1)
        _validate_fs_read_path(argv[0])
        return ["ls", "-la", argv[0]]

    if action == "fs_read":
        _require_argv_len(argv, 1)
        _validate_fs_read_path(argv[0])
        return ["cat", argv[0]]

    if action == "fs_checksum":
        _require_argv_len(argv, 1)
        _validate_fs_read_path(argv[0])
        return ["sha256sum", argv[0]]

    # ------------------------------------------------------------------
    # Filesystem mutating
    # ------------------------------------------------------------------
    if action == "fs_write":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        path = argv[0]
        content = argv[1]
        _validate_fs_write_path(path)
        # Use python3 to write the file atomically — no shell=True,
        # content is a single argv element, the script is fixed.
        # repr() ensures proper escaping of the content string.
        script = (
            "import os,sys;"
            "p=sys.argv[1];c=sys.argv[2];"
            "os.makedirs(os.path.dirname(p),exist_ok=True);"
            "with open(p,'w')as f:f.write(c)"
        )
        return ["python3", "-c", script, path, content]

    if action == "fs_copy":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_read_path(argv[0])
        _validate_fs_write_path(argv[1])
        return ["cp", "-a", argv[0], argv[1]]

    if action == "fs_move":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_write_path(argv[0])
        _validate_fs_write_path(argv[1])
        return ["mv", argv[0], argv[1]]

    if action == "fs_remove":
        _require_argv_len(argv, 1)
        _validate_fs_write_path(argv[0])
        return ["rm", "-rf", argv[0]]

    if action == "fs_mkdir":
        _require_argv_len(argv, 1)
        _validate_fs_write_path(argv[0])
        return ["mkdir", "-p", argv[0]]

    if action == "fs_chmod":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_write_path(argv[1])
        return ["chmod", argv[0], argv[1]]

    if action == "fs_chown":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_write_path(argv[1])
        return ["chown", argv[0], argv[1]]

    if action == "fs_backup":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_read_path(argv[0])
        _validate_fs_write_path(argv[1])
        return ["cp", "-a", argv[0], argv[1]]

    if action == "fs_restore":
        if len(argv) != 2:
            raise ActionError("invalid_argv_for_action")
        _validate_fs_read_path(argv[0])
        _validate_fs_write_path(argv[1])
        return ["cp", "-a", argv[0], argv[1]]

    # ------------------------------------------------------------------
    # Git read-only
    # ------------------------------------------------------------------
    if action == "git_status":
        _require_argv_len(argv, 1)
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "status"]

    if action == "git_branch":
        _require_argv_len(argv, 1)
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "branch", "-a"]

    if action == "git_log":
        if len(argv) < 1:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        n = argv[1] if len(argv) > 1 else "10"
        return ["git", "-C", argv[0], "log", "--oneline", f"-{n}"]

    if action == "git_tag_list":
        _require_argv_len(argv, 1)
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "tag"]

    # ------------------------------------------------------------------
    # Git mutating
    # ------------------------------------------------------------------
    if action == "git_clone":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        return ["git", "clone", argv[0], argv[1]]

    if action == "git_fetch":
        _require_argv_len(argv, 1)
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "fetch", "--all"]

    if action == "git_checkout":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "checkout", argv[1]]

    if action == "git_merge":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "merge", argv[1]]

    if action == "git_tag_create":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "tag", argv[1]]

    if action == "git_tag_delete":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "tag", "-d", argv[1]]

    if action == "git_clean":
        if len(argv) < 1:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "clean", "-fd"]

    if action == "git_reset":
        if len(argv) < 2:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        return ["git", "-C", argv[0], "reset", "--hard", argv[1]]

    if action == "git_push":
        if len(argv) < 1:
            raise ActionError("invalid_argv_for_action")
        _validate_git_repo(argv[0])
        cmd = ["git", "-C", argv[0], "push"]
        if len(argv) > 1:
            cmd.append(argv[1])
        if len(argv) > 2:
            cmd.append(argv[2])
        return cmd

    raise ActionError("unknown_action")


def _require_argv_len(argv: list[str], expected: int) -> None:
    if len(argv) != expected:
        raise ActionError("invalid_argv_for_action")
