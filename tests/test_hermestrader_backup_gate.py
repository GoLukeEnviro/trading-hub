from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "ops/hermes/hermestrader-backup.sh"
RESTORE_SCRIPT = REPO_ROOT / "ops/hermes/hermestrader_backup_restore_proof.py"
SQLITE_SNAPSHOT_SCRIPT = REPO_ROOT / "ops/hermes/hermestrader_sqlite_snapshot.py"
EXCLUDES = REPO_ROOT / "ops/hermes/hermestrader-backup-excludes.txt"

ROOT_DATABASES = (
    "state.db",
    "kanban.db",
    "verification_evidence.db",
    "projects.db",
)
PROFILE_DATABASES = (
    "state.db",
    "cron/executions.db",
    "memory_store.db",
    "projects.db",
    "verification_evidence.db",
)


def create_db(path: Path, *, corrupt: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        path.write_bytes(b"not a sqlite database")
        return
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE proof (value TEXT NOT NULL)")
        database.execute("INSERT INTO proof VALUES ('ok')")


def create_canonical_hermes_state(root: Path) -> None:
    for relative in ROOT_DATABASES:
        create_db(root / relative)
    profile = root / "profiles/trading-hub-orchestrator"
    for relative in PROFILE_DATABASES:
        create_db(profile / relative)


def discovery(root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "HERMESTRADER_HERMES_ROOT": str(root),
        "HERMESTRADER_PROFILE": "trading-hub-orchestrator",
    }
    return subprocess.run(
        [str(BACKUP_SCRIPT), "discover-host"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_canonical_sqlite_discovery_is_exact(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    create_canonical_hermes_state(root)

    result = discovery(root)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["count"] == 9
    assert {item["source"] for item in payload["databases"]} == {
        str(root / relative) for relative in ROOT_DATABASES
    } | {
        str(root / "profiles/trading-hub-orchestrator" / relative)
        for relative in PROFILE_DATABASES
    }


@pytest.mark.parametrize(
    "relative",
    [
        "backups/old.db",
        "backup/old.db",
        "state-snapshots/old.db",
        "snapshots/old.db",
        "recovery/old.db",
        "restore/old.db",
        "restored/old.db",
        "cache/old.db",
        "caches/old.db",
        "quarantine/old.db",
        "tmp/old.db",
        "temp/old.db",
        "tests/fixtures/old.db",
        "probes/old.db",
        "previous-upgrade-copies/old.db",
    ],
)
def test_historical_and_temporary_databases_are_ignored(
    tmp_path: Path, relative: str
) -> None:
    root = tmp_path / "hermes"
    create_canonical_hermes_state(root)
    create_db(root / relative)

    result = discovery(root)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["count"] == 9


def test_unknown_database_in_active_namespace_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    create_canonical_hermes_state(root)
    create_db(root / "profiles/trading-hub-orchestrator/new-runtime.db")

    result = discovery(root)

    assert result.returncode != 0
    assert "UNKNOWN_PRODUCTION_DB" in result.stderr


def test_legacy_state_root_is_rejected(tmp_path: Path) -> None:
    legacy = tmp_path / "home-hermes" / ".hermes"
    create_canonical_hermes_state(legacy)

    result = discovery(legacy)

    assert result.returncode != 0
    assert "UNEXPECTED_STATE_ROOT" in result.stderr


def test_expected_database_symlink_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    create_canonical_hermes_state(root)
    outside = tmp_path / "outside.db"
    create_db(outside)
    (root / "state.db").unlink()
    (root / "state.db").symlink_to(outside)

    result = discovery(root)

    assert result.returncode != 0
    assert "DATABASE_PATH_ESCAPE" in result.stderr


def test_rsync_excludes_cover_recursive_backup_namespaces() -> None:
    content = EXCLUDES.read_text(encoding="utf-8")
    for directory in (
        "backups",
        "backup",
        "state-snapshots",
        "snapshots",
        "recovery",
        "restore",
        "restored",
        "cache",
        "caches",
        "quarantine",
        "tmp",
        "temp",
        "tests",
        "probes",
        "previous-upgrade-copies",
    ):
        assert f"**/{directory}/**" in content


def test_rsync_source_capture_does_not_recursively_capture_backup_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "config.yaml").write_text("schema_version: 33\n")
    recursive = source / "backups/previous/opt/data/hermes"
    recursive.mkdir(parents=True)
    (recursive / "config.yaml").write_text("stale\n")

    subprocess.run(
        [
            "rsync",
            "-a",
            f"--exclude-from={EXCLUDES}",
            f"{source}/",
            f"{destination}/",
        ],
        check=True,
    )

    assert (destination / "config.yaml").is_file()
    assert not (destination / "backups").exists()


def test_full_step_sqlite_snapshot_completes_with_active_wal_writer(tmp_path: Path) -> None:
    source = tmp_path / "active.db"
    destination = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as database:
        assert database.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        database.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, payload BLOB NOT NULL)")
        database.executemany(
            "INSERT INTO events(payload) VALUES (?)",
            [(b"x" * 4096,) for _ in range(2048)],
        )

    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sqlite3,sys,time; "
                "db=sqlite3.connect(sys.argv[1]); "
                "[(db.execute('INSERT INTO events(payload) VALUES (?)',(b\"w\"*4096,)),db.commit(),time.sleep(.001)) "
                "for _ in range(10000)]"
            ),
            str(source),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.1)
        with sqlite3.connect(source) as database:
            count_before = database.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        result = subprocess.run(
            [str(SQLITE_SNAPSHOT_SCRIPT), str(source), str(destination)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
        with sqlite3.connect(source) as database:
            count_after = database.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        writer.terminate()
        writer.wait(timeout=10)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["method"] == "sqlite_backup_full_step"
    assert payload["integrity_check"] == "ok"
    assert count_after > count_before
    with sqlite3.connect(destination) as database:
        snapshot_count = database.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert database.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert count_before <= snapshot_count <= count_after


def test_sqlite_snapshot_rejects_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "destination.db"
    create_db(source)
    destination.write_bytes(b"do not overwrite")

    result = subprocess.run(
        [str(SQLITE_SNAPSHOT_SCRIPT), str(source), str(destination)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "DESTINATION_EXISTS" in result.stderr
    assert destination.read_bytes() == b"do not overwrite"


def test_backup_pipeline_uses_bounded_full_step_snapshot_tool() -> None:
    content = BACKUP_SCRIPT.read_text(encoding="utf-8")

    assert "HERMESTRADER_SQLITE_SNAPSHOT_TOOL" in content
    assert "HERMESTRADER_SQLITE_SNAPSHOT_TIMEOUT_SECONDS" in content
    assert 'sqlite3 -readonly "$_source" ".timeout 30000" ".backup' not in content


def test_internal_watchdog_reports_failed_timeout(tmp_path: Path) -> None:
    state = tmp_path / "state"
    reports = tmp_path / "reports"
    env = os.environ | {
        "HERMESTRADER_BACKUP_STATE_DIR": str(state),
        "HERMESTRADER_BACKUP_REPORT_DIR": str(reports),
        "HERMESTRADER_BACKUP_TIMEOUT_SECONDS": "1",
        "HERMESTRADER_BACKUP_TEST_HOLD_SECONDS": "30",
    }

    result = subprocess.run(
        [str(BACKUP_SCRIPT), "test-watchdog"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )

    assert result.returncode == 124
    report = json.loads((state / "latest-report.json").read_text())
    assert report["status"] == "FAILED"
    assert report["reason"] == "TIMEOUT"
    assert report["exit_code"] == 124


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
def test_terminating_signals_never_report_success(tmp_path: Path, sig: signal.Signals) -> None:
    state = tmp_path / "state"
    reports = tmp_path / "reports"
    env = os.environ | {
        "HERMESTRADER_BACKUP_STATE_DIR": str(state),
        "HERMESTRADER_BACKUP_REPORT_DIR": str(reports),
        "HERMESTRADER_BACKUP_TIMEOUT_SECONDS": "60",
        "HERMESTRADER_BACKUP_TEST_HOLD_SECONDS": "30",
    }
    process = subprocess.Popen(
        [str(BACKUP_SCRIPT), "test-signal-wait"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.25)
    process.send_signal(sig)
    process.communicate(timeout=10)

    assert process.returncode != 0
    report = json.loads((state / "latest-report.json").read_text())
    assert report["status"] == "FAILED"
    assert report["reason"] == f"SIGNAL_{sig.name.removeprefix('SIG')}"


def build_restore_fixture(
    tmp_path: Path, *, corrupt_db: bool = False, corrupt_checksum: bool = False
) -> tuple[Path, Path, str]:
    snapshot_id = "f" * 64
    staging_path = "/var/lib/hermestrader-backup/work/run/staging"
    fixture_root = tmp_path / "fixture"
    staging = fixture_root / staging_path.lstrip("/")
    host_dir = staging / "sqlite/host/opt/data/hermes"
    profile_dir = host_dir / "profiles/trading-hub-orchestrator"
    records: list[dict[str, str]] = []

    for relative in ROOT_DATABASES:
        export = host_dir / relative
        create_db(export, corrupt=corrupt_db and relative == "state.db")
        records.append(
            {
                "name": f"root-{relative}",
                "source": f"/opt/data/hermes/{relative}",
                "export": export.relative_to(staging).as_posix(),
                "type": "hermes-root",
                "snapshot_method": "sqlite_backup_full_step",
            }
        )
    for relative in PROFILE_DATABASES:
        export = profile_dir / relative
        create_db(export)
        records.append(
            {
                "name": f"profile-{relative}",
                "source": f"/opt/data/hermes/profiles/trading-hub-orchestrator/{relative}",
                "export": export.relative_to(staging).as_posix(),
                "type": "hermes-profile",
                "snapshot_method": "sqlite_backup_full_step",
            }
        )
    freqtrade_sources = {
        "freqforge": (
            "container:hermestrader-dryrun-freqtrade-freqforge-1:"
            "/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite"
        ),
        "freqforge-canary": (
            "container:hermestrader-dryrun-freqtrade-freqforge-canary-1:"
            "/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"
        ),
        "regime-hybrid": (
            "container:hermestrader-dryrun-freqtrade-regime-hybrid-1:"
            "/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite"
        ),
    }
    for name, source in freqtrade_sources.items():
        export = staging / f"sqlite/freqtrade/tradesv3.{name}.sqlite"
        create_db(export)
        records.append(
            {
                "name": name,
                "source": source,
                "export": export.relative_to(staging).as_posix(),
                "type": "freqtrade-dry-run",
                "snapshot_method": "sqlite_backup_full_step",
            }
        )

    inventory = staging / "system/sqlite-inventory.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    manifest_lines = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        relative = path.relative_to(staging).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  ./{relative}")
    if corrupt_checksum:
        manifest_lines[0] = f"{'0' * 64}  {manifest_lines[0].split('  ', 1)[1]}"
    (staging / "SHA256SUMS").write_text("\n".join(manifest_lines) + "\n")

    report = tmp_path / "backup-report.json"
    report.write_text(
        json.dumps(
            {
                "timestamp": "20260901T120000Z",
                "status": "SUCCESS",
                "exit_code": 0,
                "snapshot_id": snapshot_id,
                "source_root": "/opt/data/hermes",
                "staging_path": staging_path,
                "sqlite_expected": 12,
                "sqlite_actual": 12,
            }
        )
    )
    return fixture_root, report, snapshot_id


def make_fake_restic(tmp_path: Path, fixture_root: Path, *, fail: bool = False) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    restic = bin_dir / "restic"
    if fail:
        restic.write_text("#!/bin/sh\nexit 23\n")
    else:
        restic.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "target=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = '--target' ]; then target=$2; shift 2; else shift; fi\n"
            "done\n"
            f"cp -a {fixture_root}/. \"$target\"/\n"
        )
    restic.chmod(0o755)
    return bin_dir


def run_restore(
    tmp_path: Path,
    fixture_root: Path,
    report: Path,
    snapshot_id: str,
    *,
    fail_restic: bool = False,
) -> subprocess.CompletedProcess[str]:
    state = tmp_path / "proof-state"
    restic_env = tmp_path / "restic-env"
    restic_env.write_text("RESTIC_REPOSITORY=test\nRESTIC_PASSWORD=test\n")
    bin_dir = make_fake_restic(tmp_path, fixture_root, fail=fail_restic)
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(
        [
            str(RESTORE_SCRIPT),
            "--snapshot-id",
            snapshot_id,
            "--backup-report",
            str(report),
            "--state-dir",
            str(state),
            "--restic-env",
            str(restic_env),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_restore_rejects_snapshot_id_not_bound_to_backup_report(tmp_path: Path) -> None:
    fixture, report, _snapshot_id = build_restore_fixture(tmp_path)

    result = run_restore(tmp_path, fixture, report, "e" * 64)

    assert result.returncode != 0
    assert "SNAPSHOT_ID_MISMATCH" in result.stderr
    assert not (tmp_path / "proof-state/backup-proof.json").exists()


def test_restore_failure_produces_verified_false_report(tmp_path: Path) -> None:
    fixture, report, snapshot_id = build_restore_fixture(tmp_path)
    existing_proof = tmp_path / "proof-state/backup-proof.json"
    existing_proof.parent.mkdir(parents=True)
    existing_proof.write_text('{"verified":true,"snapshot_id":"previous"}\n')

    result = run_restore(tmp_path, fixture, report, snapshot_id, fail_restic=True)

    assert result.returncode != 0
    failure_reports = list((tmp_path / "proof-state/restore-proof").glob("*/restore-report.json"))
    assert len(failure_reports) == 1
    assert json.loads(failure_reports[0].read_text())["verified"] is False
    assert json.loads(existing_proof.read_text())["snapshot_id"] == "previous"


def test_checksum_failure_never_writes_positive_proof(tmp_path: Path) -> None:
    fixture, report, snapshot_id = build_restore_fixture(tmp_path, corrupt_checksum=True)

    result = run_restore(tmp_path, fixture, report, snapshot_id)

    assert result.returncode != 0
    assert "CHECKSUM_FAILED" in result.stderr
    assert not (tmp_path / "proof-state/backup-proof.json").exists()


def test_sqlite_integrity_failure_never_writes_positive_proof(tmp_path: Path) -> None:
    fixture, report, snapshot_id = build_restore_fixture(tmp_path, corrupt_db=True)

    result = run_restore(tmp_path, fixture, report, snapshot_id)

    assert result.returncode != 0
    assert "SQLITE_INTEGRITY_FAILED" in result.stderr
    assert not (tmp_path / "proof-state/backup-proof.json").exists()


def test_successful_restore_writes_atomic_verified_proof(tmp_path: Path) -> None:
    fixture, report, snapshot_id = build_restore_fixture(tmp_path)

    result = run_restore(tmp_path, fixture, report, snapshot_id)

    assert result.returncode == 0, result.stderr
    proof = json.loads((tmp_path / "proof-state/backup-proof.json").read_text())
    assert proof["version"] == 1
    assert proof["snapshot_id"] == snapshot_id
    assert proof["source_root"] == "/opt/data/hermes"
    assert len(proof["sqlite_databases"]) == 12
    assert proof["manifest_verified"] is True
    assert proof["checksums_verified"] is True
    assert proof["sqlite_integrity_verified"] is True
    assert proof["restore_verified"] is True
    assert proof["verified"] is True
    assert not list((tmp_path / "proof-state").glob("*.tmp*"))
