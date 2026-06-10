# ai4trade-bot Integration Readiness Audit

> **Read-Only Audit** — No code imports, no vendoring, no submodules.
> Audit date: 2026-06-10
> Repository: GoLukeEnviro/ai4trade-bot @ commit 55b8642 (master)

---

## 1. Repository Overview

| Property | Value |
|----------|-------|
| **Remote** | `https://github.com/GoLukeEnviro/ai4trade-bot.git` |
| **HEAD** | `55b8642` (docs: final signal runtime baseline closure report) |
| **Python Source Files** | 133 (excluding `.venv`, `__pycache__`, `site-packages`) |
| **Test Count** | 1048 (per closure report) |
| **Active Branch** | `master` (feature branches for AI, derivatives, bridge, etc.) |
| **Runtime State** | 2 SQLite databases, optional JSON cache, in-memory caches |

---

## 2. Capability Map

### 2.1 Signal Pipeline (Core)

```
CryptoSignal (raw) ─→ AIEvaluation (LLM eval) ─→ CanonicalSignalEnvelope
                                                          │
                                    ┌─────────────────────┤
                                    │                     │
                               RiskGate          CanonicalSignalRegistry
                                    │                     │
                                    ▼                     ▼
                          ConfidenceModulation       SQLite persistence
                                    │
                                    ▼
                            FreqtradeBridge
                                    │
                                    ▼
                          Advisory dicts (dry_run_only, can_execute=False)
```

| Module | Purpose | Key Concepts |
|--------|---------|-------------|
| `core/signals/envelope.py` | Universal signal container | `CanonicalSignalEnvelope`, `Actionability` (forces dry_run) |
| `core/signals/risk_gate.py` | 5-rule safety check | `min_confidence=0.3`, `stale_threshold=300s`, data quality gate |
| `core/signals/registry.py` | SQLite signal lifecycle | `CanonicalSignalRegistry`, `SignalLifecycle` state machine |
| `core/signals/confidence_modulation.py` | Conservative confidence reduction | `ConfidenceModulator`, caps final ≤ raw, never increases |
| `core/signal_model.py` | Legacy Signal+Intent | Frozen dataclasses, `mode="dry_run"` forced |
| `core/market_signals.py` | OHLCV → market state | Volume, volatility, feed health analysis; pandas only |

### 2.2 Outcome Tracking

| Module | Purpose | Key Concepts |
|--------|---------|-------------|
| `core/outcomes/model.py` | Outcome data model | `SignalOutcome`, `OutcomeLabel` (WIN/LOSS/NEUTRAL/EXPIRED) |
| `core/outcomes/repository.py` | SQLite outcome persistence | `OutcomeRepository`, separate DB from registry |
| `core/outcomes/evaluator.py` | Outcome evaluation logic | Price window evaluation |

### 2.3 Integrations

| Module | Purpose | Key Concepts |
|--------|---------|-------------|
| `integrations/freqtrade_bridge.py` | Read-only advisory bridge | 8 safety checks, confidence threshold (0.6), risk threshold (0.7) |
| `integrations/freqtrade_strategy.py` | Freqtrade strategy class | Compatible with Freqtrade strategy interface |
| `integrations/primoagent_bridge.py` | PrimoAgent integration | External agent bridge |

### 2.4 Infrastructure

| Module | Purpose | Key Concepts |
|--------|---------|-------------|
| `core/watchdog.py` | Heartbeat file monitor | `NotificationSink` Protocol, file-based health checks |
| `core/watchdog_runner.py` | Watchdog scheduling | Runnable loop |
| `core/notifications/telegram_sink.py` | Telegram alert delivery | `NotificationSink` implementation, HTML format, rate-limited |
| `config.py` | Env var + secret provider | `AI4TRADE_TOKEN`, `CLAUDE_API_KEY`, `LLM_API_KEY`; 3 backends |
| `config_schema.py` | Optional YAML config | Falls back gracefully if missing |

### 2.5 Rainbow Subsystem

| Module | Purpose | Key Concepts |
|--------|---------|-------------|
| `rainbow/models/signal.py` | Rainbow signal model | `CryptoSignal` with `SignalType`, `Direction`, `strength` |
| `rainbow/evaluation/llm_evaluator.py` | LLM-based signal evaluation | wraps Claude/OpenAI for evaluation |
| `rainbow/processor/scorer.py` | Multi-source scoring | Combines technical + sentiment + news scores |
| `rainbow/distribution/api.py` | FastAPI distribution endpoint | REST API for signal distribution |

---

## 3. Safety Assessment

| Aspect | Status | Details |
|--------|--------|---------|
| **Live trading** | 🟢 Impossible | `Actionability` validator forces `can_execute=False, dry_run_only=True` at model level; Bridge re-checks |
| **Exchange access** | 🟡 Not in audited modules | `config.py` references Bitget/CoinGecko URLs; actual adapter code in `adapters/derivatives/` (not audited) |
| **Secrets in code** | 🟡 Requires env/`.env` | `AI4TRADE_TOKEN`, `CLAUDE_API_KEY`, `LLM_API_KEY` via `SecretProvider` abstraction |
| **Network calls** | 🟡 `TelegramSink` only | HTTPS POST to `api.telegram.org`, rate-limited to 1/60s |
| **Network calls** | 🟢 Signal adapters | `rainbow/collectors/*.py` (news, reddit, twitter, TA) make outbound HTTP |
| **Docker** | 🟢 Not present | No Docker protocol or exec calls |
| **Runtime state** | 🟢 SQLite + in-memory | 2 databases (`canonical_signals.db`, `outcomes.db`), optional JSON cache |
| **Mode enforcement** | 🟢 Multi-layer | Model-level (`Actionability`), Bridge-level (8 checks), `ConfidenceModulator` |

---

## 4. Integration Readiness Summary

**Verdict:** ai4trade-bot is **ready for integration as an upstream advisory layer**, but NOT as a runtime dependency to import/vendor.

### Strengths
- Multi-layer safety enforcement (model → gate → bridge)
- Well-structured signal pipeline (raw → envelope → risk → bridge)
- 1048 tests, 0 open issues (per closure report)
- Pydantic v2 schemas compatible with SI v2

### Gaps
- No Protocol-based adapter pattern (SI v2's core pattern)
- No dry-run stub pattern (enforced at model level instead)
- No deployment/orchestration layer
- No backtest runner or walk-forward validator
- No rollback or shadow-mode tracking

### Recommended Integration Boundary

```
ai4trade-bot (upstream)                  SI v2 (orchestrator)
─────────────────────                    ─────────────────────
CanonicalSignalEnvelope ──→ read ──→ SignalProviderProtocol
SignalOutcome           ──→ read ──→ OutcomeProviderProtocol
                                    MutationCandidate
                                    BacktestRunner
                                    DeploymentPlanOrchestrator
                                    ShadowModeManager
```

The two systems are **complementary**: ai4trade-bot provides signal intelligence, SI v2 provides strategy improvement orchestration. The boundary is a Python Protocol (in-memory, no network for Phase F).