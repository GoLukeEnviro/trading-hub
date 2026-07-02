# Live Canary Transition Approval

**Marker:** `APPROVED_LIVE_CANARY_TRANSITION`
**Date:** 2026-07-02
**Author:** Luke (GoLukeEnviro)
**Status:** Active — expires 2026-07-09

---

## Approval

I hereby approve the transition to live canary mode.

This approval authorizes the system to prepare for live canary activation
(phases C1–C4). It does **not** authorize actual live execution — that
requires a separate `APPROVED_EXECUTE_LIVE_CANARY` marker.

---

## Track B Evidence

The following Track B phases are complete and verified:

| Phase | Description | Evidence |
|-------|-------------|----------|
| B1 | Live Readiness Evidence Audit | PR #429 merged |
| B2 | Production Risk Limits Spec | PR #430 merged |
| B3 | Incident Response and Go-Live Runbooks | PR #431 merged |
| B4 | Production Alerting Readiness Gate | PR #432 merged |

---

## Scope

- **Bot:** `freqtrade-freqforge-canary` (canary bot only)
- **Exchange:** Bitget (existing dry-run exchange)
- **Capital:** 500 USDT max (per B2 limits)
- **Max open trades:** 3 (per B2 limits)
- **Duration:** Until superseded or expired (7 days)

---

## Constraints

- No live execution without a separate `APPROVED_EXECUTE_LIVE_CANARY` marker.
- All B2 risk limits apply.
- Kill switch must be `NORMAL` at activation time.
- Emergency stop script must be tested before activation.
- Operator must be on-call and reachable via Telegram.

---

## Expiry

This approval expires **2026-07-09** (7 days from issuance). After expiry,
a new `APPROVED_LIVE_CANARY_TRANSITION` marker must be issued before any
live canary preparation can proceed.
