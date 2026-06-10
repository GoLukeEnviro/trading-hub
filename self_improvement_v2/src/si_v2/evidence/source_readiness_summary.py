"""Source readiness summary for external signal providers.

Reads the source manifest and checks that contract, fixture, and report
paths are present. Emits a GREEN/YELLOW/RED summary per provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ReadinessVerdict(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class ProviderReadiness:
    provider_id: str
    status: str
    contract_ok: bool
    fixtures_ok: bool
    validator_ok: bool
    events_ok: bool
    report_ok: bool
    drift_report_ok: bool
    verdict: ReadinessVerdict
    missing_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReadinessSummary:
    providers: list[ProviderReadiness]
    verdict: ReadinessVerdict
    details: str


class SourceReadinessChecker:
    """Check source readiness from manifest and local artifacts."""

    def __init__(
        self,
        manifest_path: Path | None = None,
    ) -> None:
        self._manifest_path = manifest_path or Path(
            "self_improvement_v2/evidence/source_manifest.json"
        )

    def check(self) -> ReadinessSummary:
        """Run readiness checks for all providers in manifest."""
        if not self._manifest_path.exists():
            return ReadinessSummary(
                providers=[],
                verdict=ReadinessVerdict.RED,
                details=f"Manifest not found: {self._manifest_path}",
            )

        with open(self._manifest_path) as f:
            manifest = dict(json.load(f))

        providers_raw = list(manifest.get("providers", []))
        if not providers_raw:
            return ReadinessSummary(
                providers=[],
                verdict=ReadinessVerdict.YELLOW,
                details="Manifest has no providers registered",
            )

        results: list[ProviderReadiness] = []
        overall = ReadinessVerdict.GREEN

        for provider in providers_raw:
            pid = str(provider.get("provider_id", "unknown"))
            missing: list[str] = []
            warnings_list: list[str] = []

            # Check contract path
            contract_path = str(
                provider.get("contract_path", "")
            )
            contract_ok = Path(contract_path).exists()
            if not contract_ok:
                missing.append(f"contract: {contract_path}")

            # Check fixture path
            fixture_path = str(
                provider.get("fixture_path", "")
            )
            fixtures_ok = (
                Path(fixture_path).exists()
                if fixture_path
                else False
            )
            if not fixtures_ok:
                missing.append(f"fixtures: {fixture_path}")

            # Check validator path
            validator_path = str(
                provider.get("validator_path", "")
            )
            validator_ok = (
                Path(validator_path).exists()
                if validator_path
                else True
            )  # Optional field

            # Check events path
            events_path = str(
                provider.get("events_path", "")
            )
            events_ok = (
                Path(events_path).exists()
                if events_path
                else True
            )

            # Check report path
            report_path = str(
                provider.get("report_path", "")
            )
            report_ok = (
                Path(report_path).exists()
                if report_path
                else True
            )
            if report_path and not report_ok:
                warnings_list.append(
                    f"report not found: {report_path}"
                )

            # Check drift report
            drift_path = str(
                provider.get("drift_report_path", "")
            )
            drift_ok = (
                Path(drift_path).exists()
                if drift_path
                else True
            )
            if drift_path and not drift_ok:
                warnings_list.append(
                    f"drift report not found: {drift_path}"
                )

            # Determine verdict
            if missing:
                pv = ReadinessVerdict.RED
            elif warnings_list:
                pv = ReadinessVerdict.YELLOW
            else:
                pv = ReadinessVerdict.GREEN

            if pv.value == "red":
                overall = ReadinessVerdict.RED
            elif (
                pv.value == "yellow"
                and overall.value != "red"
            ):
                overall = ReadinessVerdict.YELLOW

            results.append(
                ProviderReadiness(
                    provider_id=pid,
                    status=str(
                        provider.get("status", "unknown")
                    ),
                    contract_ok=contract_ok,
                    fixtures_ok=fixtures_ok,
                    validator_ok=validator_ok,
                    events_ok=events_ok,
                    report_ok=report_ok,
                    drift_report_ok=drift_ok,
                    verdict=pv,
                    missing_items=missing,
                    warnings=warnings_list,
                )
            )

        detail_parts: list[str] = []
        for r in results:
            detail_parts.append(
                f"{r.provider_id}: {r.verdict.value}"
            )
        details = "; ".join(detail_parts)

        return ReadinessSummary(
            providers=results,
            verdict=overall,
            details=details,
        )

    def generate_markdown(self) -> str:
        """Generate a deterministic Markdown summary."""
        summary = self.check()
        lines: list[str] = []
        lines.append("# Source Readiness Summary")
        lines.append("")
        lines.append(f"**Overall verdict:** {summary.verdict.value}")
        lines.append(f"**Details:** {summary.details}")
        lines.append("")
        if not summary.providers:
            lines.append("No providers registered.")
            return "\n".join(lines)

        lines.append("## Providers")
        lines.append("")
        lines.append(
            "| Provider | Status | Verdict | Contract | Fixtures | "
            "Validator | Events | Report | Drift |"
        )
        lines.append(
            "|----------|--------|---------|----------|----------|"
            "----------|--------|--------|-------|"
        )
        for p in summary.providers:
            lines.append(
                f"| {p.provider_id} "
                f"| {p.status} "
                f"| {p.verdict.value} "
                f"| {'✅' if p.contract_ok else '❌'} "
                f"| {'✅' if p.fixtures_ok else '❌'} "
                f"| {'✅' if p.validator_ok else '❌'} "
                f"| {'✅' if p.events_ok else '❌'} "
                f"| {'✅' if p.report_ok else '⚠️'} "
                f"| {'✅' if p.drift_report_ok else '⚠️'} |"
            )

        lines.append("")
        for p in summary.providers:
            if p.missing_items:
                lines.append(
                    f"### {p.provider_id} — Missing Items"
                )
                for item in p.missing_items:
                    lines.append(f"- ❌ {item}")
            if p.warnings:
                lines.append(
                    f"### {p.provider_id} — Warnings"
                )
                for w in p.warnings:
                    lines.append(f"- ⚠️ {w}")

        return "\n".join(lines)
