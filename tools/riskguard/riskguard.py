#!/usr/bin/env python3
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple

BASE_DIR = Path("/home/hermes/projects/trading")
SIGNAL_FILE = BASE_DIR / "ai-hedge-fund-crypto/output/hermes_signal.json"
DECISIONS_FILE = BASE_DIR / "tools/riskguard/decisions.jsonl"

ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD"}
CONFIDENCE_THRESHOLD = 0.6
MAX_AGE_MINUTES = 15


@dataclass
class Decision:
    verdict: str
    reason: str
    confidence: float
    age_minutes: float | None


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    txt = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_actions(doc: dict[str, Any]) -> List[str]:
    actions: List[str] = []

    for key in ("action", "signal", "decision"):
        val = doc.get(key)
        if isinstance(val, str):
            actions.append(val.upper())

    pairs = doc.get("pairs")
    if isinstance(pairs, dict):
        for _pair, item in pairs.items():
            if isinstance(item, dict):
                a = item.get("action")
                if isinstance(a, str):
                    actions.append(a.upper())

    signals = doc.get("signals")
    if isinstance(signals, list):
        for item in signals:
            if isinstance(item, dict):
                a = item.get("action")
                if isinstance(a, str):
                    actions.append(a.upper())

    return actions


def _extract_confidence(doc: dict[str, Any]) -> float:
    cand = doc.get("confidence")
    if isinstance(cand, (int, float)):
        return float(cand)

    pair_conf: List[float] = []
    pairs = doc.get("pairs")
    if isinstance(pairs, dict):
        for _pair, item in pairs.items():
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float)):
                pair_conf.append(float(item["confidence"]))
    if pair_conf:
        return sum(pair_conf) / len(pair_conf)

    return 0.0


def evaluate(doc: dict[str, Any]) -> Decision:
    # Schema-Minimum
    ts = _parse_ts(doc.get("timestamp"))
    if ts is None:
        return Decision("BLOCK_ENTRY", "missing_or_invalid_timestamp", 0.0, None)

    actions = _extract_actions(doc)
    if not actions:
        return Decision("BLOCK_ENTRY", "missing_action_field", _extract_confidence(doc), None)

    invalid = [a for a in actions if a not in ALLOWED_ACTIONS]
    if invalid:
        return Decision("BLOCK_ENTRY", f"invalid_actions:{sorted(set(invalid))}", _extract_confidence(doc), None)

    # Freshness
    now = datetime.now(timezone.utc)
    age_minutes = (now - ts).total_seconds() / 60.0
    conf = _extract_confidence(doc)

    if age_minutes > MAX_AGE_MINUTES:
        return Decision("WATCH_ONLY", f"stale_signal:{age_minutes:.1f}m", conf, age_minutes)

    # Confidence Gate
    if conf >= CONFIDENCE_THRESHOLD:
        return Decision("ACCEPTED", f"fresh_and_confident:{conf:.3f}", conf, age_minutes)

    return Decision("WATCH_ONLY", f"confidence_below_threshold:{conf:.3f}", conf, age_minutes)


def main() -> int:
    if not SIGNAL_FILE.exists():
        d = Decision("BLOCK_ENTRY", "signal_file_missing", 0.0, None)
        _write_decision(d)
        print(f"{d.verdict} | {d.reason}")
        return 0

    try:
        doc = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("signal root must be object")
    except Exception as exc:
        d = Decision("BLOCK_ENTRY", f"signal_parse_error:{exc.__class__.__name__}", 0.0, None)
        _write_decision(d)
        print(f"{d.verdict} | {d.reason}")
        return 0

    d = evaluate(doc)
    _write_decision(d)
    print(f"{d.verdict} | {d.reason}")
    return 0


def _write_decision(d: Decision) -> None:
    DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "signal_file": str(SIGNAL_FILE),
        "verdict": d.verdict,
        "reason": d.reason,
        "confidence": d.confidence,
        "age_minutes": d.age_minutes,
        "rules": {
            "allowed_actions": sorted(ALLOWED_ACTIONS),
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "max_age_minutes": MAX_AGE_MINUTES,
        },
    }
    with DECISIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
