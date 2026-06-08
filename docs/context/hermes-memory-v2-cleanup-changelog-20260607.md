# Hermes Memory v2 — Cleanup Changelog

**Datum:** 2026-06-07
**Typ:** Dokumentation-only, keine Mutation
**Verdict:** GREEN
**Collection:** hermes_memories_v2

## 1. Executive Summary

Die Hermes Memory v2 Collection wurde von **66 auf 39 kanonische Memories** bereinigt.

| Kategorie | Anzahl | Aktion |
|---|---:|---|
| MERGE (Sources → Targets) | 7 → 4 | Source gelöscht, Target-Text erweitert |
| QUARANTINE (operational noise) | 15 | Aus aktivem Recall entfernt |
| DROP (low-value) | 4 | Gelöscht |
| EXPIRE (superseded) | 1 | Gelöscht, Nachfolger behalten |
| **Gesamt entfernt** | **27** | **66 → 39 aktive Memories** |

Alle Mutationen liefen über exakte UUIDs. Keine semantischen Löschqueries. Rollback möglich.

## 2. Before / After

| Metrik | Before | After |
|---|---:|---:|
| Aktive Memories | 66 | 39 |
| Qdrant Points | 66 | 39 |
| Collection Status | green | green |
| Vector Size | 2560 | 2560 |
| Distance Metric | Cosine | Cosine |

## 3. Updated Merge Targets

4 Ziel-Memories wurden aktualisiert (Text erweitert, Vektor beibehalten):

### TARGET #48 (`d749c9c2...83a4`)

**Aktualisierter Text:** Live trading or strategy deployment requires configured API keys, backtest or walk-forward evidence, shadow-mode or dry-run confirmation, a risk review, a rollback plan, and explicit operator approval; Regime-Hybrid remains dry-run until those gates pass.

**Eingefügte Quellen (3):**

- **#4** (`5b419fcf...d651`): Live deployment of any bot requires configured API keys, successful walk‑forward results, an active shadow‑mode phase...
- **#36** (`9ff940d7...50ff`): User requires that before merging trading strategy changes, Hermes must provide backtest evidence, dry-run observatio...
- **#47** (`513bdf3f...feec`): User mandates that Regime-Hybrid bot changes must remain in dry-run mode until enough closed trades show positive pro...

### TARGET #11 (`0decfd76...ad1c`)

**Aktualisierter Text:** Permission repair in the trading repo should be minimal and targeted, preferring ACLs over recursive permission changes or broad ownership fixes.

**Eingefügte Quellen (1):**

- **#24** (`2b6644e1...6ece`): User's trading permission-hardening guardian can auto-correct root-owned files in the trading-guardian container by r...

### TARGET #14 (`c68e14f7...0601`)

**Aktualisierter Text:** Docker proxy EXEC is disabled; approved exec operations must bypass the proxy and use the direct Unix socket.

**Eingefügte Quellen (1):**

- **#41** (`bdcc4546...856e`): User notes that the Docker proxy has EXEC disabled, so direct docker exec must bypass the proxy using the Docker sock...

### TARGET #8 (`c175b126...6b73`)

**Aktualisierter Text:** The active Hermes memory stack uses green-mem0 with green-qdrant and the canonical collection hermes_memories_v2.

**Eingefügte Quellen (2):**

- **#46** (`2415f56a...2ac8`): User's active memory stack uses green-mem0 with green-qdrant and the collection hermes_memories_v2 for Hermes memory ...
- **#50** (`4e7b0272...979b`): User's active vector store is Qdrant, using the collection named hermes_memories_v2.

## 4. Alle entfernten IDs (27 gesamt)

