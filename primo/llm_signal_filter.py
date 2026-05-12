#!/usr/bin/env python3
"""
llm_signal_filter.py — LLM-assisted signal filter for PrimoAgent.

Uses the existing PrimoAgent infrastructure:
  - model_factory.py → ChatOpenAI via Ollama Cloud
  - crypto_portfolio_manager.py → JSON-strict prompt template
  - config.json → model configuration

Decision rules:
  - direction=long ONLY when technical signal is acceptable AND llm_verdict=approve
  - direction=none when llm_verdict is veto, neutral, or unavailable
  - Default minimum confidence for long: 0.60
  - risk_cap_percent stays exactly 1.0
  - Kelly fraction is advisory only

Safety:
  - LLM timeout configured (30s)
  - LLM errors never crash Primo — fallback to veto/none
  - Malformed LLM responses → veto/none
  - No secrets in logs
  - Every LLM decision logged to JSONL history
"""

from __future__ import annotations

import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("primo-llm-filter")

# ── Configuration ──────────────────────────────────────────────────

LLM_ENABLED = os.environ.get("PRIMO_LLM_ENABLED", "true").lower() in ("true", "1", "yes")
MIN_CONFIDENCE_FOR_LONG = float(os.environ.get("PRIMO_MIN_CONFIDENCE", "0.60"))
LLM_TIMEOUT = int(os.environ.get("PRIMO_LLM_TIMEOUT", "30"))
LLM_MODEL_OVERRIDE = os.environ.get("PRIMO_LLM_MODEL", "")  # empty = use config.json default
HISTORY_DIR = Path(os.environ.get("PRIMO_HISTORY_DIR", "/logs/history"))

ALLOWED_VERDICTS = {"approve", "veto", "neutral"}
ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", "WATCH"}

# ── JSONL History ──────────────────────────────────────────────────


def _log_decision_jsonl(record: Dict[str, Any]) -> None:
    """Append one decision record to JSONL history file."""
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        history_file = HISTORY_DIR / f"decisions_{date_str}.jsonl"
        line = json.dumps(record, default=str, ensure_ascii=False)
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        logger.warning(f"Failed to write JSONL history: {exc}")


# ── Context Builder ────────────────────────────────────────────────


