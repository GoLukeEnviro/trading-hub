"""SI v2 Progress Dashboard Generator.

Uses a static offline issue map (not live GitHub queries) to produce
a deterministic Markdown dashboard showing completed, open, and
blocked items by subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SubsystemGroup:
    name: str
    issues: list[dict[str, str]] = field(default_factory=list)


_ISSUE_MAP: list[SubsystemGroup] = [
    SubsystemGroup(
        name="Rainbow Core",
        issues=[
            {"id": "#51-#56", "title": "Validator, snapshot, drift guard core", "status": "done"},
            {"id": "#79", "title": "Rainbow envelope validator", "status": "done"},
            {"id": "#80", "title": "Read-only client", "status": "done"},
            {"id": "#81", "title": "Shadowlock audit events", "status": "done"},
            {"id": "#82", "title": "Contract snapshot", "status": "done"},
            {"id": "#83", "title": "Contract drift guard", "status": "done"},
            {"id": "#84", "title": "Fixture review report", "status": "done"},
            {"id": "#85", "title": "Source status", "status": "done"},
        ],
    ),
    SubsystemGroup(
        name="Post-Rainbow Foundation",
        issues=[
            {"id": "#100", "title": "Client fixture harness", "status": "done"},
            {"id": "#101", "title": "Source manifest", "status": "done"},
            {"id": "#102", "title": "Evidence record schema", "status": "done"},
            {"id": "#103", "title": "Readiness summary", "status": "done"},
            {"id": "#104", "title": "Episode manifest", "status": "done"},
        ],
    ),
    SubsystemGroup(
        name="Offline Pipeline",
        issues=[
            {"id": "#107", "title": "Golden path test", "status": "done"},
            {"id": "#108", "title": "Evidence bundle builder", "status": "done"},
            {"id": "#109", "title": "Regime fixtures", "status": "done"},
            {"id": "#110", "title": "Source-regime stats schema", "status": "done"},
            {"id": "#111", "title": "Attribution aggregator", "status": "done"},
            {"id": "#112", "title": "Offline quality gate", "status": "done"},
        ],
    ),
    SubsystemGroup(
        name="Episode + Readiness",
        issues=[
            {"id": "#97", "title": "Offline episode skeleton", "status": "done"},
            {"id": "#114", "title": "Episode output report renderer", "status": "done"},
            {"id": "#115", "title": "Evidence bundle integrity manifest", "status": "done"},
            {"id": "#116", "title": "Attribution report renderer", "status": "done"},
            {"id": "#117", "title": "Phase 1 readiness matrix", "status": "done"},
            {"id": "#118", "title": "Offline system architecture index", "status": "done"},
        ],
    ),
    SubsystemGroup(
        name="Governance / CI / Approval",
        issues=[
            {"id": "#120", "title": "Offline pipeline smoke workflow", "status": "done"},
            {"id": "#121", "title": "Failure taxonomy and remediation map", "status": "done"},
            {"id": "#122", "title": "Human approval gate checklist", "status": "done"},
            {"id": "#123", "title": "Implementation progress dashboard", "status": "done"},
            {"id": "#124", "title": "Live-readiness blocker inventory", "status": "open"},
            {"id": "#125", "title": "Controlled dry-run rehearsal runbook", "status": "open"},
        ],
    ),
    SubsystemGroup(
        name="Rehearsal Control (upcoming)",
        issues=[
            {"id": "#127", "title": "No-live-trading invariant tests", "status": "pending"},
            {"id": "#128", "title": "Dry-run evidence schema", "status": "pending"},
            {"id": "#129", "title": "Runtime preflight checklist report", "status": "pending"},
            {"id": "#130", "title": "Shadow-mode rehearsal report template", "status": "pending"},
            {"id": "#131", "title": "External adapter boundary audit", "status": "pending"},
            {"id": "#132", "title": "Rehearsal artifact archive manifest", "status": "pending"},
        ],
    ),
]


def _status_icon(status: str) -> str:
    return {"done": "✅", "open": "🔄", "pending": "⏳", "blocked": "❌"}.get(status, "❓")


def generate_dashboard() -> str:
    """Generate deterministic Markdown progress dashboard."""
    lines: list[str] = []
    lines.append("# SI v2 Implementation Progress Dashboard")
    lines.append("")
    lines.append(f"*Generated: deterministic offline snapshot*")
    lines.append("")

    # Overall counts
    total = sum(len(g.issues) for g in _ISSUE_MAP)
    done = sum(1 for g in _ISSUE_MAP for i in g.issues if i["status"] == "done")
    open_items = sum(1 for g in _ISSUE_MAP for i in g.issues if i["status"] == "open")
    pending = sum(1 for g in _ISSUE_MAP for i in g.issues if i["status"] == "pending")

    ready = "GREEN" if pending == 0 and open_items == 0 else "YELLOW" if open_items == 0 else "RED"
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total issues:** {total}")
    lines.append(f"- **Completed:** {done}")
    lines.append(f"- **In progress:** {open_items}")
    lines.append(f"- **Pending:** {pending}")
    lines.append(f"- **Offline readiness:** {ready}")
    lines.append(f"- **Live-readiness:** 🚫 BLOCKED (see #124)")
    lines.append("")

    for group in _ISSUE_MAP:
        lines.append(f"## {group.name}")
        lines.append("")
        lines.append("| Issue | Title | Status |")
        lines.append("|-------|-------|--------|")
        for issue in group.issues:
            icon = _status_icon(issue["status"])
            lines.append(f"| {issue['id']} | {issue['title']} | {icon} {issue['status']} |")
        lines.append("")

    # Next recommended run
    next_issues = [
        i for g in _ISSUE_MAP for i in g.issues
        if i["status"] in ("open", "pending")
    ]
    if next_issues:
        lines.append("## Next Recommended Run")
        lines.append("")
        for ni in next_issues:
            lines.append(f"- {ni['id']}: {ni['title']}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by ProgressDashboard — deterministic, offline, "
        "no GitHub API calls*"
    )

    return "\n".join(lines)
