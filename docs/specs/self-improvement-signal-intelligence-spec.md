# Self-Improvement Signal Intelligence Loop – Spec v1.0

**Status:** Draft v1.0 | **Date:** 2026-06-10 | **Owner:** Luke / GoEnviro Trading Systems  
**Complements:** `self-improvement-orchestrator-spec.md` (parameter/strategy episodes)  
**Location:** `trading-hub` (Control Plane) + integration points to `ai4trade-bot` (Rainbow Engine)

---

## 1. Purpose & Scope

Dieses Dokument definiert den **geschlossenen Lernkreislauf für Signal-Intelligenz** im Gesamtsystem.

Es ergänzt den bestehenden **Self-Improvement Orchestrator** (der sich um Strategie-Parameter und Code-Verbesserungen kümmert) um die **upstream** Ebene:

- Welche Signalquellen sind aktuell gut?
- Wie verändert sich ihre Qualität je nach Marktregime?
- Wie sollen die Gewichte im RainbowScorer automatisch angepasst werden?

**Ziel:** Ein robustes, regime-aware, weitgehend selbstlernendes Signal-Aggregationssystem, das mit minimaler manueller Pflege kontinuierlich besser wird und gleichzeitig höchste Safety-Standards einhält.

**Nicht im Scope (bleibt im Orchestrator):**
- Backtest-Episoden für Strategie-Parameter
- Code-Patches an Freqtrade-Strategien
- Forensics auf Trade-History

---

## 2. Vision & Design Principles

### Kernprinzipien

| Prinzip              | Beschreibung                                                                 | Umsetzung                                      |
|----------------------|------------------------------------------------------------------------------|------------------------------------------------|
| **Closed Loop**      | Jeder Trade fließt automatisch zurück ins Lernen                              | Outcome Tracker → Attribution → Meta-Learner   |
| **Regime-Aware**     | Kein globales Lernen – Qualität wird pro Marktregime bewertet               | Regime Detector + regime-spezifische Weights   |
| **Low Maintenance**  | Kein tägliches "gucken" nötig                                            | Hermes-Cronjobs + automatische Proposals       |
| **Safety First**     | Nie blind updaten – immer Validierung + Circuit Breaker                     | Backtest Gate + Auto-Rollback + Per-Source Guards |
| **Komplementär**   | Liefert bessere Signale an den Orchestrator                                  | Weight-Proposals als spezielle Episode-Art     |
| **Erweiterbar**      | Neue Signalquellen (Kollege, WhatsApp, etc.) mit minimalem Aufwand           | Plugin-Architektur + standardisierte `CryptoSignal` |

---

## 3. Geschlossener Lernkreislauf (Closed Loop)

```mermaid
flowchart TD
    A[Signal Layer<br/>Rainbow Collectors + "Kollege" + zukünftige Quellen] --> B[RainbowScorer<br/>+ AI Evaluation]
    B --> C[Unified Signal Stream<br/>mit rainbow_score, regime, source]
    C --> D[trading-hub / Primo / Hermes
    Decision Engine]
    D --> E[Freqtrade Dry-Run Execution
    (später Live mit Gates)]
    E --> F[Trade Outcome Tracker
    mit verknüpften signal_ids + full context]
    F --> G[Performance Attribution Engine
    pro Source + pro Regime]
    G --> H[Meta-Learner
    Weight Optimizer + Proposal Generator]
    H --> I[Validation Gate
    Backtest + Safety Checks]
    I --> J{Deutliche Verbesserung?}
    J -->|Ja + sicher| K[Weight Update
    versioniert + hot-reload]
    J -->|Nein / Risk| L[Circuit Breaker
    + Auto-Pause Source]
    K --> A
    L --> A
    style G fill:#e0f2fe
    style H fill:#bae6fd
    style I fill:#fef3c7
```

**Phasen:**
1. **Signal Generierung & Scoring** (ai4trade-bot)
2. **Execution & Outcome Tracking** (trading-hub)
3. **Attribution & Lernen** (neu: learning/)
4. **Validierung & Update** (integriert mit Orchestrator)

