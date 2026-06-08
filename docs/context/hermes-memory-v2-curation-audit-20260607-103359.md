# Hermes Memory v2 Curation Audit

## Executive Verdict

**GREEN** — audit-only completed, no memory mutation performed, report is usable for patch planning.
The canonical core is strong, but the export still contains operational noise that should stay out of canonical memory.

## Preflight Results

- Skill file exists: `/opt/data/profiles/orchestrator/skills/maintenance/hermes-memory-curation-skill/SKILL.md`
- Readability by runtime user `hermes`: YES (direct `test -r` succeeded; `sudo` is not installed here)
- Active orchestrator config: `memory.provider: mem0`, `auto_extract: false`, `base_url: http://green-mem0:8787`, `user_id: luke-hermes`
- Qdrant collections: `hermes_memories_v2`, `mem0migrations`
- `hermes_memories_v2`: status=green, points_count=66, vector_size=2560, distance=Cosine
- mem0 export count: 66 memories (IDs present)

## Memory Count Confirmation

- Exported current active memories: **66**
- Qdrant collection `hermes_memories_v2`: **66 points**, **2560-dim**, **Cosine**, **green**
- `mem0_profile` returned the same active-memory set without error; the profile is consistent with the direct export.

## Candidate Table

| memory_id | short_fact | classification | durability | decision_value | context_independence | evidence_strength | volatility_risk | privacy_risk | canonical_fit | reason | proposed_action |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 9094dc75-d849-4cb5-bb56-0b2b1eaa6ed4 | The Freqtrade Webserver (Frouha) is intended to listen on port 8180, but the current Caddy configuration inco… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| 4b648380-3b37-4361-a206-297912d2bdcc | Four Freqtrade bots run in dry‑run mode: FreqForge Canary on port 8081 with Caddy route trade.taile6801f.ts.n… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| e29c0cde-435c-4a93-b004-f0130f4ffcb7 | User's system hosts three Flask dashboards, all bound to 127.0.0.1 only: Trading Dashboard on port 5000 route… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| 5b419fcf-4937-4297-ba87-a3a2ebadd651 | Live deployment of any bot requires configured API keys, successful walk‑forward results, an active shadow‑mo… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 48 (live-deployment safety gate) |
| cacb6fe2-05fc-40f3-aecf-d594e78ff411 | Rebel bot's configuration sets max_open_trades to 0, indicating it is not enabled for live or dry‑run trading… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| ad8c97fd-6746-4fd5-9a8a-dd9ec65eb402 | RegimeHybrid bot is configured with use_custom_stoploss set to False, as the patch has been deployed. | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 48f636a3-bb49-4143-a104-c15b31214396 | User specifies that final checks must be phrased as 'operational vollständig validiert' rather than claiming … | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| c175b126-7e27-4ad5-b3e6-402d4f246b73 | User states that the active Hermes memory collection is hermes_memories_v2, accessed via the green‑mem0 insta… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 1747b38c-70f5-4d17-a120-a8af675bec40 | User runs embeddings locally through the green-ollama container using the qwen3-embedding model | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| b22e422e-faf9-4403-af62-e11f82d44a14 | Freqtrade bots operate in futures trading mode with isolated margin on the Bitget exchange, configured for dr… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 0decfd76-f961-468a-9e32-c47b1d79ad1c | Container permission changes should be minimal and targeted, preferring ACLs over recursive permission modifi… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| aa825cf0-f1ce-424a-90ca-75e54b810eac | Freqtrade bots bind exclusively to localhost ports and are never exposed publicly unless routed through Caddy… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 80f44c7a-0509-42e1-90b7-12028cc2ea6f | Hermes containers run on multiple Docker networks, specifically hermes-net and ki-fabrik, to provide service … | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| c68e14f7-986a-4b62-b64b-f57372f20601 | Docker proxy has EXEC disabled, requiring direct Unix socket access for exec operations when approved. | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 3cd21d73-07f2-44a0-a4fd-62b0bb5d1c86 | User's ai-hedge-fund-crypto signal layer runs inside a Docker container that is configured to listen on netwo… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| a7781a59-0348-47db-b1b0-79ca6804a9dc | User requires peer card facts to be labeled with explicit categories such as [Trading], [Risk], [Deployment],… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| eb179750-72fa-491a-bbc7-e6ad82c9e514 | User plans to fix the Hermes container permission issue by modifying its docker‑compose configuration to add … | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| d2433e22-d170-4e03-a507-c32859f72922 | User has configured the following cron jobs for system automation: signal-heartbeat, trading-pipeline, drawdo… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| 33e07621-abc0-4c2b-b5a6-6dd24c9df683 | User requests to first locate the Telegram bot's registration and define its intended functions. | DROP | 1 | 0 | 1 | 3 | 5 | 0 | 0 | Low-value, duplicate, or progress-only note; not worth canonical retention. | Do not retain. |
| 0621fae0-051d-4bf6-aa30-a574aba08347 | User intends to reinstall and configure the Telegram bot with the upcoming API key. | DROP | 1 | 0 | 1 | 3 | 5 | 0 | 0 | Low-value, duplicate, or progress-only note; not worth canonical retention. | Do not retain. |
| 1ee2ac15-a9f8-44f9-a472-b8143dab75a7 | User has a Telegram bot that provides Heartbeat monitoring, Intelligence Reports, and critical system analysi… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| bde8cc39-07f7-463c-894b-229054624723 | User demands data‑driven configuration and rejects any blanket default settings, insisting that all deploymen… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 04852e92-dbcf-4199-a1b1-df9a9e6edfbf | User requires that when two existing skills overlap, the assistant must propose merging them instead of keepi… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 2b6644e1-66b1-457d-aef9-53ca25046ece | User's trading permission-hardening guardian can auto-correct root-owned files in the trading-guardian contai… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 11 (minimal targeted permission repair) |
| 6d1c8ba1-f5e1-4cc8-9549-bf852509703a | User's FreqAI Rebel configuration uses the RebelLiquidation strategy on a 5‑minute timeframe, trades BTC and … | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| d1811862-24ae-4981-b4c8-51caf9c4bf1a | The file /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context or task log only |
| 833d2836-bedf-4781-94bd-af1e53779d8a | User requested creation of a dedicated research configuration file at /home/hermes/projects/trading/freqtrade… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context or task log only |
| 09cb712b-4efe-43a3-9c31-a5a25c9ce315 | User configures the Freqtrade WebUI Docker container with a safe port binding of 127.0.0.1:9092:8080 | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context or task log only |
| 4ab5980b-78a8-4a37-a358-993c338f5345 | User's active trading fleet includes the Regime‑Hybrid bot, which is configured with a side‑aware gate and op… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 62e8898c-62ad-48a4-a96d-2f312c577dd7 | User's Tailscale Funnel listens on port 443, forwards incoming traffic to Caddy which listens on port 3000, a… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| e3eb8efd-b92c-4c79-908a-2dd4cda2c50b | User's self_optimizer module for the Regime-Hybrid bot resides at /home/hermes/projects/trading/freqtrade/bot… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context or task log only |
| 383879d3-93f4-4ce1-8016-43d95bf9d54b | User requires that the sessionStrategy remain set to per-repo and cannot be changed without first proving the… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 4ca5bef9-718f-4e57-88a7-c74a15f0d5f6 | Hermes memory curation ranks facts by durability, operational value, confidence, currentness, specificity, an… | DROP | 1 | 0 | 1 | 3 | 5 | 0 | 0 | Low-value, duplicate, or progress-only note; not worth canonical retention. | Do not retain. |
| 4e4b7697-6985-45d9-81ed-9747756ac68d | User states that the old hermes_memories Qdrant collection should not be blindly migrated to the active v2 co… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| d4e193fb-fc17-4100-a143-8ec234a92861 | User states that Green-mem0 employs an extraction policy which filters out temporary content containing words… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 9ff940d7-5f0c-4c3c-b199-637fb26b50ff | User requires that before merging trading strategy changes, Hermes must provide backtest evidence, dry-run ob… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 48 (strategy-change safety gate) |
| 0d628259-3adc-44dc-8f50-8de7646204bf | User mandates that memory cleanup procedures should prioritize quarantining items and documenting them rather… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 2bc431d0-1e00-4473-b46a-adcc2f5cd2fd | User states that Mem0 Cloud is not the canonical memory target for the Hermes setup; the current storage targ… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 7ac0ccde-0aaa-48b5-a07d-c591add90267 | User specifies that Hermes must avoid broad cleanup operations, including recursive removal, recursive permis… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| dd1a3e60-3e02-4ace-ab20-1a6558354483 | User stores self-improvement files for trading bots A, B, C, and D in the directory path "self_improvement". | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context only |
| bdcc4546-0979-46af-aab1-da63e99c856e | User notes that the Docker proxy has EXEC disabled, so direct docker exec must bypass the proxy using the Doc… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 14 (exec-by-socket approval rule) |
| cf12b2b5-5bf8-4e2e-ba48-a1540bca1828 | Polymarket-Fadi runs in paper (dry‑run) mode and must not be treated as a real‑capital trading service unless… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| ff68cabb-1f6e-4ee9-82f8-6345482c178c | User configures Freqtrade bots to use custom db_url files named tradesv3 with each bot's name followed by '.d… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 051cfbd0-e7e0-4535-bee5-d5baa3d31a76 | User states that Hermes memory facts should be durable operational preferences or stable project facts, not t… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| b171beb6-3235-48fa-858b-4bb2a229e7f1 | User intentionally uses Ollama Cloud for Mem0 LLM extraction and stores vector memories locally in green‑qdra… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 2415f56a-26de-4c8a-890f-caf8cbfd2ac8 | User's active memory stack uses green-mem0 with green-qdrant and the collection hermes_memories_v2 for Hermes… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 8 (active memory stack / canonical collection) |
| 513bdf3f-7779-4cab-b782-05a86db0feec | User mandates that Regime-Hybrid bot changes must remain in dry-run mode until enough closed trades show posi… | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 48 (Regime-Hybrid dry-run safety gate) |
| d749c9c2-b9b3-4308-b079-e7b3df9f83a4 | User requires safety gates to be in place before any live trading change, mandating profit evidence, a risk r… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| c1a59b5d-76fa-4a69-ab08-bc5fae4b3998 | User requires trading bots to always run with dry_run=true unless they receive explicit approval. | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 4e7b0272-7db7-4e77-859d-785a7a85979b | User's active vector store is Qdrant, using the collection named hermes_memories_v2. | MERGE | 4 | 4 | 4 | 4 | 2 | 0 | 4 | Useful, but overlaps with a broader canonical rule; normalize wording and keep one statement. | merge into item 8 (active memory stack / canonical collection) |
| aeef29d0-1325-4035-b5eb-7c16b9f33134 | User prefers a local-only Mem0 deployment using Docker with the green-mem0 container for memory storage. | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| a547b127-a3c5-409b-b99d-575b6bd27cd7 | User states that configuration values are supplied through environment variables instead of editing the hardc… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| e65b7277-4cf6-49cb-9c3b-1bd4004d7238 | User mandates that any audit of the autonomous trading system must be performed in read‑only mode, explicitly… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 0781b9eb-04c4-41c7-b74e-c02c71495c54 | User's autonomous trading system is located in the filesystem at the path /home/hermes/projects/trading, whic… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| ef122307-fc39-4f35-961f-3f8a173e8aa0 | User assigned the task to update the AGENTS.md and SOUL.md documentation, bringing outdated information up to… | DROP | 1 | 0 | 1 | 3 | 5 | 0 | 0 | Low-value, duplicate, or progress-only note; not worth canonical retention. | Do not retain. |
| 4d64db2a-c823-475b-962a-49b92778625b | User defined an agent prompt with id "technical-gap-debt-context-audit" and version "1.0" | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | docs/context or skill registry, not canonical memory |
| 9a6a6417-c1af-48cd-b3ee-ecf06703ee78 | User selected the Gwen3-Embedding model (qwen3-embedding:4b) for the system, configured with 2560-dimensional… | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 2f157c35-65ce-4ca0-a35c-1e68caec7ff3 | User defined HERMES PRIME DIRECTIVE v1.0 as the meta-layer context engineering prompt | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 476ab015-9539-4f16-be74-c34340e2bd40 | PolyMarketBot source code is located at https://github.com/MrFadiAi/Polymarket-bot | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| e65cc404-89bf-41d5-bc69-033d67d30014 | User wants the ollama containers to be checked using the local model, the embedded model, and the cloud | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 5afbdae9-e625-43a3-9506-547fbbbe23af | User notes that config.json is hardcoded and cannot be edited | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 3c7235b5-3aa9-4dc9-b7fd-836dd70f401a | User has switched to a different embedding model for the system | EXPIRE | 1 | 0 | 2 | 3 | 5 | 0 | 0 | Outdated/transitional fact superseded by a newer specific memory. | Mark as expired/superseded by item 57. |
| 6f9bc2f8-7a03-427d-bde8-0bd4178676ee | User requires the Memory System to be thoroughly checked from top to bottom, left to right, with zero errors | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 1c0bc047-bc66-47eb-9d6b-0e894ef929a0 | User prefers the Weather Bot to appear higher up on the dashboards | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |
| 5c38b12f-8825-4f78-926e-9a92a02c891c | User proposes that the three bots, containers, and frameworks be combined onto a single dashboard for simpler… | QUARANTINE | 2 | 1 | 2 | 4 | 5 | 0 | 1 | True but operational/snapshot-like; belongs in reports or session context, not canonical memory. | reports/context only |
| e1baed92-e435-4a52-b404-b2387ef1b9fd | User wants PolyMarketBot deployed in its own separate container, isolated from the other bots | KEEP | 5 | 5 | 4 | 4 | 1 | 0 | 5 | Durable, context-independent, decision-shaping fact. | Promote to canonical memory. |

