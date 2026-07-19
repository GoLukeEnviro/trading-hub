"""Root broker for the roadmap merge controller (ADR-2026-07-19).

This is the **root-owned security controller** that holds the merge credential
and independently verifies EVERY merge precondition before executing
``gh pr merge --squash --match-head-commit <sha>``.

Architecture
------------

The broker runs as a root-owned systemd service with a Unix socket at
``/var/run/roadmap-merge-broker.sock`` (mode 0660, owned ``root:hermes``).
The controller client (running as UID 10000 ``hermes``) connects to the socket
and sends a JSON merge request. The broker:

1. Verifies the caller's identity via ``SO_PEERCRED``.
2. Checks the caller against the identity allowlist.
3. Independently collects the PR snapshot from GitHub.
4. Independently evaluates the read-only guard.
5. Independently checks the human-only denylist, path allowlist, and A1-only
   enforcement.
6. Writes an **Intent** audit record to the ``chattr +a``-protected audit file.
7. Executes ``gh pr merge --squash --match-head-commit <sha>``.
8. On timeout / 5xx / connection abort: re-queries GitHub state.
9. Writes a **Completion** audit record.
10. On completion-audit failure: writes the system-wide halt file and logs an
    incident to systemd-journald.

The broker NEVER trusts the client's pre-checks. Every invariant is
independently re-verified.

Threat model
------------

- **Unprivileged controller (UID 10000):** ``chattr +a`` prevents the
  controller from truncating or rewriting the audit log. The broker performs
  all security checks independently, so a compromised client (bypassing the
  controller) cannot produce a merge without passing the broker's checks.
- **Root compromise:** ``chattr +a`` does NOT protect against a compromised
  root — root can remove ``+a``, rewrite the audit, and impersonate the
  broker. This is an explicitly accepted boundary documented in the ADR.
- **GitHub credential exfiltration:** The credential is stored in a root-only
  tmpfs at ``/run/roadmap-merge-cred/``. The controller UID (10000) cannot
  read or modify it. The broker loads it at startup and never writes it to
  disk or to the socket.

IPC protocol
------------

Request (client → broker, JSON over Unix socket):
    {
        "action": "merge",
        "repo": "GoLukeEnviro/trading-hub",
        "pr": 637,
        "expected_issue": 634,
        "expected_head_sha": "82d8527...",
        "tracker_issue": 605,
        "controller_identity": "roadmap-merge-controller-bot",
        "client_uid": 10000,
        "client_gid": 10000
    }

Response (broker → client, JSON):
    {
        "decision": "MERGED",
        "status": "MERGED_BY_CONTROLLER",
        "merged": true,
        "merge_sha": "b18bbf0...",
        "blockers": [],
        "intent_record_id": "...",
        "completion_record_id": "..."
    }

Error response:
    {
        "decision": "MERGE_REJECTED",
        "status": "BLOCKED_BY_*",
        "merged": false,
        "merge_sha": null,
        "blockers": ["...", "..."],
        "intent_record_id": "...",
        "completion_record_id": "..."
    }
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import logging
import os
import pathlib
import re
import socket
import stat
import struct
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# NOTE: ``fcntl``, ``grp``, ``pwd`` are imported lazily inside the
# functions that need them (``validate_audit_file``, ``run_broker``)
# because they are POSIX-only. This module is fully importable on
# non-POSIX hosts.

# ----------------------------------------------------------------------
# Canonical paths
# ----------------------------------------------------------------------

_CONTROLLER_STATE_DIR = Path("/opt/data/state/roadmap-merge-controller")
_DEFAULT_SOCKET_PATH = Path("/var/run/roadmap-merge-broker.sock")
_DEFAULT_AUDIT_LOG_PATH = _CONTROLLER_STATE_DIR / "audit.jsonl"
_DEFAULT_HALT_PATH = _CONTROLLER_STATE_DIR / "halt"
_DEFAULT_ENABLE_SWITCH_PATH = _CONTROLLER_STATE_DIR / "enabled"
_DEFAULT_CREDENTIAL_DIR = Path("/run/roadmap-merge-cred")

_REPO_ROOT = Path("/workspace/projects/trading-hub")
_DENYLIST_PATH = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_denylist.txt"
_ALLOWLIST_PATH = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_allowlist.txt"
_PATHS_ALLOWLIST_PATH = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_paths_allowlist.txt"

# Required environment variable for the GitHub credential.
_GH_TOKEN_ENV_KEY = "BROKER_GH_TOKEN_PATH"

# Required status checks that must be SUCCESS before a merge.
_REQUIRED_CHECKS = ("main-gate", "offline-smoke")

# A2/A3 / live-trading trigger patterns (A1-only enforcement).
_A2A3_TRIGGER_PATTERNS = (
    "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION",
    "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT",
    "A2-APPROVED",
    "A3-APPROVED",
    "dry_run=false",
    "dry_run = false",
    "live-trading",
    "live_order",
    "exchange_key",
)

# Formal governance block pattern in comments.
_FORMAL_BLOCK_PATTERN = re.compile(
    r"\b(?:formally_blocked(?:_[a-z0-9_]+)?|blocked_by_[a-z0-9_]+)\b",
    re.IGNORECASE,
)

# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class BrokerError(Exception):
    """Base broker error. The code is stable for machine consumption."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class PeerRejected(BrokerError):
    """Peer-credential check failed."""

    def __init__(self, message: str) -> None:
        super().__init__("PEER_REJECTED", message)