---

## 4. Datenmodelle (Data Models)

Alle Modelle als Pydantic v2 Models (bereits im Projekt verwendet). Zentrale Speicherung in `learning/trade_outcomes.db` (SQLite) + JSONL Shadowlock-Erweiterung.

### 4.1 Core Models

```python
# learning/models.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional, List
from enum import Enum

class MarketRegime(str, Enum):
    STRONG_TREND_UP = "strong_trend_up"
    STRONG_TREND_DOWN = "strong_trend_down"
    WEAK_TREND = "weak_trend"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CHOPPY = "choppy"

class SignalSource(str, Enum):
    RAINBOW_TA = "rainbow_ta"
    RAINBOW_TWITTER = "rainbow_twitter"
    RAINBOW_NEWS = "rainbow_news"
    KOLLEGE = "kollege"          # der starke zweite Signalgeber
    EXTERNAL_WEBHOOK = "external_webhook"
    # zukünftig: whatsapp, polygon, etc.

class TradeOutcome(BaseModel):
    trade_id: str
    bot_name: str
    pair: str
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    max_drawdown_during_trade: float
    holding_bars: int
    
    # Signal Context zum Entscheidungszeitpunkt
    triggering_signals: List[dict] = Field(..., description="Liste von {signal_id, source, rainbow_score, confidence, ai_evaluation}")
    rainbow_score_at_entry: float
    final_decision: Literal["long", "short", "neutral"]
    
    # Regime Context
    regime_at_entry: MarketRegime
    regime_at_exit: MarketRegime
    regime_confidence: float = 0.8
    
    # Decision Context
    active_weights: dict  # {source: weight}
    score_threshold_used: float
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

```python
class SignalAttribution(BaseModel):
    source: SignalSource
    regime: MarketRegime
    period_start: datetime
    period_end: datetime
    
    n_signals: int
    n_trades_triggered: int
    winrate: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    sharpe_like: Optional[float] = None
    
    contribution_to_total_pnl: float  # wie viel P&L kam von dieser Quelle
    quality_score: float  # 0.0 - 1.0 (kombiniert alle Metriken)
```

class WeightProposal(BaseModel):
    proposal_id: str
    created_at: datetime
    source: str  # "meta_learner" | "manual"
    regime: Optional[MarketRegime] = None  # None = global
    old_weights: dict
    new_weights: dict
    expected_improvement: dict  # PF, expectancy, etc.
    backtest_validation_id: Optional[str] = None
    status: Literal["proposed", "validated", "applied", "rejected", "rolled_back"]
    justification: str
```
```

### 4.2 Speicherung

- **Primär:** `learning/trade_outcomes.db` (SQLite mit Timescale-Style Tabellen oder einfache relational)
- **Shadowlock-Erweiterung:** JSONL Logs mit `signal_provenance` Events
- **Config:** `rainbow/config/weights_regime_aware.yaml` (versioniert im Git)

---

## 5. Regime Detector (Detailliert)

**Warum der wichtigste Hebel:**
Ein Signal, das in starken Trends super funktioniert, kann in ranging Märkten katastrophal sein. Globales Lernen zerstört Performance.

### 5.1 Regime-Klassen (v1)

| Regime                | Beschreibung                              | Typische Charakteristika                  | Bevorzugte Signal-Typen      |
|-----------------------|-------------------------------------------|-------------------------------------------|------------------------------|
| `strong_trend_up`     | Klarer Aufwärtstrend                     | Hoher ADX, Price >> EMA200, steigender Slope | Momentum + Trend-Following   |
| `strong_trend_down`   | Klarer Abwärtstrend                     | Hoher ADX, Price << EMA200                | Short-Bias + Momentum        |
| `weak_trend`          | Schwacher Trend                           | Mittlerer ADX, Price nahe EMA             | Selective Trend              |
| `ranging`             | Seitwärts / Mean-Reversion               | Niedriger ADX, Price oszilliert um EMA    | Mean-Reversion, Oscillatoren |
| `high_volatility`     | Hohe Volatilität (oft choppy)            | Hoher ATR/Price                           | Tight Stops, selektiv        |
| `low_volatility`      | Niedrige Volatilität                     | Niedriger ATR                             | Breakout-Strategien          |
| `choppy`              | Hohe Vol + kein klarer Trend              | Hoher ATR + niedriger ADX                 | Sehr selektiv / pausieren    |

### 5.2 Berechnungslogik (rule-based, robust, 5m/15m/1h Timeframes)

```python
# learning/regime_detector.py

