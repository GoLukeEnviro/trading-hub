# Mem0 Memory Recovery — Corrected Report

**Date:** 2026-05-17 14:27 UTC
**Run ID:** mem0-memory-recovery-20260517
**Status:** READ-ONLY AUDIT — NO MUTATIONS

## Previous Error

The earlier Dream Mode recovery report (`dream-mode-memory-recovery-report-20260517.md`)
incorrectly treated Holographic `memory_store.db` as the active memory database.
**This was wrong.** That report has been marked OUTDATED.

## Corrected Active Backend

| Attribute | Value |
|-----------|-------|
| **Active backend** | **Mem0 (cloud)** |
| Not active | Holographic (legacy) |
| API base | `https://api.mem0.ai/v1` |
| User ID | `luke-hermes` |
| Agent ID | `hermes` |
| Plugin | `/opt/hermes/plugins/memory/mem0/__init__.py` |
| SDK version | mem0ai 2.0.2 |
| Config location | `/opt/data/profiles/orchestrator/config.yaml` → `memory.mem0` |

## Mem0 Runtime Proof

| Test | Result | Evidence |
|------|--------|----------|
| Read | **YES** | GET /memories/ returns 100 unique memories, HTTP 200 |
| Write | NOT TESTED | Would require test insert — skipped per safety rules |
| Retrieval | **YES** | POST /search/ returns scored results (0.64–0.90) |
| Total unique memories | **100** | API returns same 100 at any offset (pagination bug or API limit) |

### Retrieval Quality Sample

| Query | Top Score | Result |
|-------|-----------|--------|
| "FreqForge trading configuration" | 0.90 | FreqForge Main and Canary trading_mode=futures |
| | 0.82 | FreqForge Canary replaced the migration |
| | 0.75 | File path for config_freqforge_dryrun.json |

## Holographic Status: LEGACY ONLY

Holographic databases are **not** the active runtime memory backend.
They may contain useful legacy facts for import into Mem0 but must not be treated as live.

| DB | Facts | Integrity | Status |
|----|------:|-----------|--------|
| `memory_store.db` (live mount) | 380 | ok | Legacy — restored from .bak earlier today |
| `.bak.20260517` | 380 | ok | Backup source |
| Dream Mode backup 2026-05-16 | 371 | ok | Backup |
| dryrun | 354 | ok | Backup |
| raw_import (2026-05-14) | 2,385 | ok | Pre-dedup import, bulk |

## Legacy Fact Reclassification

Total legacy facts extracted: 3,870
Unique after cross-source dedup: 2,394

| Label | Count | Description |
|-------|------:|-------------|
| MEM0_IMPORT_CANDIDATE_CRITICAL | 212 | Current architecture, actionable, high value |
| MEM0_IMPORT_CANDIDATE_USEFUL | 1401 | Useful system/project references |
| LEGACY_ARCHIVE_ONLY | 774 | Generic, vague, or outdated |
| DO_NOT_IMPORT | 7 | Secrets, test noise, wrong paths |

## Proposed Import Batches

### Batch 1 — Critical (max 25)

These reference current architecture with specific, actionable details:

1. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) FreqForge v0.1 must remain passive and must not influence orders
2. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke prefers deterministic, no-lookahead indicators and deterministic system components over AI-based methods for tradin
3. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Hermes-orchestrator creates and maintains detailed reference documentation for baseline comparisons and results (e.g., p
4. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke prefers deterministic, fail-open system design — his RiskGuard must be deterministic (same input → same output), an
5. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke works across multiple domains — AI agent development, crypto trading bots (Freqtrade), an e-commerce Shopify store,
6. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Consistently requires deterministic components in his trading system, such as deterministic no‑lookahead indicators and 
7. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Hermes-orchestrator consistently operates all Freqtrade bot instances in dry‑run mode, using the dry_run flag true to av
8. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke consistently operates a Docker-based infrastructure on Hetzner VPS using a Tailscale → Caddy → Docker(ki-fabrik) pa
9. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke engages in trading activities including use of FreqTrade, FreqForge, MERKUR, backtesting, paper trading, and live t
10. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke’s freqtrade bot sent startup information indicating the protecitions in use are "CooldownPeriod", "StoplossGuard", 
11. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Dry-run deployment uses container freqtrade-fomo-phase3, network ki-fabrik, port 127.0.0.1:8087, dry_run=true, and initi
12. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Security verification of Hermes containers includes checking for exposed host ports, Docker socket mounts, and confirmin
13. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke uses Bitget exchange with USDT pairs for his Freqtrade bots
14. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke uses FreqTrade and FreqForge for trading systems.
15. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke’s freqtrade Regime‑Hybrid bot was upgraded on 2026-05-06 to support futures, isolated margin, and shorting, and it 
16. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke uses tools like FreqTrade, FreqForge, MERKUR, and runs backtests and live trading bots.
17. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke’s trading setup uses FreqForge MERKUR-7X with ensemble logic, a hard stop at -3%, and requires a minimum of 60–80 l
18. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke’s risk filter script imports and uses a class named "RiskGuard" to evaluate raw signals.
19. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) FreqForge uses port 8086 and Regime‑Hybrid uses port 8085.
20. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Gate-basierte Phasen-Freigabe: Luke arbeitet ausschließlich Gate-by-Gate (A→B→C→D→E→F) mit hart formulierten Grenzen zwi
21. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Twister Paper-Trading Lab ACTIVE. Workspace: /home/hermes/twister-lab/ (outside /home/hermes/projects/ which is root-own
22. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) GAP-Report 2026-05-16 completed. Critical finding: Signal Chain fully broken — ai-hedge-fund-crypto produces signals, bu
23. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) signal_bridge.py deployed: ai-hedge-fund-crypto → 3x primo_signal_state.json (shared + momentum + regime-hybrid). Cron: 
24. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Luke operates under a strict dry-run-only safety regime for trading — he consistently validates that bots run in dry_run
25. **[MEM0_IMPORT_CANDIDATE_CRITICAL]** (conf=0.90) Prefers operating all bots in dry-run (simulated) mode to avoid real capital risk

### Batch 2 — Useful (max 75)

75 items selected. Top examples:

1. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Negative claims about tools or features (e.g., 'tool X is broken') must not be saved as they may harden into self-impose
2. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Luke prioritizes deep data-driven research and backtesting validation prior to any deployment and never modifies running
3. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) NEVER set `writeFrequency` to "async" on systems with long-running sessions due to duplicate observation risk.
4. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Luke’s forthcoming actions include only documentation updates and analysis, explicitly stating that strategy files, conf
5. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) `sessionStrategy` must not be changed from `per-repo` without first proving repo state and config resolution path.
6. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Prefers extensive backtesting (≈90 days of historical data) across multiple cryptocurrency pairs before moving to live d
7. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.65) Luke ensures that each session results in at least one skill update, reviewing and patching skills systematically.
8. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Communicates in technical German/English mix, preferring direct informal address in German with English technical termin
9. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Code‑switches between German and English, using German for casual speech and English for technical terms.
10. **[MEM0_IMPORT_CANDIDATE_USEFUL]** (conf=0.60) Follows systematic diagnostic protocols: baseline run → identify killer → remove component → compare → repeat.

... and 65 more. See JSON manifest for full list.

## GO / NO-GO Decision

| Decision | Condition | Status |
|----------|-----------|--------|
| GO batch_1 | Mem0 active + retrieval works + user GO | **NEEDS LUKE'S GO** |
| GO batch_2 | After batch_1 verified | **NEEDS LUKE'S GO** |
| NO-GO bulk | 1,401 useful items too many for blind import | **BLOCKED** |
| NO-GO Holographic restore | Holographic is not active backend | **REJECTED** |

## Recommended Next Step

1. **Review batch_1 (25 items)** in the JSON manifest
2. If approved → import via Mem0 API (`POST /memories/`)
3. Verify imported memories appear in retrieval
4. Then consider batch_2 if quality holds

Exact import command (proposed, NOT executed):
```bash
# For each approved memory in batch_1:
curl -X POST https://api.mem0.ai/v1/memories/ \
  -H "Authorization: Token $MEM0_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "user_id": "luke-hermes", "agent_id": "hermes"}'
```

## Files Written

| File | Purpose |
|------|---------|
| `docs/context/mem0-memory-recovery-correction-20260517.md` | This corrected report |
| `docs/context/mem0-memory-recovery-correction-20260517.json` | Full manifest with all classified items |
| `docs/context/dream-mode-memory-recovery-report-20260517.md` | Marked OUTDATED |
| `docs/context/dream-mode-memory-recovery-manifest-20260517.json` | Marked OUTDATED |

## Safety Confirmation

- [x] No destructive mutation performed
- [x] Mem0 identified as active backend from config + runtime evidence
- [x] Holographic correctly labeled as LEGACY_ONLY
- [x] Legacy DBs inventoried as import sources only
- [x] 2,394 unique facts reclassified for Mem0 import suitability
- [x] Import batches proposed, NOT executed
- [x] Old reports marked OUTDATED
