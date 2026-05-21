#!/usr/bin/env python3
"""trading_pipeline.py — Unified Signal Pipeline v1.0

LAYERS:
  1. BRIDGE       — read ai-hedge-fund-crypto signal, normalize pairs
  2. RISKGUARD    — confidence >= 0.65 hard limit, basic risk checks
  3. SHADOWLOGGER — append-only JSONL audit trail
  4. BRIDGE-WRITE — write per-bot primo_signal_state.json files

Runs as cron job. Single-file, zero dependencies beyond stdlib.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Config ──────────────────────────────────────────────────────────

PROJECT_DIR = Path("/home/hermes/projects/trading")

# Signal sources (tried in order)
SIGNAL_INPUT_PATHS = [
    PROJECT_DIR / "ai-hedge-fund-crypto/output/hermes_signal.json",      # canonical first
    PROJECT_DIR / "ai-hedge-fund-crypto/output/latest/hermes_signal.json",
    PROJECT_DIR / "shared/hermes_signal.json",
]

# Per-bot state file targets
STATE_OUTPUT_FILES = [
    PROJECT_DIR / "freqtrade/shared/primo_signal_state.json",
    PROJECT_DIR / "freqtrade/bots/momentum/user_data/primo_signal_state.json",
    PROJECT_DIR / "freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json",
]

# RiskGuard config — import canonical constants from fleet_risk_manager
try:
    sys.path.insert(0, str(PROJECT_DIR / "freqtrade" / "shared"))
    from fleet_risk_manager import CONFIDENCE_MIN, STALENESS_MINUTES  # canonical
    CONFIDENCE_THRESHOLD = CONFIDENCE_MIN
    MAX_AGE_MINUTES = STALENESS_MINUTES
except ImportError:
    # Fallback — keep in sync with freqtrade/shared/fleet_risk_manager.py
    CONFIDENCE_THRESHOLD = 0.65      # hard limit — SOUL.md Live-Regel 4
    MAX_AGE_MINUTES = 30.0           # hard stale block threshold
MAX_POSITION_SIZE_USDT = 100.0    # max per-trade exposure
MAX_CONCURRENT_SIGNALS = 5        # max pairs with ACCEPTED verdict
SCHEMA_VERSION = "0.3"

# MCP Execution Layer config
MCP_SERVER_SCRIPT = PROJECT_DIR / "orchestrator/scripts/bitget_mcp_server.py"
MCP_DRY_RUN = True                # HARDCODED — never execute live orders
MCP_ENABLED = True                 # set False to disable MCP and use ccxt-only
MCP_LOG_DIR = PROJECT_DIR / "orchestrator/logs/mcp"

# ShadowLogger paths
SHADOW_LOG_DIR = PROJECT_DIR / "orchestrator/logs"
SHADOW_LOG_FILE = SHADOW_LOG_DIR / "shadow_decisions.jsonl"
BRIDGE_LOG_FILE = SHADOW_LOG_DIR / "signal_bridge.log"

# ── Logging ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] pipeline: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("trading_pipeline")


# ═══════════════════════════════════════════════════════════════════
# LAYER 1: BRIDGE — Read & Parse Signal
# ═══════════════════════════════════════════════════════════════════

def normalize_pair(pair: str) -> str:
    """BTC/USDT:USDT → BTC/USDT"""
    if ":" in pair:
        pair = pair.split(":", 1)[0]
    return pair.strip()


def read_signal() -> Tuple[Optional[Dict[str, Any]], str]:
    """Read signal from override, primary, or fallback path."""
    override = os.environ.get("SIGNAL_OVERRIDE", "").strip()
    if override:
        path = Path(override)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return data, str(path)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read SIGNAL_OVERRIDE {path}: {e}")
        else:
            logger.warning(f"SIGNAL_OVERRIDE path does not exist: {path}")

    for path in SIGNAL_INPUT_PATHS:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return data, str(path)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read {path}: {e}")
                continue
    return None, ""


def get_signal_age_minutes(signal: Dict[str, Any]) -> Optional[float]:
    """Calculate signal age in minutes from generated_at/timestamp fields."""
    ts_str = (
        signal.get("generated_at")
        or signal.get("timestamp_utc")
        or signal.get("timestamp")
        or ""
    )
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
        return age
    except (ValueError, TypeError):
        return None


def check_signal_freshness(signal: Optional[Dict[str, Any]], max_age_min: float = MAX_AGE_MINUTES) -> Tuple[bool, str, Optional[float]]:
    """Hard freshness gate. Returns (is_fresh, reason, age_minutes)."""
    if signal is None:
        return False, "no_signal", None
    age = get_signal_age_minutes(signal)
    if age is None:
        return False, "no_timestamp", None
    if age > max_age_min:
        return False, f"stale_{int(age)}min", age
    return True, "fresh", age


def load_known_pairs() -> List[str]:
    """Load known pair list from existing state template."""
    template = PROJECT_DIR / "freqtrade/shared/primo_signal_state.json"
    if not template.exists():
        return []
    try:
        data = json.loads(template.read_text())
        pairs = data.get("pairs", {})
        return list(pairs.keys())
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
# LAYER 2: RISKGUARD — Decision Logic
# ═══════════════════════════════════════════════════════════════════

def riskguard_checks(
    pair_data: Dict[str, Any],
    pair_key: str,
    is_stale: bool,
    accepted_count: int,
) -> Dict[str, Any]:
    """Apply RiskGuard rules. Returns enriched decision dict.

    Rules enforced:
      RG-1: Stale signal → WATCH_ONLY (fail-safe)
      RG-2: Confidence < 0.65 → WATCH_ONLY + shadow REJECTED (hard limit)
      RG-3: Missing/invalid bias → WATCH_ONLY
      RG-4: Max concurrent signals cap → WATCH_ONLY if cap exceeded
      RG-5: Quantity == 0 → WATCH_ONLY (no position proposed)
    """
    # RG-1: Stale = always watch
    if is_stale:
        return {
            "verdict": "WATCH_ONLY",
            "action": "HOLD",
            "confidence": 0.0,
            "quantity": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": "RG-1: signal stale",
        }

    confidence = float(pair_data.get("confidence", 0.0))
    bias = str(pair_data.get("bias", "neutral")).lower().strip()
    action_raw = str(pair_data.get("action", "hold")).lower().strip()
    quantity = float(pair_data.get("quantity", 0.0))

    # Map action string
    if action_raw in ("buy", "long"):
        action = "LONG"
    elif action_raw in ("sell", "short"):
        action = "SHORT"
    else:
        action = "HOLD"

    # RG-2: Confidence hard limit
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "verdict": "WATCH_ONLY",
            "action": "HOLD",
            "confidence": round(confidence, 4),
            "quantity": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": f"RG-2: confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD:.2f}",
        }

    # RG-3: Unknown bias
    if bias not in ("bullish", "bearish"):
        return {
            "verdict": "WATCH_ONLY",
            "action": action if action != "HOLD" else "HOLD",
            "confidence": round(confidence, 4),
            "quantity": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": f"RG-3: non-directional bias '{bias}'",
        }

    # RG-5: No position quantity proposed
    if quantity <= 0 and action in ("LONG", "SHORT"):
        return {
            "verdict": "WATCH_ONLY",
            "action": "HOLD",
            "confidence": round(confidence, 4),
            "quantity": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": "RG-5: quantity=0 despite directional action",
        }

    # RG-4: Max concurrent signals cap
    if accepted_count >= MAX_CONCURRENT_SIGNALS:
        return {
            "verdict": "WATCH_ONLY",
            "action": "HOLD",
            "confidence": round(confidence, 4),
            "quantity": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": f"RG-4: max concurrent signals ({MAX_CONCURRENT_SIGNALS}) reached",
        }

    if bias == "bullish":
        return {
            "verdict": "ACCEPTED",
            "action": action if action in ("LONG", "SHORT") else "LONG",
            "confidence": round(confidence, 4),
            "quantity": quantity,
            "allow_long_bias": True,
            "allow_short_bias": False,
            "riskguard_reason": "PASS: all checks OK",
        }
    else:  # bearish
        return {
            "verdict": "ACCEPTED",
            "action": action if action in ("LONG", "SHORT") else "SHORT",
            "confidence": round(confidence, 4),
            "quantity": quantity,
            "allow_long_bias": False,
            "allow_short_bias": True,
            "riskguard_reason": "PASS: all checks OK",
        }


# ═══════════════════════════════════════════════════════════════════════
# LAYER 2.5: MCP EXECUTION — Primary Execution via MCP, ccxt Fallback
# ═══════════════════════════════════════════════════════════════════════

def mcp_execute_order(symbol: str, side: str, amount: float,
                       order_type: str = "market",
                       price: Optional[float] = None) -> Dict[str, Any]:
    """Execute an order through the Bitget MCP server (always dry-run).

    Calls the MCP server's place_order tool via subprocess.
    Falls back to direct ccxt if MCP server is not reachable.

    Returns the order result dict.
    """
    if not MCP_DRY_RUN:
        return {"error": "LIVE TRADING BLOCKED — dry_run is HARDCODED True",
                "dry_run": True}

    result = {"status": "skipped", "reason": "MCP not executed", "dry_run": True}

    if MCP_ENABLED and MCP_SERVER_SCRIPT.exists():
        try:
            logger.info(f"MCP execute: {side} {amount} {symbol} via bitget-paper server")

            # Ensure trading directory is in sys.path for imports
            import sys as _sys
            _project_root = str(PROJECT_DIR)
            if _project_root not in _sys.path:
                _sys.path.insert(0, _project_root)

            from orchestrator.scripts.bitget_mcp_server import (
                handle_place_order,
                handle_get_positions,
                load_portfolio,
            )

            # Ensure portfolio loaded
            load_portfolio()

            # Execute via MCP paper engine
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                order_result = loop.run_until_complete(
                    handle_place_order(symbol, side, amount, order_type, price)
                )
                result = {
                    "status": "executed",
                    "order": order_result,
                    "execution_layer": "MCP",
                    "dry_run": True,
                }
                logger.info(f"MCP order result: {json.dumps(order_result, default=str)}")
            finally:
                loop.close()

        except ImportError as ie:
            logger.warning(f"MCP direct import failed ({ie}), trying ccxt fallback...")
            result = ccxt_execute_order(symbol, side, amount, order_type, price, is_fallback=True)
        except Exception as e:
            logger.error(f"MCP execution error: {e}")
            result = {
                "status": "failed",
                "error": str(e),
                "execution_layer": "MCP",
                "dry_run": True,
            }
    else:
        logger.info("MCP disabled or unavailable, using ccxt fallback")
        result = ccxt_execute_order(symbol, side, amount, order_type, price, is_fallback=True)

    return result


def ccxt_execute_order(symbol: str, side: str, amount: float,
                        order_type: str = "market",
                        price: Optional[float] = None,
                        is_fallback: bool = False) -> Dict[str, Any]:
    """Execute order via direct ccxt (fallback path). Always dry-run."""
    layer = "ccxt-fallback" if is_fallback else "ccxt-primary"
    try:
        try:
            import ccxt
            exchange = ccxt.bitget({
                "apiKey": "",
                "secret": "",
                "password": "",
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            })
            exchange.set_sandbox_mode(True)
        except ModuleNotFoundError:
            logger.info(f"{layer}: ccxt not available, generating simulated order")

        # Simulate order
        order_id = f"paper_ccxt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{hash(symbol+side) & 0xffff:04x}"
        logger.info(f"ccxt fallback: {side} {amount} {symbol} ({order_id})")

        return {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price or 0,
            "status": "simulated",
            "execution_layer": layer,
            "dry_run": True,
        }
    except Exception as e:
        logger.error(f"ccxt fallback failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "execution_layer": layer,
            "dry_run": True,
        }


def mcp_execute_accepted_signals(pairs_out: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute all ACCEPTED signals via MCP.

    Iterates over all pairs with ACCEPTED verdict and routes
    SHORT/LONG actions through the MCP execution layer.
    Returns a list of execution results.
    """
    execution_results = []

    for pair, decision in pairs_out.items():
        if decision.get("verdict") != "ACCEPTED":
            continue

        action = decision.get("action", "HOLD")
        if action not in ("LONG", "SHORT"):
            continue

        # Map action to side
        side = "buy" if action == "LONG" else "sell"

        # Use quantity from signal if available, else compute from max position size
        confidence = decision.get("confidence", 0.0)
        quantity = decision.get("quantity", 0.0)

        if quantity <= 0:
            # Fallback: estimate based on max position size and confidence
            # Get ticker for price estimation
            try:
                import sys as _sys
                _project_root = str(PROJECT_DIR)
                if _project_root not in _sys.path:
                    _sys.path.insert(0, _project_root)
                import asyncio
                from orchestrator.scripts.bitget_mcp_server import handle_get_ticker
                loop = asyncio.new_event_loop()
                try:
                    ticker = loop.run_until_complete(handle_get_ticker(pair))
                    price = ticker.get("last", 50000.0)
                finally:
                    loop.close()
            except Exception:
                price = 50000.0 if "BTC" in pair else 3000.0 if "ETH" in pair else 150.0

            quantity = round((MAX_POSITION_SIZE_USDT * confidence) / price, 6)
            if quantity <= 0:
                quantity = 0.001  # minimum notional

        logger.info(f"MCP executing: {action} {quantity} {pair} (conf={confidence:.2f})")
        result = mcp_execute_order(pair, side, quantity)
        execution_results.append({
            "pair": pair,
            "action": action,
            "quantity": quantity,
            "confidence": confidence,
            "result": result,
        })

    return execution_results