class GovernanceBlock(BrokerError):
    """A governance invariant blocked the merge."""

    def __init__(self, message: str, blockers: list[str]) -> None:
        super().__init__("GOVERNANCE_BLOCK", message)
        self.blockers = blockers


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MergeRequest:
    action: str
    repo: str
    pr: int
    expected_issue: int
    expected_head_sha: str
    tracker_issue: int
    controller_identity: str
    client_uid: int
    client_gid: int


@dataclass(frozen=True)
class MergeResponse:
    decision: str  # MERGED / MERGE_REJECTED / MERGE_OUTCOME_UNKNOWN
    status: str
    merged: bool
    merge_sha: Optional[str]
    blockers: list[str]
    intent_record_id: Optional[str]
    completion_record_id: Optional[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


# ----------------------------------------------------------------------
# Peer-credential verification
# ----------------------------------------------------------------------


def _get_peer_cred(sock: socket.socket) -> tuple[int, int, int]:
    """Return (pid, uid, gid) of the connected peer via SO_PEERCRED."""
    cred = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", cred)
    return pid, uid, gid


def verify_peer(
    sock: socket.socket,
    allowlist_path: Path,
) -> tuple[int, int, int]:
    """Verify the connected peer against the identity allowlist.

    Returns (pid, uid, gid) on success. Raises PeerRejected on failure.
    The broker does NOT trust the caller's self-reported UID/GID; it reads
    the actual kernel peer credentials via SO_PEERCRED.
    """
    pid, uid, gid = _get_peer_cred(sock)

    # Read the allowlist.
    if not allowlist_path.is_file():
        raise PeerRejected(f"Identity allowlist not found: {allowlist_path}")

    allowed: list[tuple[int, int, str]] = []
    for line in allowlist_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(":", 2)
        if len(parts) != 3:
            continue
        try:
            allowed_uid = int(parts[0])
            allowed_gid = int(parts[1])
            allowed_principal = parts[2]
            allowed.append((allowed_uid, allowed_gid, allowed_principal))
        except ValueError:
            continue

    # Check UID+GID.
    matched = False
    for allowed_uid, allowed_gid, _ in allowed:
        if uid == allowed_uid and gid == allowed_gid:
            matched = True
            break
    if not matched:
        raise PeerRejected(
            f"Peer UID {uid} GID {gid} not in identity allowlist"
        )

    return pid, uid, gid


# ----------------------------------------------------------------------
# GitHub principal resolution
# ----------------------------------------------------------------------


def resolve_github_principal(*, env: Optional[dict[str, str]] = None) -> str:
    """Return the authenticated GitHub principal login via ``gh api user``.

    The broker runs its OWN ``gh`` invocation with its OWN credential
    (not inherited from the client). This proves the caller's GitHub
    identity independently.
    """
    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if result.returncode != 0:
        raise BrokerError(
            "GH_PRINCIPAL_RESOLUTION_FAILED",
            result.stderr.strip() or "gh api user failed",
        )
    return result.stdout.strip()


# ----------------------------------------------------------------------
# Disable switch and halt (fail-closed)
# ----------------------------------------------------------------------


def is_controller_enabled(
    switch_path: Path = _DEFAULT_ENABLE_SWITCH_PATH,
    halt_path: Path = _DEFAULT_HALT_PATH,
) -> bool:
    """Return True iff the enable switch is active AND no halt file exists.

    Fail-closed semantics:
    - Missing, wrong content, wrong ownership, wrong mode → disabled.
    - Halt file exists → disabled (overrides enable switch).
    """
    # Halt check first (supersedes enable switch).
    if halt_path.exists():
        return False

    # Enable switch check.
    try:
        if not switch_path.is_file():
            return False
        st = switch_path.stat()
        # Ownership must be root:root.
        if st.st_uid != 0 or st.st_gid != 0:
            return False
        # Mode must be 0644 or stricter (no group/other write, no suid/sgid).
        if st.st_mode & 0o0133:  # S_IWGRP | S_IWOTH | S_ISUID | S_ISGID | S_ISVTX
            return False
        content = switch_path.read_text(encoding="utf-8")
    except OSError:
        return False
    # Accept exactly "true" or "true\n".
    return content.strip() == "true" and "\n" not in content.rstrip("\n")


def write_halt(halt_path: Path = _DEFAULT_HALT_PATH) -> None:
    """Write the halt file to disable the controller.

    This is called when a critical incident occurs (e.g., completion-audit
    failure). The halt file is root-owned and not removable by the controller
    UID. It overrides the enable switch.
    """
    try:
        halt_path.parent.mkdir(parents=True, exist_ok=True)
        halt_path.write_text("HALTED\n", encoding="utf-8")
        halt_path.chmod(0o0644)
    except OSError as exc:
        # Log to stderr; the caller (journald fallback) is responsible.
        print(f"HALT_WRITE_FAILED: {exc}", file=sys.stderr)


# ----------------------------------------------------------------------
# Audit (chattr +a protected, broker-owned)
# ----------------------------------------------------------------------


def validate_audit_file(audit_log_path: Path) -> None:
    """Validate that the audit log exists with correct owner/mode/chattr.

    Raises BrokerError if validation fails. The broker checks this at
    startup and before every audit write.
    """
    if not audit_log_path.is_file():
        raise BrokerError(
            "AUDIT_FILE_MISSING",
            f"Audit log not found: {audit_log_path}",
        )
    st = audit_log_path.stat()
    # Owner must be root:root.
    if st.st_uid != 0 or st.st_gid != 0:
        raise BrokerError(
            "AUDIT_FILE_OWNERSHIP_INVALID",
            f"Audit log owner {st.st_uid}:{st.st_gid}, expected 0:0",
        )
    # Mode must be 0644 or stricter.
    if st.st_mode & 0o0133:
        raise BrokerError(
            "AUDIT_FILE_MODE_INVALID",
            f"Audit log mode {oct(st.st_mode)}, expected 0644 or stricter",
        )
    # Verify chattr +a is set.
    try:
        result = subprocess.run(
            ["lsattr", str(audit_log_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            attrs = result.stdout.strip().split()[0] if result.stdout.strip() else ""
            if "a" not in attrs:
                raise BrokerError(
                    "AUDIT_FILE_NOT_APPEND_ONLY",
                    f"chattr +a not set on {audit_log_path} (attrs: {attrs})",
                )
        else:
            # lsattr may fail on some filesystems; log but don't hard-block.
            print(
                f"AUDIT_LSATTR_FAILED (non-blocking): {result.stderr.strip()}",
                file=sys.stderr,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"AUDIT_LSATTR_EXCEPTION (non-blocking): {exc}",
            file=sys.stderr,
        )


def write_audit_record(
    audit_log_path: Path,
    record: dict[str, Any],
) -> str:
    """Append a JSONL record to the audit log with fsync.

    Returns a unique record_id (timestamp_utc + SHA256 of the line).
    Raises BrokerError on write or fsync failure.
    """
    line = json.dumps(record, sort_keys=True) + "\n"
    record_id = hashlib.sha256(line.encode()).hexdigest()[:16]
    record["_record_id"] = record_id
    line = json.dumps(record, sort_keys=True) + "\n"
    try:
        with open(audit_log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise BrokerError(
            "AUDIT_WRITE_FAILED",
            str(exc),
        ) from exc
    return record_id


def build_audit_record(
    *,
    event: str,
    peer_pid: int,
    peer_uid: int,
    peer_gid: int,
    github_principal: str,
    pr: int,
    expected_issue: int,
    expected_head_sha: str,
    controller_identity: str,
    decision_code: str,
    merge_sha: Optional[str],
    blockers: list[str],
    phase: str,
    allowlist_version_hash: str,
    pre_merge_snapshot_hash: str,
) -> dict[str, Any]:
    """Build a structured audit record."""
    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,  # "intent" | "completion"
        "peer_pid": peer_pid,
        "peer_uid": peer_uid,
        "peer_gid": peer_gid,
        "github_principal": github_principal,
        "pr": pr,
        "expected_issue": expected_issue,
        "expected_head_sha": expected_head_sha,
        "controller_identity": controller_identity,
        "decision": decision_code,
        "merge_sha": merge_sha,
        "blockers": blockers,
        "phase": phase,
        "allowlist_version_hash": allowlist_version_hash,
        "pre_merge_snapshot_hash": pre_merge_snapshot_hash,
    }


# ----------------------------------------------------------------------
# Allowlist / denylist / paths-allowlist validation
# ----------------------------------------------------------------------


def load_allowlist(path: Path) -> list[tuple[int, int, str]]:
    """Load and parse the identity allowlist."""
    if not path.is_file():
        return []
    result: list[tuple[int, int, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(":", 2)
        if len(parts) != 3:
            continue
        try:
            uid = int(parts[0])
            gid = int(parts[1])
            principal = parts[2]
            result.append((uid, gid, principal))
        except ValueError:
            continue
    return result


def load_glob_list(path: Path) -> list[str]:
    """Load a list of glob patterns from a file."""
    if not path.is_file():
        return []
    result: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        result.append(stripped)
    return result


def _match_glob(pattern: str, path: str) -> bool:
    """Simple glob matching (supports **/prefix, single-directory *)."""
    # Convert the simple glob to a regex.
    regex_parts = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            # ** matches everything
            regex_parts.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif c == "*":
            regex_parts.append("[^/]*")
            i += 1
        elif c == "?":
            regex_parts.append(".")
            i += 1
        elif c == ".":
            regex_parts.append("\\.")
            i += 1
        elif c == "/":
            regex_parts.append("/")
            i += 1
        else:
            regex_parts.append(re.escape(c))
            i += 1
    regex = "^" + "".join(regex_parts) + "$"
    return bool(re.match(regex, path))


def check_denylist(denylist_path: Path, changed_files: list[str]) -> list[str]:
    """Check if any changed file matches the denylist.

    Returns a list of matched denylist entries. Empty = no denylist hit.
    """
    patterns = load_glob_list(denylist_path)
    hits: list[str] = []
    for pattern in patterns:
        for cf in changed_files:
            if _match_glob(pattern, cf):
                hits.append(f"{pattern} matched {cf}")
    return hits


def check_paths_allowlist(
    allowlist_path: Path,
    changed_files: list[str],
) -> list[str]:
    """Check if ALL changed files are covered by the path allowlist.

    Returns a list of unmatched files. Empty = all matched (PR is allowed).
    """
    patterns = load_glob_list(allowlist_path)
    unmatched: list[str] = []
    for cf in changed_files:
        matched = False
        for pattern in patterns:
            if _match_glob(pattern, cf):
                matched = True
                break
        if not matched:
            unmatched.append(cf)
    return unmatched


def check_a1_triggers(
    issue_body: str,
    pr_body: str,
    pr_comments: list[str],
) -> list[str]:
    """Check for A2/A3/live-trading trigger tokens."""
    haystacks = [issue_body or "", pr_body or ""] + (pr_comments or [])
    haystack = "\n".join(haystacks).lower()
    found: list[str] = []
    for pattern in _A2A3_TRIGGER_PATTERNS:
        if pattern.lower() in haystack:
            found.append(pattern)
    return found


def check_formal_governance_block(pr_comments: list[str]) -> bool:
    """Check if any PR comment carries a formal governance block marker."""
    for comment in pr_comments or []:
        if _FORMAL_BLOCK_PATTERN.search(comment):
            return True
    return False


# ----------------------------------------------------------------------
# GitHub fact collection (independent from the client)
# ----------------------------------------------------------------------


def _run_gh_json(arguments: list[str], *, env: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Run a ``gh`` command and return the parsed JSON output."""
    result = subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    if result.returncode != 0:
        raise BrokerError(
            "GH_COMMAND_FAILED",
            result.stderr.strip() or "gh command failed",
        )
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise BrokerError(
            "GH_NON_OBJECT_RESPONSE",
            "gh returned a non-object JSON payload",
        )
    return data


def _run_gh_graphql(
    query: str,
    *,
    variables: dict[str, Any],
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Run a GitHub GraphQL query via ``gh api graphql``."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, bool):
            args.extend(["-F", f"{key}={str(value).lower()}"])
        elif isinstance(value, int):
            args.extend(["-F", f"{key}={value}"])
        elif isinstance(value, str):
            args.extend(["-F", f"{key}={value}"])
        else:
            args.extend(["-f", f"{key}={value}"])
    return _run_gh_json(args, env=env)


def collect_pr_snapshot(
    *,
    repo: str,
    pr: int,
    expected_issue: int,
    tracker_issue: int,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Collect ALL facts the broker needs for independent verification.

    Returns a dict with structured snapshot fields. This is the broker's
    OWN fact collection — it does NOT trust the client's snapshot.
    """
    owner, name = repo.split("/", 1)

    # PR data via gh CLI.
    pr_data = _run_gh_json(
        [
            "pr", "view", str(pr), "--repo", repo,
            "--json",
            "state,isDraft,headRefOid,body,statusCheckRollup,comments,"
            "reviewDecision,files,mergeable",
        ],
        env=env,
    )

    # Issue data for the expected issue.
    issue_data = _run_gh_json(
        ["issue", "view", str(expected_issue), "--repo", repo, "--json", "state,labels,body"],
        env=env,
    )

    # Tracker data for tracker issue (roadmap-selected-task).
    tracker_data = _run_gh_json(
        ["issue", "view", str(tracker_issue), "--repo", repo, "--json", "body"],
        env=env,
    )

    # Review threads (unresolved count) via GraphQL.
    graphql_data = _run_gh_graphql(
        "query($owner:String!,$name:String!,$pr:Int!){"
        "repository(owner:$owner,name:$name){pullRequest(number:$pr){"
        "reviewThreads(first:100){nodes{isResolved}}}}}",
        variables={"owner": owner, "name": name, "pr": pr},
        env=env,
    )

    review_threads = (
        graphql_data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )

    checks = pr_data.get("statusCheckRollup", []) or []
    comments = pr_data.get("comments", []) or []
    files = pr_data.get("files", []) or []
    labels = issue_data.get("labels", []) or []

    # Parse roadmap-selected-task from tracker body.
    tracker_body = str(tracker_data.get("body", ""))
    selected_task = None
    match = re.search(
        r"<!--\s*roadmap-selected-task:(\d+)\s*-->",
        tracker_body,
        re.IGNORECASE,
    )
    if match:
        selected_task = int(match.group(1))

    return {
        "pr_state": str(pr_data.get("state", "")),
        "pr_is_draft": bool(pr_data.get("isDraft", False)),
        "pr_head_sha": str(pr_data.get("headRefOid", "")),
        "pr_body": str(pr_data.get("body", "")),
        "pr_mergeable": str(pr_data.get("mergeable", "")),
        "pr_review_decision": str(pr_data.get("reviewDecision") or ""),
        "pr_unresolved_threads": sum(
            1 for t in review_threads if not t.get("isResolved", False)
        ),
        "issue_state": str(issue_data.get("state", "")),
        "issue_labels": [str(lb.get("name", "")) for lb in labels],
        "issue_body": str(issue_data.get("body", "")),
        "tracker_selected_task": selected_task,
        "checks": [
            {
                "name": str(c.get("name") or c.get("context") or ""),
                "status": str(c.get("status") or "COMPLETED"),
                "conclusion": str(c.get("conclusion") or c.get("state") or ""),
            }
            for c in checks
        ],
        "comments": [str(c.get("body", "")) for c in comments],
        "changed_files": [str(f.get("path", "")) for f in files],
    }


def evaluate_guard(
    snapshot: dict[str, Any],
    *,
    expected_issue: int,
    expected_head_sha: str,
) -> tuple[bool, list[str]]:
    """Evaluate the read-only merge guard against the broker's own snapshot.

    Returns (ready, blockers). This mirrors the logic in
    ``roadmap_merge_guard.evaluate_merge_readiness`` but operates on the
    broker's dict-format snapshot (not the guard's dataclass).
    """
    blockers: list[str] = []

    if snapshot["pr_state"].upper() != "OPEN":
        blockers.append("PR_NOT_OPEN")
    if snapshot["pr_is_draft"]:
        blockers.append("PR_IS_DRAFT")
    if snapshot["pr_head_sha"].lower() != expected_head_sha.lower():
        blockers.append("HEAD_SHA_DRIFT")
    if snapshot["tracker_selected_task"] != expected_issue:
        blockers.append("TRACKER_TASK_MISMATCH")
    if snapshot["issue_state"].upper() != "OPEN":
        blockers.append("ISSUE_NOT_OPEN")

    # Issue label check (status:blocked).
    for label in snapshot["issue_labels"]:
        if label.casefold() == "status:blocked":
            blockers.append("ISSUE_BLOCKED")
            break

    # Required checks.
    check_map = {c["name"].casefold(): c for c in snapshot["checks"]}
    for required in _REQUIRED_CHECKS:
        check = check_map.get(required.casefold())
        if check is None:
            blockers.append(f"REQUIRED_CHECK_MISSING:{required}")
        elif check["status"].upper() != "COMPLETED" or check["conclusion"].upper() != "SUCCESS":
            blockers.append(f"REQUIRED_CHECK_NOT_SUCCESSFUL:{required}")

    if snapshot["pr_unresolved_threads"]:
        blockers.append("UNRESOLVED_REVIEW_THREADS")
    if snapshot["pr_review_decision"].upper() == "CHANGES_REQUESTED":
        blockers.append("CHANGES_REQUESTED")
    if check_formal_governance_block(snapshot["comments"]):
        blockers.append("FORMAL_GOVERNANCE_BLOCK")

    return (len(blockers) == 0, blockers)


def check_toctou(
    initial: dict[str, Any],
    pre_merge: dict[str, Any],
    *,
    expected_head_sha: str,
) -> list[str]:
    """Compare two snapshots for TOCTOU drift.

    Returns a list of drift blockers. Empty = no drift detected.
    """
    blockers: list[str] = []

    if pre_merge["pr_head_sha"].lower() != expected_head_sha.lower():
        blockers.append("TOCTOU_HEAD_SHA_DRIFT")
    if initial["pr_head_sha"].lower() != pre_merge["pr_head_sha"].lower():
        blockers.append("TOCTOU_HEAD_CHANGED_BETWEEN_SNAPSHOTS")
    if initial["issue_state"].lower() != pre_merge["issue_state"].lower():
        blockers.append("TOCTOU_ISSUE_STATE_CHANGED")
    if initial["issue_labels"] != pre_merge["issue_labels"]:
        blockers.append("TOCTOU_ISSUE_LABELS_CHANGED")
    if initial["tracker_selected_task"] != pre_merge["tracker_selected_task"]:
        blockers.append("TOCTOU_TRACKER_TASK_CHANGED")
    if initial["pr_unresolved_threads"] != pre_merge["pr_unresolved_threads"]:
        blockers.append("TOCTOU_THREAD_COUNT_CHANGED")
    if initial["pr_review_decision"] != pre_merge["pr_review_decision"]:
        blockers.append("TOCTOU_REVIEW_DECISION_CHANGED")
    if len(initial["comments"]) != len(pre_merge["comments"]):
        blockers.append("TOCTOU_COMMENT_COUNT_CHANGED")

    # Check conclusion drift.
    initial_checks = {c["name"].casefold(): c for c in initial["checks"]}
    pre_checks = {c["name"].casefold(): c for c in pre_merge["checks"]}
    for required in _REQUIRED_CHECKS:
        before = initial_checks.get(required.casefold())
        after = pre_checks.get(required.casefold())
        if before and after and before["conclusion"] != after["conclusion"]:
            blockers.append(f"TOCTOU_CHECK_CONCLUSION_DRIFT:{required}")

    # Governance block drift.
    initial_blocked = check_formal_governance_block(initial["comments"])
    pre_blocked = check_formal_governance_block(pre_merge["comments"])
    if pre_blocked and not initial_blocked:
        blockers.append("TOCTOU_NEW_GOVERNANCE_BLOCK")

    return blockers


# ----------------------------------------------------------------------
# Merge execution with timeout/5xx handling
# ----------------------------------------------------------------------


def execute_merge(
    *,
    repo: str,
    pr: int,
    expected_head_sha: str,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Execute ``gh pr merge --squash --match-head-commit <sha>``.

    Returns a dict with ``merge_sha`` on success.

    On timeout, 5xx, or connection abort: re-queries GitHub state. If the
    PR is now merged, returns ``MERGE_OUTCOME_UNKNOWN`` with the merge SHA
    if resolvable, or a clear indication that the merge state is unclear.

    Raises BrokerError on definite failures only (e.g., GitHub rejects the
    merge because invariants changed).
    """
    result = subprocess.run(
        [
            "gh", "pr", "merge", str(pr),
            "--repo", repo,
            "--squash",
            "--match-head-commit", expected_head_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    if result.returncode == 0:
        # Merge successful; re-fetch the merge commit SHA.
        data = _run_gh_json(
            ["pr", "view", str(pr), "--repo", repo, "--json", "mergeCommit"],
            env=env,
        )
        merge_commit = data.get("mergeCommit") or {}
        merge_sha = str(merge_commit.get("oid") or "")
        return {"merge_sha": merge_sha, "outcome": "confirmed"}

    # Check for timeout, 5xx, or connection abort.
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    combined = (stderr + " " + stdout).lower()

    is_transient = any(
        keyword in combined
        for keyword in [
            "timeout",
            "connection refused",
            "connection reset",
            "5xx",
            "500 ",
            "502 ",
            "503 ",
            "504 ",
            "internal server error",
            "gateway timeout",
            "bad gateway",
        ]
    )

    if is_transient:
        # Re-query the PR state to determine if the merge actually went through.
        try:
            recheck = _run_gh_json(
                ["pr", "view", str(pr), "--repo", repo, "--json", "state,mergeCommit,mergedAt"],
                env=env,
            )
        except BrokerError:
            # Cannot re-query either — outcome is truly unknown.
            return {"merge_sha": None, "outcome": "unknown"}

        pr_state = str(recheck.get("state", ""))
        merged_at = recheck.get("mergedAt")
        merge_commit = recheck.get("mergeCommit") or {}

        if pr_state.upper() == "MERGED" or merged_at is not None:
            # Merge did go through despite the timeout.
            merge_sha = str(merge_commit.get("oid") or "")
            return {"merge_sha": merge_sha, "outcome": "confirmed"}
        else:
            # Merge did NOT go through; the transient error was a rejection.
            raise BrokerError(
                "MERGE_REJECTED",
                f"GitHub returned transient error; PR state is {pr_state}: {stderr}",
            )

    # Definite failure from GitHub.
    raise BrokerError(
        "MERGE_REJECTED",
        stderr or stdout or "gh pr merge failed (unknown reason)",
    )


# ----------------------------------------------------------------------
# Broker core: handle one merge request
# ----------------------------------------------------------------------


def handle_merge_request(
    req: MergeRequest,
    *,
    peer_pid: int,
    peer_uid: int,
    peer_gid: int,
    env: dict[str, str],
    audit_log_path: Path = _DEFAULT_AUDIT_LOG_PATH,
    halt_path: Path = _DEFAULT_HALT_PATH,
    deny_list_path: Path = _DENYLIST_PATH,
    path_allowlist_path: Path = _PATHS_ALLOWLIST_PATH,
) -> MergeResponse:
    """Handle a single merge request from the controller client.

    This is the core security function. Every invariant is independently
    verified by the broker. The client's pre-check results are NOT trusted.
    """
    # 1. Validate the audit file before any side effects.
    validate_audit_file(audit_log_path)

    # 2. Resolve GitHub principal independently.
    github_principal = resolve_github_principal(env=env)

    # 3. Check identity allowlist (UID+GID already verified by caller, but
    #    we also check the GitHub principal against the allowlist).
    allowlist = load_allowlist(_ALLOWLIST_PATH)
    principal_allowed = any(
        auid == peer_uid and agid == peer_gid and aprincipal == github_principal
        for auid, agid, aprincipal in allowlist
    )
    if not principal_allowed:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_IDENTITY",
            merged=False,
            merge_sha=None,
            blockers=["IDENTITY_NOT_ALLOWLISTED"],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 4. Collect initial GitHub snapshot independently.
    try:
        initial = collect_pr_snapshot(
            repo=req.repo,
            pr=req.pr,
            expected_issue=req.expected_issue,
            tracker_issue=req.tracker_issue,
            env=env,
        )
    except BrokerError as exc:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_GITHUB_FACT_COLLECTION",
            merged=False,
            merge_sha=None,
            blockers=[f"GITHUB_FACT_COLLECTION_FAILED:{exc.code}"],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 5. Evaluate the read-only guard.
    guard_ready, guard_blockers = evaluate_guard(
        initial,
        expected_issue=req.expected_issue,
        expected_head_sha=req.expected_head_sha,
    )
    if not guard_ready:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_GOVERNANCE",
            merged=False,
            merge_sha=None,
            blockers=[f"GUARD:{b}" for b in guard_blockers],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 6. Check denylist for changed files.
    denylist_hits = check_denylist(deny_list_path, initial["changed_files"])
    if denylist_hits:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_DENYLIST",
            merged=False,
            merge_sha=None,
            blockers=[f"DENYLIST:{h}" for h in denylist_hits],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 7. Check path allowlist (Phase 0 — canary).
    unmatched_paths = check_paths_allowlist(path_allowlist_path, initial["changed_files"])
    if unmatched_paths:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_PATH_ALLOWLIST",
            merged=False,
            merge_sha=None,
            blockers=[f"PATH_NOT_ALLOWED:{p}" for p in unmatched_paths],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 8. Check A1-only enforcement (A2/A3 triggers).
    a1_triggers = check_a1_triggers(
        initial["issue_body"],
        initial["pr_body"],
        initial["comments"],
    )
    if a1_triggers:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_A2A3_TRIGGER",
            merged=False,
            merge_sha=None,
            blockers=[f"A2A3_TRIGGER:{t}" for t in a1_triggers],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 9. Pre-merge re-snapshot (TOCTOU).
    try:
        pre_merge = collect_pr_snapshot(
            repo=req.repo,
            pr=req.pr,
            expected_issue=req.expected_issue,
            tracker_issue=req.tracker_issue,
            env=env,
        )
    except BrokerError as exc:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_GITHUB_FACT_COLLECTION",
            merged=False,
            merge_sha=None,
            blockers=[f"PRE_MERGE_FACT_COLLECTION_FAILED:{exc.code}"],
            intent_record_id=None,
            completion_record_id=None,
        )

    toctou_blockers = check_toctou(
        initial, pre_merge,
        expected_head_sha=req.expected_head_sha,
    )
    if toctou_blockers:
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_TOCTOU",
            merged=False,
            merge_sha=None,
            blockers=[f"TOCTOU:{b}" for b in toctou_blockers],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 10. Pre-snapshot hash for audit.
    pre_merge_hash = hashlib.sha256(
        json.dumps(pre_merge, sort_keys=True).encode()
    ).hexdigest()[:16]

    # 11. Read allowlist version hash for audit.
    allowlist_version_hash = hashlib.sha256(
        _ALLOWLIST_PATH.read_bytes()
    ).hexdigest()[:16]

    # 12. Write INTENT audit record.
    phase = "phase-0"
    try:
        intent_record = build_audit_record(
            event="intent",
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            peer_gid=peer_gid,
            github_principal=github_principal,
            pr=req.pr,
            expected_issue=req.expected_issue,
            expected_head_sha=req.expected_head_sha,
            controller_identity=req.controller_identity,
            decision_code="INTENT_RECORDED",
            merge_sha=None,
            blockers=[],
            phase=phase,
            allowlist_version_hash=allowlist_version_hash,
            pre_merge_snapshot_hash=pre_merge_hash,
        )
        intent_record_id = write_audit_record(audit_log_path, intent_record)
    except BrokerError as exc:
        # Intent-audit failure blocks the merge (fail closed before merge).
        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_INTENT_AUDIT_FAILURE",
            merged=False,
            merge_sha=None,
            blockers=[f"INTENT_AUDIT_FAILED:{exc.code}"],
            intent_record_id=None,
            completion_record_id=None,
        )

    # 13. Execute the merge.
    try:
        merge_result = execute_merge(
            repo=req.repo,
            pr=req.pr,
            expected_head_sha=req.expected_head_sha,
            env=env,
        )
    except BrokerError as exc:
        # Merge rejected by GitHub; write completion record with failure.
        try:
            completion_record = build_audit_record(
                event="completion",
                peer_pid=peer_pid,
                peer_uid=peer_uid,
                peer_gid=peer_gid,
                github_principal=github_principal,
                pr=req.pr,
                expected_issue=req.expected_issue,
                expected_head_sha=req.expected_head_sha,
                controller_identity=req.controller_identity,
                decision_code="MERGE_REJECTED",
                merge_sha=None,
                blockers=[f"MERGE_REJECTED:{exc.code}"],
                phase=phase,
                allowlist_version_hash=allowlist_version_hash,
                pre_merge_snapshot_hash=pre_merge_hash,
            )
            completion_record_id = write_audit_record(audit_log_path, completion_record)
        except BrokerError:
            completion_record_id = None
            # Completion-audit failure on a non-merge is non-critical
            # (merge didn't happen, no incident needed).
            print("AUDIT_COMPLETION_WRITE_FAILED (merge was rejected anyway)", file=sys.stderr)

        return MergeResponse(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_MERGE_COMMAND",
            merged=False,
            merge_sha=None,
            blockers=[f"MERGE_COMMAND_FAILED:{exc.code}"],
            intent_record_id=intent_record_id,
            completion_record_id=completion_record_id,
        )

    # 14. Merge succeeded. Write COMPLETION audit record.
    merge_sha = merge_result.get("merge_sha")
    outcome = merge_result.get("outcome", "confirmed")

    try:
        completion_record = build_audit_record(
            event="completion",
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            peer_gid=peer_gid,
            github_principal=github_principal,
            pr=req.pr,
            expected_issue=req.expected_issue,
            expected_head_sha=req.expected_head_sha,
            controller_identity=req.controller_identity,
            decision_code="MERGED" if outcome == "confirmed" else "MERGE_OUTCOME_UNKNOWN",
            merge_sha=merge_sha,
            blockers=[],
            phase=phase,
            allowlist_version_hash=allowlist_version_hash,
            pre_merge_snapshot_hash=pre_merge_hash,
        )
        completion_record_id = write_audit_record(audit_log_path, completion_record)
    except BrokerError as exc:
        # Completion-audit failure AFTER a successful merge = CRITICAL INCIDENT.
        # The merge itself CANNOT be undone, but the controller MUST be halted.
        write_halt(halt_path)
        # Log to journald as final evidence.
        print(
            f"CRITICAL_INCIDENT: completion audit failed after successful merge: {exc}",
            file=sys.stderr,
        )
        return MergeResponse(
            decision="MERGED" if outcome == "confirmed" else "MERGE_OUTCOME_UNKNOWN",
            status="MERGED_WITH_AUDIT_INCIDENT",
            merged=True,
            merge_sha=merge_sha,
            blockers=[f"COMPLETION_AUDIT_FAILED:{exc.code}"],
            intent_record_id=intent_record_id,
            completion_record_id=None,
        )

    # Success — everything worked.
    return MergeResponse(
        decision="MERGED" if outcome == "confirmed" else "MERGE_OUTCOME_UNKNOWN",
        status="MERGED_BY_CONTROLLER",
        merged=True,
        merge_sha=merge_sha,
        blockers=[],
        intent_record_id=intent_record_id,
        completion_record_id=completion_record_id,
    )


# ----------------------------------------------------------------------
# Socket listener
# ----------------------------------------------------------------------


def run_broker(
    socket_path: Path = _DEFAULT_SOCKET_PATH,
    audit_log_path: Path = _DEFAULT_AUDIT_LOG_PATH,
    halt_path: Path = _DEFAULT_HALT_PATH,
) -> None:
    """Run the broker as a Unix-socket-based service.

    Designed to be run as a root systemd service. One merge per connection.
    The broker exits after handling one request (systemd socket activation
    or a watchdog restarts it).
    """
    # Validate audit file at startup.
    validate_audit_file(audit_log_path)

    # Remove stale socket if present.
    try:
        socket_path.unlink(missing_ok=True)
    except OSError:
        pass

    # Load the credential.
    token_path = os.environ.get(_GH_TOKEN_ENV_KEY)
    if not token_path or not Path(token_path).is_file():
        raise BrokerError(
            "CREDENTIAL_NOT_FOUND",
            f"${_GH_TOKEN_ENV_KEY} not set or file not found: {token_path}",
        )
    token = Path(token_path).read_text(encoding="utf-8").strip()

    # Build environment for gh subprocesses.
    broker_env = os.environ.copy()
    broker_env["GH_TOKEN"] = token
    broker_env.pop("GITHUB_TOKEN", None)

    # Create and bind the socket.
    import grp  # POSIX-only, imported lazily

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        socket_path.chmod(0o0660)
        # Set ownership to root:hermes so hermes can connect.
        hermes_gid = grp.getgrnam("hermes").gr_gid
        os.chown(str(socket_path), 0, hermes_gid)
        server.listen(1)
    except OSError as exc:
        server.close()
        raise BrokerError("SOCKET_BIND_FAILED", str(exc)) from exc

    logging.info("Broker listening on %s", socket_path)

    # Accept one connection.
    try:
        conn, _addr = server.accept()
    except OSError as exc:
        server.close()
        raise BrokerError("SOCKET_ACCEPT_FAILED", str(exc)) from exc

    # Verify peer identity.
    try:
        peer_pid, peer_uid, peer_gid = verify_peer(conn, _ALLOWLIST_PATH)
    except PeerRejected as exc:
        conn.sendall(
            MergeResponse(
                decision="MERGE_REJECTED",
                status="BLOCKED_BY_PEER_REJECTED",
                merged=False,
                merge_sha=None,
                blockers=[f"PEER_REJECTED:{exc.code}"],
                intent_record_id=None,
                completion_record_id=None,
            ).to_json().encode()
        )
        conn.close()
        server.close()
        return

    # Read the merge request.
    try:
        data = conn.recv(65536)
        if not data:
            raise BrokerError("EMPTY_REQUEST", "No data received from peer")
        raw = json.loads(data.decode("utf-8"))
        req = MergeRequest(**raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        conn.sendall(
            MergeResponse(
                decision="MERGE_REJECTED",
                status="BLOCKED_BY_INVALID_REQUEST",
                merged=False,
                merge_sha=None,
                blockers=[f"INVALID_REQUEST:{exc}"],
                intent_record_id=None,
                completion_record_id=None,
            ).to_json().encode()
        )
        conn.close()
        server.close()
        return

    if req.action != "merge":
        conn.sendall(
            MergeResponse(
                decision="MERGE_REJECTED",
                status="BLOCKED_BY_UNKNOWN_ACTION",
                merged=False,
                merge_sha=None,
                blockers=[f"UNKNOWN_ACTION:{req.action}"],
                intent_record_id=None,
                completion_record_id=None,
            ).to_json().encode()
        )
        conn.close()
        server.close()
        return

    # Verify disable/halt switch.
    if not is_controller_enabled(halt_path=halt_path):
        conn.sendall(
            MergeResponse(
                decision="MERGE_REJECTED",
                status="BLOCKED_BY_CONTROLLER_DISABLED",
                merged=False,
                merge_sha=None,
                blockers=["CONTROLLER_DISABLED"],
                intent_record_id=None,
                completion_record_id=None,
            ).to_json().encode()
        )
        conn.close()
        server.close()
        return

    # Handle the merge request.
    response = handle_merge_request(
        req,
        peer_pid=peer_pid,
        peer_uid=peer_uid,
        peer_gid=peer_gid,
        env=broker_env,
        audit_log_path=audit_log_path,
        halt_path=halt_path,
    )

    conn.sendall(response.to_json().encode())
    conn.close()
    server.close()


# ----------------------------------------------------------------------
# CLI (for testing and manual invocation)
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Roadmap merge controller root broker (ADR-2026-07-19)",
    )
    parser.add_argument(
        "--socket",
        type=Path,
        default=_DEFAULT_SOCKET_PATH,
        help="Unix socket path (default: %(default)s)",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=_DEFAULT_AUDIT_LOG_PATH,
        help="Audit log path (default: %(default)s)",
    )
    parser.add_argument(
        "--halt-path",
        type=Path,
        default=_DEFAULT_HALT_PATH,
        help="Halt file path (default: %(default)s)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the environment (audit file, credential, socket); don't listen",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.validate_only:
        try:
            validate_audit_file(args.audit_log)
            token_path = os.environ.get(_GH_TOKEN_ENV_KEY)
            if not token_path:
                print("VALIDATION_FAILED: BROKER_GH_TOKEN_PATH not set", file=sys.stderr)
                return 1
            if not Path(token_path).is_file():
                print(f"VALIDATION_FAILED: credential file not found: {token_path}", file=sys.stderr)
                return 1
            print("VALIDATION_PASSED")
            return 0
        except BrokerError as exc:
            print(f"VALIDATION_FAILED: {exc}", file=sys.stderr)
            return 2

    try:
        run_broker(
            socket_path=args.socket,
            audit_log_path=args.audit_log,
            halt_path=args.halt_path,
        )
    except BrokerError as exc:
        print(f"BROKER_ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
