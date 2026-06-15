#!/usr/bin/env python3
"""Rainbow Producer Acceptance Test — validates the L3 deployment.

Tests:
1. Producer health endpoint
2. Signals endpoint returns data with current timestamps
3. Freshness computation: fresh=True, age <= 900 seconds
4. Scoring eligibility check
5. Safety invariants: can_execute=False, dry_run_only=True
"""

import json
import sys
import urllib.request
from datetime import UTC, datetime as dt_mod


PRODUCER_URL = "http://127.0.0.1:8000"


def check(label: str, ok: bool, detail: str = ""):
    status = "✅" if ok else "❌"
    print(f"  {status} {label}")
    if detail:
        print(f"       {detail}")
    return ok


def main() -> int:
    failures = 0

    print("\n--- Health Check ---")
    try:
        req = urllib.request.Request(f"{PRODUCER_URL}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read())
        ok = check("GET /health returns 200", resp.status == 200)
        failures += 0 if ok else 1
        ok = check("status is healthy", health.get("status") == "healthy")
        failures += 0 if ok else 1
        ok = check("TA collector is running", health.get("collectors", {}).get("ta") == "running")
        failures += 0 if ok else 1
        print(f"       Uptime: {health.get('uptime_seconds', '?')}s")
        print(f"       Collectors: {health.get('collectors', {})}")
    except Exception as e:
        check("GET /health", False, str(e))
        failures += 1
        print("  ❌ Cannot proceed without health check")
        return 1

    print("\n--- Signals Check ---")
    try:
        req = urllib.request.Request(f"{PRODUCER_URL}/signals/latest")
        with urllib.request.urlopen(req, timeout=10) as resp:
            signals = json.loads(resp.read())

        ok = check(f"GET /signals/latest returns data ({len(signals)} signals)", len(signals) > 0)
        failures += 0 if ok else 1

        now = dt_mod.now(UTC)
        fresh_count = 0
        stale_count = 0
        freshest_age = None
        freshest_asset = None
        freshest_ts = None

        for sig in signals:
            ts_str = sig.get("timestamp", "")
            if not ts_str:
                stale_count += 1
                continue
            try:
                ts = dt_mod.fromisoformat(ts_str.replace("Z", "+00:00"))
                age = (now - ts).total_seconds()
                if age <= 900:
                    fresh_count += 1
                    if freshest_age is None or age < freshest_age:
                        freshest_age = age
                        freshest_asset = sig.get("asset", "?")
                        freshest_ts = ts_str
                else:
                    stale_count += 1
            except (ValueError, TypeError):
                stale_count += 1

        print(f"       Fresh signals (age <= 900s): {fresh_count}")
        print(f"       Stale signals (age > 900s):  {stale_count}")
        if freshest_asset:
            print(f"       Freshest: {freshest_asset} age={freshest_age:.0f}s ts={freshest_ts}")

        ok = check("Has fresh signals (age <= 900s)", fresh_count > 0)
        failures += 0 if ok else 1

    except Exception as e:
        check("GET /signals/latest", False, str(e))
        failures += 1
        return 1

    print("\n--- Freshness / Scoring Eligibility Check ---")
    sys.path.insert(0, "/home/hermes/projects/trading/self_improvement_v2/src")
    from si_v2.rainbow.client import RainbowSignalProviderClient, RainbowClientConfig

    config = RainbowClientConfig(
        enabled=True,
        mode="read_only",
        base_url=PRODUCER_URL,
        endpoint_path="/signals/latest",
        timeout_seconds=10,
    )
    client = RainbowSignalProviderClient.from_config(config)
    result = client.get_latest_signals()

    ok = check("Rainbow client SUCCESS", result.source == "read_only")
    failures += 0 if ok else 1
    ok = check(f"Signals count >= 1 ({result.count})", result.count >= 1)
    failures += 0 if ok else 1
    ok = check(f"No errors ({len(result.errors)})", len(result.errors) == 0)
    failures += 0 if ok else 1

    if result.signals:
        parsed_timestamps = []
        for envelope in result.signals:
            ts_raw = envelope.get("timestamp_utc", "")
            if ts_raw:
                try:
                    parsed_timestamps.append(dt_mod.fromisoformat(ts_raw.replace("Z", "+00:00")))
                except (ValueError, TypeError):
                    pass

        if parsed_timestamps:
            now_utc = dt_mod.now(UTC)
            freshest = max(parsed_timestamps)
            age_secs = int((now_utc - freshest).total_seconds())
            is_fresh = age_secs <= 900

            ok = check(f"fresh={is_fresh}, age={age_secs}s, threshold=900s", is_fresh)
            failures += 0 if ok else 1

            scoring = (
                result.source in ("read_only", "live")
                and result.count >= 1
                and len(result.errors) == 0
                and is_fresh
            )
            ok = check(f"Scoring eligible: {scoring}", scoring)
            failures += 0 if ok else 1
            if not scoring:
                print("       Conditions:")
                print(f"         source in read_only/live: {result.source in ('read_only', 'live')} (={result.source})")
                print(f"         count >= 1: {result.count >= 1} (={result.count})")
                print(f"         errors == 0: {len(result.errors) == 0} (={len(result.errors)})")
                print(f"         fresh: {is_fresh} (age={age_secs}s)")

    print("\n--- Safety Invariants Check ---")
    safety_ok = 0
    safety_n = 0
    for envelope in result.signals:
        actionability = envelope.get("metadata", {}).get("actionability", {})
        can_exec = actionability.get("can_execute", True)
        dry_only = actionability.get("dry_run_only", False)
        safety_n += 1
        if not can_exec and dry_only:
            safety_ok += 1

    ok = check(f"can_execute=False + dry_run_only=True on all ({safety_ok}/{safety_n})",
               safety_ok == safety_n > 0)
    failures += 0 if ok else 1

    print(f"\n{'='*50}")
    verdict = "GREEN ✅" if failures == 0 else f"RED ❌ ({failures} failure(s))"
    print(f"Verdict: {verdict}")
    print(f"{'='*50}\n")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
