#!/usr/bin/env python3
"""Initialize the conservative RiskGuard dry-run baseline (contract v1).

Canonical initializer for the Agent0 dry-run fleet. Writes the versioned
baseline state for the RiskGuard consumer adapter
(``derive_riskguard_status``) using the atomic, validated procedure from
``si_v2.risk.riskguard_baseline``.

Behaviour
---------
- ``--state-path``: target state file (default: repo-relative
  ``orchestrator/state/riskguard/riskguard_state.json`` in this checkout).
- ``--binding-commit``: commit the baseline binds to (default: current
  ``git rev-parse HEAD`` of the checkout).
- ``--backup-dir``: where a pre-existing state file is backed up before a
  re-initialization (default: ``<state-dir>/backup``; never deleted).
- Validation: the baseline is validated before write and the written file is
  re-read and re-validated. Any failure aborts without a partial state.

Safety
------
- Dry-run only. No live authority. No exchange credentials.
- ``freqai-rebel`` and unknown bots are out of scope by construction.
- This script never touches containers, configs, strategies or Docker.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[2]  # self_improvement_v2/scripts/<this> -> repo root
sys.path.insert(0, str(_REPO / "self_improvement_v2" / "src"))

from si_v2.risk.riskguard_baseline import (  # noqa: E402
    CONTRACT_NAME,
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    initialize_baseline,
    validate_state,
)


def _default_state_path() -> Path:
    return _REPO / "orchestrator" / "state" / "riskguard" / "riskguard_state.json"


def _git_head(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="RiskGuard state file (default: <repo>/orchestrator/state/riskguard/riskguard_state.json)",
    )
    parser.add_argument(
        "--binding-commit",
        default=None,
        help="Commit the baseline binds to (default: HEAD of this checkout)",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Backup directory for a pre-existing state file (default: <state-dir>/backup)",
    )
    parser.add_argument(
        "--print-state",
        action="store_true",
        help="Print the written state JSON to stdout (never contains secrets).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    state_path = (args.state_path or _default_state_path()).resolve()
    binding_commit = args.binding_commit or _git_head(_REPO)
    if len(binding_commit) < 7:
        print("INIT_FAILED: cannot determine binding_commit", file=sys.stderr)
        return 1
    backup_dir = args.backup_dir or (state_path.parent / "backup")

    try:
        record = initialize_baseline(
            state_path,
            binding_commit=binding_commit,
            backup_dir=backup_dir,
        )
    except ValueError as exc:
        print(f"INIT_FAILED: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"INIT_FAILED: io_error: {exc}", file=sys.stderr)
        return 1

    # Final read-back + independent validation for the operator log.
    try:
        written = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"INIT_FAILED: read_back_failed: {exc}", file=sys.stderr)
        return 1
    verdict = validate_state(written)
    if not verdict.ok:
        print(f"INIT_FAILED: final_validation: {verdict.reason}", file=sys.stderr)
        return 1

    record["final_validation"] = verdict.to_dict()
    record["contract_name"] = CONTRACT_NAME
    record["contract_version"] = CONTRACT_VERSION
    record["schema_version"] = SCHEMA_VERSION
    print(json.dumps(record, indent=2, sort_keys=True))

    if args.print_state:
        print(state_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
