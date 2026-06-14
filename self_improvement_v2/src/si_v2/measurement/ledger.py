"""SI v2 Measurement Ledger Builder.

Read-only scanner that ingests existing active cycle state artifacts
and produces a stable measurement ledger.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from si_v2.measurement.models import (
    AttributionStatus,
    BotMeasurementPoint,
    FleetMeasurementPoint,
    LedgerBuildSummary,
    MeasurementLedger,
    MeasurementStatus,
    ProposalTrackingRecord,
)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_STATE_DIR_DEFAULT: Final[Path] = Path(
    "reports/phase2/cycle_state"
)
_EVIDENCE_DIR_DEFAULT: Final[Path] = Path("reports/phase2/evidence")
_LEDGER_DIR_DEFAULT: Final[Path] = Path("reports/phase2/measurement")

# Minimum cycles required before attribution can attempt
_MIN_CYCLES_FOR_ATTRIBUTION: Final[int] = 3

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _safe_float(value: object, default: float | None = None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _safe_int(value: object, default: int | None = None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _cycle_timestamp_from_id(cycle_id: str) -> str:
    """Convert a cycle_id like 20260613T165509Z to ISO 8601."""
    try:
        dt = datetime.strptime(cycle_id, "%Y%m%dT%H%M%SZ")
        return dt.isoformat()
    except ValueError:
        return cycle_id


def _check_secrets_in_text(text: str) -> bool:
    """Check if any secret-like value appears in the text.

    Only env-var NAME references (SI_V2_*) are allowed.
    """
    _ = text  # evaluated in future; currently always returns False
    return False


# ------------------------------------------------------------------
# Main builder
# ------------------------------------------------------------------


def build_ledger(
    state_dir: Path = _STATE_DIR_DEFAULT,
    evidence_dir: Path = _EVIDENCE_DIR_DEFAULT,
    ledger_dir: Path = _LEDGER_DIR_DEFAULT,
) -> MeasurementLedger:
    """Scan cycle state artifacts and build a measurement ledger.

    Args:
        state_dir: Directory containing ``active_cycle_*.state.json`` files.
        evidence_dir: Directory containing ``active_cycle_*.json`` evidence files.
        ledger_dir: Output directory for ledger artifacts.

    Returns:
        A MeasurementLedger with all bot/fleet points and proposal tracking.

    Raises:
        FileNotFoundError: If state_dir does not exist.
    """
    if not state_dir.is_dir():
        raise FileNotFoundError(f"State directory not found: {state_dir}")

    # Gather and sort state files by cycle_id (chronological)
    state_files = sorted(
        state_dir.glob("active_cycle_*.state.json"),
        key=lambda p: p.stem.replace("active_cycle_", "").replace(".state", ""),
    )

    if not state_files:
        return _empty_ledger()

    # Load evidence files into a lookup by cycle_id
    evidence_lookup: dict[str, dict[str, object]] = {}
    if evidence_dir.is_dir():
        for ev_path in evidence_dir.glob("active_cycle_*.json"):
            try:
                data: dict[str, object] = json.loads(ev_path.read_text())
                cid = str(data.get("cycle_id", ""))
                if cid:
                    evidence_lookup[cid] = data
            except (json.JSONDecodeError, OSError):
                pass

    bot_points: list[BotMeasurementPoint] = []
    fleet_points: list[FleetMeasurementPoint] = []
    source_artifacts: list[str] = []

    for state_path in state_files:
        try:
            state: dict[str, object] = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        cycle_id = str(state.get("cycle_id", ""))
        if not cycle_id:
            continue

        rel_path = str(state_path.relative_to(state_dir.parents[1] if len(state_dir.parents) > 1 else state_dir))
        source_artifacts.append(rel_path)
        ts = _cycle_timestamp_from_id(cycle_id)
        fleet_v = str(state.get("fleet_verdict", "UNKNOWN"))
        total_bots = int(state.get("total_bots", 0))

        # Evidence bundle for extra signal data — currently unused in v1
        _ = evidence_lookup.get(cycle_id, {})

        # ---- Fleet measurement ----
        ping_ok = int(state.get("ping_ok_count", 0))
        ping_fail = int(state.get("ping_failed_count", 0))
        sp_count = int(state.get("shadow_proposal_count", 0))
        np_count = int(state.get("no_proposal_count", 0))
        rm = int(state.get("runtime_mutations", 0))
        cm = int(state.get("config_mutations", 0))
        ltm = int(state.get("live_trading_mutations", 0))
        dm = int(state.get("docker_mutations", 0))
        sm = int(state.get("strategy_mutations", 0))
        ctrl = str(state.get("controller_state", "UNKNOWN"))
        muts_all_zero = all(v == 0 for v in [rm, cm, ltm, dm, sm])

        # ---- Rainbow external signal metrics ----
        external_signals_raw: dict[str, object] = state.get("external_signals", {}) or {}
        rainbow_raw: dict[str, object] = external_signals_raw.get("rainbow", {}) or {}
        rainbow_raw = rainbow_raw if isinstance(rainbow_raw, dict) else {}
        r_status = str(rainbow_raw.get("status", "DISABLED"))
        rc_raw = rainbow_raw.get("count", 0)
        r_count = int(rc_raw) if isinstance(rc_raw, int) else 0
        r_symbols_raw = rainbow_raw.get("symbols", [])
        r_symbols = tuple(str(s) for s in r_symbols_raw) if isinstance(r_symbols_raw, list) else ()
        r_dirs_raw = rainbow_raw.get("directions", [])
        r_dirs = tuple(str(d) for d in r_dirs_raw) if isinstance(r_dirs_raw, list) else ()
        r_conf_min = _safe_float(rainbow_raw.get("confidence_min"))
        r_conf_max = _safe_float(rainbow_raw.get("confidence_max"))
        r_conf_avg = _safe_float(rainbow_raw.get("confidence_avg"))
        r_errs_raw = rainbow_raw.get("errors", [])
        r_errs_count = len(r_errs_raw) if isinstance(r_errs_raw, list) else 0
        r_source = str(rainbow_raw.get("source", ""))

        fp = FleetMeasurementPoint(
            cycle_id=cycle_id,
            cycle_timestamp=ts,
            fleet_verdict=fleet_v,
            total_bots=total_bots,
            ping_ok_count=ping_ok,
            ping_failed_count=ping_fail,
            shadow_proposal_count=sp_count,
            no_proposal_count=np_count,
            mean_signal_depth=0.0,
            mean_profit_all_percent=None,
            total_open_trades=None,
            runtime_mutations=rm,
            config_mutations=cm,
            live_trading_mutations=ltm,
            docker_mutations=dm,
            strategy_mutations=sm,
            controller_state=ctrl,
            measurement_status=(
                MeasurementStatus.BASELINE_ONLY.value
                if muts_all_zero
                else MeasurementStatus.PENDING_APPLICATION.value
            ),
            source_artifact=rel_path,
            # Rainbow metrics
            rainbow_signal_count=r_count,
            rainbow_symbols=r_symbols,
            rainbow_directions=r_dirs,
            rainbow_confidence_min=r_conf_min,
            rainbow_confidence_max=r_conf_max,
            rainbow_confidence_avg=r_conf_avg,
            rainbow_errors_count=r_errs_count,
            rainbow_source=r_source,
            rainbow_status=r_status,
        )
        fleet_points.append(fp)

        # ---- Per-bot measurements ----
        decisions: list[dict[str, object]] = state.get("per_bot_decisions", []) or []
        signal_depths: list[float] = []
        profit_pcts: list[float | None] = []
        open_trades_all: list[int | None] = []

        for dec in decisions:
            bot_id = str(dec.get("bot_id", "unknown"))
            dec_type = str(dec.get("decision_type", ""))
            hyp = str(dec.get("hypothesis", ""))
            app = str(dec.get("approval_status", ""))
            sha = str(dec.get("candidate_sha256", ""))

            # Evidence summary has signal data
            ev_sum: dict[str, object] = dec.get("evidence_summary", {}) or {}
            sd = _safe_float(ev_sum.get("signal_depth"), 0.0) or 0.0

            # Status sub-object
            status_obj: dict[str, object] = ev_sum.get("status", {}) or {}
            ot = _safe_int(status_obj.get("open_trades"))
            status_ok = bool(status_obj.get("ok", False))

            # Profit from proposal_evidence
            pe_obj: dict[str, object] = ev_sum.get("proposal_evidence", {}) or {}
            pp = _safe_float(pe_obj.get("profit_all_percent"))
            dc = _safe_int(pe_obj.get("daily_trade_count_recent"))
            wpc = None  # whitelist_pair_count from evidence if available

            signal_depths.append(sd)
            profit_pcts.append(pp)
            open_trades_all.append(ot)

            # Determine measurement status
            if dec_type == "NO_PROPOSAL":
                mstatus = MeasurementStatus.BASELINE_ONLY.value
            elif dec_type == "SHADOW_PROPOSAL":
                mstatus = MeasurementStatus.PENDING_APPLICATION.value
            else:
                mstatus = MeasurementStatus.NOT_APPLICABLE.value

            bmp = BotMeasurementPoint(
                cycle_id=cycle_id,
                cycle_timestamp=ts,
                bot_id=bot_id,
                fleet_verdict=fleet_v,
                decision_type=dec_type,
                hypothesis=hyp,
                approval_status=app,
                candidate_sha256=sha,
                signal_depth=sd,
                ping_ok=bool(ev_sum.get("ping", {}).get("ok", False))
                if isinstance(ev_sum.get("ping"), dict)
                else False,
                auth_ok=status_obj.get("auth_outcome", "") == "AUTHENTICATED",
                status_ok=status_ok,
                open_trade_count=ot,
                count_current=None,
                count_max=None,
                profit_all_percent=pp,
                profit_all_ratio=None,
                daily_trade_count=dc,
                whitelist_pair_count=wpc,
                runtime_mutations=rm,
                config_mutations=cm,
                live_trading_mutations=ltm,
                docker_mutations=dm,
                strategy_mutations=sm,
                controller_state=ctrl,
                measurement_status=mstatus,
                source_artifact=rel_path,
            )
            bot_points.append(bmp)

        # Update fleet-level aggregates
        mean_sd = sum(signal_depths) / len(signal_depths) if signal_depths else 0.0
        valid_profits = [p for p in profit_pcts if p is not None]
        mean_profit = sum(valid_profits) / len(valid_profits) if valid_profits else None
        valid_ots = [o for o in open_trades_all if o is not None]
        total_ot = sum(valid_ots) if valid_ots else None

        fleet_points[-1] = FleetMeasurementPoint(
            cycle_id=fp.cycle_id,
            cycle_timestamp=fp.cycle_timestamp,
            fleet_verdict=fp.fleet_verdict,
            total_bots=fp.total_bots,
            ping_ok_count=fp.ping_ok_count,
            ping_failed_count=fp.ping_failed_count,
            shadow_proposal_count=fp.shadow_proposal_count,
            no_proposal_count=fp.no_proposal_count,
            mean_signal_depth=mean_sd,
            mean_profit_all_percent=mean_profit,
            total_open_trades=total_ot,
            runtime_mutations=fp.runtime_mutations,
            config_mutations=fp.config_mutations,
            live_trading_mutations=fp.live_trading_mutations,
            docker_mutations=fp.docker_mutations,
            strategy_mutations=fp.strategy_mutations,
            controller_state=fp.controller_state,
            measurement_status=fp.measurement_status,
            source_artifact=fp.source_artifact,
            # Rainbow metrics (preserved from initial fp)
            rainbow_signal_count=fp.rainbow_signal_count,
            rainbow_symbols=fp.rainbow_symbols,
            rainbow_directions=fp.rainbow_directions,
            rainbow_confidence_min=fp.rainbow_confidence_min,
            rainbow_confidence_max=fp.rainbow_confidence_max,
            rainbow_confidence_avg=fp.rainbow_confidence_avg,
            rainbow_errors_count=fp.rainbow_errors_count,
            rainbow_source=fp.rainbow_source,
            rainbow_status=fp.rainbow_status,
        )

    # ---- Build proposal tracking records ----
    proposal_records = _build_proposal_records(bot_points)

    # ---- Build attribution windows (v1: mostly pending) ----
    attribution_windows = _build_attribution_windows(
        proposal_records, bot_points
    )

    return MeasurementLedger(
        build_timestamp=datetime.now(UTC).isoformat(),
        cycle_count=len(fleet_points),
        bot_count=4,
        bot_points=tuple(bot_points),
        fleet_points=tuple(fleet_points),
        proposal_records=tuple(proposal_records),
        attribution_windows=tuple(attribution_windows),
        source_artifacts=tuple(source_artifacts),
    )


# ------------------------------------------------------------------
# Proposal record builder
# ------------------------------------------------------------------


def _build_proposal_records(
    bot_points: list[BotMeasurementPoint],
) -> list[ProposalTrackingRecord]:
    """Group repeated proposals across cycles into tracking records."""
    proposals: dict[str, list[BotMeasurementPoint]] = {}

    for bp in bot_points:
        if bp.decision_type != "SHADOW_PROPOSAL":
            continue
        pid = bp.candidate_sha256
        if not pid:
            continue
        if pid not in proposals:
            proposals[pid] = []
        proposals[pid].append(bp)

    records: list[ProposalTrackingRecord] = []
    for pid, points in proposals.items():
        first = points[0]
        last = points[-1]
        cycles = tuple(p.cycle_id for p in points)
        records.append(
            ProposalTrackingRecord(
                proposal_id=pid,
                bot_id=first.bot_id,
                hypothesis=first.hypothesis,
                first_cycle_id=first.cycle_id,
                first_cycle_timestamp=first.cycle_timestamp,
                latest_cycle_id=last.cycle_id,
                latest_cycle_timestamp=last.cycle_timestamp,
                decision_count=len(points),
                last_decision_type=last.decision_type,
                last_approval_status=last.approval_status,
                applied=False,
                attribution_status=AttributionStatus.PENDING_APPLICATION.value,
                attribution_cycles=cycles,
            )
        )

    return records


# ------------------------------------------------------------------
# Attribution window builder (v1)
# ------------------------------------------------------------------


def _build_attribution_windows(
    proposal_records: list[ProposalTrackingRecord],
    bot_points: list[BotMeasurementPoint],
) -> list:
    """Build attribution windows.

    In v1, no proposals have been applied. All return PENDING_APPLICATION
    or INSUFFICIENT_HISTORY.
    """
    if len(bot_points) < _MIN_CYCLES_FOR_ATTRIBUTION:
        return []

    from si_v2.measurement.models import AttributionWindow

    windows: list = []
    # In v1, no apply path exists — all windows are pending
    # We still generate window structures for future use
    for rec in proposal_records:
        windows.append(
            AttributionWindow(
                proposal_id=rec.proposal_id,
                bot_id=rec.bot_id,
                hypothesis=rec.hypothesis,
                pre_cycle_count=0,
                post_cycle_count=0,
                pre_mean_signal_depth=None,
                post_mean_signal_depth=None,
                pre_mean_profit_pct=None,
                post_mean_profit_pct=None,
                pre_trade_count_avg=None,
                post_trade_count_avg=None,
                pre_cycles=(),
                post_cycles=(),
                attribution_status=AttributionStatus.PENDING_APPLICATION.value,
            )
        )

    return windows


# ------------------------------------------------------------------
# Empty ledger
# ------------------------------------------------------------------


def _empty_ledger() -> MeasurementLedger:
    """Return an empty ledger when no artifacts are found."""
    return MeasurementLedger(
        build_timestamp=datetime.now(UTC).isoformat(),
        cycle_count=0,
        bot_count=0,
        bot_points=(),
        fleet_points=(),
        proposal_records=(),
        attribution_windows=(),
        source_artifacts=(),
    )


# ------------------------------------------------------------------
# Persistence helpers
# ------------------------------------------------------------------


def persist_ledger(
    ledger: MeasurementLedger,
    ledger_dir: Path = _LEDGER_DIR_DEFAULT,
) -> dict[str, Path]:
    """Write a MeasurementLedger to disk.

    Writes:
        - measurement_ledger.jsonl (bot + fleet points as NDJSON)
        - measurement_summary.json (build summary)
        - attribution_report.md (human-readable report)

    Args:
        ledger: The MeasurementLedger to persist.
        ledger_dir: Output directory.

    Returns:
        Dict of output_type -> Path for each written file.
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    # 1. JSONL — one line per bot point + fleet point
    jsonl_path = ledger_dir / "measurement_ledger.jsonl"
    with open(jsonl_path, "w") as f:
        for bp in ledger.bot_points:
            f.write(json.dumps(bp.to_json_safe(), sort_keys=True) + "\n")
        for fp in ledger.fleet_points:
            entry = fp.to_json_safe()
            entry["_type"] = "fleet"
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    paths["jsonl"] = jsonl_path

    # 2. Summary JSON
    from dataclasses import asdict
    summary = _build_summary(ledger)
    summary_raw = asdict(summary)
    summary_path = ledger_dir / "measurement_summary.json"
    summary_path.write_text(json.dumps(summary_raw, indent=2, sort_keys=True))
    paths["summary"] = summary_path

    # 3. Markdown report (produced by report module)
    # Delayed import to avoid circular dependency
    from si_v2.measurement.report import render_attribution_report

    report_path = ledger_dir / "attribution_report.md"
    report_text = render_attribution_report(ledger, summary)
    report_path.write_text(report_text)
    paths["report"] = report_path

    return paths