| # | Audit-Ref | UUID (gekürzt) | Kategorie | Vorschau |
|---:|---:|---|---|---|
| 1 | #1 | `9094dc75...6ed4` | QUARANTINE | The Freqtrade Webserver (Frouha) is intended to listen on port 8180, but the ... |
| 2 | #2 | `4b648380...bdcc` | QUARANTINE | Four Freqtrade bots run in dry‑run mode: FreqForge Canary on port 8081 with C... |
| 3 | #3 | `e29c0cde...fcb7` | QUARANTINE | User's system hosts three Flask dashboards, all bound to 127.0.0.1 only: Trad... |
| 4 | #4 | `5b419fcf...d651` | MERGE | Live deployment of any bot requires configured API keys, successful walk‑forw... |
| 5 | #5 | `cacb6fe2...f411` | QUARANTINE | Rebel bot's configuration sets max_open_trades to 0, indicating it is not ena... |
| 6 | #15 | `3cd21d73...1c86` | QUARANTINE | User's ai-hedge-fund-crypto signal layer runs inside a Docker container that ... |
| 7 | #17 | `eb179750...e514` | QUARANTINE | User plans to fix the Hermes container permission issue by modifying its dock... |
| 8 | #18 | `d2433e22...2922` | QUARANTINE | User has configured the following cron jobs for system automation: signal-hea... |
| 9 | #19 | `33e07621...f683` | DROP | User requests to first locate the Telegram bot's registration and define its ... |
| 10 | #20 | `0621fae0...8347` | DROP | User intends to reinstall and configure the Telegram bot with the upcoming AP... |
| 11 | #24 | `2b6644e1...6ece` | MERGE | User's trading permission-hardening guardian can auto-correct root-owned file... |
| 12 | #26 | `d1811862...bf1a` | QUARANTINE | The file /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/re... |
| 13 | #27 | `833d2836...9d8a` | QUARANTINE | User requested creation of a dedicated research configuration file at /home/h... |
| 14 | #28 | `09cb712b...e315` | QUARANTINE | User configures the Freqtrade WebUI Docker container with a safe port binding... |
| 15 | #30 | `62e8898c...7dd7` | QUARANTINE | User's Tailscale Funnel listens on port 443, forwards incoming traffic to Cad... |
| 16 | #31 | `e3eb8efd...c50b` | QUARANTINE | User's self_optimizer module for the Regime-Hybrid bot resides at /home/herme... |
| 17 | #33 | `4ca5bef9...d5f6` | DROP | Hermes memory curation ranks facts by durability, operational value, confiden... |
| 18 | #36 | `9ff940d7...50ff` | MERGE | User requires that before merging trading strategy changes, Hermes must provi... |
| 19 | #40 | `dd1a3e60...4483` | QUARANTINE | User stores self-improvement files for trading bots A, B, C, and D in the dir... |
| 20 | #41 | `bdcc4546...856e` | MERGE | User notes that the Docker proxy has EXEC disabled, so direct docker exec mus... |
| 21 | #46 | `2415f56a...2ac8` | MERGE | User's active memory stack uses green-mem0 with green-qdrant and the collecti... |
| 22 | #47 | `513bdf3f...feec` | MERGE | User mandates that Regime-Hybrid bot changes must remain in dry-run mode unti... |
| 23 | #50 | `4e7b0272...979b` | MERGE | User's active vector store is Qdrant, using the collection named hermes_memor... |
| 24 | #55 | `ef122307...8aa0` | DROP | User assigned the task to update the AGENTS.md and SOUL.md documentation, bri... |
| 25 | #56 | `4d64db2a...625b` | QUARANTINE | User defined an agent prompt with id "technical-gap-debt-context-audit" and v... |
| 26 | #62 | `3c7235b5...401a` | EXPIRE | User has switched to a different embedding model for the system |
| 27 | #65 | `5c38b12f...891c` | QUARANTINE | User proposes that the three bots, containers, and frameworks be combined ont... |

## 5. Quarantined Operational Noise (15)

Diese Memories enthielten operativen Noise, temporäre Zustände oder Redundanzen,
die nicht zur dauerhaften kanonischen Erinnerung gehören:

- **#1** (`9094dc75...6ed4`): The Freqtrade Webserver (Frouha) is intended to listen on port 8180, but the current Caddy configuration incorrectly ...
- **#2** (`4b648380...bdcc`): Four Freqtrade bots run in dry‑run mode: FreqForge Canary on port 8081 with Caddy route trade.taile6801f.ts.net, Regi...
- **#3** (`e29c0cde...fcb7`): User's system hosts three Flask dashboards, all bound to 127.0.0.1 only: Trading Dashboard on port 5000 routed via /d...
- **#5** (`cacb6fe2...f411`): Rebel bot's configuration sets max_open_trades to 0, indicating it is not enabled for live or dry‑run trading yet.
- **#15** (`3cd21d73...1c86`): User's ai-hedge-fund-crypto signal layer runs inside a Docker container that is configured to listen on network port ...
- **#17** (`eb179750...e514`): User plans to fix the Hermes container permission issue by modifying its docker‑compose configuration to add group_ad...
- **#18** (`d2433e22...2922`): User has configured the following cron jobs for system automation: signal-heartbeat, trading-pipeline, drawdown-guard...
- **#26** (`d1811862...bf1a`): The file /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py was ...
- **#27** (`833d2836...9d8a`): User requested creation of a dedicated research configuration file at /home/hermes/projects/trading/freqtrade/bots/re...
- **#28** (`09cb712b...e315`): User configures the Freqtrade WebUI Docker container with a safe port binding of 127.0.0.1:9092:8080
- **#30** (`62e8898c...7dd7`): User's Tailscale Funnel listens on port 443, forwards incoming traffic to Caddy which listens on port 3000, and Caddy...
- **#31** (`e3eb8efd...c50b`): User's self_optimizer module for the Regime-Hybrid bot resides at /home/hermes/projects/trading/freqtrade/bots/regime...
- **#40** (`dd1a3e60...4483`): User stores self-improvement files for trading bots A, B, C, and D in the directory path "self_improvement".
- **#56** (`4d64db2a...625b`): User defined an agent prompt with id "technical-gap-debt-context-audit" and version "1.0"
- **#65** (`5c38b12f...891c`): User proposes that the three bots, containers, and frameworks be combined onto a single dashboard for simpler overview

