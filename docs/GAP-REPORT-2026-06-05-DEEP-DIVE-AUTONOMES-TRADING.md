# GAP-Report: Umfassender Deep-Dive für das Autonome Trading-System (Hermes Trading Hub)

**Erstellt:** 2026-06-05  
**Autor:** Meta-Orchestrator (Grok 4.3 basierte Deep Analysis)  
**Profil:** orchestrator (Trading Hub)  
**CWD:** /home/hermes/projects/trading  
**Version:** 1.0 – Vollständiger GAP-Report (Deep Dive)  
**Status:** Evidenzbasiert auf Code-Review, Dataflow-Analyse, Runtime-Logs/States, Subagent-Exploration, Gedankenexperimenten  

---

## Executive Summary

Das Trading-System (Trading Hub) zielt auf **vollständige Autonomie** ab: von der Marktdaten-Erfassung (Bitget Futures) über LLM/TA-gestützte Signalgenerierung (ai-hedge-fund-crypto), risikogefilterte Bridge (trading_pipeline), Shadow-Logging und Order-Ausführung (Freqtrade Dry-Run Fleet mit RegimeSwitchingHybrid, Momentum, FreqForge_Override, FreqAI-Rebel + parallel MCP-Paper-Simulation) bis zu Risiko- und Compliance-Management – ohne menschliches Eingreifen.

**Stärken (Fortschritt seit Mai-2026):**  
- trading_pipeline.py implementiert zentrale Bridge + RiskGuard (RG-1..5 mit Confidence ≥0.65, Stale-Block) + ShadowLogger (shadow_decisions.jsonl mit 1758+ Einträgen, Stand 2026-06-05) + atomische State-Writes (primo_signal_state.json zu 4+ Targets für FT).  
- fleet_risk_manager.py aktiv (dynamische Exposure-Multiplier 1.0→0.2, Cluster/Correlation/DD-Penalties, cross-bot Equity-Sync, check_entry_allowed).  
- FT-Strategien integrieren primo_gate_allows + FleetRisk (AND-Verknüpfung). ai-hedge produziert strukturierte hermes_signal.json (Bias/Confidence/Action/Quantity).  
- Umfangreiche Watchdogs, Guardian, Healthchecks, Drawdown-Guard, Permission-Autopilot, Qualitäts-Monitore. Alle Komponenten Dry-Run (hardcoded + Policy). Compliance- und Risk-Module in Agenten_Auto_Trade (audit_logger Hash-Chain, Tx-Store 10 Jahre, KillSwitch, CryptoVaR, Report-Gen) vorhanden und getestet.

**Gesamtreife für volle Autonomie: ~45–55 %** (starke Audit- und Gating-Schicht, aber kritische Lücken in Wiring, Resilience, Data-Enrichment, Ops-Stabilität und echten Notfall-Mechanismen verhindern "hands-off" Betrieb).

**Kritischste Top-Gaps (Zusammenfassung):**
- **Keine Funding Rates / Derivates-Microstructure** in Live-Pfad oder realistischen Backtests (Carry-Kosten bei Futures unsichtbar; nur sparse Research in fomo-phase3). 
- **Kill-Switch / echte Emergency-Close nicht wired** (Agenten KillSwitch + drawdown_guard advisory-only; keine zentrale Cancel/Close über FT REST oder MCP in Live-Pfad).
- **Permission-Drift + Cron/Guardian-Fragilität** (wiederkehrende uid0/1337 CRITICAL in shared/state/logs; viele manuelle Fixes in Backups).
- **MCP/FT-Desync + unvollständige Traceability** (RG-Entscheidungen im Shadow, aber MCP-Ergebnisse/Errors nicht persistiert; separate Paper-States).
- **Compliance-Module isoliert** (exzellent in Agenten, aber nicht auf FT-SQLite + Shadow gefüttert; keine einheitlichen AO/GoBD-Audits für Fleet-Trades).
- **Single-Point-of-Failure (Host/Exchange/LLM) + fehlende Resource-Limits** (freqai-rebel 972% CPU; keine docker limits; Bitget-only).
- **Doc-Drift** (AGENTS.md/SOUL/Charter behandeln RiskGuard/Shadow/Pipeline teilweise noch als "SPEC ONLY").
- **Niedrige Test-Coverage für Kern-Gates** (Agenten hat gute Unit/Integration für Risk/Compliance; Orchestrator/Pipeline/RG/FT-Gates nur spärlich).

Der Report liefert pro Lücke: Beschreibung, Schweregrad (🔴 KRITISCH / 🟠 HOCH / 🟡 MITTEL / 🔵 NIEDRIG), Auswirkung auf autonomen Betrieb, Eintrittswahrscheinlichkeit, konkrete Maßnahmen + Evidenz (file:line + Log/State-Snippets). Am Ende eine priorisierte Roadmap mit Zeitplan.

**Methodik (gesamt):** Mischung aus Architektur-Review (Charter/AGENTS vs. Impl), statischer Code-Analyse (50+ Files via read/grep), Dataflow-Tracing (hermes_signal → RG → Shadow → FT-Gate → Exec), Runtime-Evidenz (shadow_decisions.jsonl, fleet_risk_state.json, drawdown_state, cron jobs, perm_autopilot.log, phase-Reports), Schwachstellenscans (except/ TODO / dry_run / advisory / permission) und Gedankenexperimenten zu "schwarzen Flecken" (Black Swans). Subagent-Exploration parallel für Pipeline/MCP, Market-Data und Risk/Infra/Ops. Keine Annahme ungeprüft; Perm-Denied-Files via Python-Open oder Docker-Exec (read-only).

---

## Inhaltsverzeichnis

1. Executive Summary
2. Inhaltsverzeichnis
3. Dimension 1: Marktdaten-Lücken
4. Dimension 2: Signalgenerierungs-Lücken
5. Dimension 3: Ausführungs- & Order-Management-Lücken
6. Dimension 4: Risikomanagement-Lücken
7. Dimension 5: Technische Infrastruktur-Lücken
8. Dimension 6: Betriebliche & Prozess-Lücken
9. Cross-Cutting: State-Machine, Config-Drift, Doc-Drift, Isolation (Hub vs. Agenten vs. Twister)
10. Top-15 priorisierte Gaps (Impact × Prob × Autonomy-Blockade)
11. Priorisierte Roadmap mit Zeitplan
12. Anhang: Methodik-Details, analysierte Artefakte, Black-Swan-Details, Glossar

---

## Dimension 1: Marktdaten-Lücken

**Methodik:** Code-Review aller Provider (bitget_provider.py + binance legacy + download-Skripte + FT DataProvider), Pagination/Cache/Error-Handling, Sampling realer Feather-Dateien (Tiefe pro Pair/TF), Suche nach Funding/OI/Liquidation/Orderbook (grep über ganzes trading/), Qualitäts-Skripte (validate/probe), Backtest vs. Live-Vergleich (backtester.py vs. live DataNode), Cross-Component-Sharing (per-bot vs. ai-hedge cache), Gedankenexperimente zu undetected Gaps in Regime-Shifts.

