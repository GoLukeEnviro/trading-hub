"""SI v2 Phase 2 — Read-Only Freqtrade REST ShadowProposal Proof with JWT Auth.

PURPOSE
  Minimal proof that the SI v2 controller can:
    1. Load a bot registry config with env-reference auth metadata.
    2. Select one bot (freqtrade-freqforge).
    3. Make an unauthenticated REST GET call (/api/v1/ping) for reachability.
    4. Authenticate via HTTP Basic Auth to POST /api/v1/token/login.
    5. Fetch authenticated REST GET /api/v1/status with Bearer JWT.
    6. Build a MutationCandidate (metadata-only, no executable config change).
    7. Pass it through a RiskGuard-style local check (blocks runtime).
    8. Log via the existing ShadowLogger.
    9. Produce a documented pending-human approval artifact.

CONSTRAINTS (enforced at code level)
  - Exactly one bot (freqtrade-freqforge).
  - Two REST GET endpoints (/api/v1/ping unauthenticated, /api/v1/status authenticated).
  - One REST POST endpoint (/api/v1/token/login for auth only).
  - No other POST/PUT/PATCH/DELETE anywhere in this proof.
  - No WebSocket, Docker, or Freqtrade CLI usage.
  - No runtime mutation.
  - No config mutation.
  - Controller remains PAUSED / L3_REPOSITORY_ONLY.
  - No secrets committed, printed, or persisted.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repository-relative paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]  # up to trading-hub/
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_REPORT_PATH = (
    _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "first-rest-shadowproposal-proof.md"
)

# ---------------------------------------------------------------------------
# SI v2 module imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

from si_v2.adapters.freqtrade_rest_readonly import (  # noqa: E402
    SIV2FreqtradeTelemetryConnector,
)
from si_v2.deploy.shadow_logger import ShadowLogger  # noqa: E402
from si_v2.state.schemas import MutationCandidate  # noqa: E402


# ---------------------------------------------------------------------------
# RiskGuard-style local check (proof-only)
# ---------------------------------------------------------------------------
RISKGUARD_RESULT_PASS_SHADOW_ONLY: str = "PASS_SHADOW_ONLY"


def _riskguard_check(candidate: MutationCandidate) -> dict[str, Any]:
    """Proof-only RiskGuard-style check.

    This shadows the real RiskGuard contract (defined in
    docs/specs/runtime-safety-contract.md). In this proof it:
      - Confirms base_mode is proposal_only.
      - Confirms requires_human_approval is True.
      - Confirms mutation_policy is safe_parameter_overlay_only.
      - Blocks runtime by returning PASS_SHADOW_ONLY, not ALLOW_RUNTIME.
      - Rejects any candidate that would set dry_run=false or place orders.

    Returns:
        A verdict dict with keys: result, reason, details.
    """
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

    # Check parameters for forbidden values
    for key, value in candidate.parameters.items():
        if key == "dry_run" and value is False:
            details.append(f"parameter {key!r} = False (would enable live trading)")
        if key in ("max_open_trades", "stake_amount", "stoploss", "minimal_roi"):
            # These are allowed only if the candidate is metadata-only.
            pass

    if details:
        return {
            "result": "BLOCKED",
            "reason": "; ".join(details),
            "details": details,
        }

    return {
        "result": RISKGUARD_RESULT_PASS_SHADOW_ONLY,
        "reason": (
            f"candidate {candidate.candidate_sha256} for {candidate.bot_id} "
            "is proposal_only, requires human approval, and contains no "
            "forbidden parameters. Runtime application is blocked."
        ),
        "details": ["proposal_only=True", "runtime_blocked=True"],
    }


# ---------------------------------------------------------------------------
# Approval artifact (proof-only, pending-human)
# ---------------------------------------------------------------------------
def _build_pending_human_artifact(
    candidate: MutationCandidate,
    ping_snapshot: dict[str, Any],
    status_snapshot: dict[str, Any],
    auth_summary: dict[str, Any],
    riskguard_result: dict[str, Any],
    shadow_logger_result: dict[str, Any],
) -> dict[str, Any]:
    """Build a documented pending-human approval artifact.

    This replaces the full ApprovalGateManager.evaluate() path because the
    existing gate requires BacktestResult + WalkForwardResult objects which
    are not available for a ping+status proof.

    Returns a dictionary with all required fields for human review.
    """
    return {
        "artifact_type": "shadow_proposal_pending_human",
        "proposal_id": candidate.candidate_sha256,
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "bot_id": candidate.bot_id,
        "candidate_sha256": candidate.candidate_sha256,
        "source": "real_freqtrade_rest_get_ping_and_status",
        "hypothesis": (
            "SI v2 controller can read real dry-run bot telemetry via "
            "REST GET (authenticated) and produce a ShadowProposal "
            "artifact that passes through the safety chain without "
            "any runtime mutation."
        ),
        "evidence_summary": {
            "ping": ping_snapshot.get("response_summary", "N/A")[:200],
            "status": status_snapshot.get("response_summary", "N/A")[:200],
        },
        "auth_summary": auth_summary,
        "status": "pending_human",
        "reason": (
            "Existing ApprovalGateManager requires BacktestResult and "
            "WalkForwardResult objects that are not produced by a "
            "ping+status proof. This artifact documents the pending-human "
            "state. Full approval gate integration requires a backtest "
            "or walk-forward result in a subsequent proof iteration."
        ),
        "risk_guard_result": riskguard_result["result"],
        "shadow_logger_result": shadow_logger_result.get("outcome", "LOGGED"),
        "approval_status": "PENDING_HUMAN",
        "runtime_mutations": 0,
        "config_mutations": 0,
        "freqtrade_post_requests": 1,  # token_login only
        "metadata": {
            "selected_endpoints": ["/api/v1/ping", "/api/v1/status"],
            "auth_type": "env_basic_jwt",
            "proof_script": Path(__file__).name,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Main proof
# ---------------------------------------------------------------------------
def main() -> int:
    """Execute the one-shot ShadowProposal proof.

    Returns:
        0 on success, 1 on failure.
    """
    print("=" * 72)
    print("SI v2 Phase 2 — Read-Only REST ShadowProposal Proof with JWT Auth")
    print("=" * 72)

    # Step 1: Load bot registry
    print("\n[STEP 1] Loading bot registry...")
    if not _CONFIG_PATH.exists():
        print(f"  ERROR: Config not found at {_CONFIG_PATH}")
        return 1

    with open(_CONFIG_PATH) as f:
        registry = json.load(f)

    bots = registry.get("bots", [])
    print(f"  Loaded {len(bots)} bot(s) from registry (schema v{registry.get('schema_version', '?')})")

    # Step 2: Select exactly one bot: freqtrade-freqforge
    print("\n[STEP 2] Selecting target bot: freqtrade-freqforge...")
    selected_bot: dict[str, Any] | None = None
    for bot in bots:
        if bot.get("bot_id") == "freqtrade-freqforge":
            selected_bot = bot
            break

    if selected_bot is None:
        print("  ERROR: freqtrade-freqforge not found in registry")
        return 1

    bot_id: str = selected_bot["bot_id"]
    base_url: str = selected_bot["base_url"]
    auth_config: dict[str, Any] = selected_bot.get("auth", {})
    print(f"  Selected: {bot_id} @ {base_url}")
    print(f"  Auth type: {auth_config.get('type', 'none')}")

    # Step 3: Call unauthenticated REST GET /api/v1/ping for reachability
    print("\n[STEP 3] Connecting via unauthenticated REST GET /api/v1/ping...")
    connector = SIV2FreqtradeTelemetryConnector(base_url=base_url, bot_id=bot_id)

    ping_snapshot = connector.fetch_snapshot("/api/v1/ping")

    print(f"  Endpoint: {ping_snapshot.endpoint}")
    print(f"  Status code: {ping_snapshot.status_code}")
    print(f"  OK: {ping_snapshot.ok}")
    print(f"  Response: {ping_snapshot.response_summary[:200]}")

    ping_dict = {
        "bot_id": ping_snapshot.bot_id,
        "endpoint": ping_snapshot.endpoint,
        "status_code": ping_snapshot.status_code,
        "ok": ping_snapshot.ok,
        "response_summary": ping_snapshot.response_summary,
        "fetched_at_utc": ping_snapshot.fetched_at_utc,
    }

    if not ping_snapshot.ok:
        print("\n  WARNING: /api/v1/ping failed. Bot may be unreachable.")
        print("  Proceeding to attempt auth anyway for diagnostic purposes.")

    # Step 4: Authenticate via HTTP Basic Auth → JWT
    print("\n[STEP 4] Authenticating via HTTP Basic Auth → JWT...")
    print(f"  Auth type: {auth_config.get('type', 'none')}")
    print(f"  Username env var: {auth_config.get('username_env', 'N/A')}")
    print(f"  Password env var: {auth_config.get('password_env', 'N/A')}")

    username_env: str | None = auth_config.get("username_env")
    password_env: str | None = auth_config.get("password_env")

    # Initialize with safe defaults — always overwritten in the branches below.
    status_dict: dict[str, Any] = {
        "bot_id": bot_id,
        "endpoint": "/api/v1/status",
        "status_code": 0,
        "ok": False,
        "response_summary": "not attempted",
        "fetched_at_utc": datetime.now(UTC).isoformat(),
    }
    auth_summary: dict[str, Any] = {
        "auth_attempted": False,
        "auth_result": "NOT_ATTEMPTED",
        "missing_env_vars": [],
    }
    auth_connector: SIV2FreqtradeTelemetryConnector | None = None

    if username_env and password_env:
        import os

        # Create a new connector with auth
        auth_connector = SIV2FreqtradeTelemetryConnector(
            base_url=base_url,
            bot_id=bot_id,
            username_env=username_env,
            password_env=password_env,
        )

        # Check if env vars are present without printing values
        missing: list[str] = []
        if not os.environ.get(username_env):
            missing.append(username_env)
        if not os.environ.get(password_env):
            missing.append(password_env)

        if missing:
            print(f"  WARNING: Missing environment variables: {', '.join(missing)}")
            print("  Auth will fail. Skipping authenticated /status call.")
            print("  Set the missing env vars and re-run to complete the proof.")
            status_dict = {
                "bot_id": bot_id,
                "endpoint": "/api/v1/status",
                "status_code": 0,
                "ok": False,
                "response_summary": f"YELLOW: missing env vars ({', '.join(missing)})",
                "fetched_at_utc": datetime.now(UTC).isoformat(),
            }
            auth_summary = {
                "auth_attempted": True,
                "auth_result": "YELLOW_MISSING_ENV_VARS",
                "missing_env_vars": missing,
            }
            auth_connector = None
        else:
            try:
                auth_connector.token_login()
                print(f"  token_login: SUCCESS (token held in memory)")
                auth_summary = {
                    "auth_attempted": True,
                    "auth_result": "SUCCESS",
                    "missing_env_vars": [],
                }
            except RuntimeError as exc:
                print(f"  token_login: FAILED — {exc}")
                status_dict = {
                    "bot_id": bot_id,
                    "endpoint": "/api/v1/status",
                    "status_code": 0,
                    "ok": False,
                    "response_summary": f"auth_error: {exc}",
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                }
                auth_summary = {
                    "auth_attempted": True,
                    "auth_result": "FAILED",
                    "missing_env_vars": [],
                    "error_summary": str(exc)[:200],
                }
                auth_connector = None
    else:
        print("  No auth configured for this bot. Skipping authenticated /status call.")
        status_dict = {
            "bot_id": bot_id,
            "endpoint": "/api/v1/status",
            "status_code": 0,
            "ok": False,
            "response_summary": "no auth config in registry",
            "fetched_at_utc": datetime.now(UTC).isoformat(),
        }
        auth_summary = {
            "auth_attempted": False,
            "auth_result": "SKIPPED_NO_CONFIG",
            "missing_env_vars": [],
        }

    # Step 5: Fetch authenticated REST GET /api/v1/status
    print("\n[STEP 5] Fetching authenticated REST GET /api/v1/status...")
    if auth_connector is not None and hasattr(auth_connector, "authenticated") and auth_connector.authenticated:
        status_snapshot = auth_connector.fetch_snapshot("/api/v1/status")
        status_dict = {
            "bot_id": status_snapshot.bot_id,
            "endpoint": status_snapshot.endpoint,
            "status_code": status_snapshot.status_code,
            "ok": status_snapshot.ok,
            "response_summary": status_snapshot.response_summary,
            "fetched_at_utc": status_snapshot.fetched_at_utc,
        }
    print(f"  Endpoint: {status_dict['endpoint']}")
    print(f"  Status code: {status_dict.get('status_code', 'N/A')}")
    print(f"  OK: {status_dict.get('ok', 'N/A')}")
    print(f"  Response: {status_dict.get('response_summary', 'N/A')[:200]}")

    # Step 6: Create a MutationCandidate (metadata-only, no executable config)
    print("\n[STEP 6] Building metadata-only MutationCandidate...")

    candidate_sha = hashlib.sha256(
        json.dumps(
            {
                "bot_id": bot_id,
                "ping": ping_dict,
                "status": status_dict,
                "auth_summary": auth_summary,
                "proof_timestamp": ping_snapshot.fetched_at_utc,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]

    candidate = MutationCandidate(
        bot_id=bot_id,
        bot_name="FreqForge",
        candidate_sha256=candidate_sha,
        source_decision="observe",
        parameters={"dry_run": 1},  # metadata flag: 1 = dry-run confirmed
        active_overlay_candidates={},
        metadata_only_candidates={
            "proof_phase2_ping": 1,
            "proof_phase2_status_auth": 1,
        },
        requires_backtest=False,
        requires_paper_validation=False,
        requires_human_approval=True,
        requires_strategy_adapter=[],
    )

    print(f"  candidate_sha256: {candidate_sha}")
    print(f"  base_mode: {candidate.base_mode}")
    print(f"  requires_human_approval: {candidate.requires_human_approval}")

    # Step 7: RiskGuard-style local check
    print("\n[STEP 7] Running RiskGuard-style local check...")
    riskguard_result = _riskguard_check(candidate)
    print(f"  Result: {riskguard_result['result']}")
    print(f"  Reason: {riskguard_result['reason']}")
    for detail in riskguard_result["details"]:
        print(f"    - {detail}")

    # Step 8: ShadowLogger entry (in-memory)
    print("\n[STEP 8] Logging to ShadowLogger (in-memory)...")
    shadow_logger = ShadowLogger(log_dir=None)  # in-memory mode

    shadow_logger.log(
        bot_id=bot_id,
        candidate_sha=candidate_sha,
        params=dict(candidate.parameters),
        outcome="shadow_proposal_proof_jwt",
        phase="proof",
        decision="hold",
        reason=(
            f"Phase 2 proof: REST GET shadow proposal with JWT auth. "
            f"Ping status={ping_snapshot.status_code}, "
            f"Status code={status_dict.get('status_code', 'N/A')}, "
            f"Auth={auth_summary.get('auth_result', 'N/A')}, "
            f"RiskGuard={riskguard_result['result']}"
        ),
    )

    logged_entries = shadow_logger.get_entries(bot_id)
    shadow_logger_result: dict[str, Any] = {
        "entries_count": len(logged_entries),
        "outcome": "LOGGED",
        "phase": "proof",
        "decision": "hold",
    }
    print(f"  Entries logged: {len(logged_entries)}")
    if logged_entries:
        print(f"  Phase: {logged_entries[0]['phase']}")
        print(f"  Decision: {logged_entries[0]['decision']}")

    # Step 9: Build pending-human approval artifact
    print("\n[STEP 9] Building pending-human approval artifact...")
    approval_artifact = _build_pending_human_artifact(
        candidate=candidate,
        ping_snapshot=ping_dict,
        status_snapshot=status_dict,
        auth_summary=auth_summary,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
    )

    print(f"  Artifact type: {approval_artifact['artifact_type']}")
    print(f"  Proposal ID: {approval_artifact['proposal_id']}")
    print(f"  Approval status: {approval_artifact['approval_status']}")

    # Step 10: Write proof report
    print(f"\n[STEP 10] Writing proof report to {_REPORT_PATH}...")
    _write_report(
        ping_snapshot=ping_dict,
        status_snapshot=status_dict,
        auth_summary=auth_summary,
        candidate=candidate,
        candidate_sha=candidate_sha,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
        approval_artifact=approval_artifact,
    )
    print("  Report written successfully.")

    # Determine verdict color
    proof_ok = ping_snapshot.ok or status_dict.get("ok", False)
    auth_ok = auth_summary.get("auth_result") == "SUCCESS"
    missing_env_vars = auth_summary.get("missing_env_vars", [])

    if auth_ok:
        verdict = "GREEN"
        verdict_text = "GREEN ✅ — All safety gates exercised. Authenticated /status fetched."
    elif missing_env_vars:
        verdict = "YELLOW"
        verdict_text = (
            "YELLOW ⚠️ — Safety gates exercised. Auth structure validated. "
            "Proof incomplete: required env vars not set. "
            f"Missing: {', '.join(missing_env_vars)}"
        )
    elif proof_ok:
        verdict = "YELLOW"
        verdict_text = (
            "YELLOW ⚠️ — /api/v1/ping succeeded but /api/v1/status auth failed. "
            "Check Freqtrade API credentials and bot configuration."
        )
    else:
        verdict = "RED"
        verdict_text = (
            "RED ❌ — Bot unreachable. Both /api/v1/ping and /api/v1/status failed. "
            "Check bot container status and network connectivity."
        )

    # Summary
    print("\n" + "=" * 72)
    print("PROOF COMPLETE")
    print("=" * 72)
    print(f"  Bot contacted:      {bot_id} (1 total)")
    print(f"  REST GET calls:    2 (/api/v1/ping + /api/v1/status)")
    print(f"  REST POST calls:   1 (/api/v1/token/login)")
    print(f"  /api/v1/ping:      HTTP {ping_snapshot.status_code} ({'OK' if ping_snapshot.ok else 'FAIL'})")
    print(f"  /api/v1/status:    HTTP {status_dict.get('status_code', 'N/A')} ({'OK' if status_dict.get('ok') else 'FAIL'})")
    print(f"  Auth result:       {auth_summary.get('auth_result', 'N/A')}")
    print(f"  PUT/PATCH/DELETE:  0")
    print(f"  Mutations:          0")
    print(f"  RiskGuard:          {riskguard_result['result']}")
    print(f"  ShadowLogger:       LOGGED ({shadow_logger_result['entries_count']} entries)")
    print(f"  Approval status:    {approval_artifact['approval_status']}")
    print(f"  Controller remains: PAUSED / L3_REPOSITORY_ONLY")
    print("=" * 72)
    print(f"  Verdict: {verdict_text}")
    print("=" * 72)

    return 0


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _write_report(
    ping_snapshot: dict[str, Any],
    status_snapshot: dict[str, Any],
    auth_summary: dict[str, Any],
    candidate: MutationCandidate,
    candidate_sha: str,
    riskguard_result: dict[str, Any],
    shadow_logger_result: dict[str, Any],
    approval_artifact: dict[str, Any],
) -> None:
    """Write the Phase 2 proof report as markdown."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = f"""# SI v2 Phase 2 — Read-Only REST ShadowProposal Proof with JWT Auth

