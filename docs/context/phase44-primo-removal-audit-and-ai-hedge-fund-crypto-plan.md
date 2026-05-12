# Phase 44 — PrimoAgent Removal Audit & ai-hedge-fund-crypto Migration Plan

## Stage 1: Read-Only Audit Report

**Timestamp:** 2026-05-12T01:44Z
**Host:** f3dae81d0cc9 (Docker container)
**User:** hermes
**Working Directory:** /home/hermes/projects/trading

---

## 1. Executive Summary

This audit identifies the complete footprint of the PrimoAgent experiment across the trading system. The experiment spans 3 Docker containers, 2.15GB of images, 2 Docker volumes, 2 Hermes cron jobs, 1 Hermes skill, 1 AGENTS.md section, 26 docs/context reports, and ~624MB of source code. The original PrimoAgent source at `/home/hermes/primoagent/` is preserved intact and will be archived, not deleted.

---

## 2. Current Architecture (with PrimoAgent)

```
Hermes (orchestrator)
  │
  ├── Cron: primo-meta-filter-pipeline  (every 60m)
  │     └── run_primo_meta_filter_bridge.py  →  PrimoAgent source
  │
  ├── Cron: primoagent-signal-generation  (every 60m, last_run=ERROR)
  │     └── run_primo_crypto_pipeline.sh  →  Original pipeline
  │
  └── Hermes Bridge (container, port 9118)
        │
        ├── Polls → primo-agent:8420/signal  (every 60s)
        │
        └── Writes → /shared/signals/  (signal bus)
              │
              └── Freqtrade MVS (container, port 8087)
                    └── MinimalViableStrategy_v1.py
                          └── Reads signal file per-pair
```

---

## 3. Running Runtime Components

### 3.1 Docker Containers

| Container | Image | Status | Port | Purpose |
|-----------|-------|--------|------|---------|
| `primo-agent` | `primo-agent:latest` | ✅ Healthy | 8420 | Phase 43 LLM wrapper (NOT original full system) |
| `hermes-bridge` | `hermes-bridge:latest` | ✅ Healthy | 9118 | Polls Primo, writes signal files |
| `freqtrade-mvs` | `freqtradeorg/freqtrade:stable` | ✅ Up | 8087 | Consumes signals via MinimalViableStrategy_v1 |

**None of these are part of the production fleet.** The production fleet (freqforge, regime-hybrid, rsi, momentum, webserver) runs independently on `ki-fabrik` with zero dependency on PrimoAgent.

### 3.2 Docker Images

| Image | Size | Origin |
|-------|------|--------|
| `primo-agent:latest` | 2.01 GB | Phase 42/43 build |
| `hermes-bridge:latest` | 138 MB | Phase 42 build |

### 3.3 Docker Volumes

| Volume | Name | Usage |
|--------|------|-------|
| `primo-logs` | primo-logs | Primo container logs |
| `shared-signals` | shared-signals | Signal bus (bridge writes, Freqtrade reads) |

---

## 4. Files Proposed for Archive (Preserved, Not Deleted)

### 4.1 Active Pipeline Files — to archive

| Path | Size | Purpose |
|------|------|---------|
| `/home/hermes/projects/trading/primo/Dockerfile` | 1KB | Builds primo-agent container |
| `/home/hermes/projects/trading/primo/primo_api.py` | 12KB | Phase 43 LLM wrapper API |
| `/home/hermes/projects/trading/primo/llm_signal_filter.py` | 12KB | Phase 43 LLM filter module |
| `/home/hermes/projects/trading/bridge/Dockerfile` | 1KB | Builds hermes-bridge container |
| `/home/hermes/projects/trading/bridge/hermes_primo_bridge.py` | 13KB | Per-pair signal poller |
| `/home/hermes/projects/trading/freqtrade/bots/mvs/config/config.json` | 2KB | MVS dry-run config |
| `/home/hermes/projects/trading/freqtrade/bots/mvs/config/pairs.json` | 182B | Pair whitelist |
| `/home/hermes/projects/trading/freqtrade/shared/strategies/MinimalViableStrategy_v1.py` | 17KB | Strategy with EMA9/21 + Hermes gate |
| `/home/hermes/projects/trading/freqtrade/shared/signals/` | ~230B | Signal bus files (will be stale) |
| `/home/hermes/projects/trading/docker-compose.pipeline.yml` | 7KB | 3-service compose |