# ═══════════════════════════════════════════════════════════════════════
# LAYER 3: SHADOWLOGGER — Append-only Audit Trail
# ═══════════════════════════════════════════════════════════════════════

def shadow_log(
    timestamp: str,
    signal_source: str,
    signal_age_minutes: Optional[float],
    is_fresh: bool,
    riskguard_summary: Dict[str, Any],
    pair_decisions: List[Dict[str, Any]],
    state_writes: Dict[str, str],
) -> None:
    """Append a JSONL entry to the shadow log.

    The shadow log is append-only — never modified, never truncated.
    Each entry is a complete snapshot of one pipeline cycle.
    """
    entry = {
        "schema_version": "1.0",
        "event": "pipeline_cycle",
        "timestamp": timestamp,
        "signal": {
            "source": signal_source,
            "age_minutes": round(signal_age_minutes, 1) if signal_age_minutes is not None else None,
            "fresh": is_fresh,
        },
        "riskguard": riskguard_summary,
        "decisions": pair_decisions,
        "state_writes": state_writes,
    }

    try:
        SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SHADOW_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception as e:
        logger.error(f"ShadowLogger write failed: {e}")


def write_bridge_log(entry: Dict[str, Any]) -> None:
    """Legacy bridge log entry (backward compatible)."""
    try:
        BRIDGE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BRIDGE_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception as e:
        logger.error(f"Bridge log write failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# LAYER 4: BRIDGE-WRITE — Write Per-Bot State Files
# ═══════════════════════════════════════════════════════════════════

def build_state(
    signal: Optional[Dict[str, Any]],
    signal_age: Optional[float],
    pairs_out: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the full primo_signal_state.json dict."""
    now = datetime.now(timezone.utc)
    is_stale = signal is None or signal_age is None or signal_age > MAX_AGE_MINUTES

    state = {
        "schema_version": SCHEMA_VERSION,
        "fresh": not is_stale,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "processed_at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "age_minutes": round(signal_age, 1) if signal_age is not None else 9999.0,
        "source": "trading_pipeline_v1.0",
        "pairs": pairs_out,
    }
    return state


def atomic_write_json(path: Path, data: Dict[str, Any]) -> bool:
    """Write JSON atomically via tmp+rename."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".pipeline_tmp_",
            suffix=".json",
        )
        try:
            os.fchmod(tmp_fd, 0o644)
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.rename(tmp_path, str(path))
            return True
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.error(f"Write failed for {path}: {e}")
        return False


def write_state_files(state: Dict[str, Any], state_files: List[Path]) -> Dict[str, str]:
    """Write state to all target files. Returns {path: status}."""
    results = {}
    for path in state_files:
        ok = atomic_write_json(path, state)
        results[str(path)] = "OK" if ok else "FAIL"
        if ok:
            logger.info(f"✅ Written: {path}")
        else:
            logger.error(f"❌ FAILED: {path}")
    return results


# ═══════════════════════════════════════════════════════════════════
# MAIN — Run Full Pipeline
# ═══════════════════════════════════════════════════════════════════

def main() -> int:
    dry_run = "--dry-run" in sys.argv
    now_ts = datetime.now(timezone.utc).isoformat()

    if dry_run:
        logger.info("=== DRY RUN — no files written ===")

    # ── 1. Read Signal ──────────────────────────────────────────
    signal, source = read_signal()
    if signal is None:
        logger.warning("No signal file found. Running with stale state.")
    else:
        logger.info(f"Signal read from: {source}")

    is_fresh, freshness_reason, signal_age = check_signal_freshness(signal)
    if signal_age is not None:
        logger.info(f"Signal age: {signal_age:.1f} minutes")
    else:
        logger.warning("Cannot determine signal age.")

    is_stale = not is_fresh

    # ── 2. HARD STALE BLOCK ─────────────────────────────────────
    # If signal is stale: write empty stale state, log PIPELINE_BLOCKED, exit.
    # This prevents bots from trading on old/missing/invalid signals.
    if is_stale:
        logger.warning(f"PIPELINE BLOCKED: {freshness_reason}")
        stale_state = {
            "schema_version": SCHEMA_VERSION,
            "fresh": False,
            "stale": True,
            "block_reason": freshness_reason,
            "generated_at": now_ts,
            "processed_at": now_ts,
            "age_minutes": round(signal_age, 1) if signal_age is not None else 9999.0,
            "source": "trading_pipeline_v1.0",
            "pairs": {},
        }

        if dry_run:
            logger.info("DRY RUN — would write stale block state to all targets")
            print(json.dumps(stale_state, indent=2))
        else:
            state_writes = write_state_files(stale_state, STATE_OUTPUT_FILES)
            block_entry = {
                "schema_version": "1.0",
                "event": "PIPELINE_BLOCKED",
                "timestamp": now_ts,
                "signal": {
                    "source": source,
                    "age_minutes": round(signal_age, 1) if signal_age is not None else None,
                    "fresh": False,
                    "block_reason": freshness_reason,
                },
                "riskguard": {
                    "status": "BLOCKED",
                    "reason": freshness_reason,
                    "confidence_threshold": CONFIDENCE_THRESHOLD,
                    "max_age_minutes": MAX_AGE_MINUTES,
                },
                "decisions": [],
                "state_writes": state_writes,
            }
            try:
                SHADOW_LOG_DIR.mkdir(parents=True, exist_ok=True)
                with open(SHADOW_LOG_FILE, "a") as f:
                    f.write(json.dumps(block_entry, separators=(",", ":")) + "\n")
                logger.info("ShadowLogger: PIPELINE_BLOCKED entry appended")
            except Exception as e:
                logger.error(f"ShadowLogger write failed: {e}")
        print(f"Pipeline geblockt: {freshness_reason}")
        logger.info("Pipeline cycle complete (BLOCKED).")
        return 0

    # ── 2. Load known pairs ─────────────────────────────────────
    known_pairs = load_known_pairs()
    logger.info(f"Known pairs from template: {len(known_pairs)}")

    # ── 3. RiskGuard — evaluate each pair ───────────────────────
    accepted_count = 0
    pairs_out: Dict[str, Dict[str, Any]] = {}
    pair_decisions: List[Dict[str, Any]] = []

    # Start with all known pairs as WATCH_ONLY (default)
    for pair in known_pairs:
        pairs_out[pair] = {
            "verdict": "WATCH_ONLY",
            "action": "HOLD",
            "confidence": 0.0,
            "allow_long_bias": False,
            "allow_short_bias": False,
            "riskguard_reason": "default: no signal data",
        }

    # Overlay with signal pairs if fresh
    if not is_stale and signal:
        signal_pairs = signal.get("pairs", {})
        for pair_key, pair_data in signal_pairs.items():
            norm = normalize_pair(pair_key)

            # Preview decision count before RG-4
            decision = riskguard_checks(pair_data, pair_key, is_stale=False, accepted_count=accepted_count)

            if decision["verdict"] == "ACCEPTED":
                accepted_count += 1
                # Re-run with updated count to enforce RG-4 correctly
                decision = riskguard_checks(pair_data, pair_key, is_stale=False, accepted_count=accepted_count)

            pairs_out[norm] = decision

            shadow_decision = "REJECTED" if decision.get("riskguard_reason", "").startswith("RG-2:") else decision["verdict"]
            pair_decisions.append({
                "pair": norm,
                "confidence": decision["confidence"],
                "verdict": decision["verdict"],
                "decision": shadow_decision,
                "action": decision["action"],
                "allow_long": decision["allow_long_bias"],
                "allow_short": decision["allow_short_bias"],
                "riskguard_reason": decision.get("riskguard_reason", ""),
            })

    # ── RiskGuard Summary ───────────────────────────────────────
    total_pairs = len(pairs_out)
    accepted_count_final = sum(1 for p in pairs_out.values() if p["verdict"] == "ACCEPTED")
    watch_only_count = sum(1 for p in pairs_out.values() if p["verdict"] == "WATCH_ONLY")
    rejected_count = sum(1 for d in pair_decisions if d.get("decision") == "REJECTED")

    riskguard_summary = {
        "status": "ACTIVE" if not is_stale else "STALE",
        "total_pairs": total_pairs,
        "accepted": accepted_count_final,
        "watch_only": watch_only_count,
        "rejected": rejected_count,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "max_age_minutes": MAX_AGE_MINUTES,
        "stale": is_stale,
    }

    logger.info(
        f"RiskGuard: fresh={not is_stale}, "
        f"ACCEPTED={accepted_count_final}, "
        f"WATCH_ONLY={watch_only_count}, "
        f"total={total_pairs}"
    )

    # Log each pair decision
    for d in pair_decisions:
        logger.info(
            f"  {d['pair']}: conf={d['confidence']:.2f} "
            f"→ {d['verdict']} L={d['allow_long']} S={d['allow_short']} "
            f"[{d['riskguard_reason']}]"
        )

    # ── 3.5 MCP Execution Layer — route ACCEPTED signals via MCP ─
    mcp_results = []
    if not dry_run and not is_stale:
        try:
            mcp_results = mcp_execute_accepted_signals(pairs_out)
            for r in mcp_results:
                status = r.get("result", {}).get("status", "unknown")
                pair = r.get("pair", "?")
                action = r.get("action", "?")
                logger.info(f"MCP[{pair}] {action}: {status}")
        except Exception as e:
            logger.error(f"MCP execution layer error: {e}")
    elif dry_run:
        logger.info("DRY RUN — MCP execution skipped")
    else:
        logger.info("Stale signal — MCP execution skipped")

    # ── 4. Build State ──────────────────────────────────────────
    state = build_state(signal, signal_age, pairs_out)

    # ── 5. Write State Files or Dry-Run ─────────────────────────
    state_writes: Dict[str, str] = {}

    if dry_run:
        logger.info("DRY RUN — would write to:")
        for f in STATE_OUTPUT_FILES:
            logger.info(f"  {f}")
        print(json.dumps(state, indent=2))
    else:
        state_writes = write_state_files(state, STATE_OUTPUT_FILES)

    # ── 6. ShadowLogger ─────────────────────────────────────────
    # ALWAYS log — even in dry_run mode. Audit trail must be complete.
    shadow_log(
        timestamp=now_ts,
        signal_source=source,
        signal_age_minutes=signal_age,
        is_fresh=not is_stale,
        riskguard_summary=riskguard_summary,
        pair_decisions=pair_decisions,
        state_writes=state_writes,
    )

    # Legacy bridge log (backward compatible)
    bridge_entry = {
        "timestamp": now_ts,
        "signal_source": source,
        "signal_age_minutes": round(signal_age, 1) if signal_age is not None else None,
        "fresh": not is_stale,
        "pairs_total": total_pairs,
        "pairs_accepted": accepted_count_final,
        "pairs_watch_only": watch_only_count,
        "pairs_rejected": rejected_count,
        "writes": state_writes,
    }
    write_bridge_log(bridge_entry)

    logger.info("✅ ShadowLogger: entry appended")

    # ── 7. Exit code ────────────────────────────────────────────
    failed = sum(1 for v in state_writes.values() if v == "FAIL")
    if failed:
        logger.error(f"{failed}/{len(state_writes)} writes failed")
        return 1

    logger.info("Pipeline cycle complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
