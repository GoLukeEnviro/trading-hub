"""SEC-1 regression tests for the legacy read-only compatibility firewall."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from hermes_root import legacy
from hermes_root.daemon import RootExecutorDaemon


@pytest.fixture
def daemon(tmp_path):
    return RootExecutorDaemon(
        socket_path=str(tmp_path / "executor.sock"),
        lock_dir=str(tmp_path / "locks"),
        kill_switch_path=str(tmp_path / "DISABLED"),
        allowed_uids=frozenset({os.getuid()}),
        audit_path=str(tmp_path / "audit.jsonl"),
        repository_commit="test-sha",
    )


def _send(daemon, category: str, args: list[str]):
    payload = {"category": category, "args": args, "resource_key": "sec1:test"}
    return daemon.handle_payload(json.dumps(payload).encode(), peer_pid=123, peer_uid=os.getuid())


@pytest.mark.parametrize(
    "args,expected",
    [
        (["ps"], ("docker", "ps")),
        (["ps", "-a", "--no-trunc"], ("docker", "ps", "-a", "--no-trunc")),
        (["ps", "--format", "{{.Names}}"], ("docker", "ps", "--format", "{{.Names}}")),
        (["ps", "--filter=status=running"], ("docker", "ps", "--filter=status=running")),
    ],
)
def test_docker_ps_read_only_allowlist(args, expected):
    assert legacy.build_legacy_command("docker", args).argv == expected


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--privileged", "-v", "/:/host", "alpine"],
        ["create", "--privileged", "alpine"],
        ["exec", "container", "sh"],
        ["stop", "container"],
        ["rm", "-f", "container"],
        ["compose", "down"],
        ["inspect", "container"],
        ["--help"],
        ["ps", "--unknown"],
        ["ps", "--format", "-injected"],
    ],
)
def test_docker_mutation_and_unknown_arguments_blocked(args):
    with pytest.raises(legacy.LegacyCommandError):
        legacy.build_legacy_command("docker", args)


@pytest.mark.parametrize("verb", ["status", "is-active", "is-enabled"])
def test_systemd_read_only_allowlist(verb):
    command = legacy.build_legacy_command("systemd", [verb, "docker.service"])
    assert command.argv == ("systemctl", verb, "docker.service")


@pytest.mark.parametrize(
    "args",
    [
        ["restart", "docker.service"],
        ["start", "docker.service"],
        ["stop", "docker.service"],
        ["enable", "docker.service"],
        ["disable", "docker.service"],
        ["status", "ssh.service"],
        ["status", "--all"],
        ["status", "docker.service", "extra"],
    ],
)
def test_systemd_mutation_unknown_unit_and_injection_blocked(args):
    with pytest.raises(legacy.LegacyCommandError):
        legacy.build_legacy_command("systemd", args)


def test_filesystem_read_only_paths_allowed():
    assert legacy.build_legacy_command("fs_stat", ["/etc/hostname"]).argv == (
        "stat",
        "/etc/hostname",
    )
    assert legacy.build_legacy_command(
        "fs_stat", ["-c", "%n", "/opt/data/projects/trading-hub/AGENTS.md"]
    ).argv == ("stat", "-c", "%n", "/opt/data/projects/trading-hub/AGENTS.md")
    assert legacy.build_legacy_command("fs_ls", ["/tmp"]).argv == ("ls", "-la", "/tmp")


@pytest.mark.parametrize(
    "category,args",
    [
        ("fs_stat", ["/etc/shadow"]),
        ("fs_stat", ["/opt/data/projects/trading-hub/../../secrets"]),
        ("fs_stat", ["--help"]),
        ("fs_ls", ["/root"]),
        ("fs_ls", ["-R"]),
        ("fs_ls", ["/tmp", "/etc"]),
    ],
)
def test_filesystem_escape_traversal_and_option_injection_blocked(category, args):
    with pytest.raises(legacy.LegacyCommandError):
        legacy.build_legacy_command(category, args)


def test_blocked_legacy_request_never_invokes_subprocess_and_is_safely_audited(
    daemon, monkeypatch
):
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess.run must not be reached")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    secret_canary = "TOKEN=this-must-not-enter-audit"
    response = _send(daemon, "docker", ["run", secret_canary])

    assert response == {"decision": "BLOCKED", "reason": "legacy_docker_subcommand_blocked"}
    assert called is False
    with open(daemon.audit_path) as audit_file:
        audit_text = audit_file.read()
    assert secret_canary not in audit_text
    entry = json.loads(audit_text)
    assert entry["legacy_classification"] == "legacy:docker:blocked"


def test_allowed_legacy_request_uses_server_built_argv_and_classification(daemon, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", fake_run)
    response = _send(daemon, "systemd", ["status", "hermes-root-executor.service"])

    assert response["decision"] == "ALLOWED"
    assert captured["argv"] == ["systemctl", "status", "hermes-root-executor.service"]
    with open(daemon.audit_path) as audit_file:
        entries = [json.loads(line) for line in audit_file if line.strip()]
    assert [entry["event"] for entry in entries] == ["intent", "completion"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]
    assert {entry["legacy_classification"] for entry in entries} == {
        "legacy:systemd:status:read_only"
    }
