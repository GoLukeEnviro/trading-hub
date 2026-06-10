"""Cross-artifact semantic consistency engine (#151).

Checks that rehearsal planning artifacts (#127-#140) are consistent with
each other: required artifacts exist, cross-references are correct,
verdict semantics do not contradict, no orphan references exist, and
duplicate IDs are detected.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from rehearsal.planning_models import (
    Finding,
    ReasonCode,
    Severity,
    ValidationResult,
    Verdict,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Issues #127-#132 are the prerequisite artifacts referenced by the planning gate
PREREQUISITE_ISSUES: set[str] = {"#127", "#128", "#129", "#130", "#131", "#132"}

# Cross-reference expectations:
#   #135 (gate)    → #127-#132, #136, #137, #139
#   #138 (approval) → #135, #136, #137, #139
#   #140 (readiness) → #135-#139
GATE_REF_ISSUES: set[str] = PREREQUISITE_ISSUES | {"#136", "#137", "#139"}
APPROVAL_REF_ISSUES: set[str] = {"#135", "#136", "#137", "#139"}
READINESS_REF_ISSUES: set[str] = {"#135", "#136", "#137", "#138", "#139"}

# Issue-number pattern inside artifact files
_ISSUE_RE = re.compile(r"#\d{3}")

# Verdict definitions for #135 gate doc (section 5)
GATE_VERDICT_SEMANTICS: dict[str, str] = {
    "GREEN": "proceed",
    "YELLOW": "proceed_with_awareness",
    "RED": "do_not_proceed",
}

# Expected stop-matrix default verdict
STOP_MATRIX_DEFAULT_VERDICT = "BLOCKED"

# Readiness verdict semantics
READINESS_VERDICT_SEMANTICS: dict[str, str] = {
    "GREEN": "proceed",
    "YELLOW": "proceed_with_operator_acknowledgment",
    "RED": "do_not_proceed",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Normalise Unicode for stable cross-platform matching."""
    return unicodedata.normalize("NFKC", text)


def _extract_issue_refs(text: str) -> list[str]:
    """Return sorted unique issue references found in *text*."""
    matches: list[str] = sorted(set(_ISSUE_RE.findall(text)))
    return matches


def _text_for(path: Path) -> str:
    """Read file content as text, raising on binary / unreadable."""
    raw = path.read_bytes()
    try:
        return _normalize(raw.decode("utf-8"))
    except UnicodeDecodeError:
        # Attempt latin-1 fallback for JSON files with non-ASCII
        return _normalize(raw.decode("latin-1"))


