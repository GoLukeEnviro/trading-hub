# SI-v2 Controlled Apply Proof — 65502d13

## Status
**NO_RUNTIME_EFFECT** 🔴

## Apply Verdict
**APPLY_GATE_READY → NO_RUNTIME_EFFECT** — Overlay artifact committed but has zero runtime impact on bot.

> **POST-MERGE CORRECTION (2026-06-23T11:00 UTC):**
> Post-merge audit discovered that the overlay file was written to a path not mounted by the
> freqforge container, and even if placed correctly, Freqtrade has no mechanism to read
> `overlay_*.json` files. See `si-v2-apply-correction-no-runtime-effect-65502d13-2026-06-23.md`
> and **Issue #332** for the full analysis and next steps.

## Candidate

| Field | Value |
|-------|-------|
| Proposal ID | `65502d13a99bfadd` |
| Bot | `freqtrade-freqforge` |
| Hypothesis | `reinforce_profitable_pair_cluster_v1` |
| Walk-forward | +23.88 USDT, PF 1.56, DD 2.19%, 77 trades |
| Evaluation | PASS_REVIEW |
| Mutation policy | `safe_parameter_overlay_only` |
| Risk | LOW |
| Fleet relevance | 5/5 |

## Pre-Apply Gate

| Check | Value |
|-------|-------|
| Gate type | Manual pre-apply cycle (replaces 12:17 UTC scheduled gate — user-approved) |
| Cycle ID | `20260623T104905Z` |
| Cycle verdict | **GREEN** |
| 4/4 bots | ✅ All AUTHENTICATED, ping OK |
| Rainbow | SUCCESS (6 signals) |
| Fleet verdict | GREEN |
| Fleet verdict reason | all 4 bots authenticated and decisions generated |
| Shadow proposals | 4 (2 eligible: freqforge, canary) |
| runtime_mutations | 0 |
| config_mutations | 0 |
| live_trading_mutations | 0 |
| docker_mutations | 0 |
| strategy_mutations | 0 |
| Controller | PAUSED / L3_REPOSITORY_ONLY |
| Measurement ledger | cycles=52, mutations_all_zero=True |

## Apply Execution

| Field | Value |
|-------|-------|
| Apply timestamp | 2026-06-23T10:49:27+00:00 |
| Approval token | `APPROVE_SI_V2_CONTROLLED_APPLY_65502d13` — consumed |
| What changed | Created `freqtrade/bots/freqforge/user_data/overlay_65502d13.json` |
| Configs modified | **None** |
| Strategy modified | **None** |
| Bot restarted | **No** |
| Docker changed | **No** |

## Overlay Content

```json
{
  "_overlay_meta": {
    "proposal_id": "65502d13a99bfadd",
    "hypothesis": "reinforce_profitable_pair_cluster_v1",
    "applied_at_utc": "2026-06-23T10:49:27+00:00",
    "mutation_policy": "safe_parameter_overlay_only",
    "rollback": "rm -f freqtrade/bots/freqforge/user_data/overlay_65502d13.json",
    "evidence": {
      "walk_forward_net_pnl": 23.88,
      "profit_factor": 1.56,
      "max_drawdown_pct": 2.19,
      "total_trades": 77,
      "top_pair": "SOL/USDT:USDT"
    }
  },
  "max_open_trades": 3,
  "tradable_balance_ratio": 0.99,
  "stake_amount": "unlimited",
  "stake_currency": "USDT"
}
```

## Safety Validation

| Check | Result |
|-------|--------|
| dry_run=true | ✅ Unchanged |
| Live trading | ❌ No |
| Strategy change | ❌ No |
| Config mutation | ❌ No |
| Secrets in overlay | ❌ None found |
| dry_run=false scan | Clean |
| JSON schema | Valid |

## Rollback

```bash
rm -f freqtrade/bots/freqforge/user_data/overlay_65502d13.json
```

Snapshot preserved at: `docs/context/snapshots/apply-65502d13-20260623T104927Z`

## Mutation Counter

| Before | After |
|--------|-------|
| 0 | **1** (65502d13, overlay only) |

## PR

- Branch: `apply/si-v2-65502d13-controlled-apply`
- Commit: `040d329`
- PR: **https://github.com/GoLukeEnviro/trading-hub/pull/331**

## Related PRs

| PR | Description | Status |
|----|-------------|--------|
| #328 | Phase C Proof | Merged (`f22e81d`) |
| #329 | Approval Packet | Merged (`ebd178e`) |
| #330 | Scheduled Cycle Proof | Open |
| #331 | **Controlled Apply** | Merged — **NO_RUNTIME_EFFECT** (see Issue #332) |

## Post-Apply Measurement Plan

**BLOCKED** — Cannot measure because overlay has no runtime effect.
Measurement blocked until Issue #332 (fleet-aware overlay activation) is resolved.

### Pre-Apply Baseline (from 061729Z cycle)

| Metric | Value |
|--------|-------|
| freqforge mean_profit_all_percent | +2.42% |
| freqforge profit trend | improving |
| freqforge total_trades | 42 |
| runs observed | 5 |

### Post-Apply Targets

- Profit trend: stable or improving
- No significant drawdown increase
- 2-cycle observation window

## Controller

**PAUSED / L3_REPOSITORY_ONLY** — unchanged.

## fleet-auto-repair

Noted (separate issue). Not blocking.

## Nächster Schritt

**BLOCKED.** Siehe Issue #332: "SI-v2: Implement fleet-aware overlay activation before measurement."
Kein weiterer SI-v2 Apply oder Measurement bis der Actuator implementiert und verifiziert ist.

---

*Report generated: 2026-06-23T10:50 UTC*
*Pre-apply cycle: 20260623T104905Z*
*Apply commit: 040d329*
*Evidence directory: /opt/data/reports/si-v2-approval-gate-and-scheduled-cycle-20260623T103837Z*
