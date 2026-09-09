#!/usr/bin/env python3
"""Reusable state and manifest primitives for Hermes Change-C.

The shell driver owns service ordering and the release-pointer transaction.
This module owns deterministic state inspection/migration, immutable snapshots,
and rollback-complete manifests so the isolated probe and production A2 path
share one implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

CONFIG_SOURCE_SCHEMA = 33
CONFIG_TARGET_SCHEMA = 39
DB_SOURCE_SCHEMA = 22
DB_TARGET_SCHEMA = 26
OPERATIONAL_CONFIG_PATHS = (
    ("display", "personality"),
    ("delegation", "max_iterations"),
    ("display", "background_process_notifications"),
)
SNAPSHOT_MANIFEST = "PRE-UPGRADE-STATE-MANIFEST.json"
SNAPSHOT_MANIFEST_HASH = f"{SNAPSHOT_MANIFEST}.sha256"
EXCLUDED_DIRS = {
    "backup",
    "backups",
    "cache",
    "caches",
    "quarantine",
    "recovery",
    "restore",
    "restored",
    "snapshots",
    "state-snapshots",
    "temp",
    "tmp",
}


class ContractError(RuntimeError):
    """Stable fail-closed contract error."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code if not message else f"{code}: {message}")
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)


def load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(code, str(path)) from exc
    if not isinstance(value, dict):
        raise ContractError(code, str(path))
    return value


def _nested(value: dict[str, Any], keys: Iterable[str]) -> Any:
    cursor: Any = value
    for key in keys:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def read_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError("CONFIG_INVALID", str(path)) from exc
    if not isinstance(value, dict) or not isinstance(value.get("_config_version"), int):
        raise ContractError("CONFIG_SCHEMA_INVALID", str(path))
    return value


def inspect_database(path: Path) -> dict[str, Any]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            schema = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            foreign = list(connection.execute("PRAGMA foreign_key_check"))
        finally:
            connection.close()
    except (OSError, sqlite3.Error, TypeError) as exc:
        raise ContractError("SQLITE_INSPECTION_FAILED", str(path)) from exc
    if schema is None or sessions is None:
        raise ContractError("SQLITE_SCHEMA_INVALID", str(path))
    return {
        "schema": int(schema[0]),
        "sessions": int(sessions[0]),
        "integrity": integrity,
        "foreign_key_rows": len(foreign),
    }


def inspect_state(state_root: Path, profile: str) -> dict[str, Any]:
    homes = {"root": state_root, "profile": state_root / "profiles" / profile}
    result: dict[str, Any] = {}
    for role, home in homes.items():
        config = read_config(home / "config.yaml")
        result[role] = {
            "config_schema": config["_config_version"],
            "database": inspect_database(home / "state.db"),
            "operational_config": {".".join(keys): _nested(config, keys) for keys in OPERATIONAL_CONFIG_PATHS},
        }
    return result


