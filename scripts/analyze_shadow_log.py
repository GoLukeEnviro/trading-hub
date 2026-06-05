#!/usr/bin/env python3
"""Analyze shadow_decisions.jsonl for confidence calibration."""
import json, statistics
from pathlib import Path

log_path = Path("/home/hermes/projects/trading/orchestrator/logs/shadow_decisions.jsonl")
if not log_path.exists():
    print("Kein Shadow-Log gefunden")
    exit(1)

lines = log_path.read_text().splitlines()
entries = []
for line in lines:
    try:
        entries.append(json.loads(line))
    except:
        pass

print(f"Total entries: {len(entries)}")
print(f"Total lines in file: {len(lines)}")

# Schema versions
schemas = {}
for e in entries:
    sv = e.get("schema_version", "unknown")
    schemas[sv] = schemas.get(sv, 0) + 1
print(f"Schema versions: {schemas}")

# Find all decisions across all entries
decisions = []
for e in entries:
    decs = e.get("decisions", [])
    decisions.extend(decs)

print(f"\nTotal decision records: {len(decisions)}")

if decisions:
    accepted = [d.get("confidence", 0) for d in decisions if d.get("verdict") == "ACCEPTED"]
    watch = [d.get("confidence", 0) for d in decisions if d.get("verdict") in ("WATCH_ONLY", "HOLD")]

    print(f"\n--- ACCEPTED decisions: {len(accepted)} ---")
    if accepted:
        print(f"  min={min(accepted):.3f} max={max(accepted):.3f} mean={statistics.mean(accepted):.3f}")
        buckets = {"0.65-0.70": 0, "0.70-0.75": 0, "0.75-0.80": 0, "0.80+": 0}
        for c in accepted:
            if   c < 0.70: buckets["0.65-0.70"] += 1
            elif c < 0.75: buckets["0.70-0.75"] += 1
            elif c < 0.80: buckets["0.75-0.80"] += 1
            else:          buckets["0.80+"]      += 1
        print(f"  Distribution: {buckets}")
        print(f"  Unique values: {sorted(set([round(c,2) for c in accepted]))}")
    else:
        print("  NONE — no ACCEPTED decisions in log")

    print(f"\n--- WATCH_ONLY/HOLD decisions: {len(watch)} ---")
    if watch:
        print(f"  min={min(watch):.3f} max={max(watch):.3f} mean={statistics.mean(watch):.3f}")

    # Old threshold zone
    old_thresh = [d for d in decisions if 0.60 <= d.get("confidence", 0) < 0.65]
    print(f"\nDecisions with conf 0.60-0.65 (old threshold zone): {len(old_thresh)}")
    for d in old_thresh[:8]:
        print(f"  {d.get('pair','?'):15} conf={d.get('confidence',0):.2f} verdict={d.get('verdict','?')}")

    # Last 15 decisions
    print(f"\n--- Last 15 decisions ---")
    for d in decisions[-15:]:
        print(f"  {d.get('pair','?'):15} conf={d.get('confidence',0):.2f} verdict={d.get('verdict','?'):15} timestamp={d.get('timestamp','?')[:19]}")

# Check signal source distribution
if entries:
    watch_signals = [e.get("signal", {}).get("fresh", None) for e in entries if e.get("signal")]
    fresh_count = sum(1 for f in watch_signals if f)
    stale_count = sum(1 for f in watch_signals if f is False)
    print(f"\nSignal freshness: {fresh_count} fresh, {stale_count} stale")
