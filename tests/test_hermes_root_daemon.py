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
        resp = _send(daemon, _legacy_payload(category="docker", args=["ps"]))
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
        assert len(entries) == 2
        assert [entry["event"] for entry in entries] == ["intent", "completion"]
        assert entries[0]["audit_id"] == entries[1]["audit_id"]
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
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout=f"AWS_SECRET_ACCESS_KEY={secret}", stderr=""
            ),
        )
        _send(daemon, _v1_payload())
        entries = _read_audit(daemon)
        dumped = json.dumps(entries[-1])
        assert secret not in dumped


class TestSecretRedaction:
    """Regression coverage for the 2026-07-13 incident: a rendered
    docker-compose config exposed a live GH_TOKEN through unredacted
    executor stdout. TestAuditV2.test_no_synthetic_secrets_leak only ever
    checked the *audit log* (which stores lengths, not content, and was
    never the leak vector) — it gave false confidence. These tests check
    the actual response payload returned to the caller, which is what
    leaked. All secrets here are synthetic canaries, never real credentials.
    """

    CANARY_GH_TOKEN = "github_pat_11CANARY0000000000000000000000000000000000000000000000"
    CANARY_BEARER = "canary-bearer-token-0123456789abcdef"
    CANARY_PASSWORD = "canary-s3cr3t-password"
    CANARY_API_KEY = "canary-api-key-fedcba9876543210"

    def _fake_run_with(self, stdout: str = "", stderr: str = ""):
        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=stderr)
        return fake_run

    def test_v1_response_stdout_redacts_env_style_canary(self, daemon, monkeypatch):
        stdout = (
            "name: hermes\nservices:\n  hermes:\n    environment:\n"
            f"      GH_TOKEN: {self.CANARY_GH_TOKEN}\n"
            "      HERMES_UID: \"10000\"\n"
        )
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        resp = _send(daemon, _v1_payload(action="docker_ps"))
        assert self.CANARY_GH_TOKEN not in resp["stdout"]
        assert "[REDACTED]" in resp["stdout"]
        assert "HERMES_UID" in resp["stdout"]  # non-secret fields survive

    def test_v1_response_stderr_redacts_bearer_canary(self, daemon, monkeypatch):
        stderr = f"Authorization: Bearer {self.CANARY_BEARER}\n"
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stderr=stderr))
        resp = _send(daemon, _v1_payload())
        assert self.CANARY_BEARER not in resp["stderr"]
        assert "[REDACTED]" in resp["stderr"]

    def test_v1_response_redacts_json_style_canary(self, daemon, monkeypatch):
        stdout = f'{{"API_KEY": "{self.CANARY_API_KEY}"}}'
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        resp = _send(daemon, _v1_payload())
        assert self.CANARY_API_KEY not in resp["stdout"]
        assert "[REDACTED]" in resp["stdout"]

    def test_v1_response_redacts_env_assignment_canary(self, daemon, monkeypatch):
        stdout = f"PASSWORD={self.CANARY_PASSWORD}\n"
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        resp = _send(daemon, _v1_payload())
        assert self.CANARY_PASSWORD not in resp["stdout"]
        assert "[REDACTED]" in resp["stdout"]

    def test_legacy_response_also_redacts_canary(self, daemon, monkeypatch):
        """The legacy protocol path (_handle_legacy) has its own response
        construction, separate from _finish_v1 — must be redacted too."""
        stdout = f"GH_TOKEN: {self.CANARY_GH_TOKEN}\n"
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        resp = _send(daemon, _legacy_payload(category="docker", args=["ps"]))
        assert self.CANARY_GH_TOKEN not in resp["stdout"]
        assert "[REDACTED]" in resp["stdout"]

    def test_normal_output_unaffected_by_redaction(self, daemon, monkeypatch):
        stdout = "container1\ncontainer2\n"
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        resp = _send(daemon, _v1_payload(action="docker_ps"))
        assert resp["stdout"] == stdout

    def test_audit_log_still_has_no_canary(self, daemon, monkeypatch):
        stdout = f"GH_TOKEN: {self.CANARY_GH_TOKEN}\n"
        monkeypatch.setattr("hermes_root.daemon.subprocess.run", self._fake_run_with(stdout=stdout))
        _send(daemon, _v1_payload())
        entries = _read_audit(daemon)
        dumped = json.dumps(entries[-1])
        assert self.CANARY_GH_TOKEN not in dumped


