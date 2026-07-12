"""Tests for hermes_root.daemon — legacy parity, v1 protocol, gates, audit (Categories A-E).

Category E (regression of test_hermes_root_client.py / test_hermestrader_dryrun_compose.py)
is exercised by running those suites unchanged alongside this file; see the migration
report for combined results.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import uuid

import pytest

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


def _legacy_payload(**overrides):
    payload = {"category": "fs_stat", "args": ["-c", "%n", "/etc/hostname"]}
    payload.update(overrides)
    return payload


def _send(daemon, payload_dict, uid=None):
    raw = json.dumps(payload_dict).encode()
    return daemon.handle_payload(raw, peer_pid=1234, peer_uid=uid if uid is not None else os.getuid())


def _read_audit(daemon):
    if not os.path.exists(daemon.audit_path):
        return []
    with open(daemon.audit_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _fake_ok_run(argv, **kw):
    return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


class TestLegacyParity:
    def test_valid_fs_stat(self, daemon):
        resp = _send(daemon, _legacy_payload(category="fs_stat", args=["-c", "%n", "/etc/hostname"]))
        assert resp["decision"] == "ALLOWED"
        assert resp["returncode"] == 0

    def test_valid_fs_ls(self, daemon):
        resp = _send(daemon, _legacy_payload(category="fs_ls", args=["/tmp"]))
        assert resp["decision"] == "ALLOWED"

    def test_valid_docker_read(self, daemon, monkeypatch):
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="container1\n", stderr="")

        monkeypatch.setattr("hermes_root.daemon.subprocess.run", fake_run)
        resp = _send(daemon, _legacy_payload(category="docker", args=["ps", "--format", "{{.Names}}"]))
        assert resp["decision"] == "ALLOWED"
        assert captured["argv"] == ["docker", "ps", "--format", "{{.Names}}"]

    def test_valid_systemd_read(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _legacy_payload(category="systemd", args=["status", "docker"]))
        assert resp["decision"] == "ALLOWED"

    def test_unknown_category(self, daemon):
        resp = _send(daemon, _legacy_payload(category="nope", args=[]))
        assert resp == {"decision": "BLOCKED", "reason": "unknown_category"}

    def test_invalid_args_type(self, daemon):
        resp = _send(daemon, {"category": "fs_stat", "args": "not-a-list"})
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "invalid_args"

    def test_wrong_uid_blocked(self, daemon):
        resp = _send(daemon, _legacy_payload(), uid=99999)
        assert resp == {"decision": "BLOCKED", "reason": "peer_uid_not_allowed"}

    def test_kill_switch_blocks_everything(self, daemon):
        os.makedirs(os.path.dirname(daemon.kill_switch_path), exist_ok=True)
        open(daemon.kill_switch_path, "w").close()
        resp = _send(daemon, _legacy_payload())
        assert resp == {"decision": "BLOCKED", "reason": "emergency_disable_switch_active"}

    def test_locking_rejects_concurrent_same_resource(self, daemon):
        os.makedirs(daemon.lock_dir, exist_ok=True)
        fd = daemon._acquire_lock("explicit-lock-key")
        assert fd is not None
        try:
            resp = _send(daemon, _legacy_payload(resource_key="explicit-lock-key"))
            assert resp == {"decision": "BLOCKED", "reason": "resource_locked"}
        finally:
            daemon._release_lock(fd)

    def test_timeout_blocks(self, daemon, monkeypatch):
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 30))

        monkeypatch.setattr("hermes_root.daemon.subprocess.run", fake_run)
        resp = _send(daemon, _legacy_payload(category="docker", args=["run", "-it", "img"]))
        assert resp == {"decision": "BLOCKED", "reason": "command_timeout"}

    def test_response_schema_allowed(self, daemon):
        resp = _send(daemon, _legacy_payload())
        assert set(resp.keys()) == {"decision", "returncode", "stdout", "stderr"}

    def test_invalid_json(self, daemon):
        resp = daemon.handle_payload(b"{not json", peer_pid=1, peer_uid=os.getuid())
        assert resp == {"decision": "BLOCKED", "reason": "invalid_json"}

    def test_audit_entry_written_legacy(self, daemon):
        _send(daemon, _legacy_payload())
        entries = _read_audit(daemon)
        assert len(entries) == 1
        assert entries[0]["legacy_protocol"] is True
        assert entries[0]["category"] == "fs_stat"


class TestV1Protocol:
    def test_valid_read_request(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(daemon, _v1_payload())
        assert resp["decision"] == "ALLOWED"
        assert resp["schema_version"] == SCHEMA_VERSION

    def test_wrong_schema_version(self, daemon):
        resp = _send(daemon, _v1_payload(schema_version="hermes-root-executor.v2"))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "unknown_schema_version"

    def test_missing_required_field(self, daemon):
        payload = _v1_payload()
        del payload["task_name"]
        resp = _send(daemon, payload)
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "missing_required_field"

    def test_unknown_field(self, daemon):
        resp = _send(daemon, _v1_payload(unexpected_field="x"))
        assert resp == {"decision": "BLOCKED", "reason": "unknown_field"}

    def test_wrong_field_type(self, daemon):
        resp = _send(daemon, _v1_payload(issue_number="not-an-int"))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "invalid_field_type"

    def test_invalid_argv_too_long(self, daemon):
        resp = _send(daemon, _v1_payload(argv=["x"] * 101))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "invalid_argv"

    def test_unknown_action(self, daemon):
        resp = _send(daemon, _v1_payload(action="delete_everything"))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "unknown_action"

    def test_payload_too_large(self, daemon):
        raw = b"x" * (1_048_576 + 1)
        resp = daemon.handle_payload(raw, peer_pid=1, peer_uid=os.getuid())
        assert resp == {"decision": "BLOCKED", "reason": "payload_too_large"}

    def test_timeout_out_of_range(self, daemon):
        resp = _send(daemon, _v1_payload(timeout=301))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "invalid_timeout"


class TestGates:
    def test_a0_mutation_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(execution_class="A0", action="docker_create", argv=["img"]))
        assert resp["decision"] == "BLOCKED"

    def test_a1_mutation_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(execution_class="A1", action="docker_stop", argv=["c1"]))
        assert resp["decision"] == "BLOCKED"

    def test_a2_without_approval_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(execution_class="A2", action="docker_stop", argv=["c1"]))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "approval_reference_missing_or_invalid"

    def test_a2_wrong_approval_blocked(self, daemon):
        resp = _send(
            daemon,
            _v1_payload(execution_class="A2", action="docker_stop", argv=["c1"], approval_reference="WRONG"),
        )
        assert resp["decision"] == "BLOCKED"

    def test_a2_correct_approval_allowed(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        resp = _send(
            daemon,
            _v1_payload(execution_class="A2", action="docker_stop", argv=["c1"], approval_reference=APPROVED),
        )
        assert resp["decision"] == "ALLOWED"

    def test_a3_always_blocked(self, daemon):
        resp = _send(daemon, _v1_payload(execution_class="A3", action="docker_ps", approval_reference=APPROVED))
        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "a3_never_authorized"


class TestAuditV2:
    def test_correlation_and_request_id_present(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        payload = _v1_payload()
        _send(daemon, payload)
        entries = _read_audit(daemon)
        assert entries[-1]["request_id"] == payload["request_id"]
        assert entries[-1]["correlation_id"] == payload["correlation_id"]
        assert entries[-1]["execution_class"] == "A0"

    def test_approval_reference_redacted(self, daemon, monkeypatch):
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
        payload = _v1_payload(execution_class="A2", action="docker_stop", argv=["c1"], approval_reference=APPROVED)
        _send(daemon, payload)
        entries = _read_audit(daemon)
        dumped = json.dumps(entries[-1])
        assert APPROVED not in dumped
        assert entries[-1]["approval_reference_redacted"] == "[PRESENT]"

    def test_legacy_protocol_flag_correct(self, daemon):
        _send(daemon, _legacy_payload())
        entries = _read_audit(daemon)
        assert entries[-1]["legacy_protocol"] is True

    def test_no_synthetic_secrets_leak(self, daemon, monkeypatch):
        secret = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        monkeypatch.setattr(
            "hermes_root.daemon.subprocess.run",
            lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=f"AWS_SECRET_ACCESS_KEY={secret}", stderr=""),
        )
        _send(daemon, _v1_payload())
        entries = _read_audit(daemon)
        dumped = json.dumps(entries[-1])
        assert secret not in dumped


def test_real_socket_end_to_end(daemon, monkeypatch):
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", _fake_ok_run)
    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if os.path.exists(daemon.socket_path):
                break
            time.sleep(0.05)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5)
        client.connect(daemon.socket_path)
        client.sendall(json.dumps(_legacy_payload()).encode())
        raw = client.recv(65536)
        client.close()
        resp = json.loads(raw.decode())
        assert resp["decision"] == "ALLOWED"
    finally:
        daemon.stop()
