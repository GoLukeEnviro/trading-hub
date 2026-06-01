#!/opt/hermes/.venv/bin/python3
"""riskguard_service.py — Standalone RiskGuard Service v1.0

Extracted from trading_pipeline.py. Runs as independent cron job.
Maintains its own health check, audit log, and state file.

LAYERS:
  1. HEALTH — health check endpoint (file-based: riskguard_health.json)
  2. EVALUATE — evaluate signal against risk rules (RG-1 to RG-5)
  3. AUDIT — append-only JSONL audit trail (riskguard_audit.jsonl)
  4. STATE — write decision state file (riskguard_state.json)

RULES (RG):
  RG-1: Stale signal → WATCH_ONLY (fail-safe)
  RG-2: Confidence < threshold → WATCH_ONLY (hard limit)
  RG-3: Missing/invalid bias → WATCH_ONLY
  RG-4: Max concurrent signals cap → WATCH_ONLY
  RG-5: Quantity == 0 → WATCH_ONLY (no position proposed)

Usage:
  /opt/hermes/.venv/bin/python3 riskguard_service.py
  --dry-run    : print decisions without writing files
"""

import json
import os
import sys
import tempfile
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Config ─────────────────────────────────────────

PROJECT_DIR = Path("/home/hermes/projects/trading")
STATE_DIR = PROJECT_DIR / "orchestrator/state/riskguard"
HEALTH_FILE = STATE_DIR / "riskguard_health.json"
STATE_FILE = STATE_DIR / "riskguard_state.json"
AUDIT_FILE = STATE_DIR / "riskguard_audit.jsonl"

SIGNAL_INPUT_PATHS = [
    PROJECT_DIR / "ai-hedge-fund-crypto/output/hermes_signal.json",
    PROJECT_DIR / "ai-hedge-fund-crypto/output/latest/hermes_signal.json",
    PROJECT_DIR / "shared/hermes_signal.json",
]

CONFIDENCE_THRESHOLD = 0.65
MAX_AGE_MINUTES = 25.0
MAX_CONCURRENT_SIGNALS = 5
SCHEMA_VERSION = "1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] riskguard: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("riskguard_service")


# ── LAYER 1: HEALTH ────────────────────────────────

def write_health(status: str, checks: Dict[str, Any]) -> None:
    """Write health check status file."""
    os.makedirs(str(STATE_DIR), exist_ok=True)
    health = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "riskguard",
        "status": status,
        "checks": checks,
    }
    _atomic_write_json(str(HEALTH_FILE), health)
    return health


# ── LAYER 2: EVALUATE ──────────────────────────────

def normalize_pair(pair: str) -> str:
    if ":" in pair:
        pair = pair.split(":", 1)[0]
    return pair.strip()


def read_signal() -> Tuple[Optional[Dict[str, Any]], str]:
    override = os.environ.get("RISKGUARD_SIGNAL_OVERRIDE", "").strip()
    if override:
        path = Path(override)
        if path.exists():
            try:
                return json.loads(path.read_text()), str(path)
            except Exception as e:
                logger.warning(f"Override read failed: {e}")
    for path in SIGNAL_INPUT_PATHS:
        if path.exists():
            try:
                return json.loads(path.read_text()), str(path)
            except Exception as e:
                logger.warning(f"Read failed {path}: {e}")
                continue
    return None, ""


def get_signal_age(signal: Dict[str, Any]) -> Optional[float]:
    ts_str = signal.get("generated_at") or signal.get("timestamp_utc") or signal.get("timestamp") or ""
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None


def evaluate(pair_key: str, pair_data: Dict[str, Any], is_stale: bool, accepted_count: int) -> Dict[str, Any]:
    """RG-1 through RG-5 evaluation logic. Pure function — no side effects."""
    if is_stale:
        return {"verdict": "WATCH_ONLY", "action": "HOLD", "confidence": 0.0, "quantity": 0.0,
                "allow_long_bias": False, "allow_short_bias": False, "riskguard_reason": "RG-1: signal stale"}

    confidence = float(pair_data.get("confidence", 0.0))
    bias = str(pair_data.get("bias", "neutral")).lower().strip()
    action_raw = str(pair_data.get("action", "hold")).lower().strip()
    quantity = float(pair_data.get("quantity", 0.0))

    action = "LONG" if action_raw in ("buy", "long") else "SHORT" if action_raw in ("sell", "short") else "HOLD"

    if confidence < CONFIDENCE_THRESHOLD:
        return {"verdict": "WATCH_ONLY", "action": "HOLD", "confidence": round(confidence, 4), "quantity": 0.0,
                "allow_long_bias": False, "allow_short_bias": False,
                "riskguard_reason": f"RG-2: confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD:.2f}"}

    if bias not in ("bullish", "bearish"):
        return {"verdict": "WATCH_ONLY", "action": action if action != "HOLD" else "HOLD",
                "confidence": round(confidence, 4), "quantity": 0.0,
                "allow_long_bias": False, "allow_short_bias": False,
                "riskguard_reason": f"RG-3: non-directional bias '{bias}'"}

    if quantity <= 0 and action in ("LONG", "SHORT"):
        return {"verdict": "WATCH_ONLY", "action": "HOLD", "confidence": round(confidence, 4), "quantity": 0.0,
                "allow_long_bias": False, "allow_short_bias": False,
                "riskguard_reason": "RG-5: quantity=0 despite directional action"}

    if accepted_count >= MAX_CONCURRENT_SIGNALS:
        return {"verdict": "WATCH_ONLY", "action": "HOLD", "confidence": round(confidence, 4), "quantity": 0.0,
                "allow_long_bias": False, "allow_short_bias": False,
                "riskguard_reason": f"RG-4: max concurrent signals ({MAX_CONCURRENT_SIGNALS}) reached"}

    if bias == "bullish":
        return {"verdict": "ACCEPTED", "action": action if action in ("LONG", "SHORT") else "LONG",
                "confidence": round(confidence, 4), "quantity": quantity,
                "allow_long_bias": True, "allow_short_bias": False, "riskguard_reason": "PASS: all checks OK"}
    else:
        return {"verdict": "ACCEPTED", "action": action if action in ("LONG", "SHORT") else "SHORT",
                "confidence": round(confidence, 4), "quantity": quantity,
                "allow_long_bias": False, "allow_short_bias": True, "riskguard_reason": "PASS: all checks OK"}


