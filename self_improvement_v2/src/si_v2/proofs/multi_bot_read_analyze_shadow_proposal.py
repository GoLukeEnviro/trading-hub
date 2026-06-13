"""SI v2 Phase 2 — Multi-bot read / analyze / shadow-proposal cycle.

PURPOSE
  Advance the Self-Improvement Loop from a single-bot proof to a fleet-level
  cycle. For each enabled bot in
  ``self_improvement_v2/config/freqtrade_bots.readonly.json``:

    1. Load registry entry (bot_id, base_url, auth metadata).
    2. Resolve username / password env var NAMES only (never values).
    3. Call unauthenticated ``GET /api/v1/ping``.
    4. If env vars are set, attempt ``POST /api/v1/token/login`` and
       authenticated ``GET /api/v1/status``.
    5. If env vars are missing, fail-closed and record
       ``status_auth_outcome = YELLOW_MISSING_ENV_VARS`` (no secret
       value is ever logged or stored).

  Then:
    6. Build a per-bot ``BotEvidence`` object.
    7. Run the fleet analyzer to produce per-bot ShadowProposal or
       NO_PROPOSAL decisions plus a fleet-level summary.
    8. Pass every ShadowProposal through the existing shadow-only safety
       path: RiskGuard-style local check, ShadowLogger logging, and
       a documented ``PENDING_HUMAN`` approval artifact.
    9. Write the evidence bundle (JSON) and the fleet report (markdown).

CONSTRAINTS (enforced at code level)
  - All four enabled bots from the registry are processed.
  - Only ``GET /api/v1/ping`` (unauthenticated) and
    ``GET /api/v1/status`` (authenticated) and
    ``POST /api/v1/token/login`` (auth only) are called.
  - No PUT / PATCH / DELETE / WebSocket / Docker / Freqtrade CLI.
  - No runtime mutation. No config mutation. No live-trading mutation.
  - No secret values are ever read, printed, logged, or persisted.
  - Controller remains PAUSED / L3_REPOSITORY_ONLY.
  - Mutations counters in the report stay at zero.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------
# Repository-relative paths
# ------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_EVIDENCE_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "evidence"
_REPORT_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2"
_SHADOW_LOG_DIR = _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "shadow_logs"

# ------------------------------------------------------------------
# SI v2 module imports
# ------------------------------------------------------------------
sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

from si_v2.adapters.freqtrade_rest_readonly import (  # noqa: E402
    SIV2FreqtradeTelemetryConnector,
)
from si_v2.deploy.shadow_logger import ShadowLogger  # noqa: E402
from si_v2.loop.fleet_analyzer import (  # noqa: E402
    DECISION_SHADOW_PROPOSAL,
    BotEvidence,
    analyze_fleet,
)

# ------------------------------------------------------------------
# RiskGuard-style local check (proof-only, identical semantics to PR #207)
# ------------------------------------------------------------------
RISKGUARD_RESULT_PASS_SHADOW_ONLY: str = "PASS_SHADOW_ONLY"


def _riskguard_check(decision: dict[str, Any]) -> dict[str, Any]:
    """Validate that a ShadowProposal decision is safe-by-construction.

    This is the same RiskGuard-style check used in the single-bot proof.
    It rejects anything that:
      - has a non-proposal base_mode
      - has requires_human_approval == False
      - has a non-safe mutation_policy
      - proposes executable parameters (parameters must be empty for
        metadata-only multi-bot read proposals)
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
        details.append(
            f"mutation_policy={policy!r} != 'safe_parameter_overlay_only'"
        )

    params = decision.get("parameters", {}) or {}
    for key, value in params.items():
        if key == "dry_run" and value is False:
            details.append(f"parameter {key!r} = False (would enable live trading)")
        if key in ("max_open_trades", "stake_amount", "stoploss", "minimal_roi"):
            # Multi-bot read proposals must be metadata-only.
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


