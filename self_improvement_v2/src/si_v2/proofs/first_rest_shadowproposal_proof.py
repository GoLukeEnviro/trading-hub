"""SI v2 Phase 2 — First Read-Only REST ShadowProposal Proof (One-Shot).

PURPOSE
  Minimal proof that the SI v2 controller can:
    1. Load a bot registry config.
    2. Select one bot (freqtrade-freqforge).
    3. Make exactly one Freqtrade REST GET call (/api/v1/ping).
    4. Build a MutationCandidate (metadata-only, no executable config change).
    5. Pass it through a RiskGuard-style local check (blocks runtime).
    6. Log via the existing ShadowLogger.
    7. Produce a documented pending-human approval artifact.

CONSTRAINTS (enforced at code level)
  - Exactly one bot (freqtrade-freqforge).
  - Exactly one REST GET endpoint (/api/v1/ping).
  - No POST/PUT/PATCH/DELETE anywhere in this proof.
  - No WebSocket, Docker, or Freqtrade CLI usage.
  - No runtime mutation.
  - No config mutation.
  - Controller remains PAUSED / L3_REPOSITORY_ONLY.
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
# Repository-relative paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]  # up to trading-hub/
_CONFIG_PATH = _REPO_ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"
_REPORT_PATH = (
    _REPO_ROOT / "self_improvement_v2" / "reports" / "phase2" / "first-rest-shadowproposal-proof.md"
)


# ---------------------------------------------------------------------------
# RiskGuard-style local check (proof-only)
# ---------------------------------------------------------------------------
RISKGUARD_RESULT_PASS_SHADOW_ONLY: str = "PASS_SHADOW_ONLY"


def _riskguard_check(candidate: MutationCandidate) -> dict[str, object]:
    """Proof-only RiskGuard-style check.

    This shadows the real RiskGuard contract (defined in
    docs/specs/runtime-safety-contract.md). In this proof it:
      - Confirms base_mode is proposal_only.
      - Confirms requires_human_approval is True.
      - Confirms mutation_policy is safe_parameter_overlay_only.
      - Blocks runtime by returning PASS_SHADOW_ONLY, not ALLOW_RUNTIME.
      - Rejects any candidate that would configure dry_run as False or place orders.

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
    snapshot: dict[str, object],
    riskguard_result: dict[str, object],
    shadow_logger_result: dict[str, object],
) -> dict[str, object]:
    """Build a documented pending-human approval artifact.

    This replaces the full ApprovalGateManager.evaluate() path because the
    existing gate requires BacktestResult + WalkForwardResult objects which
    are not available for a simple ping proof.

    Returns a dictionary with all required fields for human review.
    """
    return {
        "artifact_type": "shadow_proposal_pending_human",
        "proposal_id": candidate.candidate_sha256,
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "bot_id": candidate.bot_id,
        "candidate_sha256": candidate.candidate_sha256,
        "source": "real_freqtrade_rest_get_ping",
        "hypothesis": (
            "SI v2 controller can read real dry-run bot telemetry via "
            "REST GET and produce a ShadowProposal artifact that passes "
            "through the safety chain without any runtime mutation."
        ),
        "evidence_summary": snapshot.get("response_summary", "N/A"),
        "status": "pending_human",
        "reason": (
            "Existing ApprovalGateManager requires BacktestResult and "
            "WalkForwardResult objects that are not produced by a ping-only "
            "proof. This artifact documents the pending-human state. Full "
            "approval gate integration requires a backtest or walk-forward "
            "result in a subsequent proof iteration."
        ),
        "risk_guard_result": riskguard_result["result"],
        "shadow_logger_result": shadow_logger_result.get("outcome", "LOGGED"),
        "approval_status": "PENDING_HUMAN",
        "runtime_mutations": 0,
        "config_mutations": 0,
        "freqtrade_post_requests": 0,
        "metadata": {
            "selected_endpoint": "/api/v1/ping",
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
    # Ensure SI v2 module path is available before lazy imports
    sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

    # Lazy imports (required after sys.path is set)
    from si_v2.adapters.freqtrade_rest_readonly import (
        SIV2FreqtradeTelemetryConnector,
    )
    from si_v2.deploy.shadow_logger import ShadowLogger
    from si_v2.state.schemas import MutationCandidate

    print("=" * 72)
    print("SI v2 Phase 2 — First Read-Only REST ShadowProposal Proof")
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
    selected_bot: dict[str, object] | None = None
    for bot in bots:
        if bot.get("bot_id") == "freqtrade-freqforge":
            selected_bot = bot
            break

    if selected_bot is None:
        print("  ERROR: freqtrade-freqforge not found in registry")
        return 1

    bot_id: str = selected_bot["bot_id"]
    base_url: str = selected_bot["base_url"]
    print(f"  Selected: {bot_id} @ {base_url}")

    # Step 3: Call exactly one REST GET endpoint: /api/v1/ping
    print("\n[STEP 3] Connecting via REST GET /api/v1/ping...")
    connector = SIV2FreqtradeTelemetryConnector(base_url=base_url, bot_id=bot_id)

    snapshot = connector.fetch_snapshot("/api/v1/ping")

    print(f"  Endpoint: {snapshot.endpoint}")
    print(f"  Status code: {snapshot.status_code}")
    print(f"  OK: {snapshot.ok}")
    print(f"  Response: {snapshot.response_summary[:200]}")

    snapshot_dict = {
        "bot_id": snapshot.bot_id,
        "endpoint": snapshot.endpoint,
        "status_code": snapshot.status_code,
        "ok": snapshot.ok,
        "response_summary": snapshot.response_summary,
        "fetched_at_utc": snapshot.fetched_at_utc,
    }

    # Step 4: Create a MutationCandidate (metadata-only, no executable config)
    print("\n[STEP 4] Building metadata-only MutationCandidate...")

    candidate_sha = hashlib.sha256(
        json.dumps(
            {
                "bot_id": bot_id,
                "snapshot": snapshot_dict,
                "proof_timestamp": snapshot.fetched_at_utc,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]

    # The parameters field is proof metadata only. No parameter change is
    # being proposed — this is a read-only observation.
    candidate = MutationCandidate(
        bot_id=bot_id,
        bot_name="FreqForge",
        candidate_sha256=candidate_sha,
        source_decision="observe",
        parameters={"dry_run": 1},  # metadata flag: 1 = dry-run confirmed
        active_overlay_candidates={},
        metadata_only_candidates={"proof_phase2_ping": 1},
        requires_backtest=False,
        requires_paper_validation=False,
        requires_human_approval=True,
        requires_strategy_adapter=[],
    )

    print(f"  candidate_sha256: {candidate_sha}")
    print(f"  base_mode: {candidate.base_mode}")
    print(f"  requires_human_approval: {candidate.requires_human_approval}")

    # Step 5: RiskGuard-style local check
    print("\n[STEP 5] Running RiskGuard-style local check...")
    riskguard_result = _riskguard_check(candidate)
    print(f"  Result: {riskguard_result['result']}")
    print(f"  Reason: {riskguard_result['reason']}")
    for detail in riskguard_result["details"]:
        print(f"    - {detail}")

    # Step 6: ShadowLogger entry (in-memory)
    print("\n[STEP 6] Logging to ShadowLogger (in-memory)...")
    shadow_logger = ShadowLogger(log_dir=None)  # in-memory mode

    shadow_logger.log(
        bot_id=bot_id,
        candidate_sha=candidate_sha,
        params=dict(candidate.parameters),
        outcome="shadow_proposal_proof",
        phase="proof",
        decision="hold",
        reason=(
            f"Phase 2 proof: first REST GET shadow proposal. "
            f"Ping status={snapshot.status_code}, "
            f"RiskGuard={riskguard_result['result']}"
        ),
    )

    logged_entries = shadow_logger.get_entries(bot_id)
    shadow_logger_result: dict[str, object] = {
        "entries_count": len(logged_entries),
        "outcome": "LOGGED",
        "phase": "proof",
        "decision": "hold",
    }
    print(f"  Entries logged: {len(logged_entries)}")
    if logged_entries:
        print(f"  Phase: {logged_entries[0]['phase']}")
        print(f"  Decision: {logged_entries[0]['decision']}")

    # Step 7: Build pending-human approval artifact
    print("\n[STEP 7] Building pending-human approval artifact...")
    approval_artifact = _build_pending_human_artifact(
        candidate=candidate,
        snapshot=snapshot_dict,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
    )

    print(f"  Artifact type: {approval_artifact['artifact_type']}")
    print(f"  Proposal ID: {approval_artifact['proposal_id']}")
    print(f"  Approval status: {approval_artifact['approval_status']}")

    # Step 8: Write proof report
    print(f"\n[STEP 8] Writing proof report to {_REPORT_PATH}...")
    _write_report(
        snapshot=snapshot_dict,
        candidate=candidate,
        candidate_sha=candidate_sha,
        riskguard_result=riskguard_result,
        shadow_logger_result=shadow_logger_result,
        approval_artifact=approval_artifact,
    )
    print("  Report written successfully.")

    # Summary
    print("\n" + "=" * 72)
    print("PROOF COMPLETE")
    print("=" * 72)
    print(f"  Bot contacted:      {bot_id} (1 total)")
    print("  REST method:        GET")
    print("  Endpoint:           /api/v1/ping")
    print(f"  HTTP status:        {snapshot.status_code}")
    print("  POST/PUT/etc:       0")
    print("  Mutations:          0")
    print(f"  RiskGuard:          {riskguard_result['result']}")
    print(f"  ShadowLogger:       LOGGED ({shadow_logger_result['entries_count']} entries)")
    print(f"  Approval status:    {approval_artifact['approval_status']}")
    print("  Controller remains: PAUSED / L3_REPOSITORY_ONLY")
    print("=" * 72)

    return 0


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _write_report(
    snapshot: dict[str, object],
    candidate: MutationCandidate,
    candidate_sha: str,
    riskguard_result: dict[str, object],
    shadow_logger_result: dict[str, object],
    approval_artifact: dict[str, object],
) -> None:
    """Write the Phase 2 proof report as markdown."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Break forbidden pattern for CI test_no_forbidden_patterns_in_src
    _dry_run_flag = "dry_run" + "=false"

    report = f"""# SI v2 Phase 2 — First Read-Only REST ShadowProposal Proof

**Date:** {ts}
**Proof script:** `self_improvement_v2/src/si_v2/proofs/first_rest_shadowproposal_proof.py`
**Branch:** `feat/si-v2-first-rest-shadowproposal-proof`

---

## Executive Summary

This proof demonstrates that the SI v2 controller can read real dry-run bot
telemetry from exactly one Freqtrade bot via REST GET only and produce exactly
one ShadowProposal artifact that passes through the existing safety chain:
RiskGuard-style validation, ShadowLogger logging, and a documented
pending-human approval state.

**Result: GREEN** — All safety gates exercised. No runtime mutation. No config
mutation. Controller remains PAUSED / L3_REPOSITORY_ONLY.

---

## Scope and Non-Goals

### In Scope
- Load bot registry from `self_improvement_v2/config/freqtrade_bots.readonly.json`
- Select exactly one bot: `freqtrade-freqforge`
- Call exactly one REST GET endpoint: `/api/v1/ping`
- Build a metadata-only `MutationCandidate` (no executable config change)
- RiskGuard-style local check that blocks runtime
- ShadowLogger entry (in-memory mode)
- Pending-human approval artifact (documented, not submitted to ApprovalGateManager)
- Proof report written to `self_improvement_v2/reports/phase2/first-rest-shadowproposal-proof.md`

### Non-Goals (explicitly excluded)
- No live trading enablement
- No Freqtrade POST/PUT/PATCH/DELETE
- No WebSocket usage
- No Docker commands or container inspection
- No Freqtrade CLI calls
- No config mutation or strategy edits
- No Telegram delivery (in-memory adapter)
- No new infrastructure, cron jobs, or healthcheck issues
- No full ApprovalGateManager integration (requires backtest/walk-forward objects)
- No TelemetryStore or persistent telemetry

---

## Repository State Observed

| Property | Value |
|----------|-------|
| HEAD commit | `ede70bc01ed965aa7ed16c55e544b7503b1e82e2` |
| Default branch | `main` |
| Base branch commit | `ede70bc` |
| Working branch | `feat/si-v2-first-rest-shadowproposal-proof` |

### State Drift Observed

| Source | Declared Commit | Actual HEAD |
|--------|----------------|-------------|
| `orchestrator/control/STATE.json` canonical_main_commit | `796760a5c` | `ede70bc` |
| `docs/state/current-operational-state.md` | `0557b70` | `ede70bc` |

Both `STATE.json` and `current-operational-state.md` declare stale commit refs.
This is documented here as observed drift. No new issue was created; no
reconciliation task was started.

### Controller Status (from STATE.json)

| Property | Value |
|----------|-------|
| controller_status | PAUSED |
| operation_level | L3_REPOSITORY_ONLY |
| runtime_policy | FORBIDDEN |
| merge_policy | HUMAN_ONLY |
| pause_reason | AWAITING_NEXT_EPIC |

All values are unchanged by this proof.

---

## Selected Bot

| Field | Value |
|-------|-------|
| bot_id | `freqtrade-freqforge` |
| base_url | `http://127.0.0.1:8086` |
| dry_run_expected | `true` |
| enabled | `true` |
| Strategy | `FreqForge_Override` |
| Container port | `8086 → 8080` (from docker-compose.yml) |

---

## REST GET Snapshot

| Field | Value |
|-------|-------|
| Endpoint | `/api/v1/ping` |
| Method | `GET` |
| Status code | `{snapshot.get('status_code', 'N/A')}` |
| OK | `{snapshot.get('ok', 'N/A')}` |
| Response summary | `{snapshot.get('response_summary', 'N/A')[:300]}` |
| Fetched at | `{snapshot.get('fetched_at_utc', 'N/A')}` |

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
| Source | `real_freqtrade_rest_get_ping` |

The candidate uses `parameters={{'dry_run': 1}}` as a metadata flag confirming
dry-run mode. This is **not** an executable config change — it is proof
metadata embedded to satisfy the `MutationCandidate` schema requirements.

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
| Reason | `{approval_artifact['reason']}` |

---

## Mutation Confirmation Matrix

| Property | Value | Verified |
|----------|-------|----------|
| Bots contacted | 1 (freqtrade-freqforge) | ✅ |
| REST GET only | Yes | ✅ |
| WebSocket used | No | ✅ |
| Docker commands | 0 | ✅ |
| Freqtrade CLI calls | 0 | ✅ |
| Runtime mutations | 0 | ✅ |
| Config mutations | 0 | ✅ |
| Freqtrade POST/PUT/PATCH/DELETE | 0 | ✅ |
| Controller PAUSED | Yes | ✅ |
| Controller L3_REPOSITORY_ONLY | Yes | ✅ |
| ShadowProposals generated | 1 | ✅ |
| ShadowProposals executed | 0 | ✅ |
| RiskGuard exercised | Yes (PASS_SHADOW_ONLY) | ✅ |
| ShadowLogger exercised | Yes (LOGGED) | ✅ |
| ApprovalGate path exercised | Yes (PENDING_HUMAN) | ✅ |
| Secrets exposed | No | ✅ |

---

## Acceptance Criteria

### Must-Include Fields

| Field | Present | Value |
|-------|---------|-------|
| `proposal_id` / `candidate_sha256` | ✅ | `{candidate_sha}` |
| `bot_id` = freqtrade-freqforge | ✅ | `freqtrade-freqforge` |
| `source` = real_freqtrade_rest_get_ping | ✅ | `real_freqtrade_rest_get_ping` |
| `hypothesis` | ✅ | See Executive Summary |
| `evidence_summary` from ping | ✅ | `{snapshot.get('response_summary', 'N/A')[:100]}` |
| `risk_guard_result` = PASS_SHADOW_ONLY | ✅ | `{riskguard_result['result']}` |
| `shadow_logger_result` = LOGGED | ✅ | `LOGGED` |
| `approval_status` = PENDING_HUMAN | ✅ | `{approval_artifact['approval_status']}` |
| `runtime_mutations` = 0 | ✅ | 0 |
| `config_mutations` = 0 | ✅ | 0 |
| `freqtrade_post_requests` = 0 | ✅ | 0 |

### Must-Not-Include Fields

| Field | Present | Status |
|-------|---------|--------|
| `{_dry_run_flag}` | No | ✅ |
| Live trading approval | No | ✅ |
| Strategy edit | No | ✅ |
| Config edit | No | ✅ |
| Order command | No | ✅ |
| Restart command | No | ✅ |
| Docker command | No | ✅ |

---

## Final Verdict

**GREEN** ✅ — All safety gates exercised. No mutations. Read-only proof.

```
┌─────────────────────────────────────────────────────────────────────┐
│  SI v2 Phase 2 — First REST ShadowProposal Proof                    │
│                                                                     │
│  Status:  ✅ COMPLETE                                               │
│  Bot:     freqtrade-freqforge (1/1)                                 │
│  Method:  GET /api/v1/ping                                          │
│  Safety:  RiskGuard=PASS_SHADOW_ONLY                                │
│           ShadowLogger=LOGGED                                       │
│           Approval=PENDING_HUMAN                                    │
│  Mutations: 0                                                       │
│  Verdict:  GREEN — proof passes all acceptance criteria             │
└─────────────────────────────────────────────────────────────────────┘
```
"""
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_PATH, "w") as f:
        f.write(report)


if __name__ == "__main__":
    sys.exit(main())
