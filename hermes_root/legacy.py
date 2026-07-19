"""Fail-closed compatibility firewall for the legacy executor protocol.

The legacy wire format is still consumed by deployed Hermes clients, but it
must no longer be a generic root command transport.  This module converts the
small supported read-only subset into server-owned argv and rejects everything
else before :func:`subprocess.run` is reached.

No raw client argv is returned for audit.  Callers receive only a fixed,
non-secret classification string.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MAX_LEGACY_ARGS = 16
MAX_LEGACY_ARG_LENGTH = 512

_DOCKER_BOOL_FLAGS = frozenset({"-a", "--all", "--no-trunc", "-q", "--quiet", "-s", "--size"})
_DOCKER_VALUE_FLAGS = frozenset({"--filter", "--format"})
_SYSTEMD_READ_VERBS = frozenset({"status", "is-active", "is-enabled"})
_SYSTEMD_ALLOWED_UNITS = frozenset(
    {
        "docker",
        "docker.service",
        "hermes-root-executor",
        "hermes-root-executor.service",
    }
)
_FILESYSTEM_ROOTS = (
    "/opt/data/projects/trading-hub",
    "/opt/data/hermes/audit",
    "/opt/data/state/repo-writer",
    "/run/hermes-root-executor",
    "/tmp",
)
_FILESYSTEM_EXACT_PATHS = frozenset({"/etc/hostname"})


@dataclass(frozen=True)
class LegacyCommand:
    argv: tuple[str, ...]
    audit_classification: str


class LegacyCommandError(Exception):
    """A legacy request is outside the bounded read-only compatibility set."""

    def __init__(self, reason: str, audit_classification: str):
        self.reason = reason
        self.audit_classification = audit_classification
        super().__init__(reason)


def build_legacy_command(category: str, args: list[str]) -> LegacyCommand:
    """Validate a legacy request and build a server-owned read-only argv."""
    _validate_common(args, category)
    if category == "docker":
        return _build_docker(args)
    if category == "systemd":
        return _build_systemd(args)
    if category == "fs_stat":
        return _build_fs_stat(args)
    if category == "fs_ls":
        return _build_fs_ls(args)
    raise LegacyCommandError("unknown_category", "legacy:unknown:blocked")


def _validate_common(args: list[str], category: str) -> None:
    classification = f"legacy:{category}:invalid:blocked"
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise LegacyCommandError("invalid_args", classification)
    if len(args) > MAX_LEGACY_ARGS:
        raise LegacyCommandError("legacy_too_many_args", classification)
    for arg in args:
        if len(arg) > MAX_LEGACY_ARG_LENGTH or _has_control_character(arg):
            raise LegacyCommandError("legacy_argument_blocked", classification)


def _build_docker(args: list[str]) -> LegacyCommand:
    classification = "legacy:docker:ps:read_only"
    if not args or args[0] != "ps":
        raise LegacyCommandError("legacy_docker_subcommand_blocked", "legacy:docker:blocked")

    result = ["docker", "ps"]
    index = 1
    while index < len(args):
        token = args[index]
        if token in _DOCKER_BOOL_FLAGS:
            result.append(token)
            index += 1
            continue
        if token in _DOCKER_VALUE_FLAGS:
            if index + 1 >= len(args) or args[index + 1].startswith("-"):
                raise LegacyCommandError("legacy_docker_argument_blocked", classification)
            result.extend((token, args[index + 1]))
            index += 2
            continue
        matched = next((flag for flag in _DOCKER_VALUE_FLAGS if token.startswith(flag + "=")), None)
        if matched and token != matched + "=":
            result.append(token)
            index += 1
            continue
        raise LegacyCommandError("legacy_docker_argument_blocked", classification)
    return LegacyCommand(tuple(result), classification)


def _build_systemd(args: list[str]) -> LegacyCommand:
    if len(args) != 2 or args[0] not in _SYSTEMD_READ_VERBS:
        raise LegacyCommandError("legacy_systemd_command_blocked", "legacy:systemd:blocked")
    verb, unit = args
    if unit not in _SYSTEMD_ALLOWED_UNITS:
        raise LegacyCommandError("legacy_systemd_unit_blocked", f"legacy:systemd:{verb}:blocked")
    return LegacyCommand(
        ("systemctl", verb, unit),
        f"legacy:systemd:{verb}:read_only",
    )


def _build_fs_stat(args: list[str]) -> LegacyCommand:
    classification = "legacy:fs_stat:read_only"
    if len(args) == 1:
        path = args[0]
        result = ["stat", path]
    elif len(args) == 3 and args[0] in {"-c", "--format"}:
        if not args[1] or args[1].startswith("-") or _has_control_character(args[1]):
            raise LegacyCommandError("legacy_stat_format_blocked", classification)
        path = args[2]
        result = ["stat", "-c", args[1], path]
    else:
        raise LegacyCommandError("legacy_stat_argument_blocked", classification)
    _validate_filesystem_path(path, classification)
    return LegacyCommand(tuple(result), classification)


def _build_fs_ls(args: list[str]) -> LegacyCommand:
    classification = "legacy:fs_ls:read_only"
    if len(args) != 1 or args[0].startswith("-"):
        raise LegacyCommandError("legacy_ls_argument_blocked", classification)
    path = args[0]
    _validate_filesystem_path(path, classification)
    return LegacyCommand(("ls", "-la", path), classification)


def _validate_filesystem_path(path: str, classification: str) -> None:
    if not path.startswith("/") or _has_control_character(path):
        raise LegacyCommandError("legacy_path_blocked", classification)
    resolved = os.path.realpath(path)
    if resolved in _FILESYSTEM_EXACT_PATHS:
        return
    if any(resolved == root or resolved.startswith(root + "/") for root in _FILESYSTEM_ROOTS):
        return
    raise LegacyCommandError("legacy_path_blocked", classification)


def _has_control_character(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
