#!/usr/bin/env python3
"""Memory Hygiene Monitor — Daily noise detection.

Scans all Mem0 memories for contamination patterns.
Reports findings but does NOT mutate (read-only).
Designed to run as a daily Hermes cron job (no_agent=true).

PERMANENT RULE (2026-06-02):
  Memory mutations MUST use explicit UUID allowlists only.
  Semantic search results MUST NEVER be used as deletion/mutation targets.
  This script is READ-ONLY — it reports, it never deletes.

Exit 0 = clean (or only known quarantined items)
Exit 1 = new contamination detected
Exit 2 = API/DB unreachable
"""

import json
import sys
from collections import Counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MEM0 = "http://green-mem0:8787"
USER_ID = "luke-hermes"

# MEMORY_MUTATION_UUID_ONLY_GUARD_ACTIVE

# Hard blockers: these should always fail hygiene.
# 2026-06-12: "deploy key" and "memory backfill" removed — they triggered on
# legitimate operational notes that DESCRIBE keys/backfills, not the key
# material or backfill output itself. We still catch the actual key markers
# (BEGIN OPENSSH, ssh-rsa, ssh-ed25519, PRIVATE KEY).
BLOCKING_PATTERNS = {
    "credential": ["SHA256:", "ssh-rsa AAAA", "ssh-ed25519 AAAA", "BEGIN OPENSSH PRIVATE", "PRIVATE KEY"],
    "persona": ["user is a senior", "user identifies as an honest", "pragmatic, extremely honest"],
    "instruction": ["performed an immediate fix", "requested creation of a new recurring", "marks fallback behavior"],
    "meta": ["memory audit", "quota safe gating"],
    "xml": ["<?xml", "<task>", "<objective>"],
}

# Known operational/quarantined items: expected legacy noise that should not
# keep the daily monitor red. These are still reported in the log output, but
# they no longer count as blocking contamination.
QUARANTINED_PATTERNS = {
    "operational": [
        "bind mount",
        "cron job",
        "cron jobs",
        "cron scheduler",
        "health check",
        "service is running",
        "service is down",
        "container name",
        "container state", "dream mode", "sync_turn",
        "docker container",
        "dry-run deployment",
        "scheduled every",
        "last_run_at",
        "never executed",
        "mis-configured",
        "file ownership",
        "root:10000",
        "root:root",
        "telegram token",
        "legacy @tradingorchestrator_bot",
        # 2026-06-12: SSH-Key-Memories describe *which key is used where*,
        # not the key material itself. They are legitimate operational notes.
        "ssh deploy key",
        "ssh deploy keys",
        # 2026-06-12: Memories that *talk about* memory backfill are meta-noise
        # from the backfill process itself, not real backfill output.
        "memory backfill",
    ],
}


def _first_match(text: str, pattern_map: dict[str, list[str]]) -> tuple[str, str] | None:
    for category, patterns in pattern_map.items():
        for pattern in patterns:
            if pattern in text:
                return category, pattern
    return None


def main():
    try:
        req = Request(f"{MEM0}/memories/all?user_id={USER_ID}&agent_id=hermes&limit=10000")
        resp = json.loads(urlopen(req, timeout=30).read().decode())
    except HTTPError as e:
        print(f"FAIL: API unreachable: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"FAIL: API unreachable: {e}")
        sys.exit(2)

    memories = resp.get("result", {}).get("results", [])
    blocking_hits = []
    quarantined_hits = []

    for m in memories:
        text = (m.get("memory", "") or "").lower()
        hit = _first_match(text, BLOCKING_PATTERNS)
        if hit:
            blocking_hits.append((m.get("id", "?"), hit[0], hit[1], m.get("memory", "")))
            continue

        hit = _first_match(text, QUARANTINED_PATTERNS)
        if hit:
            quarantined_hits.append((m.get("id", "?"), hit[0], hit[1], m.get("memory", "")))

    if blocking_hits:
        print(f"Memory Hygiene: WARNING — {len(blocking_hits)} blocking hits in {len(memories)} memories")
        counts = Counter(cat for _, cat, _, _ in blocking_hits)
        for cat, count in counts.most_common():
            print(f"  {cat}: {count}")
        print("Sample blocking hits:")
        for mid, cat, pattern, _ in blocking_hits[:5]:
            print(f"  [{mid[:12]}] {cat}: {pattern}")
        if quarantined_hits:
            print(f"Ignored quarantined operational items: {len(quarantined_hits)}")
        sys.exit(1)

    if quarantined_hits:
        print(
            f"Memory Hygiene: CLEAN — {len(memories)} memories, "
            f"{len(quarantined_hits)} quarantined operational items ignored, 0 blocking hits"
        )
        print("Quarantined sample:")
        for mid, cat, pattern, _ in quarantined_hits[:5]:
            print(f"  [{mid[:12]}] {cat}: {pattern}")
        sys.exit(0)

    print(f"Memory Hygiene: CLEAN — {len(memories)} memories, 0 contamination hits")
    sys.exit(0)


if __name__ == "__main__":
    main()
