#!/usr/bin/env python3
"""
Memory Hygiene Wrapper — normalises exit codes for the scheduler.

Exit code contract:
  0 = clean or warning-with-findings (policy findings detected)
  2+ = technical failure (actual script error)

The underlying script exits with 1 when policy findings exist.
This wrapper translates that to 0 while preserving the warning output.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "/opt/data/profiles/orchestrator/scripts/memory_hygiene_monitor.py",
        ],
        check=False,
    )

    if result.returncode == 0:
        return 0

    if result.returncode == 1:
        print("WARNING_WITH_FINDINGS: Memory hygiene policy findings detected.")
        return 0

    print(
        f"TECHNICAL_FAILURE: Memory hygiene monitor exited with "
        f"code {result.returncode}.",
        file=sys.stderr,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
