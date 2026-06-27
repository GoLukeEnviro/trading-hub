# SI-v2 First Canary Apply Preflight — max_open_trades 3→2

**Date:** 2026-06-27  
**Candidate:** `max_open_trades_3_to_2`  
**Target Bot:** `freqtrade-freqforge-canary`  
**Parameter:** `max_open_trades`  
**Change:** `3 → 2`  
**Campaign:** First Controlled Canary Apply — Human-Gated

---

## 1. Candidate Evidence Bundle

### 1.1 Runtime Config Snapshot

Source: `freqforge-canary/user_data/config.json`

```json
{
  "dry_run": true,
  "max_open_trades": 3,
  "strategy": null
}
```

- `dry_run`: **true** ✅ (unconditional gate requirement met)
- `max_open_trades`: **3** ✅ (proven baseline, not None, not absent)
- `config.json` SHA256: `fcbb6f476be09e9e4b52c83108cd9da67504f75f3b43cf12ec72314edbe3bb16`
- `config.json` size: 2259 bytes

### 1.2 SAFE_PARAMETERS Validation

- `max_open_trades` ∈ SAFE_PARAMETERS: **true** ✅
- `validate_safe_parameter("max_open_trades", 2.0)`: **true** ✅
- Allowed range: `(1, 20)` — value 2 is within range

### 1.3 Candidate Compatibility Gate (Gate 9)

- `max_open_trades` present in `pre_apply_config`: **true** ✅
- Current value: `3` (not None) ✅
- Expected baseline `{"max_open_trades": 3}` matches runtime value: **true** ✅
- Gate result: **PASS** — "All overlay keys present in pre_apply_config with proven baselines"

### 1.4 Kill-Switch Status

```json
{
  "mode": "NORMAL",
  "reason": "initial state after PR #373",
  "triggered_by": "orchestrator"
}
```
→ **NORMAL** ✅

### 1.5 RiskGuard Adapter Status

Canonical source: `orchestrator/state/riskguard/riskguard_state.json`

Current state:
- `summary.status`: `ACTIVE`
- `summary.accepted`: `0`
- All pairs: `WATCH_ONLY` (confidence below 0.65 threshold)
- Adapter derived status: **FAIL** (no ACCEPTED pairs)

**Note:** This is a live market condition, not a code issue. The adapter correctly
fail-closes when no pair has ACCEPTED verdict. At apply time, RiskGuard must
derive PASS (≥1 ACCEPTED, 0 BLOCK_ENTRY). This is a **runtime precondition** that
depends on market signals, not on code changes.

### 1.6 Readiness Report (Full)

| Gate | Status | Reason |
|------|--------|--------|
| canary_gate | ✅ PASS | Bot is approved canary |
| safe_parameters_gate | ✅ PASS | All parameter keys and values validated |
| kill_switch_gate | ✅ PASS | Kill-switch mode is NORMAL |
| riskguard_gate | ❌ FAIL | No ACCEPTED pairs (market condition) |
| human_approval_gate | ✅ PASS | requires_human_approval is True |
| token_gate | ❌ BLOCKED | L3 token not set (expected human gate) |
| cooldown_gate | ✅ PASS | Cooldown clear |
| dry_run_gate | ✅ PASS | dry_run is True |
| compatibility_gate | ✅ PASS | All overlay keys present with proven baselines |
| **ready** | **false** | Blocked by riskguard_gate + token_gate |

**Blocking gates:**
1. `riskguard_gate` — market-dependent, will pass when ≥1 pair reaches ACCEPTED
2. `token_gate` — human L3 approval required (by design)

---

## 2. Overlay Path and Expected Content

### 2.1 Expected Overlay Path

```
/home/hermes/projects/trading/freqforge-canary/user_data/overlay_max_open.json
```

Derived from `build_host_overlay_path("freqtrade-freqforge-canary", "max_open_trades_3_to_2")`.

### 2.2 Expected Overlay Content

```json
{
  "max_open_trades": 2,
  "_meta": {
    "candidate_sha": "max_open_trades_3_to_2",
    "created_at_utc": "<ISO timestamp at apply time>",
    "source": "si_v2_controlled_apply_actuator"
  }
}
```

### 2.3 Existing Overlay Files

None. No prior overlay files exist in `freqforge-canary/user_data/`.

---

## 3. Post-Apply Verification Plan

### 3.1 Overlay File Verification

1. Check `overlay_max_open.json` exists at expected path
2. Parse JSON, verify `max_open_trades == 2`
3. Verify `_meta.candidate_sha == "max_open_trades_3_to_2"`
4. Verify `_meta.source == "si_v2_controlled_apply_actuator"`
5. Compute SHA256 of overlay file for audit log

### 3.2 Bot Config Integrity

1. Re-check `config.json` SHA256 matches baseline: `fcbb6f47...`
2. If SHA256 differs → STOP, investigate, consider rollback

### 3.3 Docker Container State

