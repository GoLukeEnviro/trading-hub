# System Architecture — Trading Hub

> **Canonical architecture reference.**
> Last updated: 2026-07-03
> Companion: `docs/state/current-operational-state.md` (runtime snapshot)
> Live Roadmap: GitHub Issue #423
> ADR Pivot: `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`

---

## 1. Data Flow Overview

```mermaid
flowchart TB
    subgraph Signal["Signal Layer"]
        AHF[ai-hedge-fund-crypto<br/>Port 8410] -->|hermes_signal.json| PS[primo_signal.py<br/>legacy signal filter]
    end

    subgraph Safety["Safety Layer"]
        PS -->|primo_gate_allows| KS[Kill Switch<br/>kill_switch.py<br/>NORMAL]
        KS -->|NORMAL/HALT_NEW/EMERGENCY| FT[Freqtrade Fleet]
        RG[RiskGuard Spec] -.->|ACCEPTED/WATCH_ONLY/BLOCK_ENTRY| FT
        SL[ShadowLogger<br/>JSONL Audit] -->|append-only| LOG[orchestrator/logs/]
    end

    subgraph Fleet["Execution Layer"]
        FT --> F1[FreqForge :8086]
        FT --> F2[Regime-Hybrid :8085]
        FT --> F3[Canary :8081]
        FT --> F4[FreqAI-Rebel :8087]
    end

    subgraph Observation["SI v2 Autonomous Dry-Run Loop"]
        ACR[Active Cycle Runner<br/>6h cron] -->|REST| FT
        RB[Rainbow §5<br/>read_only] --> ACR
        ACR --> CS[CycleState]
        CS --> ML[Measurement Ledger<br/>JSONL]
        ML --> FA[Fleet Analyzer]
        FA --> SP[Shadow Proposal]
        SP -->|Policy-gated<br/>AUTONOMOUS_DRY_RUN| DEPLOY[Deploy Gate]
        DEPLOY -->|Canary overlay| CANARY_APPLY[Canary Apply]
        CANARY_APPLY --> PROOF[RuntimeEffectProof]
        PROOF --> DEC[Measurement Decision<br/>KEEP/EXTEND/ROLLBACK]
        DEC -->|KEEP| NEXT[Next Iteration]
        SP -->|Observation only| SL
    end

    subgraph Control["Controller / Orchestrator Layer"]
        CTRL[Hermes Orchestrator<br/>AUTONOMOUS_DRY_RUN] -->|manages| DEPLOY
        CTRL -.->|cron/audit| ACR
    end

    DASH[Dashboard<br/>dashboard.py :5000] -.->|read-only| FT
    DASH -.->|read-only| AHF

    style KS fill:#dc2626,color:#fff
    style ACR fill:#1a1a2e,color:#fff
    style ML fill:#16213e,color:#fff
    style CTRL fill:#0f3460,color:#fff
    style DASH fill:#533483,color:#fff
    style DEC fill:#f59e0b,color:#000
```

**Note:** `primo_signal.py` and `Bridge` are decommissioned as autonomous signal
sources. `primo_signal.py` remains in `freqtrade/shared/` as a legacy signal filter
and kill-switch integration boundary. See `docs/decommissioning-register.md`
for decommissioning history.

---

## 2. Kill-Switch Wiring

```mermaid
flowchart LR
    subgraph Triggers["Trigger Sources"]
        CLI[kill_switch_trigger.sh<br/>CLI] --> KSPY[kill_switch.py]
        AUTO[auto-check<br/>Drawdown Guard] -->|reads fleet_risk_state.json| KSPY
        CRON[Cron Timer] -->|auto_clear_minutes| KSPY
    end

    subgraph State["State File"]
        JSON[var/kill_switch.json<br/>Atomic .tmp+replace] -->|mtime cache| KSPY
    end

    subgraph Consumers["Consumers"]
        KSPY -->|is_kill_active()| PS[primo_signal.py<br/>primo_gate_allows]
        KSPY -->|is_emergency()| PS
        PS -->|False = block| FT[Freqtrade Strategies]
        FT -->|HALT_NEW| HALT[Block entries<br/>Keep positions]
        FT -->|EMERGENCY| EMERG[Block entries<br/>Close positions]
        FT -->|NORMAL| NORM[Normal operation]
    end

    style KSPY fill:#dc2626,color:#fff
    style JSON fill:#f59e0b,color:#000
    style PS fill:#f59e0b,color:#000
```

