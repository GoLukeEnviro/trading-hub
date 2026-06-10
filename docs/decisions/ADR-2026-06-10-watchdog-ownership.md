# ADR-2026-06-10: Watchdog Ownership Boundary

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#23 — ADR: Decide watchdog ownership between SI v2 and ai4trade-bot](https://github.com/GoLukeEnviro/trading-hub/issues/23)

---

## Table of Contents

1. [Context](#1-context)
2. [Existing Watchdog Implementations](#2-existing-watchdog-implementations)
3. [Options Considered](#3-options-considered)
4. [Decision](#4-decision)
5. [Consequences](#5-consequences)
6. [Domain Ownership Map](#6-domain-ownership-map)
7. [Event Model for Cross-Boundary Health](#7-event-model-for-cross-boundary-health)
8. [Failure Propagation Rules](#8-failure-propagation-rules)
9. [Safety Rules](#9-safety-rules)
10. [Follow-Up Issues](#10-follow-up-issues)
11. [References](#11-references)

---

## 1. Context

Both codebases contain watchdog concepts:

- **SI v2 / trading-hub** — multiple watchdog scripts for fleet observation,
  ledger integrity, critical events, and heartbeat monitoring. These are
  operational monitors that watch the trading infrastructure.
- **ai4trade-bot** — `core/watchdog.py` and `core/watchdog_runner.py` monitor
  heartbeat files for the Legacy and Rainbow signal services. These are
  signal-service health monitors.

Neither codebase imports or depends on the other. The architecture question
is whether (and how) these watchdog domains should intersect.

---

## 2. Existing Watchdog Implementations

### 2.1 trading-hub / SI v2

| Script | Purpose | Domain |
|--------|---------|--------|
| `orchestrator/scripts/observation_watchdog.py` | Heartbeat observation, escalation, webhook alerts | Fleet-level runtime health |
| `orchestrator/scripts/ledger_integrity_watchdog.py` | Ledger integrity, drawdown checks, source completeness | Fleet-level risk integrity |
| `orchestrator/scripts/critical_event_watchdog.py` | Critical event monitoring | Incident detection |
| `orchestrator/scripts/mot_floor_watchdog.py` | Floor/minimum-operating-threshold monitoring | Trading safety floor |
| `orchestrator/scripts/ghostbuster.py` | Stale trade/max-open cleanup | Operational cleanup |

These watchdogs are deployed via Hermes cron jobs and operate on the
server/host level. They have access to Docker, the filesystem, and
operational state but no direct dependency on ai4trade-bot.

### 2.2 ai4trade-bot

| Component | Purpose | Domain |
|-----------|---------|--------|
| `core/watchdog.py` | Heartbeat file monitor with `NotificationSink` protocol | Signal-service health |
| `core/watchdog_runner.py` | CLI entry point for standalone watchdog process | Signal-service health |
| `config/watchdog.json` | Component configuration (legacy, rainbow) | Configuration |

The ai4trade watchdog monitors heartbeat files written by the Legacy and
Rainbow signal services. It uses a `NotificationSink` protocol for
alert delivery (currently `TelegramSink`).

---

## 3. Options Considered

### Option 1: SI v2 owns self-improvement pipeline watchdog; ai4trade owns signal-service watchdog

| Aspect | Assessment |
|--------|-----------|
| **Clarity** | ✅ Clear domain boundary. Each repo owns its operational health. |
| **Coupling** | ✅ Independent deployment cycles. No cross-repo dependency. |
| **Redundancy** | 🟡 Duplicate alerting possible if both watchdogs monitor overlapping components. |
| **Safety** | ✅ No cross-repo code copying. No import risk. |
| **Integration cost** | ✅ None needed now. |

### Option 2: Shared watchdog event protocol

| Aspect | Assessment |
|--------|-----------|
| **Clarity** | 🟡 Protocol must be defined and maintained. |
| **Coupling** | ❌ Both repos depend on a shared contract. |
| **Safety** | 🟡 Protocol drift could cause missed events. |
| **Integration cost** | ❌ High for current state — no immediate need. |

### Option 3: SI v2 consumes ai4trade health as read-only input only

| Aspect | Assessment |
|--------|-----------|
| **Clarity** | ✅ SI v2 reads ai4trade heartbeat files as evidence. No write-back. |
| **Coupling** | 🟡 SI v2 depends on ai4trade's heartbeat file format and location. |
| **Safety** | ✅ Read-only consumption. Fail-closed if heartbeat missing. |
| **Integration cost** | 🟡 Medium — needs documented heartbeat contract. |

### Option 4: No integration for now

| Aspect | Assessment |
|--------|-----------|
| **Simplicity** | ✅ Maximum simplicity. No cross-repo contract. |
| **Risk** | 🟡 SI v2 has no visibility into ai4trade-bot health for self-improvement decisions. |
| **Future cost** | 🟡 May need refactoring when integration becomes necessary. |

---

## 4. Decision

**Primary choice: Option 1 — Separate ownership with domain boundaries.**

- **SI v2 / trading-hub** owns the fleet-level infrastructure watchdog domain:
  observation, ledger integrity, critical events, fleet health monitoring.
- **ai4trade-bot** owns the signal-service watchdog domain: heartbeats for
  Legacy and Rainbow services, signal freshness monitoring.

**Future option: Option 3 — Read-only heartbeat consumption (Phase H).**

If SI v2 needs ai4trade health evidence for self-improvement pipeline
decisions (e.g., "is Rainbow generating signals?"), it MAY consume
ai4trade's heartbeat files as **read-only evidence**. This requires:

1. A documented heartbeat file contract (path, format, freshness threshold).
2. Fail-closed behavior if heartbeat is missing or stale.
3. No write-back to ai4trade state from SI v2.

---

## 5. Consequences

### Positive

- **Clear ownership:** Each team/component knows which watchdog domain it owns.
- **Independent deployment:** No shared release coordination needed.
- **No cross-repo coupling:** No imports, no shared protocols, no submodules.
- **Existing code unchanged:** All current watchdog scripts continue to work.
- **Safety preserved:** No cross-repo code copying, no runtime imports.

### Negative

- **Duplicate alerting possible:** Both domains could alert on overlapping
  symptoms (e.g., a down signal service is a signal-service problem AND a
  fleet-observation problem). Mitigation: SI v2 observation watchdog should
  treat ai4trade signals as read-only evidence, not primary alert source.
- **No shared escalation protocol:** Each domain has its own escalation path.
  Acceptable because the domains are distinct.

### Neutral

- **Future integration is option 3 when needed:** No premature standardization.

---

## 6. Domain Ownership Map

```
┌─────────────────────────────────────────────────────────┐
│                 trading-hub / SI v2                      │
│                                                          │
│  ┌────────────────────┐  ┌─────────────────────────┐    │
│  │ Fleet Observation   │  │ Ledger Integrity        │    │
│  │ Watchdog            │  │ Watchdog                │    │
│  │ (observation_watch  │  │ (ledger_integrity_watch │    │
│  │ _dog.py)            │  │ _dog.py)                │    │
│  └────────┬───────────┘  └──────────┬──────────────┘    │
│           │                         │                    │
│           ▼                         ▼                    │
│  ┌──────────────────────────────────────────┐           │
│  │  Fleet / Infrastructure Health State     │           │
│  └──────────────────────────────────────────┘           │
│                                                          │
│  DOES NOT OWN: signal-service health                     │
│  CONSUMES AS READ-ONLY: ai4trade heartbeat evidence      │
│  (future, Phase H)                                       │
└──────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 ai4trade-bot                             │
│                                                          │
│  ┌────────────────────┐  ┌─────────────────────────┐    │
│  │ Watchdog            │  │ Heartbeat Writer        │    │
│  │ (core/watchdog.py)  │  │ (core/heartbeat_writer  │    │
│  │                     │  │ .py)                    │    │
│  │ Monitors:           │  │ Written by:             │    │
│  │  - Legacy heartbeat │  │  - Legacy (main.py)     │    │
│  │  - Rainbow heartbeat│  │  - Rainbow (rainbow/    │    │
│  └────────┬───────────┘  │    main.py)              │    │
│           │              └─────────────────────────┘    │
│           ▼                                              │
│  ┌──────────────────────────────────────────┐           │
│  │  Signal-Service Health State             │           │
│  └──────────────────────────────────────────┘           │
│                                                          │
│  OWNS: signal-service health monitoring                  │
│  DOES NOT OWN: fleet-level infrastructure monitoring     │
└──────────────────────────────────────────────────────────┘
```

---

## 7. Event Model for Cross-Boundary Health

No shared event protocol is defined at this time. If in the future (Phase H
or later) SI v2 needs to consume ai4trade signal-service health, it shall:

1. **Read heartbeat files directly** from a documented shared path.
2. **Treat missing/stale heartbeat as evidence** that signal service is
   degraded — this influences self-improvement pipeline decisions
   (e.g., "skip signal-dependent stages").
3. **Never write** to ai4trade heartbeat files or state.
4. **Fail closed** if the heartbeat file format is unknown or corrupted.

### Minimal Heartbeat Contract (for future read-only consumption)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component` | string | ✅ | Component identifier (e.g., "legacy", "rainbow") |
| `status` | string | ✅ | One of: "healthy", "degraded", "starting", "stopped" |
| `timestamp_utc` | ISO 8601 | ✅ | When the heartbeat was written |
| `uptime_seconds` | number | - | Seconds since component start |

Expected path: `{ai4trade_root}/storage/heartbeat_{component}.json`

---

## 8. Failure Propagation Rules

| Scenario | Effect on SI v2 | Effect on ai4trade-bot |
|----------|----------------|----------------------|
| Fleet watchdog detects missing ai4trade heartbeat | SI v2 marks signal-dependent stages as `DEGRADED` | No effect (separate domain) |
| ai4trade watchdog detects missing fleet health | No effect (separate domain) | ai4trade continues independent operation |
| Fleet watchdog crashes | Affects fleet observation only | No effect |
| ai4trade watchdog crashes | SI v2 loses read-only health evidence | No effect on signal generation |
| Both watchdogs healthy | Full operational visibility | Full signal-service health |

**Key principle:** No cross-domain failure cascade. A watchdog failure in one
domain must never cause outages in the other domain.

---

## 9. Safety Rules

1. **No cross-repo code copying.** Never copy ai4trade watchdog code into
   trading-hub or vice versa. If shared logic emerges, extract to a
   standalone library under a separate repository.

2. **No runtime imports.** SI v2 must never `import` ai4trade modules at
   runtime. All evidence is file-based (heartbeat JSON).

3. **No write-back.** SI v2 must never write to ai4trade-managed files,
   directories, or state.

4. **Fail-closed for consumed evidence.** If SI v2 reads ai4trade heartbeats
   and the heartbeat is missing/stale/corrupt, SI v2 must treat this as
   evidence of signal-service degradation and adjust its pipeline accordingly.

5. **No coupling of deployment cycles.** Changes to one repo's watchdog
   must never require coordinated deployment of the other repo.

---

## 10. Follow-Up Issues

| Issue | Action | Priority |
|-------|--------|----------|
| — | Document heartbeat file contract in ai4trade-bot's `docs/` | Phase H |
| #22 | RiskGuard/ShadowLogger runtime safety contract (already done) | ✅ Complete |
| — | Update AGENTS.md to reflect watchdog domain ownership | Low (cleanup) |
| — | SHALL: Add watchdog domain ownership to SI v2 docs index | With #32 |

---

## 11. References

| Document | Location |
|----------|----------|
| ai4trade-bot watchdog | `core/watchdog.py`, `core/watchdog_runner.py`, `config/watchdog.json` |
| ai4trade-bot heartbeat writer | `core/heartbeat_writer.py` |
| ai4trade-bot watchdog report | `docs/reports/runtime-health-watchdog-report.md` |
| SI v2 observation watchdog | `orchestrator/scripts/observation_watchdog.py` |
| SI v2 ledger watchdog | `orchestrator/scripts/ledger_integrity_watchdog.py` |
| Runtime safety contract | `docs/specs/runtime-safety-contract.md` (from #22) |
| ADR: AI4Trade Integration Boundary | `self_improvement_v2/docs/ADR_AI4TRADE_INTEGRATION_BOUNDARY.md` |
| AGENTS.md | `/home/hermes/projects/trading/AGENTS.md` |