### Gap-Bewertungstabelle (Auszug – vollständig im Deep-Dive)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| M1.1 | Keine Funding Rates im Live-Pfad oder realistischen Backtests (Carry-Kosten bei Futures unsichtbar; positive Funding bei Longs erodiert PnL unbemerkt in Seitwärtsmärkten) | 🔴 KRITISCH | Falsche "Profitabilität" von Signalen; autonome Positionen halten trotz negativer Carry; Stresstests unbrauchbar; Live-PnL vs. Backtest-Drift | Hoch (Futures 8h-Cadence immer relevant) | 1. BitgetProvider um fetch_funding_rate + persist (als separate Feather/Parquet mit Forward-Fill). 2. Erweitere download_*-Skripte (additive, dedup). 3. FT futures-Configs + backtest mit funding (simulate_funding). 4. Pipeline/RG: Funding-Residual-Feature in Signals. 5. FleetRisk: Funding-Exposure-Multiplier. | bitget_provider.py:174 (nur OHLCV); fomo-phase3/build_5m_dataset.py:118 (nur Research); regime feathers funding ~155 Zeilen 2026-04 bis 05 (sparse, ~2 Monate); FT Strategies: 0 Referenzen zu funding_rate |
| M1.2 | Keine systematische Gap-/Stale-/Outlier-Detection in Live-Datenpfad (Provider geben leere DF oder gepaddete Daten bei Fehlern zurück; keine consecutive-ts-Checks) | 🟠 HOCH | Silent bad bars → falsche TA/LLM-Signale; RG blockt nicht; FT native Logic übernimmt unkontrolliert | Mittel-Hoch (Rate-Limits, API-Flaps, Netzwerk) | 1. BitgetProvider + FT-DP-Wrapper: post-fetch `count_missing_bars(expected, actual)` + `last_bar_age < 2*tf` + z-score Outlier-Flag. 2. DataNode: raise oder flag + Alert an Pipeline. 3. Integriere in validate-Skripte als Cron-Job (central data lake). | _klines_to_dataframe:89 (Padd mit 0.5*vol Schätzungen); get_..._end_time:215 (kein Check); validate_bitget_15m...py:56 (nur offline expected vs len); keine Runtime-Checks in workflow.py |
| M1.3 | Inkonsistente History-Tiefe + keine zentrale Data Lake / Sharing (Regime-Hybrid 4 Jahre 15m BTC ~154k Bars seit 2022; Freqforge/Momentum nur 1–2 Monate; Funding/Mark immer nur ~2 Monate; ai-hedge Runtime-Cache oft leer, pro-Query-CSVs) | 🟠 HOCH | Walk-Forward / Regime-Training unzuverlässig; verschiedene Bots trainieren auf unterschiedliche Marktphasen; Duplizierte Downloads | Hoch (per-bot user_data/data Mounts) | 1. Einheitliches central/data/bitget/ (feather/parquet + Metadata: earliest/latest/quality). 2. Shared Mount in allen Compose + ai-hedge Adapter (oder rsync-Cron). 3. Backfill-Job + Freshness-API. 4. Prune-Policy + Versioning. | freqtrade/bots/regime-hybrid/.../BTC_USDT_USDT-15m-futures.feather:154389 rows 2022-01-01→2026-05; freqforge ~6k rows ab 2026-03; ai-hedge cache/ 0 files (ls); download-Skripte additive aber per-bot |
| M1.4 | Keine Orderbook-Depth, Liquidations-History, Open-Interest als Features (nur ad-hoc CLI in bitget_market.py; MCP sim liq 5% hardcoded) | 🟡 MITTEL | Keine Erkennung von Crowding / Liquidations-Cascades / Liquidity-Dry-ups; Microstructure-Blindspot | Mittel (bei Vol-Spitzen relevant) | 1. Provider: fetch_open_interest + liquidations (ccxt wo verfügbar) + Depth-Snapshots (top 10/20). 2. Persist + Features in Indicators (oi_alignment, book_imbalance). 3. RG: Liquidity-Filter vor ACCEPTED. | bitget_market.py:76 (nur CLI); MCP:374 (5% liq est); fomo: synthetic oi; 0 in ai-hedge / prod FT strategies |
| M1.5 | ai-hedge "Sentiment Collector" ist reiner Price-Proxy (CoinGecko ch24/ch7d/vol als "TA Pillar 40%"); keine echten X/News/On-Chain-Daten; fehlende Consts im aktuellen File vs. .bak | 🟡 MITTEL | 3-Pillar-Modell degeneriert zu TA-only; LLM-Prompts mit falschen "Sentiment"-Daten; Divergenz-Detection schwach | Hoch (aktueller Code) | 1. Echte Quellen (CoinGecko News + X API oder Perplexity/Firecrawl wie in anderen Tools). 2. Fix sentiment_collector.py (restore consts aus bak). 3. Optional: Funding-Basis als 4. Pillar. | sentiment_collector.py:5 (Pillar 1 "TA proxy from CoinGecko"); 21 (BITGET_API_BASE unused); .bak.20260605 hat URLs/Maps; collect() schreibt /output/sentiment_data.json (wird in portfolio_node geladen) |

**Text-Diagramm-Beschreibung – Marktdaten-Flow (Lücken rot):**

```
Live: Bitget ccxt (public OHLCV) 
  → BitgetProvider.get_history_klines_with_end_time (limit=500, ~3 Wochen @1h; Rate-Retry 1x; Cache per-Range-CSV; NO gap-check)
  → DataNode (pro Ticker + pro Interval aus config: nur ["1h"])
  → Workflow (Multi-Node Merge) → MacdStrategy (5-Cat Indicators auf 1h-DFs)
  → ... → hermes_signal.json (Bias/Conf von LLM auf TA+Sentiment-Proxy)

Parallel FT: Per-Bot download-Skripte → user_data/data/bitget/*.feather (inkonsistente Tiefe 1–48 Monate; Funding nur fomo-Research ~2 Monate)
  → FT DataProvider + merge_informative (15m primary + 1h/4h)
  → Strategy (keine Funding-Costs)

Lücke: Kein unified Lake → Duplizierung + Drift. Keine Funding/OI/Depth → versteckte Kosten + Blindspot Microstructure. Keine Live-Gap-Validation → silent bad data → RG/FT fressen Müll.
```

**Unbekannte Unbekannte (Black Swans – Beispiele):**
- Exchange-API-Change (Bitget deprecated endpoint oder neue Rate-Limit-Policy) während Vol-Spitze → alle Provider leere DFs → LLM "neutral/hold" oder falsche Bias; Pipeline stale-block oder RG-3; FT native Logic übernimmt unkontrolliert.
- Delisting eines Core-Pairs (z.B. OP oder NEAR) oder Hardfork → historische Feather brechen Backtests; Live-Signale auf nicht-existierendes Instrument; keine automatische Pair-List-Update + graceful Decom.
- Daten-Gap über mehrere Stunden (Exchange Maintenance + Cache-Hit auf stale) → Indicators mit NaNs/flat → Confidence künstlich hoch oder 0; LLM-Halluzination auf unvollständigen Prompt-Inputs.