def _try_load_json(path: Path) -> dict[str, object] | None:
    """Attempt to parse *path* as JSON; return None on failure."""
    try:
        text = _text_for(path)
        return dict(json.loads(text))
    except (ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# Artifact issue-number extraction
# ---------------------------------------------------------------------------

# Heuristic patterns for extracting the primary "owned" issue number from
# the footer / header of each artifact file.
_ISSUE_OWNER_RE = re.compile(
    r"(?:Created as part of\s+)?#(\d{3})",
)


def _extract_issue_number(text: str, path: Path, fallback: str | None = None) -> str | None:
    """Extract the primary issue number (#NNN) from an artifact.

    Looks for markers like "Created as part of #135" or "#135 — Title".
    Falls back to extracting the first ``#NNN`` found, or *fallback*.
    """
    # Try footer pattern first
    for m in _ISSUE_OWNER_RE.finditer(text):
        return f"#{m.group(1)}"
    # Fallback: first #NNN
    if fallback:
        return fallback
    return None


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

# Verdict tables in gate doc use markdown tables with "**GREEN**", "**YELLOW**", "**RED**"
_GATE_VERDICT_ROW_RE = re.compile(r"\*\*(GREEN|YELLOW|RED)\*\*\s*\|")
# Readiness verdict table in readiness doc
_READINESS_VERDICT_ROW_RE = re.compile(r"\*\*(GREEN|YELLOW|RED)\*\*\s*\|")


def _collect_gate_verdicts(text: str) -> set[str]:
    """Return set of verdict labels defined in the gate doc."""
    verdicts: set[str] = set()
    for m in _GATE_VERDICT_ROW_RE.finditer(text):
        verdicts.add(m.group(1))
    return verdicts


def _collect_readiness_verdicts(text: str) -> set[str]:
    """Return set of verdict labels defined in the readiness doc."""
    verdicts: set[str] = set()
    for m in _READINESS_VERDICT_ROW_RE.finditer(text):
        verdicts.add(m.group(1))
    return verdicts


def _collect_ids(text: str) -> list[str]:
    """Collect all unique IDs (P-NN, F-NN, SC-NN, RR-NN, PG-NN, obs-, ev-) from text."""
    ids: list[str] = []
    # Capture markdown table ID patterns
    for m in re.finditer(r"(?<=\|)\s*(P-\d+|F-\d+|SC-\d+|RR-\d+|PG-\d+)\s*(?=\|)", text):
        ids.append(m.group(1).strip())
    # Capture inline patterns like "id": "SC-01"
    for m in re.finditer(r'"(?:id|check_id)"\s*:\s*"([^"]+)"', text):
        ids.append(m.group(1))
    return ids


def run_semantic_consistency(
    result: ValidationResult,
    artifact_paths: list[str],
) -> ValidationResult:
    """Check cross-artifact semantic consistency for a rehearsal proposal.

    Parameters
    ----------
    result:
        A ``ValidationResult`` instance to which findings are appended.
    artifact_paths:
        Absolute or relative paths to all planning artifacts (issues
        #127-#140) that should be loaded and cross-checked.

    Returns
    -------
    ValidationResult
        The same *result* with findings added in deterministic order.
    """
    # ------------------------------------------------------------------
    # 1. Map issue numbers to artifact paths
    # ------------------------------------------------------------------
    paths = [Path(p).resolve() for p in artifact_paths]
    issue_to_path: dict[str, Path] = {}
    path_to_text: dict[Path, str] = {}
    path_to_json: dict[Path, dict[str, object]] = {}

    for p in paths:
        try:
            if not p.is_file():
                # File doesn't exist — will be caught by artifact-existence check
                continue
            text = _text_for(p)
            path_to_text[p] = text
            data = _try_load_json(p)
            if data is not None:
                path_to_json[p] = data
            issue_num = _extract_issue_number(text, p)
            if issue_num:
                issue_to_path[issue_num] = p
        except OSError:
            # Unreadable — will be caught by MISSING check
            continue

    # ------------------------------------------------------------------
    # 2. Check that all #127-#132 artifacts exist among the paths
    # ------------------------------------------------------------------
    found_prereqs = {iss for iss in PREREQUISITE_ISSUES if iss in issue_to_path}
    missing_prereqs = PREREQUISITE_ISSUES - found_prereqs

    for iss in sorted(missing_prereqs):
        result.add(
            Finding(
                reason_code=ReasonCode.ARTIFACT_MISSING,
                severity=Severity.BLOCKER,
                verdict=Verdict.BLOCKED,
                message=f"Prerequisite artifact {iss} not found in provided paths",
                check_id="SC-PREREQ-EXISTS",
                field_path=f"artifacts/{iss}",
                evidence=f"Expected artifact for {iss} is missing from the provided path list",
                remediation=f"Ensure the artifact for {iss} is included in the path list",
            )
        )

    # ------------------------------------------------------------------
    # 3. Cross-reference checks for #135
    # ------------------------------------------------------------------
    gate_path = issue_to_path.get("#135")
    if gate_path is not None and gate_path in path_to_text:
        gate_text = path_to_text[gate_path]
        gate_refs = set(_extract_issue_refs(gate_text))
        missed = GATE_REF_ISSUES - gate_refs
        for missing_ref in sorted(missed):
            result.add(
                Finding(
                    reason_code=ReasonCode.REFERENCE_MISSING,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"#135 gate doc does not reference {missing_ref}",
                    check_id="SC-REF-135",
                    field_path=f"cross_refs/#135/{missing_ref}",
                    evidence=f"Gate doc at {gate_path.name} missing reference to {missing_ref}",
                    remediation=f"Add a reference to {missing_ref} in the planning gate document",
                )
            )

    # ------------------------------------------------------------------
    # 4. Cross-reference checks for #138 (approval packet)
    # ------------------------------------------------------------------
    approval_path = issue_to_path.get("#138")
    if approval_path is not None and approval_path in path_to_text:
        approval_text = path_to_text[approval_path]
        approval_refs = set(_extract_issue_refs(approval_text))
        missed = APPROVAL_REF_ISSUES - approval_refs
        for missing_ref in sorted(missed):
            result.add(
                Finding(
                    reason_code=ReasonCode.REFERENCE_MISSING,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"#138 approval doc does not reference {missing_ref}",
                    check_id="SC-REF-138",
                    field_path=f"cross_refs/#138/{missing_ref}",
                    evidence=f"Approval doc at {approval_path.name} missing reference to {missing_ref}",
                    remediation=f"Add a reference to {missing_ref} in the approval packet document",
                )
            )

    # ------------------------------------------------------------------
    # 5. Cross-reference checks for #140 (readiness record)
    # ------------------------------------------------------------------
    readiness_path = issue_to_path.get("#140")
    if readiness_path is not None and readiness_path in path_to_text:
        readiness_text = path_to_text[readiness_path]
        readiness_refs = set(_extract_issue_refs(readiness_text))
        missed = READINESS_REF_ISSUES - readiness_refs
        for missing_ref in sorted(missed):
            result.add(
                Finding(
                    reason_code=ReasonCode.REFERENCE_MISSING,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"#140 readiness doc does not reference {missing_ref}",
                    check_id="SC-REF-140",
                    field_path=f"cross_refs/#140/{missing_ref}",
                    evidence=f"Readiness doc at {readiness_path.name} missing reference to {missing_ref}",
                    remediation=f"Add a reference to {missing_ref} in the readiness decision record",
                )
            )

    # ------------------------------------------------------------------
    # 6. Check verdict definitions are consistent
    # ------------------------------------------------------------------

    # 6a. #135 gate defines GREEN/YELLOW/RED
    if gate_path is not None and gate_path in path_to_text:
        gate_verdicts = _collect_gate_verdicts(path_to_text[gate_path])
        expected_verdicts = {"GREEN", "YELLOW", "RED"}
        missing_verdicts = expected_verdicts - gate_verdicts
        for v in sorted(missing_verdicts):
            result.add(
                Finding(
                    reason_code=ReasonCode.MISSING_REQUIRED_FIELD,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"#135 gate doc missing {v} verdict definition",
                    check_id="SC-VERDICT-135",
                    field_path="verdicts/gate",
                    evidence=f"Gate doc at {gate_path.name} does not define {v} verdict",
                    remediation=f"Add {v} verdict row to the gate verdicts table",
                )
            )

    # 6b. #136 stop-matrix default_verdict is BLOCKED
    stop_path = issue_to_path.get("#136")
    if stop_path is not None and stop_path in path_to_json:
        stop_data = path_to_json[stop_path]
        actual_default = stop_data.get("default_verdict", "")
        if actual_default != STOP_MATRIX_DEFAULT_VERDICT:
            result.add(
                Finding(
                    reason_code=ReasonCode.STOP_MATRIX_NOT_BLOCKED,
                    severity=Severity.BLOCKER,
                    verdict=Verdict.BLOCKED,
                    message=(
                        f"#136 stop-matrix default_verdict is '{actual_default}', "
                        f"expected '{STOP_MATRIX_DEFAULT_VERDICT}'"
                    ),
                    check_id="SC-VERDICT-136",
                    field_path="stop_condition_matrix.default_verdict",
                    evidence=f"Found '{actual_default}' instead of '{STOP_MATRIX_DEFAULT_VERDICT}'",
                    remediation=f"Set default_verdict to '{STOP_MATRIX_DEFAULT_VERDICT}'",
                )
            )

    # 6c. #140 readiness defines GREEN/YELLOW/RED
    if readiness_path is not None and readiness_path in path_to_text:
        readiness_verdicts = _collect_readiness_verdicts(path_to_text[readiness_path])
        expected_verdicts = {"GREEN", "YELLOW", "RED"}
        missing_verdicts = expected_verdicts - readiness_verdicts
        for v in sorted(missing_verdicts):
            result.add(
                Finding(
                    reason_code=ReasonCode.MISSING_REQUIRED_FIELD,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"#140 readiness doc missing {v} verdict definition",
                    check_id="SC-VERDICT-140",
                    field_path="verdicts/readiness",
                    evidence=f"Readiness doc at {readiness_path.name} does not define {v} verdict",
                    remediation=f"Add {v} verdict row to the readiness verdicts table",
                )
            )

    # 6d. Contradictory verdicts: gate says RED should block, readiness says RED should block
    if (
        gate_path is not None
        and readiness_path is not None
        and gate_path in path_to_text
        and readiness_path in path_to_text
    ):
        gate_contains_red_proceed = _contains_contradictory_verdict(
            path_to_text[gate_path], "RED", "proceed"
        )
        readiness_contains_green_block = _contains_contradictory_verdict(
            path_to_text[readiness_path], "GREEN", "do not proceed"
        )
        if gate_contains_red_proceed:
            result.add(
                Finding(
                    reason_code=ReasonCode.CONTRADICTORY_VERDICT,
                    severity=Severity.BLOCKER,
                    verdict=Verdict.BLOCKED,
                    message="#135 gate doc defines RED with proceed semantics — contradicts safety policy",
                    check_id="SC-CONTRADICT-135",
                    field_path="verdicts/gate/RED",
                    evidence=f"Gate doc at {gate_path.name} associates RED with proceed",
                    remediation="Ensure RED verdict means 'do not proceed' in the gate doc",
                )
            )
        if readiness_contains_green_block:
            result.add(
                Finding(
                    reason_code=ReasonCode.CONTRADICTORY_VERDICT,
                    severity=Severity.BLOCKER,
                    verdict=Verdict.BLOCKED,
                    message="#140 readiness doc defines GREEN with block semantics — contradicts policy",
                    check_id="SC-CONTRADICT-140",
                    field_path="verdicts/readiness/GREEN",
                    evidence=f"Readiness doc at {readiness_path.name} associates GREEN with do-not-proceed",
                    remediation="Ensure GREEN verdict means 'proceed' in the readiness doc",
                )
            )

    # ------------------------------------------------------------------
    # 7. Orphan references
    # ------------------------------------------------------------------
    all_known_issues: set[str] = set(issue_to_path.keys())
    orphan_check_count = 0

    for p in paths:
        if p not in path_to_text:
            continue
        txt = path_to_text[p]
        refs = _extract_issue_refs(txt)
        for ref in refs:
            if ref not in all_known_issues:
                orphan_check_count += 1
                result.add(
                    Finding(
                        reason_code=ReasonCode.REFERENCE_ORPHAN,
                        severity=Severity.MAJOR,
                        verdict=Verdict.WARNING,
                        message=f"Orphan reference {ref} in {p.name} — no matching artifact found",
                        check_id=f"SC-ORPHAN-{orphan_check_count:03d}",
                        field_path=f"artifacts/{p.name}/references",
                        evidence=f"Found reference {ref} but no artifact provides that issue number",
                        remediation=f"Either add an artifact for {ref} or remove the orphan reference",
                    )
                )

    # ------------------------------------------------------------------
    # 8. Duplicate IDs within artifacts
    # ------------------------------------------------------------------
    for p in paths:
        if p not in path_to_text:
            continue
        txt = path_to_text[p]
        ids = _collect_ids(txt)
        seen: dict[str, int] = {}
        for id_ in ids:
            seen[id_] = seen.get(id_, 0) + 1
        for dup_id, count in sorted(seen.items()):
            if count > 1:
                result.add(
                    Finding(
                        reason_code=ReasonCode.ID_DUPLICATE,
                        severity=Severity.MINOR,
                        verdict=Verdict.WARNING,
                        message=f"Duplicate ID '{dup_id}' appears {count} times in {p.name}",
                        check_id=f"SC-DUPID-{dup_id.replace('-', '_')}",
                        field_path=f"artifacts/{p.name}/ids/{dup_id}",
                        evidence=f"Found {count} occurrences of ID '{dup_id}' in {p.name}",
                        remediation=f"Rename duplicate '{dup_id}' to a unique identifier",
                    )
                )

    # ------------------------------------------------------------------
    # 9. Detect duplicate JSON IDs within stop-condition matrix (#136)
    # ------------------------------------------------------------------
    if stop_path is not None and stop_path in path_to_json:
        stop_data = path_to_json[stop_path]
        conditions = stop_data.get("conditions", [])
        cond_ids: dict[str, int] = {}
        for cond in conditions:
            cid = cond.get("id", "")
            if cid:
                cond_ids[cid] = cond_ids.get(cid, 0) + 1
        for dup_cid, count in sorted(cond_ids.items()):
            if count > 1:
                result.add(
                    Finding(
                        reason_code=ReasonCode.ID_DUPLICATE,
                        severity=Severity.MAJOR,
                        verdict=Verdict.WARNING,
                        message=f"Duplicate condition ID '{dup_cid}' appears {count} times in stop matrix",
                        check_id=f"SC-DUPID-COND-{dup_cid.replace('-', '_')}",
                        field_path=f"stop_condition_matrix.conditions.{dup_cid}",
                        evidence=f"Found {count} occurrences of condition ID '{dup_cid}'",
                        remediation=f"Rename duplicate condition ID '{dup_cid}' to a unique value",
                    )
                )

    # Finalise the result
    result.finalize()
    return result


def _contains_contradictory_verdict(text: str, verdict_label: str, forbidden_phrase: str) -> bool:
    """Check if a verdict table row links *verdict_label* with *forbidden_phrase*.

    Captures everything after the verdict-label cell up to the closing ``|``,
    extracts the last cell, and checks for the forbidden phrase.  For ``RED``
    (forbidden_phrase="proceed") the check is whether the last cell says
    "proceed" without the "do not" negation.  For ``GREEN``
    (forbidden_phrase="do not proceed") the check is whether the last cell
    literally contains that phrase.
    """
    row_re = re.compile(
        rf"\|\s*\*{{0,2}}{re.escape(verdict_label)}\*{{0,2}}\s*\|(.+)\|",
        re.IGNORECASE,
    )
    for m in row_re.finditer(text):
        remainder = m.group(1)
        # Split on | and take last cell
        cells = [c.strip() for c in remainder.split("|")]
        last_cell = cells[-1] if cells else ""
        if forbidden_phrase.lower() == "proceed":
            if "proceed" in last_cell.lower() and "do not proceed" not in last_cell.lower():
                return True
        else:
            if forbidden_phrase.lower() in last_cell.lower():
                return True
    return False