import pandas as pd
import talib as ta

def detect_regime(df: pd.DataFrame, timeframe: str = "15m") -> tuple[MarketRegime, float]:
    """
    Gibt (regime, confidence) zurück.
    df muss OHLCV mit Spalten ['open','high','low','close','volume'] haben.
    """
    close = df['close']
    high = df['high']
    low = df['low']
    
    adx = ta.ADX(high, low, close, timeperiod=14)
    plus_di = ta.PLUS_DI(high, low, close, timeperiod=14)
    minus_di = ta.MINUS_DI(high, low, close, timeperiod=14)
    atr = ta.ATR(high, low, close, timeperiod=14)
    ema200 = ta.EMA(close, timeperiod=200)
    
    last_adx = adx.iloc[-1]
    last_plus = plus_di.iloc[-1]
    last_minus = minus_di.iloc[-1]
    last_atr_pct = (atr.iloc[-1] / close.iloc[-1]) * 100
    last_price_vs_ema = (close.iloc[-1] - ema200.iloc[-1]) / ema200.iloc[-1] * 100
    
    # Slope des Preises über letzte 20 Kerzen
    slope = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
    
    confidence = 0.7  # Basis
    
    if last_adx > 35:
        if last_plus > last_minus and slope > 1.5:
            return MarketRegime.STRONG_TREND_UP, min(0.95, confidence + 0.2)
        elif last_minus > last_plus and slope < -1.5:
            return MarketRegime.STRONG_TREND_DOWN, min(0.95, confidence + 0.2)
    
    if last_adx < 20 and last_atr_pct < 1.8:
        return MarketRegime.RANGING, confidence
    
    if last_atr_pct > 3.5 and last_adx < 25:
        return MarketRegime.CHOPPY, 0.85
    
    if last_atr_pct > 3.0:
        return MarketRegime.HIGH_VOLATILITY, 0.75
    
    if last_adx > 25:
        return MarketRegime.WEAK_TREND, 0.65
    
    return MarketRegime.LOW_VOLATILITY, 0.6
```

**Erweiterung (später):** HMM, einfacher Transformer auf Multi-Timeframe Features, oder LLM-basierte Regime-Narrative (DeepSeek 4 Pro, temp=0.1).

### 5.3 Integration

- Jeder `CryptoSignal` bekommt `regime` + `regime_confidence` angehängt
- Jeder `TradeOutcome` speichert `regime_at_entry` + `regime_at_exit`
- Regime Detector läuft als Service oder wird bei jedem Scoring-Call aufgerufen

---

## 6. Performance Attribution Engine

**Trigger:** Täglich 03:00 via Hermes Cron **oder** nach 50 abgeschlossenen Trades.

Berechnet für jede Quelle + jedes Regime:

- Winrate, Expectancy, Profit Factor, Max DD, Trade Count
- Anteil am Gesamt-P&L
- "Quality Score" (gewichtete Kombination)

**Output:** `SignalAttribution` Records + aggregierter Report (Markdown + JSON)

---

## 7. Meta-Learner & Weight Optimizer (Kern des Self-Improvement)

### 7.1 Grundlogik (v1 – robust & erklärbar)

```python
# learning/meta_learner.py