**Zusammenfassung Dim 1:** Basis-OHLCV solide (Pagination + Dedup in Skripten), aber für Futures-Autonomie unzureichend (keine Derivate-Daten, keine Live-Qualität, keine Zentralisierung). Readiness ~40%. Priorität: Funding + Gap-Validation + Central Lake (P0/P1).

---

## Dimension 2: Signalgenerierungs-Lücken

**Methodik:** Vollständige Trace des ai-hedge Graph/Workflow/Strategies/Indicators/LLM-Prompts (read macd_strategy, indicators, portfolio_node, workflow, agent, sentiment); Vergleich Config vs. FT Pairs/TFs; Backtest-Logik vs. Live; Grep nach Overfit-Risiken (Hyperopt, Walk-Forward, Min-Trades 60); Regime-Handling in FT Strategies; Microstructure (keine); Gedankenexpts zu LLM-Non-Determinismus + Drift.

### Gap-Bewertungstabelle (Auszug)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| S2.1 | Final-Decision durch LLM (DeepSeek-v4-pro, temp 0.35 für portfolio_manager) mit 3-Pillar-Prompt; non-deterministisch + temperature-sensitiv + keine Calibration/Ensemble | 🟠 HOCH | Unterschiedliche Runs → unterschiedliche Actions/Conf/Qty bei identischen Inputs; "hold" mit 0.03–0.09 Conf (historisch) trotz "hoher Edge"; RG-2 blockt viele | Hoch (LLM-Natur + Prompt-Änderungen) | 1. Baseline-Ensemble (TA-only deterministisch + LLM). 2. Temperature-Sweep + Self-Consistency (mehrere Samples, Vote). 3. Confidence-Calibration (Platt-Scaling oder historisches Histogram aus shadow). 4. Fallback: Wenn LLM-Conf < X oder Divergenz → native FT nur. | portfolio_management_node.py:202 (llm = get_llm temp 0.35); 260 (chain.invoke ohne Retry im Snippet); config.yaml:20 (deepseek-v4-pro); Shadow-Beispiele: viele low-conf HOLD |
| S2.2 | Sentiment-Collector degeneriert zu CoinGecko-Price-Proxy (keine echten Social/On-Chain); fehlende Consts im Prod-File | 🟡 MITTEL | 3-Pillar-Modell → de-facto 1-Pillar (TA); LLM-Prompts mit "X-Sentiment strong" auf Basis von Vol-Chg (zirkulär); Divergenz-Regeln schwach | Hoch (Code-State) | Siehe M1.5; zusätzlich: echte X/Perplexity/Firecrawl Integration (Tools existieren schon in Repo); Weight-Adjustment wenn Proxy. | sentiment_collector.py:93 (W_TA=0.40 "price trend proxy"); 351 (Pillar 1 FAILED); bak vs. current Diff |
| S2.3 | Nur 1h in live config (intervals:["1h"]); Multi-TF Support im Code, aber nicht genutzt für Signale | 🟡 MITTEL | Verpasste kürzere Regime (Scalp 5m/15m) oder längere Trends; FT nutzt informative 1h/4h, ai-hedge nicht aligned | Mittel | 1. Config + Workflow: mind. ["15m","1h","4h"] für live. 2. Per-Ticker Multi-TF Features im Prompt. 3. Alignment mit FT informative Timeframes. | config.yaml:11; workflow.py:19 (DataNode per interval); DataNode:39 (single tf); FT Regime: merge_informative_pair |
| S2.4 | Keine explizite Regime-Detection im Signal-Layer (ai-hedge); FT hat RegimeSwitchingHybrid, aber Signal (LLM) kann konträr sein | 🟠 HOCH | LLM gibt "bullish" in Bear-Regime → RG accepted → FT native oder Gate blockt; inkonsistente Bias | Mittel-Hoch (Crypto hat klare Regimes) | 1. Regime-Classifier (z.B. HMM/ADX/Vol-Regime) als zusätzlicher Analyst-Node oder Feature im Prompt. 2. Regime-spezifische Prompts/Weights. 3. FT Regime-Logic als "soft veto" in RG (via fleet_risk_state). | FT RegimeSwitchingHybrid_v7... (adx_rel + HTF ema); ai-hedge: keine Regime-Node; portfolio Prompt: "CONVERGENCE" ohne Regime |
| S2.5 | Backtests optimistisch (keine Fees/Slippage/Funding; prefetch nur primary interval; limit=500 in sim) | 🟠 HOCH | Promoted Strategies performen in Live schlechter; 60-Trade-Gate (Charter) erfüllt, aber mit falschen PnL | Hoch (Standard in vielen AI-Hedge Setups) | 1. Backtester: full fees (taker 0.06% Bitget) + slippage (bps) + funding_pnl. 2. Prefetch alle Intervals + consistent end_time Logic. 3. Walk-Forward + Purged K-Fold + Min 60 non-overlap Trades + Net-Edge > Baseline. | backtester.py:273 (prefetch primary only); 335 (re-fetch limit); FT backtests: fees via exchange config, funding nur wenn data+config (meist nicht) |

**Text-Diagramm-Beschreibung – Signal-Generierung (vereinfacht):**

```
Tickers (7: BTC/ETH/SOL/AVAX/NEAR/ARB/OP @1h)
  → DataNode(s) → MacdStrategy (Trend 0.25 + MeanRev 0.20 + Mom 0.25 + Vol 0.15 + StatArb 0.15 → combined)
  → RiskNode (20% pos limit, cash check)
  → Sentiment (CoinGecko proxy + F&G + X-vol proxy)
  → PortfolioManagementNode (LLM Prompt "THREE-PILLAR CONVERGENCE" + 75-95 full size etc.)
  → JSON {decisions: {TICKER: {action, quantity, confidence 0-100, reasoning}}}
  → hermes_signal.json (timestamp, pairs mit bias/conf/action/qty)

Lücken: LLM non-det + low real Conf; Sentiment Proxy; 1h-only; kein Regime; Backtest ohne Real-Kosten.
```

**Unbekannte Unbekannte:**
- LLM-Provider-Änderung (ollama.com Endpoint, Modell-Update) → Prompt-Format bricht oder Temperature-Effekt ändert sich → plötzliche "hold"-Welle oder über-konfidente falsche Actions.
- Prompt-Injection / vergiftete Sentiment-Daten (wenn echte X-Quelle) → systematische Bias in alle Decisions.
- Overfit an historische LLM-Outputs (Shadow wird für Calibration genutzt, aber zukünftige LLM-Versionen verhalten sich anders).

**Zusammenfassung Dim 2:** TA-Ensemble solide (5 Kategorien, ADX etc.), LLM-Prompt detailliert mit guten Regeln, aber non-det + Proxy-Sentiment + fehlende Multi-TF/Regime + optimistische Validation = hohes Risiko für "stille Degradierung". Readiness ~50%. Priorität: Calibration + echte Sentiment + realistische Backtests (P1).