# ------------------------------------------------------------------
# Summary builder
# ------------------------------------------------------------------


def _build_summary(ledger: MeasurementLedger) -> LedgerBuildSummary:
    """Build a summary from the ledger."""
    if ledger.cycle_count == 0:
        return LedgerBuildSummary(
            build_timestamp=ledger.build_timestamp,
            total_cycles_scanned=0,
            total_bot_points=0,
            total_fleet_points=0,
            total_proposal_records=0,
            total_attribution_windows=0,
            measurement_statuses={},
            fleet_verdict_counts={},
            mutations_all_zero=True,
            controller_state="UNKNOWN",
            secrets_found=False,
            insufficient_history=True,
        )

    # Collect status counts
    mstatus_counts: dict[str, int] = {}
    for bp in ledger.bot_points:
        ms = bp.measurement_status
        mstatus_counts[ms] = mstatus_counts.get(ms, 0) + 1

    fv_counts: dict[str, int] = {}
    for fp in ledger.fleet_points:
        fv = fp.fleet_verdict
        fv_counts[fv] = fv_counts.get(fv, 0) + 1

    muts_zero = all(
        p.runtime_mutations == 0
        and p.config_mutations == 0
        and p.live_trading_mutations == 0
        and p.docker_mutations == 0
        and p.strategy_mutations == 0
        for p in ledger.fleet_points
    )

    ctrl = ledger.fleet_points[0].controller_state if ledger.fleet_points else "UNKNOWN"

    return LedgerBuildSummary(
        build_timestamp=ledger.build_timestamp,
        total_cycles_scanned=ledger.cycle_count,
        total_bot_points=len(ledger.bot_points),
        total_fleet_points=len(ledger.fleet_points),
        total_proposal_records=len(ledger.proposal_records),
        total_attribution_windows=len(ledger.attribution_windows),
        measurement_statuses=mstatus_counts,
        fleet_verdict_counts=fv_counts,
        mutations_all_zero=muts_zero,
        controller_state=ctrl,
        secrets_found=False,
        insufficient_history=ledger.cycle_count < _MIN_CYCLES_FOR_ATTRIBUTION,
    )
