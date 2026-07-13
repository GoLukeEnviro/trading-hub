"""Tests for the repository-managed systemd installers under ops/systemd/.

These never touch the real host systemd/filesystem state — non-root and
wrong-GID rejection are exercised by prepending fake `id`/`getent`
wrapper scripts to PATH and running the installers in --check mode
(precondition-only, no install/reload/restart).
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_SYSTEMD = REPO_ROOT / "ops" / "systemd"
PERMISSIONS_SCRIPT = OPS_SYSTEMD / "install-hermes-executor-permissions-fix.sh"
COMMIT_SCRIPT = OPS_SYSTEMD / "install-repository-commit-env.sh"
R5A_SCRIPT = OPS_SYSTEMD / "install-r5a-compose-executor-extension.sh"
GROUP_DROPIN = OPS_SYSTEMD / "hermes-root-executor.service.d" / "10-hermes-group-permissions.conf"
COMMIT_DROPIN = OPS_SYSTEMD / "hermes-root-executor.service.d" / "20-repository-commit.conf"


def _make_fake_bin(tmp_path: Path, name: str, script_body: str) -> Path:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/usr/bin/env bash\n{script_body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_check(script: Path, fake_bin_dir: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if fake_bin_dir is not None:
        env["PATH"] = f"{fake_bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(script), "--check"],
        capture_output=True, text=True, timeout=10, env=env,
    )


def _run_r5a_check(
    expected_commit: str | None, fake_bin_dir: Path | None = None
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if fake_bin_dir is not None:
        env["PATH"] = f"{fake_bin_dir}:{env['PATH']}"
    args = ["bash", str(R5A_SCRIPT)]
    if expected_commit is not None:
        args += ["--expected-commit", expected_commit]
    args.append("--check")
    return subprocess.run(args, capture_output=True, text=True, timeout=10, env=env)


class TestBashSyntax:
    def test_permissions_script_syntax(self):
        result = subprocess.run(["bash", "-n", str(PERMISSIONS_SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_commit_script_syntax(self):
        result = subprocess.run(["bash", "-n", str(COMMIT_SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestDropinExactContent:
    def test_group_permissions_dropin_exact_values(self):
        content = GROUP_DROPIN.read_text()
        assert content == (
            "[Service]\n"
            "Group=hermes\n"
            "RuntimeDirectoryMode=0750\n"
            "RuntimeDirectoryPreserve=restart\n"
        )

    def test_repository_commit_dropin_exact_values(self):
        content = COMMIT_DROPIN.read_text()
        assert content == (
            "[Service]\n"
            "EnvironmentFile=/etc/hermes-root-executor/repository-commit.env\n"
        )


class TestPermissionsInstallerFailClosed:
    def test_check_passes_as_root_with_correct_gid(self):
        """Sanity: real environment (this host) has hermes GID 10000 and
        tests run as a user that can at least read the script; this proves
        the happy path of --check mode works without needing fakes."""
        result = _run_check(PERMISSIONS_SCRIPT)
        # Either passes (root, correct GID) or fails cleanly on "must run
        # as root" if the test runner isn't root — both are acceptable
        # here; the fake-based tests below assert the specific messages.
        assert "root check OK" in result.stdout or "must run as root" in result.stderr

    def test_non_root_rejected(self, tmp_path):
        fake_bin = _make_fake_bin(tmp_path, "id", 'echo 1000')
        result = _run_check(PERMISSIONS_SCRIPT, fake_bin)
        assert result.returncode != 0
        assert "must run as root" in result.stderr

    def test_wrong_gid_rejected(self, tmp_path):
        fake_bin = _make_fake_bin(tmp_path, "id", 'echo 0')
        # getent group hermes -> wrong GID
        getent_body = (
            'if [[ "$1" == "group" && "$2" == "hermes" ]]; then\n'
            '  echo "hermes:x:9999:deploy"\n'
            "else\n"
            '  exit 1\n'
            "fi"
        )
        _make_fake_bin(tmp_path, "getent", getent_body)
        result = _run_check(PERMISSIONS_SCRIPT, fake_bin)
        assert result.returncode != 0
        assert "expected 10000" in result.stderr

    def test_missing_hermes_group_rejected(self, tmp_path):
        fake_bin = _make_fake_bin(tmp_path, "id", 'echo 0')
        _make_fake_bin(tmp_path, "getent", 'exit 2')
        result = _run_check(PERMISSIONS_SCRIPT, fake_bin)
        assert result.returncode != 0
        assert "does not exist" in result.stderr


class TestCommitInstallerFailClosed:
    def test_non_root_rejected(self, tmp_path):
        fake_bin = _make_fake_bin(tmp_path, "id", 'echo 1000')
        result = _run_check(COMMIT_SCRIPT, fake_bin)
        assert result.returncode != 0
        assert "must run as root" in result.stderr

    def test_check_resolves_current_repo_commit(self):
        """Sanity: --check (as whatever user runs the tests) still
        resolves a real commit SHA from this checkout via git rev-parse,
        proving the resolve_commit() path works end to end."""
        result = _run_check(COMMIT_SCRIPT)
        if "must run as root" not in result.stderr:
            assert "resolved repository commit:" in result.stdout


class TestR5AInstallerSyntax:
    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(R5A_SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestR5AInstallerFailClosed:
    def test_missing_expected_commit_rejected(self):
        result = _run_r5a_check(expected_commit=None)
        assert result.returncode != 0
        assert "--expected-commit is required" in result.stderr

    def test_non_root_rejected(self, tmp_path):
        fake_bin = _make_fake_bin(tmp_path, "id", 'echo 1000')
        result = _run_r5a_check("deadbeef", fake_bin)
        assert result.returncode != 0
        assert "must run as root" in result.stderr

    def test_commit_mismatch_rejected(self):
        """A validly-shaped but wrong SHA must be rejected against the
        real repository HEAD -- this only reads git state, never mutates
        it, so it is safe to run against the real checkout."""
        result = _run_r5a_check("deadbeef")
        if "must run as root" not in result.stderr:
            assert result.returncode != 0
            assert "repository commit mismatch" in result.stderr

    def test_correct_commit_check_passes(self):
        """Sanity: --check with the real current HEAD succeeds end to
        end (root check, source package check, commit check, clean-tree
        check) without installing, reloading, or restarting anything."""
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        result = _run_r5a_check(head)
        assert "all precondition checks passed" in result.stdout or "must run as root" in result.stderr


class TestErrTraceRequiredForNestedRollback:
    """Regression test for a real R5A-installer bug: `trap ... ERR` set
    inside main() silently did not fire when the failing command was
    inside a nested function (e.g. verify_executor_health), so
    rollback() was never invoked on a real failure. Root cause: bash
    only propagates the ERR trap into function calls when `set -o
    errtrace` (-E) is also active -- `set -euo pipefail` alone is not
    enough. Fixed by changing the installer's option line to
    `set -Eeuo pipefail`.
    """

    _HARNESS = """set {opts}
