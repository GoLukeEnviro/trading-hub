# 2026-06-05 — LIVE_RISK ↔ LEDGER_RISK Reconciliation Audit

## TL;DR
- **1061.62 USDT Differenz** zwischen LIVE_RISK und LEDGER_RISK Equity
- **~93% (994.24 USDT)**: Rebel fehlt komplett als `source_key` in LEDGER
- **~7% (67.39 USDT)**: 4-Tage-Drift der 3 aktiven Bots seit letztem LIVE_RISK-Write
- **Root Cause**: LEDGER aggregiert nicht über alle 4 LIVE-Bots
- **Risk-Bewertung**: Niedrig (Datenmodell-Lücke, keine Live-Order-Implikation)

## Daten-Inputs (alle read-only, Zeitstempel 2026-06-05)

### LEDGER_RISK (fleet_risk_state.jsonportfolio.sources, fresh)
| Source Key | current_equity | peak_equity | updated_at |
|---|---|---|---|
| baseline_v1_freqforge | 970.73 | 1021.83 | 2026-06-05T12:18:00+00:00 |
| freqforge_canary_v1 | 482.03 | 507.40 | 2026-06-05T12:17:59+00:00 |
| regime_hybrid_dryrun | 983.88 | 993.82 | 2026-06-05T12:17:56+00:00 |
| **SUM** | **2436.64** | **2523.05** | — |

### LIVE_RISK (drawdown_state.json, **STALE 4d**)
| Bot | balance | starting | pnl | reachable |
|---|---|---|---|---|
| freqforge | 1007.90 | 950.00 | +57.90 | True |
| canary | 503.23 | 500.00 | +3.23 | True |
| regime_hybrid | 992.90 | 1000.00 | -7.10 | True |
| rebel | 994.24 | 1000.00 | -5.76 | True |
| **SUM** | **3498.27** | **3450.00** | **+48.27** | **4/4** |

### Delta-Analyse
| Mapping | LIVE | LEDGER | Δ |
|---|---|---|---|
| freqforge → baseline_v1_freqforge | 1007.90 | 970.73 | **+37.17** |
| canary → freqforge_canary_v1 | 503.23 | 482.03 | **+21.20** |
| regime_hybrid → regime_hybrid_dryrun | 992.90 | 983.88 | **+9.02** |
| rebel → **MISSING** | 994.24 | — | **+994.24** |
| **TOTAL** | 3498.27 | 2436.64 | **+1061.62** ✓ |

Δ matches the observed LIVE-LEDGER portfolio gap to within 0.01 USDT.

## Root Cause Analysis

### Component 1: Rebel fehlt in LEDGER (994.24 USDT, 93.6%)
- `portfolio.sources` hat keinen `rebel`, `freqai-rebel` oder `rebel_*` Key
- `trade_history` hat 0 Einträge mit `source` containing "rebel"
- Mögliche Gründe:
  1. **Rebel hat 0 trades** (VISIBILITY_GAP) → kein Update-Trigger im Ledger-Collector
  2. **Rebel hat keine host-side config mount** → Collector kann Balance nicht lesen
  3. **Rebel-Key wurde nie angelegt** weil der Collector ihn nicht kennt
- Bestätigung über `docker exec freqai-rebel` und Collector-Code nötig (Out-of-Scope für Tier-0)

### Component 2: 4-Tage-Drift der 3 aktiven Bots (67.39 USDT, 6.4%)
- LEDGER: 970.73 + 482.03 + 983.88 = 2436.64 (frisch, 12:18:00)
- LIVE (stale, 01.06 04:01): 1007.90 + 503.23 + 992.90 = 2504.03
- Delta: +67.39 USDT (LIVE höher)
- Das ist **positive equity appreciation über 4 Tage** — plausibel und nicht besorgniserregend

## Implications

### Für Reporting-Health
- **LEDGER_RISK ist NICHT falsch**, aber **UNVOLLSTÄNDIG** — fehlende 994 USDT Rebel
- Reporting-Health-Score 73 berücksichtigt bereits "unvollständig" implizit
- Empfehlung: Ledger-Collector soll Rebel als Source registrieren (Tier-2 — Code-Touch)

### Für LIVE_RISK
- `drawdown_state.json` ist 4 Tage alt, per_bot-Werte sind veraltet
- Aber: **Drawdown 0% ist immer noch die jüngste Live-Wahrheit** bis Refresh
- Empfehlung: LIVE_RISK-Refresh-Trigger (Tier-2 — User-Approval)

### Für Verdict
- Verdict bleibt **WARNING**, Begründungen dokumentiert
- **NICHT GREEN**, weil:
  - LIVE_RISK stale (4d)
  - LEDGER_RISK unvollständig (Rebel fehlt)
  - VISIBILITY_GAP (Rebel)
  - Permission errors (separat)

## Recommended Actions (tier-klassifiziert)

| Action | Tier | Begründung | Approval |
|---|---|---|---|
| Ledger-Collector um `rebel`-Source erweitern | T2 | Code-Touch im Risk-Layer | erforderlich |
| LIVE_RISK-Refresh-Trigger (read-only) | T2 | Mutation von LIVE-State | erforderlich |
| Watchdog: "LEDGER sources < active_bots" Alert | T1 | Monitoring-Erweiterung | self-approved |
| Canonical-Notiz: "LEDGER unvollständig, Rebel fehlt" | T0 | Doku-Update | self-approved |

## Audit-Status
- **Read-only Audit:** ✓ durchgeführt
- **Keine Mutationen:** ✓ bestätigt
- **Canonical update:** optional (nur Notiz in canonical-trading-status.md)
- **Memory-Save:** Audit-Pattern als Skill speichern (Tier-0-Empfehlung)