**Modes:**

| Mode | Entries | Positions | Use Case |
|------|---------|-----------|----------|
| `NORMAL` | ✅ Allowed | ✅ Held | Normal operation |
| `HALT_NEW` | ❌ Blocked | ✅ Held | Elevated risk, manual pause |
| `EMERGENCY` | ❌ Blocked | ❌ Signal close | Drawdown breach, emergency |

**Thresholds (default):** HALT at 12% drawdown, EMERGENCY at 18%.

**Current status: NORMAL** (set 2026-06-29, approved).

---

## 3. SI v2 Autonomous Dry-Run Loop

```mermaid
sequenceDiagram
    participant Cron as Hermes Scheduler
    participant ACR as ActiveCycleRunner
    participant FT as Freqtrade REST
    participant RB as Rainbow §5
    participant ML as Measurement Ledger
    participant FA as FleetAnalyzer
    participant SP as ShadowProposal
    participant Policy as Autonomy Policy
    participant Canary as Canary Bot
    participant Proof as RuntimeEffectProof
    participant DEC as Decision Engine
    participant LOG as ShadowLogger

    Cron->>ACR: every 6h (17 */6 * * *)
    ACR->>FT: fetch telemetry (4 bots)
    ACR->>RB: fetch rainbow read_only
    RB-->>ACR: 3 metrics (freshness check)
    ACR->>ML: append cycle snapshot
    ML->>FA: analyze fleet
    FA->>SP: generate proposal
    SP->>LOG: append JSONL audit trail
    SP->>Policy: evaluate gates
    Policy-->>SP: PASS / FAIL
    SP->>Canary: dry-run overlay apply (policy-gated)
    Canary->>Proof: verify effect
    Proof->>DEC: measurement decision
    DEC-->>Cron: KEEP / EXTEND / ROLLBACK
    Note over DEC,Cron: AUTONOMOUS_DRY_RUN — no human gate per apply
```

**Note:** No volatile cycle/ledger/scoring counters are canonical truth.
See `docs/state/current-operational-state.md` for the validated runtime snapshot.

---

## 4. Controller / Orchestrator State

```mermaid
stateDiagram-v2
    [*] --> AUTONOMOUS_DRY_RUN
    AUTONOMOUS_DRY_RUN --> LIVE_CANDIDATE : C4 KEEP + APPROVED_LIVE_FLEET_ROLLOUT
    LIVE_CANDIDATE --> LIVE_ACTIVE : staged rollout approved
    LIVE_ACTIVE --> AUTONOMOUS_DRY_RUN : ROLLBACK / EMERGENCY
    AUTONOMOUS_DRY_RUN --> FORBIDDEN : safety gate triggered
    FORBIDDEN --> AUTONOMOUS_DRY_RUN : safety gate resolved

    note right of AUTONOMOUS_DRY_RUN
        Current state (2026-07-03)
        Policy: AUTONOMOUS_DRY_RUN
        Apply: policy-gated, canary-first
        Dry-run only: dry_run=true
        D1: BLOCKED
          (C4 ROLLBACK_RECOMMENDED
           + missing APPROVED_LIVE_FLEET_ROLLOUT)
    end note
```

### State definitions

| State | Meaning | Authority |
|-------|---------|-----------|
| `LIVE_FORBIDDEN` | Default. No real orders, no live keys, no `dry_run=false`. | — |
| `AUTONOMOUS_DRY_RUN` | Policy-gated canary dry-run apply. No human gate per iteration. | ADR-2026-07-01 |
| `LIVE_CANDIDATE` | Single canary approved for live observation. | Human approval marker |
| `LIVE_ACTIVE` | Live mode active under approved limits. | Human approval marker |
| `FORBIDDEN` | Safety gate triggered — all activity blocked. | RiskGuard / Kill Switch |

