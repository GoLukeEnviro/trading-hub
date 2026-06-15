#!/usr/bin/env python3
"""Repository secret scanner with redacted findings.

The scanner is intentionally conservative and CI-friendly:
- scans tracked files by default (no runtime/untracked state)
- reports path, line and rule only; never prints matched secret values
- treats committed runtime JSON credentials as high-confidence findings
- ignores schema/property names and environment-variable indirection such as
  ``PASSWORD_ENV`` or ``${TOKEN}``
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MAX_FILE_BYTES = 1_000_000
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(^|_)(api[_-]?key|key|secret|token|password|passphrase|jwt_secret_key|credential)(_|$)|jwt"
)
ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passphrase|jwt[_-]?secret[_-]?key)\b\s*[:=]\s*['\"]?([^'\"\s,#}]+)"
)
TOKEN_RE = re.compile(
    r"(?x)(\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{20,}\b)"
)
PLACEHOLDER_MARKERS = (
    "CHANGE_ME",
    "REDACT",
    "PLACEHOLDER",
    "EXAMPLE",
    "DUMMY",
    "LOCAL_ONLY",
    "YOUR_",
    "<",
)
SAFE_KEY_SUFFIXES = ("_env", "_env_var", "_environment", "_ref", "_reference")
SAFE_VALUE_WORDS = {
    "",
    "null",
    "none",
    "true",
    "false",
    "yes",
    "no",
    "enabled",
    "disabled",
    "operator",
    "cli",
    "status",
    "secret",
    "token",
    "password",
}
SKIP_DIR_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
SCHEMA_PATH_MARKERS = (".schema.json", "/schema/", "/schemas/")
FIXTURE_PATH_MARKERS = ("/tests/fixtures/", "/fixtures/")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    key_path: str = ""

    def redacted(self) -> str:
        suffix = f" key={self.key_path}" if self.key_path else ""
        return f"{self.path}:{self.line}: {self.rule}{suffix}"


def _run_git_ls_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [root / line for line in result.stdout.splitlines() if line]


def _is_probably_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\0" in chunk


def _iter_files(root: Path, tracked: bool, paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p) if Path(p).is_absolute() else root / p for p in paths]
    if tracked:
        return _run_git_ls_files(root)
    return [p for p in root.rglob("*") if p.is_file()]


def _safe_to_skip_path(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    parts = set(Path(rel).parts)
    if parts & SKIP_DIR_PARTS:
        return True
    try:
        return path.stat().st_size > MAX_FILE_BYTES or _is_probably_binary(path)
    except OSError:
        return True


def _is_placeholder(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return True
    text = str(value).strip()
    upper = text.upper()
    if upper in {word.upper() for word in SAFE_VALUE_WORDS}:
        return True
    if text.startswith("${") and text.endswith("}"):
        return True
    if any(marker in upper for marker in PLACEHOLDER_MARKERS):
        return True
    return len(text) < 8


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {char: text.count(char) for char in set(text)}
    return -sum((count / len(text)) * math.log2(count / len(text)) for count in counts.values())


def _looks_like_secret_value(value: object) -> bool:
    if _is_placeholder(value):
        return False
    text = str(value).strip()
    if TOKEN_RE.search(text):
        return True
    if len(text) >= 20 and _entropy(text) >= 3.4:
        return True
    # Runtime config passwords/JWTs are often human-generated and lower entropy.
    return len(text) >= 8


def _key_is_sensitive(key: str) -> bool:
    lower = key.lower()
    if lower.endswith(SAFE_KEY_SUFFIXES):
        return False
    return bool(SENSITIVE_KEY_RE.search(lower))


def _path_is_schema_or_fixture(rel: str) -> bool:
    normalized = "/" + rel
    return any(marker in normalized for marker in SCHEMA_PATH_MARKERS + FIXTURE_PATH_MARKERS)


def _line_for_key(text: str, key: str) -> int:
    needle = f'"{key}"'
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return 1


def _scan_json(path: Path, rel: str, text: str) -> list[Finding]:
    if _path_is_schema_or_fixture(rel):
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    findings: list[Finding] = []

    def walk(obj: object, key_path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{key_path}.{key}" if key_path else str(key)
                is_sensitive_value = (
                    _key_is_sensitive(str(key))
                    and not isinstance(value, (dict, list))
                    and _looks_like_secret_value(value)
                )
                if is_sensitive_value:
                    findings.append(
                        Finding(
                            path=rel,
                            line=_line_for_key(text, str(key)),
                            rule="json-sensitive-key",
                            key_path=current_path,
                        )
                    )
                walk(value, current_path)
        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                walk(item, f"{key_path}[{index}]")

    walk(payload)
    return findings


def _scan_text(path: Path, rel: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if TOKEN_RE.search(line):
            findings.append(Finding(path=rel, line=line_no, rule="known-token-prefix"))
    return findings


def scan_paths(root: Path, files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if not path.exists() or not path.is_file() or _safe_to_skip_path(path, root):
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix == ".json":
            findings.extend(_scan_json(path, rel, text))
        findings.extend(_scan_text(path, rel, text))
    # De-duplicate while preserving deterministic order.
    unique = sorted(set(findings), key=lambda item: (item.path, item.line, item.rule, item.key_path))
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan repository files for high-confidence secrets.")
    parser.add_argument("paths", nargs="*", help="Optional explicit paths to scan instead of the default file set.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--tracked", action="store_true", help="Scan git-tracked files only.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    files = _iter_files(root=root, tracked=args.tracked or not args.paths, paths=args.paths)
    findings = scan_paths(root, files)
    if findings:
        print("Secret scan failed. Redacted findings:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.redacted()}", file=sys.stderr)
        return 1
    print("Secret scan passed: no high-confidence secret findings in scanned files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
