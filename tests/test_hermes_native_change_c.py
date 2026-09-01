"""Tests for scripts/hermes-native-change-c.sh.

This script never runs against the real HermesTrader host from a test: every
filesystem path (`HERMES_NATIVE_ROOT`, `HERMES_NATIVE_STATE_DIR`,
`HERMES_NATIVE_LOCK_FILE`, ...) and every pinned release identity constant
(`HERMES_NATIVE_CHANGE_C_TEST_TARGET_*`, `HERMES_NATIVE_CHANGE_C_TEST_UPSTREAM_REPO`)
is redirected into `tmp_path` and a local git fixture. `stage` is exercised
against a real local bare git remote (no network access to GitHub), using
`uv`/`git`/`python3` exactly as the production path does.

Requires: bash, git, python3, uv, flock on PATH. Run with::

    pytest tests/test_hermes_native_change_c.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "hermes-native-change-c.sh"

STAGE_TIMEOUT = 300

# `stage` shells out to the real `uv` (matching the production install path
# exactly). Not every CI runner has it preinstalled -- this repo's shared
# main-gate.yml does not -- so, like the shellcheck check below, tests that
# actually invoke `stage` skip cleanly instead of failing when `uv` is
# absent, rather than this test file reaching into shared CI config to add
# it. Verified locally with a real `uv` install: 17 passed, 1 skipped
# (shellcheck only).
requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv not installed in this test environment"
)

PYPROJECT_TOML = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "hermes-agent-fixture"
version = "0.21.0"
requires-python = ">=3.9"

[project.optional-dependencies]
all = []

[project.scripts]
hermes = "hermes_agent_fixture:main"

[tool.setuptools]
packages = ["hermes_agent_fixture"]
"""

PACKAGE_INIT = """\
def main() -> None:
    print("fixture-hermes")
"""

