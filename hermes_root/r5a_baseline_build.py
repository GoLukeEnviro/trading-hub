#!/usr/bin/env python3
"""Bounded one-time builder for a new canonical R5A image baseline."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path("/opt/data/projects/trading-hub")
RAINBOW_ROOT = Path("/opt/data/projects/ai4trade-bot-r5a-6e850c8")
LOCK_FILE = REPO_ROOT / "ops/hermes/hermestrader-dryrun-images.lock.json"
RAINBOW_SOURCE_LOCK = REPO_ROOT / "ops/ai4trade-rainbow.lock.yml"
Run = Callable[..., subprocess.CompletedProcess[str]]


class BaselineBuildError(RuntimeError):
    """A stable fail-closed baseline-build error."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output(run: Run, argv: list[str]) -> str:
    result = run(argv, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise BaselineBuildError(f"COMMAND_FAILED:{argv[0]}")
    return result.stdout.strip()


def _locked_rainbow_sha(text: str) -> str:
    match = re.search(r"(?m)^locked_sha:\s*([0-9a-f]{40})\s*$", text)
    if not match:
        raise BaselineBuildError("RAINBOW_SOURCE_LOCK_INVALID")
    return match.group(1)


def build(*, run: Run = subprocess.run) -> tuple[str, str]:
    try:
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineBuildError("IMAGE_LOCK_MISSING_OR_INVALID") from exc
    if lock.get("status") != "baseline_pending":
        raise BaselineBuildError("BASELINE_BUILD_NOT_PENDING")
    repo_git = ["git", "-c", f"safe.directory={REPO_ROOT}", "-C", str(REPO_ROOT)]
    rainbow_git = ["git", "-c", f"safe.directory={RAINBOW_ROOT}", "-C", str(RAINBOW_ROOT)]
    if _output(run, [*repo_git, "status", "--porcelain"]):
        raise BaselineBuildError("CANONICAL_REPOSITORY_DIRTY")
    repo_commit = _output(run, [*repo_git, "rev-parse", "HEAD"])
    freq = lock["freqtrade"]
    rainbow = lock["rainbow"]
    freq_dockerfile = REPO_ROOT / "freqtrade/Dockerfile.hermes10000"
    entrypoint = REPO_ROOT / "freqtrade/entrypoint.sh"
    source_lock_text = RAINBOW_SOURCE_LOCK.read_text(encoding="utf-8")
    rainbow_sha = _locked_rainbow_sha(source_lock_text)
    if _sha256(freq_dockerfile) != freq["dockerfile_sha256"]:
        raise BaselineBuildError("FREQTRADE_DOCKERFILE_HASH_MISMATCH")
    if _sha256(entrypoint) != freq["entrypoint_sha256"]:
        raise BaselineBuildError("FREQTRADE_ENTRYPOINT_HASH_MISMATCH")
    if _sha256(RAINBOW_SOURCE_LOCK) != rainbow["source_lock_sha256"]:
        raise BaselineBuildError("RAINBOW_SOURCE_LOCK_HASH_MISMATCH")
    if rainbow_sha != rainbow["source_commit"]:
        raise BaselineBuildError("RAINBOW_SOURCE_COMMIT_MISMATCH")
    if _output(run, [*rainbow_git, "rev-parse", "HEAD"]) != rainbow_sha:
        raise BaselineBuildError("RAINBOW_CHECKOUT_COMMIT_MISMATCH")
    if _output(run, [*rainbow_git, "status", "--porcelain"]):
        raise BaselineBuildError("RAINBOW_CHECKOUT_DIRTY")
    rainbow_dockerfile = RAINBOW_ROOT / "rainbow.Dockerfile"
    if _sha256(rainbow_dockerfile) != rainbow["dockerfile_sha256"]:
        raise BaselineBuildError("RAINBOW_DOCKERFILE_HASH_MISMATCH")

    freq_tag = f"hermestrader/freqtrade-r5a:r7a-{repo_commit[:12]}-{freq['dockerfile_sha256'][:12]}"
    rainbow_tag = f"hermestrader/rainbow-r5a:{rainbow_sha[:12]}-{rainbow['dockerfile_sha256'][:12]}"
    commands = (
        [
            "docker",
            "build",
            "--pull",
            "-f",
            str(freq_dockerfile),
            "-t",
            freq_tag,
            "--label",
            f"org.opencontainers.image.revision={repo_commit}",
            "--label",
            f"io.trading-hub.r5a.base-digest={freq['base_digest']}",
            "--label",
            f"io.trading-hub.r5a.dockerfile-sha256={freq['dockerfile_sha256']}",
            "--label",
            f"io.trading-hub.r5a.entrypoint-sha256={freq['entrypoint_sha256']}",
            str(REPO_ROOT / "freqtrade"),
        ],
        [
            "docker",
            "build",
            "--pull",
            "-f",
            str(rainbow_dockerfile),
            "-t",
            rainbow_tag,
            "--label",
            f"org.opencontainers.image.revision={rainbow_sha}",
            "--label",
            f"io.trading-hub.r5a.dockerfile-sha256={rainbow['dockerfile_sha256']}",
            str(RAINBOW_ROOT),
        ],
    )
    for command in commands:
        result = run(command, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise BaselineBuildError("DOCKER_BUILD_FAILED")
    return freq_tag, rainbow_tag


def main() -> int:
    try:
        freq_tag, rainbow_tag = build()
    except (BaselineBuildError, KeyError, OSError) as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 1
    print(f"R5A_FREQTRADE_TAG={freq_tag}")
    print(f"R5A_RAINBOW_TAG={rainbow_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
