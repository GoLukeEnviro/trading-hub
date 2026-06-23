# SI-v2 Apply Actuator — Runtime Activation Plan

**Target:** Future L3 runtime activation
**Approval Token:** `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION="APPROVE"`
**Status:** DRAFT — Do not execute without explicit approval

## Prerequisites

Before ANY runtime activation:

- [ ] This plan reviewed and approved
- [ ] `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION="APPROVE"` set in a separate session
- [ ] All 4 bots running and healthy
- [ ] Current config snapshots taken for all 4 bots
- [ ] Rollback plan documented
- [ ] ShadowLogger operational
- [ ] RiskGuard operational
- [ ] Controller in PAUSED / L3_REPOSITORY_ONLY

## Activation Steps

### Step 1: Pre-Activation Audit

```bash
cd /home/hermes/projects/trading/self_improvement_v2
python3 scripts/si_v2_apply_actuator_audit.py --mode audit
```

Verify all 4 bindings are VERIFIED. Record output.

### Step 2: Config Snapshot

```bash
for bot_id in freqtrade-freqforge freqtrade-freqforge-canary freqtrade-regime-hybrid freqai-rebel; do
  BINDING=$(python3 -c "
from si_v2.apply_actuator.runtime_binding import resolve_binding
print(resolve_binding('$bot_id').host_config_path)
")
  cp "$BINDING" "${BINDING}.bak-$(date -u +%Y%m%dT%H%M%SZ)"
done
```

### Step 3: Generate Effective Config

For the approved proposal, run:

```bash
cd /home/hermes/projects/trading/self_improvement_v2
python3 scripts/si_v2_apply_actuator_audit.py \
  --mode report \
  --proposal-id <PROPOSAL_ID> \
  --bot-id <BOT_ID> \
  --output /tmp/actuator-report.json
```

Review the draft. Verify:
- `dry_run_preserved: true`
- `live_trading_forbidden: true`
- `changed_keys` match expected parameters

### Step 4: Place Overlay in Correct Runtime Path

```bash
# Example for freqforge
cp <overlay_file> /home/hermes/projects/trading/freqforge/user_data/overlay_<PROPOSAL_ID[:8]>.json
```

**CRITICAL:** Must use the VERIFIED host_user_data_path from the binding table.
NOT `freqtrade/bots/freqforge/user_data/`.

### Step 5: Verify Runtime Visibility

```bash
docker exec trading-freqtrade-freqforge-1 sh -lc \
  'ls -la /freqtrade/user_data/overlay_*.json'
```

File must be visible. If not, stop — do not proceed.

### Step 6: Reload Bot Config

Option A (preferred): Restart bot with multi-config:
```bash
# This requires modifying docker-compose or restarting the container
# ONLY with explicit approval
```

Option B: Freqtrade reload (if supported):
```bash
docker exec trading-freqtrade-freqforge-1 sh -lc \
  'freqtrade trade --reload'
```

### Step 7: Verify Loaded Config

```bash
docker exec trading-freqtrade-freqforge-1 sh -lc \
  'cat /freqtrade/user_data/config.json' | python3 -c "
import json, sys
config = json.load(sys.stdin)
print('max_open_trades:', config.get('max_open_trades'))
print('stake_amount:', config.get('stake_amount'))
print('tradable_balance_ratio:', config.get('tradable_balance_ratio'))
print('dry_run:', config.get('dry_run'))
"
```

Must show expected values.

### Step 8: Run Actuator Proof

```bash
cd /home/hermes/projects/trading/self_improvement_v2
python3 scripts/si_v2_apply_actuator_audit.py \
  --mode report \
  --proposal-id <PROPOSAL_ID> \
  --bot-id <BOT_ID>
```

If proof status is GREEN:
- Mutation counter may increment
- Measurement may begin after 2 post-apply cycles

### Step 9: Begin Measurement

- Wait 2 full SI-v2 cycles
- Run `post_apply_impact.evaluate_apply_plan_impact()`
- Attribution report decides keep/rollback/iterate

## Rollback

```bash
# Simply remove the overlay file
rm -f /home/hermes/projects/trading/<BOT_USER_DATA>/overlay_<PROPOSAL_ID[:8]>.json

# If multi-config was used, the bot will fall back to base config.json
# on next restart or reload
```

## Hard Blocks

The following conditions MUST block activation:
- Any `dry_run=false` detected
- Any live trading credentials
- Any strategy file change
- Overlay not visible inside container
- Wrong host path used
- Bot not running
- Controller not PAUSED

## DO NOT DO

- Do NOT modify `config.json` directly
- Do NOT set `dry_run=false`
- Do NOT enable live trading
- Do NOT change strategy files
- Do NOT run `docker-compose down/up` without explicit approval
- Do NOT skip the runtime visibility check
- Do NOT skip the loaded config verification
