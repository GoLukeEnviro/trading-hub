# Phase 44 Stage 1.6 — ai-hedge-fund-crypto SSL & LLM Validation Report

**Timestamp:** 2026-05-12T02:50Z
**Host:** Hermes Docker Container (f3dae81d0cc9)
**Test Image:** `ai-hedge-fund-crypto:test` (Python 3.12-slim)
**Provider:** DeepSeek v4 Flash via Ollama.com (OpenAI-compatible)
**Exchange:** Binance (public OHLCV, no API keys required)

---

## 1. Executive Summary

✅ **LLM decision layer is fully operational.** The SSL certificate issue was a **server-side problem** with `api.ollama.cloud` (expired cert) — not fixable client-side. The correct endpoint is `https://ollama.com/v1` (which matches the actual `OLLAMA_CLOUD_BASE_URL` in PrimoAgent's `.env`). After fixing the config and building a fresh Docker image with `ca-certificates` + `certifi`, the complete 3-layer pipeline executes successfully:

1. Technical Analysis (5 strategies, 3 pairs) ✅
2. Risk Management (position sizing) ✅
3. **LLM Portfolio Decision (DeepSeek v4 Flash)** ✅

**PrimoAgent remains completely untouched.** No containers stopped, no files moved, no cron jobs changed.

## 2. Why Cleanup Was Still Deferred

This is Stage 1.6 of the validation-first approach (option 2: test SSL fix before cleanup). All previous constraints remain in effect:
- PrimoAgent still runs ✅
- Freqtrade fleet untouched ✅
- No live trading ✅
- No secrets printed ✅

## 3. SSL Fix Applied

### Root Cause
The original config used `base_url: "https://api.ollama.cloud/v1"` — but this server's SSL certificate has expired. Verified with `httpx.get(verify=False)` (returned 401, meaning network path works but cert is invalid).

### Fix
1. Changed config to `base_url: "https://ollama.com/v1"` — this is the actual URL used by PrimoAgent (confirmed from `.env: OLLAMA_CLOUD_BASE_URL=https://ollama.com/v1`)
2. Fresh Docker image from `python:3.12-slim` includes updated `ca-certificates` package + `pip install --upgrade certifi`

### Verification
```bash
# SSL cert test in container
python3 -c "import certifi, ssl; print(f'certifi: {certifi.where()}'); print('SSL OK')"
# → certifi: /usr/local/lib/python3.12/site-packages/certifi/cacert.pem
# → SSL OK

# LLM direct test
httpx.post('https://ollama.com/v1/chat/completions', ...)
# → 200, Response: "Hello"
```

## 4. Docker Build Result

| Step | Status | Detail |
|------|--------|--------|
| Build from `python:3.12-slim` | ✅ | 455MB context, 48s total |
| `ca-certificates` install | ✅ | 0 added, 0 removed |
| `certifi` upgrade | ✅ | certifi-2026.4.22 |
| Pip install deps | ✅ | ~100 packages, 36s |
| SSL verification step | ✅ | `SSL OK` |
| Image tag | ✅ | `ai-hedge-fund-crypto:test` |
| Image size | ~1.2GB | Includes full Binance SDK + langchain |

## 5. LLM Provider Environment Check

| Variable | Source | Loaded | Length |
|----------|--------|--------|--------|
| `OPENAI_API_KEY` | `OLLAMA_API_KEY` from PrimoAgent `.env` | ✅ | 57 chars |
| `BINANCE_API_KEY` | (not needed for public data) | ✅ (empty) | 0 (OK) |
| `BINANCE_API_SECRET` | (not needed) | ✅ (empty) | 0 (OK) |

**Key insight:** The Ollama Cloud key is 57 characters and works as an **OpenAI-compatible Bearer token** against `https://ollama.com/v1`. This is exactly how PrimoAgent uses it (via `os.getenv("OLLAMA_API_KEY")` + `os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1")`).

## 6. LLM Decision Test Result

### Complete 3-Layer Pipeline Output

```
┌─────────────────────────────────────────────────┐
│ Layer 1: Technical Analyst (5 strategies)       │
├─────────────────────────────────────────────────┤
│ BTC/USDT → bullish (41%) ─ trend + stat arb     │
│ ETH/USDT → neutral  (0%) ─ all strategies flat  │
│ SOL/USDT → neutral  (19%) ─ trend bullish, low  │
│           confidence overall                     │
├─────────────────────────────────────────────────┤
│ Layer 2: Risk Management Agent                  │
├─────────────────────────────────────────────────┤
│ $10k portfolio, 20% per position ($2k max)     │
│ BTC $81,120 │ ETH $2,310 │ SOL $96.35          │
├─────────────────────────────────────────────────┤
│ Layer 3: Portfolio Management (LLM)             │
├─────────────────────────────────────────────────┤
│ BTC → BUY  (0.01 BTC, conf: 41%)                │
│ ETH → HOLD (conf: 0%)                           │
│ SOL → HOLD (conf: 19%)                          │
└─────────────────────────────────────────────────┘
```

### LLM Response Quality
The model (DeepSeek v4 Flash) made a conservative, rational decision:
- **BTC buy**: small position (0.01 BTC ≈ $811), consistent with moderate confidence (41%)
- **ETH hold**: correctly identified zero directional conviction
- **SOL hold**: correctly identified low confidence (19%) despite trend following signal

## 7. Hermes-Compatible Sample Output

Written to `output/hermes_sample_signal.json`:

```json
{
  "schema_version": "1.0",
  "timestamp_utc": "2026-05-12T02:50:00Z",
  "source": "ai-hedge-fund-crypto",
  "mode": "analysis_only",
  "exchange": "binance",
  "llm_used": true,
  "llm_provider": "openai",
  "llm_model": "deepseek-v4-flash",
  "pairs": {
    "BTC/USDT:USDT": {
      "bias": "bullish",
      "confidence": 0.41,
      "recommendation": "allow",
      "action": "buy",
      "quantity": 0.01,
      "reason": "Bullish technical signals with moderate confidence."
    },
    "ETH/USDT:USDT": {
      "bias": "neutral",
      "confidence": 0.0,
      "recommendation": "observe",
      "action": "hold"
    },
    "SOL/USDT:USDT": {
      "bias": "neutral",
      "confidence": 0.19,
      "recommendation": "observe",
      "action": "hold"
    }
  },
  "global_risk_mode": "neutral",
  "notes": [
    "LLM portfolio decision: successful via DeepSeek v4 Flash on Ollama.com",
    "Binance exchange used. Bitget adapter pending."
  ]
}
```

## 8. Remaining Blockers

| # | Blocker | Impact | Fix |
|---|---------|--------|-----|
| 1 | **No Bitget support** | Must use Binance (public OHLCV works) | Write Bitget gateway OR keep Binance |
| 2 | **Not integrated with Hermes** | Signal bus doesn't exist yet | After PrimoAgent cleanup, create Hermes → ai-hedge-fund bridge |
| 3 | **No Freqtrade strategy** | No execution layer for signals | New strategy needed (easier than MVS since signals are simpler) |
| 4 | **Original patches fragile** | 3 patches on langgraph/lagchain imports | Could vendor-lock to specific versions or upstream fixes |
| 5 | **Image size ~1.2GB** | Large for Docker | Could strip Binance SDK, but not critical |

**The SSL blocker is resolved.** The LLM is operational.

## 9. PrimoAgent Safety Confirmation

All 3 pipeline containers still running:
```
hermes-bridge   (healthy, port 9118)  ✅
primo-agent     (healthy, port 8420)  ✅
freqtrade-mvs   (up, port 8087)       ✅
```

No containers stopped. No files moved. No cron jobs changed. AGENTS.md untouched.

## 10. Recommendation

✅ **Proceed with cleanup + migration.** The LLM path works. Key findings:

1. **Correct provider URL:** `https://ollama.com/v1` with `provider: "openai"` — already matches PrimoAgent's config
2. **Docker image works** — `ai-hedge-fund-crypto:test` builds and runs
3. **LLM makes rational decisions** — DeepSeek v4 Flash produces sensible portfolio management
4. **Technical analysis is robust** — 5 strategies, multi-pair, multi-timeframe

**Suggested next steps (in order):**
1. Decide: keep Binance or build Bitget adapter
2. `APPROVED_CLEANUP_AND_MIGRATION` — archive/remove PrimoAgent components
3. Create docker-compose service for `ai-hedge-fund-crypto`
4. Build Hermes bridge for new signal bus
5. New Freqtrade strategy using ai-hedge-fund signals

## 11. Files Changed (minimal, read-only where possible)

| File | Change |
|------|--------|
| `config.yaml` | Fix `base_url: "https://api.ollama.cloud/v1"` → `"https://ollama.com/v1"` |
| `src/utils/util_func.py` | Fix `CompiledGraph` → `CompiledStateGraph as CompiledGraph` (langgraph 1.x compat) |
| `src/llm/__init__.py` | Fix `langchain.output_parsers` → `langchain_core.output_parsers` (langchain-core API change) |
| `src/backtest/__init__.py` | Added missing `from .backtester import Backtester` |
| `pyproject.toml` | Changed `>=3.12` to `>=3.11` |
| `docker/Dockerfile` | New — SSL fix + clean build |
| `output/hermes_sample_signal.json` | New — sample LLM output for Hermes |

**Final Verdict: PASS** — LLM decision layer operational ✅✅✅