def calculate_quality_score(attribution: SignalAttribution) -> float:
    """
    Kombiniert mehrere Metriken zu einem stabilen Quality Score (0.0 - 1.0).
    """
    pf = attribution.profit_factor
    wr = attribution.winrate
    exp = attribution.expectancy
    dd = attribution.max_drawdown
    n = attribution.n_trades_triggered
    
    if n < 15:
        return 0.4  # zu wenig Daten → konservativ
    
    score = (
        min(pf / 2.0, 1.0) * 0.35 +           # Profit Factor
        wr * 0.25 +                            # Winrate
        max(0, min(exp * 5, 1.0)) * 0.20 +     # Expectancy
        max(0, (10 - min(dd, 15)) / 10) * 0.20 # Drawdown (negativ gewichtet)
    )
    return max(0.1, min(0.95, score))

def update_weights(
    current_weights: dict,
    attributions: list[SignalAttribution],
    regime: MarketRegime | None = None,
    learning_rate: float = 0.15
) -> dict:
    """
    Neue Gewichte berechnen. EMA-Style Update.
    """
    new_weights = current_weights.copy()
    
    for attr in attributions:
        src = attr.source
        if src not in new_weights:
            continue
        
        quality = calculate_quality_score(attr)
        old_w = new_weights[src]
        
        # Regime-spezifisch oder global
        multiplier = 1.0
        if regime and attr.regime == regime:
            multiplier = 1.3  # stärkeres Update im aktuellen Regime
        
        target_w = old_w * (0.6 + 0.4 * quality) * multiplier
        new_w = old_w * (1 - learning_rate) + target_w * learning_rate
        
        new_weights[src] = max(0.05, min(1.8, new_w))  # Safety bounds
    
    return new_weights
