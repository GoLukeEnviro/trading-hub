#!/usr/bin/env python3
"""
primo_api.py — FastAPI server wrapping PrimoAgent signal logic with LLM filter.

Exposes:
  GET  /health                     → container liveness
  GET  /signal?pair=BTC/USDT       → single-pair signal (technical + LLM)
  POST /signal                     → multi-pair signal batch
  GET  /pairs                      → list monitored pairs

Signal flow:
  1. Fetch OHLCV → compute indicators → deterministic signal (v0.4 bot)
  2. Build LLM context from indicators + baseline result
  3. Call LLM via crypto_portfolio_manager prompt → JSON verdict
  4. Combine technical + LLM → final direction/confidence
  5. Return enriched signal with llm_verdict, market_regime, etc.

Safety:
  - If PRIMO_LLM_ENABLED=false → deterministic only, llm_verdict='unavailable'
  - LLM errors → fallback to direction=none, llm_verdict='error'
  - Every decision logged to /logs/history/decisions_YYYYMMDD.jsonl
"""

from __future__ import annotations

import os
import sys
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

# ── path setup ─────────────────────────────────────────────────────
PRIMO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PRIMO_ROOT))

# ── logging ────────────────────────────────────────────────────────
LOG_DIR = Path(os.environ.get("PRIMO_LOG_DIR", "/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primo.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("primo-api")

# ── config ─────────────────────────────────────────────────────────
ALLOWED_PAIRS = os.environ.get(
    "PRIMO_ALLOWED_PAIRS",
    "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"
).split(",")

TIMEFRAME = os.environ.get("PRIMO_TIMEFRAME", "1h")
SIGNAL_FRESHNESS_SECONDS = int(os.environ.get("PRIMO_SIGNAL_FRESHNESS", "90"))
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1")
LLM_ENABLED = os.environ.get("PRIMO_LLM_ENABLED", "true").lower() in ("true", "1", "yes")

app = FastAPI(title="PrimoAgent Signal API", version="2.0.0")

# Optional API key for signal and pair endpoints (health always open)
PRIMO_API_KEY = os.environ.get("PRIMO_API_KEY", "")


def _require_auth(request: Request) -> None:
    """FastAPI dependency: require X-API-Key header when PRIMO_API_KEY is set.

    Health endpoint bypasses this check.
    Never logs the key value.
    """
    if not PRIMO_API_KEY:
        return
    provided = request.headers.get("X-API-Key", "")
    if provided != PRIMO_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


# ── lazy imports ───────────────────────────────────────────────────
_adapter_mod = None
_bot_mod = None
_llm_filter_mod = None


def _get_adapter_mod():
    global _adapter_mod
    if _adapter_mod is None:
        import crypto_data_adapter as m
        _adapter_mod = m
    return _adapter_mod


def _get_bot_mod():
    global _bot_mod
    if _bot_mod is None:
        import primo_trading_bot_v0_4 as m
        _bot_mod = m
    return _bot_mod


def _get_llm_filter():
    global _llm_filter_mod
    if _llm_filter_mod is None:
        import llm_signal_filter as m
        _llm_filter_mod = m
    return _llm_filter_mod


# ── signal generation ──────────────────────────────────────────────

def _freqtrade_to_spot(pair: str) -> str:
    """BTC/USDT:USDT → BTC/USDT"""
    return pair.split(":")[0] if ":" in pair else pair


def generate_signal_for_pair(pair_freqtrade: str) -> Dict[str, Any]:
    """
    Generate signal for one pair using PrimoAgent's pipeline + LLM filter.

    Flow:
      1. Fetch OHLCV + compute indicators
      2. Run deterministic v0.4 bot → baseline signal
      3. If LLM_ENABLED: build context → call LLM → combine
      4. If not: return deterministic only with llm_verdict='unavailable'
    """
    adapter = _get_adapter_mod()
    bot = _get_bot_mod()

    pair_spot = _freqtrade_to_spot(pair_freqtrade)
    normalized = adapter.normalize_pair(pair_spot)

    try:
        # Step 1: Market data + indicators
        exchange = adapter.get_exchange()  # noqa: F841
        df = adapter.fetch_ohlcv(normalized, TIMEFRAME, limit=300)
        if df is None or len(df) < 50:
            logger.warning(f"Insufficient data for {pair_freqtrade}")
            return _build_signal(
                pair_freqtrade, "none", 0.0, "insufficient_data",
                llm_verdict="unavailable", market_regime="unknown"
            )

        indicators = adapter.compute_indicators(df)
        latest_price = float(df["close"].iloc[-1])

        # Step 2: Deterministic baseline
        tech_result = bot.process_trade_signal(indicators, llm_data=None)

        # Step 3: LLM filter
        if LLM_ENABLED and OLLAMA_API_KEY:
            llm_filter = _get_llm_filter()

            # Build context from indicators for LLM prompt
            indicator_context = _extract_indicator_values(indicators)
            llm_context = llm_filter.build_llm_context(
                pair=pair_spot,
                pair_freqtrade=pair_freqtrade,
                timeframe=TIMEFRAME,
                indicators=indicator_context,
                latest_price=latest_price,
                technical_result=tech_result,
            )

            # Call LLM
            llm_verdict = llm_filter.call_llm_signal_filter(llm_context)

            # Combine
            combined = llm_filter.combine_technical_and_llm_signal(
                technical_result=tech_result,
                llm_verdict=llm_verdict,
                pair=pair_freqtrade,
            )

            return _build_signal(
                pair=pair_freqtrade,
                direction=combined["direction"],
                confidence=combined["confidence"],
                reason=combined["reason"],
                llm_verdict=combined.get("llm_verdict", "unknown"),
                llm_model=combined.get("llm_model", ""),
                llm_reason_short=combined.get("llm_reason_short", ""),
                market_regime=combined.get("market_regime", "unknown"),
                veto=combined.get("veto", True),
            )
        else:
            # LLM not available — return deterministic result only
            direction = "long" if tech_result.get("action") == "BUY" else "none"
            confidence = float(tech_result.get("confidence", 0.0))
            reason = ", ".join(tech_result.get("reasons", [])) if tech_result.get("reasons") else tech_result.get("signal_quality", "")

            return _build_signal(
                pair_freqtrade, direction, confidence, reason,
                llm_verdict="unavailable",
                market_regime=tech_result.get("regime", "unknown"),
            )

    except Exception as exc:
        logger.error(f"Signal generation failed for {pair_freqtrade}: {exc}")
        traceback.print_exc()
        return _build_signal(
            pair_freqtrade, "none", 0.0, f"error: {str(exc)[:100]}",
            llm_verdict="error", market_regime="unknown"
        )


def _extract_indicator_values(indicators: Any) -> Dict[str, Any]:
    """
    Extract indicator values from the compute_indicators result.
    Handles both dict and DataFrame return types.
    """
    result = {}
    try:
        if hasattr(indicators, "iloc"):
            # It's a DataFrame — extract last row
            last = indicators.iloc[-1]
            col_map = {
                "rsi_14": ["rsi_14", "RSI", "rsi"],
                "ema_50": ["ema_50", "EMA_50", "ema50"],
                "ema_200": ["ema_200", "EMA_200", "ema200"],
                "adx_14": ["adx_14", "ADX", "adx"],
                "atr_percent": ["atr_percent", "ATR_pct", "atr"],
                "bb_width": ["bb_width", "BB_width"],
                "bb_position_pct": ["bb_position_pct", "BB_pos_pct"],
                "volume_ratio": ["volume_ratio", "vol_ratio"],
            }
            for key, possible_cols in col_map.items():
                for col in possible_cols:
                    if col in last.index:
                        result[key] = float(last[col])
                        break
        elif isinstance(indicators, dict):
            result = indicators
    except Exception:
        pass
    return result


def _build_signal(
    pair: str,
    direction: str,
    confidence: float,
    reason: str,
    llm_verdict: str = "unavailable",
    llm_model: str = "",
    llm_reason_short: str = "",
    market_regime: str = "unknown",
    veto: bool = True,
) -> Dict[str, Any]:
    """Build the v1.0+ signal schema with optional LLM enrichment."""
    return {
        "schema_version": "1.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "primo-agent",
        "approved_by": "pending",  # Hermes sets this
        "pair": pair,
        "direction": direction,
        "confidence": round(float(confidence), 4),
        "kelly_fraction_advisory": 0.0,
        "risk_cap_percent": 1.0,
        "reason": reason,
        "veto": veto,
        "market_regime": market_regime,
        "llm_verdict": llm_verdict,
        "llm_model": llm_model,
        "llm_reason_short": llm_reason_short,
    }


# ── endpoints ──────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Container liveness check."""
    return {
        "status": "healthy",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pairs_monitored": len(ALLOWED_PAIRS),
        "llm_enabled": LLM_ENABLED and bool(OLLAMA_API_KEY),
        "log_file": str(LOG_FILE),
    }


@app.get("/pairs")
def list_pairs(auth: None = Depends(_require_auth)):
    """List all monitored pairs."""
    return {"pairs": ALLOWED_PAIRS, "timeframe": TIMEFRAME, "llm_enabled": LLM_ENABLED}


@app.get("/signal")
def get_signal(
    auth: None = Depends(_require_auth),
    pair: str = Query(..., description="Pair in Freqtrade format, e.g. BTC/USDT:USDT"),
):
    """Generate signal for a single pair."""
    if pair not in ALLOWED_PAIRS:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not in allowed list")
    signal = generate_signal_for_pair(pair)
    logger.info(
        f"GET /signal {pair} → dir={signal['direction']} conf={signal['confidence']:.4f} "
        f"llm={signal.get('llm_verdict', 'N/A')} regime={signal.get('market_regime', 'N/A')}"
    )
    return signal


class MultiSignalRequest(BaseModel):
    pairs: list[str] = Field(default_factory=lambda: ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])


@app.post("/signal")
def post_signal(req: MultiSignalRequest, auth: None = Depends(_require_auth)):
    """Generate signals for multiple pairs."""
    signals = []
    for pair in req.pairs:
        if pair not in ALLOWED_PAIRS:
            signals.append(_build_signal(pair, "none", 0.0, "pair_not_allowed", llm_verdict="unavailable"))
        else:
            signals.append(generate_signal_for_pair(pair))

    logger.info(f"POST /signal {len(signals)} pairs processed")
    return {"signals": signals, "count": len(signals), "timestamp_utc": datetime.now(timezone.utc).isoformat()}


# ── startup ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("PrimoAgent API v2.0 starting up")
    logger.info(f"Allowed pairs: {ALLOWED_PAIRS}")
    logger.info(f"Timeframe: {TIMEFRAME}")
    logger.info(f"LLM enabled: {LLM_ENABLED}")
    logger.info(f"Log: {LOG_FILE}")

    # Pre-warm exchange connection
    try:
        adapter = _get_adapter_mod()
        adapter.get_exchange()
        logger.info("Exchange connection pre-warmed")
    except Exception as exc:
        logger.warning(f"Exchange pre-warm failed (non-fatal): {exc}")

    # Test LLM connectivity
    if LLM_ENABLED and OLLAMA_API_KEY:
        try:
            llm_filter = _get_llm_filter()
            logger.info(f"LLM filter loaded, model={'override' if llm_filter.LLM_MODEL_OVERRIDE else 'config:portfolio_manager'}")
        except Exception as exc:
            logger.warning(f"LLM filter init warning: {exc}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PRIMO_PORT", "8420"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
