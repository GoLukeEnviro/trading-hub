# System Architecture — Trading Hub

> **Canonical architecture reference.**
> Last updated: 2026-06-15
> Companion: `docs/state/current-operational-state.md` (runtime snapshot)

---

## 1. Data Flow Overview

```mermaid
flowchart TB
    subgraph Signal["Signal Layer"]
        AHF[ai-hedge-fund-crypto<br/>Port 8410] -->|hermes_signal.json| BRIDGE[Bridge / primo_signal.py]
    end

    subgraph Safety["Safety Layer"]
        BRIDGE -->|primo_gate_allows| KS[Kill Switch<br/>kill_switch.py]
        KS -->|NORMAL/HALT_NEW/EMERGENCY| FT[Freqtrade Fleet]
        RG[RiskGuard Spec] -.->|ACCEPTED/WATCH_ONLY/BLOCK_ENTRY| BRIDGE
        SL[ShadowLogger<br/>JSONL Audit] -->|append-only| LOG[orchestrator/logs/]
    end

    subgraph Fleet["Execution Layer"]
        FT --> F1[FreqForge :8086]
        FT --> F2[Regime-Hybrid :8085]
        FT --> F3[Canary :8081]
        FT --> F4[FreqAI-Rebel :8087]
    end

    subgraph Observation["SI v2 Observation Layer"]
        ACR[Active Cycle Runner<br/>6h cron] -->|REST| FT
        RB[Rainbow §5<br/>read_only] --> ACR
        ACR --> CS[CycleState]
        CS --> ML[Measurement Ledger<br/>JSONL]
        ML --> FA[Fleet Analyzer]
        FA --> SP[Shadow Proposal]
        SP -.->|IF APPROVED| DEPLOY[Deploy Gate]
        DEPLOY -.->|PAUSED| HOLD
    end

    subgraph Control["Controller Layer"]
        CTRL[SI v2 Controller<br/>PAUSED] -->|HUMAN_ONLY merge| REPO[Repository]
        CTRL -.->|QUEUE| ACR
    end

    DASH[Dashboard<br/>dashboard.py :5000] -.->|read-only| FT
    DASH -.->|read-only| AHF

    style KS fill:#dc2626,color:#fff
    style ACR fill:#1a1a2e,color:#fff
    style ML fill:#16213e,color:#fff
    style CTRL fill:#0f3460,color:#fff
    style DASH fill:#533483,color:#fff
```

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

---

## 3. SI v2 Observation Loop

```mermaid
sequenceDiagram
    participant Cron as Hermes Scheduler
    participant ACR as ActiveCycleRunner
    participant FT as Freqtrade REST
    participant RB as Rainbow §5
    participant ML as Measurement Ledger
    participant FA as FleetAnalyzer
    participant SP as ShadowProposal
    participant LOG as ShadowLogger

    Cron->>ACR: every 6h (17 */6 * * *)
    ACR->>FT: fetch telemetry (4 bots)
    ACR->>RB: fetch rainbow read_only
    RB-->>ACR: 3 metrics (freshness check)
    ACR->>ML: append cycle snapshot
    ML->>FA: analyze 27 fleet cycles
    FA->>SP: generate proposal
    SP->>LOG: append JSONL audit trail
    Note over SP,LOG: Controller PAUSED — no mutations applied
    ACR-->>Cron: exit 0 (GREEN verdict)
```

**Current state:**
- 27 fleet cycles completed
- 108 bot measurement points
- 24 proposal records
- All mutation counters: **zero**
- Scoring gate: **0/10** (awaiting producer freshness)

---

## 4. Controller State Machine

```mermaid
stateDiagram-v2
    [*] --> PAUSED
    PAUSED --> QUEUE : approval_gate=False removed
    QUEUE --> ACTIVE : epic selected + human approval
    ACTIVE --> PAUSED : epic completed or interrupted
    ACTIVE --> BLOCKED : CI failure / safety gate
    BLOCKED --> QUEUE : human review + fix
    QUEUE --> PAUSED : manual pause
    PAUSED --> [*] : controller deactivated

    note right of PAUSED
        Current state (2026-06-15)
        Reason: AWAITING_NEXT_APPROVED_EPIC
        Policy: L3_REPOSITORY_ONLY
        Merge: HUMAN_ONLY
        Runtime: FORBIDDEN
    end note

    note right of ACTIVE
        Future state
        Autonomous work packages
        HUMAN_ONLY merge authority
    end note
```

---

## 5. Component Ownership & Status

| Component | Role | Status | Authority |
|-----------|------|--------|-----------|
| `ai-hedge-fund-crypto` | Signal generation | 🟢 ACTIVE | Advisory only |
| `orchestrator/` | Hermes control plane | 🟢 ACTIVE | Audit, docs, git ops |
| `self_improvement_v2/` | SI v2 engine | 🟢 ACTIVE (observation) | Proposals only |
| `freqtrade/shared/kill_switch.py` | Central kill switch | 🟡 PENDING (#220) | Override all entries |
| `freqtrade/shared/primo_signal.py` | Signal bridge | 🟢 ACTIVE | Advisory + kill-switch block |
| `freqtrade/shared/fleet_risk_manager.py` | Fleet risk state | 🟢 ACTIVE | Advisory |
| `freqtrade/` (fleet) | Dry-run execution | 🟢 ACTIVE | Strategy logic |
| `freqforge/` | FreqForge bot | 🟢 ACTIVE | Strategy logic |
| `freqforge-canary/` | Canary bot | 🟢 ACTIVE | Strategy logic |
| `tools/freqforge/` | Shadow evaluator | 🟡 PASSIVE | None (observer) |
| `shadowlock/` | ShadowLock service | 🟢 ACTIVE | Evidence trail |
| `dashboard.py` | Operational dashboard | 🟢 ACTIVE | Read-only |
| `Caddyfile` | Reverse proxy | 🟢 ACTIVE | Fleet routing |
| RiskGuard (spec) | Safety gates | 🔶 SI v2 SPEC | Advisory design |
| ShadowLogger | Audit trail | 🟢 DEPLOYED | Evidence |
| SI v2 Controller | Automation control | ⏸ PAUSED | HUMAN_ONLY merge |

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
| SI v2 Module Map | `self_improvement_v2/README.md` |
| Kill-Switch Runbook | `docs/runbooks/kill-switch.md` |
| Roadmap v2 | `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` |
| Safety Contract | `docs/specs/runtime-safety-contract.md` |
| AGENTS.md | `AGENTS.md` |
