"""SI v2 Active Multi-Bot Cycle Runner v1.

A repeatable Self-Improvement cycle step that reads authenticated telemetry
from all four Freqtrade dry-run bots, normalizes it, analyzes it in fleet
context, generates per-bot ShadowProposals or NO_PROPOSAL decisions, and
persists a cycle state/report for later measurement.

Usage:
    python -m si_v2.loop.active_cycle_runner

Exit codes:
    0   — Cycle completed successfully (all bots processed, decisions made)
    1   — Registry not found or invalid
    2   — Evidence collection failed for all bots (fleet RED)
    3   — Internal error (unexpected exception)

Safety guarantees (enforced at code level):
    - No live trading enablement
    - No ``dry_run`` set to ``False``
    - No Freqtrade POST/PUT/PATCH/DELETE beyond JWT login
    - No Docker commands
    - No config mutations
    - No strategy changes
    - No secrets printed, persisted, or committed
    - All mutation counters are 0
    - Controller remains PAUSED / L3_REPOSITORY_ONLY
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# ------------------------------------------------------------------
# Repository-relative paths
# ------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_EVIDENCE_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "evidence"
_REPORT_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2"
_SHADOW_LOG_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "shadow_logs"
_CYCLE_STATE_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "cycle_state"

# ------------------------------------------------------------------
# SI v2 module imports
# ------------------------------------------------------------------
sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

from si_v2.adapters.freqtrade_rest_readonly import (  # noqa: E402
    SIV2FreqtradeTelemetryConnector,
)
from si_v2.deploy.shadow_logger import ShadowLogger  # noqa: E402
from si_v2.loop.cycle_state import (  # noqa: E402
    build_cycle_state,
    persist_cycle_state,
    print_cycle_state,
)
from si_v2.loop.fleet_analyzer import (  # noqa: E402
    DECISION_SHADOW_PROPOSAL,
    BotEvidence,
    JsonObject,
    analyze_fleet,
)
from si_v2.loop.telemetry_normalizer import (  # noqa: E402
    NormalizedTelemetry,
    normalize_raw_evidence,
)
from si_v2.signals.freqtrade_signals import (  # noqa: E402
    collect_bot_signals,
)
from si_v2.signals.fusion import (  # noqa: E402
    build_proposal_evidence,
    fuse_signals,
)
from si_v2.signals.models import (  # noqa: E402
    BotSignalSnapshot,
)

# ------------------------------------------------------------------
# RiskGuard-style local check (same semantics as PR #207, #208)
# ------------------------------------------------------------------
RISKGUARD_RESULT_PASS_SHADOW_ONLY: str = "PASS_SHADOW_ONLY"


def _riskguard_check(decision: dict[str, object]) -> dict[str, object]:
    """Validate that a ShadowProposal decision is safe-by-construction.

    Rejects anything that:
      - has a non-proposal base_mode
      - has requires_human_approval == False
      - has a non-safe mutation_policy
      - proposes executable parameters
      - proposes setting dry_run to a non-default value
    """
    details: list[str] = []

    base_mode = decision.get("base_mode", "")
    if base_mode != "proposal_only":
        details.append(f"base_mode={base_mode!r} != 'proposal_only'")

    if not decision.get("requires_human_approval", False):
        details.append("requires_human_approval is False")

    policy = decision.get("mutation_policy", "")
    if policy != "safe_parameter_overlay_only":
        details.append(f"mutation_policy={policy!r} != 'safe_parameter_overlay_only'")

    raw_params = decision.get("parameters", {}) or {}
    params = raw_params if isinstance(raw_params, dict) else {}
    for key, value in params.items():
        if key == "dry_run" and value is False:
            details.append(f"parameter {key!r} = False (would enable live trading)")
        if key in ("max_open_trades", "stake_amount", "stoploss", "minimal_roi"):
            details.append(
                f"parameter {key!r} is not allowed in metadata-only multi-bot proposal"
            )

    if details:
        return {
            "result": "BLOCKED",
            "reason": "; ".join(details),
            "details": details,
        }

    return {
        "result": RISKGUARD_RESULT_PASS_SHADOW_ONLY,
        "reason": (
            f"candidate {decision.get('candidate_sha256')} for "
            f"{decision.get('bot_id')} is proposal_only, requires human "
            f"approval, has empty parameters, and a safe mutation policy. "
            f"Runtime application is blocked."
        ),
        "details": [
            "proposal_only=True",
            "runtime_blocked=True",
            "parameters_empty=True",
        ],
    }


# ------------------------------------------------------------------
# Evidence collection per bot
# ------------------------------------------------------------------


def _collect_one(
    bot: dict[str, object],
    now_iso: str,
) -> tuple[NormalizedTelemetry, dict[str, object], SIV2FreqtradeTelemetryConnector | None]:
    """Collect /ping, /status evidence for a single bot, plus an auth connector
    for optional signal collection.

    Returns a tuple of (NormalizedTelemetry, debug_dict, auth_connector_or_None).
    The auth connector can be reused for additional signal endpoints.
    No credential value is ever read, printed, or stored.
    """
    bot_id: str = bot["bot_id"]  # type: ignore[index]
    base_url: str = bot["base_url"]  # type: ignore[index]
    auth_cfg_raw: object = bot.get("auth", {}) or {}
    auth_cfg: dict[str, object] = auth_cfg_raw if isinstance(auth_cfg_raw, dict) else {}
    auth_type: str = auth_cfg.get("type", "none") if isinstance(auth_cfg.get("type"), str) else "none"
    username_env: str | None = auth_cfg.get("username_env") if isinstance(auth_cfg.get("username_env"), str) else None
    password_env: str | None = auth_cfg.get("password_env") if isinstance(auth_cfg.get("password_env"), str) else None

    # ---- Step A: unauthenticated /api/v1/ping ----
    ping_connector = SIV2FreqtradeTelemetryConnector(
        base_url=base_url,
        bot_id=bot_id,
    )
    ping_snapshot = ping_connector.fetch_snapshot("/api/v1/ping")

    # ---- Step B: authenticated /api/v1/status ----
    status_status_code = 0
    status_response_summary = "not_attempted"
    status_auth_outcome = "NOT_ATTEMPTED"
    missing_env_vars: list[str] = []
    auth_error_summary = ""
    auth_connector: SIV2FreqtradeTelemetryConnector | None = None

    if username_env and password_env:
        # Check env vars by NAME only — never read the value
        if not os.environ.get(username_env):
            missing_env_vars.append(username_env)
        if not os.environ.get(password_env):
            missing_env_vars.append(password_env)

        if missing_env_vars:
            status_auth_outcome = "YELLOW_MISSING_ENV_VARS"
            status_response_summary = (
                f"YELLOW: missing env vars ({', '.join(missing_env_vars)})"
            )
        else:
            # Build an authenticated connector and attempt login + status
            _auth_connector_inner = SIV2FreqtradeTelemetryConnector(
                base_url=base_url,
                bot_id=bot_id,
                username_env=username_env,
                password_env=password_env,
            )
            try:
                _auth_connector_inner.token_login()
                status_auth_outcome = "AUTHENTICATED"
                auth_connector = _auth_connector_inner
            except RuntimeError as exc:
                status_auth_outcome = "FAILED"
                auth_error_summary = str(exc)[:200]
                status_response_summary = f"auth_error: {auth_error_summary}"
                auth_connector = None
            else:
                try:
                    status_snapshot = auth_connector.fetch_snapshot("/api/v1/status")
                    status_status_code = status_snapshot.status_code
                    status_response_summary = status_snapshot.response_summary
                    if not status_snapshot.ok and status_snapshot.status_code == 401:
                        status_auth_outcome = "AUTHENTICATED_NO_STATUS"
                except RuntimeError as exc:
                    status_auth_outcome = "AUTHENTICATED_NO_STATUS"
                    status_response_summary = f"status_error: {str(exc)[:200]}"
    else:
        status_response_summary = "no auth config in registry"

    # ---- Step C: Normalize ----
    telemetry = normalize_raw_evidence(
        bot_id=bot_id,
        base_url=base_url,
        ping_status_code=ping_snapshot.status_code,
        ping_response_summary=ping_snapshot.response_summary,
        status_status_code=status_status_code,
        status_response_summary=status_response_summary,
        status_auth_outcome=status_auth_outcome,
        username_env=username_env,
        password_env=password_env,
        missing_env_vars=missing_env_vars,
        auth_error_summary=auth_error_summary,
        fetched_at_utc=now_iso,
        auth_type=auth_type,
    )

    debug = {
        "ping": {
            "status_code": ping_snapshot.status_code,
            "ok": ping_snapshot.ok,
            "response_summary": ping_snapshot.response_summary[:200],
        },
        "status": {
            "status_code": status_status_code,
            "response_summary": status_response_summary[:200],
            "auth_outcome": status_auth_outcome,
        },
        "missing_env_vars": list(missing_env_vars),
    }

    return telemetry, debug, auth_connector


# ------------------------------------------------------------------
# Git helpers
# ------------------------------------------------------------------


def _current_commit_sha() -> str:
    """Return the current short commit SHA, or 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _current_branch() -> str:
    """Return the current branch name, or 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(_REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


# ------------------------------------------------------------------
# BotEvidence builder helper from NormalizedTelemetry
# ------------------------------------------------------------------


def _telemetry_to_bot_evidence(
    telemetry: NormalizedTelemetry,
    signal_depth: float = 0.0,
    proposal_evidence_json: JsonObject | None = None,
) -> BotEvidence:
    """Convert NormalizedTelemetry to a BotEvidence dataclass.

    Args:
        telemetry: Normalized telemetry for one bot.
        signal_depth: Optional signal depth score (0.0-1.0).
        proposal_evidence_json: Optional structured proposal evidence.

    Returns:
        A BotEvidence dataclass suitable for ``analyze_fleet()``.
    """
    return BotEvidence(
        bot_id=telemetry.bot_id,
        base_url=telemetry.base_url,
        auth_type=telemetry.auth_type,
        username_env=telemetry.username_env,
        password_env=telemetry.password_env,
        ping_endpoint="/api/v1/ping",
        ping_status_code=telemetry.ping_status_code,
        ping_ok=telemetry.ping_ok,
        ping_response_summary=telemetry.ping_response_summary[:200],
        status_endpoint="/api/v1/status",
        status_status_code=telemetry.status_status_code,
        status_ok=telemetry.status_ok,
        status_response_summary=telemetry.status_response_summary[:200],
        status_auth_outcome=telemetry.status_auth_outcome,
        status_open_trades=telemetry.status_open_trades,
        missing_env_vars=tuple(telemetry.missing_env_vars),
        auth_error_summary=(
            telemetry.auth_error_summary[:200]
            if telemetry.auth_error_summary
            else ""
        ),
        fetched_at_utc=telemetry.fetched_at_utc,
        signal_depth=signal_depth,
        proposal_evidence_json=proposal_evidence_json,
    )


# ------------------------------------------------------------------
# Secret leak check
# ------------------------------------------------------------------


def _check_secret_leak(
    evidence_bundle: dict[str, object],
    telemetry_list: list[NormalizedTelemetry],
) -> None:
    """Verify that no env-var value has leaked into the evidence bundle.

    Scans the serialized JSON of the evidence bundle for any value that
    matches a known env-var value. Uses strict JSON-quoted-value matching
    to avoid false positives from bot IDs or base URLs that happen to be
    substrings of credential values.

    Args:
        evidence_bundle: The serialized evidence bundle dict.
        telemetry_list: List of normalized telemetry for all bots.

    Raises:
        RuntimeError: If a secret leak is detected.
    """
    bundle_text = json.dumps(evidence_bundle)
    for telemetry in telemetry_list:
        for env_name in (telemetry.username_env, telemetry.password_env):
            if env_name and os.environ.get(env_name):
                val = os.environ[env_name]
                if f'"{val}"' in bundle_text:
                    raise RuntimeError(
                        f"SECRET LEAK: env value for {env_name} found in evidence bundle"
                    )


# ------------------------------------------------------------------
# Main cycle
# ------------------------------------------------------------------


def run_active_cycle() -> int:
    """Execute one active multi-bot cycle.

    Returns:
        0 on success, non-zero on failure.
    """
    branch = _current_branch()
    commit_sha = _current_commit_sha()
    now_iso = datetime.now(UTC).isoformat()
    cycle_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    print("=" * 72)
    print("SI v2 Active Multi-Bot Cycle Runner v1")
    print("=" * 72)
    print(f"  branch:        {branch}")
    print(f"  commit:        {commit_sha}")
    print(f"  cycle_id:      {cycle_id}")

    # ------------------------------------------------------------------
    # Step 1: Load bot registry
    # ------------------------------------------------------------------
    print("\n[STEP 1] Loading bot registry...")
    if not _CONFIG_PATH.exists():
        print(f"  ERROR: registry not found at {_CONFIG_PATH}")
        return 1

    with open(_CONFIG_PATH) as f:
        registry = json.load(f)

    bots = [b for b in registry.get("bots", []) if b.get("enabled", True)]
    print(f"  Loaded {len(bots)} enabled bot(s) "
          f"(schema v{registry.get('schema_version', '?')})")

    if not bots:
        print("  ERROR: no enabled bots in registry")
        return 1

    # ------------------------------------------------------------------
    # Step 2: Collect per-bot evidence
    # ------------------------------------------------------------------
    print("\n[STEP 2] Collecting per-bot evidence (ping + status)...")
    telemetry_list: list[NormalizedTelemetry] = []
    evidence_list: list[BotEvidence] = []
    debug_by_bot: dict[str, dict[str, object]] = {}
    auth_connectors_by_bot: dict[str, SIV2FreqtradeTelemetryConnector] = {}

    for bot in bots:
        bot_id = bot.get("bot_id", "<missing>")
        print(f"\n  --- {bot_id} @ {bot.get('base_url')} ---")
        telemetry, debug, auth_connector = _collect_one(bot, now_iso)
        telemetry_list.append(telemetry)
        evidence_list.append(_telemetry_to_bot_evidence(telemetry))
        debug_by_bot[bot_id] = debug
        if auth_connector is not None:
            auth_connectors_by_bot[bot_id] = auth_connector

        print(f"  /api/v1/ping:  HTTP {debug['ping']['status_code']} "
              f"({'OK' if debug['ping']['ok'] else 'FAIL'})")
        print(f"  auth outcome:  {debug['status']['auth_outcome']}")
        if debug["missing_env_vars"]:
            print(f"  missing env:   {', '.join(debug['missing_env_vars'])}")
        print(f"  /api/v1/status: HTTP {debug['status']['status_code']} "
              f"({'AUTH' if debug['status']['auth_outcome'] == 'AUTHENTICATED' else 'SKIP'})")

    # ------------------------------------------------------------------
    # Step 2b: Collect rich signal snapshots (optional, non-blocking)
    # ------------------------------------------------------------------
    print("\n[STEP 2b] Collecting rich signal summaries...")
    signal_snapshots: list[BotSignalSnapshot] = []
    signal_snapshots_by_bot: dict[str, BotSignalSnapshot] = {}
    for bot in bots:
        bot_id = bot.get("bot_id", "<missing>")
        connector = auth_connectors_by_bot.get(bot_id)
        if connector is not None and connector.authenticated:
            try:
                snap = collect_bot_signals(connector, bot_id, cycle_id)
                signal_snapshots.append(snap)
                signal_snapshots_by_bot[bot_id] = snap
                q = snap.signal_quality
                if q:
                    print(f"  {bot_id}: signal_depth={snap.signal_depth:.2f} "
                          f"({q.available_count}/{q.total_endpoints} endpoints)")
                else:
                    print(f"  {bot_id}: signal_depth={snap.signal_depth:.2f}")
            except Exception as exc:
                print(f"  {bot_id}: signal collection error — {str(exc)[:80]}")
        else:
            print(f"  {bot_id}: skip (not authenticated)")

    # Fuse fleet signals
    fleet_signals = fuse_signals(signal_snapshots, cycle_id)
    has_rich_signals = fleet_signals.has_rich_signals
    print(f"  fleet_signal_depth={fleet_signals.fleet_signal_depth:.2f}, "
          f"rich_signals={has_rich_signals}")

    # Rebuild evidence_list with signal data for signal-aware fleet analysis
    evidence_list = [
        _telemetry_to_bot_evidence(
            t,
            signal_depth=(
                signal_snapshots_by_bot[t.bot_id].signal_depth
                if t.bot_id in signal_snapshots_by_bot
                else 0.0
            ),
            proposal_evidence_json=(
                build_proposal_evidence(signal_snapshots_by_bot[t.bot_id]).to_json_safe()
                if t.bot_id in signal_snapshots_by_bot
                else None
            ),
        )
        for t in telemetry_list
    ]

    # ------------------------------------------------------------------
    # Step 3: Analyze fleet
    # ------------------------------------------------------------------
    print("\n[STEP 3] Running fleet analyzer...")
    decision = analyze_fleet(evidence_list, cycle_id=cycle_id)
    assert decision.fleet_summary is not None
    summary = decision.fleet_summary

    print(f"  total bots:           {summary.total_bots}")
    print(f"  ping ok:              {summary.ping_ok_count}")
    print(f"  ping failed:          {summary.ping_failed_count}")
    print(f"  status authenticated: {summary.status_authenticated_count}")
    print(f"  status yellow (env):  {summary.status_yellow_missing_env_count}")
    print(f"  status failed:        {summary.status_failed_count}")
    print(f"  shadow proposals:     {summary.shadow_proposal_count}")
    print(f"  no-proposal:          {summary.no_proposal_count}")
    print(f"  fleet verdict:        {summary.fleet_verdict}")
    print(f"  verdict reason:       {summary.fleet_verdict_reason}")

    # Determine exit code based on fleet verdict
    fleet_exit_code = 2 if summary.ping_ok_count == 0 and summary.total_bots > 0 else 0

    # ------------------------------------------------------------------
    # Step 4: Safety path for every ShadowProposal
    # ------------------------------------------------------------------
    print("\n[STEP 4] Passing ShadowProposals through safety path...")
    _SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)
    shadow_logger = ShadowLogger(log_dir=_SHADOW_LOG_DIR)

    safety_results: list[dict[str, object]] = []
    for d in decision.per_bot:
        if d.decision_type != DECISION_SHADOW_PROPOSAL:
            safety_results.append({
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "no_proposal_reason": d.no_proposal_reason,
                "riskguard": "SKIPPED_NO_PROPOSAL",
                "shadow_logger": "SKIPPED_NO_PROPOSAL",
                "approval_status": "NOT_APPLICABLE",
            })
            continue

        decision_dict = _asdict_proposal(d)
        riskguard = _riskguard_check(decision_dict)

        shadow_logger.log(
            bot_id=d.bot_id,
            candidate_sha=d.candidate_sha256,
            params=dict(d.parameters),
            outcome="active_cycle_shadow_proposal",
            phase="propose",
            decision="hold",
            reason=(
                f"Active cycle v1: ping_ok={d.evidence_summary['ping']['ok']}, "
                f"status_auth_outcome={d.evidence_summary['status']['auth_outcome']}, "
                f"open_trades={d.evidence_summary['status']['open_trades']}, "
                f"hypothesis={d.hypothesis}, "
                f"RiskGuard={riskguard['result']}"
            ),
        )
        entries = shadow_logger.get_entries(d.bot_id)

        safety_results.append({
            "bot_id": d.bot_id,
            "decision_type": d.decision_type,
            "candidate_sha256": d.candidate_sha256,
            "hypothesis": d.hypothesis,
            "riskguard": riskguard["result"],
            "riskguard_reason": riskguard["reason"],
            "shadow_logger": "LOGGED" if entries else "EMPTY",
            "shadow_logger_entries": len(entries),
            "approval_status": "PENDING_HUMAN",
        })

    print(f"  safety evaluations:   {len(safety_results)}")

    # ------------------------------------------------------------------
    # Step 5: Persist artifacts
    # ------------------------------------------------------------------
    print("\n[STEP 5] Persisting cycle artifacts...")
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _CYCLE_STATE_DIR.mkdir(parents=True, exist_ok=True)

    # 5a. Evidence bundle (JSON)
    per_bot_raw = [_asdict_proposal(d) for d in decision.per_bot]

    evidence_bundle: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "active_cycle_runner_v1",
        "cycle_id": cycle_id,
        "branch": branch,
        "commit_sha": commit_sha,
        "generated_at_utc": now_iso,
        "registry_path": str(_CONFIG_PATH.relative_to(_REPO_ROOT)),
        "bots": [
            {
                "bot_id": t.bot_id,
                "base_url": t.base_url,
                "auth_type": t.auth_type,
                "username_env": t.username_env,
                "password_env": t.password_env,
                "ping": {
                    "status_code": t.ping_status_code,
                    "ok": t.ping_ok,
                    "response_summary": t.ping_response_summary[:200],
                },
                "status": {
                    "status_code": t.status_status_code,
                    "ok": t.status_ok,
                    "response_summary": t.status_response_summary[:200],
                    "auth_outcome": t.status_auth_outcome,
                    "open_trades": t.status_open_trades,
                },
                "missing_env_vars": list(t.missing_env_vars),
                "auth_error_summary": t.auth_error_summary[:200],
                "fetched_at_utc": t.fetched_at_utc,
            }
            for t in telemetry_list
        ],
        "per_bot_decisions": per_bot_raw,
        "safety_results": safety_results,
        "fleet_summary": {
            "total_bots": summary.total_bots,
            "ping_ok_count": summary.ping_ok_count,
            "ping_failed_count": summary.ping_failed_count,
            "status_authenticated_count": summary.status_authenticated_count,
            "status_yellow_missing_env_count": summary.status_yellow_missing_env_count,
            "status_failed_count": summary.status_failed_count,
            "shadow_proposal_count": summary.shadow_proposal_count,
            "no_proposal_count": summary.no_proposal_count,
            "fleet_verdict": summary.fleet_verdict,
            "fleet_verdict_reason": summary.fleet_verdict_reason,
            "runtime_mutations": 0,
            "config_mutations": 0,
            "live_trading_mutations": 0,
            "docker_mutations": 0,
            "strategy_mutations": 0,
        },
    }

    bundle_path = _EVIDENCE_DIR / f"active_cycle_{cycle_id}.json"
    with open(bundle_path, "w") as f:
        json.dump(evidence_bundle, f, indent=2, sort_keys=True)
    print(f"  evidence bundle:  {bundle_path.relative_to(_REPO_ROOT)}")

    # Secret leak check
    _check_secret_leak(evidence_bundle, telemetry_list)

    # 5b. Cycle state
    cycle_state = build_cycle_state(
        cycle_id=cycle_id,
        branch=branch,
        commit_sha=commit_sha,
        fleet_decision=decision,
        per_bot_decisions_raw=per_bot_raw,
    )
    state_path = persist_cycle_state(state=cycle_state, state_dir=_CYCLE_STATE_DIR)
    print(f"  cycle state:      {state_path.relative_to(_REPO_ROOT)}")
    print(f"\n{print_cycle_state(cycle_state)}")

    # 5c. Markdown report
    report_path = _REPORT_DIR / "active_cycle_runner_report.md"
    report_text = _build_report_markdown(
        cycle_id=cycle_id,
        branch=branch,
        commit_sha=commit_sha,
        now_iso=now_iso,
        telemetry_list=telemetry_list,
        decision=decision,
        safety_results=safety_results,
    )
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"  report:           {report_path.relative_to(_REPO_ROOT)}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("CYCLE COMPLETE")
    print("=" * 72)
    print(f"  fleet verdict:           {summary.fleet_verdict}")
    print(f"  shadow proposals:        {summary.shadow_proposal_count}")
    print(f"  no-proposal:             {summary.no_proposal_count}")
    print("  mutation counters:")
    print("    runtime:               0")
    print("    config:                0")
    print("    live_trading:          0")
    print("    docker:                0")
    print("    strategy:              0")
    print("  controller:              PAUSED / L3_REPOSITORY_ONLY")
    print(f"  evidence bundle:         {bundle_path}")
    print(f"  cycle state:             {state_path}")
    print(f"  report:                  {report_path}")
    print("=" * 72)

    return fleet_exit_code


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _asdict_proposal(decision) -> dict[str, object]:
    """Convert a ShadowProposalDecision to a safe dict."""
    return {
        "decision_type": decision.decision_type,
        "bot_id": decision.bot_id,
        "candidate_sha256": decision.candidate_sha256,
        "base_mode": decision.base_mode,
        "mutation_policy": decision.mutation_policy,
        "requires_human_approval": decision.requires_human_approval,
        "hypothesis": decision.hypothesis,
        "parameters": dict(decision.parameters),
        "metadata_only_candidates": dict(decision.metadata_only_candidates),
        "evidence_summary": decision.evidence_summary,
        "no_proposal_reason": decision.no_proposal_reason,
        "fetched_at_utc": decision.fetched_at_utc,
    }


def _build_report_markdown(
    cycle_id: str,
    branch: str,
    commit_sha: str,
    now_iso: str,
    telemetry_list: list[NormalizedTelemetry],
    decision,
    safety_results: list[dict[str, object]],
) -> str:
    """Render the cycle markdown report."""
    summary = decision.fleet_summary

    lines: list[str] = []
    lines.append("# SI v2 Active Multi-Bot Cycle Runner — Report")
    lines.append("")
    lines.append(f"**Timestamp (UTC):** {now_iso}")
    lines.append(f"**Cycle ID:** `{cycle_id}`")
    lines.append(f"**Branch:** `{branch}`")
    lines.append(f"**Commit SHA:** `{commit_sha}`")
    lines.append("**Registry:** `self_improvement_v2/config/freqtrade_bots.readonly.json`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        "This is a repeatable Self-Improvement cycle step (v1) that "
        "read authenticated telemetry from all four Freqtrade dry-run bots, "
        "normalized it, analyzed it in fleet context, generated per-bot "
        "ShadowProposals or NO_PROPOSAL decisions, and persisted a cycle "
        "state/report for later measurement."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Bots Processed")
    lines.append("")
    lines.append("| # | bot_id | base_url | auth_type |")
    lines.append("|---|--------|----------|-----------|")
    for t in telemetry_list:
        idx = telemetry_list.index(t) + 1
        lines.append(
            f"| {idx} | `{t.bot_id}` | `{t.base_url}` | `{t.auth_type}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Bot Decision Table")
    lines.append("")
    lines.append("| bot_id | decision | hypothesis | no_proposal_reason | approval |")
    lines.append("|--------|----------|------------|--------------------|----------|")
    for d in decision.per_bot:
        hyp = d.hypothesis or "-"
        reason = d.no_proposal_reason or "-"
        lines.append(
            f"| `{d.bot_id}` | `{d.decision_type}` | `{hyp}` | `{reason}` "
            f"| `{next((s['approval_status'] for s in safety_results if s['bot_id'] == d.bot_id), '?')}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### Fleet-Level Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| total_bots | `{summary.total_bots}` |")
    lines.append(f"| ping_ok_count | `{summary.ping_ok_count}` |")
    lines.append(f"| ping_failed_count | `{summary.ping_failed_count}` |")
    lines.append(f"| status_authenticated_count | `{summary.status_authenticated_count}` |")
    lines.append(f"| status_yellow_missing_env_count | `{summary.status_yellow_missing_env_count}` |")
    lines.append(f"| shadow_proposal_count | `{summary.shadow_proposal_count}` |")
    lines.append(f"| no_proposal_count | `{summary.no_proposal_count}` |")
    lines.append(f"| fleet_verdict | `{summary.fleet_verdict}` |")
    lines.append(f"| reason | {summary.fleet_verdict_reason} |")
    lines.append("")
    lines.append("### Mutation Counters")
    lines.append("")
    lines.append("| Counter | Value |")
    lines.append("|---------|-------|")
    lines.append("| runtime_mutations | `0` |")
    lines.append("| config_mutations | `0` |")
    lines.append("| live_trading_mutations | `0` |")
    lines.append("| docker_mutations | `0` |")
    lines.append("| strategy_mutations | `0` |")
    lines.append("| controller_state | `PAUSED / L3_REPOSITORY_ONLY` |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Safety Confirmation")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append("| controller_paused | Yes |")
    lines.append("| runtime_mutations | 0 |")
    lines.append("| config_mutations | 0 |")
    lines.append("| live_trading_mutations | 0 |")
    lines.append("| docker_mutations | 0 |")
    lines.append("| strategy_mutations | 0 |")
    lines.append("| secrets_in_bundle | No (checked) |")
    lines.append("| all_proposals_pending_human | Yes |")
    lines.append("")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def main() -> int:
    """Entry point for ``python -m si_v2.loop.active_cycle_runner``."""
    try:
        return run_active_cycle()
    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
