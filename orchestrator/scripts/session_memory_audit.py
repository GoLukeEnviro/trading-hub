#!/usr/bin/env python3
"""
Session-Start Memory Audit — lightweight fact extraction trigger.

Runs periodically (every 4h) to:
1. Check Holographic DB health (integrity, fact count, recent activity)
2. Count facts added since last run
3. Report summary for session context injection

This is NOT Dream Mode — no mutation, no consolidation.
Pure read-only health check + activity summary.
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

FACTS_DB = Path("/home/hermes/.hermes/shared-memory/holographic/memory_store.db")
STATE_FILE = Path("/home/hermes/.hermes/shared-memory/holographic/memory_store.db").parent / "session_audit_state.json"


def main():
    if not FACTS_DB.exists():
        print("SESSION-AUDIT FAIL: Facts DB missing")
        sys.exit(1)

    conn = sqlite3.connect(f"file:{FACTS_DB}?mode=ro", uri=True)

    # Integrity
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

    # Total facts
    total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    # Facts in last 4h
    recent_4h = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE created_at > datetime('now','-4 hours')"
    ).fetchone()[0]

    # Facts in last 24h
    recent_24h = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE created_at > datetime('now','-24 hours')"
    ).fetchone()[0]

    # Last fact timestamp
    last_fact = conn.execute(
        "SELECT MAX(created_at) FROM facts"
    ).fetchone()[0]

    # Category breakdown
    cats = conn.execute(
        "SELECT category, COUNT(*) FROM facts GROUP BY category"
    ).fetchall()

    # HRR dimension
    vec = conn.execute(
        "SELECT length(hrr_vector) FROM facts WHERE length(hrr_vector)>0 LIMIT 1"
    ).fetchone()

    # Recent facts preview (last 5)
    recent_facts = conn.execute('''
        SELECT fact_id, substr(content,1,80), category, trust_score, created_at
        FROM facts ORDER BY created_at DESC LIMIT 5
    ''').fetchall()

    conn.close()

    # Load previous state for delta calculation
    prev_total = total
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
            prev_total = prev.get("total_facts", total)
        except Exception:
            pass

    delta = total - prev_total

    # Save state
    STATE_FILE.write_text(json.dumps({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "total_facts": total,
    }))

    # Output
    hrr_dim = vec[0] // 8 if vec else 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"MEMORY AUDIT — {now}")
    print(f"Integrity: {integrity}")
    print(f"Total facts: {total} (+{delta} since last audit)")
    print(f"Recent 4h: {recent_4h} | 24h: {recent_24h}")
    print(f"HRR dim: {hrr_dim}")
    print(f"Last fact: {last_fact}")
    print()
    print("Categories:")
    for cat, count in cats:
        print(f"  {cat}: {count}")
    print()

    if recent_facts:
        print("Latest facts:")
        for fid, content, cat, trust, ts in recent_facts:
            print(f"  [{fid}] {ts} | {cat} | trust={trust} | {content}")

    # Health assessment
    issues = []
    if integrity != "ok":
        issues.append("INTEGRITY CHECK FAILED")
    if hrr_dim != 0 and hrr_dim != 1024:
        issues.append(f"HRR dim mismatch: {hrr_dim} != 1024")
    if recent_24h == 0:
        issues.append("NO new facts in 24h — auto_extract may be broken")

    if issues:
        print()
        print("ISSUES:")
        for i in issues:
            print(f"  ! {i}")
    else:
        print()
        print("Health: OK")


if __name__ == "__main__":
    main()
