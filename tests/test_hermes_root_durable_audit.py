"""SEC-3 regression tests for durable pre-execution intent auditing."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from hermes_root import audit
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
        "issue_number": 634,
        "task_name": "SEC-3",
        "execution_class": "A0",
        "resource_key": "sec3:test",
        "action": "docker_ps",
        "argv": [],
        "cwd": "/tmp",
        "timeout": 30,
        "approval_reference": None,
    }
    payload.update(overrides)
    return payload


def _send(daemon, payload):
    return daemon.handle_payload(
        json.dumps(payload).encode(), peer_pid=1234, peer_uid=os.getuid()
    )


def _entries(daemon):
    if not os.path.exists(daemon.audit_path):
        return []
    with open(daemon.audit_path, encoding="utf-8") as audit_file:
        return [json.loads(line) for line in audit_file if line.strip()]


def _ok(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


class _FailingStream:
    def __init__(self, *, failure: str):
        self.failure = failure

    def write(self, value):
        if self.failure == "write":
            raise OSError("synthetic write failure")
        if self.failure == "partial":
            return len(value) - 1
        return len(value)

    def flush(self):
        if self.failure == "flush":
            raise OSError("synthetic flush failure")

    def fileno(self):
        return 99

    def close(self):
        return None


def test_durable_intent_precedes_subprocess_and_completion(daemon, monkeypatch):
    order = []
    original_write = audit.write_audit_entry

    def tracked_write(*args, **kwargs):
        audit_id = original_write(*args, **kwargs)
        order.append(kwargs["event"])
        return audit_id

    def fake_run(argv, **kwargs):
        assert order == ["intent"]
        order.append("subprocess")
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("hermes_root.daemon.audit.write_audit_entry", tracked_write)
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", fake_run)

    response = _send(daemon, _v1_payload())

    assert response["decision"] == "ALLOWED"
    assert order == ["intent", "subprocess", "completion"]


@pytest.mark.parametrize("failure", ["write", "flush", "partial"])
def test_intent_write_or_flush_failure_prevents_subprocess(
    daemon, monkeypatch, failure
):
    monkeypatch.setattr(
        audit, "_open_audit_stream", lambda path: _FailingStream(failure=failure)
    )
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    response = _send(daemon, _v1_payload())

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "audit_intent_durability_failure"
    assert called is False


def test_intent_fsync_failure_prevents_subprocess(daemon, monkeypatch):
    monkeypatch.setattr(audit.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fsync")))
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    response = _send(daemon, _v1_payload())

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "audit_intent_durability_failure"
    assert called is False


def test_intent_open_failure_prevents_subprocess(daemon, monkeypatch):
    monkeypatch.setattr(
        audit,
        "_open_audit_stream",
        lambda path: (_ for _ in ()).throw(OSError("open")),
    )
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    response = _send(daemon, _v1_payload())

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "audit_intent_durability_failure"
    assert called is False


def test_new_file_directory_fsync_failure_prevents_subprocess(daemon, monkeypatch):
    monkeypatch.setattr(
        audit,
        "_sync_parent_directory",
        lambda path: (_ for _ in ()).throw(OSError("directory fsync")),
    )
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    response = _send(daemon, _v1_payload())

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "audit_intent_durability_failure"
    assert called is False


def test_success_has_correlated_intent_and_completion(daemon, monkeypatch):
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", _ok)
    response = _send(daemon, _v1_payload())
    entries = _entries(daemon)

    assert [entry["event"] for entry in entries] == ["intent", "completion"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"] == response["audit_id"]
    assert entries[0]["durability_required"] == "flush+fsync"
    assert entries[0]["audit_event_id"] != entries[1]["audit_event_id"]


def test_nonzero_exit_has_correlated_execution_error(daemon, monkeypatch):
    monkeypatch.setattr(
        "hermes_root.daemon.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 7, stdout="", stderr="failed"
        ),
    )
    response = _send(daemon, _v1_payload())
    entries = _entries(daemon)

    assert response["decision"] == "ALLOWED"
    assert response["returncode"] == 7
    assert response["reason"] == "command_failed"
    assert [entry["event"] for entry in entries] == ["intent", "execution_error"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]


def test_subprocess_exception_has_correlated_execution_error(daemon, monkeypatch):
    monkeypatch.setattr(
        "hermes_root.daemon.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic")),
    )
    response = _send(daemon, _v1_payload())
    entries = _entries(daemon)

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "subprocess_execution_error"
    assert [entry["event"] for entry in entries] == ["intent", "execution_error"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]


def test_timeout_has_correlated_timeout_event(daemon, monkeypatch):
    monkeypatch.setattr(
        "hermes_root.daemon.subprocess.run",
        lambda argv, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(argv, kwargs["timeout"])
        ),
    )
    response = _send(daemon, _v1_payload())
    entries = _entries(daemon)

    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "command_timeout"
    assert [entry["event"] for entry in entries] == ["intent", "timeout"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]


def test_rejected_request_has_no_execution_intent(daemon, monkeypatch):
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("hermes_root.daemon.subprocess.run", forbidden_run)
    response = _send(
        daemon,
        _v1_payload(execution_class="A1", action="docker_stop", argv=["c1"]),
    )
    entries = _entries(daemon)

    assert response["decision"] == "BLOCKED"
    assert called is False
    assert [entry["event"] for entry in entries] == ["rejected"]


def test_legacy_allowed_request_keeps_safe_classification(daemon, monkeypatch):
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", _ok)
    payload = {
        "category": "systemd",
        "args": ["status", "hermes-root-executor.service"],
        "resource_key": "sec3:legacy",
    }
    response = _send(daemon, payload)
    entries = _entries(daemon)

    assert response["decision"] == "ALLOWED"
    assert [entry["event"] for entry in entries] == ["intent", "completion"]
    assert entries[0]["audit_id"] == entries[1]["audit_id"]
    assert {entry["legacy_classification"] for entry in entries} == {
        "legacy:systemd:status:read_only"
    }


def test_secret_canary_is_absent_from_intent_and_completion(daemon, monkeypatch):
    canary = "TOKEN=SEC3-CANARY-DO-NOT-PERSIST-0123456789"
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", _ok)
    response = _send(daemon, _v1_payload(argv=["--filter", canary]))

    assert response["decision"] == "ALLOWED"
    with open(daemon.audit_path, encoding="utf-8") as audit_file:
        audit_text = audit_file.read()
    assert canary not in audit_text


def test_terminal_audit_failure_never_returns_success(daemon, monkeypatch):
    original_write = audit.write_audit_entry
    subprocess_called = False

    def fail_completion(*args, **kwargs):
        if kwargs["event"] == "completion":
            raise audit.AuditDurabilityError("fsync")
        return original_write(*args, **kwargs)

    def fake_run(argv, **kwargs):
        nonlocal subprocess_called
        subprocess_called = True
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("hermes_root.daemon.audit.write_audit_entry", fail_completion)
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", fake_run)
    response = _send(daemon, _v1_payload())

    assert subprocess_called is True
    assert response["decision"] == "BLOCKED"
    assert response["reason"] == "audit_terminal_durability_failure"
    assert [entry["event"] for entry in _entries(daemon)] == ["intent"]


def _direct_audit_write(path, index):
    return audit.write_audit_entry(
        str(path),
        request_id=f"request-{index}",
        correlation_id=f"correlation-{index}",
        issue_number=634,
        task_name="SEC-3",
        execution_class="A0",
        action="docker_ps",
        category=None,
        resource_key=f"resource-{index}",
        peer_pid=index,
        peer_uid=10000,
        legacy_protocol=False,
        approval_reference=None,
        decision="BLOCKED",
        reason="test",
        returncode=None,
        duration_ms=0,
        stdout_len=0,
        stderr_len=0,
        timeout=30,
        daemon_version="test",
        repository_commit="test-sha",
        event="rejected",
    )


def test_concurrent_records_remain_valid_append_only_jsonl(tmp_path):
    audit_path = tmp_path / "concurrent.jsonl"
    with ThreadPoolExecutor(max_workers=8) as executor:
        audit_ids = list(executor.map(lambda i: _direct_audit_write(audit_path, i), range(32)))

    with open(audit_path, encoding="utf-8") as audit_file:
        entries = [json.loads(line) for line in audit_file]
    assert len(entries) == 32
    assert len(set(audit_ids)) == 32
    assert {entry["request_id"] for entry in entries} == {
        f"request-{index}" for index in range(32)
    }


def test_v1_response_shape_remains_compatible(daemon, monkeypatch):
    monkeypatch.setattr("hermes_root.daemon.subprocess.run", _ok)
    response = _send(daemon, _v1_payload())
    assert set(response) == {
        "schema_version",
        "request_id",
        "correlation_id",
        "decision",
        "reason",
        "returncode",
        "stdout",
        "stderr",
        "started_at",
        "finished_at",
        "duration_ms",
        "resource_key",
        "action",
        "execution_class",
        "audit_id",
    }
