# Bot Roles & Shadow Architecture Spec

**Project:** trading-hub  
**Version:** 1.0  
**Date:** 2026-06-07  
**Status:** Active

---

## 1. Core Principles

- Separate signal generation, risk management, and execution into distinct layers.
- Every bot has exactly one role. Roles do not overlap at runtime.
- Shadow mode is read-only. It never influences execution.
- All mode transitions are logged to the Shadowlock ledger before taking effect.

---

## 2. Bot Registry

| Bot | Role | Mode | Priority | Strategy Path |
|---|---|---|---|---|
| FreqForge | Core Fleet | live/dry | 1 | freqforge/user_data/strategies/ |
| FreqForge-Canary | Core Safety | dry/shadow | 2 | freqforge-canary/user_data/strategies/ |
| Regime-Hybrid | Experimental | dry/shadow | 3 | freqtrade/bots/regime-hybrid/user_data/strategies/ |
| FreqAI-Rebel | Research-Only | shadow | 4 | freqtrade/bots/freqai-rebel/user_data/strategies/ |

---

## 3. Mode Definitions

### live
- Real capital deployed.
- All trades execute against the live exchange.
- Risk manager is active and enforces drawdown limits.
- Only FreqForge is permitted in live mode.

### dry
- Paper trading. No real capital.
- Signals are generated and executed against a simulated balance.
- Used for forward-testing before live promotion.

### shadow
- Signals are generated but never executed.
- Output is logged to Shadowlock for comparison against dry/live.
- Used for drift detection and canary validation.
- Shadow mode must never write to the exchange API.

### zombie
- Bot container is running but emitting no signals or heartbeats.
- Detected by Shadowlock silence_event after missed interval.
- Triggers an alert; requires manual investigation before mode change.

---

## 4. Mode Transition Rules

```
shadow -> dry:   Requires 14-day shadow run with PF >= 1.3 and no drift_events.
dry -> live:     Requires 30-day dry run with PF >= 1.5, WR >= 50%, max_DD < 10%.
live -> dry:     Triggered by max_DD breach or manual override.
any -> zombie:   Automatic; detected by Shadowlock silence_event.
zombie -> any:   Manual only; requires root-cause sign-off in docs/decisions/.
```

---

## 5. Shadow Comparison Targets

| Comparison | Source A | Source B | Drift Threshold |
|---|---|---|---|
| Signal intent vs execution | Shadow signals | Dry trades | 10% rel. PF delta / 7d |
| Shadow vs Dry PnL | Shadow PnL | Dry PnL | 10% rel. PF delta / 7d |
| Shadow vs Live PnL | Shadow PnL | Live PnL | 10% rel. PF delta / 7d |

If drift exceeds threshold: emit `drift_event` to Shadowlock, surface in next periodic summary.

---

## 6. Risk Manager Integration

- `fleet_risk_manager.py` is shared across all bots.
- It enforces:
  - Global max open trades across the fleet.
  - Per-bot drawdown limits.
  - Pair blacklist propagation.
- Any change to `fleet_risk_manager.py` is treated as a HIGH-plausibility profitability parameter change by the Forensics Agent.

---

## 7. Lifecycle Ownership

| Event | Owner |
|---|---|n| Mode transition decision | Human operator |
| Mode transition logging | Shadowlock Writer |
| Drift detection | Shadowlock Writer |
| Silence detection | Shadowlock Writer |
| Recovery proposal | Profitability Forensics Agent |
| Episode execution | Self-Improvement Orchestrator |

---

## 8. Related Specs

- `docs/specs/shadowlock-writer-spec.md` — logging and audit layer
- `docs/specs/profitability-forensics-agent-spec.md` — historical reconstruction
- `ORCHESTRATOR_CHARTER.md` — self-improvement vision and charter