def _write_config_preserving_mode(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.chmod(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)


def migrate_state(
    state_root: Path,
    profile: str,
    target_python: Path,
    *,
    source_config_schema: int = CONFIG_SOURCE_SCHEMA,
    source_db_schema: int = DB_SOURCE_SCHEMA,
    target_config_schema: int = CONFIG_TARGET_SCHEMA,
    target_db_schema: int = DB_TARGET_SCHEMA,
) -> dict[str, Any]:
    """Migrate root/profile in place and prove all state invariants."""
    before = inspect_state(state_root, profile)
    for role in ("root", "profile"):
        if before[role]["config_schema"] != source_config_schema:
            raise ContractError("SOURCE_CONFIG_SCHEMA_MISMATCH", role)
        if before[role]["database"]["schema"] != source_db_schema:
            raise ContractError("SOURCE_DB_SCHEMA_MISMATCH", role)

    homes = {"root": state_root, "profile": state_root / "profiles" / profile}
    before_configs = {role: read_config(home / "config.yaml") for role, home in homes.items()}
    for role, home in homes.items():
        environment = os.environ.copy()
        environment["HERMES_HOME"] = str(home)
        environment.pop("HERMES_PROFILE", None)
        try:
            subprocess.run(
                [
                    str(target_python),
                    "-c",
                    "from hermes_cli.config import migrate_config; migrate_config(interactive=False, quiet=True)",
                ],
                env=environment,
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=180,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ContractError("CONFIG_MIGRATION_FAILED", role) from exc
        migrated = read_config(home / "config.yaml")
        for keys in OPERATIONAL_CONFIG_PATHS:
            prior = _nested(before_configs[role], keys)
            if prior is None:
                continue
            cursor = migrated
            for key in keys[:-1]:
                cursor = cursor.setdefault(key, {})
            cursor[keys[-1]] = prior
        _write_config_preserving_mode(home / "config.yaml", migrated)
        try:
            subprocess.run(
                [
                    str(target_python),
                    "-c",
                    "from pathlib import Path; import sys; from hermes_state import SessionDB; "
                    "SessionDB(db_path=Path(sys.argv[1]), read_only=False).close()",
                    str(home / "state.db"),
                ],
                env=environment,
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=300,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ContractError("DB_MIGRATION_FAILED", role) from exc

    after = inspect_state(state_root, profile)
    for role in ("root", "profile"):
        checks = (
            after[role]["config_schema"] == target_config_schema,
            after[role]["database"]["schema"] == target_db_schema,
            after[role]["database"]["sessions"] == before[role]["database"]["sessions"],
            after[role]["database"]["integrity"] == ["ok"],
            after[role]["database"]["foreign_key_rows"] == 0,
            after[role]["operational_config"] == before[role]["operational_config"],
        )
        if not all(checks):
            raise ContractError("MIGRATION_INVARIANT_FAILED", role)
    return {
        "version": 1,
        "created_at": utc_now(),
        "before": before,
        "after": after,
        "session_invariant_verified": True,
        "sqlite_integrity_verified": True,
        "config_drift_verified": True,
        "migration_verified": True,
        "backend_probe_verified": False,
        "verified": False,
    }


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _copy_state_with_sqlite_snapshots(source: Path, destination: Path, snapshot_helper: Path) -> None:
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
        relative_root = root_path.relative_to(source)
        target_root = destination / relative_root
        target_root.mkdir(parents=True, exist_ok=True)
        shutil.copystat(root_path, target_root, follow_symlinks=False)
        for name in list(dirs):
            item = root_path / name
            if item.is_symlink():
                (target_root / name).symlink_to(os.readlink(item))
                dirs.remove(name)
        for name in files:
            item = root_path / name
            target = target_root / name
            if item.is_symlink():
                target.symlink_to(os.readlink(item))
            elif name.endswith(("-wal", "-shm")) and _is_sqlite(Path(str(item).rsplit("-", 1)[0])):
                # The hardened helper materializes a self-contained database.
                # Copying live sidecars beside it would reapply an unrelated WAL.
                continue
            elif _is_sqlite(item):
                try:
                    subprocess.run([str(snapshot_helper), str(item), str(target)], check=True, timeout=300)
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    raise ContractError("SQLITE_SNAPSHOT_FAILED", str(item)) from exc
                shutil.copystat(item, target, follow_symlinks=False)
            else:
                shutil.copy2(item, target, follow_symlinks=False)


def inventory(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if relative in {SNAPSHOT_MANIFEST, SNAPSHOT_MANIFEST_HASH}:
            continue
        if path.is_symlink():
            entries.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        elif path.is_dir():
            entries.append({"path": relative, "type": "directory", "mode": path.stat().st_mode & 0o777})
        elif path.is_file():
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "size": path.stat().st_size,
                    "mode": path.stat().st_mode & 0o777,
                    "sha256": sha256_file(path),
                }
            )
    return entries


def create_pre_upgrade_snapshot(
    source: Path,
    snapshot_parent: Path,
    profile: str,
    snapshot_helper: Path,
    metadata: dict[str, Any],
) -> tuple[Path, str, dict[str, Any]]:
    """Create and verify an immutable full rollback snapshot atomically."""
    if not snapshot_helper.is_file() or not os.access(snapshot_helper, os.X_OK):
        raise ContractError("SQLITE_SNAPSHOT_HELPER_MISSING", str(snapshot_helper))
    before = inspect_state(source, profile)
    for role in ("root", "profile"):
        database = before[role]["database"]
        if database["integrity"] != ["ok"] or database["foreign_key_rows"] != 0:
            raise ContractError("SOURCE_STATE_INVALID", role)
    snapshot_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    temporary = Path(tempfile.mkdtemp(prefix=f".pre-upgrade-{stamp}.", dir=snapshot_parent))
    final = snapshot_parent / stamp
    try:
        _copy_state_with_sqlite_snapshots(source, temporary, snapshot_helper)
        copied = inspect_state(temporary, profile)
        if copied != before:
            raise ContractError("STATE_SNAPSHOT_INVARIANT_FAILED")
        for path in temporary.rglob("*"):
            if path.is_file() and not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
        manifest = {
            "version": 1,
            "created_at": utc_now(),
            "state_snapshot_root": str(final),
            "inventory": inventory(temporary),
            "state": copied,
            "root_config_schema": copied["root"]["config_schema"],
            "profile_config_schema": copied["profile"]["config_schema"],
            "root_db_schema": copied["root"]["database"]["schema"],
            "profile_db_schema": copied["profile"]["database"]["schema"],
            "root_session_count": copied["root"]["database"]["sessions"],
            "profile_session_count": copied["profile"]["database"]["sessions"],
            "root_sqlite_integrity": copied["root"]["database"]["integrity"],
            "profile_sqlite_integrity": copied["profile"]["database"]["integrity"],
            "root_fk_violation_count": copied["root"]["database"]["foreign_key_rows"],
            "profile_fk_violation_count": copied["profile"]["database"]["foreign_key_rows"],
            **metadata,
        }
        atomic_write_json(temporary / SNAPSHOT_MANIFEST, manifest, 0o400)
        manifest_hash = sha256_file(temporary / SNAPSHOT_MANIFEST)
        (temporary / SNAPSHOT_MANIFEST_HASH).write_text(f"{manifest_hash}  {SNAPSHOT_MANIFEST}\n", encoding="ascii")
        os.chmod(temporary / SNAPSHOT_MANIFEST_HASH, 0o400)
        os.replace(temporary, final)
        verify_pre_upgrade_snapshot(final, manifest_hash, profile)
        return final, manifest_hash, manifest
    except Exception:
        if temporary.exists():
            failed = snapshot_parent / f"failed-{stamp}"
            os.replace(temporary, failed)
        raise


def verify_pre_upgrade_snapshot(snapshot: Path, expected_hash: str, profile: str) -> dict[str, Any]:
    manifest_path = snapshot / SNAPSHOT_MANIFEST
    manifest = load_json(manifest_path, "PRE_UPGRADE_STATE_MANIFEST_INVALID")
    if sha256_file(manifest_path) != expected_hash:
        raise ContractError("PRE_UPGRADE_STATE_MANIFEST_HASH_MISMATCH")
    try:
        sidecar_hash = (snapshot / SNAPSHOT_MANIFEST_HASH).read_text(encoding="ascii").split()[0]
    except (OSError, IndexError) as exc:
        raise ContractError("PRE_UPGRADE_STATE_MANIFEST_HASH_MISSING") from exc
    if sidecar_hash != expected_hash or manifest.get("inventory") != inventory(snapshot):
        raise ContractError("PRE_UPGRADE_STATE_INVENTORY_MISMATCH")
    if inspect_state(snapshot, profile) != manifest.get("state"):
        raise ContractError("PRE_UPGRADE_STATE_CONTENT_MISMATCH")
    return manifest


PRECUTOVER_REQUIRED = {
    "previous_symlink_target",
    "previous_version",
    "target_version",
    "target_sha",
    "pre_upgrade_state_path",
    "pre_upgrade_state_manifest_sha256",
    "root_session_count",
    "profile_session_count",
    "backup_proof_ref",
    "fleet_baseline_ref",
    "fleet_image_lock_ref",
    "timestamp",
    "operator",
    "gates_passed",
}


def write_precutover_manifest(path: Path, value: dict[str, Any], profile: str) -> dict[str, Any]:
    missing = PRECUTOVER_REQUIRED - value.keys()
    if missing or value.get("gates_passed") is not True:
        raise ContractError("PRECUTOVER_MANIFEST_INCOMPLETE", ",".join(sorted(missing)))
    verify_pre_upgrade_snapshot(
        Path(value["pre_upgrade_state_path"]),
        str(value["pre_upgrade_state_manifest_sha256"]),
        profile,
    )
    atomic_write_json(path, value, 0o600)
    return validate_precutover_manifest(path, profile)


def validate_precutover_manifest(path: Path, profile: str) -> dict[str, Any]:
    value = load_json(path, "PRECUTOVER_MANIFEST_INVALID")
    missing = PRECUTOVER_REQUIRED - value.keys()
    if missing or value.get("gates_passed") is not True:
        raise ContractError("PRECUTOVER_MANIFEST_INCOMPLETE", ",".join(sorted(missing)))
    snapshot = verify_pre_upgrade_snapshot(
        Path(str(value["pre_upgrade_state_path"])),
        str(value["pre_upgrade_state_manifest_sha256"]),
        profile,
    )
    state = snapshot["state"]
    if value["root_session_count"] != state["root"]["database"]["sessions"]:
        raise ContractError("ROOT_SESSION_BASELINE_MISMATCH")
    if value["profile_session_count"] != state["profile"]["database"]["sessions"]:
        raise ContractError("PROFILE_SESSION_BASELINE_MISMATCH")
    if path.stat().st_mode & 0o777 != 0o600:
        raise ContractError("PRECUTOVER_MANIFEST_MODE_INVALID")
    return value


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--state", type=Path, required=True)
    inspect_parser.add_argument("--profile", required=True)
    inspect_parser.add_argument("--output", type=Path)
    migrate_parser = sub.add_parser("migrate")
    migrate_parser.add_argument("--state", type=Path, required=True)
    migrate_parser.add_argument("--profile", required=True)
    migrate_parser.add_argument("--python", type=Path, required=True)
    migrate_parser.add_argument("--output", type=Path, required=True)
    verify_parser = sub.add_parser("verify-snapshot")
    verify_parser.add_argument("--snapshot", type=Path, required=True)
    verify_parser.add_argument("--sha256", required=True)
    verify_parser.add_argument("--profile", required=True)
    manifest_parser = sub.add_parser("verify-manifest")
    manifest_parser.add_argument("--manifest", type=Path, required=True)
    manifest_parser.add_argument("--profile", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_state(args.state, args.profile)
            if args.output:
                atomic_write_json(args.output, result)
            else:
                print(json.dumps(result, sort_keys=True))
        elif args.command == "migrate":
            atomic_write_json(args.output, migrate_state(args.state, args.profile, args.python))
        elif args.command == "verify-snapshot":
            verify_pre_upgrade_snapshot(args.snapshot, args.sha256, args.profile)
        elif args.command == "verify-manifest":
            validate_precutover_manifest(args.manifest, args.profile)
    except ContractError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
