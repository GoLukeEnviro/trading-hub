#!/usr/bin/env python3
"""Bridge PrimoAgent signals into per-bot Freqtrade state files.

Risk-Aware Version (0.2.0):
- Prefers RiskGuard output as primary source
- Falls back to raw signal only if explicitly configured (disabled by default)
- Writes risk-aware state files with verdict fields
- Fails open when RiskGuard is missing/invalid

Input (preferred):
  /home/hermes/primoagent/output/signals/primo_risk_filtered_latest.json

Input (fallback, optional):
  /home/hermes/primoagent/output/signals/primo_multi_signal_latest.json

Outputs:
  /home/hermes/projects/trading/freqtrade/bots/<bot>/user_data/primo_signal_state.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

VERSION = "0.2.0-risk-aware"
RISKGUARD_VERSION_DEFAULT = "0.1.0"

MAX_AGE_MINUTES_DEFAULT = 45.0
DEFAULT_RISK_INPUT = Path("/home/hermes/primoagent/output/signals/primo_risk_filtered_latest.json")
DEFAULT_RAW_INPUT = Path("/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json")
DEFAULT_BOT_ROOT = Path("/home/hermes/projects/trading/freqtrade/bots")
DEFAULT_BOTS = ["rsi", "momentum", "regime-hybrid"]


def parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 timestamp."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def normalize_pair(pair: str) -> str:
    """Normalize pair name (remove :USDT suffix)."""
    pair = str(pair).strip().upper()
    if ":" in pair:
        pair = pair.split(":", 1)[0]
    return pair


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file."""
    return json.loads(path.read_text())


def source_timestamp(source_path: Path, data: Dict[str, Any]) -> datetime:
    """Get source timestamp from meta or file mtime."""
    meta = data.get("meta") or {}
    generated_at = parse_iso8601(meta.get("generated_at"))
    if generated_at:
        return generated_at
    return datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc)


