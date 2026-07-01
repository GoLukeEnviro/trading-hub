"""SI-v2 Phase 7 — Autonomous Measurement Watcher.

Consumes Phase-6C T0 activation records, reads fleet evidence through
a pluggable evidence-reader, evaluates measurement readiness, emits
KEEP / EXTEND / ROLLBACK decisions, and writes decision packs.

This module is **read-only**. It does NOT:
- Execute any runtime mutation
- Enable schedulers or watchers
- Replace the existing final_decision_pack infrastructure
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: str = "freqtrade-freqforge-canary"
CONTROL_BOT_ID: str = "freqtrade-freqforge"
EXPECTED_NEXT_COMPONENT: str = "autonomous_measurement_watcher"
DECISION_PACK_FILENAME: str = "decision_pack.json"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class T0ActivationRecord:
    """T0 activation record written by Phase 6C Runtime Ceremony Runner."""

    change_id: str
    candidate_id: str
    target_bot: str
    runtime_status: str
    runtime_proof_status: str
    t0_timestamp_utc: str
    next_required_component: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> T0ActivationRecord:
        return cls(
            change_id=str(data.get("change_id", "")),
            candidate_id=str(data.get("candidate_id", "")),
            target_bot=str(data.get("target_bot", "")),
            runtime_status=str(data.get("runtime_status", "")),
            runtime_proof_status=str(data.get("runtime_proof_status", "")),
            t0_timestamp_utc=str(data.get("t0_timestamp_utc", "")),
            next_required_component=str(data.get("next_required_component", "")),
        )


@dataclass(frozen=True)
class MeasurementWatcherInput:
    """All inputs for the autonomous measurement watcher."""

    t0_record_path: str
    """Path to the T0 activation record JSON file."""

    fleet_evidence_ref: str
    """Reference string for the fleet evidence snapshot (e.g. a file path
    or database ref the reader understands)."""

    control_bot: str = CONTROL_BOT_ID
    """Control bot ID for comparison."""

    canary_bot: str = CANARY_BOT_ID
    """Canary bot ID (must match T0 activation record)."""

    min_closed_trades_per_arm: int = 3
    """Minimum number of closed trades on both canary and control before
    a KEEP / ROLLBACK decision can be emitted."""

    max_measurement_age_hours: int = 72
    """If the T0 timestamp is older than this, the measurement is
    considered stale."""

    allow_extend: bool = True
    """If True, EXTEND_MEASUREMENT can be emitted for ambiguous evidence."""


@dataclass(frozen=True)
class MeasurementPoint:
    """A single measurement snapshot from fleet evidence.

    Simplified for the watcher — focuses on the fields needed for
    canary-vs-control comparison.
    """

    label: Literal["T1", "T2", "T3"]
    timestamp_utc: str
    canary_closed_trades: int
    control_closed_trades: int
    canary_open_trades: int
    control_open_trades: int
    canary_profit_abs: float
    control_profit_abs: float
    canary_profit_factor: float | None
    control_profit_factor: float | None
    evidence_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "timestamp_utc": self.timestamp_utc,
            "canary_closed_trades": self.canary_closed_trades,
            "control_closed_trades": self.control_closed_trades,
            "canary_open_trades": self.canary_open_trades,
            "control_open_trades": self.control_open_trades,
            "canary_profit_abs": self.canary_profit_abs,
            "control_profit_abs": self.control_profit_abs,
            "canary_profit_factor": self.canary_profit_factor,
            "control_profit_factor": self.control_profit_factor,
            "evidence_source": self.evidence_source,
        }


@dataclass(frozen=True)
class MeasurementWatcherResult:
    """Structured result from the autonomous measurement watcher."""

    status: Literal[
        "MEASUREMENT_READY",
        "MEASUREMENT_NOT_READY",
        "MEASUREMENT_BLOCKED",
        "FINAL_DECISION_EMITTED",
    ]
    change_id: str
    candidate_id: str
    target_bot: str
    final_decision: Literal[
        "KEEP_CANARY_OVERLAY",
        "EXTEND_MEASUREMENT",
        "ROLLBACK_CANARY_OVERLAY",
        "NONE",
    ]
    measurement_points: tuple[MeasurementPoint, ...]
    blocked_reasons: tuple[str, ...]
    decision_pack_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "autonomous_measurement_watcher_result",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "final_decision": self.final_decision,
            "measurement_points": [mp.to_dict() for mp in self.measurement_points],
            "blocked_reasons": list(self.blocked_reasons),
            "decision_pack_path": self.decision_pack_path,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Evidence Reader Protocol
# ---------------------------------------------------------------------------


class FleetEvidenceReader(Protocol):
    """Protocol for a read-only fleet evidence reader.

    Implementations should read from real Freqtrade dry-run databases,
    REST APIs, or other runtime evidence sources. The watcher does not
    care about the backing store — only that the snapshot dict conforms
    to the expected schema.

    Expected snapshot schema::

        {
            "timestamp_utc": "2026-07-01T12:00:00Z",
            "source": "freqtrade_dry_run_db",
            "control": {
                "bot_id": "freqtrade-freqforge",
                "closed_trades_since_t0": 4,
                "open_trades": 0,
                "profit_abs_since_t0": 1.23,
                "profit_factor_since_t0": 1.31
            },
            "canary": {
                "bot_id": "freqtrade-freqforge-canary",
                "closed_trades_since_t0": 5,
                "open_trades": 1,
                "profit_abs_since_t0": 1.91,
                "profit_factor_since_t0": 1.44
            }
        }
    """

    def read_measurement_snapshot(
        self,
        *,
        change_id: str,
        t0_timestamp_utc: str,
        control_bot: str,
        canary_bot: str,
    ) -> dict[str, object]:
        """Return a fleet measurement snapshot dict.

        Raises ``FileNotFoundError`` or ``ValueError`` if evidence
        is unavailable or invalid.
        """
        ...


# ---------------------------------------------------------------------------
# Decision pack writer
# ---------------------------------------------------------------------------


def _write_decision_pack(
    *,
    change_id: str,
    candidate_id: str,
    target_bot: str,
    decision: str,
    status: str,
    measurement_points: tuple[MeasurementPoint, ...],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
) -> str:
    """Write a decision pack JSON file.

    Returns the path to the written file.

    Raises ``OSError`` if the file cannot be written.
    """
    decision_pack_dir.mkdir(parents=True, exist_ok=True)
    pack = {
        "event": "autonomous_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": decision,
        "status": status,
        "measurement_points": [mp.to_dict() for mp in measurement_points],
        "evidence_ref": evidence_ref,
        "created_at_utc": now_utc,
        "next_required_component": (
            "rollback_executor_or_next_iteration"
            if decision in ("ROLLBACK_CANARY_OVERLAY", "KEEP_CANARY_OVERLAY")
            else "extend_measurement_or_recheck"
        ),
        "runtime_mutation": "NONE",
    }
    filename = f"{change_id[:24]}_{decision_pack_dir.name}_{decision}.json"
    path = decision_pack_dir / filename
    tmp = path.with_suffix(f".json.tmp.{abs(hash(now_utc))}")
    tmp.write_text(json.dumps(pack, indent=2))
    tmp.replace(path)
    return str(path)


# ---------------------------------------------------------------------------
# Evidence snapshot validation
# ---------------------------------------------------------------------------


def _validate_evidence_snapshot(
    snapshot: dict[str, object],
) -> tuple[bool, tuple[str, ...]]:
    """Validate the evidence snapshot dict against the expected schema.

    Returns (valid, reasons).
    """
    reasons: list[str] = []

    if not isinstance(snapshot.get("control"), dict):
        reasons.append("missing_or_invalid: snapshot.control is not a dict")
    if not isinstance(snapshot.get("canary"), dict):
        reasons.append("missing_or_invalid: snapshot.canary is not a dict")
    if not snapshot.get("source"):
        reasons.append("missing: snapshot.source is empty")
    if not snapshot.get("timestamp_utc"):
        reasons.append("missing: snapshot.timestamp_utc is empty")

    for arm, label in [("control", "control"), ("canary", "canary")]:
        arm_data = snapshot.get(arm)
        if not isinstance(arm_data, dict):
            continue
        for field in ("closed_trades_since_t0", "open_trades", "profit_abs_since_t0"):
            val = arm_data.get(field)
            if val is None:
                reasons.append(f"missing: {label}.{field} is None")

    return len(reasons) == 0, tuple(reasons)


def _extract_arm_data(
    arm_dict: dict[str, object],
) -> tuple[int, int, float, float | None]:
    """Extract (closed_trades, open_trades, profit_abs, profit_factor)
    from an arm dict.

    Returns (0, 0, 0.0, None) for missing fields.
    """
    closed_raw: object = arm_dict.get("closed_trades_since_t0", 0)
    closed = int(closed_raw) if closed_raw is not None else 0  # type: ignore[arg-type]
    open_raw: object = arm_dict.get("open_trades", 0)
    open_t = int(open_raw) if open_raw is not None else 0  # type: ignore[arg-type]
    profit_raw: object = arm_dict.get("profit_abs_since_t0", 0.0)
    profit = float(profit_raw) if profit_raw is not None else 0.0  # type: ignore[arg-type]
    pf_raw: object = arm_dict.get("profit_factor_since_t0")
    pf_val: float | None = float(pf_raw) if pf_raw is not None else None  # type: ignore[arg-type]
    return closed, open_t, profit, pf_val


# ---------------------------------------------------------------------------
# Readiness rules
# ---------------------------------------------------------------------------


def _check_measurement_readiness(
    canary_closed: int,
    control_closed: int,
    min_closed_trades: int,
) -> tuple[bool, str | None]:
    """Check whether both arms have enough closed trades.

    Returns (ready, reason_if_not_ready).
    """
    if canary_closed < min_closed_trades:
        return False, (
            f"canary_insufficient_closed_trades: "
            f"canary has {canary_closed} closed trades, "
            f"need at least {min_closed_trades}"
        )
    if control_closed < min_closed_trades:
        return False, (
            f"control_insufficient_closed_trades: "
            f"control has {control_closed} closed trades, "
            f"need at least {min_closed_trades}"
        )
    return True, None


def _check_t0_age(
    t0_timestamp_utc: str,
    max_age_hours: int,
    now_utc: str,
) -> tuple[bool, str | None]:
    """Check if the T0 timestamp is within the max age window.

    Returns (fresh, reason_if_stale).
    """
    try:
        t0_dt = datetime.fromisoformat(t0_timestamp_utc.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        return False, f"timestamp_parse_error: {e}"

    age_hours = (now_dt - t0_dt).total_seconds() / 3600
    if age_hours > max_age_hours:
        return False, (
            f"t0_measurement_stale: {age_hours:.1f} hours since T0 "
            f"(max {max_age_hours} hours)"
        )
    return True, None


# ---------------------------------------------------------------------------
# Snapshot label extraction
# ---------------------------------------------------------------------------


def _extract_snapshot_label(snapshot: dict[str, object]) -> Literal["T1", "T2", "T3"]:
    """Extract the measurement label from an evidence snapshot.

    If the snapshot has a ``label`` field with value ``T1``, ``T2``, or
    ``T3``, it is preserved. Otherwise defaults to ``T1`` (the first
    post-T0 measurement point).

    T0 is never a valid measurement point label — T0 is the activation
    record, not a fleet-evidence snapshot.
    """
    raw = str(snapshot.get("label", "")).upper()
    if raw in ("T1", "T2", "T3"):
        return cast("Literal['T1', 'T2', 'T3']", raw)
    return "T1"


# ---------------------------------------------------------------------------
# Final decision emission
# ---------------------------------------------------------------------------


def _emit_keep_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[MeasurementPoint, ...],
    snapshot: dict[str, object],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
) -> MeasurementWatcherResult:
    """Emit KEEP_CANARY_OVERLAY."""
    pack_path = _write_decision_pack(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        decision="KEEP_CANARY_OVERLAY",
        status="FINAL_DECISION_EMITTED",
        measurement_points=points,
        evidence_ref=evidence_ref,
        decision_pack_dir=decision_pack_dir,
        now_utc=now_utc,
    )
    return MeasurementWatcherResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="KEEP_CANARY_OVERLAY",
        measurement_points=points,
        blocked_reasons=(),
        decision_pack_path=pack_path,
        next_step=(
            f"KEEP_CANARY_OVERLAY emitted for {candidate_id}. "
            f"Canary overlay is performing at or above control baseline. "
            f"Prepare next candidate iteration."
        ),
    )


def _emit_rollback_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[MeasurementPoint, ...],
    snapshot: dict[str, object],
    decision_pack_dir: Path,
    now_utc: str,
    reasons: tuple[str, ...],
) -> MeasurementWatcherResult:
    """Emit ROLLBACK_CANARY_OVERLAY.

    Does NOT execute the rollback — only emits the decision.
    """
    pack_path = _write_decision_pack(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        decision="ROLLBACK_CANARY_OVERLAY",
        status="FINAL_DECISION_EMITTED",
        measurement_points=points,
        evidence_ref=str(snapshot.get("source", "unknown")),
        decision_pack_dir=decision_pack_dir,
        now_utc=now_utc,
    )
    return MeasurementWatcherResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="ROLLBACK_CANARY_OVERLAY",
        measurement_points=points,
        blocked_reasons=reasons,
        decision_pack_path=pack_path,
        next_step=(
            f"ROLLBACK_CANARY_OVERLAY emitted for {candidate_id}. "
            f"Canary is underperforming or safety degraded. "
            f"Rollback is required but not executed by this watcher."
        ),
    )


def _emit_extend_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[MeasurementPoint, ...],
    snapshot: dict[str, object],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
    reasons: tuple[str, ...],
) -> MeasurementWatcherResult:
    """Emit EXTEND_MEASUREMENT."""
    pack_path = _write_decision_pack(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        decision="EXTEND_MEASUREMENT",
        status="FINAL_DECISION_EMITTED",
        measurement_points=points,
        evidence_ref=evidence_ref,
        decision_pack_dir=decision_pack_dir,
        now_utc=now_utc,
    )
    return MeasurementWatcherResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="EXTEND_MEASUREMENT",
        measurement_points=points,
        blocked_reasons=reasons,
        decision_pack_path=pack_path,
        next_step=(
            f"EXTEND_MEASUREMENT emitted for {candidate_id}. "
            f"Evidence is ambiguous — extend measurement window."
        ),
    )


def _determine_final_decision(
    canary_closed: int,
    control_closed: int,
    canary_profit: float,
    control_profit: float,
    canary_pf: float | None,
    control_pf: float | None,
    allow_extend: bool,
) -> tuple[
    Literal["KEEP_CANARY_OVERLAY", "ROLLBACK_CANARY_OVERLAY", "EXTEND_MEASUREMENT"],
    tuple[str, ...],
]:
    """Determine the final decision based on readiness evidence.

    Returns (decision, reasons).
    """
    reasons: list[str] = []

    # Canary vs control profit comparison
    profit_gap = canary_profit - control_profit

    # Profit factor comparison
    pf_available = canary_pf is not None and control_pf is not None
    canary_pf_below_control = False
    if pf_available and canary_pf is not None and control_pf is not None:
        canary_pf_below_control = canary_pf < control_pf

    # Canary clearly outperforms or matches control
    if profit_gap >= 0 and not canary_pf_below_control:
        reasons.append(
            f"canary_outperforms_or_matches: "
            f"profit={canary_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        return "KEEP_CANARY_OVERLAY", tuple(reasons)

    # Canary clearly underperforms
    if profit_gap < -0.01 and canary_pf_below_control:
        reasons.append(
            f"canary_underperforms: "
            f"profit={canary_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        reasons.append(
            f"canary_profit_factor_below_control: "
            f"canary_pf={canary_pf}, control_pf={control_pf}"
        )
        return "ROLLBACK_CANARY_OVERLAY", tuple(reasons)

    # Canary has lower profit but acceptable profit factor
    if profit_gap < -0.01:
        reasons.append(
            f"canary_profit_below_control: "
            f"profit={canary_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        if allow_extend:
            reasons.append("allow_extend=True — extending for more evidence")
            return "EXTEND_MEASUREMENT", tuple(reasons)
        return "ROLLBACK_CANARY_OVERLAY", tuple(reasons)

    # Canary profit matches but profit factor is worse
    if pf_available and canary_pf_below_control and profit_gap >= 0:
        reasons.append(
            f"canary_profit_factor_below_control: "
            f"canary_pf={canary_pf}, control_pf={control_pf}"
        )
        if allow_extend:
            reasons.append("allow_extend=True — extending for more evidence")
            return "EXTEND_MEASUREMENT", tuple(reasons)
        # Small positive profit with worse PF — KEEP but document
        return "KEEP_CANARY_OVERLAY", tuple(reasons)

    # Ambiguous — extend
    reasons.append(
        f"ambiguous_evidence: "
        f"profit_gap={profit_gap:+.4f}, "
        f"pf_available={pf_available}"
    )
    if allow_extend:
        reasons.append("allow_extend=True — extending for more evidence")
        return "EXTEND_MEASUREMENT", tuple(reasons)
    return "KEEP_CANARY_OVERLAY", tuple(reasons)


# ---------------------------------------------------------------------------
# Main watcher function
# ---------------------------------------------------------------------------


def run_autonomous_measurement_watcher(
    input_: MeasurementWatcherInput,
    *,
    evidence_reader: FleetEvidenceReader | None = None,
    decision_pack_dir: Path | None = None,
    now_utc: str | None = None,
) -> MeasurementWatcherResult:
    """Run the autonomous measurement watcher.

    Args:
        input_: All inputs for the watcher.
        evidence_reader: A FleetEvidenceReader implementation. If None,
            the watcher will read the snapshot from the fleet_evidence_ref
            as a JSON file path (for testing with static files).
        decision_pack_dir: Override for decision pack output directory.
            Defaults to ``var/si_v2/measurement_decisions/<change_id>/``.
        now_utc: Override for current UTC time (for testing).

    Returns:
        ``MeasurementWatcherResult`` with decision and evidence.

    Raises:
        FileNotFoundError: If the T0 record or evidence snapshot file
            cannot be read.
        ValueError: If evidence data is structurally invalid.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    blocked: list[str] = []
    points: list[MeasurementPoint] = []

    # ------------------------------------------------------------------
    # Step 1: Read T0 activation record
    # ------------------------------------------------------------------

    if not input_.t0_record_path:
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id="",
            candidate_id="",
            target_bot="",
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=("t0_record_path_empty: no T0 record path provided",),
            decision_pack_path="",
            next_step="Provide a valid T0 activation record path.",
        )

    t0_path = Path(input_.t0_record_path)
    if not t0_path.exists():
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id="",
            candidate_id="",
            target_bot="",
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=(f"t0_record_not_found: {t0_path} does not exist",),
            decision_pack_path="",
            next_step="Ensure the T0 activation record exists before running the watcher.",
        )

    try:
        t0_data: dict[str, object] = json.loads(t0_path.read_text())
        t0_record = T0ActivationRecord.from_dict(t0_data)
    except (json.JSONDecodeError, OSError) as e:
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id="",
            candidate_id="",
            target_bot="",
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=(f"t0_record_read_error: {e}",),
            decision_pack_path="",
            next_step="Fix the T0 activation record file and retry.",
        )

    change_id = t0_record.change_id
    candidate_id = t0_record.candidate_id
    target_bot = t0_record.target_bot

    # ------------------------------------------------------------------
    # Step 2: Validate T0 record
    # ------------------------------------------------------------------

    if t0_record.runtime_status != "CEREMONY_EXECUTED_GREEN":
        blocked.append(
            f"t0_not_green: runtime_status={t0_record.runtime_status!r}, "
            f"expected CEREMONY_EXECUTED_GREEN"
        )
    if t0_record.runtime_proof_status != "GREEN":
        blocked.append(
            f"t0_proof_not_green: runtime_proof_status="
            f"{t0_record.runtime_proof_status!r}, expected GREEN"
        )
    if t0_record.target_bot != input_.canary_bot:
        blocked.append(
            f"t0_wrong_target_bot: {t0_record.target_bot!r} != "
            f"{input_.canary_bot!r}"
        )
    if t0_record.next_required_component != EXPECTED_NEXT_COMPONENT:
        blocked.append(
            f"t0_wrong_next_component: "
            f"{t0_record.next_required_component!r} != "
            f"{EXPECTED_NEXT_COMPONENT!r}"
        )

    if blocked:
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=tuple(blocked),
            decision_pack_path="",
            next_step="Review blocked reasons. T0 record validation failed.",
        )

    # ------------------------------------------------------------------
    # Step 3: Check T0 age
    # ------------------------------------------------------------------

    age_ok, age_reason = _check_t0_age(
        t0_record.t0_timestamp_utc,
        input_.max_measurement_age_hours,
        resolved_now,
    )
    if not age_ok:
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=(age_reason,) if age_reason else ("t0_too_old",),
            decision_pack_path="",
            next_step="T0 measurement window is stale. A fresh ceremony is needed.",
        )

    # ------------------------------------------------------------------
    # Step 4: Read fleet evidence
    # ------------------------------------------------------------------

    snapshot: dict[str, object] = {}

    if evidence_reader is not None:
        # Use the provided reader implementation
        try:
            snapshot = evidence_reader.read_measurement_snapshot(
                change_id=change_id,
                t0_timestamp_utc=t0_record.t0_timestamp_utc,
                control_bot=input_.control_bot,
                canary_bot=input_.canary_bot,
            )
        except (FileNotFoundError, ValueError, OSError) as e:
            return MeasurementWatcherResult(
                status="MEASUREMENT_BLOCKED",
                change_id=change_id,
                candidate_id=candidate_id,
                target_bot=target_bot,
                final_decision="NONE",
                measurement_points=(),
                blocked_reasons=(f"evidence_reader_error: {e}",),
                decision_pack_path="",
                next_step="Fix the evidence reader and retry.",
            )
    else:
        # Fallback: read evidence from JSON file path
        evidence_path = Path(input_.fleet_evidence_ref)
        if not evidence_path.exists():
            return MeasurementWatcherResult(
                status="MEASUREMENT_BLOCKED",
                change_id=change_id,
                candidate_id=candidate_id,
                target_bot=target_bot,
                final_decision="NONE",
                measurement_points=(),
                blocked_reasons=(
                    f"evidence_not_found: {evidence_path} does not exist",
                ),
                decision_pack_path="",
                next_step="Provide a valid evidence snapshot file.",
            )
        try:
            snapshot = json.loads(evidence_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return MeasurementWatcherResult(
                status="MEASUREMENT_BLOCKED",
                change_id=change_id,
                candidate_id=candidate_id,
                target_bot=target_bot,
                final_decision="NONE",
                measurement_points=(),
                blocked_reasons=(f"evidence_read_error: {e}",),
                decision_pack_path="",
                next_step="Fix the evidence snapshot file and retry.",
            )

    # ------------------------------------------------------------------
    # Step 5: Validate evidence snapshot
    # ------------------------------------------------------------------

    valid, validation_reasons = _validate_evidence_snapshot(snapshot)
    if not valid:
        blocked.extend(validation_reasons)

    if blocked:
        return MeasurementWatcherResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=tuple(blocked),
            decision_pack_path="",
            next_step="Fix evidence snapshot and retry.",
        )

    # ------------------------------------------------------------------
    # Step 6: Extract arm data
    # ------------------------------------------------------------------

    control_data = snapshot.get("control", {})
    canary_data = snapshot.get("canary", {})

    control_closed, control_open, control_profit, control_pf = (
        _extract_arm_data(control_data)
    )
    canary_closed, canary_open, canary_profit, canary_pf = (
        _extract_arm_data(canary_data)
    )

    evidence_source = str(snapshot.get("source", "unknown"))
    snapshot_ts = str(snapshot.get("timestamp_utc", resolved_now))

    # Create measurement point
    measurement_point = MeasurementPoint(
        label=_extract_snapshot_label(snapshot),
        timestamp_utc=snapshot_ts,
        canary_closed_trades=canary_closed,
        control_closed_trades=control_closed,
        canary_open_trades=canary_open,
        control_open_trades=control_open,
        canary_profit_abs=canary_profit,
        control_profit_abs=control_profit,
        canary_profit_factor=canary_pf,
        control_profit_factor=control_pf,
        evidence_source=evidence_source,
    )
    points = (measurement_point,)

    # ------------------------------------------------------------------
    # Step 7: Check readiness
    # ------------------------------------------------------------------

    ready, not_ready_reason = _check_measurement_readiness(
        canary_closed,
        control_closed,
        input_.min_closed_trades_per_arm,
    )
    if not ready:
        return MeasurementWatcherResult(
            status="MEASUREMENT_NOT_READY",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            final_decision="NONE",
            measurement_points=points,
            blocked_reasons=(
                (not_ready_reason,) if not_ready_reason else ("insufficient_closed_trades",)
            ),
            decision_pack_path="",
            next_step=(
                f"Measurement not ready. "
                f"Canary: {canary_closed} closed trades, "
                f"Control: {control_closed} closed trades. "
                f"Need at least {input_.min_closed_trades_per_arm} per arm."
            ),
        )

    # ------------------------------------------------------------------
    # Step 8: Emit final decision
    # ------------------------------------------------------------------

    resolved_decision_pack_dir = (
        decision_pack_dir or Path(f"var/si_v2/measurement_decisions/{change_id}")
    )
    evidence_ref = input_.fleet_evidence_ref

    decision, decision_reasons = _determine_final_decision(
        canary_closed=canary_closed,
        control_closed=control_closed,
        canary_profit=canary_profit,
        control_profit=control_profit,
        canary_pf=canary_pf,
        control_pf=control_pf,
        allow_extend=input_.allow_extend,
    )

    if decision == "KEEP_CANARY_OVERLAY":
        return _emit_keep_decision(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            points=points,
            snapshot=snapshot,
            evidence_ref=evidence_ref,
            decision_pack_dir=resolved_decision_pack_dir,
            now_utc=resolved_now,
        )

    if decision == "ROLLBACK_CANARY_OVERLAY":
        return _emit_rollback_decision(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target_bot,
            points=points,
            snapshot=snapshot,
            decision_pack_dir=resolved_decision_pack_dir,
            now_utc=resolved_now,
            reasons=decision_reasons,
        )

    # EXTEND_MEASUREMENT
    return _emit_extend_decision(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        points=points,
        snapshot=snapshot,
        evidence_ref=evidence_ref,
        decision_pack_dir=resolved_decision_pack_dir,
        now_utc=resolved_now,
        reasons=decision_reasons,
    )
