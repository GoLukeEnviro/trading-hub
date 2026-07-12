# Architecture Decision Records

This directory contains decision records (ADRs) for significant architectural
choices made in the Trading Hub project.

---

## Index

| Date | Title | Status |
|------|-------|--------|
| 2026-05-14 | [SOUL.md / AGENTS.md Sync](2026-05-14-soul-agents-sync.md) | ✅ Final |
| 2026-06-10 | [Watchdog Ownership Boundary](ADR-2026-06-10-watchdog-ownership.md) | ✅ Final |
| 2026-06-27 | [Controlled Self-Improvement — Human-Gated Apply](ADR-2026-06-27-controlled-self-improvement-human-gated-apply.md) | ✅ Superseded by ADR-2026-07-01 |
| 2026-06-27 | [SI-v2 Restart with Overlay — Runtime Proof](ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof.md) | ✅ Final |
| 2026-07-01 | [SI-v2 Autonomous Dry-Run Loop — Live Target](ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md) | ✅ Final — current SI-v2 policy |
| 2026-07-11 | [Hermes Root Runtime Authority](ADR-2026-07-11-hermes-root-runtime-authority.md) | ✅ Active |
| 2026-07-11 | [HermesTrader R7A Dry-Run-Topology](ADR-2026-07-11-hermes-r7a-dryrun-topology.md) | ✅ Accepted |

## Approval Markers

| Marker | Scope | Status | Location |
|--------|-------|--------|----------|
| `APPROVED_EXECUTE_LIVE_CANARY` | Execute live canary activation ceremony | ✅ Used (C3) | `APPROVED_EXECUTE_LIVE_CANARY.md` |
| `APPROVED_LIVE_CANARY_TRANSITION` | Authorize live canary transition | ✅ Used (C1–C3) | `APPROVED_LIVE_CANARY_TRANSITION.md` |
| `APPROVED_LIVE_CANARY_ROLLBACK` | Authorize live canary rollback | ✅ Used (C4) | `APPROVED_LIVE_CANARY_ROLLBACK.md` |
| `APPROVED_LIVE_FLEET_ROLLOUT` | Authorize live fleet rollout (D1) | ❌ Missing — D1 BLOCKED | — |

## Format

Each ADR follows this structure:

- **Title** — What was decided
- **Date** — When the decision was made
- **Status** — Final, Superseded, or Deprecated
- **Context** — Why the decision was needed
- **Decision** — What was decided
- **Consequences** — What this decision implies
- **Related** — Links to related ADRs or issues
