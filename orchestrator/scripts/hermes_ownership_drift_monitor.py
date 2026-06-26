#!/usr/bin/env python3
"""Report-only ownership drift monitor for Hermes Home scope.

Never mutates permissions. Compares against a versioned baseline and classifies
findings to avoid alarm fatigue from known legacy inventory.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import grp
import hashlib
from datetime import datetime, timezone
from pathlib import Path

FOREIGN_UIDS = {0, 1000, 10000}
CANONICAL_UID = 1337
DEFAULT_SCOPES = [
    "/home/hermes",
    "/opt/hermes-green/config/profiles",
    "/opt/hermes-green/config/logs",
]
REPORT_DIR = Path("/home/hermes/projects/trading/orchestrator/reports")
BASELINE_PATH = REPORT_DIR / "ownership-drift-baseline.json"

ACTIVE_RUNTIME_PREFIXES = (
    "/home/hermes/projects/trading/freqforge/",
    "/home/hermes/projects/trading/freqforge-canary/",
    "/home/hermes/projects/trading/freqtrade/bots/",
    "/home/hermes/projects/trading/freqtrade/shared/",
    "/home/hermes/projects/trading/ai-hedge-fund-crypto/output/",
    "/home/hermes/projects/trading/var/trading-shadowlock/",
    "/home/hermes/projects/trading/orchestrator/state/",
    "/home/hermes/projects/trading/orchestrator/logs/",
    "/opt/hermes-green/config/profiles/orchestrator/",
)

ARCHIVE_PREFIXES = (
    "/home/hermes/archive/",
    "/home/hermes/freqtrade-momentum/",
    "/home/hermes/freqtrade-regime-hybrid/",
    "/home/hermes/backups/",
    "/home/hermes/projects/trading/archive/",
    "/home/hermes/projects/trading/backups/",
    "/home/hermes/projects/trading/var/trading-self-improvement/",
)

EXPECTED_SERVICE_PREFIXES = (
    "/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json",
    "/home/hermes/projects/trading/orchestrator/reports/",
)


def _owner_label(st) -> str:
    try:
        user = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        user = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)
    return f"{user}:{group} ({st.st_uid}:{st.st_gid})"


def _path_key(path: str, owner: str, mode: str) -> str:
    return hashlib.sha256(f"{path}|{owner}|{mode}".encode()).hexdigest()


def classify_finding(path: str, mtime: float, baseline_keys: set[str], owner: str, mode: str) -> str:
    key = _path_key(path, owner, mode)
    if key in baseline_keys:
        return "KNOWN_LEGACY"

    age_hours = (datetime.now(timezone.utc).timestamp() - mtime) / 3600.0
    if any(path.startswith(p) for p in ARCHIVE_PREFIXES):
        return "ARCHIVE_EXCEPTION"
    if path in EXPECTED_SERVICE_PREFIXES or any(path.startswith(p) for p in EXPECTED_SERVICE_PREFIXES):
        return "EXPECTED_SERVICE_PATH"
    if any(path.startswith(p) for p in ACTIVE_RUNTIME_PREFIXES):
        if age_hours <= 48:
            return "ACTIVE_VIOLATION"
        return "KNOWN_LEGACY"
    if age_hours <= 48:
        return "UNKNOWN"
    return "KNOWN_LEGACY"


def scan_scope(root: Path, max_depth: int = 6) -> list[dict]:
    findings: list[dict] = []
    if not root.exists():
        return findings
    root_parts = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_parts
        if depth > max_depth:
            dirnames[:] = []
            continue
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            try:
                st = path.lstat()
            except OSError:
                continue
            if st.st_uid in FOREIGN_UIDS or st.st_gid in FOREIGN_UIDS:
                findings.append(
                    {
                        "path": str(path),
                        "owner": _owner_label(st),
                        "uid": st.st_uid,
                        "gid": st.st_gid,
                        "mode": oct(st.st_mode & 0o7777),
                        "type": "dir" if path.is_dir() else "file",
                        "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                    }
                )
    return findings


def load_baseline() -> dict:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "keys": [], "paths": {}}


def save_baseline(findings: list[dict]) -> None:
    keys = []
    paths = {}
    for f in findings:
        key = _path_key(f["path"], f["owner"], f["mode"])
        keys.append(key)
        paths[f["path"]] = {
            "owner": f["owner"],
            "mode": f["mode"],
            "category": classify_finding(f["path"], datetime.fromisoformat(f["mtime_utc"]).timestamp(), set(), f["owner"], f["mode"]),
        }
    payload = {
        "version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "keys": keys,
        "paths": paths,
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes ownership drift monitor (report-only)")
    parser.add_argument("--json-out", type=Path, help="Optional JSON report path")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--init-baseline", action="store_true", help="Capture current inventory as baseline")
    parser.add_argument("--recent-hours", type=float, default=48.0, help="Recent mtime window for active alerts")
    parser.add_argument("scopes", nargs="*", help="Extra paths to scan")
    args = parser.parse_args()

    scopes = [Path(p) for p in DEFAULT_SCOPES] + [Path(p) for p in args.scopes]
    started = datetime.now(timezone.utc).isoformat()
    all_findings: list[dict] = []

    for scope in scopes:
        for item in scan_scope(scope, max_depth=args.max_depth):
            item["scope_root"] = str(scope)
            all_findings.append(item)

    baseline = load_baseline()
    baseline_keys = set(baseline.get("keys", []))

    categories: dict[str, list] = {
        "ACTIVE_VIOLATION": [],
        "KNOWN_LEGACY": [],
        "ARCHIVE_EXCEPTION": [],
        "EXPECTED_SERVICE_PATH": [],
        "UNKNOWN": [],
    }

    for f in all_findings:
        mtime = datetime.fromisoformat(f["mtime_utc"]).timestamp()
        cat = classify_finding(f["path"], mtime, baseline_keys, f["owner"], f["mode"])
        f["category"] = cat
        categories[cat].append(f)

    new_since_baseline = [
        f for f in all_findings
        if _path_key(f["path"], f["owner"], f["mode"]) not in baseline_keys
    ]

    alert_findings = [
        f for f in all_findings
        if f["category"] in {"ACTIVE_VIOLATION", "UNKNOWN"}
        and (datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(f["mtime_utc"]).timestamp()) / 3600.0 <= args.recent_hours
    ]

    if args.init_baseline:
        save_baseline(all_findings)

    report = {
        "generated_at_utc": started,
        "runtime_uid": os.getuid(),
        "runtime_gid": os.getgid(),
        "baseline_path": str(BASELINE_PATH),
        "baseline_exists": BASELINE_PATH.exists(),
        "baseline_finding_count": len(baseline_keys),
        "foreign_uid_thresholds": sorted(FOREIGN_UIDS),
        "finding_count": len(all_findings),
        "category_counts": {k: len(v) for k, v in categories.items()},
        "new_since_baseline_count": len(new_since_baseline),
        "alert_count": len(alert_findings),
        "alert_findings": alert_findings[:200],
        "new_since_baseline": new_since_baseline[:200],
        "truncated": len(all_findings) > 5000,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_out = REPORT_DIR / f"ownership-drift-{ts}.json"
    out_path = args.json_out or default_out
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"[drift-monitor] total={len(all_findings)} "
        f"active_violations={len(categories['ACTIVE_VIOLATION'])} "
        f"alerts={len(alert_findings)} new={len(new_since_baseline)} "
        f"report={out_path}"
    )
    return 1 if alert_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())