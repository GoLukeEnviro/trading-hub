# Live Canary Execution Approval

**Marker:** `APPROVED_EXECUTE_LIVE_CANARY`
**Date:** 2026-07-02
**Author:** Luke (GoLukeEnviro)
**Status:** Active — expires 2026-07-09

---

## Approval

I hereby approve the controlled live canary activation ceremony for
`freqtrade-freqforge-canary` per the C2 config plan (PR #434).

This approval is **limited** to:

- The controlled ceremony defined by Track C3: activation, snapshot, rollback,
  and measurement-start procedures.
- The canary bot `freqtrade-freqforge-canary` only — not the full fleet.

This approval does **not** authorize:

- Full fleet rollout.
- Strategy mutation, pair expansion, or risk-parameter changes.
- Live capital beyond the B2-defined limits (500 USDT max).

---

## Prerequisites Confirmed

| Prerequisite | Status | Evidence |
|---|---|---|
| C1 — Live Canary Approval Gate | ✅ Merged | PR #433 |
| C2 — Live Canary Config Plan | ✅ Merged | PR #434 |
| B2 — Production Risk Limits | ✅ Merged | PR #430 |
| B4 — Production Alerting Readiness | ✅ Merged | PR #432 |
| `APPROVED_LIVE_CANARY_TRANSITION` | ✅ Present | Active until 2026-07-09 |

---

## Constraints

1. **No live orders may be placed** by this approval alone — the ceremony
   is dry-run preparation for live canary mode.
2. All B2 risk limits apply at all times.
3. Kill switch must be `NORMAL` at activation time.
4. Rollback path must be verified before activation.
5. Operator must be on-call and reachable via Telegram during activation.

---

## Expiry

This approval expires **2026-07-09** (7 days from issuance), in alignment
with the transition marker expiry. After expiry, a new
`APPROVED_EXECUTE_LIVE_CANARY` marker must be issued before any live canary
activation ceremony can proceed.