See `docs/architecture/si-v2-autonomous-dry-run-loop.md` for detailed architecture.

---

## 5. Component Ownership & Status

| Component | Role | Status | Authority |
|-----------|------|--------|-----------|
| `ai-hedge-fund-crypto` | Signal generation | 🟢 ACTIVE | Advisory only |
| `orchestrator/` | Hermes control plane | 🟢 ACTIVE | Audit, docs, git ops |
| `self_improvement_v2/` | SI v2 engine | 🟢 ACTIVE | AUTONOMOUS_DRY_RUN |
| `freqtrade/shared/kill_switch.py` | Central kill switch | 🟢 DEPLOYED — NORMAL | Override all entries |
| `freqtrade/shared/primo_signal.py` | Legacy signal filter | 🟡 LEGACY | Advisory + kill-switch block |
| `freqtrade/shared/fleet_risk_manager.py` | Fleet risk state | 🟢 ACTIVE | Advisory |
| `freqtrade/` (fleet) | Dry-run execution | 🟢 ACTIVE | Strategy logic |
| `freqforge/` | FreqForge bot | 🟢 ACTIVE | Strategy logic |
| `freqforge-canary/` | Canary bot | 🟡 STOPPED | Strategy logic (baseline return) |
| `tools/freqforge/` | Shadow evaluator | 🟡 PASSIVE | None (observer) |
| `shadowlock/` | ShadowLock service | 🟢 ACTIVE | Evidence trail |
| `dashboard.py` | Operational dashboard | 🟢 ACTIVE | Read-only |
| `Caddyfile` | Reverse proxy | 🟢 ACTIVE | Fleet routing |
| RiskGuard (spec) | Safety gates | 🔶 SI v2 SPEC | Advisory design |
| ShadowLogger | Audit trail | 🟢 DEPLOYED | Evidence |
| Hermes Orchestrator | Automation control | 🟢 AUTONOMOUS_DRY_RUN | Policy-gated |

### Decommissioned components

| Component | Status | Replaced by |
|-----------|--------|-------------|
| Primo / PrimoAgent | ❌ Decommissioned (Phase 44-45) | SI-v2 autonomous loop |
| Bridge (hermes_primo_bridge.py) | ❌ Decommissioned (Phase 44-45) | SI-v2 apply chain |
| intelligence/ | ❌ Vestigial | — |
| Momentum bot | ❌ Decommissioned | — |
| MVS bot | ⬜ Not deployed | — |

---

## 6. Network Topology

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| ai-hedge-fund-crypto | 8410 | HTTP | Localhost only |
| FreqForge API | 8086 | HTTP | Docker network |
| Regime-Hybrid API | 8085 | HTTP | Docker network |
| Canary API | 8081 | HTTP | Docker network |
| FreqAI-Rebel API | 8087 | HTTP | Docker network |
| Dashboard | 5000 | HTTP | Caddy reverse proxy |
| Rainbow stub | 8412 | HTTP | Localhost only |
| Docker socket proxy | 2375 | HTTP | Container-internal |

---

## 7. Related Documents

| Document | Location |
|----------|----------|
| Current Operational State | `docs/state/current-operational-state.md` |
| Live Roadmap | GitHub Issue #423 |
| SI v2 Module Map | `self_improvement_v2/README.md` |
| SI-v2 Detail Architecture | `docs/architecture/si-v2-autonomous-dry-run-loop.md` |
| ADR: Autonomous Dry-Run | `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md` |
| Kill-Switch Runbook | `docs/runbooks/kill-switch.md` |
| Production Risk Limits | `docs/specs/production-risk-limits-spec.md` |
| Incident Response Runbooks | `docs/specs/incident-response-runbooks.md` |
| Safety Contract | `docs/specs/runtime-safety-contract.md` |
| AGENTS.md | `AGENTS.md` |
