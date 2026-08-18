"""Tests for the extended root-executor action registry (systemd, Docker, Filesystem, Git).

Covers all new actions added in the Core Action Extension PR.
Tests are structured by domain: systemd, Docker, Filesystem, Git.
Each test verifies argv construction, validation, and error handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid

import pytest

from hermes_root import actions
from hermes_root.actions import ActionError, build_argv
from hermes_root.daemon import RootExecutorDaemon
from hermes_root.schema import SCHEMA_VERSION

APPROVED = "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION"


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


def _v1_payload(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "issue_number": 531,
        "task_name": "H3B",
        "execution_class": "A0",
        "resource_key": "test:resource",
        "action": "docker_ps",
        "argv": [],
        "cwd": "/tmp",
        "timeout": 30,
        "approval_reference": None,
    }
    payload.update(overrides)
    return payload


def _send(daemon, payload_dict, uid=None):
    raw = json.dumps(payload_dict).encode()
    return daemon.handle_payload(raw, peer_pid=1234, peer_uid=uid if uid is not None else os.getuid())


def _fake_ok_run(argv, **kw):
    return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


# ============================================================================
# systemd — extended actions
# ============================================================================

class TestSystemdActions:
    """systemctl start, stop, daemon-reload, enable, disable, is-active, is-enabled."""

    def test_systemctl_start(self):
        argv = build_argv("systemctl_start", ["docker.service"])
        assert argv == ["systemctl", "start", "docker.service"]

    def test_systemctl_stop(self):
        argv = build_argv("systemctl_stop", ["docker.service"])
        assert argv == ["systemctl", "stop", "docker.service"]

    def test_systemctl_daemon_reload(self):
        argv = build_argv("systemctl_daemon_reload", [])
        assert argv == ["systemctl", "daemon-reload"]

    def test_systemctl_daemon_reload_rejects_argv(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("systemctl_daemon_reload", ["extra"])

    def test_systemctl_enable(self):
        argv = build_argv("systemctl_enable", ["hermes-root-executor.service"])
        assert argv == ["systemctl", "enable", "hermes-root-executor.service"]

    def test_systemctl_disable(self):
        argv = build_argv("systemctl_disable", ["hermes-root-executor.service"])
        assert argv == ["systemctl", "disable", "hermes-root-executor.service"]

    def test_systemctl_is_active(self):
        argv = build_argv("systemctl_is_active", ["docker.service"])
        assert argv == ["systemctl", "is-active", "docker.service"]

    def test_systemctl_is_enabled(self):
        argv = build_argv("systemctl_is_enabled", ["docker.service"])
        assert argv == ["systemctl", "is-enabled", "docker.service"]

    def test_systemctl_missing_unit(self):
        for action in ["systemctl_start", "systemctl_stop", "systemctl_enable",
                       "systemctl_disable", "systemctl_is_active", "systemctl_is_enabled"]:
            with pytest.raises(ActionError, match="invalid_argv"):
                build_argv(action, [])

    def test_systemctl_restart_preserved(self):
        argv = build_argv("systemctl_restart", ["hermes-root-executor.service"])
        assert argv == ["systemctl", "restart", "hermes-root-executor.service"]

    def test_systemctl_status_preserved(self):
        argv = build_argv("systemctl_status", ["docker.service"])
        assert argv == ["systemctl", "status", "docker.service"]


# ============================================================================
# Docker — extended actions
# ============================================================================

class TestDockerActions:
    """docker start, pull, logs, images, network, volume, exec."""

    def test_docker_start(self):
        argv = build_argv("docker_start", ["my-container"])
        assert argv == ["docker", "start", "my-container"]

    def test_docker_pull(self):
        argv = build_argv("docker_pull", ["ubuntu:22.04"])
        assert argv == ["docker", "pull", "ubuntu:22.04"]

    def test_docker_logs(self):
        argv = build_argv("docker_logs", ["my-container"])
        assert argv == ["docker", "logs", "--tail", "100", "my-container"]

    def test_docker_images(self):
        argv = build_argv("docker_images", [])
        assert argv == ["docker", "images"]

    def test_docker_images_with_all(self):
        argv = build_argv("docker_images", ["--all"])
        assert argv == ["docker", "images", "--all"]

    def test_docker_network_create(self):
        argv = build_argv("docker_network_create", ["my-net"])
        assert argv == ["docker", "network", "create", "my-net"]

    def test_docker_network_remove(self):
        argv = build_argv("docker_network_remove", ["my-net"])
        assert argv == ["docker", "network", "rm", "my-net"]

    def test_docker_volume_create(self):
        argv = build_argv("docker_volume_create", ["my-vol"])
        assert argv == ["docker", "volume", "create", "my-vol"]

    def test_docker_volume_remove(self):
        argv = build_argv("docker_volume_remove", ["my-vol"])
        assert argv == ["docker", "volume", "rm", "my-vol"]

    def test_docker_exec(self):
        argv = build_argv("docker_exec", ["my-container", "ls", "-la"])
        assert argv == ["docker", "exec", "my-container", "ls", "-la"]

    def test_docker_exec_too_few_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("docker_exec", ["my-container"])

    def test_docker_create_preserved(self):
        argv = build_argv("docker_create", ["--name", "test", "ubuntu:22.04"])
        assert argv == ["docker", "create", "--name", "test", "ubuntu:22.04"]

    def test_docker_stop_preserved(self):
        argv = build_argv("docker_stop", ["my-container"])
        assert argv == ["docker", "stop", "my-container"]

    def test_docker_remove_preserved(self):
        argv = build_argv("docker_remove", ["my-container"])
        assert argv == ["docker", "rm", "my-container"]

    def test_docker_inspect_preserved(self):
        argv = build_argv("docker_inspect", ["my-container"])
        assert argv == ["docker", "inspect", "my-container"]

    def test_docker_ps_preserved(self):
        argv = build_argv("docker_ps", [])
        assert argv == ["docker", "ps"]


# ============================================================================
# Filesystem — read-only actions
# ============================================================================

class TestFilesystemReadActions:
    """fs_stat, fs_ls, fs_read, fs_checksum."""

    def test_fs_stat(self):
        argv = build_argv("fs_stat", ["/tmp/test.txt"])
        assert argv == ["stat", "/tmp/test.txt"]

    def test_fs_ls(self):
        argv = build_argv("fs_ls", ["/tmp"])
        assert argv == ["ls", "-la", "/tmp"]

    def test_fs_read(self):
        argv = build_argv("fs_read", ["/tmp/test.txt"])
        assert argv == ["cat", "/tmp/test.txt"]

    def test_fs_checksum(self):
        argv = build_argv("fs_checksum", ["/tmp/test.txt"])
        assert argv == ["sha256sum", "/tmp/test.txt"]

    def test_fs_readonly_missing_path(self):
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum"]:
            with pytest.raises(ActionError, match="invalid_argv"):
                build_argv(action, [])

    def test_fs_readonly_path_traversal_blocked(self):
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum"]:
            with pytest.raises(ActionError, match="traversal|outside"):
                build_argv(action, ["/etc/shadow"])

    def test_fs_readonly_relative_path_blocked(self):
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum"]:
            with pytest.raises(ActionError, match="not_absolute"):
                build_argv(action, ["relative/path"])

    def test_fs_read_gate0_native_dataset_allowed(self):
        # #702: the frozen Gate-0 dataset must be readable via the executor
        # (read-only evidence path for the selection backtest).
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum"]:
            argv = build_argv(action, ["/opt/data/gate0-freqtrade-native-r1/futures"])
            assert argv[-1].startswith("/opt/data/gate0-freqtrade-native-r1")

    def test_fs_read_gate0_backtest_results_allowed(self):
        # #702: backtest results must be readable for evidence collection.
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum"]:
            argv = build_argv(action, ["/opt/data/gate0-backtest-results"])
            assert argv[-1].startswith("/opt/data/gate0-backtest-results")


# ============================================================================
# Filesystem — mutating actions
# ============================================================================

class TestFilesystemWriteActions:
    """fs_write, fs_copy, fs_move, fs_remove, fs_mkdir, fs_chmod, fs_chown."""

    def test_fs_write(self):
        argv = build_argv("fs_write", ["/tmp/test.txt", "hello world"])
        assert argv[0] == "python3"
        assert argv[1] == "-c"
        assert "/tmp/test.txt" in argv
        assert "hello world" in argv

    def test_fs_copy(self):
        argv = build_argv("fs_copy", ["/tmp/src.txt", "/tmp/dst.txt"])
        assert argv == ["cp", "-a", "/tmp/src.txt", "/tmp/dst.txt"]

    def test_fs_move(self):
        argv = build_argv("fs_move", ["/tmp/src.txt", "/tmp/dst.txt"])
        assert argv == ["mv", "/tmp/src.txt", "/tmp/dst.txt"]

    def test_fs_remove(self):
        argv = build_argv("fs_remove", ["/tmp/test.txt"])
        assert argv == ["rm", "-rf", "/tmp/test.txt"]

    def test_fs_mkdir(self):
        argv = build_argv("fs_mkdir", ["/tmp/newdir"])
        assert argv == ["mkdir", "-p", "/tmp/newdir"]

    def test_fs_chmod(self):
        argv = build_argv("fs_chmod", ["0755", "/tmp/test.txt"])
        assert argv == ["chmod", "0755", "/tmp/test.txt"]

    def test_fs_chown(self):
        argv = build_argv("fs_chown", ["hermes:hermes", "/tmp/test.txt"])
        assert argv == ["chown", "hermes:hermes", "/tmp/test.txt"]

    def test_fs_backup(self):
        argv = build_argv("fs_backup", ["/tmp/src", "/tmp/backup"])
        assert argv == ["cp", "-a", "/tmp/src", "/tmp/backup"]

    def test_fs_restore(self):
        argv = build_argv("fs_restore", ["/tmp/backup", "/tmp/restore"])
        assert argv == ["cp", "-a", "/tmp/backup", "/tmp/restore"]

    def test_fs_write_too_few_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("fs_write", ["/tmp/test.txt"])

    def test_fs_copy_wrong_arg_count(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("fs_copy", ["/tmp/src.txt"])

    def test_fs_chmod_wrong_arg_count(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("fs_chmod", ["0755"])

    def test_fs_chown_wrong_arg_count(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("fs_chown", ["hermes"])

    def test_fs_mutating_path_traversal_blocked(self):
        for action in ["fs_remove", "fs_mkdir"]:
            with pytest.raises(ActionError, match="traversal|outside"):
                build_argv(action, ["/etc/shadow"])

    def test_fs_mutating_relative_path_blocked(self):
        for action in ["fs_remove", "fs_mkdir"]:
            with pytest.raises(ActionError, match="not_absolute"):
                build_argv(action, ["relative/path"])

    def test_fs_write_gate0_backtest_results_allowed(self):
        # #702: the results directory must be writable via the executor
        # (results mount for the selection backtest).
        argv = build_argv("fs_mkdir", ["/opt/data/gate0-backtest-results/gate0-selection"])
        assert argv[-1].startswith("/opt/data/gate0-backtest-results")
        argv = build_argv("fs_chmod", ["0755", "/opt/data/gate0-backtest-results/gate0-selection"])
        assert argv[-1].startswith("/opt/data/gate0-backtest-results")
        argv = build_argv("fs_chown", ["10000:10000", "/opt/data/gate0-backtest-results/gate0-selection"])
        assert argv[-1].startswith("/opt/data/gate0-backtest-results")


# ============================================================================
# Git — read-only actions
# ============================================================================

class TestGitReadActions:
    """git_status, git_branch, git_log, git_tag_list."""

    def test_git_status(self):
        argv = build_argv("git_status", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "status"]

    def test_git_branch(self):
        argv = build_argv("git_branch", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "branch", "-a"]

    def test_git_log(self):
        argv = build_argv("git_log", ["/opt/data/projects/trading-hub", "5"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "log", "--oneline", "-5"]

    def test_git_log_default_count(self):
        argv = build_argv("git_log", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "log", "--oneline", "-10"]

    def test_git_tag_list(self):
        argv = build_argv("git_tag_list", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "tag"]

    def test_git_readonly_missing_repo(self):
        for action in ["git_status", "git_branch", "git_tag_list"]:
            with pytest.raises(ActionError, match="invalid_argv"):
                build_argv(action, [])

    def test_git_readonly_repo_traversal_blocked(self):
        for action in ["git_status", "git_branch", "git_tag_list"]:
            with pytest.raises(ActionError, match="traversal|outside"):
                build_argv(action, ["/etc"])

    def test_git_readonly_relative_path_blocked(self):
        for action in ["git_status", "git_branch", "git_tag_list"]:
            with pytest.raises(ActionError, match="not_absolute"):
                build_argv(action, ["relative/path"])


# ============================================================================
# Git — mutating actions
# ============================================================================

class TestGitWriteActions:
    """git_clone, git_fetch, git_checkout, git_merge, git_tag_create,
    git_tag_delete, git_clean, git_reset, git_push."""

    def test_git_clone(self):
        argv = build_argv("git_clone", ["https://github.com/org/repo.git", "/tmp/repo"])
        assert argv == ["git", "clone", "https://github.com/org/repo.git", "/tmp/repo"]

    def test_git_fetch(self):
        argv = build_argv("git_fetch", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "fetch", "--all"]

    def test_git_checkout(self):
        argv = build_argv("git_checkout", ["/opt/data/projects/trading-hub", "main"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "checkout", "main"]

    def test_git_merge(self):
        argv = build_argv("git_merge", ["/opt/data/projects/trading-hub", "feature-branch"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "merge", "feature-branch"]

    def test_git_tag_create(self):
        argv = build_argv("git_tag_create", ["/opt/data/projects/trading-hub", "v1.0"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "tag", "v1.0"]

    def test_git_tag_delete(self):
        argv = build_argv("git_tag_delete", ["/opt/data/projects/trading-hub", "v1.0"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "tag", "-d", "v1.0"]

    def test_git_clean(self):
        argv = build_argv("git_clean", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "clean", "-fd"]

    def test_git_reset(self):
        argv = build_argv("git_reset", ["/opt/data/projects/trading-hub", "HEAD~1"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "reset", "--hard", "HEAD~1"]

    def test_git_push(self):
        argv = build_argv("git_push", ["/opt/data/projects/trading-hub"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "push"]

    def test_git_push_with_remote_and_branch(self):
        argv = build_argv("git_push", ["/opt/data/projects/trading-hub", "origin", "main"])
        assert argv == ["git", "-C", "/opt/data/projects/trading-hub", "push", "origin", "main"]

    def test_git_clone_too_few_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("git_clone", ["https://github.com/org/repo.git"])

    def test_git_checkout_too_few_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("git_checkout", ["/opt/data/projects/trading-hub"])

    def test_git_merge_too_few_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("git_merge", ["/opt/data/projects/trading-hub"])

    def test_git_mutating_repo_traversal_blocked(self):
        for action in ["git_fetch", "git_clean"]:
            with pytest.raises(ActionError, match="traversal|outside"):
                build_argv(action, ["/etc"])

    def test_git_mutating_relative_path_blocked(self):
        for action in ["git_fetch", "git_clean"]:
            with pytest.raises(ActionError, match="not_absolute"):
                build_argv(action, ["relative/path"])


# ============================================================================
# Integration — daemon handles new actions end-to-end
# ============================================================================

class TestNewActionsDaemonIntegration:
    """End-to-end daemon handling of new actions (mocked subprocess)."""

    def test_docker_logs_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="docker_logs", argv=["my-container"]))
        assert resp["decision"] == "ALLOWED"

    def test_docker_images_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="docker_images", argv=[]))
        assert resp["decision"] == "ALLOWED"

    def test_systemctl_start_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="systemctl_start", argv=["docker.service"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_systemctl_daemon_reload_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="systemctl_daemon_reload", argv=[],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_fs_stat_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="fs_stat", argv=["/tmp"]))
        assert resp["decision"] == "ALLOWED"

    def test_fs_read_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="fs_read", argv=["/tmp/test.txt"]))
        assert resp["decision"] == "ALLOWED"

    def test_fs_mkdir_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="fs_mkdir", argv=["/tmp/newdir"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_git_status_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="git_status", argv=["/opt/data/projects/trading-hub"],
        ))
        assert resp["decision"] == "ALLOWED"

    def test_git_fetch_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="git_fetch", argv=["/opt/data/projects/trading-hub"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_git_clone_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="git_clone", argv=["https://github.com/org/repo.git", "/tmp/repo"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_unknown_action_still_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(action="nonexistent_action"))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "unknown_action"

    def test_mutating_new_action_without_approval_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(
            action="systemctl_start", argv=["docker.service"],
            execution_class="A2", approval_reference=None,
        ))
        assert resp["decision"] == "BLOCKED"
        assert "approval" in resp["reason"]


# ============================================================================
# Schema — all new actions registered
# ============================================================================

class TestSchemaRegistration:
    """All new actions are properly registered in ALL_ACTIONS."""

    def test_systemd_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["systemctl_start", "systemctl_stop", "systemctl_daemon_reload",
                       "systemctl_enable", "systemctl_disable",
                       "systemctl_is_active", "systemctl_is_enabled"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_docker_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["docker_start", "docker_pull", "docker_logs", "docker_images",
                       "docker_network_create", "docker_network_remove",
                       "docker_volume_create", "docker_volume_remove", "docker_exec"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_fs_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["fs_stat", "fs_ls", "fs_read", "fs_checksum",
                       "fs_write", "fs_copy", "fs_move", "fs_remove",
                       "fs_mkdir", "fs_chmod", "fs_chown",
                       "fs_backup", "fs_restore"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_git_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["git_status", "git_branch", "git_log", "git_tag_list",
                       "git_clone", "git_fetch", "git_checkout", "git_merge",
                       "git_tag_create", "git_tag_delete", "git_clean",
                       "git_reset", "git_push"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_readonly_mutating_partition(self):
        from hermes_root.schema import READONLY_ACTIONS, MUTATING_ACTIONS, ALL_ACTIONS
        assert READONLY_ACTIONS | MUTATING_ACTIONS == ALL_ACTIONS
        assert READONLY_ACTIONS & MUTATING_ACTIONS == frozenset()