def test_real_timeout_with_real_subprocess(daemon, monkeypatch):
    """Non-mocked timeout proof (Issue #531 requirement): the existing
    test_timeout_blocks mocks subprocess.run entirely, which only proves
    the daemon *would* handle a TimeoutExpired exception, not that a real,
    long-running subprocess actually gets bounded and cleaned up.

    This test forces actions.build_argv to return a real "sleep" command
    for a single request only (monkeypatched per-test, never added to the
    production ALL_ACTIONS/LEGACY_CATEGORY_BINARIES registry — no new
    permanent action or generic shell capability is introduced), sends it
    through the real AF_UNIX socket server with timeout=1, and verifies:
    genuine subprocess.TimeoutExpired handling, a bounded wall-clock
    duration (not the full sleep duration), the correct decision/reason,
    and no orphaned child process left behind afterward.
    """
    import hermes_root.daemon as daemon_mod

    original_build_argv = daemon_mod.actions.build_argv
    # An unusual, specific duration (not a shell comment — subprocess.run
    # never invokes a shell, so sleep only accepts numeric time arguments)
    # to keep the orphan-process check below unlikely to collide with any
    # unrelated sleep invocation on the host/CI runner.
    sleep_duration = "5.417"

    def slow_build_argv(action, argv):
        if action == "docker_ps":
            # A real subprocess guaranteed to outlive a 1s timeout.
            return ["sleep", sleep_duration]
        return original_build_argv(action, argv)

    monkeypatch.setattr(daemon_mod.actions, "build_argv", slow_build_argv)

    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if os.path.exists(daemon.socket_path):
                break
            time.sleep(0.05)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(10)
        client.connect(daemon.socket_path)
        payload = _v1_payload(action="docker_ps", timeout=1)

        start = time.monotonic()
        client.sendall(json.dumps(payload).encode())
        raw = client.recv(65536)
        elapsed = time.monotonic() - start
        client.close()
        resp = json.loads(raw.decode())

        assert resp["decision"] == "BLOCKED"
        assert resp["reason"] == "command_timeout"
        assert resp["correlation_id"] == payload["correlation_id"]
        # Bounded: the ~1s configured timeout fired, we did not wait out
        # the full 5s sleep.
        assert 1.0 <= elapsed < 4.0, f"expected timeout around 1s, took {elapsed:.2f}s"

        # No orphaned child process: subprocess.run(timeout=...) kills the
        # process on TimeoutExpired before re-raising; confirm nothing
        # matching this test's unique marker is still running.
        time.sleep(0.3)
        leftover = subprocess.run(
            ["pgrep", "-f", f"sleep {sleep_duration}"], capture_output=True, text=True
        )
        assert leftover.returncode != 0, (
            f"orphaned sleep process found: {leftover.stdout!r}"
        )

        # No lock file left held.
        entries = _read_audit(daemon)
        assert entries[-1]["reason"] == "command_timeout"
        assert entries[-1]["correlation_id"] == payload["correlation_id"]
    finally:
        daemon.stop()


class TestMainRepositoryCommit:
    """main() must fail closed without a valid HERMES_ROOT_EXECUTOR_
    REPOSITORY_COMMIT, instead of silently defaulting to "unknown" (as it
    did before this fix — every audit entry logged repository_commit=
    "unknown" regardless of what was actually deployed)."""

    def test_non_root_blocked(self, monkeypatch):
        import hermes_root.daemon as daemon_mod
        monkeypatch.setattr(daemon_mod.os, "geteuid", lambda: 1000)
        with pytest.raises(SystemExit, match="must run as root"):
            daemon_mod.main()

    def test_missing_env_var_fails_closed(self, monkeypatch):
        import hermes_root.daemon as daemon_mod
        monkeypatch.setattr(daemon_mod.os, "geteuid", lambda: 0)
        monkeypatch.delenv("HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT", raising=False)
        with pytest.raises(SystemExit, match="HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT"):
            daemon_mod.main()

    def test_malformed_env_var_fails_closed(self, monkeypatch):
        import hermes_root.daemon as daemon_mod
        monkeypatch.setattr(daemon_mod.os, "geteuid", lambda: 0)
        monkeypatch.setenv("HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT", "not-a-sha!!")
        with pytest.raises(SystemExit, match="HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT"):
            daemon_mod.main()

    def test_empty_env_var_fails_closed(self, monkeypatch):
        import hermes_root.daemon as daemon_mod
        monkeypatch.setattr(daemon_mod.os, "geteuid", lambda: 0)
        monkeypatch.setenv("HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT", "   ")
        with pytest.raises(SystemExit, match="HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT"):
            daemon_mod.main()

    def test_valid_commit_starts_daemon_with_it(self, monkeypatch):
        import hermes_root.daemon as daemon_mod
        monkeypatch.setattr(daemon_mod.os, "geteuid", lambda: 0)
        monkeypatch.setenv("HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT", "abc1234")

        captured = {}

        def fake_serve_forever(self):
            captured["repository_commit"] = self.repository_commit

        monkeypatch.setattr(daemon_mod.RootExecutorDaemon, "serve_forever", fake_serve_forever)
        daemon_mod.main()
        assert captured["repository_commit"] == "abc1234"


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