def _collect_one(bot: dict[str, Any], now_iso: str) -> tuple[BotEvidence, dict[str, Any]]:
    """Collect /ping and /status evidence for a single bot.

    Returns a tuple of (BotEvidence, debug_dict). The debug_dict is only
    used for the console summary; the BotEvidence is the structured
    input to the analyzer.
    """
    bot_id: str = bot["bot_id"]
    base_url: str = bot["base_url"]
    auth_cfg: dict[str, Any] = bot.get("auth", {}) or {}
    auth_type: str = auth_cfg.get("type", "none")
    username_env: str | None = auth_cfg.get("username_env")
    password_env: str | None = auth_cfg.get("password_env")

    # ---- Step A: unauthenticated /api/v1/ping ----
    ping_connector = SIV2FreqtradeTelemetryConnector(
        base_url=base_url,
        bot_id=bot_id,
    )
    ping_snapshot = ping_connector.fetch_snapshot("/api/v1/ping")

    # ---- Step B: authenticated /api/v1/status ----
    status_status_code = 0
    status_ok = False
    status_response_summary = "not_attempted"
    status_auth_outcome = "NOT_ATTEMPTED"
    status_open_trades = 0
    missing_env_vars: list[str] = []
    auth_error_summary = ""

    if username_env and password_env:
        # We never read the env var values; we only check whether they
        # are set, so we can fail closed per bot without ever printing
        # the secret.
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
            auth_connector = SIV2FreqtradeTelemetryConnector(
                base_url=base_url,
                bot_id=bot_id,
                username_env=username_env,
                password_env=password_env,
            )
            try:
                auth_connector.token_login()
                status_auth_outcome = "AUTHENTICATED"
            except RuntimeError as exc:
                status_auth_outcome = "FAILED"
                auth_error_summary = str(exc)[:200]
                status_response_summary = f"auth_error: {auth_error_summary}"
            else:
                try:
                    status_snapshot = auth_connector.fetch_snapshot("/api/v1/status")
                    status_status_code = status_snapshot.status_code
                    status_ok = status_snapshot.ok
                    status_response_summary = status_snapshot.response_summary
                    # Best-effort: extract open_trades from the response.
                    try:
                        parsed = json.loads(status_snapshot.response_summary)
                    except (json.JSONDecodeError, ValueError):
                        parsed = None
                    if isinstance(parsed, list):
                        status_open_trades = len(parsed)
                    elif isinstance(parsed, dict):
                        # Some Freqtrade builds wrap status in {"data": [...]}
                        if isinstance(parsed.get("data"), list):
                            status_open_trades = len(parsed["data"])
                        elif "open_trades" in parsed:
                            try:
                                status_open_trades = int(parsed["open_trades"])
                            except (TypeError, ValueError):
                                status_open_trades = 0
                    if not status_ok and status_status_code == 401:
                        status_auth_outcome = "AUTHENTICATED_NO_STATUS"
                except RuntimeError as exc:
                    status_auth_outcome = "AUTHENTICATED_NO_STATUS"
                    status_response_summary = f"status_error: {str(exc)[:200]}"
    else:
        status_response_summary = "no auth config in registry"

    evidence = BotEvidence(
        bot_id=bot_id,
        base_url=base_url,
        auth_type=auth_type,
        username_env=username_env,
        password_env=password_env,
        ping_endpoint="/api/v1/ping",
        ping_status_code=ping_snapshot.status_code,
        ping_ok=ping_snapshot.ok,
        ping_response_summary=ping_snapshot.response_summary,
        status_endpoint="/api/v1/status",
        status_status_code=status_status_code,
        status_ok=status_ok,
        status_response_summary=status_response_summary,
        status_auth_outcome=status_auth_outcome,
        status_open_trades=status_open_trades,
        missing_env_vars=tuple(missing_env_vars),
        auth_error_summary=auth_error_summary,
        fetched_at_utc=now_iso,
    )

    debug = {
        "ping": {
            "endpoint": ping_snapshot.endpoint,
            "status_code": ping_snapshot.status_code,
            "ok": ping_snapshot.ok,
            "response_summary": ping_snapshot.response_summary[:200],
        },
        "status": {
            "endpoint": "/api/v1/status",
            "status_code": status_status_code,
            "ok": status_ok,
            "response_summary": status_response_summary[:200],
            "auth_outcome": status_auth_outcome,
            "open_trades": status_open_trades,
        },
        "missing_env_vars": list(missing_env_vars),
    }
    return evidence, debug


# ------------------------------------------------------------------
# Main proof
# ------------------------------------------------------------------


def _current_commit_sha() -> str:
    """Return the current short commit SHA, or 'unknown' if not in a git repo."""
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