```

### 7.2 Weight Proposal Generation

Der Meta-Learner schreibt **nie direkt** in die Live-Config.
Er erzeugt stattdessen ein `WeightProposal` + Begründung (inkl. "Warum hat Quelle X in Regime Y schlecht performt?") .

**Später erweiterbar mit LLM (DeepSeek 4 Pro, temp=0.1):**
- Reiche narrative Begründung generieren
- Hypothesen erzeugen ("Kollege ist in ranging Märkten zu aggressiv")
- Vorschläge für neue Filter-Regeln

### 7.3 Integration mit existierendem Orchestrator

Weight-Updates können als spezielle `proposal_type: "signal_weight_update"` an den Orchestrator übergeben werden.
Der Orchestrator führt dann einen Backtest mit alten vs. neuen Weights durch und entscheidet über Promotion.

---

## 8. Validation Gate & Safety Layer

**Nie ohne Gate updaten!**

1. Meta-Learner erzeugt Proposal
2. **Validation Gate** (nutzt Orchestrator-Infrastruktur):
   - Backtest auf letzten 60–120 Tagen mit alten vs. neuen Weights
   - Muss mind. +15% besseren Expectancy / PF haben
   - Keine Verschlechterung in kritischen Regimen
3. Bei Bestehen → `READY_FOR_REVIEW` oder Auto-Promotion (wenn Schwellen + Risiko niedrig)
4. **Auto-Rollback**: Wenn in den nächsten 25 Trades die Performance schlechter ist als vorher → alte Weights automatisch wiederherstellen + Incident loggen

**Circuit Breaker (pro Quelle):**
- Wenn Winrate in letzten 30 Signalen < 35% in einem Regime → Weight temporär auf 0.25 cappen
- Globaler Breaker: Gesamt-Drawdown > 8% in 24h → neue Trades pausieren + Alert

---

## 9. Automatisierung & Low-Maintenance (Hermes Integration)

Hermes triggert via Cron / Event:

| Job                              | Trigger                     | Frequenz          | Verantwortlich          |
|----------------------------------|-----------------------------|-------------------|-------------------------|
| Regime Detector Refresh          | Market Data Update          | alle 5-15 min     | Rainbow Service         |
| Attribution + Meta-Learner Run   | Cron + Trade Count          | täglich 03:00 + nach 50 Trades | learning/meta_learner.py |
| Weight Proposal Validation       | Neues Proposal              | bei Erstellung    | Orchestrator            |
| Health Check aller Signalquellen | Cron                        | alle 30 min       | Dashboard + Alerts      |

Alle Configs (`weights_regime_aware.yaml`) sind versioniert und hot-reload-fähig.

---

## 10. Dashboard-Erweiterungen (trading-hub/dashboard.py)

Neue Cards / Tabs:

- **Signal Source Health** (pro Quelle + Regime)
  - Aktueller Weight
  - Quality Score (letzte 7/30 Tage)
  - Winrate / PF pro Regime
  - Letztes Attribution-Run
- **Learning Status**
  - Letzter Meta-Learner Run + Proposed Changes
  - Circuit Breaker Status
  - Auto-Rollback History
- **Drill-down:** Klick auf Quelle → detaillierte Attribution + Trade-Liste

Plugin-Mechanismus: Neue Quellen erscheinen automatisch.

---

## 11. Phasenweiser Rollout (realistisch & sicher)

| Phase | Zeitraum     | Fokus                                      | Deliverable                                      | Risiko |
|-------|--------------|--------------------------------------------|--------------------------------------------------|--------|
| 1     | Woche 1-2    | Logging & Attribution                      | TradeOutcome Tracker + Regime Detector + erste Reports | Niedrig |
| 2     | Woche 3-4    | Meta-Learner + Proposals                   | Automatische Quality-Berechnung + Weight-Proposals | Mittel |
| 3     | Woche 5-6    | Validation Gate + Orchestrator Integration | Backtest-Gate + erste kontrollierte Updates      | Mittel |
| 4     | ab Woche 7   | Controlled Auto-Update + starke Safety     | Auto-Update bei klaren Verbesserungen + Rollback | Kontrolliert |

---

## 12. Benötigte neue Komponenten

| Komponente                        | Pfad im trading-hub          | Priorität | Geschätzter Aufwand |
|-----------------------------------|------------------------------|----------|---------------------|
| Trade Outcome Tracker             | `learning/outcome_tracker.py` | Hoch     | Mittel              |
| Regime Detector                   | `learning/regime_detector.py` | Hoch     | Mittel              |
| Attribution Engine                | `learning/attribution.py`     | Hoch     | Mittel-Hoch         |
| Meta-Learner                      | `learning/meta_learner.py`    | Hoch     | Mittel              |
| Weight Config Manager             | `rainbow/config/` (shared)    | Hoch     | Niedrig             |
| Validation Gate (Orchestrator-Erweiterung) | `orchestrator/`          | Mittel   | Mittel              |
| Circuit Breaker Service           | `learning/circuit_breaker.py` | Hoch     | Niedrig-Mittel      |
| Dashboard Cards                   | `dashboard.py`                | Mittel   | Niedrig             |

---

## 13. Offene Fragen & Nächste Schritte

**Offen (bitte priorisieren):**
- Wie genau sieht die Schnittstelle zum "Kollegen" aus? (Webhook? Polling? Welches Format?)
- Soll der Regime Detector auch LLM-unterstützt Narrative erzeugen (DeepSeek)?
- Wie tief soll die Integration mit dem existierenden Orchestrator gehen (Weight-Proposals als eigene Episode-Art)?
- Wo soll die Trade-Outcome DB liegen (trading-hub vs. shared Volume)?

**Nächste konkrete Schritte (empfohlen):**
1. `learning/regime_detector.py` als erstes kleines, testbares Modul bauen
2. Trade-Outcome-Tracking in `primo/` oder `bridge/` implementieren (wichtigster Enabler)
3. Erste manuelle Attribution-Reports laufen lassen und analysieren
4. Meta-Learner v1 (EMA, regime-aware) bauen
5. WeightProposal-Schema mit Orchestrator-Team abstimmen

---

**Dieses Dokument ist die verbindliche Planungsgrundlage für den Signal-Intelligence-Self-Improvement-Loop.**
Es wird direkt ins Repository übernommen und dient als Referenz für alle weiteren Implementierungen.

---

*Erstellt mit tiefer Integration der bestehenden Self-Improvement-Orchestrator-Architektur und Rainbow-Engine.*