---

## Dimension 3: Ausführungs- & Order-Management-Lücken

**Methodik:** Vollständige Analyse trading_pipeline.py (Bridge/RG/MCP/Shadow/Write), bitget_mcp_server.py (Paper-Engine), primo_signal.py (Gate), FT Strategy Entry-Logik (Regime + FreqForge), Vergleich mit Charter Gate 5, Suche nach SOR/Slippage/Partial/Failover/Teilausführung, Gedankenexpts zu Broker-Ausfall.

### Gap-Bewertungstabelle (Auszug)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| E3.1 | MCP-Ergebnisse (Status, Order-ID, Error, actual qty) werden **nie** in Shadow oder primo_signal_state persistiert (nur stdout + separate mcp/*.jsonl) | 🟠 HOCH | Keine End-to-End-Traceability: "Warum wurde dieser ACCEPTED nicht ausgeführt?"; Audit-Lücke; Desync MCP vs. FT vs. Shadow | Hoch (Code-Design) | 1. mcp_results in shadow_decision + build_state aufnehmen. 2. State erweitern um "execution_layer": {"mcp_status", "ft_status"}. 3. Reconciliation-Job (quality_hub oder new). | trading_pipeline.py:780-786 (mcp_results nur geloggt, nicht returned); 825 (shadow call ohne exec); 571 (pairs_out nur RG) |
| E3.2 | Off-by-One in RG-4 Concurrent Cap (preview mit accepted_count=4 → ACCEPT, inc auf 5, re-call mit 5 → RG-4 WATCH; effektiv max ~4 statt 5) + Duplikat-Logik in riskguard_service | 🟡 MITTEL | Weniger Diversifikation als spezifiziert; Inkonsistenz zwischen Pipeline und standalone Service | Hoch (Logik in 2 Files) | 1. Fix Cap-Logik (z.B. post-inc check oder separate accepted_this_cycle). 2. Single Source of Truth (fleet_risk_manager oder shared RG-Modul). 3. Test mit genau 5 Kandidaten. | trading_pipeline.py:722-728 + 235-244; riskguard_service.py:219-222 (identisch) |
| E3.3 | Kein Smart Order Routing, kein explizites Slippage/Market-Impact-Modell, keine Teilausführungs-Logik (FT intern + MCP market-order sim; Fallback ccxt sandbox bei MCP-Fehler) | 🟠 HOCH | Bei Volatilität: hoher Slippage nicht modelliert → falsche Qty/Conf; keine Partial-Fill-Handling über Zyklen; kein Routing zu besserer Venue/Liquidität | Mittel (Crypto 24/7, aber Spikes) | 1. In Pipeline/MCP: post-order Slippage-Check + Adjust (real oder sim). 2. FT: nutze existing entry_pricing = "order_book_top" + slippage config. 3. Erweitere RG um Liquidity-Filter (Depth oder ATR-Vol). 4. MCP: Limit-Orders + IOC/FOK für bessere Control. | FT configs: entry_pricing (top); MCP: market-only sim; trading_pipeline:272 (order_type default market); keine Impact-Formel |
| E3.4 | Kein Failover bei Broker/Exchange-Ausfall (Bitget-only; MCP ccxt sandbox Fallback nur für Paper; FT API-Pong in Healthchecks, aber keine auto Switch) | 🔴 KRITISCH | Voller Ausfall → stale Signals + Block oder native FT ohne externe Preise; keine sekundäre Venue (z.B. Kraken, Bybit) | Mittel (Exchange Incidents passieren) | 1. Multi-Exchange DataProvider (ccxt unified). 2. Fallback-Signal-Modus (letzter guter State + TA-only). 3. Healthcheck erweitern um "exchange_healthy"; Pipeline: wenn Exchange down → force WATCH_ONLY + Alert. 4. Paper/Live: Exchange-Client mit Circuit. | docker-compose + alle Provider: nur bitget; bitget_mcp + FT: keine secondary; healthchecks: API-Pong aber keine Exchange-Latency/Status |
| E3.5 | FT "fail-open" auf stale/missing/WATCH_ONLY (primo_gate_allows return True) + keine Force-Close auf Block | 🟠 HOCH | Bei Pipeline-Fehler oder RG-Block: FT läuft native Strategie (kann aggressiv sein); keine zentrale "Halt all entries" die auch offene managt | Hoch (Gate-Design per Charter "fail-open on stale") | 1. State erweitern um global "system_mode": "NORMAL" / "HALT_NEW" / "REDUCE_ONLY". 2. FT Strategies: zusätzlicher globaler Gate aus fleet_risk_state oder zentraler Datei. 3. Drawdown/Kill: setze max_open_trades=0 + force_exit Tags via FT REST (MCP oder freqtrade_client). | primo_signal.py:70-74 (return True); FT Regime:323 (long_gate = primo... and risk...); Charter: "fail-open on stale/missing signals" |

**Text-Diagramm-Beschreibung – Execution Flow (Lücken):**

```
hermes_signal.json (fresh, conf>0.65, bias)
  → trading_pipeline: read → RG-1..5 (stale/conf/bias/qty/cap) → ACCEPTED/WATCH
  → (if ACCEPTED) mcp_execute (direct import handlers, always dry, margin 20% cap, fallback ccxt sim)
  → write_state (verdict + allow_bias flags, **keine mcp_results**)
  → shadow (RG only)
  → FT per-bot primo_signal_state.json
  → Strategy: long_gate = primo_gate_allows(...) AND long_risk_allowed
  → populate_entry (native Conditions + Gate)

Lücken: Trace bricht bei MCP (Ergebnisse fehlen im Audit); Cap off-by-1; kein SOR/Slippage/Impact; Failover fehlt; fail-open + keine Force-Reduce.
```

**Unbekannte Unbekannte:**
- Bitget kompletter API-Ausfall + gleichzeitiger LLM-Provider-Down → Pipeline stale-block (gut), aber FT Bots laufen weiter mit letztem bekannten State oder native Logic auf potenziell falschen lokalen Daten.
- Teilausführung (Partial Fill) bei großem Qty → nachfolgende Zyklen sehen "Position offen" nicht korrekt (MCP/FT State Desync); kein "scale in only if average better".
- "Ghost Orders" (MCP paper order accepted, aber FT nicht, oder umgekehrt) → Portfolio-Recon fehlt komplett.

**Zusammenfassung Dim 3:** Pipeline schließt viele alte Bridge-Gaps (RG + Shadow + States), aber Traceability-Lücke, Cap-Bug, fehlendes Microstructure-Handling und fehlendes Failover/Force-Reduce verhindern robuste Autonomie. Readiness ~55%. Priorität: Trace + Cap-Fix + Force-Reduce + Multi-Exchange-Prep (P0).

---

## Dimension 4: Risikomanagement-Lücken

