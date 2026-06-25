#!/usr/bin/env python3
# github_repo_access_check.py — validate GitHub repository access using a local token.
#
# Loads:
#   /opt/data/profiles/orchestrator/secrets/github.env
#   /opt/data/profiles/orchestrator/secrets/github-repositories.json
#
# Uses the GitHub REST API directly (urllib.request). gh is optional.
# Never prints the token.

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_DIR = Path("/opt/data/profiles/orchestrator/secrets")
ENV_FILE = SECRETS_DIR / "github.env"
REPO_FILE = SECRETS_DIR / "github-repositories.json"
API_BASE = "https://api.github.com"
PLACEHOLDER_TOKEN = "PASTE_FINE_GRAINED_GITHUB_TOKEN_HERE"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file without executing shell expansions."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Do not keep literal placeholders or shell references.
            if value == PLACEHOLDER_TOKEN or value.startswith("${"):
                value = ""
            values[key] = value
    return values


def load_token(env_values: dict[str, str]) -> str:
    token = env_values.get("GITHUB_TOKEN", "")
    if not token:
        token = env_values.get("GH_TOKEN", "")
    return token


def load_repo_config(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: repo config missing: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def api_get(url: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-github-repo-access-check/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                parsed = {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
        return exc.code, data
    except urllib.error.URLError as exc:
        print(f"ERROR: request failed for {url}: {exc.reason}", file=sys.stderr)
        return 0, {}


def sanitize_repo_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise ValueError(f"invalid repository name: {name}")
    return name


def summarize_permissions(data: dict) -> str:
    perms = data.get("permissions")
    if not perms or not isinstance(perms, dict):
        return "unknown"
    parts = []
    for key in sorted(perms):
        parts.append(f"{key}={perms[key]}")
    return ",".join(parts) if parts else "none"


def main() -> int:
    if not ENV_FILE.exists():
        print(f"ERROR: env file missing: {ENV_FILE}", file=sys.stderr)
        print("Run: bash orchestrator/scripts/github_auth_bootstrap.sh --init", file=sys.stderr)
        return 2

    env_values = load_env_file(ENV_FILE)
    token = load_token(env_values)

    if not token or token == PLACEHOLDER_TOKEN:
        print("ERROR: GitHub token is missing or still the placeholder.", file=sys.stderr)
        print("Edit: nano /opt/data/profiles/orchestrator/secrets/github.env", file=sys.stderr)
        return 2

    config = load_repo_config(REPO_FILE)
    repos = config.get("repositories", [])
    if not isinstance(repos, list):
        print("ERROR: repositories must be a list", file=sys.stderr)
        return 2

    if gh_available():
        print("gh CLI is available (not required).")
    else:
        print("gh CLI is not available; using urllib.request fallback.")

    required_failed = 0
    optional_failed = 0

    print(f"{'repo':<50} {'reachable':<10} {'default_branch':<18} {'archived':<10} {'required':<10} permissions")
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        raw_name = entry.get("name", "")
        required = bool(entry.get("required", False))
        try:
            name = sanitize_repo_name(raw_name)
        except ValueError as exc:
            print(f"{raw_name:<50} INVALID    {'':18} {'':10} {str(required):<10}")
            if required:
                required_failed += 1
            else:
                optional_failed += 1
            continue

        encoded = name.replace("/", "%2F")
        url = f"{API_BASE}/repos/{encoded}"
        status, data = api_get(url, token)
        reachable = status == 200 and data is not None
        if reachable:
            default_branch = data.get("default_branch", "unknown")
            archived = str(data.get("archived", False)).lower()
            permissions = summarize_permissions(data)
        else:
            default_branch = "n/a"
            archived = "n/a"
            permissions = f"http_{status}"

        print(f"{name:<50} {str(reachable):<10} {default_branch:<18} {archived:<10} {str(required):<10} {permissions}")

        if not reachable:
            if required:
                required_failed += 1
            else:
                optional_failed += 1

    print()
    if required_failed:
        print(f"FAILED: {required_failed} required repository(s) not reachable.")
        return 1
    if optional_failed:
        print(f"OK for required repos; {optional_failed} optional repository(s) not reachable.")
        return 0
    print("All listed repositories are reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