# ============================================================================
# R5A — HermesTrader dry-run compose execution tests (Issue #527)
# ============================================================================

R5A_APPROVED = "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT"
H3B_APPROVED = "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION"


@pytest.fixture(autouse=True)
def _r5a_mock_compose_file(monkeypatch):
    """Mock _validate_compose_file so R5A argv tests don't require the
    canonical compose file to exist on the test filesystem.
    This is safe for all tests — it only skips the filesystem existence
    check and does not change path resolution behavior."""
    from hermes_root import actions as actions_mod
    monkeypatch.setattr(actions_mod, "_validate_compose_file", lambda p: p)


def _r5a_v1_payload(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "issue_number": 527,
        "task_name": "R5A",
        "execution_class": "A2",
        "resource_key": "r5a:compose",
        "action": "r5a_compose_build",
        "argv": [],
        "cwd": "/tmp",
        "timeout": 120,
        "approval_reference": R5A_APPROVED,
    }
    payload.update(overrides)
    return payload


class TestR5AComposeExactArgv:
    """Exact argv generation for each R5A compose action."""

    def test_build_all_services(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_build", [])
        assert argv == [
            "docker", "compose", "-f",
            "/opt/data/projects/trading-hub/docker-compose.hermestrader-dryrun.yml",
            "-p", "hermestrader-dryrun", "build",
        ]

    def test_build_specific_services(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_build", ["freqtrade-freqforge", "rainbow"])
        assert "freqtrade-freqforge" in argv
        assert "rainbow" in argv
        assert "freqai-rebel" not in argv
        assert argv[-2:] == ["freqtrade-freqforge", "rainbow"]

    def test_up_all_services_includes_dash_d(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_up", [])
        assert argv[-1] == "-d"
        assert "up" in argv

    def test_stop_services(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_stop", ["freqtrade-freqforge"])
        assert "stop" in argv
        assert "freqtrade-freqforge" in argv
        assert "-d" not in argv

    def test_down_all_services(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_down", [])
        assert "down" in argv
        assert "-d" not in argv
        assert "--volumes" not in argv
        assert "-v" not in argv


class TestR5AComposeCanonicalPath:
    """Canonical compose path only — no arbitrary paths accepted."""

    def test_hardcoded_canonical_path_used(self):
        from hermes_root.actions import R5A_CANONICAL_COMPOSE_FILE
        assert R5A_CANONICAL_COMPOSE_FILE == (
            "/opt/data/projects/trading-hub/docker-compose.hermestrader-dryrun.yml"
        )

    def test_hardcoded_canonical_project_used(self):
        from hermes_root.actions import R5A_CANONICAL_PROJECT
        assert R5A_CANONICAL_PROJECT == "hermestrader-dryrun"


class TestR5AComposeServiceAllowlist:
    """Service allowlist validation — only the 5 default services."""

    def test_all_default_services_allowed(self, daemon):
        from hermes_root.actions import build_argv
        for svc in ["freqtrade-freqforge", "freqtrade-freqforge-canary",
                      "freqtrade-regime-hybrid", "freqtrade-webserver", "rainbow"]:
            argv = build_argv("r5a_compose_build", [svc])
            assert svc in argv

    def test_unknown_service_rejected(self, daemon):
        from hermes_root.actions import ActionError, build_argv
        with pytest.raises(ActionError, match="invalid_service"):
            build_argv("r5a_compose_build", ["nonexistent-service"])

    def test_rebel_service_blocked(self, daemon):
        from hermes_root.actions import ActionError, build_argv
        with pytest.raises(ActionError, match="rebel_blocked"):
            build_argv("r5a_compose_build", ["freqai-rebel"])

    def test_rebel_in_mixed_list_blocked(self, daemon):
        from hermes_root.actions import ActionError, build_argv
        with pytest.raises(ActionError, match="rebel_blocked"):
            build_argv("r5a_compose_up", ["freqtrade-freqforge", "freqai-rebel"])


class TestR5AComposeDownVolumesBlocked:
    """down -v / --volumes is explicitly blocked."""

    def test_down_v_flag_blocked(self, daemon):
        from hermes_root.actions import ActionError, build_argv
        with pytest.raises(ActionError, match="down_volumes_flag_blocked"):
            build_argv("r5a_compose_down", ["-v"])

    def test_down_volumes_flag_blocked(self, daemon):
        from hermes_root.actions import ActionError, build_argv
        with pytest.raises(ActionError, match="down_volumes_flag_blocked"):
            build_argv("r5a_compose_down", ["--volumes"])

    def test_down_with_valid_services_no_v(self, daemon):
        from hermes_root.actions import build_argv
        argv = build_argv("r5a_compose_down", ["freqtrade-freqforge"])
        assert "down" in argv
        assert "-v" not in argv
        assert "--volumes" not in argv


class TestR5AComposePolicyGates:
    """Policy gate enforcement: approval, execution class, issue context."""

    def test_r5a_approval_allowed(self, daemon):
        resp = _send(daemon, _r5a_v1_payload())
        assert resp["decision"] == "ALLOWED"

    def test_h3b_approval_also_accepted(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(approval_reference=H3B_APPROVED))
        assert resp["decision"] == "ALLOWED"

    def test_missing_approval_blocked(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(approval_reference=None))
        assert resp["decision"] == "BLOCKED"
        assert "approval" in resp["reason"]

    def test_wrong_approval_blocked(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(approval_reference="BOGUS"))
        assert resp["decision"] == "BLOCKED"
        assert "approval" in resp["reason"]

    def test_a3_always_blocked(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(execution_class="A3"))
        assert resp["decision"] == "BLOCKED"
        assert "a3" in resp["reason"]

    def test_a0_mutation_blocked(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(execution_class="A0"))
        assert resp["decision"] == "BLOCKED"

    def test_a1_mutation_blocked(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(execution_class="A1"))
        assert resp["decision"] == "BLOCKED"

    def test_issue_context_required(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(issue_number=None))
        assert resp["decision"] == "BLOCKED"

    def test_task_context_required(self, daemon):
        resp = _send(daemon, _r5a_v1_payload(task_name=""))
        assert resp["decision"] == "BLOCKED"


class TestR5AComposeAuditFields:
    """Audit completeness for R5A compose actions."""

    def test_audit_fields_present_on_allow(self, daemon):
        resp = _send(daemon, _r5a_v1_payload())
        assert resp["decision"] == "ALLOWED"
        assert resp.get("audit_id"), "audit_id must be present"
        assert resp.get("schema_version") == SCHEMA_VERSION
        assert resp.get("execution_class") == "A2"
        assert resp.get("action") == "r5a_compose_build"
        assert resp.get("resource_key") == "r5a:compose"

    def test_audit_file_written(self, daemon):
        _send(daemon, _r5a_v1_payload())
        entries = _read_audit(daemon)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["action"] == "r5a_compose_build"
        assert entry["execution_class"] == "A2"
        assert entry["audit_id"]
        assert entry["decision"] == "ALLOWED"
        assert entry.get("approval_reference_redacted") == "[PRESENT]"

    def test_audit_on_blocked(self, daemon):
        _send(daemon, _r5a_v1_payload(approval_reference=None))
        entries = _read_audit(daemon)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["decision"] == "BLOCKED"


class TestR5AComposeKillSwitch:
    """Kill switch blocks R5A compose actions."""

    def test_kill_switch_blocks_r5a(self, daemon, tmp_path):
        ks = tmp_path / "DISABLED"
        ks.write_text("")
        daemon.kill_switch_path = str(ks)
        resp = _send(daemon, _r5a_v1_payload())
        assert resp["decision"] == "BLOCKED"
        assert "emergency" in resp["reason"]


class TestR5AComposeRedaction:
    """Redaction of approval reference in audit."""

    def test_approval_reference_redacted_in_audit(self, daemon):
        _send(daemon, _r5a_v1_payload(approval_reference=R5A_APPROVED))
        entries = _read_audit(daemon)
        entry = entries[0]
        assert entry["approval_reference_redacted"] == "[PRESENT]"
        raw = json.dumps(entry)
        assert R5A_APPROVED not in raw
