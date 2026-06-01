# Phase 3: Equity Recovery, Canary Check, Signal-Heartbeat Fix — 2026-05-30

## 1. Equity Protection rückgängig gemacht

**Problem:** Der System-Optimizer hatte alle 4 Bots auf 50% Stake reduziert
(Equity 9998 < 7d-Avg 9999 → false positive, nur 0.01% unter Schwelle).
Das blockierte unnötig Positionsgrößen.

**Fix:**
- FreqForge: stake 50.0 → 100
- Regime-Hybrid: stake 25.0 → 50
- Canary: stake 25.0 → 50
- Rebel: stake 25.0 → 50
- Alle 4 Container restarted
- original_stakes.json geleert (keine Reduktion mehr aktiv)

## 2. Canary SHORTs geprüft

**Status:** Kein Handlungsbedarf. Die 2 legendären Mai-23 SHORTs (BTC@74564, ETH@2026)
wurden bereits am 27. Mai gewinnbringend geschlossen (+0.02, +0.03 USDT).

Aktuell: 1 offene Position — BTC SHORT seit heute 13:45, SL bei 80342 (sicher).
Canary gesamt: 33 Trades, 90.6% WR, +3.19 USDT PnL.

## 3. signal-heartbeat.sh Fix (v3)

**Problem:** Script versuchte curl-Aufruf gegen ai-hedge-fund-crypto via DNS/Docker-Netzwerk.
Timeout, weil:
- Hermes Container kann Docker-internal Port 8080 nicht direkt erreichen (Netzwerk-Isolation)
- ai-hedge-fund-crypto Container hat kein curl-Binary
- 300s curl-Timeout + 2 Retries = 900s Blockade

**Fix:** Script auf `docker exec` + Python urllib umgestellt:
- `docker exec ai-hedge-fund-crypto python3 -c "urllib.request..."` triggert Signal intern
- Signal wird direkt in den Host-Mount geschrieben (Output-Verzeichnis)
- Kein curl-Binary im Container nötig
- Timeout auf 120s reduziert (realistische LLM-Generierungszeit)

**Getestet:** Signal-Hearbeat OK (0.0min alt), Pipeline hat BTC/ETH/SOL als ACCEPTED
mit 0.80 confidence durch den RiskGuard gebracht.
