#!/usr/bin/env python3
"""Restore and verify one exact HermesTrader backup snapshot, fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

CANONICAL_SOURCE_ROOT = "/opt/data/hermes"
EXPECTED_DATABASE_COUNT = 12
EXPECTED_HERMES_SOURCES = {
    "/opt/data/hermes/state.db",
    "/opt/data/hermes/kanban.db",
    "/opt/data/hermes/verification_evidence.db",
    "/opt/data/hermes/projects.db",
    "/opt/data/hermes/profiles/trading-hub-orchestrator/state.db",
    "/opt/data/hermes/profiles/trading-hub-orchestrator/cron/executions.db",
    "/opt/data/hermes/profiles/trading-hub-orchestrator/memory_store.db",
    "/opt/data/hermes/profiles/trading-hub-orchestrator/projects.db",
    "/opt/data/hermes/profiles/trading-hub-orchestrator/verification_evidence.db",
}
EXPECTED_FREQTRADE_PREFIXES = {
    "container:hermestrader-dryrun-freqtrade-freqforge-1:",
    "container:hermestrader-dryrun-freqtrade-freqforge-canary-1:",
    "container:hermestrader-dryrun-freqtrade-regime-hybrid-1:",
}


class ProofFailure(RuntimeError):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, object], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path, reason: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofFailure(reason, f"cannot read valid JSON from {path}: {exc}") from exc


def safe_manifest_path(staging: Path, raw_name: str) -> Path:
    normalized = raw_name[2:] if raw_name.startswith("./") else raw_name
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ProofFailure("MANIFEST_INVALID", f"unsafe manifest path: {raw_name!r}")
    candidate = staging.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(staging.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ProofFailure("MANIFEST_INVALID", f"manifest path escapes restore: {raw_name!r}") from exc
    return candidate


def parse_manifest(staging: Path) -> dict[str, str]:
    manifest_path = staging / "SHA256SUMS"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProofFailure("MANIFEST_MISSING", str(exc)) from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ProofFailure("MANIFEST_INVALID", f"line {number} has invalid format")
        digest, raw_name = match.groups()
        path = safe_manifest_path(staging, raw_name)
        relative = path.relative_to(staging).as_posix()
        if relative in entries:
            raise ProofFailure("MANIFEST_INVALID", f"duplicate entry: {relative}")
        entries[relative] = digest
    if not entries:
        raise ProofFailure("MANIFEST_INVALID", "manifest is empty")
    actual = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "SHA256SUMS"
    }
    if actual != set(entries):
        missing = sorted(actual - set(entries))[:5]
        stale = sorted(set(entries) - actual)[:5]
        raise ProofFailure(
            "MANIFEST_INCOMPLETE",
            f"unlisted_files={missing!r} missing_files={stale!r}",
        )
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(staging: Path, entries: dict[str, str]) -> None:
    for relative, expected in entries.items():
        path = staging / relative
        try:
            actual = sha256(path)
        except OSError as exc:
            raise ProofFailure("CHECKSUM_FAILED", f"cannot read {relative}: {exc}") from exc
        if actual != expected:
            raise ProofFailure(
                "CHECKSUM_FAILED",
                f"sha256 mismatch for {relative}: expected={expected} actual={actual}",
            )


def validate_inventory(staging: Path, manifest: dict[str, str]) -> list[dict[str, str]]:
    inventory_path = staging / "system/sqlite-inventory.json"
    inventory = load_json(inventory_path, "SQLITE_INVENTORY_INVALID")
    if not isinstance(inventory, list) or len(inventory) != EXPECTED_DATABASE_COUNT:
        actual_count = len(inventory) if isinstance(inventory, list) else "non-list"
        raise ProofFailure(
            "SQLITE_INVENTORY_INVALID",
            f"expected {EXPECTED_DATABASE_COUNT} records, got {actual_count}",
        )
    normalized: list[dict[str, str]] = []
    sources: set[str] = set()
    for index, item in enumerate(inventory):
        if not isinstance(item, dict):
            raise ProofFailure("SQLITE_INVENTORY_INVALID", f"record {index} is not an object")
        required = {key: item.get(key) for key in ("name", "source", "export", "type")}
        if not all(isinstance(value, str) and value for value in required.values()):
            raise ProofFailure("SQLITE_INVENTORY_INVALID", f"record {index} has missing fields")
        source = required["source"]
        export = required["export"]
        assert isinstance(source, str) and isinstance(export, str)
        safe_manifest_path(staging, export)
        if export not in manifest:
            raise ProofFailure("SQLITE_INVENTORY_INVALID", f"export absent from manifest: {export}")
        if source in sources:
            raise ProofFailure("SQLITE_INVENTORY_INVALID", f"duplicate source: {source}")
        sources.add(source)
        normalized.append({key: str(value) for key, value in required.items()})

    hermes_sources = {source for source in sources if source.startswith("/opt/data/hermes/")}
    freqtrade_sources = sources - hermes_sources
    if hermes_sources != EXPECTED_HERMES_SOURCES:
        raise ProofFailure("SQLITE_INVENTORY_INVALID", "Hermes canonical source set mismatch")
    observed_prefixes = {
        prefix
        for prefix in EXPECTED_FREQTRADE_PREFIXES
        if any(source.startswith(prefix) for source in freqtrade_sources)
    }
    if len(freqtrade_sources) != 3 or observed_prefixes != EXPECTED_FREQTRADE_PREFIXES:
        raise ProofFailure("SQLITE_INVENTORY_INVALID", "Freqtrade canonical source set mismatch")
    return normalized


def verify_sqlite(staging: Path, inventory: list[dict[str, str]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in inventory:
        path = staging / item["export"]
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                rows = connection.execute("PRAGMA integrity_check").fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ProofFailure("SQLITE_INTEGRITY_FAILED", f"{item['source']}: {exc}") from exc
        if rows != [("ok",)]:
            raise ProofFailure("SQLITE_INTEGRITY_FAILED", f"{item['source']}: {rows!r}")
        results.append(item | {"integrity_check": "ok"})
    return results


def run_restic_restore(restic_env: Path, snapshot_id: str, raw_root: Path) -> None:
    if not restic_env.is_file():
        raise ProofFailure("RESTORE_FAILED", f"restic environment missing: {restic_env}")
    command = [
        "/bin/bash",
        "-c",
        'set -a; source "$1"; set +a; shift; exec restic restore "$@"',
        "hermes-restore-proof",
        str(restic_env),
        snapshot_id,
        "--target",
        str(raw_root),
    ]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise ProofFailure("RESTORE_FAILED", f"restic exit={completed.returncode}: {detail[0]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--backup-report", default="/var/lib/hermestrader-backup/latest-report.json")
    parser.add_argument("--state-dir", default="/var/lib/hermes-native-change-c")
    parser.add_argument("--restic-env", default="/etc/restic/restic-env")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    restore_root = state_dir / "restore-proof" / run_id
    raw_root = restore_root / "raw"
    restore_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    raw_root.mkdir(mode=0o700)
    failure_report = restore_root / "restore-report.json"
    base_result: dict[str, object] = {
        "version": 1,
        "created_at": utc_now(),
        "snapshot_id": args.snapshot_id,
        "source_root": CANONICAL_SOURCE_ROOT,
        "restore_root": str(restore_root),
        "sqlite_databases": [],
        "manifest_verified": False,
        "checksums_verified": False,
        "sqlite_integrity_verified": False,
        "restore_verified": False,
        "verified": False,
    }

    try:
        if not re.fullmatch(r"[0-9a-f]{64}", args.snapshot_id):
            raise ProofFailure("SNAPSHOT_ID_INVALID", args.snapshot_id)
        report = load_json(Path(args.backup_report), "BACKUP_REPORT_INVALID")
        if not isinstance(report, dict):
            raise ProofFailure("BACKUP_REPORT_INVALID", "report is not an object")
        if report.get("snapshot_id") != args.snapshot_id:
            raise ProofFailure(
                "SNAPSHOT_ID_MISMATCH",
                f"requested={args.snapshot_id} report={report.get('snapshot_id')}",
            )
        if report.get("status") != "SUCCESS" or report.get("exit_code") != 0:
            raise ProofFailure("BACKUP_REPORT_FAILED", "qualifying report is not SUCCESS/0")
        if report.get("source_root") != CANONICAL_SOURCE_ROOT:
            raise ProofFailure("BACKUP_REPORT_INVALID", "unexpected source_root")
        if (
            report.get("sqlite_expected") != EXPECTED_DATABASE_COUNT
            or report.get("sqlite_actual") != EXPECTED_DATABASE_COUNT
        ):
            raise ProofFailure("BACKUP_REPORT_INVALID", "SQLite count is not exactly 12")
        staging_path = report.get("staging_path")
        if (
            not isinstance(staging_path, str)
            or not staging_path.startswith("/var/lib/hermestrader-backup/work/")
            or not staging_path.endswith("/staging")
        ):
            raise ProofFailure("BACKUP_REPORT_INVALID", "unsafe staging_path")

        run_restic_restore(Path(args.restic_env), args.snapshot_id, raw_root)
        staging = raw_root / staging_path.lstrip("/")
        if not staging.is_dir():
            raise ProofFailure("RESTORE_FAILED", f"restored staging root missing: {staging}")
        manifest = parse_manifest(staging)
        base_result["manifest_verified"] = True
        verify_checksums(staging, manifest)
        base_result["checksums_verified"] = True
        inventory = validate_inventory(staging, manifest)
        sqlite_results = verify_sqlite(staging, inventory)
        base_result["sqlite_databases"] = sqlite_results
        base_result["sqlite_integrity_verified"] = True
        base_result["restore_verified"] = True
        base_result["verified"] = True
        base_result["completed_at"] = utc_now()
        atomic_json(failure_report, base_result)
        atomic_json(state_dir / "backup-proof.json", base_result)
        print(json.dumps(base_result, sort_keys=True))
        return 0
    except ProofFailure as exc:
        base_result["completed_at"] = utc_now()
        base_result["reason"] = exc.reason
        base_result["error"] = exc.detail
        atomic_json(failure_report, base_result)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