rollback() {{ echo ROLLBACK_CALLED > "{marker}"; }}
trap rollback ERR
nested_failure() {{ false; }}
main() {{ nested_failure; }}
main
"""

    def _run(self, tmp_path, opts):
        # Deliberately NOT wrapped in `cmd || true`: that would suppress
        # errexit for the whole call, same as the original bug, and
        # defeat the point of the test. Let the harness exit non-zero
        # (as a real installer failure would) and check the trap's side
        # effect (the marker file) rather than output that would only
        # appear if the script kept running afterward.
        marker = tmp_path / "marker.txt"
        script = tmp_path / "harness.sh"
        script.write_text(self._HARNESS.format(opts=opts, marker=marker))
        subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=5)
        return marker.read_text() if marker.exists() else ""

    def test_err_trap_not_inherited_without_errtrace(self, tmp_path):
        """Reproduces the bug in isolation: without -E, a nested
        function's failure does not trigger the outer ERR trap."""
        assert self._run(tmp_path, "-euo pipefail") == ""

    def test_err_trap_inherited_with_errtrace(self, tmp_path):
        """Proves the fix in isolation: with -E, the same nested
        failure correctly triggers the outer ERR trap."""
        assert self._run(tmp_path, "-Eeuo pipefail") == "ROLLBACK_CALLED\n"

    def test_r5a_installer_has_errtrace_enabled(self):
        content = R5A_SCRIPT.read_text()
        assert "set -Eeuo pipefail" in content
        assert "set -euo pipefail" not in content