VERIFIED_BACKUP_PROOF = {
    "snapshot_id": "abc123",
    "manifest_verified": True,
    "checksums_verified": True,
    "sqlite_integrity_verified": True,
    "restore_verified": True,
    "verified": True,
}


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def _make_bare_fixture_repo(tmp_path: Path, tag: str) -> tuple[Path, str]:
    """Build a tiny installable package, commit it, tag it, and clone it
    bare so `stage` can `git clone --depth 1 --branch <tag> <path>` against
    a real local remote with no network access. Returns (bare_repo_path, sha).
    """
    work_dir = tmp_path / "fixture-src"
    work_dir.mkdir()
    (work_dir / "pyproject.toml").write_text(PYPROJECT_TOML, encoding="utf-8")
    pkg_dir = work_dir / "hermes_agent_fixture"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(PACKAGE_INIT, encoding="utf-8")
    (work_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")
    uv = shutil.which("uv")
    if uv is not None:
        subprocess.run([uv, "lock"], cwd=work_dir, capture_output=True, text=True, check=True)

    _run_git(["init", "-b", "main"], cwd=work_dir)
    _run_git(["add", "."], cwd=work_dir)
    _run_git(["commit", "-m", "fixture init"], cwd=work_dir)
    sha = _run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip()
    _run_git(["tag", tag], cwd=work_dir)

    bare_dir = tmp_path / "upstream.git"
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(work_dir), str(bare_dir)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return bare_dir, sha


def _make_fake_node_archive(tmp_path: Path, version: str = "24.20.0") -> tuple[Path, str]:
    root = tmp_path / f"node-v{version}-linux-x64"
    bindir = root / "bin"
    bindir.mkdir(parents=True)
    node = bindir / "node"
    node.write_text(f"#!/bin/sh\necho v{version}\n", encoding="utf-8")
    node.chmod(0o755)
    npm = bindir / "npm"
    npm.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *' run build '*) mkdir -p hermes_cli/web_dist; echo fixture > hermes_cli/web_dist/index.html;;\n"
        "esac\n",
        encoding="utf-8",
    )
    npm.chmod(0o755)
    archive = tmp_path / f"node-v{version}-linux-x64.tar.xz"
    with tarfile.open(archive, "w:xz") as tf:
        tf.add(root, arcname=root.name)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def _base_env(tmp_path: Path, *, target_sha: str | None = None, target_tag: str = "vtest-0.21.0",
              upstream_repo: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    native_root = tmp_path / "hermes-native"
    state_dir = tmp_path / "state"
    env.update({
        "HERMES_NATIVE_ROOT": str(native_root),
        "HERMES_NATIVE_STATE_DIR": str(state_dir),
        "HERMES_NATIVE_LOCK_FILE": str(tmp_path / "lock" / "change-c.lock"),
        "HERMES_NATIVE_AUDIT_LOG": str(state_dir / "audit.jsonl"),
        "HERMES_NATIVE_PRECUTOVER_MANIFEST": str(state_dir / "pre-cutover-manifest.json"),
        "HERMES_NATIVE_BACKUP_PROOF": str(state_dir / "backup-proof.json"),
        "HERMES_NATIVE_FLEET_BASELINE": str(state_dir / "fleet-baseline.json"),
        "HERMES_NATIVE_REPORT_DIR": str(state_dir / "reports"),
        "HERMES_NATIVE_CHANGE_C_TEST_TARGET_TAG": target_tag,
        "HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION": "0.21.0",
        "HERMES_NATIVE_UV_BIN": shutil.which("uv") or "/missing/uv",
    })
    if target_sha is not None:
        env["HERMES_NATIVE_CHANGE_C_TEST_TARGET_SHA"] = target_sha
    if upstream_repo is not None:
        env["HERMES_NATIVE_CHANGE_C_TEST_UPSTREAM_REPO"] = upstream_repo
    return env


def _run(args: list[str], env: dict[str, str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def _snapshot_tree(root: Path) -> set[tuple[str, str, str]]:
    """Structural snapshot: (relpath, kind, extra). extra is a symlink
    target for symlinks, a sha256 for files, empty for directories.
    Deliberately ignores mtimes (too flaky to compare across fast test runs).
    """
    if not root.exists():
        return set()
    entries: set[tuple[str, str, str]] = set()
    for path in root.rglob("*"):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            entries.add((rel, "symlink", os.readlink(path)))
        elif path.is_dir():
            entries.add((rel, "dir", ""))
        elif path.is_file():
            entries.add((rel, "file", hashlib.sha256(path.read_bytes()).hexdigest()))
    return entries


# ---------------------------------------------------------------------------
# Syntax / static checks
# ---------------------------------------------------------------------------


class TestStaticChecks:
    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_shellcheck_if_available(self):
        shellcheck = subprocess.run(["bash", "-c", "command -v shellcheck"], capture_output=True, text=True)
        if shellcheck.returncode != 0:
            pytest.skip("shellcheck not installed in this environment")
        result = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_no_forbidden_patterns(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "pip install hermes-agent" not in content
        assert "uv pip install" not in content
        assert "UV_NO_CONFIG" not in content
        assert "uv sync --locked" in content
        assert "uv lock --check" in content
        assert re.search(r"curl[^\n]*\|[^\n]*bash", content) is None
        assert "origin/main" not in content
        assert "/usr/local/lib/hermes-agent" not in content
        assert "rm -rf /opt/hermes-native/releases/0.19.0" not in content
        # Broader guard: no `rm -rf`/`rm -f` line may reference the source
        # release version, the source release dir variable, or the bare
        # current symlink variable as a deletion target.
        for line in content.splitlines():
            if re.search(r"\brm\s+-rf?\b", line):
                assert "SOURCE_RELEASE_DIR" not in line
                assert "HERMES_SOURCE_VERSION" not in line
                assert "0.19.0" not in line
                assert re.search(r"rm\s+-rf?\s+\"?\$\{?CURRENT_SYMLINK\}?\"?\s*$", line) is None

    def test_uses_errtrace_for_reliable_cleanup_traps(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "set -Eeuo pipefail" in content

    def test_hermes_root_executor_never_in_stop_or_start_order(self):
        content = SCRIPT.read_text(encoding="utf-8")
        stop_order = re.search(r"STOP_ORDER=\(([^)]*)\)", content).group(1)
        start_order = re.search(r"START_ORDER=\(([^)]*)\)", content).group(1)
        assert "hermes-root-executor" not in stop_order
        assert "hermes-root-executor" not in start_order

    def test_no_daemon_reload(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "daemon-reload" not in content

    def test_exact_release_and_state_contract(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert "0.21.0" in content
        assert "v2026.8.31" in content
        assert "29112bef099274229cadff79cdff7bf7b99c4b77" in content
        assert "/opt/data/hermes" in content
        assert "LEGACY_STATE_PATH_REJECTED" in content
        assert "not cryptographically verified" in content

    def test_probe_contract_is_exact_and_fail_closed(self):
        content = SCRIPT.read_text(encoding="utf-8")
        assert 'before_db[role]["sessions"] == after_db[role]["sessions"]' in content
        assert 'after_db[role]["integrity"] == ["ok"]' in content
        assert 'after_db[role]["foreign_key_rows"] == 0' in content
        assert "cursor[path[-1]] = old" in content
        assert "never the duplicate" in content
        assert "127.0.0.1 --port 29119" in content
        assert "UNEXPECTED_LISTENER" in content

    def test_cutover_is_disabled_in_a1(self):
        content = SCRIPT.read_text(encoding="utf-8")
        match = re.search(r"cmd_cutover\(\) \{(.*?)\n\}", content, re.S)
        assert match and "CUTOVER_SEPARATE_GATE" in match.group(1)
        assert "atomic_symlink_swap" not in match.group(1)


# ---------------------------------------------------------------------------
# plan: never mutates
# ---------------------------------------------------------------------------


class TestPlanNeverMutates:
    def test_plan_on_empty_state_creates_nothing(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        state_dir = Path(env["HERMES_NATIVE_STATE_DIR"])
        lock_file = Path(env["HERMES_NATIVE_LOCK_FILE"])
        assert not native_root.exists()
        assert not state_dir.exists()

        result = _run(["plan"], env)
        assert result.returncode == 0, result.stderr
        assert not native_root.exists()
        assert not state_dir.exists()
        assert not lock_file.exists()

    def test_plan_with_existing_release_leaves_tree_byte_identical(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        (release_019 / "bin" / "hermes").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        (native_root / "current").symlink_to(release_019, target_is_directory=True)

        before = _snapshot_tree(native_root)
        result = _run(["plan"], env)
        after = _snapshot_tree(native_root)

        assert result.returncode == 0, result.stderr
        assert before == after

    def test_dry_run_flag_forces_plan_behavior_for_stage(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        result = _run(["stage", "--dry-run"], env)
        assert result.returncode == 0, result.stderr
        assert not native_root.exists()


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------


class TestStage:
    @requires_uv
    def test_stage_against_fake_remote_creates_release_without_touching_current(self, tmp_path):
        bare_repo, sha = _make_bare_fixture_repo(tmp_path, tag="vtest-0.21.0")
        archive, archive_sha = _make_fake_node_archive(tmp_path)
        env = _base_env(tmp_path, target_sha=sha, target_tag="vtest-0.21.0", upstream_repo=str(bare_repo))
        env["HERMES_NATIVE_CHANGE_C_TEST_NODE_ARCHIVE"] = str(archive)
        env["HERMES_NATIVE_CHANGE_C_TEST_NODE_SHA256"] = archive_sha
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        # Pre-existing 0.19.0 + current, to prove stage never touches them.
        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        (release_019 / "bin" / "hermes").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        (native_root / "current").symlink_to(release_019, target_is_directory=True)
        before_019 = _snapshot_tree(release_019)
        current_target_before = os.readlink(native_root / "current")

        result = _run(["stage"], env, timeout=STAGE_TIMEOUT)
        assert result.returncode == 0, result.stdout + result.stderr

        target_release = native_root / "releases" / "0.21.0"
        assert (target_release / "source" / ".git").exists()
        assert (
            (target_release / "venv" / "bin" / "python").exists()
            or (target_release / "venv" / "bin" / "python3").exists()
        )
        manifest_path = target_release / "RELEASE-MANIFEST.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == "0.21.0"
        assert manifest["tag"] == "vtest-0.21.0"
        assert manifest["sha"] == sha
        assert manifest["source_commit_verified"] is True
        assert manifest["tag_commit_verified"] is True
        assert manifest["lock_gate"] == "PASS"
        assert manifest["node_archive_sha256"] == archive_sha
        assert manifest["dashboard_artifacts_verified"] is True
        assert (target_release / "source" / "hermes_cli" / "web_dist" / "index.html").exists()
        assert (target_release / "bin" / "hermes").exists()

        # current + 0.19.0 must be byte-for-byte untouched.
        assert os.readlink(native_root / "current") == current_target_before
        assert _snapshot_tree(release_019) == before_019

    @requires_uv
    def test_wrong_sha_aborts_with_target_sha_mismatch_and_cleans_up(self, tmp_path):
        bare_repo, real_sha = _make_bare_fixture_repo(tmp_path, tag="vtest-0.21.0")
        bogus_sha = "0" * 40 if real_sha != "0" * 40 else "1" * 40
        env = _base_env(tmp_path, target_sha=bogus_sha, target_tag="vtest-0.21.0", upstream_repo=str(bare_repo))
        native_root = Path(env["HERMES_NATIVE_ROOT"])

        result = _run(["stage"], env, timeout=STAGE_TIMEOUT)

        assert result.returncode != 0
        assert "TARGET_SHA_MISMATCH" in result.stderr
        target_release = native_root / "releases" / "0.21.0"
        assert not target_release.exists()
        assert list((Path(env["HERMES_NATIVE_STATE_DIR"]) / "quarantine").glob("stage-0.21.0-*"))

    def test_node_sha_mismatch_fails(self, tmp_path):
        archive, _ = _make_fake_node_archive(tmp_path)
        env = _base_env(tmp_path)
        env["HERMES_NATIVE_CHANGE_C_TEST_NODE_SHA256"] = "0" * 64
        harness = tmp_path / "node-check.sh"
        harness.write_text(f'source "{SCRIPT}"\nverify_node_archive "{archive}"\n', encoding="utf-8")
        result = subprocess.run(["bash", str(harness)], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert "NODE_SHA_MISMATCH" in result.stderr

    def test_lock_mismatch_fails_without_unlocked_fallback(self, tmp_path):
        bare_repo, sha = _make_bare_fixture_repo(tmp_path, tag="vtest-0.21.0")
        fake_uv = tmp_path / "uv"
        python = tmp_path / "python3.13"
        python.write_text("#!/bin/sh\necho 'Python 3.13.99'\n", encoding="utf-8")
        python.chmod(0o755)
        fake_uv.write_text(
            f'#!/bin/sh\nif [ "$1 $2" = "python find" ]; then echo "{python}"; exit 0; fi\nexit 42\n',
            encoding="utf-8",
        )
        fake_uv.chmod(0o755)
        env = _base_env(tmp_path, target_sha=sha, upstream_repo=str(bare_repo))
        env["HERMES_NATIVE_UV_BIN"] = str(fake_uv)
        result = _run(["stage"], env)
        assert result.returncode != 0
        assert "LOCK_GATE_FAIL" in result.stderr
        assert not (Path(env["HERMES_NATIVE_ROOT"]) / "releases" / "0.21.0").exists()


class TestStatePath:
    def test_legacy_state_path_is_rejected(self, tmp_path):
        env = _base_env(tmp_path)
        env["HERMES_NATIVE_HERMES_HOME"] = "/home/hermes/.hermes"
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        release = native_root / "releases" / "0.19.0"
        (release / "bin").mkdir(parents=True)
        (native_root / "current").symlink_to(release, target_is_directory=True)
        harness = tmp_path / "state-check.sh"
        harness.write_text(f'source "{SCRIPT}"\nassert_source_runtime_unchanged\n', encoding="utf-8")
        result = subprocess.run(["bash", str(harness)], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert "LEGACY_STATE_PATH_REJECTED" in result.stderr


# ---------------------------------------------------------------------------
# pre-cutover
# ---------------------------------------------------------------------------


class TestPreCutover:
    def test_fails_without_backup_proof(self, tmp_path):
        env = _base_env(tmp_path)
        result = _run(["pre-cutover"], env)
        assert result.returncode != 0
        assert "BACKUP_PROOF_MISSING" in result.stderr

    def test_fails_with_unverified_backup_proof(self, tmp_path):
        env = _base_env(tmp_path)
        backup_proof = Path(env["HERMES_NATIVE_BACKUP_PROOF"])
        backup_proof.parent.mkdir(parents=True)
        backup_proof.write_text(json.dumps({"backup_id": "x", "verified": False}), encoding="utf-8")
        result = _run(["pre-cutover"], env)
        assert result.returncode != 0
        assert "BACKUP_PROOF_INVALID" in result.stderr

    @requires_uv
    def test_passes_and_writes_manifest_when_gates_are_green(self, tmp_path):
        bare_repo, sha = _make_bare_fixture_repo(tmp_path, tag="vtest-0.21.0")
        archive, archive_sha = _make_fake_node_archive(tmp_path)
        env = _base_env(tmp_path, target_sha=sha, target_tag="vtest-0.21.0", upstream_repo=str(bare_repo))
        env["HERMES_NATIVE_CHANGE_C_TEST_NODE_ARCHIVE"] = str(archive)
        env["HERMES_NATIVE_CHANGE_C_TEST_NODE_SHA256"] = archive_sha
        native_root = Path(env["HERMES_NATIVE_ROOT"])

        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        (release_019 / "bin" / "hermes").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        (native_root / "current").symlink_to(release_019, target_is_directory=True)

        backup_proof = Path(env["HERMES_NATIVE_BACKUP_PROOF"])
        backup_proof.parent.mkdir(parents=True)
        backup_proof.write_text(json.dumps(VERIFIED_BACKUP_PROOF), encoding="utf-8")

        stage_result = _run(["stage"], env, timeout=STAGE_TIMEOUT)
        assert stage_result.returncode == 0, stage_result.stdout + stage_result.stderr

        result = _run(["pre-cutover"], env)
        assert result.returncode == 0, result.stdout + result.stderr

        manifest_path = Path(env["HERMES_NATIVE_PRECUTOVER_MANIFEST"])
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["gates_passed"] is True
        assert manifest["previous_version"] == "0.19.0"
        assert manifest["previous_symlink_target"].endswith("0.19.0")


# ---------------------------------------------------------------------------
# cutover
# ---------------------------------------------------------------------------


class TestCutover:
    def test_fails_when_pre_cutover_state_file_is_missing(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        (release_019 / "bin" / "hermes").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        (native_root / "current").symlink_to(release_019, target_is_directory=True)

        manifest_path = Path(env["HERMES_NATIVE_PRECUTOVER_MANIFEST"])
        assert not manifest_path.exists()

        result = _run(["cutover"], env)
        assert result.returncode != 0
        assert "CUTOVER_SEPARATE_GATE" in result.stderr
        # current must remain untouched since the gate failed before any
        # service stop / symlink swap was attempted.
        assert os.readlink(native_root / "current") == str(release_019)


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_fails_hard_without_manifest_and_changes_nothing(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        (release_019 / "bin" / "hermes").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        (native_root / "current").symlink_to(release_019, target_is_directory=True)
        before = _snapshot_tree(native_root)

        manifest_path = Path(env["HERMES_NATIVE_PRECUTOVER_MANIFEST"])
        assert not manifest_path.exists()

        result = _run(["rollback"], env)

        assert result.returncode != 0
        assert "ROLLBACK_MANIFEST_MISSING" in result.stderr
        assert _snapshot_tree(native_root) == before

    def test_restores_state_pointer_services_and_quarantines_failed_state(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        release_019 = native_root / "releases" / "0.19.0"
        (release_019 / "bin").mkdir(parents=True)
        hermes = release_019 / "bin" / "hermes"
        hermes.write_text("#!/bin/sh\necho 'Hermes Agent v0.19.0'\n", encoding="utf-8")
        hermes.chmod(0o755)
        (native_root / "current").symlink_to(release_019, target_is_directory=True)

        live = tmp_path / "live-hermes"
        pre = tmp_path / "pre-state"
        live.mkdir()
        pre.mkdir()
        (live / "marker").write_text("failed-0.21", encoding="utf-8")
        (pre / "marker").write_text("pre-0.19", encoding="utf-8")
        env["HERMES_NATIVE_HERMES_HOME"] = str(live)
        env["HERMES_NATIVE_QUARANTINE_DIR"] = str(tmp_path / "quarantine")

        manifest = Path(env["HERMES_NATIVE_PRECUTOVER_MANIFEST"])
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({
            "previous_symlink_target": str(release_019),
            "pre_upgrade_state_path": str(pre),
        }), encoding="utf-8")
        fake_bin = tmp_path / "fake-bin"
        fake_bin.mkdir()
        systemctl = fake_bin / "systemctl"
        systemctl.write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path / "services.log"}"\n', encoding="utf-8")
        systemctl.chmod(0o755)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        result = _run(["rollback"], env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (live / "marker").read_text(encoding="utf-8") == "pre-0.19"
        quarantined = list((tmp_path / "quarantine").glob("failed-0.21-state-*"))
        assert len(quarantined) == 1
        assert (quarantined[0] / "marker").read_text(encoding="utf-8") == "failed-0.21"
        assert (native_root / "current").resolve() == release_019.resolve()
        service_lines = (tmp_path / "services.log").read_text(encoding="utf-8").splitlines()
        assert service_lines == [
            "stop hermes-desktop-serve.service", "stop hermes-dashboard.service",
            "stop hermes-gateway.service", "start hermes-gateway.service",
            "start hermes-dashboard.service", "start hermes-desktop-serve.service",
        ]


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------


class TestSecretRedaction:
    def test_report_never_leaks_env_file_secret_values(self, tmp_path):
        env = _base_env(tmp_path)
        native_root = Path(env["HERMES_NATIVE_ROOT"])
        target_release = native_root / "releases" / "0.21.0"
        target_release.mkdir(parents=True)
        (target_release / ".env").write_text(
            "API_KEY=xxxsecret\nDB_PASSWORD=hunter2\nHERMES_PROFILE=trading-hub-orchestrator\n",
            encoding="utf-8",
        )

        result = _run(["report"], env)
        assert result.returncode == 0, result.stdout + result.stderr
        report_path = Path(result.stdout.strip())
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")

        assert "xxxsecret" not in content
        assert "hunter2" not in content
        assert "<REDACTED>" in content
        # Non-secret keys must still be visible -- redaction must be
        # targeted, not a blanket wipe of the whole file.
        assert "HERMES_PROFILE=trading-hub-orchestrator" in content

    def test_redact_secrets_function_direct(self, tmp_path):
        harness = tmp_path / "harness.sh"
        harness.write_text(
            f'source "{SCRIPT}"\n'
            'printf "API_KEY=xxxsecret\\nMY_TOKEN=abc123\\nHERMES_PROFILE=foo\\n" | redact_secrets\n',
            encoding="utf-8",
        )
        env = _base_env(tmp_path)
        result = subprocess.run(
            ["bash", str(harness)], capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode == 0, result.stderr
        assert "xxxsecret" not in result.stdout
        assert "abc123" not in result.stdout
        assert "API_KEY=<REDACTED>" in result.stdout
        assert "MY_TOKEN=<REDACTED>" in result.stdout
        assert "HERMES_PROFILE=foo" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
