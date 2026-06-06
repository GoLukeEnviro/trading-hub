# Context: 2026-06-06 Prime Directive Execution

## Was gemacht wurde

### Prio 1 🔴 Permission Fix (FreqAI-Rebel config.json)
- **Config-Status**: Bereits korrekt — `dry_run=true`, `db_url` auf `tradesv3.freqai_rebel.dryrun.sqlite`, Datei writable
- **Gefunden**: `primo_signal_state.json` im Volume ist 0 Bytes und root-owned → kann nicht gelöscht werden (kein sudo). Aber: Pipeline schreibt nicht in dieses Verzeichnis, und separater Bind-Mount überschreibt die Datei.
- **Container-Name**: `freqai-rebel` → tatsächlich `trading-freqai-rebel-1`

### Prio 2 🟡 Trailing-Stop Audit
- **FreqForge/Canary**: Kein trailing_stop in Config + Strategy hat `trailing_stop=False` (hart kodiert)
- **Regime-Hybrid**: trailing_stop korrekt mit `trailing_only_offset_is_reached=true`
- **FreqAI-Rebel**: trailing_stop aktiv mit 0.8%/1.2% (eng)
- **Vorschlag**: FreqForge/Canary um trailing ergänzen (0.02/0.03/offset), Freigabe nötig

### Prio 3 🟡 BTC-Pair Confidence-Schwelle
- **Aktuell**: Globaler `CONFIDENCE_THRESHOLD = 0.65` in trading_pipeline.py
- **Keine per-Pair-Schwellen vorhanden**
- **Signal aktuell**: BTC/ETH/SOL alle bei confidence 0.85
- **Problem**: BTC 50% WR (1/2, -0.60 USDT)
- **Vorschlag**: `PAIR_CONFIDENCE_OVERRIDES = {"BTC/USDT": 0.85}` in RiskGuard, Freigabe nötig

### Prio 4 🟢 Health-Check Verifikation
- **DB-Pfade (commit cb9cde9)**: ✅ Alle korrekt — bot-spezifische Namen, generische `tradesv3.sqlite` nirgends mehr
- **freqtrade_monitor.py**: ❌ Container-Namen falsch → `docker exec` fehlschlägt → "container not running"
- **quality_hub_monitor.py**: ❌ Selbes Problem → Rebel zeigt fälschlich `dry_run=F`
- **Ursache**: Naming-Drift durch docker-compose project prefix (`trading-`) und suffix (`-1`)
- **Betroffen**: 4 Bots × 2 Scripts + guardian (alte `ai-hedge-fund-crypto` Referenz)

### Prio 5 🟢 Regime-Hybrid Diagnose
- **AIOverride-Hook**: ✅ Vorhanden — `primo_gate_allows()` aus primo_signal.py
- **Modell**: Veto (blockt entries), kein Force-Entry → kein `ai_override_short` enter_tag
- **Negativer PnL**: Signal blockiert aktuell ALLE longs (`allow_long_bias=false`) im SHORT-Bias
- **enter_tag-Erwartung**: Die erwarteten Tags existieren nicht — das ist Architektur, kein Bug

### Prio 6 🔵 Docs Update
- `docs/state/current-operational-state.md` aktualisiert
- Git commit `bb7334e`: "docs: operational state update 2026-06-06"

## Offene Punkte (Freigabe nötig)
1. Container-Namen in freqtrade_monitor.py + quality_hub_monitor.py fixen
2. Trailing-Stop zu FreqForge/Canary Config hinzufügen
3. Per-Pair-Confidence für BTC in trading_pipeline.py
4. Root-owned primo_signal_state.json cleanup (sudo nötig)