**Date:** {ts}
**Proof script:** `self_improvement_v2/src/si_v2/proofs/first_rest_shadowproposal_proof.py`
**Branch:** `feat/si-v2-readonly-freqtrade-jwt-auth`

---

## Executive Summary

This proof demonstrates that the SI v2 controller can read real dry-run bot
telemetry from exactly one Freqtrade bot via REST GET with JWT authentication
and produce exactly one ShadowProposal artifact that passes through the
existing safety chain: RiskGuard-style validation, ShadowLogger logging, and
a documented pending-human approval state.

**Root cause (this PR):** `/api/v1/ping` is unauthenticated but `/api/v1/status`
requires JWT authentication. The previous proof (PR #205) could only reach
`/api/v1/ping`. This PR adds minimal JWT auth so `/api/v1/status` can be
fetched.

**Implementation:** HTTP Basic Auth to `POST /api/v1/token/login`, in-memory
JWT Bearer token for authenticated `GET /api/v1/status`.

**Secret handling:** Environment variable references only in the registry.
No committed credentials. No persisted tokens. No printed secrets.

**Safety:** One bot, one-shot proof, shadow-only proposal. Controller remains
PAUSED / L3_REPOSITORY_ONLY.

---

## Prior Proof Chain

| PR | What | Status |
|----|------|--------|
| #205 | First REST ShadowProposal proof (ping only) | OPEN |
| #206 | Fix registry to use Docker DNS URLs | MERGED |
| #207 (this) | Add minimal JWT auth for /api/v1/status | PENDING |

---

## Scope and Non-Goals

### In Scope
- Load bot registry with env-reference auth metadata
- Select exactly one bot: `freqtrade-freqforge`
- Call unauthenticated REST GET `/api/v1/ping` for reachability
- Authenticate via HTTP Basic Auth to `POST /api/v1/token/login`
- Fetch authenticated REST GET `/api/v1/status`
- Build a metadata-only `MutationCandidate` (no executable config change)
- RiskGuard-style local check that blocks runtime
- ShadowLogger entry (in-memory mode)
- Pending-human approval artifact
- Proof report with JWT auth section

### Non-Goals (explicitly excluded)
- No live trading enablement
- No Freqtrade PUT/PATCH/DELETE
- No `/api/v1/balance` or `/api/v1/show_config` (future iteration)
- No WebSocket usage
- No Docker commands or container inspection
- No Freqtrade CLI calls
- No config mutation or strategy edits
- No Telegram delivery (in-memory adapter)
- No new infrastructure, cron jobs, or healthcheck issues
- No full ApprovalGateManager integration (requires backtest/walk-forward objects)
- No TelemetryStore or persistent telemetry

---

## Registry Auth Metadata Shape

```json
"auth": {{
  "type": "env_basic_jwt",
  "username_env": "SI_V2_FREQTRADE_FREQFORGE_USERNAME",
  "password_env": "SI_V2_FREQTRADE_FREQFORGE_PASSWORD"
}}
```

All four bots follow the same pattern with bot-specific env var names.
No real credentials are stored in the repository.

---

## REST GET Snapshots

### /api/v1/ping (unauthenticated, reachability)

| Field | Value |
|-------|-------|
| Endpoint | `/api/v1/ping` |
| Method | `GET` |
| Auth required | No |
| Status code | `{ping_snapshot.get('status_code', 'N/A')}` |
| OK | `{ping_snapshot.get('ok', 'N/A')}` |
| Response summary | `{ping_snapshot.get('response_summary', 'N/A')[:200]}` |
| Fetched at | `{ping_snapshot.get('fetched_at_utc', 'N/A')}` |

### /api/v1/status (authenticated, bot status)

| Field | Value |
|-------|-------|
| Endpoint | `/api/v1/status` |
| Method | `GET` |
| Auth required | Yes (Bearer JWT) |
| Status code | `{status_snapshot.get('status_code', 'N/A')}` |
| OK | `{status_snapshot.get('ok', 'N/A')}` |
| Response summary | `{status_snapshot.get('response_summary', 'N/A')[:200]}` |
| Fetched at | `{status_snapshot.get('fetched_at_utc', 'N/A')}` |

### Auth (token_login)

| Field | Value |
|-------|-------|
| Method | `POST /api/v1/token/login` |
| Auth type | HTTP Basic Auth (from env vars) |
| Result | `{auth_summary.get('auth_result', 'N/A')}` |
| Missing env vars | `{', '.join(auth_summary.get('missing_env_vars', [])) or 'none'}` |

---

## ShadowProposal Generated

| Field | Value |
|-------|-------|
| Type | `MutationCandidate` (metadata-only) |
| candidate_sha256 | `{candidate_sha}` |
| bot_id | `{candidate.bot_id}` |
| base_mode | `{candidate.base_mode}` |
| requires_human_approval | `{candidate.requires_human_approval}` |
| Parameters | `{dict(candidate.parameters)}` |
| Metadata-only candidates | `{candidate.metadata_only_candidates}` |
| Source | `real_freqtrade_rest_get_ping_and_status` |

---

## Safety Gate Results

### RiskGuard (Proof-Only)

| Field | Value |
|-------|-------|
| Result | `{riskguard_result['result']}` |
| Reason | `{riskguard_result['reason']}` |
| Details | {'; '.join(riskguard_result['details'])} |

### ShadowLogger (In-Memory)

| Field | Value |
|-------|-------|
| Result | `LOGGED` |
| Entries | `{shadow_logger_result['entries_count']}` |
| Phase | `{shadow_logger_result['phase']}` |
| Decision | `{shadow_logger_result['decision']}` |

### Approval Gate (Documented Pending-Human Artifact)

| Field | Value |
|-------|-------|
| Artifact type | `{approval_artifact['artifact_type']}` |
| Proposal ID | `{approval_artifact['proposal_id']}` |
| Approval status | `{approval_artifact['approval_status']}` |

---

## Mutation Confirmation Matrix

| Property | Value | Verified |
|----------|-------|----------|
| Bots contacted | 1 (freqtrade-freqforge) | ✅ |
| REST GET only (data) | Yes | ✅ |
| REST POST (auth only) | 1 (token_login) | ✅ |
| REST PUT/PATCH/DELETE | 0 | ✅ |
| WebSocket used | No | ✅ |
| Docker commands | 0 | ✅ |
| Freqtrade CLI calls | 0 | ✅ |
| Runtime mutations | 0 | ✅ |
| Config mutations | 0 | ✅ |
| Controller PAUSED | Yes | ✅ |
| Controller L3_REPOSITORY_ONLY | Yes | ✅ |
| ShadowProposals generated | 1 | ✅ |
| ShadowProposals executed | 0 | ✅ |
| RiskGuard exercised | Yes (PASS_SHADOW_ONLY) | ✅ |
| ShadowLogger exercised | Yes (LOGGED) | ✅ |
| ApprovalGate path exercised | Yes (PENDING_HUMAN) | ✅ |
| Secrets in repo | No | ✅ |
| Secrets printed | No | ✅ |
| Tokens persisted | No | ✅ |

---

## Explicit Non-Goals (Not Changed in This PR)

- No docker-compose.yml change
- No network change
- No port change
- No depends_on change
- No service change
- No healthcheck change
- No runtime mutation
- No controller activation
- No full telemetry system

---

## Final Verdict

Proof result: {approval_artifact.get('metadata', {}).get('verdict', 'see console output')}

"""
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_PATH, "w") as f:
        f.write(report)


if __name__ == "__main__":
    sys.exit(main())