1. Verify `trading-freqtrade-freqforge-canary-1` container status unchanged
2. No restart should have occurred (actuator does not restart)
3. Container should still show "Up 8 hours" (or longer, not reset)

---

## 4. Rollback Plan

### 4.1 Rollback Steps

1. Remove only the overlay file created by this campaign:
   ```bash
   rm /home/hermes/projects/trading/freqforge-canary/user_data/overlay_max_open.json
   ```
2. Verify `config.json` is unchanged (SHA256 matches baseline)
3. **[L3 SEPARATE APPROVAL]** Restart the bot to reload without overlay
   - Restart is NOT performed by the actuator
   - Requires separate `APPROVE_RESTART` token
4. After restart, verify `max_open_trades` returns to 3

### 4.2 Rollback Safety

- Only the overlay file is removed — no config mutation
- `config.json` baseline is never touched by the actuator
- Rollback is fully reversible (re-apply overlay if needed)

---

## 5. RuntimeEffectProof Plan

### 5.1 Objective

Prove whether the overlay is runtime-visible/effective without restarting Docker.

### 5.2 Method

1. Inspect container process command line (verify `--config` path)
2. Inspect mounted volumes (verify `user_data` is mounted)
3. Check if Freqtrade reads overlay files at runtime or only at startup
4. If overlay is not runtime-visible without restart → classify as YELLOW
5. If restart is needed → requires separate `APPROVE_RESTART` L3 token

### 5.3 Classification Rules

| Verdict | Condition |
|---------|-----------|
| GREEN | Runtime visibility AND effective value proven |
| YELLOW | Overlay exists but runtime visibility not proven (needs restart) |
| RED | Runtime contradicts overlay, dry_run=false, or unexpected mutation |

### 5.4 Post-Proof Gates

- `mutation_counter_should_increment = true` only after GREEN
- `measurement_allowed = true` only after GREEN
- Measurement window T0/T1/T2/T3 starts only after GREEN

---

## 6. Measurement Window Plan (Post-GREEN Only)

### 6.1 Observation Points

| Point | Time After GREEN | Metrics |
|-------|------------------|---------|
| T0 | Immediate | Baseline: trades, exposure, drawdown, bot health |
| T1 | +1 hour | First observation: trade count, max concurrent trades |
| T2 | +6 hours | Mid-window: exposure, rejected entries, RiskGuard state |
| T3 | +24 hours | Full window: net PnL, win rate, max drawdown |

### 6.2 Metrics

- Trade count (should decrease or stay stable with max_open_trades=2)
- Max concurrent open trades (should not exceed 2)
- Exposure (stake_amount × open_trades)
- Drawdown (max drawdown %)
- Rejected entries (if any)
- RiskGuard state (ACCEPTED/WATCH_ONLY/BLOCK_ENTRY counts)
- Bot health (container uptime, ping status, error logs)

### 6.3 Success/Failure Criteria

- **Success:** max_open_trades effective = 2, no live trading, dry_run remains true
- **Failure:** max_open_trades > 2, dry_run=false, unexpected mutation, container crash

---

## 7. Human Gate Status

### 7.1 Required L3 Approval Phrase

```text
I approve L3 controlled canary apply for candidate max_open_trades_3_to_2 on freqtrade-freqforge-canary with parameter max_open_trades from 3 to 2.
```

### 7.2 Current Status

- **L3 token:** NOT SET (expected)
- **Approval phrase:** NOT RECEIVED
- **Action:** PREPARED_BUT_NOT_APPLIED

### 7.3 Additional Precondition

- **RiskGuard:** Must derive PASS at apply time. Currently FAIL due to market
  conditions (0 ACCEPTED pairs). This is a runtime precondition that may resolve
  when market signals change. The L3 approval phrase alone is insufficient —
  RiskGuard must also be PASS at the moment of apply.

---

## 8. Runtime Impact

**Zero.** No overlay written, no config changed, no Docker restart, no live trading.

---

## 9. Files Changed

None (this is a read-only preflight report).

---

## 10. Exact Next Action

```text
1. Wait for L3 approval phrase from Luke:
   "I approve L3 controlled canary apply for candidate max_open_trades_3_to_2
    on freqtrade-freqforge-canary with parameter max_open_trades from 3 to 2."

2. Verify RiskGuard derives PASS at apply time
   (check orchestrator/state/riskguard/riskguard_state.json has ≥1 ACCEPTED pair)

3. Set APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION=APPROVE

4. Run check_readiness() — all 9 gates must PASS

5. Run execute_apply() — expect SHADOW_OVERLAY_WRITTEN

6. Verify overlay file at expected path

7. Run RuntimeEffectProof → classify GREEN/YELLOW/RED

8. If GREEN: set mutation_counter++ and measurement_allowed=true
   If YELLOW: document that restart is needed (separate APPROVE_RESTART)
   If RED: rollback immediately

9. If GREEN: start T0/T1/T2/T3 measurement window
```