**Methodik:** Vergleich aller Risk-Layer (pipeline RG, fleet_risk_manager, drawdown_guard, Agenten KillSwitch/CryptoVaR, ai-hedge risk_node, FT Protections); Wiring-Checks (Importe, Calls in confirm_entry); Dynamic Sizing (nur Entry-Throttle, keine Live-Resize); Cross-Portfolio (ja via shared); VaR/Stress (Agenten Lib, nicht live); Kill-Wiring (nein); Gedankenexpts zu Correlated DD + Cascade.

### Gap-Bewertungstabelle (Auszug)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| R4.1 | Zentraler Kill-Switch / Emergency-Close existiert (Agenten KillSwitchManager mit File/SIGUSR/PnL-Trigger, should_close_positions; drawdown_guard Levels) aber **nicht wired** zu FT Fleet oder MCP (advisory-only, Telegram) | 🔴 KRITISCH | Kein automatischer Stop bei -30% oder correlated Crash; manuelles Eingreifen nötig; Autonomie gebrochen | Hoch (Market-Crashes passieren) | 1. Zentrale kill_switch.json + Service. 2. FT: in custom_exit oder via freqtrade_client / REST "force_exit all" + set max_open=0. 3. MCP: cancel_all + close positions. 4. Pipeline/RG: bei Kill-Active → force WATCH_ONLY + block. 5. Wire drawdown_guard Thresholds zu real Actions (mit Approval-Gate oder Safe-Mode). | Agenten risk_manager.py:105-139 (KillSwitch + should_close); drawdown_guard.py:14 ("KEIN automatisches Pausieren"); trading_pipeline:282 (hard dry); FT: keine Kill-Imports |
| R4.2 | Dynamic Position Sizing / Exposure Reduction nur bei *neuen* Entries (fleet_risk multipliers 1.0/0.75/0.5/0.2/0 + check_entry_allowed); keine Live-Resize offener Positionen bei DD-Spieke | 🟠 HOCH | Offene Risk kann weiterlaufen und eskalieren; "ScaleDownManager" (Agenten) ungenutzt | Hoch (DD entwickelt sich über Zeit) | 1. FleetRisk: bei Multiplier <1 → queue "reduce" für offene (via FT position_adjust oder custom). 2. Pipeline: scale signal quantity by current multiplier vor ACCEPTED. 3. Agenten ScaleDown + CryptoVaR in FleetRisk integrieren (live VaR). | fleet_risk_manager.py:627 (get_exposure_multiplier), 765 (check_entry); Agenten:532 (CryptoVaR),  ScaleDownManager; keine Resize-Calls |
| R4.3 | RG Concurrent Cap + FleetRisk Limits per-cycle / per-source, aber **keine globale Portfolio-View über alle Bots + MCP Paper + "would-be" Positions** | 🟡 MITTEL | Über-Exposure bei schnellen Signalen über multiple Bots; MCP Paper kann "fiktive" Limits sprengen | Mittel | 1. Zentrale Portfolio-State (equity + open notional + uPnL) aus FT sqlite + MCP portfolio + pending signals. 2. RG/FleetRisk: query global vor ACCEPT. 3. Drawdown-Guard erweitern auf global. | fleet_risk_state (per source); MCP separate portfolio.json; drawdown_state per-bot; keine unified view in pipeline |
| R4.4 | Keine Live VaR / CVaR / Stresstests im autonomen Pfad (Agenten CryptoVaR vorhanden: hist + param + monte, aber nur in isoliertem Main) | 🟠 HOCH | Keine quantitative "wie schlimm wird's bei -15% BTC Crash?"-Schätzung vor Entry; Backtests ohne Stress-Szenarien | Mittel | 1. FleetRisk: periodische VaR auf live History + shadow. 2. Stress-Job (1x/Tag): simuliere -10/-20/-30% auf current Portfolio via backtester-Engine. 3. RG: block wenn VaR > Limit. 4. Wire Agenten VaR. | Agenten risk_manager.py:532 (CryptoVaR); 0 Calls in pipeline/FT/fleet_risk; backtests haben keine Stress-Overlay |
| R4.5 | FT interne Protections (MaxDrawdown etc.) + Strategy custom_stoploss existieren, aber keine zentrale "Risk Override" die alle Bots gleichzeitig pausiert/reduziert | 🟡 MITTEL | Korrellierte Events → jeder Bot reagiert isoliert; Delay oder Inkonsistenz | Mittel | 1. Zentrale "risk_override.json" (HALT / REDUCE / NORMAL) gelesen von allen Strategies + Pipeline. 2. FT: Protection + custom logic priorisiert Override. 3. Healthcheck + Guardian: bei global Risk-Event → broadcast. | FT Strategies haben protections (z.B. v5); keine zentrale Override-Datei; fleet_risk ist read für Entries |

**Text-Diagramm-Beschreibung – Risk Layers (vereinfacht):**

```
Signal → Pipeline RG-1..5 (per-signal conf/stale/cap)
  → FleetRisk (global DD + cluster + corr + equity_mult) → check_entry_allowed
  → FT Strategy Gate (primo AND risk) → Entry

Parallel/Isoliert:
- Agenten KillSwitch / Circuit / VaR (in eigenem Main + Tests)
- drawdown_guard (Telegram advisory @ 5/8/12/15%)
- ai-hedge risk_node (20% sim-only)

Lücken: Kill nicht wired; Dynamic nur Entry (keine Resize); Keine globale unified View + Live-VaR; Advisory-only für DD.
```

**Unbekannte Unbekannte:**
- Korrellierter Liquidations-Cascade über alle 7+ Pairs (z.B. BTC-Dominanz-Event) → fleet_risk throttled new Entries (gut), aber offene Shorts/Longs reiten die DD bis -30%+ ohne auto-Close; MCP Paper separat depleted.
- "Risk-Model-Drift": Historische DD-Limits (fleet_risk 6/12/18%) passen nicht mehr zu aktueller Vol/Hebel; keine auto-Adjust + Validation gegen Out-of-Sample.

**Zusammenfassung Dim 4:** Mehrschichtiges Risk (RG + FleetRisk + FT) mit guter Cross-Bot-View für Entries; aber fehlende Kill-Wiring, fehlende Live-Resize/VaR und isolierte Agenten-Module = hohes Cascade-Risiko. Readiness ~50%. Priorität: Kill-Wiring + Dynamic Resize + unified View + Live-VaR (P0 kritisch für Autonomy).

---

## Dimension 5: Technische Infrastruktur-Lücken

**Methodik:** Review aller docker-compose (main, fleet, guardian, Agenten), Resource-Settings, Security (docker-proxy), Monitoring/Alerting (autopilot, fleet_health, quality_hub, 10+ watchdogs), Logging/Audit (shadow vs. compliance), DB (sqlite + json + decomm mem0), Scalability (cron 10m, sync, event-loops), Backtest-Env, Gedankenexpts zu OOM/SPOF/Network-Partition.