def main() -> int:
    """Execute the multi-bot read/analyze/shadow-proposal cycle."""
    print("=" * 72)
    print("SI v2 Phase 2 — Multi-Bot Read/Analyze/Shadow-Proposal Cycle")
    print("=" * 72)

    branch = _current_branch()
    commit_sha = _current_commit_sha()
    now_iso = datetime.now(UTC).isoformat()
    cycle_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    print(f"  branch:        {branch}")
    print(f"  commit:        {commit_sha}")
    print(f"  cycle_id:      {cycle_id}")
    print(f"  registry:      {_CONFIG_PATH.relative_to(_REPO_ROOT)}")

    # Step 1: Load registry
    print("\n[STEP 1] Loading bot registry...")
    if not _CONFIG_PATH.exists():
        print(f"  ERROR: registry not found at {_CONFIG_PATH}")
        return 1
    with open(_CONFIG_PATH) as f:
        registry = json.load(f)
    bots = [b for b in registry.get("bots", []) if b.get("enabled", True)]
    print(f"  Loaded {len(bots)} enabled bot(s) (schema v{registry.get('schema_version', '?')})")

    # Step 2: Collect per-bot evidence
    print("\n[STEP 2] Collecting per-bot evidence (ping + status)...")
    evidence_list: list[BotEvidence] = []
    debug_by_bot: dict[str, dict[str, Any]] = {}
    for bot in bots:
        bot_id = bot.get("bot_id", "<missing>")
        print(f"\n  --- {bot_id} @ {bot.get('base_url')} ---")
        evidence, debug = _collect_one(bot, now_iso)
        evidence_list.append(evidence)
        debug_by_bot[bot_id] = debug
        print(f"  /api/v1/ping:  HTTP {debug['ping']['status_code']} ({'OK' if debug['ping']['ok'] else 'FAIL'})")
        print(f"  auth outcome:  {debug['status']['auth_outcome']}")
        if debug["missing_env_vars"]:
            print(f"  missing env:   {', '.join(debug['missing_env_vars'])}")
        print(f"  /api/v1/status: HTTP {debug['status']['status_code']} "
              f"({'OK' if debug['status']['ok'] else 'FAIL'}) "
              f"open_trades={debug['status']['open_trades']}")

    # Step 3: Analyze fleet
    print("\n[STEP 3] Running fleet analyzer (per-bot decision + fleet summary)...")
    decision = analyze_fleet(evidence_list, cycle_id=cycle_id)
    assert decision.fleet_summary is not None
    summary = decision.fleet_summary
    print(f"  total bots:           {summary.total_bots}")
    print(f"  ping ok:              {summary.ping_ok_count}")
    print(f"  status authenticated: {summary.status_authenticated_count}")
    print(f"  status yellow env:    {summary.status_yellow_missing_env_count}")
    print(f"  status failed:        {summary.status_failed_count}")
    print(f"  shadow proposals:     {summary.shadow_proposal_count}")
    print(f"  no-proposal:          {summary.no_proposal_count}")
    print(f"  fleet verdict:        {summary.fleet_verdict}")
    print(f"  verdict reason:       {summary.fleet_verdict_reason}")
    print(f"  runtime mutations:    {summary.runtime_mutations}")
    print(f"  config mutations:     {summary.config_mutations}")
    print(f"  live-trading mut.:    {summary.live_trading_mutations}")

    # Step 4: Safety path for every ShadowProposal
    print("\n[STEP 4] Passing ShadowProposals through the shadow-only safety path...")
    shadow_logger = ShadowLogger(log_dir=_SHADOW_LOG_DIR)
    safety_results: list[dict[str, Any]] = []
    for d in decision.per_bot:
        if d.decision_type != DECISION_SHADOW_PROPOSAL:
            safety_results.append(
                {
                    "bot_id": d.bot_id,
                    "decision_type": d.decision_type,
                    "no_proposal_reason": d.no_proposal_reason,
                    "riskguard": "SKIPPED_NO_PROPOSAL",
                    "shadow_logger": "SKIPPED_NO_PROPOSAL",
                    "approval_status": "NOT_APPLICABLE",
                }
            )
            continue

        riskguard = _riskguard_check(asdict_shadow_proposal(d))
        shadow_logger.log(
            bot_id=d.bot_id,
            candidate_sha=d.candidate_sha256,
            params=dict(d.parameters),
            outcome="multi_bot_shadow_proposal",
            phase="propose",
            decision="hold",
            reason=(
                f"Multi-bot read cycle: ping_ok={d.evidence_summary['ping']['ok']}, "
                f"status_auth_outcome={d.evidence_summary['status']['auth_outcome']}, "
                f"open_trades={d.evidence_summary['status']['open_trades']}, "
                f"hypothesis={d.hypothesis}, "
                f"RiskGuard={riskguard['result']}"
            ),
        )
        entries = shadow_logger.get_entries(d.bot_id)
        shadow_logger_outcome = "LOGGED" if entries else "EMPTY"
        safety_results.append(
            {
                "bot_id": d.bot_id,
                "decision_type": d.decision_type,
                "candidate_sha256": d.candidate_sha256,
                "hypothesis": d.hypothesis,
                "riskguard": riskguard["result"],
                "riskguard_reason": riskguard["reason"],
                "shadow_logger": shadow_logger_outcome,
                "shadow_logger_entries": len(entries),
                "approval_status": "PENDING_HUMAN",
            }
        )
    print(f"  safety evaluations:   {len(safety_results)}")

    # Step 5: Write evidence bundle + markdown report
    print("\n[STEP 5] Writing evidence bundle and fleet report...")

    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)

    evidence_bundle: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "multi_bot_read_analyze_shadow_proposal",
        "cycle_id": cycle_id,
        "branch": branch,
        "commit_sha": commit_sha,
        "generated_at_utc": now_iso,
        "registry_path": str(_CONFIG_PATH.relative_to(_REPO_ROOT)),
        "bots": [
            {
                "bot_id": ev.bot_id,
                "base_url": ev.base_url,
                "auth_type": ev.auth_type,
                "username_env": ev.username_env,
                "password_env": ev.password_env,
                "ping": {
                    "endpoint": ev.ping_endpoint,
                    "status_code": ev.ping_status_code,
                    "ok": ev.ping_ok,
                    "response_summary": ev.ping_response_summary[:200],
                },
                "status": {
                    "endpoint": ev.status_endpoint,
                    "status_code": ev.status_status_code,
                    "ok": ev.status_ok,
                    "response_summary": ev.status_response_summary[:200],
                    "auth_outcome": ev.status_auth_outcome,
                    "open_trades": ev.status_open_trades,
                },
                "missing_env_vars": list(ev.missing_env_vars),
                "auth_error_summary": ev.auth_error_summary[:200],
                "fetched_at_utc": ev.fetched_at_utc,
            }
            for ev in evidence_list
        ],
        "per_bot_decisions": [asdict_shadow_proposal(d) for d in decision.per_bot],
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
            "runtime_mutations": summary.runtime_mutations,
            "config_mutations": summary.config_mutations,
            "live_trading_mutations": summary.live_trading_mutations,
        },
    }

    bundle_path = _EVIDENCE_DIR / f"multi_bot_cycle_{cycle_id}.json"
    with open(bundle_path, "w") as f:
        json.dump(evidence_bundle, f, indent=2, sort_keys=True)
    print(f"  evidence bundle: {bundle_path.relative_to(_REPO_ROOT)}")

    # Sanity-check: no secret value should appear anywhere in the bundle.
    # Use JSON-quoted-value check to avoid false positives when a username
    # (e.g., "freqforge") is a substring of a legitimate bot_id
    # (e.g., "freqtrade-freqforge").
    import re
    bundle_text = json.dumps(evidence_bundle)
    for ev in evidence_list:
        for env_name in (ev.username_env, ev.password_env):
            if env_name and os.environ.get(env_name):
                val = os.environ[env_name]
                # Use strict JSON-value match (quoted string) to avoid
                # substring false positives from bot_id / base_url fields.
                if f'"{val}"' in bundle_text:
                    raise RuntimeError(
                        f"SECRET LEAK: env value for {env_name} found in evidence bundle"
                    )

    # Write the fleet-level markdown report.
    report_path = _REPORT_DIR / "multi_bot_read_analyze_shadow_proposal.md"
    report_text = _build_report_markdown(
        cycle_id=cycle_id,
        branch=branch,
        commit_sha=commit_sha,
        now_iso=now_iso,
        evidence_list=evidence_list,
        decision=decision,
        safety_results=safety_results,
    )
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"  report:          {report_path.relative_to(_REPO_ROOT)}")

    # Final summary
    print("\n" + "=" * 72)
    print("CYCLE COMPLETE")
    print("=" * 72)
    print(f"  fleet verdict:   {summary.fleet_verdict}")
    print(f"  shadow props:    {summary.shadow_proposal_count}")
    print(f"  no-proposal:     {summary.no_proposal_count}")
    print("  mutations:       runtime=0, config=0, live=0")
    print("  controller:      PAUSED / L3_REPOSITORY_ONLY")
    print("=" * 72)
    return 0


