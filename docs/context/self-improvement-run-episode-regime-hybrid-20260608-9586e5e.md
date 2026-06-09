# Self-Improvement Run — episode-regime-hybrid-20260608-9586e5e

## 1. Run-Metadaten
- **Trigger:** post-forensics
- **Source-Forensics-Run-ID:** `forensics-20260608-001`
- **Episode-ID:** `episode-regime-hybrid-20260608-9586e5e`
- **Ziel-Bot:** `regime-hybrid`
- **Kandidat:** `Rollback der RR-FIX-Stack-Schicht für regime-hybrid`
- **Recovery-Candidates-Quelle:** `docs/context/recovery-candidates-2026-06-08.md`
- **Gewählter Kandidat:** Rank 1, `priority_score = 0.0322`, `recovery_confidence = 0.25`, `window PF = 0.5498`
- **Episode-Window:** letzte 180 Tage
- **Timerange im Backtest:** `20251210-20260608`

## 2. Phase 0–2: Preflight, Ranking, Episode-Vorbereitung
- `freqtrade --version` hat im Container `trading-freqtrade-regime-hybrid-1` geantwortet; Host-PATH ist dafür nicht relevant, der Backtest lief container-intern.
- `git rev-parse HEAD` ergab `9586e5e6f027465f16c4c66a071efbf0c4c9de62`.
- Aktive Strategy-SHA-256: `e9791f158da3441e04962cd2c398aa35686b52cbd2e4aeb5d36cbeb2153ee587`.
- Aktive Config-SHA-256: `f04546dd30f41da66e34be4c053a598d6b47f68cf5619e790ad29bad670e0c07`.
- Episode-Kopie der Strategy: `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration_episode_episode-regime-hybrid-20260608-9586e5e.py`.
- Episode-Kopie der Config: `freqtrade/bots/regime-hybrid/user_data/config_episode_episode-regime-hybrid-20260608-9586e5e.json`.
- Patch-Inhalt der Episode-Kopie:
  - Exit-Geometrie vereinfacht (`minimal_roi`, `stoploss`, `use_custom_stoploss`, `trailing_stop`).
  - ATR-Risk-Parameter neu gesetzt (`atr_sl_trend`, `atr_sl_range`, `atr_tp_trend`).
  - Fleet-Risk-Crash gefixt durch `self.risk_manager.state = self.risk_manager.refresh_from_disk()`.
- Validierung: AST-Parse der Strategy **OK**, JSON-Parse der Config **OK**.

## 3. Phase 3: Backtest
- Backtest lief erfolgreich im Container mit der Episode-Strategy und der Episode-Config.
- Ergebnisdatei wurde aus dem Freqtrade-Backtest-ZIP extrahiert: `freqtrade/bots/regime-hybrid/user_data/backtest_results/backtest-result-2026-06-08_06-23-32.zip`.
- Backtest-Summary:
  - **Trades:** 64
  - **Wins / Losses / Draws:** 44 / 20 / 0
  - **Winrate:** 68.75%
  - **Profit Factor:** 0.7567154683596228
  - **Total PnL:** -1.36097669 USDT
  - **Total PnL %:** -0.14%
  - **Max Drawdown:** 2.70349123 USDT / 0.27020842271817014%
  - **Trades pro Tag:** 0.36
  - **Market Change:** -40.77379459890796%
- Exit-Reasons:
  - **ROI:** 50 Trades, davon 44 Gewinner und 6 Verlierer
  - **Stop Loss:** 14 Trades, alle Verlierer
- Paar-Konzentration:
  - **100% der Trades:** `ARB/USDT:USDT`
  - Kein anderer Pair im Backtest handelte tatsächlich

## 4. Phase 4: Bewertung
- **Klassifikation:** `partial`
- **Warum nicht pass?** PF liegt weiterhin unter 1.0.
- **Warum nicht fail?** Der Run hat sich klar verbessert gegenüber dem Forensics-Baseline-Wert.
- **Baseline-Vergleich:** PF von `0.5498` auf `0.7567154683596228` → **+0.2069154683596228 PF**.
- **Outcome-Margin:** `-0.2432845316403772` relativ zur Pass-Schwelle PF=1.0.
- **Confidence:** `medium` — genügend Trades für eine robuste Tendenz, aber starke Ein-Pair-Konzentration.
- **Interpretation:** Die Episode hat das System aus dem klaren Verlustloch herausgezogen, aber noch nicht in einen profitablen Zustand gebracht.

## 5. Phase 5: Nächste Aktion
- **Next Action Label:** `FOLLOW_UP_EPISODE_REQUIRED`
- Empfohlene nächste Richtung: die nächste RR-FIX-Rollback-Schicht isoliert testen oder die ARB-Konzentration separat auditieren.
- Keine Unified-Diff-Ausgabe, weil die Episode **nicht** `pass` erreicht hat.
- Kein HARD_STOP: keine Live-Risiko-Eskalation, kein Credential-Fund, keine destructive Aktion.

## 6. Phase 6–7: Finalisierung & Artefakte
- **Backtest-Raw JSON:** `var/trading-shadowlock/backtests/episode-regime-hybrid-20260608-9586e5e-raw.json`
- **Reproducibility JSONL:** `var/trading-shadowlock/backtests/episode-regime-hybrid-20260608-9586e5e.jsonl`
- **Shadowlock-Log:** `var/trading-shadowlock/logs/2026/06/08.jsonl`
- **Shadowlock-State:** `var/trading-shadowlock/state/regime-hybrid.seq` → `1`
- **Shadowlock-Entry SHA-256:** `aa48991de13d67c6b57e0a934d233d204d5a5346d95062b84beae23e58747f0c`
- **Report-SHA256-Check:** aktive Strategy blieb unverändert; Post-Check entspricht dem git-HEAD-Hash.
- **Episode-Dateien:**
  - Strategy-Episode: `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration_episode_episode-regime-hybrid-20260608-9586e5e.py`
  - Config-Episode: `freqtrade/bots/regime-hybrid/user_data/config_episode_episode-regime-hybrid-20260608-9586e5e.json`
- **Backtest-ZIP SHA-256:** `4ffe989e102d80cfc6a03661316b8e77666b8e785d36eaea7db62eb795dd6f9c`
- **Errors:** keine
- **Warnings:**
  - 100% der Trades kamen aus nur einem Pair (`ARB/USDT:USDT`).
  - Die Episode ist verbessert, aber weiterhin unter der Profitabilitäts-Schwelle.
  - Der Markt war im Fenster stark negativ; das Ergebnis ist defensiv, aber noch nicht profitabel.
