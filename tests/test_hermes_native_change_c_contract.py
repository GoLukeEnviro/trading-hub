"""Failure-injection tests for the Hermes A2 state/rollback contract."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml

from ops.hermes import hermes_native_change_c as contract

PROFILE = "trading-hub-orchestrator"


def _database(path: Path, schema: int = 22, sessions: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_version VALUES (?)", (schema,))
    connection.execute("CREATE TABLE sessions(id INTEGER PRIMARY KEY, value TEXT)")
    connection.executemany("INSERT INTO sessions(value) VALUES (?)", [(f"s{i}",) for i in range(sessions)])
    connection.commit()
    connection.close()


def _state(root: Path, *, schema: int = 22, config_schema: int = 33) -> Path:
    for home, sessions in ((root, 3), (root / "profiles" / PROFILE, 7)):
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "_config_version": config_schema,
                    "display": {"personality": "technical", "background_process_notifications": "all"},
                    "delegation": {"max_iterations": 50},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        _database(home / "state.db", schema=schema, sessions=sessions)
    (root / "ordinary.txt").write_text("rollback me", encoding="utf-8")
    return root


def _snapshot_helper(path: Path) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sqlite3,sys\n"
        "s=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro',uri=True)\n"
        "d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _metadata(tmp_path: Path) -> dict[str, str]:
    return {
        "source_release_version": "0.19.0",
        "source_release_symlink_target": "/opt/hermes-native/releases/0.19.0",
        "target_release_version": "0.21.0",
        "target_release_commit": "29112bef099274229cadff79cdff7bf7b99c4b77",
        "backup_proof_reference": str(tmp_path / "backup-proof.json"),
        "r5a_fleet_provenance_proof_reference": str(tmp_path / "fleet-proof.json"),
        "fleet_image_lock_reference": "ops/hermes/hermestrader-dryrun-images.lock.json",
        "operator": "fixture",
    }


def _snapshot(tmp_path: Path):
    source = _state(tmp_path / "source")
    return contract.create_pre_upgrade_snapshot(
        source,
        tmp_path / "snapshots",
        PROFILE,
        _snapshot_helper(tmp_path / "sqlite-snapshot"),
        _metadata(tmp_path),
    )


def _precutover_value(snapshot: Path, digest: str, manifest: dict, tmp_path: Path) -> dict:
    return {
        "previous_symlink_target": "/opt/hermes-native/releases/0.19.0",
        "previous_version": "0.19.0",
        "target_version": "0.21.0",
        "target_sha": "29112bef099274229cadff79cdff7bf7b99c4b77",
        "pre_upgrade_state_path": str(snapshot),
        "pre_upgrade_state_manifest_sha256": digest,
        "root_session_count": manifest["root_session_count"],
        "profile_session_count": manifest["profile_session_count"],
        "backup_proof_ref": str(tmp_path / "backup-proof.json"),
        "fleet_baseline_ref": str(tmp_path / "fleet-proof.json"),
        "fleet_image_lock_ref": "ops/hermes/hermestrader-dryrun-images.lock.json",
        "timestamp": "2026-09-09T00:00:00+00:00",
        "operator": "fixture",
        "gates_passed": True,
    }


def test_snapshot_is_complete_integrity_bound_and_sqlite_safe(tmp_path: Path) -> None:
    source = _state(tmp_path / "source")
    (source / "state.db-wal").write_bytes(b"stale-live-wal")
    snapshot, digest, manifest = contract.create_pre_upgrade_snapshot(
        source,
        tmp_path / "snapshots",
        PROFILE,
        _snapshot_helper(tmp_path / "sqlite-snapshot"),
        _metadata(tmp_path),
    )
    assert contract.verify_pre_upgrade_snapshot(snapshot, digest, PROFILE) == manifest
    assert manifest["root_config_schema"] == 33
    assert manifest["profile_config_schema"] == 33
    assert manifest["root_db_schema"] == 22
    assert manifest["profile_db_schema"] == 22
    assert manifest["root_session_count"] == 3
    assert manifest["profile_session_count"] == 7
    assert manifest["root_sqlite_integrity"] == ["ok"]
    assert manifest["profile_fk_violation_count"] == 0
    assert not (snapshot / "state.db-wal").exists()
    assert all(not (entry.get("mode", 0) & 0o222) for entry in manifest["inventory"] if entry["type"] == "file")


@pytest.mark.parametrize("missing", ["pre_upgrade_state_path", "pre_upgrade_state_manifest_sha256"])
def test_incomplete_precutover_manifest_is_blocked(tmp_path: Path, missing: str) -> None:
    snapshot, digest, snapshot_manifest = _snapshot(tmp_path)
    value = _precutover_value(snapshot, digest, snapshot_manifest, tmp_path)
    value.pop(missing)
    with pytest.raises(contract.ContractError, match="PRECUTOVER_MANIFEST_INCOMPLETE"):
        contract.write_precutover_manifest(tmp_path / "precutover.json", value, PROFILE)


def test_nonexistent_snapshot_is_blocked(tmp_path: Path) -> None:
    snapshot, digest, snapshot_manifest = _snapshot(tmp_path)
    value = _precutover_value(snapshot, digest, snapshot_manifest, tmp_path)
    value["pre_upgrade_state_path"] = str(tmp_path / "missing")
    with pytest.raises(contract.ContractError, match="PRE_UPGRADE_STATE_MANIFEST_INVALID"):
        contract.write_precutover_manifest(tmp_path / "precutover.json", value, PROFILE)


def test_wrong_manifest_hash_is_blocked(tmp_path: Path) -> None:
    snapshot, digest, snapshot_manifest = _snapshot(tmp_path)
    value = _precutover_value(snapshot, digest, snapshot_manifest, tmp_path)
    value["pre_upgrade_state_manifest_sha256"] = "0" * 64
    with pytest.raises(contract.ContractError, match="MANIFEST_HASH_MISMATCH"):
        contract.write_precutover_manifest(tmp_path / "precutover.json", value, PROFILE)


def test_corrupt_snapshot_is_blocked(tmp_path: Path) -> None:
    snapshot, digest, _ = _snapshot(tmp_path)
    ordinary = snapshot / "ordinary.txt"
    ordinary.chmod(0o600)
    ordinary.write_text("corrupt", encoding="utf-8")
    with pytest.raises(contract.ContractError, match="INVENTORY_MISMATCH"):
        contract.verify_pre_upgrade_snapshot(snapshot, digest, PROFILE)


def test_precutover_manifest_is_atomic_0600_and_session_bound(tmp_path: Path) -> None:
    snapshot, digest, snapshot_manifest = _snapshot(tmp_path)
    value = _precutover_value(snapshot, digest, snapshot_manifest, tmp_path)
    path = tmp_path / "precutover.json"
    contract.write_precutover_manifest(path, value, PROFILE)
    assert path.stat().st_mode & 0o777 == 0o600
    bad = json.loads(path.read_text(encoding="utf-8"))
    bad["root_session_count"] += 1
    contract.atomic_write_json(path, bad)
    with pytest.raises(contract.ContractError, match="ROOT_SESSION_BASELINE_MISMATCH"):
        contract.validate_precutover_manifest(path, PROFILE)


def test_migration_uses_runtime_counts_and_preserves_operational_values(monkeypatch, tmp_path: Path) -> None:
    state = _state(tmp_path / "state")

    def fake_run(argv, *, env, **_kwargs):
        home = Path(env["HERMES_HOME"])
        if "migrate_config" in argv[2]:
            config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
            config = {"_config_version": 39, "display": {}, "delegation": {}}
            (home / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        else:
            database = Path(argv[-1])
            connection = sqlite3.connect(database)
            connection.execute("UPDATE schema_version SET version=26")
            connection.commit()
            connection.close()
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(contract.subprocess, "run", fake_run)
    result = contract.migrate_state(state, PROFILE, Path("/target/python"))
    assert result["migration_verified"] is True
    assert result["before"]["root"]["database"]["sessions"] == 3
    assert result["after"]["profile"]["database"]["sessions"] == 7
    assert result["before"]["root"]["operational_config"] == result["after"]["root"]["operational_config"]


def test_source_schema_mismatch_is_blocked_before_migration(tmp_path: Path) -> None:
    state = _state(tmp_path / "state", config_schema=32)
    with pytest.raises(contract.ContractError, match="SOURCE_CONFIG_SCHEMA_MISMATCH"):
        contract.migrate_state(state, PROFILE, Path("/target/python"))


def test_session_drift_is_blocked(monkeypatch, tmp_path: Path) -> None:
    state = _state(tmp_path / "state")

    def fake_run(argv, *, env, **_kwargs):
        home = Path(env["HERMES_HOME"])
        if "migrate_config" in argv[2]:
            config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
            config["_config_version"] = 39
            (home / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        else:
            connection = sqlite3.connect(argv[-1])
            connection.execute("UPDATE schema_version SET version=26")
            connection.execute("DELETE FROM sessions WHERE id=(SELECT MAX(id) FROM sessions)")
            connection.commit()
            connection.close()
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(contract.subprocess, "run", fake_run)
    with pytest.raises(contract.ContractError, match="MIGRATION_INVARIANT_FAILED"):
        contract.migrate_state(state, PROFILE, Path("/target/python"))


@pytest.mark.parametrize(
    "failure_code",
    [
        "SERVICE_STOP_FAILED",
        "PREUPGRADE_STATE_SNAPSHOT_FAILED",
        "PRODUCTION_STATE_MIGRATION_FAILED",
        "CONFIG_MIGRATION_FAILED",
        "DB_MIGRATION_FAILED",
        "MIGRATION_INVARIANT_FAILED",
        "STATE_INVARIANT_ERROR",
        "SYMLINK_SWAP_FAILED",
        "SERVICE_START_FAILED",
        "BACKEND_VERSION_MISMATCH",
        "BACKEND_HEALTH_FAILURE",
        "UNEXPECTED_PUBLIC_BIND",
        "ROOT_EXECUTOR_SOCKET_MISSING",
        "R5A_PARITY_LOSS",
    ],
)
def test_every_post_mutation_fatal_routes_to_automatic_rollback(tmp_path: Path, failure_code: str) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "hermes-native-change-c.sh"
    harness = tmp_path / "rollback-route.sh"
    marker = tmp_path / "rollback-trigger"
    harness.write_text(
        f'source "{script}"\n'
        f'perform_rollback() {{ printf "%s" "$1" > "{marker}"; }}\n'
        "TRANSACTION_MUTATED=true\n"
        f"fatal {failure_code} injected\n",
        encoding="utf-8",
    )
    environment = os.environ | {
        "HERMES_NATIVE_STATE_DIR": str(tmp_path / "change-state"),
        "HERMES_NATIVE_AUDIT_LOG": str(tmp_path / "audit.jsonl"),
        "HERMES_NATIVE_LOCK_FILE": str(tmp_path / "change.lock"),
    }
    result = subprocess.run(["bash", str(harness)], env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert marker.read_text(encoding="utf-8") == failure_code


def _release_manifest(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "RELEASE-MANIFEST.json").write_text(
        json.dumps(
            {
                "version": "0.21.0",
                "tag": "v2026.8.31",
                "sha": "29112bef099274229cadff79cdff7bf7b99c4b77",
                "source_commit_verified": True,
                "tag_commit_verified": True,
                "lock_gate": "PASS",
                "dashboard_artifacts_verified": True,
                "node_archive_sha256": "2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2",
            }
        ),
        encoding="utf-8",
    )


def _fake_runtime_tools(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    service_log = tmp_path / "services.log"
    (fake_bin / "systemctl").write_text(
        f'#!/bin/sh\necho "$*" >> "{service_log}"\n'
        'if [ "$1" = is-active ]; then [ "${3:-}" = hermes-root-executor.service ] && exit 0; exit 1; fi\n',
        encoding="utf-8",
    )
    (fake_bin / "systemctl").chmod(0o755)
    r5a = tmp_path / "r5a.py"
    r5a.write_text(
        "import json,os\n"
        "p=os.environ.get('R5A_PROOF_OUTPUT')\n"
        "if p: open(p,'w').write(json.dumps({'verified':True,'freqtrade_dry_run_count':4}))\n"
        "print('R5A_PROVENANCE_GATE=PASS')\n",
        encoding="utf-8",
    )
    return fake_bin, r5a


def test_happy_path_orchestrates_019_to_021_start_and_validate(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "hermes-native-change-c.sh"
    native = tmp_path / "native"
    source = native / "releases" / "0.19.0"
    target = native / "releases" / "0.21.0"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "hermes").write_text("#!/bin/sh\necho 0.19.0\n", encoding="utf-8")
    (source / "bin" / "hermes").chmod(0o755)
    _release_manifest(target)
    (target / "venv" / "bin").mkdir(parents=True)
    (target / "venv" / "bin" / "python").write_text('#!/bin/sh\nexec /usr/bin/python3 "$@"\n', encoding="utf-8")
    (target / "venv" / "bin" / "python").chmod(0o755)
    (native / "current").symlink_to(source, target_is_directory=True)
    state = _state(tmp_path / "live")
    state_tool = tmp_path / "state-tool.py"
    state_tool.write_text(
        "import pathlib,sys\n"
        "args=sys.argv\n"
        "\nif 'migrate' in args:\n"
        " p=pathlib.Path(args[args.index('--output')+1])\n"
        " p.parent.mkdir(parents=True,exist_ok=True)\n"
        " p.write_text('{}')\n",
        encoding="utf-8",
    )
    fake_bin, r5a = _fake_runtime_tools(tmp_path)
    precutover = tmp_path / "precutover.json"
    precutover.write_text("{}", encoding="utf-8")
    change_state = tmp_path / "change-state"
    change_state.mkdir()
    (change_state / "backup-proof.json").write_text(
        json.dumps(
            {
                "snapshot_id": "fixture",
                "manifest_verified": True,
                "checksums_verified": True,
                "sqlite_integrity_verified": True,
                "restore_verified": True,
                "verified": True,
            }
        ),
        encoding="utf-8",
    )
    for name in ("migration-probe.json", "rollback-proof.json"):
        (change_state / name).write_text(json.dumps({"verified": True}), encoding="utf-8")
    harness = tmp_path / "happy.sh"
    harness.write_text(
        f'source "{script}"\n'
        "A2_APPROVAL=APPROVED_A2_HERMES_021_CUTOVER\n"
        "cmd_validate() { echo VALIDATE_PASS; return 0; }\n"
        "cmd_cutover\n",
        encoding="utf-8",
    )
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HERMES_NATIVE_ROOT": str(native),
        "HERMES_NATIVE_STATE_DIR": str(change_state),
        "HERMES_NATIVE_LOCK_FILE": str(tmp_path / "change.lock"),
        "HERMES_NATIVE_PRECUTOVER_MANIFEST": str(precutover),
        "HERMES_NATIVE_HERMES_HOME": str(state),
        "HERMES_NATIVE_STATE_TOOL": str(state_tool),
        "HERMES_NATIVE_R5A_VERIFY_HELPER": str(r5a),
        "HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION": "0.21.0",
    }
    result = subprocess.run(["bash", str(harness)], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (native / "current").resolve() == target.resolve()
    assert "CUTOVER_EXECUTED=YES" in result.stdout


def test_full_rollback_fixture_restores_exact_state_and_019_pointer(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "hermes-native-change-c.sh"
    native = tmp_path / "native"
    source_release = native / "releases" / "0.19.0"
    target_release = native / "releases" / "0.21.0"
    (source_release / "bin").mkdir(parents=True)
    (source_release / "bin" / "hermes").write_text("#!/bin/sh\necho 'Hermes Agent 0.19.0'\n", encoding="utf-8")
    (source_release / "bin" / "hermes").chmod(0o755)
    target_release.mkdir(parents=True)
    (native / "current").symlink_to(target_release, target_is_directory=True)

    original = _state(tmp_path / "original")
    snapshot, digest, snapshot_manifest = contract.create_pre_upgrade_snapshot(
        original,
        tmp_path / "snapshots",
        PROFILE,
        _snapshot_helper(tmp_path / "sqlite-snapshot"),
        _metadata(tmp_path),
    )
    live = tmp_path / "live"
    live.mkdir()
    (live / "failed-candidate").write_text("retain", encoding="utf-8")
    precutover = tmp_path / "precutover.json"
    value = _precutover_value(snapshot, digest, snapshot_manifest, tmp_path)
    value["previous_symlink_target"] = str(source_release)
    contract.write_precutover_manifest(precutover, value, PROFILE)

    fake_bin, r5a = _fake_runtime_tools(tmp_path)
    executor_socket = tmp_path / "executor.sock"
    executor_socket.touch()
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HERMES_NATIVE_ROOT": str(native),
        "HERMES_NATIVE_STATE_DIR": str(tmp_path / "change-state"),
        "HERMES_NATIVE_LOCK_FILE": str(tmp_path / "change.lock"),
        "HERMES_NATIVE_PRECUTOVER_MANIFEST": str(precutover),
        "HERMES_NATIVE_HERMES_HOME": str(live),
        "HERMES_NATIVE_QUARANTINE_DIR": str(tmp_path / "quarantine"),
        "HERMES_NATIVE_R5A_VERIFY_HELPER": str(r5a),
        "HERMES_NATIVE_ROOT_EXECUTOR_SOCKET": str(executor_socket),
        "HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS": "65534",
        "HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION": "0.21.0",
    }
    result = subprocess.run(["bash", str(script), "rollback"], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (native / "current").resolve() == source_release.resolve()
    assert contract.inventory(live) == contract.inventory(snapshot)
    assert contract.inspect_state(live, PROFILE) == contract.inspect_state(snapshot, PROFILE)
    quarantined = list((tmp_path / "quarantine").glob("failed-0.21-state-*"))
    assert len(quarantined) == 1
    assert (quarantined[0] / "failed-candidate").read_text(encoding="utf-8") == "retain"
