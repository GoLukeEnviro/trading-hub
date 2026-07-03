# Live Canary Rollback Approval

**Marker:** `APPROVED_LIVE_CANARY_ROLLBACK`
**Date:** 2026-07-03
**Author:** Luke (GoLukeEnviro)

---

I approve the controlled rollback of `freqtrade-freqforge-canary` to dry-run mode per the C3 rollback plan documented in `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json`.

## Decision Context

- **C4 decision:** `ROLLBACK_RECOMMENDED` — validated by #438 (C4 Decision Triage)
- **C3 rollback plan:** Reviewed and substantively complete per #440 (C3 Rollback Plan Review Gate)
- **Triggering metric:** `max_drawdown_pct = 82.79%` exceeds critical threshold of 20.0%
- **Secondary metric:** `sharpe_ratio = 0.03` borderline (min: 0.5)
- **Measurement window:** 2026-06-18 to 2026-07-02 — LINK/USDT -9.33% loss on 2026-06-24 confirmed inside window

## Rollback Scope

- **Target:** `freqtrade-freqforge-canary` only
- **No fleet rollout**
- **No pair expansion**
- **No strategy mutation**
- **No exchange key deployment**

## Required Post-Rollback Steps

1. Verify dry-run operation (logs, DB, API health)
2. Reset kill switch to NORMAL
3. File post-mortem report in `docs/incidents/`
4. Do not start D1 without C4 KEEP + `APPROVED_LIVE_FLEET_ROLLOUT`
