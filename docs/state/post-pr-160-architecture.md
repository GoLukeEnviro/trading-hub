# Post-PR-160 Architecture — Simplified Overview

> **Canonical at commit `fdac27c`** — controller contract layer is now merged.
>
> This diagram describes the architecture **after** PR #160. The controller is
> PAUSED. All SI v2 intelligence runs on fixtures only.

---

## Architecture Diagram

```mermaid
%%{init: {'themeVariables': { 'fontSize': '13px'}}}%%
graph TB
    subgraph External["External / VPS"]
        AHFC["ai-hedge-fund-crypto<br/>Signal Generator<br/>(Bitget Futures OHLCV)"]
        SLW["Shadowlock Writer<br/>SQLite on VPS"]
    end

    subgraph Runtime["Docker Compose Fleet"]
        FF["FreqForge<br/>(dry-run)"]
        RH["Regime-Hybrid<br/>(dry-run)"]
        FFC["FreqForge-Canary<br/>(dry-run)"]
        FAR["FreqAI-Rebel<br/>(dry-run)"]
    end

    subgraph Controller["SI v2 Continuous Controller<br/>🚫 PAUSED"]
        direction TB
        ST["STATE.json<br/>operation_level: L3_REPOSITORY_ONLY<br/>runtime_policy: FORBIDDEN"]
        Q["QUEUE.json<br/>(empty)"]
        POL["POLICY.md<br/>merge_policy: HUMAN_ONLY"]
    end

    subgraph SIv2["SI v2 Offline Pipeline<br/>🧪 FIXTURE-ONLY"]
        direction TB
        RB["Rainbow Core<br/>validator / snapshot / drift guard<br/>(fixture signals only)"]
        EV["Evidence Pipeline<br/>bundle builder / manifest<br/>(fixture data only)"]
        RG["Regime Detection<br/>#55-#56: NOT STARTED<br/>fixture labels only"]
        AT["Attribution<br/>#57-#59: NOT STARTED<br/>fixture aggregator only"]
        QG["Quality Gate<br/>offline, artifact-existence check"]
        EP["Episode Runner<br/>skeleton + report<br/>(fixture only)"]
    end

    subgraph Phase1["Phase 1 Intelligence Layer<br/>⬜ NOT STARTED"]
        I55["#55: Regime Detector Schema"]
        I56["#56: Regime Run & Enrichment"]
        I57["#57: Performance Attribution Engine"]
        I58["#58: source_regime_stats Table"]
        I59["#59: Automated Attribution Reports"]
        I60["#60: Shadowlock Maintenance Command"]
        I61["#61: Intelligence Layer Tracker"]
    end

    subgraph Blocked["⛔ BLOCKED"]
        TIMER["Timer-based Activation<br/>(cron not installed)"]
        USER["Dedicated User Isolation<br/>(not created)"]
    end

    AHFC -->|hermes_signal.json| FF
    AHFC --> RH
    AHFC --> FFC
    AHFC --> FAR

    SLW -.->|fixture only| SIv2

    SIv2 -.->|design reference only| Phase1
    Controller --- POL
    Controller --- ST
    Controller --- Q

    Controller -.->|PAUSED - awaiting epic| Phase1

    TIMER -->|blocks| Phase1
    USER -->|blocks| Phase1

    classDef done fill:#a8e6cf,stroke:#333,stroke-width:1px
    classDef active fill:#d3e3fc,stroke:#333,stroke-width:1px
    classDef notstarted fill:#ffd3b6,stroke:#333,stroke-width:1px
    classDef paused fill:#ffaaa5,stroke:#333,stroke-width:1px
    classDef blocked fill:#d3d3d3,stroke:#999,stroke-width:1px,stroke-dasharray:5 5

    class AHFC,SLW active
    class FF,RH,FFC,FAR done
    class Controller paused
    class RB,EV,AT,QG,EP done
    class RG,I55,I56,I57,I58,I59,I60,I61 notstarted
    class TIMER,USER blocked
```

---

## Layer Summary

| Layer | Status | Description |
|-------|--------|-------------|
| **Signal Generation** | ✅ ACTIVE | `ai-hedge-fund-crypto` runs live on VPS, outputs signal JSON |
| **Execution Fleet** | ✅ DRY-RUN | 4 Freqtrade bots in dry-run mode, no live orders |
| **SI v2 Controller** | 🚫 PAUSED | Repository-level control plane, awaiting next approved epic |
| **SI v2 Offline Pipeline** | ✅ COMPLETE (fixture) | All offline components built, but fixture-only |
| **Phase 1 Intelligence** | ⬛ NOT STARTED | Issues #55–#61, all OPEN, no code written |
| **Timer Activation** | ⛔ BLOCKED | Cron-based scheduler not installed |
| **Dedicated User** | ⛔ BLOCKED | Credential isolation not implemented |
| **RiskGuard (production)** | 📄 SPEC ONLY | No deployed component |

---

## Data Flow Summary

```
[ai-hedge-fund-crypto]  →  signal JSON  →  [Freqtrade bots (dry-run)]
                                          ↕ (read-only)
[Shadowlock Writer]  →  SQLite  →  [SI v2 Offline Pipeline (fixture-only)]

[External state: /opt/data/si-v2-controller/state/]
    ├── STATE.json      controller_status: "PAUSED"
    ├── QUEUE.json      empty
    ├── CURRENT_EPIC.md no active epic
    ├── HANDOFF.md      awaiting next approved epic
    └── runs/           proof report only
```

---

## Key Invariants

1. **No live trading** — all bots `dry_run=true`, `LIVE_FORBIDDEN` state
2. **No timer-based automation** — controller activation requires manual invocation
3. **No dedicated user** — no credential isolation for controller operations
4. **No production attribution** — all evidence/attribution is fixture-based
5. **Controller merge policy: HUMAN_ONLY** — no automated merge

---

*Architecture diagram at commit fdac27c, 2026-06-11*
