"""Check for untracked source files in self_improvement_v2/src/.

Scans the source directory and verifies every .py file is tracked by git.
Prints a list of untracked files. Exits 0 if clean, 1 if untracked found.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the untracked source check."""
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        sys.exit(1)

    # Get all .py files in src/
    all_py_files: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        rel = py_file.relative_to(project_root)
        all_py_files.add(str(rel))

    if not all_py_files:
        print("No .py files found in src/")
        sys.exit(0)

    # Get git tracked files
    result = subprocess.run(
        ["git", "ls-files", "--", "self_improvement_v2/src/"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    tracked_files: set[str] = set()
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            tracked_files.add(line)

    # Note: files not yet committed won't appear in ls-files unless staged
    # Also check staged files
    result_staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "self_improvement_v2/src/"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    for line in result_staged.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            tracked_files.add(line)

    untracked = all_py_files - tracked_files

    if untracked:
        print("Untracked source files found:")
        for f in sorted(untracked):
            print(f"  {f}")
        sys.exit(1)
    else:
        print("All source files are tracked by git.")
        sys.exit(0)


if __name__ == "__main__":
    main()