## KEEP Items

- **Durable canonical core:** 39 items
### Memory architecture / recall stack
8, 9, 10, 12, 13, 14, 38, 42, 43, 44, 45, 49, 51, 52, 53, 54, 57, 58, 59, 60, 61, 63, 64, 66

### User preferences / durable operating rules
6, 7, 11, 16, 21, 22, 23, 25, 29, 32, 34, 35, 37, 39, 48


## MERGE Items with normalized wording

- **Merge candidates:** 7 items
- 4 → 48: live-deployment safety gate (API keys + walk-forward + shadow-mode + positive dry-run performance + approval)
- 24 → 11: normalize permission repair into the minimal/targeted repair rule
- 36 → 48: strategy-change safety gate (backtest + dry-run observation + rollback)
- 41 → 14: direct socket exec only after approval
- 46 → 8 and 50 → 8: active memory stack / canonical collection statement
- 47 → 48: Regime-Hybrid remains dry-run until positive profit behavior and acceptable risk metrics

## QUARANTINE Items with destination recommendation

- **Quarantine candidates:** 15 items
- 1,2,3: current dashboard/route/port snapshots — keep in reports/context only
- 5: Rebel max_open_trades=0 is a config snapshot, not a canonical memory
- 15: ai-hedge-fund-crypto port 8410 is a deployment detail
- 17,18: proposed permission fix and cron inventory are operational notes
- 26,27,28,30,31,40,56,65: file paths, prompt IDs, route plans, and task-progress notes belong in docs/context or reports

