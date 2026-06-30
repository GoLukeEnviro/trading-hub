# SI-v2 T4 Measurement Retrieval

**Date:** 2026-06-30T16:00:00Z
**Verdict:** `STILL_WAITING`
**Candidate:** `max_open_trades_3_to_2`
**Target Bot:** `freqtrade-freqforge-canary`
**Control Bot:** `freqtrade-freqforge`

---

## 1. Verdict

```
STILL_WAITING — Canary hat 0 neue geschlossene Trades seit T3.
Keine Measurement Decision Engine ausführbar.
Kein Apply, kein Rollback, keine Mutation.
```

---

## 2. Timestamp UTC

```
2026-06-30T16:00:00Z
```

---

## 3. Git Evidence

| Check | Result |
|-------|--------|
| HEAD | `f9b42f5` — fix(si-v2): refresh freqtrade historical evidence path (#400) |
| Working tree | Clean (nur untracked docs/reports/context) |
| Letzte 3 Commits | `f9b42f5` #400, `12d5ff1` #399, `01e2062` fleet underperformance |

---

## 4. Fleet Evidence

| Bot | Container | Uptime | Status |
|-----|-----------|--------|--------|
| freqtrade-freqforge | `trading-freqtrade-freqforge-1` | 2 days | ✅ healthy |
| freqtrade-freqforge-canary | `trading-freqtrade-freqforge-canary-1` | 2 days | ✅ up |
| freqtrade-regime-hybrid | `trading-freqtrade-regime-hybrid-1` | 2 days | ✅ up |
| freqai-rebel | `trading-freqai-rebel-1` | 2 days | ✅ up |

---

## 5. Canary Evidence

| Check | Required | Actual | Verdict |
|-------|----------|--------|---------|
| dry_run | true | **true** | ✅ PASS |
| max_open_trades | 2 | **2** (overlay loaded) | ✅ PASS |
| Overlay SHA | intact | `max_open_trades_3_to_2` | ✅ PASS |
| Container healthy | ✅ | Up 2 days | ✅ PASS |
| **New closed trades since T3** | ≥1 | **0** | ❌ **FAIL** |
| Open trades | — | **2** (UNI, DOT) | ⏳ still open |
| Last close | — | 2026-06-24 16:51 (LINK, -2.24 USDT) | ⏳ 6 days ago |
| Total closed | — | 59 | unchanged |
| Total profit | — | +3.98 USDT | unchanged |

### Canary Open Trades

| Pair | Open Date | Rate | Stake | Stop Loss |
|------|-----------|------|-------|-----------|
| UNI/USDT:USDT | 2026-06-29 21:15 | 2.938 | 23.50 USDT | 2.674 |
| DOT/USDT:USDT | 2026-06-30 14:15 | 0.814 | 24.42 USDT | 0.887 |

---

## 6. Control Evidence (FreqForge)

| Check | Required | Actual | Verdict |
|-------|----------|--------|---------|
| dry_run | true | **true** | ✅ PASS |
| max_open_trades | 5 | **5** (→3 via overlay) | ✅ PASS |
| Container healthy | ✅ | Up 2 days (healthy) | ✅ PASS |
| **New closed trades since T3** | ≥1 | **3** | ✅ PASS |
| Open trades | — | **0** | ✅ |
| Total closed | — | 81 | +1 since T3 |
| Total profit | — | +3.34 USDT | changed from -1.79 (T4 readiness) |

### Control New Closed Trades Since T3

| Pair | Open | Close | Profit | Realized |
|------|------|-------|--------|----------|
| BTC/USDT:USDT | 2026-06-29 04:45 | 2026-06-30 12:24 | +1.53% | **+5.13 USDT** ✅ |
| ETH/USDT:USDT | 2026-06-29 04:45 | 2026-06-29 17:46 | -3.84% | **-12.70 USDT** ❌ |
| SOL/USDT:USDT | 2026-06-29 04:45 | 2026-06-29 17:05 | -4.11% | **-13.88 USDT** ❌ |

---

## 7. Safety Evidence

| Check | Required | Actual | Verdict |
|-------|----------|--------|---------|
| Kill Switch | NORMAL | **No kill_switch.json file** (→ NORMAL) | ✅ PASS |
| dry_run (all bots) | true | **all true** | ✅ PASS |
| Canary overlay intact | ✅ | **intact** | ✅ PASS |
| RiskGuard | available | integrated in ai-hedge-fund | ✅ PASS |
| Unexpected restarts | 0 | **0** | ✅ PASS |
| Errors since T3 | 0 | **0** | ✅ PASS |

---

## 8. Measurement Eligibility

| Criterion | Required | Actual | Eligible? |
|-----------|----------|--------|-----------|
| Canary new closed trades | ≥1 | **0** | ❌ |
| Control new closed trades | ≥1 | **3** | ✅ |
| Kill Switch NORMAL | ✅ | ✅ | ✅ |
| dry_run all bots | ✅ | ✅ | ✅ |
| Historical summary fresh | ✅ | 2026-06-30 13:03 UTC | ✅ |

**Measurement Decision Engine ausführbar?** ❌ **NEIN** — Canary hat 0 neue geschlossene Trades.

---

## 9. Decision

```
OUTCOME: STILL_WAITING
Kein KEEP, kein EXTEND_MEASUREMENT, kein ROLLBACK_REQUIRED.
Nächster Check: nach dem nächsten Canary-Trade-Close.
```

### Begründung

- Canary hat **0 neue geschlossene Trades** seit T3 (2026-06-28).
- Canary hat **2 offene Trades**: UNI/USDT (seit 2026-06-29 21:15) und DOT/USDT (seit 2026-06-30 14:15).
- Control hat 3 neue geschlossene Trades (1 Gewinn, 2 Verluste) — aber ohne Canary-Close ist kein Vergleich möglich.
- Keine Safety-RED, kein Kill Switch, kein Drift.
- Der Engpass ist rein temporal: Canary-Positionen müssen schließen.

---

## 10. Next Step

```
1. Warten auf Canary-Trade-Close (UNI oder DOT).
2. Sobald ≥1 Canary-Close + ≥1 Control-Close seit T3:
   → Measurement Decision Engine ausführen (read-only).
   → Outcome: KEEP | EXTEND_MEASUREMENT | ROLLBACK_REQUIRED.
3. Kein neuer Apply, kein Rollback, keine Pair Expansion bis dahin.
4. Regime-Hybrid und FreqAI-Rebel Underperformance ist separater Track.
```

---

## Evidence

```
Git HEAD:       f9b42f5
Canary closed:  59 (0 new since T3)
Canary open:    2 (UNI, DOT)
Control closed: 81 (3 new since T3)
Control open:   0
Kill Switch:    NORMAL (no file)
dry_run:        true (all 4 bots)
Summary fresh:  2026-06-30T13:03:01Z
```

## Validation

- Git HEAD verified: `f9b42f5`
- Working tree: clean (untracked docs only)
- Canary DB queried: 59 closed, 2 open
- Control DB queried: 81 closed, 0 open
- All 4 bots `dry_run=true`
- No kill_switch.json → NORMAL
- Historical summary: 3h old, still fresh

## Files changed

```
docs/reports/si-v2-t4-measurement-retrieval-2026-06-30-1600Z.md  (NEW)
```

## Mutation status

```
NONE — read-only retrieval, no config changes, no Docker changes, no apply, no rollback.
```
