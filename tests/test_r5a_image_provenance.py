"""Regression coverage for the 2026-09-09 R5A recovery incident."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hermes_root import r5a_baseline_build as baseline_build
from hermes_root import r5a_recovery as recovery

FREQ_ID = "sha256:" + "1" * 64
RAINBOW_ID = "sha256:" + "2" * 64


def _lock() -> dict:
    return {
        "version": 1,
        "status": "locked",
        "repository_commit": "a" * 40,
        "freqtrade": {
            "runtime_image_id": FREQ_ID,
            "image_manifest_digest": FREQ_ID,
            "immutable_tag": "hermestrader/freqtrade-r5a:locked",
            "base_digest": "sha256:" + "3" * 64,
            "dockerfile_sha256": "4" * 64,
            "entrypoint_sha256": "5" * 64,
            "source_commit": "6" * 40,
            "config_user": "10000:10000",
        },
        "rainbow": {
            "runtime_image_id": RAINBOW_ID,
            "image_manifest_digest": RAINBOW_ID,
            "immutable_tag": "hermestrader/rainbow-r5a:locked",
            "dockerfile_sha256": "7" * 64,
            "source_lock_sha256": "8" * 64,
            "source_commit": "9" * 40,
            "config_user": "10000:10000",
        },
    }


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_committed_lock_is_complete_and_locked() -> None:
    lock = recovery.load_lock(Path("ops/hermes/hermestrader-dryrun-images.lock.json"))
    assert lock["status"] == "locked"
    assert lock["freqtrade"]["runtime_image_id"] == (
        "sha256:aa4ab78532d996b0d3ac7b034819918e2085495dd1368399705b208d331bd380"
    )
    assert lock["rainbow"]["runtime_image_id"] == (
        "sha256:7e2fab4a87790a1aadebed29b2688ec4c45a80ed9763e69f0d3d285093cc5db0"
    )


def test_wrong_base_digest_fails_closed(tmp_path: Path) -> None:
    lock = _lock()
    lock["freqtrade"]["base_digest"] = "latest"
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(recovery.ProvenanceError, match="BASE_DIGEST_INVALID"):
        recovery.load_lock(path)


def test_valid_but_wrong_base_digest_fails_source_binding(tmp_path: Path) -> None:
    lock = _lock()
    (tmp_path / "freqtrade").mkdir()
    (tmp_path / "ops").mkdir()
    dockerfile = tmp_path / "freqtrade/Dockerfile.hermes10000"
    entrypoint = tmp_path / "freqtrade/entrypoint.sh"
    source_lock = tmp_path / "ops/ai4trade-rainbow.lock.yml"
    dockerfile.write_text(f"FROM freqtradeorg/freqtrade@sha256:{'a' * 64}\n", encoding="utf-8")
    entrypoint.write_text("entrypoint", encoding="utf-8")
    source_lock.write_text("lock", encoding="utf-8")
    lock["freqtrade"]["dockerfile_sha256"] = recovery._sha256(dockerfile)
    lock["freqtrade"]["entrypoint_sha256"] = recovery._sha256(entrypoint)
    lock["rainbow"]["source_lock_sha256"] = recovery._sha256(source_lock)
    with pytest.raises(recovery.ProvenanceError, match="BASE_DIGEST_MISMATCH"):
        recovery.verify_locked_images(lock, repo_root=tmp_path)


def test_wrong_entrypoint_hash_fails_before_docker(tmp_path: Path) -> None:
    lock = _lock()
    (tmp_path / "freqtrade").mkdir()
    (tmp_path / "freqtrade/Dockerfile.hermes10000").write_text("dockerfile", encoding="utf-8")
    (tmp_path / "freqtrade/entrypoint.sh").write_text("wrong", encoding="utf-8")
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops/ai4trade-rainbow.lock.yml").write_text("lock", encoding="utf-8")
    lock["freqtrade"]["dockerfile_sha256"] = recovery._sha256(tmp_path / "freqtrade/Dockerfile.hermes10000")
    lock["rainbow"]["source_lock_sha256"] = recovery._sha256(tmp_path / "ops/ai4trade-rainbow.lock.yml")
    with pytest.raises(recovery.ProvenanceError, match="FREQTRADE_ENTRYPOINT_HASH_MISMATCH"):
        recovery.verify_locked_images(lock, repo_root=tmp_path)


def test_rainbow_wrong_source_lock_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rainbow_root = tmp_path / "rainbow"
    (repo / "freqtrade").mkdir(parents=True)
    (repo / "ops/hermes").mkdir(parents=True)
    rainbow_root.mkdir()
    dockerfile = repo / "freqtrade/Dockerfile.hermes10000"
    entrypoint = repo / "freqtrade/entrypoint.sh"
    source_lock = repo / "ops/ai4trade-rainbow.lock.yml"
    rainbow_dockerfile = rainbow_root / "rainbow.Dockerfile"
    dockerfile.write_text("FROM pinned\n", encoding="utf-8")
    entrypoint.write_text("#!/bin/sh\n", encoding="utf-8")
    source_lock.write_text(f"locked_sha: {'9' * 40}\n", encoding="utf-8")
    rainbow_dockerfile.write_text("FROM pinned\n", encoding="utf-8")
    lock = _lock()
    lock["freqtrade"]["dockerfile_sha256"] = baseline_build._sha256(dockerfile)
    lock["freqtrade"]["entrypoint_sha256"] = baseline_build._sha256(entrypoint)
    lock["rainbow"]["dockerfile_sha256"] = baseline_build._sha256(rainbow_dockerfile)
    lock["rainbow"]["source_lock_sha256"] = "0" * 64
    lock["status"] = "baseline_pending"
    lock_path = repo / "ops/hermes/hermestrader-dryrun-images.lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setattr(baseline_build, "REPO_ROOT", repo)
    monkeypatch.setattr(baseline_build, "RAINBOW_ROOT", rainbow_root)
    monkeypatch.setattr(baseline_build, "LOCK_FILE", lock_path)
    monkeypatch.setattr(baseline_build, "RAINBOW_SOURCE_LOCK", source_lock)

    def run(argv, **_kwargs):
        if argv[-2:] == ["status", "--porcelain"]:
            return _completed()
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return _completed("a" * 40)
        raise AssertionError(argv)

    with pytest.raises(baseline_build.BaselineBuildError, match="SOURCE_LOCK_HASH_MISMATCH"):
        baseline_build.build(run=run)


def test_missing_image_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(recovery, "_verify_source_files", lambda *_: None)

    def run(*_args, **_kwargs):
        return _completed(returncode=1)

    with pytest.raises(recovery.ProvenanceError, match="COMMAND_FAILED:image"):
        recovery.verify_locked_images(_lock(), run=run, repo_root=tmp_path)


def test_rainbow_wrong_image_config_digest_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(recovery, "_verify_source_files", lambda *_: None)

    def run(argv, **_kwargs):
        is_freq = "freqtrade" in argv[-1]
        item = _lock()["freqtrade" if is_freq else "rainbow"]
        labels = {
            "org.opencontainers.image.revision": item["source_commit"],
            "io.trading-hub.r5a.dockerfile-sha256": item["dockerfile_sha256"],
        }
        if is_freq:
            labels.update(
                {
                    "io.trading-hub.r5a.base-digest": item["base_digest"],
                    "io.trading-hub.r5a.entrypoint-sha256": item["entrypoint_sha256"],
                }
            )
        image_id = FREQ_ID if is_freq else "sha256:" + "a" * 64
        return _completed(json.dumps([{
            "Id": image_id,
            "RepoDigests": [f"test@{item['image_manifest_digest']}"],
            "Config": {"User": "10000:10000", "Labels": labels},
        }]))

    with pytest.raises(recovery.ProvenanceError, match="IMAGE_ID_MISMATCH"):
        recovery.verify_locked_images(_lock(), run=run, repo_root=tmp_path)


def _fleet_runner(config: Path, *, drift: bool = False, dry_run: bool = True):
    calls: list[list[str]] = []
    config.write_text(json.dumps({"dry_run": dry_run}), encoding="utf-8")

    def run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[:3] == ["docker", "ps", "-a"]:
            names = [f"{recovery.PROJECT}-{service}-1" for service in recovery.EXPECTED_SERVICES]
            return _completed("\n".join(names) + "\n")
        if argv[:2] == ["docker", "inspect"]:
            name = argv[-1]
            service = name.removeprefix(f"{recovery.PROJECT}-").removesuffix("-1")
            is_rainbow = service == "rainbow"
            image_id = RAINBOW_ID if is_rainbow else FREQ_ID
            if drift and service == recovery.FREQTRADE_SERVICES[0]:
                image_id = "sha256:" + "a" * 64
            mounts = (
                []
                if is_rainbow
                else [
                    {
                        "Source": str(config),
                        "Destination": "/freqtrade/user_data/config.example.json",
                        "RW": False,
                    }
                ]
            )
            return _completed(
                json.dumps(
                    [
                        {
                            "Image": image_id,
                            "RestartCount": 0,
                            "State": {
                                "Running": True,
                                "OOMKilled": False,
                                "Health": {"Status": "healthy"},
                            },
                            "Config": {
                                "Image": "hermestrader/rainbow-r5a:locked"
                                if is_rainbow
                                else "hermestrader/freqtrade-r5a:locked",
                                "Labels": {
                                    "com.docker.compose.project": recovery.PROJECT,
                                    "com.docker.compose.service": service,
                                },
                            },
                            "Mounts": mounts,
                        }
                    ]
                )
            )
        if argv[:2] == ["docker", "compose"]:
            return _completed()
        raise AssertionError(argv)

    return run, calls


def test_image_tag_drift_never_starts_or_recreates(tmp_path: Path) -> None:
    run, calls = _fleet_runner(tmp_path / "config.json", drift=True)
    with pytest.raises(recovery.ProvenanceError, match="CONTAINER_IMAGE_ID_MISMATCH"):
        recovery.verify_existing_fleet(_lock(), run=run)
    assert not any(call[:2] == ["docker", "compose"] for call in calls)
    assert not any("start" in call or "up" in call or "build" in call or "pull" in call for call in calls)


def test_dry_run_false_is_hard_failure(tmp_path: Path) -> None:
    run, calls = _fleet_runner(tmp_path / "config.json", dry_run=False)
    with pytest.raises(recovery.ProvenanceError, match="DRY_RUN_FALSE"):
        recovery.verify_existing_fleet(_lock(), run=run)
    assert not any(call[:2] == ["docker", "compose"] for call in calls)


def test_compose_image_drift_fails_before_deploy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"dry_run": True}), encoding="utf-8")
    services = {
        service: {
            "image": (
                "hermestrader/rainbow-r5a:locked" if service == "rainbow" else "hermestrader/freqtrade-r5a:locked"
            ),
            "volumes": []
            if service == "rainbow"
            else [
                {
                    "type": "bind",
                    "source": str(config),
                    "target": "/freqtrade/user_data/config.example.json",
                    "read_only": True,
                }
            ],
        }
        for service in recovery.EXPECTED_SERVICES
    }
    services[recovery.FREQTRADE_SERVICES[0]]["image"] = "hermestrader/freqtrade-r5a:drift"

    def run(_argv, **_kwargs):
        return _completed(json.dumps({"services": services}))

    with pytest.raises(recovery.ProvenanceError, match="COMPOSE_IMAGE_TAG_MISMATCH"):
        recovery.verify_compose_contract(_lock(), run=run, repo_root=tmp_path)


def test_happy_recovery_uses_compose_start_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run, calls = _fleet_runner(tmp_path / "config.json")
    monkeypatch.setattr(recovery, "load_lock", lambda *_: _lock())
    monkeypatch.setattr(recovery, "verify_locked_images", lambda *_args, **_kwargs: None)
    recovery.execute("start-existing", [], run=run, repo_root=tmp_path, lock_path=tmp_path / "lock")
    compose = [call for call in calls if call[:2] == ["docker", "compose"]]
    assert len(compose) == 1
    assert "start" in compose[0]
    assert "up" not in compose[0]
    assert "build" not in compose[0]
    assert "pull" not in compose[0]


def test_deploy_path_cannot_build_or_pull(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(recovery, "load_lock", lambda *_: _lock())
    monkeypatch.setattr(recovery, "verify_locked_images", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recovery, "verify_compose_contract", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recovery, "verify_post_action_health", lambda *_args, **_kwargs: None)

    def run(argv, **_kwargs):
        calls.append(list(argv))
        return _completed()

    recovery.execute("deploy-locked", [], run=run, repo_root=tmp_path)
    command = calls[-1]
    assert command[-5:] == ["up", "-d", "--no-build", "--pull", "never"]