### 4.2 Original PrimoAgent Source — to archive (NOT deleted)

| Path | Size | Purpose |
|------|------|---------|
| `/home/hermes/primoagent/` | 623MB | Complete original source + .venv |
| `/home/hermes/primoagent/run_primo_crypto_pipeline.py` | — | Original crypto pipeline entry point |
| `/home/hermes/primoagent/src/` | — | Full LangChain/LangGraph agent code |
| `/home/hermes/primoagent/.env` | — | 7 API keys (preserved) |

### 4.3 Hermes Scripts — to disable symlinks

| Path | Type | Status |
|------|------|--------|
| `/home/hermes/.hermes/scripts/primo_meta_filter_bridge.py` | Symlink → `/home/hermes/primoagent/` | Disable |
| `/home/hermes/.hermes/scripts/run_primo_crypto_pipeline.sh` | Shell wrapper | Disable |

---

## 5. Hermes Cron Jobs — to pause/disable

| Job ID | Name | Schedule | Status | Action |
|--------|------|----------|--------|--------|
| `3fe8adc7d579` | primo-meta-filter-pipeline | every 60m | ✅ Running | PAUSE |
| `523afae330bf` | primoagent-signal-generation | every 60m | ❌ Last ERROR | PAUSE |

---

## 6. Hermes Skill — to deprecate

| Skill | Path | Action |
|-------|------|--------|
| `primo-meta-filter-pipeline` | `~/.hermes/profiles/orchestrator/skills/trading/primo-meta-filter-pipeline/` | Deprecate archive |

---

## 7. AGENTS.md References — to remove

Section `### PrimoAgent — Trading Core` (lines 9-30) — describes PrimoAgent as central signal brain. Must be removed or rewritten.

---

## 8. docs/context Reports — to archive

26 reports referencing Phase 41/42/43/43c in `/home/hermes/projects/trading/docs/context/` and `/home/hermes/projects/trading/Agenten_Auto_Trade/docs/context/`. These are historical records and can remain or be moved to an archive subdirectory.

---

## 9. Files That Must Be PRESERVED (NOT touched)

- `/home/hermes/primoagent/.env` — 7 API keys (OLLAMA, FINNHUB, FIRECRAWL, PERPLEXITY, OPENAI, OLLAMA_CLOUD)
- All production Freqtrade fleet files under `/home/hermes/projects/trading/freqtrade/bots/{freqforge,regime-hybrid,rsi,momentum,webserver}/`
- `/home/hermes/projects/trading/freqtrade/docker-compose.fleet.yml` — no PrimoAgent references
- `/home/hermes/projects/trading/Agenten_Auto_Trade/docker-compose.yml` — no PrimoAgent references
- All Hermes profile configs, SOUL.md, skills NOT specific to PrimoAgent
- All Honcho containers and data

---

## 10. Target: ai-hedge-fund-crypto

**Repository:** https://github.com/51bitquant/ai-hedge-fund-crypto
**License:** MIT | **Stars:** 583 | **Language:** Python 100%

**Key Facts:**
- LangGraph DAG-based workflow architecture (already familiar)
- Supports Ollama as LLM provider via base_url config
- Multi-timeframe analysis (30m, 1h, 4h)
- 5 strategy types: trend, mean reversion, momentum, volatility, statistical arbitrage
- Risk management + LLM portfolio manager nodes
- Uses Binance for market data (ccxt — can adapt to Bitget)
- Mode: backtest OR live (signal-only OR real execution)
- config.yaml for all settings, .env for API keys

**Requirements:**
- Binance API keys for market data (can adapt to Bitget via ccxt)
- OpenAI/Groq/OpenRouter/Gemini/Anthropic/Ollama key for LLM
- Python 3.12 recommended
- uv package manager

**Compatibility with existing setup:**
- ✅ Supports Ollama as provider (can use Ollama Cloud)
- ✅ Supports Gemini via google provider
- ✅ LangGraph DAG (already familiar architecture)
- ✅ Dry-run / backtest mode available
- ⚠️ Uses Binance by default, needs adaptation to Bitget
- ⚠️ Requires uv (not yet installed)

---

## 11. Cleanup Proposal: APPROVAL REQUIRED

### Proposed Archive Commands (after approval):

