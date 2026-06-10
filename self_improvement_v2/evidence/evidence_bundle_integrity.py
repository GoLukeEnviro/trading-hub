"""Evidence Bundle Integrity Manifest generator.

Lists evidence bundle files with stable identifiers and optional
deterministic checksums for known outputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _stable_rel_path(root: Path, file_path: Path) -> str:
    """Compute a stable relative path from root to file_path."""
    return str(file_path.relative_to(root))


def generate_integrity_manifest(
    root: Path | None = None,
) -> dict[str, object]:
    """Generate the evidence bundle integrity manifest.

    Scans the known evidence bundle output files and produces
    a deterministic manifest with file identifiers and SHA-256 hashes.
    """
    root = root or Path("self_improvement_v2")

    bundle_files: list[dict[str, object]] = []

    # Known evidence bundle output directories and patterns
    scan_patterns: list[tuple[str, str]] = [
        ("evidence", "*.json"),
        ("reports/evidence", "*.json"),
        ("reports/readiness", "*.md"),
        ("reports/attribution", "*.json"),
        ("reports/attribution", "*.md"),
        ("episode", "*.json"),
        ("reports/episode", "*.md"),
    ]

    for subdir, glob_pattern in scan_patterns:
        target = root / subdir
        if target.exists():
            for f in sorted(target.glob(glob_pattern)):
                try:
                    content = f.read_bytes()
                    sha256 = hashlib.sha256(content).hexdigest()
                except OSError:
                    sha256 = ""
                bundle_files.append(
                    {
                        "file": _stable_rel_path(root, f),
                        "sha256": sha256,
                        "size_bytes": f.stat().st_size if f.exists() else 0,
                    }
                )

    # Add known fixture directories
    fixture_dirs = [
        "fixtures/rainbow-signals",
        "fixtures/regime-labels",
        "fixtures/source-regime-stats",
    ]
    for fd in fixture_dirs:
        fd_path = root / fd
        if fd_path.exists():
            for f in sorted(fd_path.glob("*.json")):
                try:
                    content = f.read_bytes()
                    sha256 = hashlib.sha256(content).hexdigest()
                except OSError:
                    sha256 = ""
                bundle_files.append(
                    {
                        "file": _stable_rel_path(root, f),
                        "sha256": sha256,
                        "size_bytes": f.stat().st_size if f.exists() else 0,
                    }
                )

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "created_by": "EvidenceBundleIntegrityManifest",
        "generated_at": "",  # empty for determinism; filled at call time if desired
        "file_count": len(bundle_files),
        "files": bundle_files,
    }

    return manifest


def write_manifest(
    output_path: str | Path = "self_improvement_v2/evidence/evidence_bundle_integrity_manifest.json",
    root: Path | None = None,
) -> Path:
    """Generate and write the integrity manifest to disk."""
    output = Path(output_path)
    manifest = generate_integrity_manifest(root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output