## 6. Dropped Low-Value Items (4)

- **#19** (`33e07621...f683`): User requests to first locate the Telegram bot's registration and define its intended functions.
- **#20** (`0621fae0...8347`): User intends to reinstall and configure the Telegram bot with the upcoming API key.
- **#33** (`4ca5bef9...d5f6`): Hermes memory curation ranks facts by durability, operational value, confidence, currentness, specificity, and safety...
- **#55** (`ef122307...8aa0`): User assigned the task to update the AGENTS.md and SOUL.md documentation, bringing outdated information up to date

## 7. Expired / Superseded Items (1)

- **EXPIRED #62** (`3c7235b5...401a`):
  - User has switched to a different embedding model for the system
- **RETAINED #57** (`9a6a6417...ee78`):
  - User selected the Gwen3-Embedding model (qwen3-embedding:4b) for the system, configured with 2560-dimensional embeddings and a collection size of 1024, and requested it be applied throughout the ar...

## 8. Validation Results

### Recall Sanity Checks (4/4 PASS)

| Query | Top Score | Verdict |
|---|---:|---|
| green-mem0 green-qdrant hermes_memories_v2 | 0.901 | PASS |
| dry-run safety | 0.679 | PASS |
| Docker proxy EXEC disabled | 0.936 | PASS |
| qwen3-embedding 2560 | 0.870 | PASS |

### Post-Mutation Counts

- Qdrant points: **39**
- mem0 export: **39**
- Targets #8, #11, #14, #48, #57: alle **present**
- Secret-Einführungen: **0**

## 9. Rollback Artifacts

| Artefakt | Pfad |
|---|---|
| Pre-Mutation Backup (66 Memories) | `hermes-memory-v2-pre-mutation-backup-20260607-110654.json` (sha256=4ca2106cf5b9bb2a... 33520B) |
| Post-Mutation Export (39 Memories) | `hermes-memory-v2-post-mutation-export-20260607-111112.json` (sha256=651b423bbce1afe4... 20321B) |
| Execution Report MD | `hermes-memory-v2-exact-id-patch-execution-20260607-111112.md` (sha256=404267a12bac80e2... 6148B) |
| Execution Report JSON | `hermes-memory-v2-exact-id-patch-execution-20260607-111112.json` (sha256=ffb407b361ad8a99... 8729B) |
| Audit Report MD | `hermes-memory-v2-curation-audit-20260607-103359.md` (sha256=6a885d0f28e7414c... 24127B) |
| Audit Report JSON | `hermes-memory-v2-curation-audit-20260607-103359.json` (sha256=2a6af40e6c078596... 55632B) |
| Patch Plan MD | `hermes-memory-v2-exact-id-patch-plan-20260607-105142.md` (sha256=8ea32a3c53138cc3... 24792B) |
| Patch Plan JSON | `hermes-memory-v2-exact-id-patch-plan-20260607-105142.json` (sha256=cd9c6be4150da2cc... 33691B) |

**Rollback:** Pre-Mutation-Backup enthält alle 66 Original-Memories mit IDs, Texten und Metadaten.

## 10. Final Canonical State

```
Hermes Memory v2:
- Active collection: hermes_memories_v2
- Active canonical memories: 39
- Operational noise: removed from active recall
- Rollback backup: exists (66 memories)
- Recall sanity: 4/4 PASS
- auto_extract: disabled
- Status: operational vollständig validiert
```

---

*Dieser Changelog dokumentiert die abgeschlossene Bereinigung. Keine weiteren Mutationen erforderlich.*

*Generiert: 2026-06-07 11:47 UTC*