#!/usr/bin/env python3
"""Deterministic renderer: canonical-roadmap.yaml -> Derived-View Markdown.

The Markdown output carries NO authority (spec §2). Only the YAML is canonical.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

SRC = Path("config/governance/canonical-roadmap.yaml")
DST = Path("docs/roadmap/canonical-program-roadmap.md")
HEADER = (
    "<!--\n"
    "GENERATED FROM config/governance/canonical-roadmap.yaml\n"
    "DO NOT EDIT MANUALLY\n"
    "-->\n"
)


def render(data: dict) -> str:
    lines = [HEADER, "# Canonical Program Roadmap\n",
             f"Roadmap revision: {data['roadmap_revision']}  ",
             f"Governance contract revision: {data['governance_contract_revision']}\n",
             "| Phase | Title | Status | Depends on | Exit gate | Issue(s) | Class |",
             "|---|---|---|---|---|---|---|"]
    for p in data["phases"]:
        deps = ", ".join(p["dependencies"]) or "—"
        issues = p.get("issues") or ([p["issue"]] if "issue" in p else [])
        issues_s = ", ".join(f"#{i}" for i in issues) or "—"
        cls = p.get("execution_class", "—")
        lines.append(
            f"| {p['id']} | {p['title']} | {p['status']} | {deps} "
            f"| {p['exit_gate']} | {issues_s} | {cls} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = ap.parse_args()
    out = render(yaml.safe_load(SRC.read_text()))
    if args.stdout:
        print(out, end="")
    else:
        DST.write_text(out)


if __name__ == "__main__":
    main()