## DROP Items

- **Drop candidates:** 4 items
- 19,20: Telegram bot registration/reinstall are task instructions, not durable memory; 20 also mentions a future API key and stays out of canonical memory
- 33: curation-ranking policy is already captured by the new skill, so the memory copy is redundant
- 55: docs update task-progress note

## UPDATE / SUPERSEDE / EXPIRE Proposals

- **Expire candidates:** 1 item
- 62: vague embedding-model switch is superseded by item 57, which states the actual current model and dimensions

## REVIEW Items

- **Review candidates:** 0 items
- No secret / credential / private-key material was found in the 66-memory export.
- The only future-secret reference is item 20, which mentions an upcoming API key but does not store any secret value; it is not promoted.

## Privacy and sensitivity review

- No passwords, API keys, tokens, cookies, private keys, or secret payloads were present in the exported memories.
- Item 20 references a future API key in a task note, which is a reason to keep it out of canonical memory, not a reason to store the secret.
- The rest of the export is mostly operational context, configuration notes, and user preferences.

## Risks

- A large portion of the current set is still operational and should be quarantined, not canonized.
- Several items are duplicates or overlaps and should be normalized before any patching.
- One vague embedding-model transition should be marked expired because it is superseded by the later specific model fact.
- File paths, port mappings, current route layouts, and task-progress notes will age out quickly if they are stored canonically.

## Safe next actions

- Keep canonical memory focused on the 39 KEEP items and the normalized versions of the 7 MERGE items.
- Leave the 15 QUARANTINE items in reports/context, not canonical memory.
- Remove the 4 DROP items from future memory imports.
- Mark item 62 as expired/superseded by item 57 if mutation is later approved.
- If you want, I can turn this audit into an exact-ID patch plan next — but only after you approve mutation.

## Final decision

**MEMORY CLOSED** — audit completed successfully, no mutation required for this run.
