# ADR: ai4trade-bot Integration Boundary

**Status:** Draft for Phase F review
**Date:** 2026-06-10
**Author:** SI v2 Meta-Orchestrator

---

## Context

SI v2 (self_improvement_v2/) and ai4trade-bot are complementary systems:

- **SI v2** orchestrates strategy improvement: observe → analyze → propose → backtest → approve → deploy
- **ai4trade-bot** provides signal intelligence: raw signal → envelope → risk gate → bridge → advisory

Both are mature codebases (SI v2: 178 tests, ai4trade-bot: 1048 tests). We need an integration boundary
that is safe, maintainable, and does not create coupling risk.

## Options Considered

### Option A: Git Submodule

Vendor ai4trade-bot as a git submodule under SI v2.

| Pro | Con |
|-----|-----|
| Always latest version | Couples deployment cycles |
| No code duplication | Submodule drift risk |
| Shared test infrastructure | Conflict with Hermes deployment |

**Safety risk:** Submodule gives access to all ai4trade-bot code including exchange adapters.
**Decision:** ❌ Rejected — too coupled, Security risk from exchange adapter code.

### Option B: Local Python Package (pip install -e)

Add ai4trade-bot as a local dependency in `pyproject.toml`.

| Pro | Con |
|-----|-----|
| Clean import interface | Tight coupling to internal schemas |
| Type checking works | Risk of importing unsafe modules |
| Easy to test | No runtime isolation |

**Safety risk:** Direct import gives access to `config.py` (loads API keys), exchange adapters,
and all runtime code. A SI v2 import could accidentally trigger env var loading.
**Decision:** ❌ Rejected — too much trust in code that reads secrets.

### Option C: Generated Adapter Contract

Define a Protocol in SI v2, implement a lightweight REST client in ai4trade-bot.

| Pro | Con |
|-----|-----|
| Network boundary = safety boundary | Latency + reliability |
| Clear API contract | API drift handling |
| Versioned | More infrastructure |

**Safety risk:** Network calls to internal service. Fail-closed policy mitigates.
**Decision:** ✅ **Recommended default** — safest architectural boundary.

### Option D: Copied Vendor Code (STRONGLY REJECTED)

Copy relevant ai4trade-bot files into SI v2.

| Pro | Con |
|-----|-----|
| None | Divergence nightmare, license risk, stale code |

**Decision:** ❌❌ **Strongly rejected** — violates every software engineering principle.

### Option E: Protocol Adapter (Phase F Recommendation)

Define Python Protocols in SI v2 that match ai4trade-bot's output contracts.
Implement in-memory / DryRun adapters only. Real REST client deferred to Phase H.

| Pro | Con |
|-----|-----|
| No coupling | Adapter interface may need refactoring |
| Clear boundary | Duplicated schema validation |
| Safe for Phase F (in-memory only) | Not immediately functional |
| Tests pass with DryRun stubs | |

**Safety risk:** Minimal — in-memory only, no network, no imports.
**Decision:** ✅ **Recommended for Phase F** — clean boundary, safe, forward-compatible
to Option C (REST API) in Phase H.

## Decision

**Phase F:** Define `SignalProviderProtocol` and `OutcomeProviderProtocol` in SI v2 under
`src/si_v2/integrations/ai4trade/`. Implement in-memory DryRun adapters only.

**Phase H (future):** Implement REST API adapters consuming ai4trade-bot's `rainbow/distribution/api.py`.
Network boundary provides isolation; fail-closed policy provides safety.

**Never:** Direct code copying, submodule import, or pip-install of ai4trade-bot.

## Architecture

```
┌──────────────────────┐     Protocol Adapter     ┌──────────────────────┐
│   ai4trade-bot       │◄─────────────────────────│   SI v2              │
│                      │    (in-memory, Phase F)   │                      │
│  CanonicalSignalRegistry─────► SignalProviderProtocol  │
│  OutcomeRepository   ───────► OutcomeProviderProtocol  │
│  RiskGate            ───────► RiskGateProviderProtocol  │
│                      │                           │                      │
│  Rainbow API (future)───► REST Client (Phase H)│    Orchestrator       │
└──────────────────────┘                           └──────────────────────┘
```

## Rationale

1. **Protocol-first** matches SI v2's established pattern (DockerAdapter, FreqtradeAdapter, TelegramAdapter all use Protocol)
2. **In-memory Phase F** allows testing without network dependency
3. **REST Phase H** provides network isolation — ai4trade-bot runs in its own process
4. **No code copying** prevents divergence and security vulnerabilities
5. **Fail-closed** — if ai4trade-bot is unavailable, SI v2 continues with DryRun data

## Consequences

**Positive:**
- Clean separation of concerns
- SI v2 tests pass without ai4trade-bot installed
- Integration can be tested independently
- Migration to REST is a drop-in adapter swap (like DryRunStub → RealAdapter)

**Negative:**
- Protocol interfaces may need refinement as we discover ai4trade-bot edge cases
- Schema validation duplicated at boundary
- Phase H REST adapter needs ai4trade-bot's Rainbow API to be deployed