# ── LAYER 3: AUDIT ─────────────────────────────────

def write_audit(entry: Dict[str, Any]) -> bool:
    """Append-one JSONL audit entry."""
    try:
        os.makedirs(str(STATE_DIR), exist_ok=True)
        with open(str(AUDIT_FILE), "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        return True
    except Exception as e:
        logger.error(f"Audit write failed: {e}")
        return False


# ── HELPERS ────────────────────────────────────────

def _atomic_write_json(path: str, data: Dict[str, Any]) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".riskguard.", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except Exception as e:
        try: os.unlink(tmp)
        except: pass
        logger.error(f"Write failed: {e}")
        return False


# ── MAIN ───────────────────────────────────────────

def main() -> int:
    dry_run = "--dry-run" in sys.argv
    now_ts = datetime.now(timezone.utc).isoformat()

    # 1. Read signal
    signal, source = read_signal()
    if signal is None:
        logger.warning("No signal file found")
        write_health("DEGRADED", {"signal_found": False, "error": "no signal file"})
        return 1

    age = get_signal_age(signal)
    is_stale = age is None or age > MAX_AGE_MINUTES
    logger.info(f"Signal: {source} | age={age:.1f}min | stale={is_stale}")

    # 2. Evaluate all pairs
    signal_pairs = signal.get("pairs", {})
    accepted_count = 0
    decisions = []
    pairs_out = {}

    for pair_key, pair_data in signal_pairs.items():
        norm = normalize_pair(pair_key)
        decision = evaluate(pair_key, pair_data, is_stale=False, accepted_count=accepted_count)
        if decision["verdict"] == "ACCEPTED":
            accepted_count += 1
            decision = evaluate(pair_key, pair_data, is_stale=False, accepted_count=accepted_count)
        pairs_out[norm] = decision
        decisions.append({
            "pair": norm,
            "confidence": decision["confidence"],
            "verdict": decision["verdict"],
            "action": decision["action"],
            "allow_long": decision["allow_long_bias"],
            "allow_short": decision["allow_short_bias"],
            "riskguard_reason": decision.get("riskguard_reason", ""),
        })

    # 3. Summary
    accepted_final = sum(1 for p in pairs_out.values() if p["verdict"] == "ACCEPTED")
    watch_only_final = sum(1 for p in pairs_out.values() if p["verdict"] == "WATCH_ONLY")

    summary = {
        "status": "ACTIVE",
        "total_pairs": len(pairs_out),
        "accepted": accepted_final,
        "watch_only": watch_only_final,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "max_age_minutes": MAX_AGE_MINUTES,
        "concurrent_signals": MAX_CONCURRENT_SIGNALS,
        "stale": is_stale,
    }

    logger.info(f"RiskGuard: ACCEPTED={accepted_final}, WATCH_ONLY={watch_only_final}, total={len(pairs_out)}")
    for d in decisions:
        logger.info(f"  {d['pair']}: conf={d['confidence']:.2f} -> {d['verdict']} [{d['riskguard_reason']}]")

    if dry_run:
        print(json.dumps({"summary": summary, "decisions": decisions}, indent=2))
        return 0

    # 4. Write state
    state = {
        "schema_version": "1.0",
        "timestamp": now_ts,
        "signal_source": source,
        "signal_age_minutes": round(age, 1) if age else None,
        "summary": summary,
        "pairs": pairs_out,
    }
    state_ok = _atomic_write_json(str(STATE_FILE), state)

    # 5. Write audit
    audit_entry = {
        "schema_version": "1.0",
        "event": "riskguard_evaluation",
        "timestamp": now_ts,
        "signal": {"source": source, "age_minutes": round(age, 1) if age else None, "fresh": not is_stale},
        "summary": summary,
        "decisions": decisions,
        "state_written": state_ok,
    }
    audit_ok = write_audit(audit_entry)

    # 6. Write health
    health = write_health("OK" if state_ok else "DEGRADED", {
        "signal_found": signal is not None,
        "signal_age_minutes": round(age, 1) if age else None,
        "state_written": state_ok,
        "audit_written": audit_ok,
        "accepted": accepted_final,
        "watch_only": watch_only_final,
    })

    logger.info(f"State: {'OK' if state_ok else 'FAIL'} | Audit: {'OK' if audit_ok else 'FAIL'} | Health: {health['status']}")
    return 0 if state_ok else 1


if __name__ == "__main__":
    sys.exit(main())