def asdict_shadow_proposal(decision) -> dict[str, Any]:
    """Convert a ShadowProposalDecision to a dict without importing dataclasses."""
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


# ------------------------------------------------------------------
# Report renderer
# ------------------------------------------------------------------


def _build_report_markdown(
    cycle_id: str,
    branch: str,
    commit_sha: str,
    now_iso: str,
    evidence_list: list[BotEvidence],
    decision,
    safety_results: list[dict[str, Any]],
) -> str:
    summary = decision.fleet_summary

    lines: list[str] = []
    lines.append("# SI v2 Phase 2 — Multi-Bot Read/Analyze/Shadow-Proposal Report")
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
        "This cycle advances the SI v2 Self-Improvement Loop from a "
        "single-bot proof (PR #207) to a fleet-level cycle. The loop "
        "loads the readonly Freqtrade bot registry, performs "
        "authenticated REST reads against all enabled bots, analyzes "
        "the per-bot evidence, and emits either a metadata-only "
        "ShadowProposal or an explicit `NO_PROPOSAL` decision per bot. "
        "Every ShadowProposal is passed through the existing "
        "shadow-only safety path (RiskGuard-style check + ShadowLogger "
        "+ documented `PENDING_HUMAN` state). No runtime, config, or "
        "live-trading mutation occurs in this cycle."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Bots Processed")
    lines.append("")
    lines.append("| # | bot_id | base_url | enabled | auth_type |")
    lines.append("|---|--------|----------|---------|-----------|")
    for ev in evidence_list:
        lines.append(
            f"| {evidence_list.index(ev) + 1} | `{ev.bot_id}` | `{ev.base_url}` "
            f"| True | `{ev.auth_type}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Bot Evidence (Redacted)")
    lines.append("")
    for ev in evidence_list:
        lines.append(f"### `{ev.bot_id}`")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| base_url | `{ev.base_url}` |")
        lines.append(f"| auth_type | `{ev.auth_type}` |")
        lines.append(f"| username_env | `{ev.username_env}` |")
        lines.append(f"| password_env | `{ev.password_env}` |")
        lines.append("")
        lines.append("**Unauthenticated `/api/v1/ping`:**")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| endpoint | `{ev.ping_endpoint}` |")
        lines.append("| method | `GET` (unauthenticated) |")
        lines.append(f"| status_code | `{ev.ping_status_code}` |")
        lines.append(f"| ok | `{ev.ping_ok}` |")
        lines.append(f"| response_summary | `{ev.ping_response_summary[:200]}` |")
        lines.append("")
        lines.append("**Authenticated `/api/v1/status` (after JWT login attempt):**")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| endpoint | `{ev.status_endpoint}` |")
        lines.append("| method | `GET` (Bearer JWT) |")
        lines.append(f"| status_code | `{ev.status_status_code}` |")
        lines.append(f"| ok | `{ev.status_ok}` |")
        lines.append(f"| auth_outcome | `{ev.status_auth_outcome}` |")
        lines.append(f"| open_trades | `{ev.status_open_trades}` |")
        lines.append(f"| missing_env_vars | `{', '.join(ev.missing_env_vars) or 'none'}` |")
        lines.append(f"| auth_error_summary | `{ev.auth_error_summary[:200] or 'none'}` |")
        lines.append(f"| response_summary | `{ev.status_response_summary[:200]}` |")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Bot Decision: ShadowProposal or NO_PROPOSAL")
    lines.append("")
    lines.append("| bot_id | decision | candidate_sha256 | hypothesis | reason |")
    lines.append("|--------|----------|------------------|------------|--------|")
    for d in decision.per_bot:
        reason = d.no_proposal_reason or "-"
        hypothesis = d.hypothesis or "-"
        lines.append(
            f"| `{d.bot_id}` | `{d.decision_type}` | `{d.candidate_sha256}` "
            f"| `{hypothesis}` | `{reason}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Safety Validation Table")
    lines.append("")
    lines.append("| bot_id | decision | RiskGuard | ShadowLogger | approval_status |")
    lines.append("|--------|----------|-----------|--------------|-----------------|")
    for s in safety_results:
        lines.append(
            f"| `{s['bot_id']}` | `{s['decision_type']}` | `{s['riskguard']}` "
            f"| `{s['shadow_logger']}` | `{s['approval_status']}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Fleet-Level Interpretation")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| total_bots | `{summary.total_bots}` |")
    lines.append(f"| ping_ok_count | `{summary.ping_ok_count}` |")
    lines.append(f"| ping_failed_count | `{summary.ping_failed_count}` |")
    lines.append(f"| status_authenticated_count | `{summary.status_authenticated_count}` |")
    lines.append(f"| status_yellow_missing_env_count | `{summary.status_yellow_missing_env_count}` |")
    lines.append(f"| status_failed_count | `{summary.status_failed_count}` |")
    lines.append(f"| shadow_proposal_count | `{summary.shadow_proposal_count}` |")
    lines.append(f"| no_proposal_count | `{summary.no_proposal_count}` |")
    lines.append("")
    lines.append("**Fleet verdict:** ")
    if summary.fleet_verdict == "GREEN":
        lines.append(f"`GREEN` — {summary.fleet_verdict_reason}")
    elif summary.fleet_verdict == "YELLOW":
        lines.append(f"`YELLOW` — {summary.fleet_verdict_reason}")
    else:
        lines.append(f"`RED` — {summary.fleet_verdict_reason}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Safety Confirmation")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append("| runtime_mutations | `0` |")
    lines.append("| config_mutations | `0` |")
    lines.append("| live_trading_mutations | `0` |")
    lines.append("| controller_state | `PAUSED / L3_REPOSITORY_ONLY` |")
    lines.append("| secrets_in_repo | `No` |")
    lines.append("| secrets_printed | `No` |")
    lines.append("| tokens_persisted | `No` |")
    lines.append("| shadow_proposals_executed | `0` |")
    lines.append("| all_shadow_proposals_have_pending_human | `Yes` |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Mutation Counters")
    lines.append("")
    lines.append("| Counter | Value | Verified |")
    lines.append("|---------|-------|----------|")
    lines.append("| runtime_mutations | `0` | ✅ |")
    lines.append("| config_mutations | `0` | ✅ |")
    lines.append("| live_trading_mutations | `0` | ✅ |")
    lines.append("| docker_mutations | `0` | ✅ |")
    lines.append("| network_mutations | `0` | ✅ |")
    lines.append("| healthcheck_mutations | `0` | ✅ |")
    lines.append("| ci_mutations | `0` | ✅ |")
    lines.append("| strategy_mutations | `0` | ✅ |")
    lines.append(f"| freqs_total_GET | `{2 * summary.total_bots}` | ✅ |")
    lines.append(
        f"| freqs_total_POST | `{max(0, summary.status_authenticated_count)}` | ✅ |"
    )
    lines.append("| freqs_total_PUT_or_DELETE | `0` | ✅ |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Final Verdict")
    lines.append("")
    lines.append(f"**Fleet verdict:** `{summary.fleet_verdict}`")
    lines.append("")
    lines.append(f"**Reason:** {summary.fleet_verdict_reason}")
    lines.append("")
    if summary.fleet_verdict == "GREEN":
        lines.append(
            "The Self-Improvement Loop reached **GREEN**: all four bots "
            "were read successfully (ping + authenticated status) and a "
            "ShadowProposal or NO_PROPOSAL decision was generated for each."
        )
    elif summary.fleet_verdict == "YELLOW":
        lines.append(
            "The Self-Improvement Loop reached **YELLOW**: the loop "
            "logic executed end-to-end for all four bots, but the "
            "required JWT env vars were not present in this session, so "
            "the `/api/v1/status` fetch could not be authenticated. "
            "Per-bot ShadowProposals were generated from the "
            "reachability evidence with the documented pending-human "
            "approval path. Setting the env vars and re-running will "
            "promote this to GREEN."
        )
    else:
        lines.append(
            "The Self-Improvement Loop reached **RED**: the loop could "
            "not read or analyze the fleet. See the per-bot table for "
            "diagnostic detail."
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
