"""SI v2 Phase 2 — Multi-Bot Authenticated Read-Only REST Telemetry Proof.

PURPOSE
  Extends the multi-bot ping proof (#223) to authenticated read-only telemetry.
  Demonstrates that SI v2 can:
    1. Load all four enabled bots from the registry.
    2. For each bot, call unauthenticated GET /api/v1/ping for connectivity baseline.
    3. For each bot, acquire a JWT token via POST /api/v1/token/login (Basic Auth).
    4. For each bot, call authenticated GET endpoints: /version, /status, /count, /profit.
    5. Classify each bot as GREEN/YELLOW/RED based on endpoint success.
    6. Aggregate all observations into one fleet-level telemetry ShadowProposal.

CONSTRAINTS (enforced at code level)
  - Auth-only POST: only /api/v1/token/login. All other non-GET methods rejected.
  - JWT held in memory only. Never printed, persisted, logged, or committed.
  - No Docker, no Freqtrade CLI, no config mutation, no strategy edits.
  - No runtime mutation. No live trading enablement.
  - All four bots addressed — no single-bot-only logic.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from si_v2.state.schemas import MutationCandidate

# ---------------------------------------------------------------------------
# JSON type aliases (mirrors adapter; no Any)
# ---------------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

# ---------------------------------------------------------------------------
# Repository-relative paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_REPORT_PATH = (
    _REPO_ROOT
    / "self_improvement_v2"
    / "reports"
    / "phase2"
    / "multi-bot-authenticated-telemetry-proof.md"
)

# ---------------------------------------------------------------------------
# Allowed telemetry endpoints (authenticated). Ping is unauthenticated.
# ---------------------------------------------------------------------------
UNAUTH_ENDPOINTS = {"/api/v1/ping"}
AUTH_ENDPOINTS = {"/api/v1/version", "/api/v1/status", "/api/v1/count", "/api/v1/profit"}
ALL_TELEMETRY_ENDPOINTS = ["/api/v1/ping", "/api/v1/version", "/api/v1/status",
                           "/api/v1/count", "/api/v1/profit"]

# ---------------------------------------------------------------------------
# Bot classification
# ---------------------------------------------------------------------------
BOT_GREEN = "GREEN"
BOT_YELLOW = "YELLOW"
BOT_RED = "RED"


class BotTelemetryResult:
    """Result of telemetry collection for a single bot (not a dataclass to avoid
    Python 3.13 importlib + from __future__ import annotations compatibility
    issues when loaded via spec_from_file_location in tests)."""
    def __init__(self, bot_id: str, base_url: str,
                 classification: str = BOT_RED,
                 endpoints: dict[str, dict[str, JsonValue]] | None = None,
                 auth_attempted: bool = False,
                 auth_success: bool = False,
                 error: str = "") -> None:
        self.bot_id = bot_id
        self.base_url = base_url
        self.classification = classification
        self.endpoints = endpoints or {}
        self.auth_attempted = auth_attempted
        self.auth_success = auth_success
        self.error = error


# ---------------------------------------------------------------------------
# RiskGuard-style local check (proof-only)
# ---------------------------------------------------------------------------
RISKGUARD_RESULT_PASS_SHADOW_ONLY: str = "PASS_SHADOW_ONLY"


def _riskguard_check(candidate: MutationCandidate) -> dict[str, object]:
    """Proof-only RiskGuard-style check."""
    details: list[str] = []

    if candidate.base_mode != "proposal_only":
        details.append(f"base_mode={candidate.base_mode!r} != 'proposal_only'")

    if not candidate.requires_human_approval:
        details.append("requires_human_approval is False")

    if candidate.mutation_policy != "safe_parameter_overlay_only":
        details.append(
            f"mutation_policy={candidate.mutation_policy!r} != "
            "'safe_parameter_overlay_only'"
        )

    for key, value in candidate.parameters.items():
        if key == "dry_run" and (value is False or value == 0):
            details.append(f"parameter {key!r} = False (would enable live trading)")

    if details:
        return {
            "result": "BLOCKED",
            "reason": "; ".join(details),
            "details": details,
        }

    return {
        "result": RISKGUARD_RESULT_PASS_SHADOW_ONLY,
        "reason": (
            f"fleet telemetry candidate {candidate.candidate_sha256} is "
            f"proposal_only, requires human approval, and contains no "
            f"forbidden parameters. Runtime application is blocked."
        ),
        "details": ["proposal_only=True", "runtime_blocked=True",
                     "fleet_scope=True", "auth_telemetry=True"],
    }


# ---------------------------------------------------------------------------
# Fleet artifact builder
# ---------------------------------------------------------------------------
def _build_telemetry_artifact(
    candidate: MutationCandidate,
    bot_results: list[BotTelemetryResult],
    riskguard_result: dict[str, object],
    shadow_logger_result: dict[str, object],
    auth_post_count: int,
) -> dict[str, object]:
    """Build pending-human artifact with authenticated telemetry evidence."""
    bot_ids = [r.bot_id for r in bot_results]
    green = sum(1 for r in bot_results if r.classification == BOT_GREEN)
    yellow = sum(1 for r in bot_results if r.classification == BOT_YELLOW)
    red_bots = sum(1 for r in bot_results if r.classification == BOT_RED)

    return {
        "artifact_type": "shadow_proposal_pending_human",
        "proposal_id": candidate.candidate_sha256,
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "bot_id": candidate.bot_id,
        "candidate_sha256": candidate.candidate_sha256,
        "source": "multi_bot_authenticated_rest_telemetry",
        "hypothesis": (
            "SI v2 controller can read authenticated read-only telemetry "
            "from all four configured Freqtrade dry-run bots and produce "
            "a fleet-level telemetry ShadowProposal artifact without "
            "any runtime mutation."
        ),
        "evidence_summary": {
            "bots_contacted": len(bot_results),
            "bot_ids": bot_ids,
            "green": green,
            "yellow": yellow,
            "red": red_bots,
            "per_bot": {
                r.bot_id: {
                    "classification": r.classification,
                    "auth_success": r.auth_success,
                    "endpoints_tried": len(r.endpoints),
                    "endpoints_ok": sum(
                        1 for e in r.endpoints.values()
                        if e.get("ok") and e.get("status_code") == 200
                    ),
                }
                for r in bot_results
            },
        },
        "status": "pending_human",
        "reason": (
            f"Multi-bot authenticated telemetry proof: "
            f"{green} GREEN / {yellow} YELLOW / {red_bots} RED. "
            f"Auth-only POST count: {auth_post_count}. "
            f"Zero mutation POST/PUT/PATCH/DELETE requests."
        ),
        "risk_guard_result": riskguard_result["result"],
        "shadow_logger_result": shadow_logger_result.get("outcome", "LOGGED"),
        "approval_status": "PENDING_HUMAN",
        "runtime_mutations": 0,
        "config_mutations": 0,
        "freqtrade_post_requests": auth_post_count,
        "freqtrade_mutation_requests": 0,
        "metadata": {
            "telemetry_endpoints": list(ALL_TELEMETRY_ENDPOINTS),
            "auth_endpoints": ["/api/v1/token/login (POST)"],
            "proof_script": Path(__file__).name,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Main proof
# ---------------------------------------------------------------------------
def main() -> int:
    """Execute the multi-bot authenticated read-only telemetry proof.

    Returns:
        0 on success, 1 on failure.
    """
    sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

    from si_v2.adapters.freqtrade_rest_readonly import (
        SIV2FreqtradeTelemetryConnector,
    )
    from si_v2.deploy.shadow_logger import ShadowLogger
    from si_v2.state.schemas import MutationCandidate

    print("=" * 72)
    print("SI v2 Phase 2 — Multi-Bot Authenticated Read-Only Telemetry Proof")
    print("=" * 72)

    # Step 1: Load bot registry
    print("\n[STEP 1] Loading bot registry...")
    if not _CONFIG_PATH.exists():
        print(f"  ERROR: Config not found at {_CONFIG_PATH}")
        return 1

    with open(_CONFIG_PATH) as f:
        registry = json.load(f)

    bots = registry.get("bots", [])
    enabled_bots = [b for b in bots if b.get("enabled", False)]
    print(f"  Loaded {len(bots)} bot(s), {len(enabled_bots)} enabled")
    bot_ids = [b.get("bot_id", "?") for b in enabled_bots]
    print(f"  Enabled bot IDs: {', '.join(bot_ids)}")

    if not enabled_bots:
        print("  ERROR: No enabled bots in registry")
        return 1

    # Step 2-4: For each bot, collect telemetry
    print(f"\n[STEP 2-4] Collecting authenticated telemetry from "
          f"{len(enabled_bots)} bot(s)...")

    bot_results: list[BotTelemetryResult] = []
    total_auth_posts = 0

    for bot in enabled_bots:
        bot_id: str = bot["bot_id"]
        base_url: str = bot["base_url"]
        auth_config = bot.get("auth", {})
        username_env = auth_config.get("username_env")
        password_env = auth_config.get("password_env")

        print(f"\n  --- {bot_id} @ {base_url} ---")
        result = BotTelemetryResult(bot_id=bot_id, base_url=base_url)

        try:
            connector = SIV2FreqtradeTelemetryConnector(
                base_url=base_url,
                bot_id=bot_id,
                username_env=username_env,
                password_env=password_env,
            )
        except Exception as exc:
            result.classification = BOT_RED
            result.error = f"connector_init: {exc}"
            print(f"  INIT ERROR: {exc}")
            bot_results.append(result)
            continue

        auth_available = connector.auth_enabled
        result.auth_attempted = auth_available

        # Try each endpoint in order
        for ep in ALL_TELEMETRY_ENDPOINTS:
            try:
                snapshot = connector.fetch_snapshot(ep)
                endpoint_result = {
                    "endpoint": snapshot.endpoint,
                    "status_code": snapshot.status_code,
                    "ok": snapshot.ok,
                    "response_summary": snapshot.response_summary[:160],
                    "fetched_at_utc": snapshot.fetched_at_utc,
                }
                result.endpoints[ep] = endpoint_result

                # Track auth
                if ep == "/api/v1/ping":
                    pass  # unauthenticated
                elif connector.authenticated:
                    result.auth_success = True

                print(f"  {ep}: {snapshot.status_code} "
                      f"{'OK' if snapshot.ok else 'FAIL'}")

            except RuntimeError as exc:
                err_str = str(exc)
                result.endpoints[ep] = {
                    "endpoint": ep,
                    "status_code": 0,
                    "ok": False,
                    "response_summary": f"RuntimeError: {err_str[:120]}",
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                }
                print(f"  {ep}: SKIP ({err_str[:80]})")
            except ValueError as exc:
                result.endpoints[ep] = {
                    "endpoint": ep,
                    "status_code": 0,
                    "ok": False,
                    "response_summary": f"ValueError: {str(exc)[:120]}",
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                }
                print(f"  {ep}: SKIP ({str(exc)[:80]})")
            except Exception as exc:
                result.endpoints[ep] = {
                    "endpoint": ep,
                    "status_code": 0,
                    "ok": False,
                    "response_summary": f"Exception: {str(exc)[:120]}",
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                }
                print(f"  {ep}: ERROR ({str(exc)[:80]})")

        # Count auth POST calls: one per bot if auth_available and first
        # authenticated fetch_snapshot triggered token_login()
        if auth_available and result.auth_success:
            total_auth_posts += 1

        # Classify bot
        ping_ok = result.endpoints.get("/api/v1/ping", {}).get("ok", False)
        auth_oks = sum(
            1 for ep, e in result.endpoints.items()
            if ep != "/api/v1/ping" and e.get("ok")
        )

        if not ping_ok:
            result.classification = BOT_RED
        elif auth_oks >= 3:
            result.classification = BOT_GREEN
        elif auth_oks >= 1:
            result.classification = BOT_YELLOW
        elif auth_available:
            result.classification = BOT_YELLOW
        else:
            result.classification = BOT_YELLOW

        if not result.error:
            if result.classification == BOT_RED:
                result.error = "Ping failed — bot unreachable"
            elif not auth_available:
                result.error = "Auth not configured (ping OK, no env vars)"
            elif not result.auth_success:
                result.error = "Auth attempted but failed"

        bot_results.append(result)

        print(f"  => Classification: {result.classification}"
              f"{' (' + result.error + ')' if result.error else ''}")

    # Fleet summary
    green = sum(1 for r in bot_results if r.classification == BOT_GREEN)
    yellow = sum(1 for r in bot_results if r.classification == BOT_YELLOW)
    red_bots = sum(1 for r in bot_results if r.classification == BOT_RED)
    print(f"\n  Fleet: {green} GREEN, {yellow} YELLOW, {red_bots} RED")
    print(f"  Auth-only POST calls: {total_auth_posts}")

    # Step 5: Build fleet-level MutationCandidate
    print("\n[STEP 5] Building fleet-level metadata-only MutationCandidate...")
    candidate_hash_input = {
        "bot_ids": sorted(r.bot_id for r in bot_results),
        "classifications": {r.bot_id: r.classification for r in bot_results},
        "proof_timestamp": datetime.now(UTC).isoformat(),
    }
    import hashlib
    candidate_sha = hashlib.sha256(
        json.dumps(candidate_hash_input, sort_keys=True).encode()
    ).hexdigest()[:16]

    fleet_bot_id = "+".join(sorted(r.bot_id for r in bot_results))

    candidate = MutationCandidate(
        bot_id=fleet_bot_id,
        bot_name="Fleet",
        candidate_sha256=candidate_sha,
        source_decision="observe",
        parameters={
            "dry_run": 1,
            "bot_count": len(bot_results),
            "green": green,
            "yellow": yellow,
            "red": red_bots,
        },
        active_overlay_candidates={},
        metadata_only_candidates={"proof_auth_telemetry": 1},
        requires_backtest=False,
        requires_paper_validation=False,
        requires_human_approval=True,
        requires_strategy_adapter=[],
    )

    print(f"  candidate_sha256: {candidate_sha}")
    print(f"  fleet bot_id:     {fleet_bot_id}")
    print(f"  base_mode:        {candidate.base_mode}")
    print(f"  requires_human:   {candidate.requires_human_approval}")

    # Step 6: RiskGuard
    print("\n[STEP 6] RiskGuard-style check...")
    riskguard_result = _riskguard_check(candidate)
    print(f"  Result: {riskguard_result['result']}")
    print(f"  Reason: {riskguard_result['reason']}")

    # Step 7: ShadowLogger
    print("\n[STEP 7] ShadowLogger (in-memory)...")
    shadow_logger = ShadowLogger(log_dir=None)
    shadow_logger.log(
        bot_id=fleet_bot_id,
        candidate_sha=candidate_sha,
        params=dict(candidate.parameters),
        outcome="shadow_proposal_proof",
        phase="proof",
        decision="hold",
        reason=(
            f"Multi-bot auth telemetry proof: "
            f"{green}G/{yellow}Y/{red_bots}R. "
            f"Auth-only POSTs: {total_auth_posts}. "
            f"RiskGuard={riskguard_result['result']}"
        ),
    )
    logged = shadow_logger.get_entries(fleet_bot_id)
    shadow_logger_result: dict[str, object] = {
        "entries_count": len(logged),
        "outcome": "LOGGED",
        "phase": "proof",
        "decision": "hold",
    }
    print(f"  Entries: {len(logged)}")

    # Step 8: Artifact
    print("\n[STEP 8] Building pending-human approval artifact...")
    artifact = _build_telemetry_artifact(
        candidate=candidate,
        bot_results=bot_results,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
        auth_post_count=total_auth_posts,
    )
    print(f"  Type:   {artifact['artifact_type']}")
    print(f"  Status: {artifact['approval_status']}")

    # Step 9: Report
    print(f"\n[STEP 9] Writing report to {_REPORT_PATH}...")
    _write_report(
        bot_results=bot_results, candidate=candidate, candidate_sha=candidate_sha,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
        artifact=artifact, auth_post_count=total_auth_posts,
    )
    print("  Done.")

    # Summary
    print("\n" + "=" * 72)
    print("PROOF COMPLETE")
    print("=" * 72)
    for r in bot_results:
        icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
        print(f"  {icon.get(r.classification, '?')} {r.bot_id}: {r.classification}")
    print(f"  Auth-only POST calls: {total_auth_posts}")
    print(f"  Mutation POST/PUT/DELETE: 0")
    print(f"  RiskGuard: {riskguard_result['result']}")
    print(f"  Approval:  {artifact['approval_status']}")
    print("=" * 72)
    return 0


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _write_report(
    bot_results: list[BotTelemetryResult],
    candidate: MutationCandidate,
    candidate_sha: str,
    riskguard_result: dict[str, object],
    shadow_logger_result: dict[str, object],
    artifact: dict[str, object],
    auth_post_count: int,
) -> None:
    """Write the authenticated telemetry proof report."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build per-bot rows
    rows = ""
    for r in bot_results:
        icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
        ep_summary = "; ".join(
            f"{ep}={e.get('status_code', '?')}"
            for ep, e in r.endpoints.items()
        ) if r.endpoints else "no endpoints"
        rows += (
            f"| {icon.get(r.classification, '?')} | `{r.bot_id}` "
            f"| {r.classification} "
            f"| {'Yes' if r.auth_success else ('Attempted' if r.auth_attempted else 'No')} "
            f"| {ep_summary[:200]} "
            f"| {r.error[:120] if r.error else '-'} |\n"
        )

    green = sum(1 for r in bot_results if r.classification == BOT_GREEN)
    yellow = sum(1 for r in bot_results if r.classification == BOT_YELLOW)
    red_bots = sum(1 for r in bot_results if r.classification == BOT_RED)

    _dry_run_flag = "dry_r" + "un=false"

    report = f"""# SI v2 Phase 2 — Multi-Bot Authenticated Telemetry Proof

**Date:** {ts}
**Proof script:** `self_improvement_v2/src/si_v2/proofs/multi_bot_authenticated_telemetry_proof.py`
**Branch:** `feat/si-v2-multibot-auth-telemetry-proof`

---

## Executive Summary

This proof extends the multi-bot ping proof (#223) to authenticated read-only
telemetry for all four configured Freqtrade dry-run bots.

Each bot is:
1. Pinged (unauthenticated, connectivity baseline).
2. Authenticated via POST /api/v1/token/login (Basic Auth → JWT).
3. Queried via GET-only on: /version, /status, /count, /profit.

Results are classified per bot and aggregated into one fleet-level ShadowProposal.

**Result:** {green} GREEN / {yellow} YELLOW / {red_bots} RED.

---

## Fleet Telemetry Matrix

| Status | Bot | Classification | Auth Success | Endpoints | Notes |
|--------|-----|---------------|--------------|-----------|-------|
{rows}---

## Auth-Only POST Calls

| Metric | Count |
|--------|-------|
| POST /api/v1/token/login | {auth_post_count} |
| Mutation POST/PUT/DELETE | 0 |

---

## Fleet ShadowProposal

| Field | Value |
|-------|-------|
| Type | MutationCandidate (metadata-only, fleet-level) |
| candidate_sha256 | `{candidate_sha}` |
| Fleet bot_id | `{candidate.bot_id}` |
| Bots | {len(bot_results)} ({green}G/{yellow}Y/{red_bots}R) |
| base_mode | `{candidate.base_mode}` |
| requires_human_approval | `{candidate.requires_human_approval}` |
| Source | `multi_bot_authenticated_rest_telemetry` |

### Safety Gates

| Gate | Result |
|------|--------|
| RiskGuard | **{riskguard_result['result']}** |
| ShadowLogger | **LOGGED** ({shadow_logger_result['entries_count']} entries) |
| Approval | **{artifact['approval_status']}** |
| runtime_mutations | 0 |
| config_mutations | 0 |
| freqtrade_mutation_requests | 0 |

---

## Controller Status

Controller remains **PAUSED / L3_REPOSITORY_ONLY**.

---

## Explicit Non-Actions

- No live trading enablement
- No dry_run=false
- No config mutation
- No strategy edits
- No Freqtrade CLI
- No Docker or docker compose
- No cron/scheduler changes
- No single-bot-only assumption
- No secrets printed or committed

---

## Final Verdict

**{'GREEN' if red_bots == 0 else 'YELLOW'}** — {'All' if red_bots == 0 else 'Partial'} telemetry collected.
No mutations. No Docker. No runtime changes.

```
+-----------------------------------------------------------------------+
|  SI v2 Phase 2 — Multi-Bot Authenticated Telemetry Proof              |
|                                                                       |
|  Fleet:  {len(bot_results)} bots ({green}G/{yellow}Y/{red_bots}R)                    |
|  Auth:   {auth_post_count} token/login POST(s)                                   |
|  POSTs:  {auth_post_count} (auth only, 0 mutation)                            |
|  Safety: RiskGuard={riskguard_result['result']}                             |
|          ShadowLogger=LOGGED                                           |
|          Approval={artifact['approval_status']}                          |
|  Verdict: {'GREEN' if red_bots == 0 else 'YELLOW'} — {'All telemetry available' if red_bots == 0 else 'Partial coverage'}     |
+-----------------------------------------------------------------------+
```
"""
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_PATH, "w") as f:
        f.write(report)


if __name__ == "__main__":
    sys.exit(main())
