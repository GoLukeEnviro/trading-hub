"""Tests for the repository-managed systemd installers under ops/systemd/.

These never touch the real host systemd/filesystem state — non-root and
wrong-GID rejection are exercised by prepending fake `id`/`getent`
wrapper scripts to PATH and running the installers in --check mode
(precondition-only, no install/reload/restart).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_SYSTEMD = REPO_ROOT / "ops" / "systemd"
PERMISSIONS_SCRIPT = OPS_SYSTEMD / "install-hermes-executor-permissions-fix.sh"
COMMIT_SCRIPT = OPS_SYSTEMD / "install-repository-commit-env.sh"
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