def build_llm_context(
    pair: str,
    pair_freqtrade: str,
    timeframe: str,
    indicators: Dict[str, Any],
    latest_price: float,
    technical_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the prompt context dict for the LLM from technical indicators
    and deterministic baseline result.

    Returns a flat dict matching the crypto_portfolio_manager template variables.
    """
    # Extract indicators safely
    rsi_14 = indicators.get("rsi_14", indicators.get("RSI", "N/A"))
    ema_50 = indicators.get("ema_50", indicators.get("EMA_50", "N/A"))
    ema_200 = indicators.get("ema_200", indicators.get("EMA_200", "N/A"))
    adx_14 = indicators.get("adx_14", indicators.get("ADX", "N/A"))
    atr_pct = indicators.get("atr_percent", indicators.get("ATR_pct", "N/A"))
    bb_width = indicators.get("bb_width", indicators.get("BB_width", "N/A"))
    bb_pos = indicators.get("bb_position_pct", indicators.get("BB_pos_pct", "N/A"))
    vol_ratio = indicators.get("volume_ratio", indicators.get("vol_ratio", "N/A"))

    # Determine EMA trend
    try:
        e50 = float(ema_50) if ema_50 not in ("N/A", None) else None
        e200 = float(ema_200) if ema_200 not in ("N/A", None) else None
        if e50 and e200:
            ema_trend = "bullish" if e50 > e200 else "bearish"
        else:
            ema_trend = "unknown"
    except (ValueError, TypeError):
        ema_trend = "unknown"

    # Baseline result
    baseline_action = technical_result.get("action", "WATCH")
    baseline_confidence = technical_result.get("confidence", 0.0)
    baseline_quality = technical_result.get("signal_quality", "unknown")
    baseline_strategy_fit = technical_result.get("strategy_fit", "unknown")
    baseline_reasons = ", ".join(technical_result.get("reasons", []))

    return {
        "pair": pair,
        "pair_freqtrade": pair_freqtrade,
        "timeframe": timeframe,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "latest_price": f"{latest_price:.2f}",
        "rsi_14": _fmt(rsi_14),
        "ema_50": _fmt(ema_50),
        "ema_200": _fmt(ema_200),
        "ema_trend": ema_trend,
        "adx_14": _fmt(adx_14),
        "atr_percent": _fmt(atr_pct),
        "bb_width": _fmt(bb_width),
        "bb_position_pct": _fmt(bb_pos),
        "volume_ratio": _fmt(vol_ratio),
        "news_available": "false",
        "sentiment_label": "UNKNOWN",
        "news_score": "N/A",
        "source_note": "No news feed in MVS v1",
        "baseline_action": baseline_action,
        "baseline_confidence": f"{baseline_confidence:.2f}",
        "baseline_quality": baseline_quality,
        "baseline_strategy_fit": baseline_strategy_fit,
        "baseline_reasons": baseline_reasons[:300] if baseline_reasons else "N/A",
    }


def _fmt(val: Any) -> str:
    """Format a value for the prompt table."""
    if val is None or val == "N/A":
        return "N/A"
    try:
        return f"{float(val):.4f}"
    except (ValueError, TypeError):
        return str(val)


# ── LLM Call ───────────────────────────────────────────────────────


def call_llm_signal_filter(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call the LLM with the crypto portfolio manager prompt.

    Returns parsed verdict dict:
      {"action": "BUY|SELL|HOLD|WATCH", "confidence": 0.0-0.90, "reasoning_summary": "..."}

    On any failure, returns fallback veto.
    """
    if not LLM_ENABLED:
        return {
            "action": "WATCH",
            "confidence": 0.0,
            "reasoning_summary": "LLM disabled by config",
        }

    try:
        # Import here to avoid crash if langchain not installed
        from src.config.model_factory import ModelFactory
        from src.config import config
        from src.prompts.crypto_portfolio_manager import (
            get_crypto_portfolio_manager_template,
            get_crypto_signal_output_parser,
        )

        # Create LLM instance
        if LLM_MODEL_OVERRIDE:
            # Use override model directly
            from langchain_openai import ChatOpenAI
            base_url = os.environ.get("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1")
            api_key = os.environ.get("OLLAMA_API_KEY", "")
            llm = ChatOpenAI(
                model=LLM_MODEL_OVERRIDE,
                temperature=0.2,
                base_url=base_url,
                api_key=api_key,
                request_timeout=LLM_TIMEOUT,
            )
        else:
            # Use config.json portfolio_manager model
            model_config = config.model_portfolio_manager
            model_config_with_timeout = {**model_config}
            llm = ModelFactory.create_model(model_config_with_timeout)
            # Try to set timeout on the underlying client
            try:
                llm.request_timeout = LLM_TIMEOUT
            except Exception:
                pass

        # Build prompt chain
        prompt_template = get_crypto_portfolio_manager_template()
        output_parser = get_crypto_signal_output_parser()

        context_with_format = {
            **context,
            "format_instructions": output_parser.get_format_instructions(),
        }

        chain = prompt_template | llm | output_parser

        # Synchronous invoke (FastAPI endpoint is sync in primo_api.py)
        result = chain.invoke(context_with_format)

        logger.info(
            f"LLM verdict: action={result.get('action')} "
            f"confidence={result.get('confidence')} "
            f"summary={result.get('reasoning_summary', '')[:80]}"
        )

        return result

    except Exception as exc:
        logger.error(f"LLM call failed: {exc}")
        traceback.print_exc()
        return {
            "action": "WATCH",
            "confidence": 0.0,
            "reasoning_summary": f"LLM error: {str(exc)[:100]}",
        }


# ── Combine Technical + LLM ────────────────────────────────────────


def combine_technical_and_llm_signal(
    technical_result: Dict[str, Any],
    llm_verdict: Dict[str, Any],
    pair: str,
) -> Dict[str, Any]:
    """
    Combine deterministic technical result with LLM verdict into final signal.

    Decision rules:
      - BUY from both → direction=long (if confidence >= threshold)
      - BUY from technical but not from LLM → direction=none
      - WATCH/HOLD from technical → direction=none regardless of LLM
      - Any error → direction=none
    """
    tech_action = str(technical_result.get("action", "WATCH")).upper()
    tech_confidence = float(technical_result.get("confidence", 0.0))

    llm_action = str(llm_verdict.get("action", "WATCH")).upper()
    llm_confidence = float(llm_verdict.get("confidence", 0.0))
    llm_reasoning = str(llm_verdict.get("reasoning_summary", ""))

    # Determine LLM verdict category
    if llm_action == "BUY":
        llm_verdict_category = "approve"
    elif llm_action == "SELL":
        # SELL is also a directional signal, but v1 only allows long
        llm_verdict_category = "veto"
    elif llm_action == "WATCH":
        llm_verdict_category = "veto"
    else:
        llm_verdict_category = "neutral"

    # Final direction logic
    direction = "none"
    final_confidence = 0.0
    reason = ""

    if tech_action == "BUY" and llm_verdict_category == "approve":
        # Both agree on bullish
        combined_conf = min(tech_confidence, llm_confidence)
        if combined_conf >= MIN_CONFIDENCE_FOR_LONG:
            direction = "long"
            final_confidence = round(combined_conf, 4)
            reason = f"Tech+LLM agree BUY (tech={tech_confidence:.2f}, llm={llm_confidence:.2f}). {llm_reasoning[:200]}"
        else:
            direction = "none"
            final_confidence = round(combined_conf, 4)
            reason = f"Both BUY but confidence {combined_conf:.2f} < threshold {MIN_CONFIDENCE_FOR_LONG}"
    elif tech_action == "BUY" and llm_verdict_category != "approve":
        direction = "none"
        final_confidence = round(min(tech_confidence, llm_confidence), 4)
        reason = f"Tech BUY but LLM={llm_action} ({llm_verdict_category}). {llm_reasoning[:200]}"
    else:
        direction = "none"
        final_confidence = 0.0
        reason = f"Tech={tech_action}, LLM={llm_action}. No edge."

    # Determine market regime from technical result
    regime = technical_result.get("regime", "unknown")
    regime_map = {
        "trending": "trend",
        "trend": "trend",
        "ranging": "range",
        "range": "range",
        "volatile": "high_volatility",
        "high_volatility": "high_volatility",
        "low_liquidity": "low_liquidity",
    }
    market_regime = regime_map.get(regime, "unknown")

    result = {
        "direction": direction,
        "confidence": final_confidence,
        "reason": reason,
        "market_regime": market_regime,
        "llm_verdict": llm_verdict_category,
        "llm_model": LLM_MODEL_OVERRIDE or "config:portfolio_manager",
        "llm_reason_short": llm_reasoning[:200] if llm_reasoning else "",
        "veto": direction != "long",  # veto=True when no trade
    }

    # Log to JSONL
    _log_decision_jsonl({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pair": pair,
        "technical_action": tech_action,
        "technical_confidence": tech_confidence,
        "technical_regime": regime,
        "technical_reasons": technical_result.get("reasons", []),
        "llm_action": llm_action,
        "llm_confidence": llm_confidence,
        "llm_verdict": llm_verdict_category,
        "llm_reasoning": llm_reasoning[:500],
        "llm_model": result["llm_model"],
        "final_direction": direction,
        "final_confidence": final_confidence,
        "min_confidence_threshold": MIN_CONFIDENCE_FOR_LONG,
    })

    return result
