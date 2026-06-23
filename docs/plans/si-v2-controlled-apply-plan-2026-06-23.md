# SI-v2 Controlled Apply Plan — `65502d13` (freqrtrade-freqforge)

**Date:** 2026-06-23  
**Status:** PLAN ONLY — no execution without approval token  
**Proposal:** `65502d13a99bfadd`  
**Hypothesis:** `reinforce_profitable_pair_cluster_v1`  
**Target:** `freqtrade-freqforge` (port 8086)

---

## Approval Token

```bash
export APPROVE_SI_V2_CONTROLLED_APPLY_65502d13="APPROVE"
```

**Without token:** abort, no apply.

---

## Preflight Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Rainbow healthy | `python3 orchestrator/scripts/rainbow_producer_readiness_check.py` | GREEN, exit 0 |
| Freqforge running | `docker inspect trading-freqtrade-freqforge-1 --format '{{.State.Status}}'` | running |
| Freqforge dry-run | grep `dry_run` in config | True |
| SI-v2 latest cycle GREEN | Latest cycle state | 4/4 bots, mutations 0 |
| Controller PAUSED | Cycle state | PAUSED / L3_REPOSITORY_ONLY |
| Approval token set | env check | present |

---

## Apply Action

The `safe_parameter_overlay_only` policy means:

1. **Read** the current overlay proposal from the ShadowLogger or evidence bundle
2. **Create** a parameter overlay file: `freqtrade/bots/freqforge/user_data/overlay_65502d13.json`
3. **Apply** the overlay via Freqtrade's parameter overlay mechanism
4. **Restart** freqtrade-freqforge (dry-run) to pick up changes

Exact overlay content is determined by the ShadowLogger shadow decision log and the candidate SHA.

---

## Post-Apply Validation

| Gate | Check | Expected |
|------|-------|----------|
| Freqforge status | `docker inspect` | running, healthy |
| API reachable | `curl -sf http://trading-freqtrade-freqforge-1:8080/api/v1/ping` | pong |
| Config unchanged | Compare config hash | Only overlay added |
| dry_run | Verify | True |
| Trade generation | Monitor logs | Normal trading activity |
| SI-v2 cycle (12:17) | Active cycle runner | 4/4 bots, mutations 0 (+ overlay) |

---

## Measurement Cycle Plan

| Cycle | Expected Time | Check |
|-------|--------------|-------|
| 1 | 12:17 UTC (same day) | Freqforge trades, profit factor, drawdown |
| 2 | 18:17 UTC | Confirmation, no regression |

---

## Rollback Plan

```bash
# Remove overlay
rm -f freqtrade/bots/freqforge/user_data/overlay_65502d13.json
# Restart bot
docker restart trading-freqtrade-freqforge-1
# Verify
curl -sf http://trading-freqtrade-freqforge-1:8080/api/v1/ping
# Document
# → docs/context/si-v2-rollback-65502d13-YYYYMMDD.md
```

---

## Non-Goals

| Action | Status |
|--------|--------|
| Strategy code change | ❌ Not allowed |
| Config mutation | ❌ Only overlay |
| Live trading | ❌ Never |
| `dry_run=false` | ❌ Never |
| Other bots affected | ❌ No |
| Docker Compose | ❌ Not used |
| Auto-restart | ❌ Not enabled |
| SI-v2 scoring change | ❌ Not changed |

---

## Safety Gates

| Gate | Before Apply |
|------|-------------|
| Controller PAUSED | ✅ Maintained |
| All mutations 0 | ✅ (overlay is approved mutation) |
| dry_run=True | ✅ |
| Rainbow fresh | ✅ |
| History gate open | ✅ |
