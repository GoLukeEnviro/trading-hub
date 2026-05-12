# Fleet Dry-Run Safety Audit — Orchestrator Bootstrap — 2026-05-07

## Executive Summary

**Status: PASS — GREEN**

All three Freqtrade bots are running in dry-run mode with no exchange credentials.

## Bot Status Overview

| Bot | Container | Port | Strategy | State | Dry-Run | Credentials |
|-----|-----------|------|----------|-------|---------|-------------|
| **freqtrade-rsi** | Up 6 hours | 8081 | SimpleRSIOnly_v1 | RUNNING | ✅ True | ✅ Absent |
| **freqtrade-momentum** | Up 6 hours | 8084 | MomentumBG15_v1 | RUNNING | ✅ True | ✅ Absent |
| **freqtrade-regime-hybrid** | Up 6 hours | 8085 | RegimeSwitchingHybrid_v6_Stable | RUNNING | ✅ True | ✅ Absent |

## Detailed Audit

### 1. freqtrade-rsi (Port 8081)

**Container:**
- Status: Up 6 hours
- Image: freqtradeorg/freqtrade:stable
- Port: 127.0.0.1:8081->8081/tcp

**Command Line:**
```
freqtrade trade --config /freqtrade/config/config.json --strategy SimpleRSIOnly_v1
```

**Config Audit:**
- `dry_run: True` ✅
- `trading_mode: futures` ✅
- `exchange.key: absent` ✅
- `exchange.secret: absent` ✅

**Strategy:**
- Class: `SimpleRSIOnly_v1`
- Matches CLI: ✅ Yes

**Verdict:** GREEN — Safe, no live-money risk

---

### 2. freqtrade-momentum (Port 8084)

**Container:**
- Status: Up 6 hours
- Image: freqtrade-momentum-custom:running
- Port: 127.0.0.1:8084->8082/tcp

**Command Line:**
```
freqtrade trade --config /freqtrade/config/config.json --strategy MomentumBG15_v1
```

**Config Audit:**
- `dry_run: True` ✅
- `trading_mode: futures` ✅
- `exchange.key: absent` ✅
- `exchange.secret: absent` ✅

**Strategy:**
- Class: `MomentumBG15_v1`
- Matches CLI: ✅ Yes

**Verdict:** GREEN — Safe, no live-money risk

---

### 3. freqtrade-regime-hybrid (Port 8085)

**Container:**
- Status: Up 6 hours
- Image: freqtradeorg/freqtrade:stable
- Port: 127.0.0.1:8085->8085/tcp

**Command Line:**
```
freqtrade trade --config /freqtrade/config/config_regime_hybrid_dryrun.json --strategy RegimeSwitchingHybrid_v6_Stable
```

**Config Audit:**
- `dry_run: True` ✅
- `trading_mode: futures` ✅
- `margin_mode: isolated` ✅
- `exchange.key: absent` ✅
- `exchange.secret: absent` ✅

**Strategy:**
- Class: `RegimeSwitchingHybrid_v6_Stable`
- Matches CLI: ✅ Yes

**Verdict:** GREEN — Safe, no live-money risk

---

## Security Assessment

### Exchange Credentials
- **RSI:** No keys present
- **Momentum:** No keys present
- **Regime-Hybrid:** No keys present

### REST API Credentials
- Internal API passwords may exist for bot control
- These are NOT exchange trading credentials
- Not audited in detail (internal control risk only)
- No real-money risk if `dry_run: true`

### Trading Mode
- All bots: `futures` mode
- Regime-Hybrid: `isolated` margin mode
- No spot trading active

### Dry-Run Status
- All bots: `dry_run: True`
- No real orders can be placed
- All trades are simulated

## Signal Bridge Status

**Bridge Script:**
- Path: `/home/hermes/projects/trading/freqtrade/tools/primo_signal_bridge.py`
- Status: Exists (not audited in detail this phase)

**Shared Helper:**
- Path: `/home/hermes/projects/trading/freqtrade/shared/primo_signal.py`
- Status: Exists (not audited in detail this phase)

**Signal State Files:**
- Expected: `user_data/primo_signal_state.json` per bot
- Status: Not verified this phase (deferred to next phase)

## Risk Classification

| Risk | Status | Notes |
|------|--------|-------|
| Live trading enabled | ❌ NOT PRESENT | All bots dry_run: true |
| Exchange credentials | ❌ NOT PRESENT | All keys absent |
| Wrong strategy deployed | ❌ NOT PRESENT | CLI matches expected |
| Container not running | ❌ NOT PRESENT | All up 6+ hours |
| API unreachable | ❌ NOT PRESENT | Verified via API ping earlier |

## Verdict

**GREEN — Fleet is safe for continued dry-run operations.**

No live-money risk detected.
No credential leaks detected.
No strategy mismatches detected.
All containers healthy.

## Recommendations

1. Continue dry-run operations
2. Complete RiskGuard + ShadowLogger stabilization
3. Add signal state file verification to next audit
4. Add trade count verification to next audit
5. Consider adding API health check to regular monitoring

---

**Audit Date:** 2026-05-07  
**Auditor:** orchestrator profile  
**Status:** PASS — GREEN  
**Next Audit:** After RiskGuard + ShadowLogger stabilization
