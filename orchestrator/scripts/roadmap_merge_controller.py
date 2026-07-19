"""Client-side roadmap merge controller (ADR-2026-07-19).

This module is the **client** side of the merge controller. It performs
lightweight pre-checks (disable switch, writer lock), then delegates the
actual merge decision and execution to the **root broker** via a Unix socket.

The broker at ``/var/run/roadmap-merge-broker.sock`` (root-owned) independently
re-verifies every invariant and holds the merge credential. This module
NEVER calls ``gh pr merge`` directly — the broker does.

Usage (CLI, from the Hermes agent as UID 10000)::

    python -m orchestrator.scripts.roadmap_merge_controller \\
        --repo GoLukeEnviro/trading-hub \\
        --pr 637 \\
        --expected-issue 634 \\
        --expected-head-sha b18bbf0... \\
        --controller-identity roadmap-merge-controller-bot

The controller is **shipped disabled**. The enable switch at
``/opt/data/state/roadmap-merge-controller/enabled`` must exist with
exact content ``true\n`` for any merge to proceed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# ----------------------------------------------------------------------
# Canonical paths
# ----------------------------------------------------------------------

_DEFAULT_SOCKET_PATH = Path("/var/run/roadmap-merge-broker.sock")
_CONTROLLER_STATE_DIR = Path("/opt/data/state/roadmap-merge-controller")
_DISABLE_SWITCH_PATH = _CONTROLLER_STATE_DIR / "enabled"
_HALT_PATH = _CONTROLLER_STATE_DIR / "halt"

# Enable token — only exact match enables the controller.
_ENABLE_TOKEN = "true"


# ----------------------------------------------------------------------
# Result dataclass
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ControllerResult:
    """Stable, JSON-serialisable controller result."""

    decision: str  # MERGED / MERGE_REJECTED / MERGE_OUTCOME_UNKNOWN / CONTROLLER_DISABLED
    status: str
    merged: bool
    merge_sha: Optional[str]
    blockers: list[str]
    broker_response: Optional[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


# ----------------------------------------------------------------------
# Disable switch and halt (fail-closed client-side check)
# ----------------------------------------------------------------------


def is_controller_enabled(
    switch_path: Path = _DISABLE_SWITCH_PATH,
    halt_path: Path = _HALT_PATH,
) -> bool:
    """Return True iff the enable switch is active AND no halt file exists.

    Client-side pre-check only. The broker independently re-verifies this.
    """
    # Halt overrides enable.
    if halt_path.exists():
        return False
    try:
        if not switch_path.is_file():
            return False
        st = switch_path.stat()
        if st.st_uid != 0 or st.st_gid != 0:
            return False
        content = switch_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return content.strip() == _ENABLE_TOKEN and "\n" not in content.rstrip("\n")


# ----------------------------------------------------------------------
# Broker IPC
# ----------------------------------------------------------------------


def _send_to_broker(
    request: dict[str, Any],
    socket_path: Path = _DEFAULT_SOCKET_PATH,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    """Send a JSON request to the root broker and return the response.

    The broker verifies SO_PEERCRED on the other end, so the client's
    self-reported UID/GID are advisory; the broker reads the real
    kernel credentials.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_sec)
    try:
        sock.connect(str(socket_path))
        payload = json.dumps(request).encode("utf-8")
        sock.sendall(payload)
        raw_response = sock.recv(65536)
        if not raw_response:
            raise RuntimeError("Broker returned empty response")
        return json.loads(raw_response.decode("utf-8"))
    finally:
        sock.close()


# ----------------------------------------------------------------------
# Controller entry point
# ----------------------------------------------------------------------


def run_controller(
    *,
    repo: str,
    pr_number: int,
    expected_issue: int,
    expected_head_sha: str,
    tracker_issue: int,
    controller_identity: str,
    socket_path: Path = _DEFAULT_SOCKET_PATH,
    switch_path: Path = _DISABLE_SWITCH_PATH,
    halt_path: Path = _HALT_PATH,
) -> ControllerResult:
    """Run the controller client: pre-check, then delegate to the broker.

    The client does minimum pre-checks. The broker independently verifies
    ALL invariants (guard, denylist, allowlist, TOCTOU, A1-only, etc.)
    and holds the merge credential.

    Args:
        switch_path: Enable switch path (default: production path).
        halt_path: Halt file path (default: production path).
    """
    # 1. Pre-check: disable switch and halt.
    if not is_controller_enabled(switch_path=switch_path, halt_path=halt_path):
        return ControllerResult(
            decision="CONTROLLER_DISABLED",
            status="BLOCKED_BY_CONTROLLER_DISABLED",
            merged=False,
            merge_sha=None,
            blockers=["CONTROLLER_DISABLED"],
            broker_response=None,
        )

    # 2. Build the IPC request.
    request = {
        "action": "merge",
        "repo": repo,
        "pr": pr_number,
        "expected_issue": expected_issue,
        "expected_head_sha": expected_head_sha,
        "tracker_issue": tracker_issue,
        "controller_identity": controller_identity,
        "client_uid": os.getuid() if hasattr(os, "getuid") else 10000,
        "client_gid": os.getgid() if hasattr(os, "getgid") else 10000,
    }

    # 3. Send to broker and return the result.
    try:
        response = _send_to_broker(request, socket_path=socket_path)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        return ControllerResult(
            decision="MERGE_REJECTED",
            status="BLOCKED_BY_BROKER_COMMUNICATION",
            merged=False,
            merge_sha=None,
            blockers=[f"BROKER_COMMUNICATION_FAILED:{exc}"],
            broker_response=None,
        )

    return ControllerResult(
        decision=response.get("decision", "MERGE_REJECTED"),
        status=response.get("status", "UNKNOWN"),
        merged=response.get("merged", False),
        merge_sha=response.get("merge_sha"),
        blockers=response.get("blockers", []),
        broker_response=response.get("status"),
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _full_sha(value: str) -> str:
    import re

    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character commit SHA")
    return value.lower()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Roadmap merge controller client (ADR-2026-07-19). "
            "Delegates merge execution to the root broker. "
            "Shipped disabled — enable switch required."
        ),
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-issue", required=True, type=int)
    parser.add_argument("--expected-head-sha", required=True, type=_full_sha)
    parser.add_argument("--tracker-issue", type=int, default=605)
    parser.add_argument(
        "--controller-identity",
        required=True,
        help="Controller identity recorded in audit (advisory; broker enforces real identity)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_controller(
        repo=args.repo,
        pr_number=args.pr,
        expected_issue=args.expected_issue,
        expected_head_sha=args.expected_head_sha,
        tracker_issue=args.tracker_issue,
        controller_identity=args.controller_identity,
    )
    print(result.to_json())
    if result.merged:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