def build_risk_aware_state(
    risk_path: Path,
    raw_path: Optional[Path],
    max_age_minutes: float,
    use_raw_fallback: bool = False
) -> Dict[str, Any]:
    """Build risk-aware state from RiskGuard output.
    
    Priority:
    1. RiskGuard output (if valid and fresh)
    2. Raw fallback (only if use_raw_fallback=True and RiskGuard unavailable)
    3. Fail-open (no directional bias)
    """
    now = utc_now()
    
    # Try RiskGuard first
    risk_data: Optional[Dict[str, Any]] = None
    riskguard_available = False
    riskguard_version = RISKGUARD_VERSION_DEFAULT
    source_type = "fail_open_no_riskguard"
    source_file = str(risk_path)
    source_generated_at: Optional[str] = None
    max_signal_age_hours: float = 6.0
    
    if risk_path.exists():
        try:
            risk_data = load_json(risk_path)
            riskguard_available = True
            
            # Extract metadata
            meta = risk_data.get("meta", {})
            riskguard_version = meta.get("riskguard_version", RISKGUARD_VERSION_DEFAULT)
            source_generated_at = meta.get("source_generated_at")
            max_signal_age_hours = meta.get("max_signal_age_hours", 6.0)
            
        except (json.JSONDecodeError, Exception):
            risk_data = None
    
    # If RiskGuard failed and raw fallback is enabled
    if risk_data is None and use_raw_fallback and raw_path and raw_path.exists():
        try:
            risk_data = load_json(raw_path)
            source_type = "raw_fallback"
            source_file = str(raw_path)
            meta = risk_data.get("meta", {})
            source_generated_at = meta.get("generated_at")
            riskguard_available = False
        except Exception:
            risk_data = None
    
    # Fail-open: no data available
    if risk_data is None:
        return {
            "schema_version": "0.2",
            "bridge_version": VERSION,
            "written_at": now.isoformat(),
            "source_type": "fail_open_no_riskguard",
            "source_file": str(risk_path),
            "riskguard_available": False,
            "riskguard_version": None,
            "source_generated_at": None,
            "max_signal_age_hours": None,
            "pairs": {},
            "summary": {
                "total": 0,
                "accepted_count": 0,
                "watch_only_count": 0,
                "blocked_count": 0,
                "stale_count": 0,
                "long_bias_count": 0,
                "short_bias_count": 0,
                "fail_open": True
            }
        }
    
    # Process RiskGuard results
    if source_type == "fail_open_no_riskguard":
        source_type = "riskguard"
    
    pairs: Dict[str, Any] = {}
    accepted_count = 0
    watch_only_count = 0
    blocked_count = 0
    stale_count = 0
    long_bias_count = 0
    short_bias_count = 0
    
    results = risk_data.get("results", [])
    for item in results:
        if not isinstance(item, dict):
            continue
        
        pair = normalize_pair(item.get("pair", ""))
        source_action = str(item.get("source_action", "HOLD")).upper().strip()
        normalized_action = str(item.get("normalized_action", "HOLD")).upper().strip()
        confidence = item.get("confidence", 0.0)
        verdict = str(item.get("verdict", "UNKNOWN")).upper().strip()
        reasons = item.get("reasons", [])
        age_seconds = item.get("age_seconds", 0)
        
        # Calculate freshness
        age_minutes = age_seconds / 60.0
        is_fresh = age_minutes <= float(max_age_minutes)
        
        # Determine bias flags based on verdict
        allow_long_bias = False
        allow_short_bias = False
        watch_only = False
        block_entry = False
        
        if verdict == "ACCEPTED":
            if normalized_action in {"BUY", "LONG"}:
                allow_long_bias = True
                long_bias_count += 1
            elif normalized_action in {"SELL", "SHORT"}:
                allow_short_bias = True
                short_bias_count += 1
            accepted_count += 1
        elif verdict == "WATCH_ONLY":
            watch_only = True
            watch_only_count += 1
        elif verdict == "BLOCK_ENTRY":
            block_entry = True
            blocked_count += 1
        else:
            # UNKNOWN or other
            if normalized_action in {"BUY", "LONG"}:
                allow_long_bias = False  # conservative
            elif normalized_action in {"SELL", "SHORT"}:
                allow_short_bias = False  # conservative
        
        if not is_fresh:
            stale_count += 1
        
        pairs[pair] = {
            "pair": pair,
            "source_action": source_action,
            "normalized_action": normalized_action,
            "confidence": float(confidence) if confidence is not None else 0.0,
            "verdict": verdict,
            "reasons": reasons,
            "age_seconds": int(age_seconds),
            "is_fresh": is_fresh,
            "allow_long_bias": allow_long_bias,
            "allow_short_bias": allow_short_bias,
            "watch_only": watch_only,
            "block_entry": block_entry
        }
    
    total = len(pairs)
    
    state: Dict[str, Any] = {
        "schema_version": "0.2",
        "bridge_version": VERSION,
        "written_at": now.isoformat(),
        "source_type": source_type,
        "source_file": source_file,
        "riskguard_available": riskguard_available,
        "riskguard_version": riskguard_version if riskguard_available else None,
        "source_generated_at": source_generated_at,
        "max_signal_age_hours": max_signal_age_hours,
        "pairs": pairs,
        "summary": {
            "total": total,
            "accepted_count": accepted_count,
            "watch_only_count": watch_only_count,
            "blocked_count": blocked_count,
            "stale_count": stale_count,
            "long_bias_count": long_bias_count,
            "short_bias_count": short_bias_count,
            "fail_open": False
        }
    }
    
    return state


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON atomically (temp file + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=str(path.parent), prefix=path.name + ".tmp.") as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_state_for_bots(state: Dict[str, Any], bot_root: Path, bots: List[str]) -> List[Path]:
    """Write state file for each bot."""
    written: List[Path] = []
    for bot in bots:
        dest = bot_root / bot / "user_data" / "primo_signal_state.json"
        atomic_write_json(dest, state)
        written.append(dest)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Risk-Aware Bridge v0.2.0 — Writes risk-filtered state to Freqtrade bots"
    )
    parser.add_argument(
        "--risk-input",
        type=Path,
        default=DEFAULT_RISK_INPUT,
        help="Path to RiskGuard output JSON (default: primo_risk_filtered_latest.json)"
    )
    parser.add_argument(
        "--raw-input",
        type=Path,
        default=DEFAULT_RAW_INPUT,
        help="Path to raw signal JSON (fallback only)"
    )
    parser.add_argument(
        "--use-raw-fallback",
        action="store_true",
        help="Enable raw signal fallback if RiskGuard unavailable (DISABLED BY DEFAULT)"
    )
    parser.add_argument(
        "--bot-root",
        type=Path,
        default=DEFAULT_BOT_ROOT,
        help="Bot root directory"
    )
    parser.add_argument(
        "--bots",
        nargs="*",
        default=DEFAULT_BOTS,
        help="Bot names"
    )
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=MAX_AGE_MINUTES_DEFAULT,
        help="Max signal age in minutes"
    )
    args = parser.parse_args()
    
    # Build risk-aware state
    state = build_risk_aware_state(
        risk_path=args.risk_input,
        raw_path=args.raw_input if args.use_raw_fallback else None,
        max_age_minutes=args.max_age_minutes,
        use_raw_fallback=args.use_raw_fallback
    )
    
    # Write state for all bots
    written = write_state_for_bots(state, args.bot_root, args.bots)
    
    # Print summary
    summary = state.get("summary", {})
    print(json.dumps({
        "bridge_version": VERSION,
        "source_type": state.get("source_type"),
        "riskguard_available": state.get("riskguard_available"),
        "fresh": summary.get("accepted_count", 0) > 0,
        "bots_written": [str(p) for p in written],
        "summary": summary,
    }, indent=2))
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