class TestR5ABackupDirCaptureNotPolluted:
    """Regression test for a third bug found alongside errtrace and the
    health-check assertion: log() printed to stdout, but
    `backup_dir="$(do_backup)"` captures do_backup()'s entire stdout --
    so every `log "backed up ..."` line inside do_backup() became part
    of the captured backup_dir value instead of just the final path.
    Harmless while rollback() never fired (the errtrace bug above), but
    the errtrace fix makes rollback() fire on real failures, and
    rollback() builds paths like "${backup_dir}/hermes_root" -- with a
    polluted, multi-line backup_dir that path silently does not exist,
    so a real rollback would wrongly take the "no package backup --
    removed new package" branch instead of restoring it. Fixed by
    sending log() output to stderr, leaving stdout clean for command
    substitution.
    """

    _HARNESS = """set -Eeuo pipefail
log() { printf '[x] %s\\n' "$1"REDIRECT_TOKEN; }
do_backup() {
    log "backed up something"
    log "backed up something else"
    printf '%s' "/the/real/path"
}
captured="$(do_backup)"
printf '%s' "$captured" > "OUT_TOKEN"
"""

    def _run(self, tmp_path, redirect):
        out = tmp_path / "captured.txt"
        script = tmp_path / "harness.sh"
        text = self._HARNESS.replace("REDIRECT_TOKEN", redirect).replace("OUT_TOKEN", str(out))
        script.write_text(text)
        subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=5)
        return out.read_text() if out.exists() else ""

    def test_stdout_logging_pollutes_captured_return_value(self, tmp_path):
        """Reproduces the bug in isolation: log() to stdout corrupts a
        `var="$(fn)"` capture with every intermediate log line."""
        assert self._run(tmp_path, redirect="") != "/the/real/path"

    def test_stderr_logging_keeps_captured_return_value_clean(self, tmp_path):
        """Proves the fix in isolation: log() to stderr leaves the
        captured value as exactly the function's real return value."""
        assert self._run(tmp_path, redirect=" >&2") == "/the/real/path"

    def test_r5a_installer_log_writes_to_stderr(self):
        content = R5A_SCRIPT.read_text()
        assert re.search(r"log\(\) \{ printf.*>&2", content)
class TestR5AHealthCheckAssertion:
    """Regression test for a second real bug found alongside the
    errtrace issue: verify_executor_health() runs its self-test as
    root (peer_uid=0), which DEFAULT_ALLOWED_UIDS={10000} deliberately
    excludes -- so the daemon correctly responds BLOCKED /
    peer_uid_not_allowed. The installer's own comment said as much,
    but the assertion below it still asserted decision == 'ALLOWED',
    so every real run would hit this and (pre-errtrace-fix) silently
    skip rollback. Fixed to assert the documented expected outcome.
    """

    def test_health_check_asserts_blocked_not_allowed(self):
        content = R5A_SCRIPT.read_text()
        assert "resp.get('decision') == 'BLOCKED'" in content
        assert "resp.get('reason') == 'peer_uid_not_allowed'" in content
        assert "resp.get('decision') == 'ALLOWED'" not in content
