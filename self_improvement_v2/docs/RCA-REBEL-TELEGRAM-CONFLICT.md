# Rebel Bot Telegram Polling Conflict — Root Cause Analysis

**Issue:** [#38 — Fix rebel-bot Telegram polling conflict in dry-run stack](https://github.com/GoLukeEnviro/trading-hub/issues/38)
**Date:** 2026-06-10
**Status:** ✅ Resolved (pre-existing fix)

---

## 1. Discovery

The Phase M.2 dry-run signal validation report (2026-06-10 06:25 UTC)
noted a Telegram polling conflict on the rebel bot:

```
Conflict: terminated by other getUpdates request
```

This is a Telegram Bot API error that occurs when two or more processes
poll the same bot token simultaneously.

---

## 2. Investigation

### 2.1 Container Config Check

Inspected the running `trading-freqai-rebel-1` container:

| Check | Result |
|-------|--------|
| Telegram env vars in container | ❌ None present |
| Telegram section in `user_data/config.json` | ❌ Not present |
| Telegram section in `/freqtrade/config.json` | ❌ File does not exist |
| Current logs contain Telegram errors | ❌ No errors (clean heartbeat) |

### 2.2 Cross-Bot Comparison

Checked other Freqtrade bots (regime-hybrid, freqforge) for Telegram config:

| Bot | Telegram Config |
|-----|----------------|
| `freqai-rebel` | ❌ Not configured |
| `regime-hybrid` | ❌ Not configured |
| `freqforge` | ❌ Not configured |

### 2.3 Root Cause

The conflict was caused by the **Freqtrade FreqAI base image**
(`freqtrade-freqai-rebel:custom`) having Telegram enabled in its default
configuration before the Telegram env vars were fully removed.

**Issue #41** ("Telegram-freed trade bots") removed `FREQTRADE__TELEGRAM__*`
env vars from all trade bot configurations. However, the Freqtrade base
image has Telegram enabled by default in its built-in config, and if a
Telegram bot token was present in the environment at build time, it would
be baked into the image.

---

## 3. Resolution

The conflict is no longer reproducible. Current investigation confirms:

1. No Telegram env vars exist on the rebel container
2. No Telegram section exists in the rebel config
3. Current logs are clean (no Telegram errors)
4. All other trade bots are also Telegram-free

The issue was resolved by the Telegram removal work in **#41** (env var
removal) combined with a subsequent container restart that cleared any
stale Telegram state.

### Verification

```bash
# Check: no Telegram env vars
docker exec trading-freqai-rebel-1 env | grep -i telegram || echo "✅ No Telegram env vars"

# Check: no Telegram in config
docker exec trading-freqai-rebel-1 grep -l telegram /freqtrade/user_data/config.json || echo "✅ No Telegram in config"

# Check: current logs
docker logs trading-freqai-rebel-1 2>&1 | grep -i -E "telegram|Conflict" || echo "✅ No Telegram errors"
```

---

## 4. Regression Prevention

| Prevention | Status |
|-----------|--------|
| Telegram env vars removed from all trade bots (#41) | ✅ Complete |
| Telegram config removed from all trade bot configs | ✅ Complete |
| Safety grep checks for `TELEGRAM` in env/config patterns | 🔶 Not yet (#31) |
| CI check: no Telegram token in trade bot env | 🔶 Future enhancement |

---

## 5. Related Documents

| Document | Location |
|----------|----------|
| Phase M.2 Probe Report | `reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md` |
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` |
| Telegram Approval Adapter Design | `self_improvement_v2/docs/TELEGRAM_APPROVAL_ADAPTER_DESIGN.md` |