```bash
# 1. Stop PrimoAgent-related containers
docker stop primo-agent hermes-bridge freqtrade-mvs
docker rm primo-agent hermes-bridge freqtrade-mvs

# 2. Pause Hermes cron jobs
#   - primo-meta-filter-pipeline (3fe8adc7d579)
#   - primoagent-signal-generation (523afae330bf)

# 3. Remove Docker images (source preserved)
docker rmi primo-agent:latest hermes-bridge:latest

# 4. Remove Docker volumes
docker volume rm primo-logs shared-signals

# 5. Create archival backup
mkdir -p /home/hermes/projects/trading/backups/phase44-archive-$(date +%Y%m%d_%H%M%S)

# 6. Move active pipeline files to archive
mv /home/hermes/projects/trading/primo /home/hermes/projects/trading/backups/phase44-archive-*/primo
mv /home/hermes/projects/trading/bridge /home/hermes/projects/trading/backups/phase44-archive-*/bridge
mv /home/hermes/projects/trading/freqtrade/bots/mvs /home/hermes/projects/trading/backups/phase44-archive-*/mvs
mv /home/hermes/projects/trading/freqtrade/shared/signals /home/hermes/projects/trading/backups/phase44-archive-*/signals
mv /home/hermes/projects/trading/freqtrade/shared/strategies/MinimalViableStrategy_v1.py /home/hermes/projects/trading/backups/phase44-archive-*/MinimalViableStrategy_v1.py
mv /home/hermes/projects/trading/docker-compose.pipeline.yml /home/hermes/projects/trading/backups/phase44-archive-*/docker-compose.pipeline.yml

# 7. Disable Hermes script symlinks
rm /home/hermes/.hermes/scripts/primo_meta_filter_bridge.py
rm /home/hermes/.hermes/scripts/run_primo_crypto_pipeline.sh

# 8. Deprecate PrimoAgent skill
#   - Rename skill or mark as deprecated in SKILL.md

# 9. Archive docs/context PrimoAgent reports
#   - Move to docs/context/archive/ subdirectory
```

### Proposed ai-hedge-fund-crypto Setup (after approval):

```bash
# 1. Clone repository
cd /home/hermes/projects/trading
git clone https://github.com/51bitquant/ai-hedge-fund-crypto.git

# 2. Install uv
curl -fsSL https://install.lunarvim.org/uv.sh | sh

# 3. Create venv + install deps
cd ai-hedge-fund-crypto
uv venv --python 3.12
source .venv/bin/activate
uv pip sync

# 4. Configure LLM provider (Ollama Cloud)
cp config.example.yaml config.yaml
# Edit: provider: ollama, base_url: <OLLAMA_CLOUD_BASE_URL>

# 5. Configure pairs (BTCUSDT, ETHUSDT, SOLUSDT)
# 6. Dry-run smoke test
uv run backtest.py
```

---

## 12. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Binance API keys required for market data | HIGH (new keys) | Adapt ccxt to use Bitget public data |
| New codebase never tested in this environment | MEDIUM | Run in backtest mode first, then dry-run |
| PrimoAgent .env keys may not map to ai-hedge-fund .env | MEDIUM | OLLAMA_API_KEY ≈ Ollama, needs mapping |
| AGENTS.md describes PrimoAgent as central | LOW | Update after migration approved |
| 2 active cron jobs running stale PrimoAgent code | LOW | Pause immediately on approval |
| freqtrade-mvs still running on port 8087 | LOW | Port conflict if new service uses same port |

---

## 13. Verification Checklist (for Stage 2)

- [ ] docker ps — no primo-agent, hermes-bridge, or freqtrade-mvs running
- [ ] docker images — no primo-agent:latest or hermes-bridge:latest
- [ ] docker volume ls — no primo-logs or shared-signals
- [ ] docker compose config — no PrimoAgent references
- [ ] Cron jobs paused — primo-meta-filter-pipeline, primoagent-signal-generation
- [ ] Archive backup exists with all files
- [ ] docs/context archived
- [ ] Production fleet unaffected (freqforge, regime-hybrid, rsi, momentum, webserver)
- [ ] Freqtrade dry_run still true for all bots
- [ ] All .env keys preserved

---

## 14. STOP POINT

**This concludes Stage 1 (Read-Only Audit).**

No files have been modified, moved, or deleted.

The following still need your explicit approval before Stage 2 begins:

**APPROVED_CLEANUP_AND_MIGRATION**

Awaiting your decision.
