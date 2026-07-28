"""Tests for the runtime management actions (Caddy, UFW, hostname, sysctl, users/groups).

Covers all new actions added in PR 2: Runtime Management.
Tests verify argv construction, validation, and error handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid

import pytest

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
        "resource_key": "test:runtime",
        "action": "caddy_validate",
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
# Caddy
# ============================================================================

class TestCaddyActions:
    """caddy_validate, caddy_reload, caddy_fmt."""

    def test_caddy_validate(self):
        argv = build_argv("caddy_validate", ["/etc/caddy/Caddyfile"])
        assert argv == ["caddy", "validate", "--config", "/etc/caddy/Caddyfile"]

    def test_caddy_reload(self):
        argv = build_argv("caddy_reload", ["/etc/caddy/Caddyfile"])
        assert argv == ["caddy", "reload", "--config", "/etc/caddy/Caddyfile"]

    def test_caddy_fmt(self):
        argv = build_argv("caddy_fmt", ["/etc/caddy/Caddyfile"])
        assert argv == ["caddy", "fmt", "--overwrite", "/etc/caddy/Caddyfile"]

    def test_caddy_missing_config(self):
        for action in ["caddy_validate", "caddy_reload", "caddy_fmt"]:
            with pytest.raises(ActionError, match="invalid_argv"):
                build_argv(action, [])


# ============================================================================
# UFW / Firewall
# ============================================================================

class TestUFWActions:
    """ufw_status, ufw_allow, ufw_deny, ufw_enable, ufw_disable."""

    def test_ufw_status(self):
        argv = build_argv("ufw_status", [])
        assert argv == ["ufw", "status", "verbose"]

    def test_ufw_status_rejects_argv(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("ufw_status", ["extra"])

    def test_ufw_allow(self):
        argv = build_argv("ufw_allow", ["22/tcp"])
        assert argv == ["ufw", "allow", "22/tcp"]

    def test_ufw_deny(self):
        argv = build_argv("ufw_deny", ["80/tcp"])
        assert argv == ["ufw", "deny", "80/tcp"]

    def test_ufw_enable(self):
        argv = build_argv("ufw_enable", [])
        assert argv == ["ufw", "--force", "enable"]

    def test_ufw_enable_rejects_argv(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("ufw_enable", ["extra"])

    def test_ufw_disable(self):
        argv = build_argv("ufw_disable", [])
        assert argv == ["ufw", "--force", "disable"]

    def test_ufw_disable_rejects_argv(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("ufw_disable", ["extra"])

    def test_ufw_missing_rule(self):
        for action in ["ufw_allow", "ufw_deny"]:
            with pytest.raises(ActionError, match="invalid_argv"):
                build_argv(action, [])


# ============================================================================
# Hostname
# ============================================================================

class TestHostnameActions:
    """hostname_get, hostname_set."""

    def test_hostname_get(self):
        argv = build_argv("hostname_get", [])
        assert argv == ["hostnamectl", "status", "--static"]

    def test_hostname_get_rejects_argv(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("hostname_get", ["extra"])

    def test_hostname_set(self):
        argv = build_argv("hostname_set", ["hermestrader"])
        assert argv == ["hostnamectl", "set-hostname", "hermestrader"]

    def test_hostname_set_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("hostname_set", [])


# ============================================================================
# sysctl
# ============================================================================

class TestSysctlActions:
    """sysctl_get, sysctl_set."""

    def test_sysctl_get(self):
        argv = build_argv("sysctl_get", ["net.ipv4.ip_forward"])
        assert argv == ["sysctl", "-n", "net.ipv4.ip_forward"]

    def test_sysctl_set(self):
        argv = build_argv("sysctl_set", ["net.ipv4.ip_forward", "1"])
        assert argv == ["sysctl", "-w", "net.ipv4.ip_forward=1"]

    def test_sysctl_get_missing_key(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("sysctl_get", [])

    def test_sysctl_set_wrong_arg_count(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("sysctl_set", ["net.ipv4.ip_forward"])

    def test_sysctl_set_too_many_args(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("sysctl_set", ["a", "b", "c"])


# ============================================================================
# User / Group management
# ============================================================================

class TestUserGroupActions:
    """user_create, user_modify, user_delete, group_create, group_delete."""

    def test_user_create(self):
        argv = build_argv("user_create", ["newuser"])
        assert argv == ["useradd", "newuser"]

    def test_user_create_with_args(self):
        argv = build_argv("user_create", ["newuser", "-G", "docker", "-m"])
        assert argv == ["useradd", "newuser", "-G", "docker", "-m"]

    def test_user_modify(self):
        argv = build_argv("user_modify", ["newuser", "-aG", "docker"])
        assert argv == ["usermod", "newuser", "-aG", "docker"]

    def test_user_delete(self):
        argv = build_argv("user_delete", ["olduser"])
        assert argv == ["userdel", "-r", "olduser"]

    def test_group_create(self):
        argv = build_argv("group_create", ["newgroup"])
        assert argv == ["groupadd", "newgroup"]

    def test_group_delete(self):
        argv = build_argv("group_delete", ["oldgroup"])
        assert argv == ["groupdel", "oldgroup"]

    def test_user_create_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("user_create", [])

    def test_user_modify_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("user_modify", [])

    def test_user_delete_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("user_delete", [])

    def test_group_create_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("group_create", [])

    def test_group_delete_missing_name(self):
        with pytest.raises(ActionError, match="invalid_argv"):
            build_argv("group_delete", [])


# ============================================================================
# Integration — daemon handles runtime actions end-to-end
# ============================================================================

class TestRuntimeActionsDaemonIntegration:
    """End-to-end daemon handling of runtime actions (mocked subprocess)."""

    def test_caddy_validate_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="caddy_validate", argv=["/etc/caddy/Caddyfile"]))
        assert resp["decision"] == "ALLOWED"

    def test_caddy_reload_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="caddy_reload", argv=["/etc/caddy/Caddyfile"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_ufw_status_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="ufw_status", argv=[]))
        assert resp["decision"] == "ALLOWED"

    def test_ufw_allow_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="ufw_allow", argv=["22/tcp"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_hostname_get_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="hostname_get", argv=[]))
        assert resp["decision"] == "ALLOWED"

    def test_hostname_set_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="hostname_set", argv=["hermestrader"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_sysctl_get_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(action="sysctl_get", argv=["net.ipv4.ip_forward"]))
        assert resp["decision"] == "ALLOWED"

    def test_sysctl_set_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="sysctl_set", argv=["net.ipv4.ip_forward", "1"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_user_create_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="user_create", argv=["newuser"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_group_create_via_daemon(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload(
            action="group_create", argv=["newgroup"],
            execution_class="A2", approval_reference=APPROVED,
        ))
        assert resp["decision"] == "ALLOWED"

    def test_runtime_mutating_without_approval_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(
            action="caddy_reload", argv=["/etc/caddy/Caddyfile"],
            execution_class="A2", approval_reference=None,
        ))
        assert resp["decision"] == "BLOCKED"
        assert "approval" in resp["reason"]


# ============================================================================
# Schema — all runtime actions registered
# ============================================================================

class TestRuntimeSchemaRegistration:
    """All runtime actions are properly registered in ALL_ACTIONS."""

    def test_caddy_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["caddy_validate", "caddy_reload", "caddy_fmt"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_ufw_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["ufw_status", "ufw_allow", "ufw_deny", "ufw_enable", "ufw_disable"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_hostname_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["hostname_get", "hostname_set"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_sysctl_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["sysctl_get", "sysctl_set"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_user_group_actions_in_all(self):
        from hermes_root.schema import ALL_ACTIONS
        for action in ["user_create", "user_modify", "user_delete",
                       "group_create", "group_delete"]:
            assert action in ALL_ACTIONS, f"{action} missing from ALL_ACTIONS"

    def test_readonly_mutating_partition(self):
        from hermes_root.schema import READONLY_ACTIONS, MUTATING_ACTIONS, ALL_ACTIONS
        assert READONLY_ACTIONS | MUTATING_ACTIONS == ALL_ACTIONS
        assert READONLY_ACTIONS & MUTATING_ACTIONS == frozenset()
