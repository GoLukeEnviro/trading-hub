"""Rainbow advisory candidate quality evaluator.

Produces a typed, deterministic advisory quality assessment for
ShadowProposal candidates based on Rainbow signal evidence.

Safety invariants (monotonic):
- Rainbow evidence can rank, annotate or downgrade ShadowProposals.
- Rainbow evidence CANNOT increase Autonomy confidence.
- Rainbow evidence CANNOT bypass RiskGuard or Judge.
- Rainbow evidence CANNOT create parameter mutations.
- Rainbow evidence CANNOT authorize execution.
- For identical baseline candidate and gate inputs:
  decision_with_rainbow must be equal to or stricter than
  decision_without_rainbow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


# ── Alignment states ──────────────────────────────────────────────────────


class AlignmentState:
    """Advisory alignment between Rainbow signal and candidate direction."""

    ALIGNED = "ALIGNED"
    CONFLICTING = "CONFLICTING"
    NEUTRAL = "NEUTRAL"
    UNUSABLE = "UNUSABLE"
    ABSENT = "ABSENT"


# ── Quality result ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class RainbowCandidateQuality:
    """Typed advisory quality assessment for a single candidate.

    This is a read-only, non-authoritative assessment. It must not be
    used as Autonomy confidence, RiskGuard confidence, Judge approval,
    or execution authority.

    Attributes:
        source_ids: Rainbow source IDs that contributed evidence.
        evidence_ids: Evidence record IDs from the input pipeline.
        rainbow_direction: Direction from the freshest matching signal.
        rainbow_confidence: Confidence from the freshest matching signal.
        freshness_age_seconds: Age of the freshest signal in seconds.
        reason_codes: Reason codes from the signal metadata.
        quality_status: Overall quality: fresh, stale, degraded, unavailable.
        alignment: Alignment with candidate direction.
        advisory_score: Score for ranking only (0.0-1.0). Not confidence.
        downgrade_reasons: Reasons the candidate should be downgraded.
        usable: Whether the evidence is usable for advisory purposes.
    """

    source_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    rainbow_direction: str | None = None
    rainbow_confidence: float | None = None
    freshness_age_seconds: float | None = None
    reason_codes: tuple[str, ...] = ()
    quality_status: str = "absent"
    alignment: str = AlignmentState.ABSENT
    advisory_score: float = 0.0
    downgrade_reasons: tuple[str, ...] = ()
    usable: bool = False

    def to_dict(self) -> JsonObject:
        return {
            "source_ids": list(self.source_ids),
            "evidence_ids": list(self.evidence_ids),
            "rainbow_direction": self.rainbow_direction,
            "rainbow_confidence": self.rainbow_confidence,
            "freshness_age_seconds": self.freshness_age_seconds,
            "reason_codes": list(self.reason_codes),
            "quality_status": self.quality_status,
            "alignment": self.alignment,
            "advisory_score": self.advisory_score,
            "downgrade_reasons": list(self.downgrade_reasons),
            "usable": self.usable,
        }


# ── Quality evaluator ─────────────────────────────────────────────────────


class RainbowCandidateQualityEvaluator:
    """Evaluate Rainbow evidence quality for candidate ranking.

    Pure, deterministic, no I/O, no network calls, no file writes.
    """

    def __init__(
        self,
        max_signal_age_seconds: float = 3600.0,
        stale_age_seconds: float = 7200.0,
    ) -> None:
        self._max_signal_age = max_signal_age_seconds
        self._stale_age = stale_age_seconds

    def evaluate(
        self,
        candidate_direction: str | None,
        rainbow_signals: list[dict[str, object]],
        rainbow_evidence: list[dict[str, object]],
        now: datetime | None = None,
    ) -> RainbowCandidateQuality:
        """Evaluate Rainbow evidence quality for a candidate.

        Args:
            candidate_direction: Direction of the candidate proposal
                (e.g. "long", "short", "flat", or None).
            rainbow_signals: Validated Rainbow signal envelopes.
            rainbow_evidence: ProposalEvidenceRecord dicts from the
                evidence input pipeline with source_id matching "rainbow:*".
            now: Current time for freshness checks.

        Returns:
            RainbowCandidateQuality with advisory assessment.
        """
        if now is None:
            now = datetime.now(UTC)

        if not rainbow_signals and not rainbow_evidence:
            return RainbowCandidateQuality(alignment=AlignmentState.ABSENT)

        # Collect source IDs and evidence IDs
        source_ids: set[str] = set()
        evidence_ids: set[str] = set()
        for ev in rainbow_evidence:
            sid = ev.get("source_id")
            if isinstance(sid, str):
                source_ids.add(sid)
            eid = ev.get("evidence_id")
            if isinstance(eid, str):
                evidence_ids.add(eid)

        # Find the freshest signal
        freshest_signal = self._find_freshest(rainbow_signals, now)
        if freshest_signal is None:
            return RainbowCandidateQuality(
                source_ids=tuple(sorted(source_ids)),
                evidence_ids=tuple(sorted(evidence_ids)),
                quality_status="absent",
                alignment=AlignmentState.ABSENT,
                usable=False,
            )

        # Extract signal metadata
        direction = self._safe_str(freshest_signal, "direction")
        confidence = self._safe_float(freshest_signal, "confidence")
        ts_str = self._safe_str(freshest_signal, "timestamp_utc")
        reason_codes_raw = freshest_signal.get("metadata", {})
        rc = reason_codes_raw.get("reason_codes", []) if isinstance(reason_codes_raw, dict) else []
        reason_codes = tuple(
            str(r) for r in (rc if isinstance(rc, list) else [])
        )

        # Calculate freshness
        freshness_age: float | None = None
        quality_status = "fresh"
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                age = (now - ts).total_seconds()
                freshness_age = age
                if age > self._stale_age:
                    quality_status = "unavailable"
                elif age > self._max_signal_age:
                    quality_status = "stale"
            except (ValueError, TypeError):
                quality_status = "degraded"

        # Determine alignment
        alignment = self._determine_alignment(candidate_direction, direction)

        # Calculate advisory score (for ranking only, NOT confidence)
        advisory_score = self._compute_advisory_score(
            alignment=alignment,
            quality_status=quality_status,
            confidence=confidence,
            freshness_age=freshness_age,
        )

        # Determine downgrade reasons
        downgrade_reasons: list[str] = []
        if quality_status == "stale":
            downgrade_reasons.append("rainbow_signal_stale")
        elif quality_status == "degraded":
            downgrade_reasons.append("rainbow_signal_degraded")
        elif quality_status == "unavailable":
            downgrade_reasons.append("rainbow_signal_unavailable")
        if alignment == AlignmentState.CONFLICTING:
            downgrade_reasons.append(
                f"rainbow_direction_conflict: signal={direction}, "
                f"candidate={candidate_direction}"
            )
        if alignment == AlignmentState.UNUSABLE:
            downgrade_reasons.append("rainbow_evidence_unusable")

        usable = quality_status == "fresh" and alignment != AlignmentState.UNUSABLE

        return RainbowCandidateQuality(
            source_ids=tuple(sorted(source_ids)),
            evidence_ids=tuple(sorted(evidence_ids)),
            rainbow_direction=direction,
            rainbow_confidence=confidence,
            freshness_age_seconds=freshness_age,
            reason_codes=reason_codes,
            quality_status=quality_status,
            alignment=alignment,
            advisory_score=advisory_score,
            downgrade_reasons=tuple(downgrade_reasons),
            usable=usable,
        )

    def _find_freshest(
        self,
        signals: list[dict[str, object]],
        now: datetime,
    ) -> dict[str, object] | None:
        """Find the freshest signal from a list of envelopes."""
        best: JsonObject | None = None
        best_ts: datetime | None = None

        for signal in signals:
            ts_str = self._safe_str(signal, "timestamp_utc")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best = signal

        return best

    def _determine_alignment(
        self,
        candidate_direction: str | None,
        signal_direction: str | None,
    ) -> str:
        """Determine alignment between candidate and signal direction.

        Alignment rules:
        - If either is None/unknown → NEUTRAL
        - If both are the same direction → ALIGNED
        - If candidate is long and signal is short → CONFLICTING
        - If candidate is short and signal is long → CONFLICTING
        - Otherwise → NEUTRAL
        """
        if candidate_direction is None or signal_direction is None:
            return AlignmentState.NEUTRAL

        cd = candidate_direction.lower().strip()
        sd = signal_direction.lower().strip()

        if cd == sd:
            return AlignmentState.ALIGNED

        # Long vs short conflict
        if {cd, sd} == {"long", "short"}:
            return AlignmentState.CONFLICTING

        return AlignmentState.NEUTRAL

    def _compute_advisory_score(
        self,
        alignment: str,
        quality_status: str,
        confidence: float | None,
        freshness_age: float | None,
    ) -> float:
        """Compute an advisory score for ranking purposes only.

        Rules:
        - Unusable/stale/degraded evidence → 0.0
        - Absent evidence → 0.0
        - Conflicting evidence → 0.0
        - Neutral evidence → 0.3 (informational)
        - Aligned fresh evidence → 0.5 + confidence * 0.5 (max 1.0)
        """
        if quality_status in ("stale", "degraded", "unavailable"):
            return 0.0
        if alignment == AlignmentState.ABSENT:
            return 0.0
        if alignment == AlignmentState.CONFLICTING:
            return 0.0
        if alignment == AlignmentState.NEUTRAL:
            return 0.3
        if alignment == AlignmentState.ALIGNED:
            base = 0.5
            if confidence is not None:
                base += confidence * 0.5
            return min(base, 1.0)
        return 0.0

    @staticmethod
    def _safe_str(d: JsonObject, key: str) -> str | None:
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    @staticmethod
    def _safe_float(d: JsonObject, key: str) -> float | None:
        val = d.get(key)
        if isinstance(val, (int, float)):
            return float(val)
        return None