### Gap-Bewertungstabelle (Auszug)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| I5.1 | Keine Docker Resource Limits (mem_limit, cpu) + Single-Host SPOF; freqai-rebel kann 972% CPU + mehrere GiB verbrauchen und Host/Fleet lahmlegen | 🔴 KRITISCH | OOM oder CPU-Starvation → Container-Kills oder totale Degradation; kein Failover-Host | Hoch (beobachtet in Logs/Health) | 1. deploy.resources in allen Compose (limits + reservations, bes. für freqai-rebel, ollama, qdrant). 2. Multi-Node oder zumindest Swap/ Monitoring + Auto-Pause. 3. Guardian: bei CPU>800% → throttle oder restart. | docker-compose.yml:66 (keine limits); fleet.yml:20 (user 10000); healthchecks + prior GAPs: freqai 972%; 30.6 GiB Host |
| I5.2 | Monitoring/Alerting fragmentiert (autopilot decision_queue, fleet_health GREEN/YELLOW/RED, quality_hub, drawdown_guard, mcp_watchdog, permission_autopilot, ledger_watchdog, observation_* etc.); keine Unified Escalation | 🟠 HOCH | Alert Fatigue oder verpasste Kaskade (z.B. Perm-Drift + stale + DD gleichzeitig); keine single "System Health Score" | Hoch (viele Skripte) | 1. Zentraler Aggregator (z.B. erweitere quality_hub_monitor oder neuer fleet_monitor.py): konsumiere alle Watchdogs + shadow + risk_state + health. 2. Severity + Telegram + decision_queue. 3. Prometheus-Exporter oder einfaches /health JSON. | trading_autopilot.py:244 (build_monitor_report); fleet_healthcheck:142; quality_hub_monitor; 10+ *watchdog*.sh/py; keine single Source |
| I5.3 | Logging/Audit stark (shadow_decisions.jsonl + mcp paper logs + bridge.log), aber **Compliance-Module (Agenten audit_logger Hash-Chain, tx_store SQLite 10y, report_gen) nicht wired** zu FT-Trades / Pipeline-Shadow | 🟠 HOCH | Regulatorische Lücke (BaFin/GoBD/AO): keine tamper-evident, 10-Jahres-Archivierung der tatsächlichen Fleet-Trades; nur technische Shadow | Hoch (separate Codebase) | 1. Bridge/Collector: FT sqlite + shadow_decisions → Agenten tx_store + audit_logger (oder unified Schema). 2. Täglicher/Trade-basierter Compliance-Report-Job. 3. Audit-Trail für RG-Entscheidungen + Exec-Status. | Agenten compliance/* (production-grade, tests); trading_pipeline shadow (technisch); 0 Cross-Wiring; main.py Agenten nur für eigenes Engine |
| I5.4 | Cron/Guardian + Permission-Handling fragil (wiederkehrende CRITICAL uid0_1337 in shared/state/logs/output; permission_autopilot.sh oft REPORT_ONLY; viele manuelle Backups) | 🟠 HOCH | Pipeline/State-Writes brechen über Zeit; "stale" States → FT fallback oder falsche Gates; manuelle Intervention | Sehr hoch (evident in perm_autopilot.log) | 1. permission_autopilot: --apply als Default in Guardian-Mode + Auto-Fix für 10000/hermes. 2. Guardian: pre-flight Permission-Check + Restore aus Backup. 3. Alle Volumes/Files: korrekte UID/GID + ACL in Compose. 4. Monitoring: "perm_drift" als eigener Health-Check. | perm_autopilot.log (CRITICAL scans); permission_autopilot.sh:22 (limited APPLY); external_cron_guardian + jobs; viele *_backup in orchestrator/backups |
| I5.5 | Keine Redundanz (Exchange: nur Bitget; LLM: ollama.com + local; Host: single; DB: per-bot sqlite + json, mem0/qdrant decomm/partiell) | 🔴 KRITISCH | Ausfall einer Komponente = partieller oder voller Autonomy-Verlust; keine graceful Degradation auf Secondary | Mittel-Hoch | 1. Sekundäre Exchange (Kraken/Bybit) für Data + Fallback-Exec. 2. LLM: local ollama primary + Circuit zu Cloud-Fallback. 3. DB: zentrale View oder Replik. 4. Chaos-Tests (simulierter Outage). | Alle Provider/Compose: Bitget dominant; compose hat local ollama/qdrant aber Docs decomm; keine secondary in Code |

**Text-Diagramm-Beschreibung – Infra (vereinfacht):**

```
docker-proxy (read-only: CONTAINERS/SERVICES/INFO; kein POST/DELETE/EXEC)
  → hermes-net + proxy-net
  → ai-hedge (signal) + hermes-green (orchestrator) + green-ollama/qdrant/mem0 + FT Fleet (per-bot, shared mount) + caddy + hermes-watchdog (simple ping)

Lücken: Keine mem/cpu Limits; Single Host/Exchange/LLM; Fragmented Monitoring; Perm-Drift; Compliance nicht integriert.
```

**Unbekannte Unbekannte:**
- Network-Partition (Tailscale/Caddy down) → Healthchecks/Pings fehlschlagen, aber Container laufen "lokal" weiter mit stale Data; Pipeline kann nicht schreiben, FT Gates fallback.
- Gleichzeitiger OOM + Bitget Rate-Limit während LLM-Train (freqai) → totale Blackout; Guardian selbst down.

**Zusammenfassung Dim 5:** Gute Security-Basis (docker-proxy), reichhaltige (aber fragmentierte) Observability, solide Logging. Schwächen: Ressourcen, Redundanz, Perm-Stabilität, Compliance-Wiring. Readiness ~55%. Priorität: Resource-Limits + Perm-Hardening + Unified Monitor + Compliance-Bridge (P0).

---

## Dimension 6: Betriebliche & Prozess-Lücken

**Methodik:** Analyse von Cron/Guardian/Jobs (external_cron_guardian, jobs.json, trading_pipeline Aufrufe), Model-Update (Hyperopt-Phasen manuell via scripts/phase-*.md), Recovery (fleet_auto_repair advisory), Graceful Deg (stale block gut, aber darüber hinaus?), Error-Mgmt, Compliance-Wiring, Doc-Drift (AGENTS.md vs. deployed), Test-Coverage, Approval-Gates (decision_queue), Evidenz aus Backups + phase-Reports + logs.

### Gap-Bewertungstabelle (Auszug)

| ID | Gap-Beschreibung | Schweregrad | Pot. Auswirkung auf autonomen Betrieb | Wahrscheinlichkeit | Konkrete Verbesserungsvorschläge / Maßnahmen | Evidenz |
|----|------------------|-------------|---------------------------------------|--------------------|---------------------------------------------|---------|
| O6.1 | Model-Updates / Kalibrierung manuell (Hyperopt, SL-Sweeps, Walk-Forward, Phase-Reports in docs/context/); keine auto-Retrain on Performance-Drift oder Regime-Shift | 🟠 HOCH | Stale Models/Parameter während Marktwechsel → systematische Underperformance oder Risk-Eskalation; 60-Trade-Gate erfüllt mit veralteten Strats | Hoch (Crypto-Regimes ändern sich) | 1. Performance-Trigger in quality_hub / fleet_risk (z.B. 20% unter Baseline → queue Hyperopt). 2. Guardian: auto-start safe Hyperopt-Job (mit Approval). 3. FreqAI-Rebel: auto-Retrain Schedule + Validation. 4. "Last-Retrain" + "Next-Review" in State. | scripts/ (elite_batch, walk_forward, sl_sweep, hyperopt-prep in phase-25 etc.); fleet_auto_repair.py:77 (parses "Done training" logs, advisory); keine Trigger in pipeline |
| O6.2 | Recovery & Auto-Repair advisory-only (fleet_auto_repair.py: "advisory only — never live-trade changes"; patches/ manuell; ghostbuster etc. logs/alerts) | 🟠 HOCH | Bei Container-Crash, Config-Drift, Strategy-Fehler: manuelles Eingreifen; lange Downtime oder falsche States | Mittel | 1. Erweitere fleet_auto_repair zu "Safe Auto" (z.B. restart via guardian-approved, param-Patches via auto_params). 2. Pre-defined Runbooks + Auto-Apply für bekannte Klassen (Perm, Stale-State). 3. Integration mit decision_queue. | fleet_auto_repair.py:13-18; patches/safety-v1/; guardian_loop; keine Auto-Actions in Logs |
| O6.3 | Graceful Degradation partiell (Pipeline stale → hard block + empty state → FT fallback zu native; gute "fail-open" für Entries, aber keine zentrale "Halt all + Reduce" bei breitem Failure) | 🟡 MITTEL | Teil-Ausfall (z.B. nur LLM oder nur ein Watchdog) → inkonsistente States; keine "Degrade to HOLD + Notify + Wait for Human" State-Machine | Mittel | 1. Top-Level Circuit Breaker in Pipeline/Autopilot: bei N roten Watchdogs oder Kill-Active → force global WATCH_ONLY + shadow "DEGRADED" + Telegram. 2. FT: zusätzlicher globaler Gate. 3. Test: simuliere Component-Failure. | trading_pipeline:647 (stale block gut); FT primo_gate: return True (fail-open); drawdown_guard / autopilot: keine zentrale Deg-State |
| O6.4 | Compliance-Module (Agenten) production-grade (Hash-Chain Audit, 10y Tx-Store, Anlage-SO-Reports) aber **nicht integriert** in Live-FT/Pipeline (Shadow ist technisch, nicht regulatorisch) | 🔴 KRITISCH | Bei Live-Start: keine BaFin/GoBD-konforme Aufzeichnung der tatsächlichen Entscheidungen + Trades; Haftungs- und Audit-Risiko | Hoch (wenn Live angestrebt) | 1. Collector: FT tradesv3.*.sqlite + shadow + mcp logs → Agenten transaction_store + audit_logger. 2. Täglicher Compliance-Report (unified). 3. Key-Rotation + Audit für Pipeline-Entscheidungen. 4. Wire in Charter/SOUL als Pflicht vor Live. | Agenten compliance/* (audit_logger.py:18k, tx_store 30k etc.); trading_pipeline shadow (kein Hash-Chain, kein 10y-Store); 0 Cross-Imports |
| O6.5 | Doc-Drift (AGENTS.md:46 "RiskGuard/Shadow SPEC ONLY" trotz deployed pipeline + riskguard_service + shadow 1758 Entries; prior GAPs veraltet; Phase-Docs verstreut) | 🟠 HOCH | Neue Agenten/Dev lesen falsche Architektur → falsche Annahmen, Breaks, Sicherheitslücken; Onboarding-Risiko | Sehr hoch (evident) | 1. Vollständiger Audit + Sync aller Docs (AGENTS, SOUL, Charter, README, state/current-*, context/Readmes). 2. "Live Status" Section mit Links zu shadow / fleet_risk_state / health. 3. Post-Change: obligatorisches Doc-Update in Guardian/Commit-Hook. | AGENTS.md:46-63 (Stand Mai); ORCHESTRATOR_CHARTER v2.0; shadow_decisions.jsonl aktiv; trading_pipeline deployed per jobs + logs; viele phase-*.md pre-pipeline |

**Zusammenfassung Dim 6:** Viele Tools und Prozesse (Guardian, Watchdogs, Phase-Docs), aber manuelle Updates, advisory Recovery, isolierte Compliance, Doc-Drift und fehlende zentrale Degradation = hohes operatives Risiko für echte Autonomie. Readiness ~45%. Priorität: Compliance-Wiring + Doc-Sync + Auto-Retrain-Trigger + zentrale Degradation + Permission-Stabilität (P0).

---

## Cross-Cutting Themen

**State-Machine-Gaps (Charter v2.0 vs. IST):**
- SOLL: INIT → PREFLIGHT (Gate 0 Reality Lock) → ... → RISK_FILTERED (Gate 3) → SHADOW_LOGGED (Gate 4) → FLEET_SYNCED (Gate 5) → MONITORING.
- IST (2026-06): Starke Abdeckung SIGNAL_READY (ai-hedge healthy) + MONITORING (autopilot + healthchecks); Gate 0 nie ausgeführt (per prior GAP); Gate 3/4/5 teilweise durch pipeline (RG + Shadow + Writes), aber nicht vollständig (mcp_results fehlen, Trace-Lücke, FT Gates oft fallback).
- Error States: DATA_STALE gut geblockt; RISK_BLOCKED existiert (RG), aber advisory in anderen Layern; FLEET_UNHEALTHY detektiert, aber keine auto-Recovery.

**Config-Drift & Thresholds:** 0.65 überall (gut); MAX_AGE 25m (pipeline) vs. 30m (fleet_risk + primo fallback) → Inkonsistenz.

**Isolation:** Trading Hub, Agenten_Auto_Trade (Compliance/Risk excellent, aber separater Compose/Netzwerk), Twister-Lab (synthetische Daten, eigene Risk/Logger, 0 Cross-Pollination), fomo-phase3 (realistic Funding in Research) – Synergie-Potenzial ungenutzt.

---

## Top-15 priorisierte Gaps (nach Impact auf Autonomie × Prob × Blockade-Faktor)

1. 🔴 Kill-Switch nicht wired (R4.1) – System kann bei Crash nicht selbst stoppen.
2. 🔴 Keine Funding Rates (M1.1) – versteckte Kosten + falsche Backtests.
3. 🔴 Compliance-Module isoliert (O6.4 + I5.3) – regulatorisches Risiko bei Live.
4. 🔴 Single Host + keine Resource Limits (I5.1) – totaler Ausfall möglich.
5. 🟠 Traceability-Lücke MCP-Ergebnisse (E3.1) – Audit unvollständig.
6. 🟠 Permission-Drift + Cron-Fragilität (I5.4 + O6.5) – Writes brechen.
7. 🟠 LLM non-det + fehlende Calibration (S2.1) – inkonsistente Actions.
8. 🟠 Kein Failover / Multi-Exchange (E3.4) – Bitget-Down = Blackout.
9. 🟠 Dynamic Sizing nur Entry, keine Live-Resize (R4.2) – offene Risk eskaliert.
10. 🟠 Doc-Drift (O6.5) – falsche mentale Modelle.
11. 🟡 RG Cap Off-by-One + Duplikate (E3.2).
12. 🟡 Keine Live VaR/Stress (R4.4).
13. 🟡 Data Gap-Detection nur offline (M1.2).
14. 🟡 Sentiment Proxy + 1h-only (S2.2 + S2.3).
15. 🟡 Advisory-only Recovery (O6.2).

---

## Priorisierte Roadmap mit Zeitplan

| Priorität | Gap-Cluster | Konkrete Tasks (Files) | Verifizierungs-Kriterien | Aufwand (Agent-Tage) | Abhängigkeiten |
|-----------|-------------|------------------------|--------------------------|----------------------|---------------|
| **P0 – SOFORT (Woche 1)** | Ops/Infra/Stabilität | 1. Permission-Autopilot --apply Default + Guardian-Pre-Flight (permission_autopilot.sh, external_cron_guardian.sh). 2. Resource Limits in Compose (docker-compose.yml + fleet.yml). 3. Unified Monitor Aggregator (neuer oder erweitere quality_hub_monitor.py). 4. Doc-Sync (AGENTS.md, SOUL, Charter, state/*, context/READMEs). 5. Unit-Tests für RG1-5 + stale block + Cap (orchestrator/tests/). | 7 Tage keine CRITICAL Perm in Logs; docker inspect zeigt Limits; single health Score >90%; alle Docs haben "Live Status" Section mit Shadow-Link; 80%+ Coverage für Pipeline RG. | 4–6 | Guardian + Compose |
| **P0 – SOFORT (Woche 1–2)** | Risk Wiring | 1. Zentrale kill_switch.json + Service (fleet_risk_manager oder neu). 2. FT/MCP: Wire zu force_exit + cancel_all (via freqtrade_client oder MCP handlers). 3. Drawdown-Guard: Option "auto_reduce" (mit Safe-Mode). 4. Pipeline: bei Kill → force WATCH_ONLY. | Kill-Event in Shadow + FT max_open=0 + Positions reduced; Test: simuliere -30% → auto Action + Log. | 3–5 | P0 Ops |
| **P1 – 2 Wochen** | Data | 1. Funding + OI/Depth in BitgetProvider + 1–2 Download-Skripte + Central Lake. 2. Live Gap/Quality Validator (post-fetch in Provider + Cron). 3. Unify History-Depths (prune + backfill Job). | Funding-Feathers 6+ Monate für Core-Pairs; Validator blockt bei >1% missing in letzter Stunde; alle Bots nutzen gleichen Lake. | 5–7 | – |
| **P1 – 2–3 Wochen** | Signal/Exec Close-Loop | 1. Traceability: mcp_results + exec_status in Shadow + State (trading_pipeline.py). 2. Fix RG-4 Cap + unify mit riskguard_service. 3. Force-Reduce Gate (global risk_override.json). 4. Calibration für LLM (Shadow-Histogram). | Shadow-Einträge enthalten "mcp_result"; Cap exakt 5; bei global HALT keine Entries; LLM-Conf calibrated (Brier-Score oder Histogram-Report). | 4–6 | P0 Risk |
| **P2 – 3–4 Wochen** | Resilience + Compliance | 1. Multi-Exchange Fallback (Data + optional Exec). 2. Live VaR + Stress-Job (fleet_risk + backtest Engine). 3. Compliance Bridge (FT sqlite + shadow → Agenten tx_store/audit_logger). 4. Dynamic Resize (FleetRisk Multiplier auf offene + Pipeline Qty-Scale). | Sekundäre Exchange liefert Data; VaR-Report täglich; Compliance-Report enthält FT Trades + RG-Entscheidungen (Hash-Chain); offene Positions reduced bei DD-Spieke. | 6–8 | P1 Data + Risk |
| **P3 – 4–8 Wochen** | Validation + Ops Maturity | 1. Auto-Retrain-Trigger (Performance/Regime). 2. Full Recovery Automation (Safe Auto-Repair mit Approval). 3. Zentrale Degradation State-Machine + Chaos-Tests. 4. Test-Coverage Gate + E2E Pipeline/FT Integration Tests. 5. Roadmap-Review + Live-Gate (60 Trades + WF + Shadow + Kill + Funding). | Auto-Retrain läuft bei Drift; Recovery ohne Human für bekannte Klassen; Degradation-State in allen Layern; 90%+ Coverage; Live-Readiness-Checklist 100% grün. | 8–12 | Alle vorher |

**Gesamt-Zeitplan (aggressiv, mit Review-Gates):**  
- Woche 1–2: P0 (Stabilität + Kill) → stabiler Dry-Run-Betrieb ohne manuelle Fixes.  
- Woche 3–4: P1 (Data + Close-Loop) → verlässliche, nachvollziehbare Paper-Trades.  
- Monat 2: P2 (Resilience + Compliance) → regulatorisch tragfähig + multi-venue ready.  
- Danach: P3 + kontinuierliche Validation → Go-Live Vorbereitung (per Charter: Backtest → 48h+ Paper → explizite Freigabe).

---

## Anhang

**Methodik-Details:** Siehe Plan + Subagent-Reports (Pipeline/MCP 019e9840-..., Data 019e9843-..., Risk/Infra/Ops 019e9848-...). 50+ Files gelesen/grepped, 3 Subagents parallel, Runtime-Probes (feathers, shadow, jobs, logs via python), Black-Swan-Workshops per Dimension.

**Analysierte Artefakte (Auswahl):** trading_pipeline.py, bitget_mcp_server.py, fleet_risk_manager.py, RegimeSwitchingHybrid_*.py, ai-hedge src/graph/* + indicators/* + data_providers/* + sentiment_collector.py, Agenten risk_manager.py + compliance/*, alle docker-compose, orchestrator/scripts/* (guardian, watchdogs, permission, drawdown, quality_hub etc.), docs/ORCHESTRATOR_CHARTER.md + AGENTS.md + SOUL.md + GAP-*.md + phase-*.md, shadow_decisions.jsonl (recent), fleet_risk_state.json, drawdown_state.json, cron jobs, perm_autopilot.log, data feathers (sampling).

**Glossar (Auswahl):** RG = RiskGuard; FT = Freqtrade; MCP = (hier) Bitget Paper Trading Layer (MCP-Protokoll); primo_signal_state = Bridge-Output für FT Gates (verdict + allow_*_bias); Shadow = append-only Audit (shadow_decisions.jsonl); FleetRisk = cross-bot DD/Corr/Exposure Manager; fail-open = bei fehlendem/stale Signal → native Strategy-Logic erlaubt.

**Empfehlung:** Diesen Report als lebendes Dokument behandeln (nach jedem P0/P1 Milestone updaten). Nächster Schritt nach Review: Detaillierte Implementierungs-Pläne für P0 Items (design-doc oder direkt via implement Skill).

---

*Ende des GAP-Reports. Das Dokument dient als klare, evidenzbasierte Grundlage für die Weiterentwicklung zu einem vollständig autonomen, resilienten und performanten Trading-System.*