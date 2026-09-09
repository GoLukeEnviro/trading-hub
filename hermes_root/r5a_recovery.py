#!/usr/bin/env python3
"""Fail-closed R5A image provenance gate and bounded recovery entrypoint.

Recovery is deliberately different from deployment: ``start-existing`` can
only call ``docker compose start`` after proving that the exact five stopped
containers, their immutable tags, image IDs, provenance labels and dry-run
configs match the committed lock.  ``deploy-locked`` is the separately gated
reconciliation path and cannot build or pull.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path("/opt/data/projects/trading-hub")
COMPOSE_FILE = REPO_ROOT / "docker-compose.hermestrader-dryrun.yml"
LOCK_FILE = REPO_ROOT / "ops/hermes/hermestrader-dryrun-images.lock.json"
PROJECT = "hermestrader-dryrun"
EXPECTED_SERVICES = (
    "freqtrade-freqforge",
    "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid",
    "freqtrade-webserver",
    "rainbow",
)
FREQTRADE_SERVICES = EXPECTED_SERVICES[:4]
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
Run = Callable[..., subprocess.CompletedProcess[str]]


class ProvenanceError(RuntimeError):
    """A stable fail-closed recovery error."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_json(run: Run, argv: list[str]) -> dict[str, Any]:
    result = run(argv, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProvenanceError(f"COMMAND_FAILED:{argv[1] if len(argv) > 1 else argv[0]}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProvenanceError("INVALID_DOCKER_INSPECT_JSON") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ProvenanceError("INVALID_DOCKER_INSPECT_RESULT")
    return value[0]


def load_lock(path: Path = LOCK_FILE) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvenanceError("IMAGE_LOCK_MISSING_OR_INVALID") from exc
    if data.get("version") != 1:
        raise ProvenanceError("IMAGE_LOCK_VERSION_INVALID")
    if data.get("status") != "locked":
        raise ProvenanceError("IMAGE_BASELINE_PENDING")
    for section in ("freqtrade", "rainbow"):
        item = data.get(section)
        if not isinstance(item, dict):
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_INVALID")
        if not SHA256_RE.fullmatch(str(item.get("runtime_image_id", ""))):
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_IMAGE_ID_INVALID")
        if not SHA256_RE.fullmatch(str(item.get("image_manifest_digest", ""))):
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_MANIFEST_DIGEST_INVALID")
        for key in ("dockerfile_sha256",):
            if not HEX_SHA256_RE.fullmatch(str(item.get(key, ""))):
                raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_{key.upper()}_INVALID")
        if not COMMIT_RE.fullmatch(str(item.get("source_commit", ""))):
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_SOURCE_COMMIT_INVALID")
        immutable_tag = str(item.get("immutable_tag", ""))
        if not immutable_tag or immutable_tag.endswith(":latest"):
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_TAG_INVALID")
        if item.get("config_user") != "10000:10000":
            raise ProvenanceError(f"IMAGE_LOCK_{section.upper()}_USER_INVALID")
    if not HEX_SHA256_RE.fullmatch(str(data["freqtrade"].get("entrypoint_sha256", ""))):
        raise ProvenanceError("IMAGE_LOCK_FREQTRADE_ENTRYPOINT_SHA256_INVALID")
    if not SHA256_RE.fullmatch(str(data["freqtrade"].get("base_digest", ""))):
        raise ProvenanceError("IMAGE_LOCK_FREQTRADE_BASE_DIGEST_INVALID")
    if not HEX_SHA256_RE.fullmatch(str(data["rainbow"].get("source_lock_sha256", ""))):
        raise ProvenanceError("IMAGE_LOCK_RAINBOW_SOURCE_LOCK_SHA256_INVALID")
    if not COMMIT_RE.fullmatch(str(data.get("repository_commit", ""))):
        raise ProvenanceError("IMAGE_LOCK_REPOSITORY_COMMIT_INVALID")
    return data


def _verify_source_files(lock: dict[str, Any], repo_root: Path) -> None:
    freq = lock["freqtrade"]
    rainbow = lock["rainbow"]
    checks = (
        (repo_root / "freqtrade/Dockerfile.hermes10000", freq["dockerfile_sha256"], "FREQTRADE_DOCKERFILE"),
        (repo_root / "freqtrade/entrypoint.sh", freq["entrypoint_sha256"], "FREQTRADE_ENTRYPOINT"),
        (repo_root / "ops/ai4trade-rainbow.lock.yml", rainbow["source_lock_sha256"], "RAINBOW_SOURCE_LOCK"),
    )
    for path, expected, label in checks:
        if not path.is_file() or _sha256(path) != expected:
            raise ProvenanceError(f"{label}_HASH_MISMATCH")
    expected_from = f"FROM freqtradeorg/freqtrade@{freq['base_digest']}"
    dockerfile_lines = (repo_root / "freqtrade/Dockerfile.hermes10000").read_text(encoding="utf-8").splitlines()
    if not dockerfile_lines or dockerfile_lines[0] != expected_from:
        raise ProvenanceError("FREQTRADE_BASE_DIGEST_MISMATCH")


def _verify_image(
    run: Run,
    *,
    image: dict[str, Any],
    expected_labels: dict[str, str],
    expected_user: str,
) -> None:
    tag = image["immutable_tag"]
    inspected = _run_json(run, ["docker", "image", "inspect", tag])
    if inspected.get("Id") != image["runtime_image_id"]:
        raise ProvenanceError("IMAGE_ID_MISMATCH")
    repo_digests = inspected.get("RepoDigests") or []
    if not any(str(digest).endswith(f"@{image['image_manifest_digest']}") for digest in repo_digests):
        raise ProvenanceError("IMAGE_MANIFEST_DIGEST_MISMATCH")
    config = inspected.get("Config") or {}
    if config.get("User") != expected_user:
        raise ProvenanceError("IMAGE_USER_MISMATCH")
    labels = config.get("Labels") or {}
    for key, expected in expected_labels.items():
        if labels.get(key) != expected:
            raise ProvenanceError(f"IMAGE_LABEL_MISMATCH:{key}")


def verify_locked_images(lock: dict[str, Any], *, run: Run = subprocess.run, repo_root: Path = REPO_ROOT) -> None:
    _verify_source_files(lock, repo_root)
    freq = lock["freqtrade"]
    _verify_image(
        run,
        image=freq,
        expected_labels={
            "org.opencontainers.image.revision": freq["source_commit"],
            "io.trading-hub.r5a.base-digest": freq["base_digest"],
            "io.trading-hub.r5a.dockerfile-sha256": freq["dockerfile_sha256"],
            "io.trading-hub.r5a.entrypoint-sha256": freq["entrypoint_sha256"],
        },
        expected_user=freq["config_user"],
    )
    rainbow = lock["rainbow"]
    _verify_image(
        run,
        image=rainbow,
        expected_labels={
            "org.opencontainers.image.revision": rainbow["source_commit"],
            "io.trading-hub.r5a.dockerfile-sha256": rainbow["dockerfile_sha256"],
        },
        expected_user=rainbow["config_user"],
    )


def verify_existing_fleet(lock: dict[str, Any], *, run: Run = subprocess.run) -> None:
    result = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.Names}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProvenanceError("FLEET_INVENTORY_FAILED")
    expected_names = {f"{PROJECT}-{service}-1" for service in EXPECTED_SERVICES}
    if set(result.stdout.splitlines()) != expected_names:
        raise ProvenanceError("FLEET_SET_MISMATCH")

    all_names = run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if all_names.returncode != 0:
        raise ProvenanceError("FLEET_INVENTORY_FAILED")
    if any("freqai-rebel" in name.lower() for name in all_names.stdout.splitlines()):
        raise ProvenanceError("REBEL_PRESENT")

    for service in EXPECTED_SERVICES:
        name = f"{PROJECT}-{service}-1"
        container = _run_json(run, ["docker", "inspect", name])
        image = lock["rainbow"] if service == "rainbow" else lock["freqtrade"]
        if container.get("Image") != image["runtime_image_id"]:
            raise ProvenanceError("CONTAINER_IMAGE_ID_MISMATCH")
        config = container.get("Config") or {}
        if config.get("Image") != image["immutable_tag"]:
            raise ProvenanceError("CONTAINER_IMAGE_TAG_MISMATCH")
        labels = config.get("Labels") or {}
        if labels.get("com.docker.compose.project") != PROJECT or labels.get("com.docker.compose.service") != service:
            raise ProvenanceError("CONTAINER_COMPOSE_LABEL_MISMATCH")
        if service in FREQTRADE_SERVICES:
            configs = [
                mount.get("Source")
                for mount in container.get("Mounts", [])
                if mount.get("Destination") == "/freqtrade/user_data/config.example.json" and mount.get("RW") is False
            ]
            if len(configs) != 1:
                raise ProvenanceError("DRY_RUN_CONFIG_MOUNT_INVALID")
            try:
                dry_run = json.loads(Path(configs[0]).read_text(encoding="utf-8")).get("dry_run")
            except (OSError, json.JSONDecodeError) as exc:
                raise ProvenanceError("DRY_RUN_CONFIG_INVALID") from exc
            if dry_run is not True:
                raise ProvenanceError("DRY_RUN_FALSE")


def verify_compose_contract(lock: dict[str, Any], *, run: Run = subprocess.run, repo_root: Path = REPO_ROOT) -> None:
    """Bind the rendered deployment definition to the lock and dry-run invariant."""
    result = run(
        [
            "docker",
            "compose",
            "-f",
            str(repo_root / COMPOSE_FILE.name),
            "-p",
            PROJECT,
            "config",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProvenanceError("COMPOSE_CONFIG_FAILED")
    try:
        rendered = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProvenanceError("COMPOSE_CONFIG_INVALID") from exc
    services = rendered.get("services") if isinstance(rendered, dict) else None
    if not isinstance(services, dict) or set(services) != set(EXPECTED_SERVICES):
        raise ProvenanceError("COMPOSE_SERVICE_SET_MISMATCH")
    for service in EXPECTED_SERVICES:
        definition = services[service]
        image = lock["rainbow"] if service == "rainbow" else lock["freqtrade"]
        if not isinstance(definition, dict) or definition.get("image") != image["immutable_tag"]:
            raise ProvenanceError("COMPOSE_IMAGE_TAG_MISMATCH")
        if service not in FREQTRADE_SERVICES:
            continue
        configs = [
            volume.get("source")
            for volume in definition.get("volumes", [])
            if isinstance(volume, dict)
            and volume.get("type") == "bind"
            and volume.get("target") == "/freqtrade/user_data/config.example.json"
            and volume.get("read_only") is True
        ]
        if len(configs) != 1:
            raise ProvenanceError("DRY_RUN_CONFIG_MOUNT_INVALID")
        try:
            dry_run = json.loads(Path(configs[0]).read_text(encoding="utf-8")).get("dry_run")
        except (OSError, json.JSONDecodeError) as exc:
            raise ProvenanceError("DRY_RUN_CONFIG_INVALID") from exc
        if dry_run is not True:
            raise ProvenanceError("DRY_RUN_FALSE")


def verify_post_action_health(
    services: list[str],
    *,
    run: Run = subprocess.run,
    timeout_seconds: float = 120,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Require every requested canonical workload to be running and healthy."""
    expected = services or list(EXPECTED_SERVICES)
    deadline = clock() + timeout_seconds
    while True:
        all_healthy = True
        for service in expected:
            container = _run_json(run, ["docker", "inspect", f"{PROJECT}-{service}-1"])
            state = container.get("State") or {}
            health = state.get("Health") or {}
            if container.get("RestartCount") != 0 or state.get("OOMKilled") is not False:
                raise ProvenanceError("FLEET_RUNTIME_STATE_MISMATCH")
            if state.get("Running") is not True or health.get("Status") != "healthy":
                all_healthy = False
        if all_healthy:
            return
        if clock() >= deadline:
            raise ProvenanceError("FLEET_HEALTH_TIMEOUT")
        sleep(2)


def verify_runtime_fleet(
    lock: dict[str, Any],
    *,
    run: Run = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Verify the complete immutable, healthy, dry-run-only R5A runtime.

    This is the canonical read-only A2 gate.  Recovery, Hermes readiness,
    pre-cutover and post-cutover validation must not reimplement a weaker
    subset of these checks.
    """
    verify_locked_images(lock, run=run, repo_root=repo_root)
    verify_compose_contract(lock, run=run, repo_root=repo_root)
    verify_existing_fleet(lock, run=run)
    verify_post_action_health(list(EXPECTED_SERVICES), run=run, timeout_seconds=0)

    containers: list[dict[str, Any]] = []
    for service in EXPECTED_SERVICES:
        name = f"{PROJECT}-{service}-1"
        inspected = _run_json(run, ["docker", "inspect", name])
        state = inspected.get("State") or {}
        health = state.get("Health") or {}
        config = inspected.get("Config") or {}
        containers.append(
            {
                "service": service,
                "name": name,
                "running": state.get("Running") is True,
                "health": health.get("Status"),
                "restart_count": inspected.get("RestartCount"),
                "oom_killed": state.get("OOMKilled"),
                "image_id": inspected.get("Image"),
                "image_tag": config.get("Image"),
            }
        )
    return {
        "version": 1,
        "verified": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT,
        "expected_services": list(EXPECTED_SERVICES),
        "freqtrade_dry_run_count": len(FREQTRADE_SERVICES),
        "rebel_absent": True,
        "image_lock": str(repo_root / "ops/hermes/hermestrader-dryrun-images.lock.json"),
        "image_lock_sha256": _sha256(repo_root / "ops/hermes/hermestrader-dryrun-images.lock.json"),
        "repository_commit": lock["repository_commit"],
        "containers": containers,
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def execute(
    mode: str,
    services: list[str],
    *,
    run: Run = subprocess.run,
    repo_root: Path = REPO_ROOT,
    lock_path: Path = LOCK_FILE,
) -> dict[str, Any] | None:
    if any(service not in EXPECTED_SERVICES for service in services):
        raise ProvenanceError("INVALID_SERVICE")
    lock = load_lock(lock_path)
    if mode == "verify-only":
        if services:
            raise ProvenanceError("INVALID_SERVICE")
        return verify_runtime_fleet(lock, run=run, repo_root=repo_root)
    verify_locked_images(lock, run=run, repo_root=repo_root)
    if mode == "start-existing":
        verify_existing_fleet(lock, run=run)
        command = ["docker", "compose", "-f", str(repo_root / COMPOSE_FILE.name), "-p", PROJECT, "start"]
    elif mode == "deploy-locked":
        verify_compose_contract(lock, run=run, repo_root=repo_root)
        command = [
            "docker",
            "compose",
            "-f",
            str(repo_root / COMPOSE_FILE.name),
            "-p",
            PROJECT,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
        ]
    else:
        raise ProvenanceError("INVALID_MODE")
    command.extend(services)
    result = run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProvenanceError("COMPOSE_ACTION_FAILED")
    verify_post_action_health(services, run=run)
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("BLOCKED_INVALID_MODE", file=sys.stderr)
        return 2
    try:
        evidence = execute(args[0], args[1:])
    except ProvenanceError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 1
    output = os.environ.get("R5A_PROOF_OUTPUT")
    if output and evidence is not None:
        _atomic_json(Path(output), evidence)
    print("R5A_PROVENANCE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
