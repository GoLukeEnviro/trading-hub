"""SI-v2 Phase 10.4 — Post-Fleet Measurement Watcher.

Measures whether a promoted dry-run overlay helped or harmed the selected
fleet target compared with its pre-apply baseline and/or the control bot.

This module is **read-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Enable schedulers or watchers
- Execute rollback
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DECISION_PACK_DIR: str = "var/si_v2/post_fleet_measurement/decision_packs"
DEFAULT_MIN_CLOSED_TRADES: int = 3
DEFAULT_MAX_MEASUREMENT_AGE_HOURS: int = 72

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementStartRecord:
    """Measurement start record written by Phase 10.3 executor.

    Attributes:
        event: Must be "measurement_start_record".
        target_bot: Bot that received the overlay.
        ceremony_status: Status of the ceremony.
        measurement_started_at_utc: ISO 8601 timestamp.
        expected_parameter: Parameter being measured.
        expected_value: Expected parameter value.
        runtime_mutation: Must be "NONE".
    """

    event: str
    target_bot: str
    ceremony_status: str
    measurement_started_at_utc: str
    expected_parameter: str
    expected_value: int | float
    runtime_mutation: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MeasurementStartRecord:
        return cls(
            event=str(data.get("event", "")),
            target_bot=str(data.get("target_bot", "")),
            ceremony_status=str(data.get("ceremony_status", "")),
            measurement_started_at_utc=str(
                data.get("measurement_started_at_utc", "")
            ),
            expected_parameter=str(data.get("expected_parameter", "")),
            expected_value=_safe_numeric(data.get("expected_value", 0)),
            runtime_mutation=str(data.get("runtime_mutation", "")),
        )


@dataclass(frozen=True)
class FleetEvidenceSnapshot:
    """A single post-apply evidence snapshot for a fleet target.

    Attributes:
        label: Measurement point label (T1, T2, T3).
        timestamp_utc: ISO 8601 timestamp.
        target_closed_trades: Closed trades on the target bot since T0.
        target_open_trades: Open trades on the target bot.
        target_profit_abs: Absolute profit on the target bot since T0.
        target_profit_factor: Profit factor on the target bot (optional).
        control_closed_trades: Closed trades on the control bot since T0.
        control_open_trades: Open trades on the control bot.
        control_profit_abs: Absolute profit on the control bot since T0.
        control_profit_factor: Profit factor on the control bot (optional).
        evidence_source: Source description.
    """

    label: Literal["T1", "T2", "T3"]
    timestamp_utc: str
    target_closed_trades: int
    target_open_trades: int
    target_profit_abs: float
    target_profit_factor: float | None
    control_closed_trades: int
    control_open_trades: int
    control_profit_abs: float
    control_profit_factor: float | None
    evidence_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "timestamp_utc": self.timestamp_utc,
            "target_closed_trades": self.target_closed_trades,
            "target_open_trades": self.target_open_trades,
            "target_profit_abs": self.target_profit_abs,
            "target_profit_factor": self.target_profit_factor,
            "control_closed_trades": self.control_closed_trades,
            "control_open_trades": self.control_open_trades,
            "control_profit_abs": self.control_profit_abs,
            "control_profit_factor": self.control_profit_factor,
            "evidence_source": self.evidence_source,
        }


@dataclass(frozen=True)
class PostFleetMeasurementInput:
    """All inputs for the post-fleet measurement watcher.

    Attributes:
        measurement_start_record_path: Path to the measurement_start_record.json
            from Phase 10.3 executor.
        target_bot: Bot that received the overlay.
        control_bot: Control bot for comparison.
        min_closed_trades: Minimum closed trades on both arms before
            a KEEP / ROLLBACK decision can be emitted.
        max_measurement_age_hours: If the measurement start timestamp is
            older than this, the measurement is considered stale.
        allow_extend: If True, EXTEND_MEASUREMENT can be emitted for
            ambiguous evidence.
    """

    measurement_start_record_path: str
    target_bot: str
    control_bot: str = "freqtrade-freqforge"
    min_closed_trades: int = DEFAULT_MIN_CLOSED_TRADES
    max_measurement_age_hours: int = DEFAULT_MAX_MEASUREMENT_AGE_HOURS
    allow_extend: bool = True


@dataclass(frozen=True)
class PostFleetMeasurementResult:
    """Structured result from the post-fleet measurement watcher.

    Attributes:
        status: Overall measurement status.
        change_id: Change ID from the measurement start record.
        candidate_id: Candidate ID (derived from change_id).
        target_bot: Bot that received the overlay.
        final_decision: KEEP / EXTEND / ROLLBACK / NONE.
        measurement_points: Evidence snapshots collected.
        blocked_reasons: Human-readable reasons for blocking.
        decision_pack_path: Path to the written decision pack.
        next_step: Suggested next action.
    """

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
        "KEEP_FLEET_OVERLAY",
        "EXTEND_MEASUREMENT",
        "ROLLBACK_FLEET_OVERLAY",
        "NONE",
    ]
    measurement_points: tuple[FleetEvidenceSnapshot, ...]
    blocked_reasons: tuple[str, ...]
    decision_pack_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "post_fleet_measurement_result",
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
# Helpers
# ---------------------------------------------------------------------------


def _safe_numeric(value: object) -> int | float:
    """Safely convert a value to int or float."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return 0
    return 0


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def _read_json(path: str) -> dict[str, object] | None:
    """Read and parse a JSON file. Returns None on failure."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Measurement start record reader
# ---------------------------------------------------------------------------


def _read_measurement_start_record(
    path: str,
) -> tuple[MeasurementStartRecord | None, tuple[str, ...]]:
    """Read and validate a measurement start record.

    Returns (record, reasons).
    """
    reasons: list[str] = []
    data = _read_json(path)
    if data is None:
        return None, (f"measurement_start_record_not_readable: {path}",)

    record = MeasurementStartRecord.from_dict(data)

    if record.event != "measurement_start_record":
        reasons.append(
            f"unexpected_event: {record.event!r} != measurement_start_record"
        )
    if not record.target_bot:
        reasons.append("target_bot_empty: measurement start record has no target_bot")
    if not record.measurement_started_at_utc:
        reasons.append(
            "measurement_started_at_utc_empty: no timestamp in record"
        )
    if record.runtime_mutation != "NONE":
        reasons.append(
            f"runtime_mutation_not_none: {record.runtime_mutation!r}"
        )

    if reasons:
        return None, tuple(reasons)
    return record, ()


# ---------------------------------------------------------------------------
# Evidence snapshot reader
# ---------------------------------------------------------------------------


class FleetEvidenceReader(Protocol):
    """Protocol for a read-only fleet evidence reader.

    Implementations should read from real Freqtrade dry-run databases
    or other runtime evidence sources.
    """

    def read_fleet_measurement_snapshot(
        self,
        *,
        target_bot: str,
        control_bot: str,
        measurement_started_at_utc: str,
    ) -> dict[str, object]:
        """Return a fleet measurement snapshot dict.

        Expected schema::

            {
                "timestamp_utc": "2026-07-01T12:00:00Z",
                "source": "freqtrade_dry_run_db",
                "label": "T1",
                "target": {
                    "bot_id": "freqtrade-regime-hybrid",
                    "closed_trades_since_t0": 4,
                    "open_trades": 0,
                    "profit_abs_since_t0": 1.23,
                    "profit_factor_since_t0": 1.31
                },
                "control": {
                    "bot_id": "freqtrade-freqforge",
                    "closed_trades_since_t0": 5,
                    "open_trades": 1,
                    "profit_abs_since_t0": 1.91,
                    "profit_factor_since_t0": 1.44
                }
            }

        Raises ``FileNotFoundError`` or ``ValueError`` if evidence
        is unavailable or invalid.
        """
        ...


def _read_evidence_snapshot_from_file(
    path: str,
) -> dict[str, object] | None:
    """Read an evidence snapshot from a JSON file path.

    Used for testing with static files.
    """
    return _read_json(path)


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

    if not isinstance(snapshot.get("target"), dict):
        reasons.append("missing_or_invalid: snapshot.target is not a dict")
    if not isinstance(snapshot.get("control"), dict):
        reasons.append("missing_or_invalid: snapshot.control is not a dict")
    if not snapshot.get("source"):
        reasons.append("missing: snapshot.source is empty")
    if not snapshot.get("timestamp_utc"):
        reasons.append("missing: snapshot.timestamp_utc is empty")

    for arm, label in [("target", "target"), ("control", "control")]:
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
    """Extract (closed_trades, open_trades, profit_abs, profit_factor)."""
    closed_raw: object = arm_dict.get("closed_trades_since_t0", 0)
    closed = int(closed_raw) if closed_raw is not None else 0
    open_raw: object = arm_dict.get("open_trades", 0)
    open_t = int(open_raw) if open_raw is not None else 0
    profit_raw: object = arm_dict.get("profit_abs_since_t0", 0.0)
    profit = float(profit_raw) if profit_raw is not None else 0.0
    pf_raw: object = arm_dict.get("profit_factor_since_t0")
    pf_val: float | None = float(pf_raw) if pf_raw is not None else None
    return closed, open_t, profit, pf_val


# ---------------------------------------------------------------------------
# Readiness rules
# ---------------------------------------------------------------------------


def _check_measurement_readiness(
    target_closed: int,
    control_closed: int,
    min_closed_trades: int,
) -> tuple[bool, str | None]:
    """Check whether both arms have enough closed trades.

    Returns (ready, reason_if_not_ready).
    """
    if target_closed < min_closed_trades:
        return False, (
            f"target_insufficient_closed_trades: "
            f"target has {target_closed} closed trades, "
            f"need at least {min_closed_trades}"
        )
    if control_closed < min_closed_trades:
        return False, (
            f"control_insufficient_closed_trades: "
            f"control has {control_closed} closed trades, "
            f"need at least {min_closed_trades}"
        )
    return True, None


def _check_measurement_age(
    measurement_started_at_utc: str,
    max_age_hours: int,
    now_utc: str,
) -> tuple[bool, str | None]:
    """Check if the measurement start is within the max age window.

    Returns (fresh, reason_if_stale).
    """
    try:
        start_dt = datetime.fromisoformat(
            measurement_started_at_utc.replace("Z", "+00:00")
        )
        now_dt = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        return False, f"timestamp_parse_error: {e}"

    age_hours = (now_dt - start_dt).total_seconds() / 3600
    if age_hours > max_age_hours:
        return False, (
            f"measurement_stale: {age_hours:.1f} hours since start "
            f"(max {max_age_hours} hours)"
        )
    return True, None


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def _determine_final_decision(
    target_closed: int,
    control_closed: int,
    target_profit: float,
    control_profit: float,
    target_pf: float | None,
    control_pf: float | None,
    allow_extend: bool,
) -> tuple[
    Literal["KEEP_FLEET_OVERLAY", "ROLLBACK_FLEET_OVERLAY", "EXTEND_MEASUREMENT"],
    tuple[str, ...],
]:
    """Determine the final decision based on readiness evidence.

    Returns (decision, reasons).
    """
    reasons: list[str] = []

    # Target vs control profit comparison
    profit_gap = target_profit - control_profit

    # Profit factor comparison
    pf_available = target_pf is not None and control_pf is not None
    target_pf_below_control = False
    if pf_available and target_pf is not None and control_pf is not None:
        target_pf_below_control = target_pf < control_pf

    # Target clearly outperforms or matches control
    if profit_gap >= 0 and not target_pf_below_control:
        reasons.append(
            f"target_outperforms_or_matches: "
            f"profit={target_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        return "KEEP_FLEET_OVERLAY", tuple(reasons)

    # Target clearly underperforms
    if profit_gap < -0.01 and target_pf_below_control:
        reasons.append(
            f"target_underperforms: "
            f"profit={target_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        reasons.append(
            f"target_profit_factor_below_control: "
            f"target_pf={target_pf}, control_pf={control_pf}"
        )
        return "ROLLBACK_FLEET_OVERLAY", tuple(reasons)

    # Target has lower profit but acceptable profit factor
    if profit_gap < -0.01:
        reasons.append(
            f"target_profit_below_control: "
            f"profit={target_profit:+.4f} vs control={control_profit:+.4f}, "
            f"gap={profit_gap:+.4f}"
        )
        if allow_extend:
            reasons.append("allow_extend=True — extending for more evidence")
            return "EXTEND_MEASUREMENT", tuple(reasons)
        return "ROLLBACK_FLEET_OVERLAY", tuple(reasons)

    # Target profit matches but profit factor is worse
    if pf_available and target_pf_below_control and profit_gap >= 0:
        reasons.append(
            f"target_profit_factor_below_control: "
            f"target_pf={target_pf}, control_pf={control_pf}"
        )
        if allow_extend:
            reasons.append("allow_extend=True — extending for more evidence")
            return "EXTEND_MEASUREMENT", tuple(reasons)
        return "KEEP_FLEET_OVERLAY", tuple(reasons)

    # Ambiguous — extend
    reasons.append(
        f"ambiguous_evidence: "
        f"profit_gap={profit_gap:+.4f}, "
        f"pf_available={pf_available}"
    )
    if allow_extend:
        reasons.append("allow_extend=True — extending for more evidence")
        return "EXTEND_MEASUREMENT", tuple(reasons)
    return "KEEP_FLEET_OVERLAY", tuple(reasons)


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
    measurement_points: tuple[FleetEvidenceSnapshot, ...],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
) -> str:
    """Write a decision pack JSON file.

    Returns the path to the written file.
    """
    decision_pack_dir.mkdir(parents=True, exist_ok=True)
    pack: dict[str, object] = {
        "event": "post_fleet_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": decision,
        "status": status,
        "measurement_points": [mp.to_dict() for mp in measurement_points],
        "evidence_ref": evidence_ref,
        "created_at_utc": now_utc,
        "next_required_component": (
            "fleet_rollback_executor_or_next_iteration"
            if decision in ("ROLLBACK_FLEET_OVERLAY", "KEEP_FLEET_OVERLAY")
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
# Decision emission helpers
# ---------------------------------------------------------------------------


def _emit_keep_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[FleetEvidenceSnapshot, ...],
    snapshot: dict[str, object],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
) -> PostFleetMeasurementResult:
    """Emit KEEP_FLEET_OVERLAY."""
    pack_path = _write_decision_pack(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        decision="KEEP_FLEET_OVERLAY",
        status="FINAL_DECISION_EMITTED",
        measurement_points=points,
        evidence_ref=evidence_ref,
        decision_pack_dir=decision_pack_dir,
        now_utc=now_utc,
    )
    return PostFleetMeasurementResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="KEEP_FLEET_OVERLAY",
        measurement_points=points,
        blocked_reasons=(),
        decision_pack_path=pack_path,
        next_step=(
            f"KEEP_FLEET_OVERLAY emitted for {candidate_id} on {target_bot}. "
            f"Fleet overlay is performing at or above control baseline. "
            f"Prepare next candidate iteration."
        ),
    )


def _emit_rollback_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[FleetEvidenceSnapshot, ...],
    snapshot: dict[str, object],
    decision_pack_dir: Path,
    now_utc: str,
    reasons: tuple[str, ...],
) -> PostFleetMeasurementResult:
    """Emit ROLLBACK_FLEET_OVERLAY.

    Does NOT execute the rollback — only emits the decision.
    """
    pack_path = _write_decision_pack(
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        decision="ROLLBACK_FLEET_OVERLAY",
        status="FINAL_DECISION_EMITTED",
        measurement_points=points,
        evidence_ref=str(snapshot.get("source", "unknown")),
        decision_pack_dir=decision_pack_dir,
        now_utc=now_utc,
    )
    return PostFleetMeasurementResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="ROLLBACK_FLEET_OVERLAY",
        measurement_points=points,
        blocked_reasons=reasons,
        decision_pack_path=pack_path,
        next_step=(
            f"ROLLBACK_FLEET_OVERLAY emitted for {candidate_id} on {target_bot}. "
            f"Fleet overlay is underperforming or safety degraded. "
            f"Rollback is required but not executed by this watcher."
        ),
    )


def _emit_extend_decision(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    points: tuple[FleetEvidenceSnapshot, ...],
    snapshot: dict[str, object],
    evidence_ref: str,
    decision_pack_dir: Path,
    now_utc: str,
    reasons: tuple[str, ...],
) -> PostFleetMeasurementResult:
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
    return PostFleetMeasurementResult(
        status="FINAL_DECISION_EMITTED",
        change_id=change_id,
        candidate_id=candidate_id,
        target_bot=target_bot,
        final_decision="EXTEND_MEASUREMENT",
        measurement_points=points,
        blocked_reasons=reasons,
        decision_pack_path=pack_path,
        next_step=(
            f"EXTEND_MEASUREMENT emitted for {candidate_id} on {target_bot}. "
            f"Evidence is ambiguous — extend measurement window."
        ),
    )


# ---------------------------------------------------------------------------
# Main watcher function
# ---------------------------------------------------------------------------


def run_post_fleet_measurement_watcher(
    input_: PostFleetMeasurementInput,
    *,
    evidence_snapshot: dict[str, object] | None = None,
    evidence_reader: FleetEvidenceReader | None = None,
    decision_pack_dir: Path | None = None,
    now_utc: str | None = None,
) -> PostFleetMeasurementResult:
    """Run the post-fleet measurement watcher.

    Args:
        input_: All inputs for the watcher.
        evidence_snapshot: Direct evidence snapshot dict (for testing).
            If provided, takes precedence over evidence_reader.
        evidence_reader: A FleetEvidenceReader implementation. Used when
            evidence_snapshot is None.
        decision_pack_dir: Override for decision pack output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        PostFleetMeasurementResult with measurement status and decision.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_pack_dir = decision_pack_dir or Path(DEFAULT_DECISION_PACK_DIR)

    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Read measurement start record
    # ------------------------------------------------------------------

    start_record, start_reasons = _read_measurement_start_record(
        input_.measurement_start_record_path,
    )
    if start_record is None:
        return PostFleetMeasurementResult(
            status="MEASUREMENT_BLOCKED",
            change_id="",
            candidate_id="",
            target_bot=input_.target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=start_reasons,
            decision_pack_path="",
            next_step="Provide a valid measurement start record path and retry.",
        )

    change_id = start_record.measurement_started_at_utc[:24]
    candidate_id = f"fleet-{input_.target_bot}-{change_id}"

    # Validate target bot matches
    if start_record.target_bot != input_.target_bot:
        blocked.append(
            f"target_bot_mismatch: start record has {start_record.target_bot}, "
            f"input has {input_.target_bot}"
        )

    # ------------------------------------------------------------------
    # Step 2: Read evidence snapshot
    # ------------------------------------------------------------------

    snapshot: dict[str, object] | None = evidence_snapshot

    if snapshot is None and evidence_reader is not None:
        try:
            snapshot = evidence_reader.read_fleet_measurement_snapshot(
                target_bot=input_.target_bot,
                control_bot=input_.control_bot,
                measurement_started_at_utc=(
                    start_record.measurement_started_at_utc
                ),
            )
        except (FileNotFoundError, ValueError) as e:
            blocked.append(f"evidence_reader_error: {e}")

    if snapshot is None:
        blocked.append(
            "no_evidence_snapshot: no snapshot provided and no reader available"
        )

    if blocked:
        return PostFleetMeasurementResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=tuple(blocked),
            decision_pack_path="",
            next_step="Review blocked reasons and fix before retrying.",
        )

    assert snapshot is not None

    # ------------------------------------------------------------------
    # Step 3: Validate evidence snapshot
    # ------------------------------------------------------------------

    valid, validation_reasons = _validate_evidence_snapshot(snapshot)
    if not valid:
        return PostFleetMeasurementResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            final_decision="NONE",
            measurement_points=(),
            blocked_reasons=validation_reasons,
            decision_pack_path="",
            next_step="Fix evidence snapshot schema and retry.",
        )

    # ------------------------------------------------------------------
    # Step 4: Extract arm data
    # ------------------------------------------------------------------

    target_data = snapshot.get("target", {})
    control_data = snapshot.get("control", {})

    assert isinstance(target_data, dict)
    assert isinstance(control_data, dict)

    target_closed, target_open, target_profit, target_pf = (
        _extract_arm_data(target_data)
    )
    control_closed, control_open, control_profit, control_pf = (
        _extract_arm_data(control_data)
    )

    # Build measurement point
    label_raw = str(snapshot.get("label", "T1")).upper()
    label: Literal["T1", "T2", "T3"] = (
        "T1" if label_raw not in ("T1", "T2", "T3") else label_raw  # type: ignore[assignment]
    )

    point = FleetEvidenceSnapshot(
        label=label,
        timestamp_utc=str(snapshot.get("timestamp_utc", resolved_now)),
        target_closed_trades=target_closed,
        target_open_trades=target_open,
        target_profit_abs=target_profit,
        target_profit_factor=target_pf,
        control_closed_trades=control_closed,
        control_open_trades=control_open,
        control_profit_abs=control_profit,
        control_profit_factor=control_pf,
        evidence_source=str(snapshot.get("source", "unknown")),
    )

    # ------------------------------------------------------------------
    # Step 5: Check measurement readiness
    # ------------------------------------------------------------------

    ready, ready_reason = _check_measurement_readiness(
        target_closed, control_closed, input_.min_closed_trades,
    )
    if not ready:
        return PostFleetMeasurementResult(
            status="MEASUREMENT_NOT_READY",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            final_decision="NONE",
            measurement_points=(point,),
            blocked_reasons=(ready_reason,) if ready_reason else (),
            decision_pack_path="",
            next_step=(
                f"Not enough closed trades yet. "
                f"Target has {target_closed}, control has {control_closed}, "
                f"need at least {input_.min_closed_trades} each. "
                f"Re-check when more trades close."
            ),
        )

    # ------------------------------------------------------------------
    # Step 6: Check measurement age
    # ------------------------------------------------------------------

    fresh, age_reason = _check_measurement_age(
        start_record.measurement_started_at_utc,
        input_.max_measurement_age_hours,
        resolved_now,
    )
    if not fresh:
        return PostFleetMeasurementResult(
            status="MEASUREMENT_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            final_decision="NONE",
            measurement_points=(point,),
            blocked_reasons=(age_reason,) if age_reason else (),
            decision_pack_path="",
            next_step="Measurement is stale. Re-run with a fresh measurement.",
        )

    # ------------------------------------------------------------------
    # Step 7: Determine final decision
    # ------------------------------------------------------------------

    decision, decision_reasons = _determine_final_decision(
        target_closed=target_closed,
        control_closed=control_closed,
        target_profit=target_profit,
        control_profit=control_profit,
        target_pf=target_pf,
        control_pf=control_pf,
        allow_extend=input_.allow_extend,
    )

    # ------------------------------------------------------------------
    # Step 8: Emit decision
    # ------------------------------------------------------------------

    evidence_ref = str(snapshot.get("source", "unknown"))

    if decision == "KEEP_FLEET_OVERLAY":
        return _emit_keep_decision(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            points=(point,),
            snapshot=snapshot,
            evidence_ref=evidence_ref,
            decision_pack_dir=resolved_pack_dir,
            now_utc=resolved_now,
        )
    elif decision == "ROLLBACK_FLEET_OVERLAY":
        return _emit_rollback_decision(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            points=(point,),
            snapshot=snapshot,
            decision_pack_dir=resolved_pack_dir,
            now_utc=resolved_now,
            reasons=decision_reasons,
        )
    else:
        return _emit_extend_decision(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            points=(point,),
            snapshot=snapshot,
            evidence_ref=evidence_ref,
            decision_pack_dir=resolved_pack_dir,
            now_utc=resolved_now,
            reasons=decision_reasons,
        )
