# SI v2 ↔ ai4trade-bot Compatibility Matrix

> **Read-Only Comparison** — No code imports, no vendoring.
> SI v2 branch: feat/si-v2-foundation @ 1d2076d
> ai4trade-bot @ 55b8642

---

## Compatibility Table

| SI v2 Module | ai4trade-bot Equivalent | Overlap | Decision | Rationale |
|-------------|------------------------|---------|----------|-----------|
| `state/schemas.SafeParameters` | `CanonicalSignalEnvelope.confidence, risk_score` | 🟡 Partial | **Keep separate** | Different abstraction level: strategy params vs signal metadata |
| `state/schemas.BacktestResult` | `core/outcomes/model.SignalOutcome` | 🟡 Partial | **Adapt schema** | Both track outcome of a decision; models differ structurally |
| `state/schemas.AnalysisResult` | `core/market_signals.MarketSignalAnalyzer` | 🟢 Low | **Keep separate** | SI v2 window analysis (12h/24h/72h) vs market state signals |
| `adapters/FreqtradeAdapter` | `integrations/freqtrade_bridge.FreqtradeBridge` | 🟡 Partial | **Reuse via adapter** | Bridge produces advisory dicts; SI v2 needs typed Protocol |
| `adapters/DockerAdapter` | — | 🟢 None | **Keep separate** | No Docker in ai4trade-bot |
| `adapters/TelegramAdapter` | `core/notifications/telegram_sink.TelegramSink` | 🟡 Partial | **Adapt schema** | TelegramSink is watchdog-focused; SI v2 needs approval messages |
| `observe/trade_exporter` | `core/outcomes` | 🟡 Partial | **Keep separate** | TradeExporter: Freqtrade trade history → OutcomeRepository: signal outcome |
| `analyze/performance_analyzer` | `core/market_signals` | 🟢 Low | **Keep separate** | Performance vs market analysis |
| `propose/safe_parameters` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `propose/strategy_mutator` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `propose/similarity_checker` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `backtest/backtest_runner` | — | 🟢 None | **Keep separate** | Not present in ai4trade-bot |
| `backtest/walk_forward` | — | 🟢 None | **Keep separate** | Not present in ai4trade-bot |
| `approve/approval_gate` | `core/signals/risk_gate.RiskGate` | 🟡 Partial | **Reuse via adapter** | Different domains: signal risk vs deployment approval |
| `deploy/rollback_plan` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `deploy/deployment_plan` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `deploy/shadow_mode` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| `cron/generator` | — | 🟢 None | **Keep separate** | Unique to SI v2 |
| — | `CanonicalSignalRegistry` | 🟢 None | **Ignore for Phase F** | Signal lifecycle storage — upstream dependency |
| — | `ConfidenceModulator` | 🟢 None | **Ignore for Phase F** | Upstream intelligence layer |
| — | `Watchdog` | 🟡 Partial | **Deprecate SI v2 duplicate?** | Similar concept; integration via NotificationSink Protocol |

---

## Canonical Ownership Decisions

| Concept | Owner | Rationale |
|---------|-------|-----------|
| **Signal Model** | ai4trade-bot (`CanonicalSignalEnvelope`) | Mature, 1048 tests, live-trading-gated |
| **Risk Gate** | ai4trade-bot (`RiskGate`) | 5-rule safety check, shared with signal pipeline |
| **Confidence Scoring** | ai4trade-bot (`ConfidenceModulator`) | Mature modulation; SI v2 should consume, not duplicate |
| **Outcome Tracking** | ai4trade-bot (`OutcomeRepository`) | SQLite persistence, evaluation logic |
| **Freqtrade Bridge** | ai4trade-bot (`FreqtradeBridge`) | Read-only advisory; SI v2 consumes via Protocol |
| **Notification Layer** | ai4trade-bot (`TelegramSink`) | Working Telegram integration; SI v2 needs extended format |
| **Watchdog/Health** | 🔄 **Undecided** | Both have similar concepts; need integration design |
| **Strategy Mutation** | SI v2 (`strategy_mutator`) | Unique to SI v2 mutation pipeline |
| **Backtest Runner** | SI v2 (`backtest_runner`) | Unique to SI v2 |
| **Walk-Forward** | SI v2 (`walk_forward`) | Unique to SI v2 |
| **Deployment Orchestration** | SI v2 (`deployment_plan`) | Unique to SI v2 |
| **Shadow Mode** | SI v2 (`shadow_mode`) | Unique to SI v2 |
| **Rollback** | SI v2 (`rollback_plan`) | Unique to SI v2 |
| **Safe Parameters** | SI v2 (`safe_parameters`) | Unique to SI v2 |

---

## Recommended Integration Points

### High Priority (Phase G)

| Integration | Type | SI v2 Interface | ai4trade-bot Consumer |
|-------------|------|----------------|----------------------|
| Signal Provider | Protocol adapter | `SignalProviderProtocol` | `CanonicalSignalRegistry` |
| Outcome Provider | Protocol adapter | `OutcomeProviderProtocol` | `OutcomeRepository` |
| Risk Gate | Protocol adapter | `RiskGateProviderProtocol` | `RiskGate` |

### Medium Priority (Phase H)

| Integration | Type | SI v2 Interface | ai4trade-bot Consumer |
|-------------|------|----------------|----------------------|
| Confidence Modulation | Protocol adapter | `ConfidenceProviderProtocol` | `ConfidenceModulator` |
| Freqtrade Advisory | Direct dict | `FreqtradeBridge` output | Already compatible |

### Low Priority (Post v2)

| Integration | Type | SI v2 Interface | ai4trade-bot Consumer |
|-------------|------|----------------|----------------------|
| Watchdog | Cross-system | `NotificationSink` Protocol | `Watchdog` |
| Telegram Notification | Shared adapter | `TelegramAdapter` Protocol | `TelegramSink` |