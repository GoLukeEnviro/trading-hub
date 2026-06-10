# Self-Improvement Trading System — Consolidated Architecture v1.0

**Project:** trading-hub + ai4trade-bot  
**Status:** Production-Ready Draft  
**Date:** 2026-06-10  
**Owner:** LukeVs / GoEnviro

---

## 1. Vision & Goal

Create a **low-maintenance, closed-loop self-improving trading system** that:
- Collects signals from multiple sources (Rainbow + strong "Kollege" signaler)
- Aggregates and scores them intelligently (regime-aware)
- Executes in dry-run / paper / live with strong safety
- Automatically learns from outcomes (performance attribution per source + regime)
- Proposes improvements via a structured Orchestrator
- Keeps everything auditable and reconstructable via Shadowlock

The system must run with **minimal daily intervention** after initial setup.

## 2. High-Level Architecture (4 Layers)

```
[Execution Layer]          Freqtrade Bots (FreqForge, Canary, Regime-Hybrid, ...)
         ↓
[Signal Layer]            Rainbow Collectors + External "Kollege" + AI-Hedge-Fund
         ↓
[Intelligence Layer]      RainbowScorer + Regime Detector + Meta-Learner + Weight Optimizer
         ↓
[Governance Layer]        Self-Improvement Orchestrator + Shadowlock + Forensics + Specs
```

## 3. Core Closed Loop (Signal Intelligence)

1. Signal Generation (Rainbow + Kollege)
2. Aggregation & Scoring (RainbowScorer + AI Eval)
3. Regime Detection (attached to every signal & trade)
4. Execution (via trading-hub / Hermes)
5. Outcome Tracking (TradeOutcome with signal_ids + regime)
6. Performance Attribution (per source, per regime)
7. Meta-Learner proposes new weights
8. Validation Gate (Backtest + Safety checks)
9. Weight Update (versioned, hot-reloadable) or Circuit Breaker

## 4. Key Components Status (June 2026)

| Component                        | Status          | Location                              | Notes |
|----------------------------------|-----------------|---------------------------------------|-------|
| Rainbow / ai4trade-bot           | Good            | Separate repo                         | Strong base |
| Shadowlock Writer                | Running         | trading-hub                           | Healthy, seq=128+ |
| Self-Improvement Orchestrator    | Functional      | docs/prompts + self_improvement/      | First episode done (partial) |
| Profitability Forensics          | Implemented     | docs/specs + tools                    | Good first run |
| Regime Detector                  | Missing         | -                                     | Highest priority next |
| Meta-Learner (Weight Optimizer)  | Missing         | -                                     | Core of signal self-improvement |
| Validation Gate + Circuit Breaker| Partial         | trading-hub risk manager              | Needs formalization |

## 5. Next Priority Implementation Order

1. **Regime Detector** (rule-based v1 + extensible)
2. **Trade Outcome Tracker** integration
3. **Meta-Learner v1** (EMA regime-aware quality scoring)
4. **Shadowlock Indexer** (SQLite read cache for fast queries)
5. Formal **Validation Gate** in Orchestrator

## 6. Safety Principles (Non-Negotiable)

- Never auto-apply weight changes without backtest gate + human review initially
- Per-source circuit breakers (winrate < 35% in regime → weight cap)
- Global drawdown circuit breaker
- All changes versioned + reproducible via git + shadowlock

This document + the existing specs in `docs/specs/` form the canonical reference for all future agents.
