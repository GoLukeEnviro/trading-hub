#!/usr/bin/env python3
"""Rainbow Producer Acceptance Test — validates the L3 deployment.

Tests:
1. Producer health endpoint
2. Signals endpoint returns data with current timestamps
3. Freshness computation via RainbowClient: fresh=True, age <= threshold
4. Scoring eligibility check (all 5 conditions)
5. Safety invariants: can_execute=False, dry_run_only=True

Usage:
    python3 orchestrator/scripts/rainbow_producer_acceptance_test.py
    python3 orchestrator/scripts/rainbow_producer_acceptance_test.py --base-url http://127.0.0.1:8000
    RAINBOW_PRODUCER_URL=http://localhost:8000 python3 ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC
from datetime import datetime as dt_mod
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────
_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_FRESHNESS_MAX_SECONDS = 900
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = (_SCRIPT_DIR / ".." / "..").resolve()  # orchestrator/scripts/ -> trading-hub root


def _resolve_repo_root() -> Path:
    """Auto-detect repo root from script location.

    Falls back to cwd if the expected structure isn't found.
    """
    candidate = _REPO_ROOT
    if (candidate / "self_improvement_v2").is_dir():
        return candidate
    # Try CWD
    cwd = Path.cwd().resolve()
    if (cwd / "self_improvement_v2").is_dir():
        return cwd
    # Try parent chains of cwd
    for parent in [cwd, *list(cwd.parents)]:
        if (parent / "self_improvement_v2").is_dir():
            return parent
    return _REPO_ROOT  # best guess


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rainbow Producer Acceptance Test",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RAINBOW_PRODUCER_URL", _DEFAULT_BASE_URL),
        help=f"Producer base URL (default: {_DEFAULT_BASE_URL}, env: RAINBOW_PRODUCER_URL)",
    )
    parser.add_argument(
        "--freshness-max-seconds",
        type=int,
        default=_DEFAULT_FRESHNESS_MAX_SECONDS,
        help=f"Freshness threshold in seconds (default: {_DEFAULT_FRESHNESS_MAX_SECONDS})",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_resolve_repo_root(),
        help="Trading-hub repo root (auto-detected by default)",
    )
    return parser.parse_args(argv)


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "✅" if ok else "❌"
    print(f"  {status} {label}")
    if detail:
        print(f"       {detail}")
    return ok


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    base_url = args.base_url.rstrip("/")
    freshness_threshold = args.freshness_max_seconds
    repo_root = args.repo_root.resolve()

    failures = 0

    print("Rainbow Producer Acceptance Test")
    print(f"  base-url:       {base_url}")
    print(f"  freshness-max:  {freshness_threshold}s")
    print(f"  repo-root:      {repo_root}")
    print()

    # ── Health Check ──────────────────────────────────────────────────────
    print("--- Health Check ---")
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read())
        failures += 0 if check("GET /health returns 200", resp.status == 200) else 1
        failures += 0 if check("status is healthy", health.get("status") == "healthy") else 1
        failures += 0 if check("TA collector is running",
                               health.get("collectors", {}).get("ta") == "running") else 1
        print(f"       Uptime: {health.get('uptime_seconds', '?')}s")
        print(f"       Collectors: {health.get('collectors', {})}")
    except Exception as e:
        check("GET /health", False, str(e))
        print("  ❌ Cannot proceed without health check")
        return 1

    # ── Signals Check ─────────────────────────────────────────────────────
    print("\n--- Signals Check ---")
    try:
        req = urllib.request.Request(f"{base_url}/signals/latest")
        with urllib.request.urlopen(req, timeout=10) as resp:
            signals = json.loads(resp.read())

        failures += 0 if check(
            f"GET /signals/latest returns data ({len(signals)} signals)", len(signals) > 0
        ) else 1

        now = dt_mod.now(UTC)
        fresh_count = 0
        stale_count = 0
        freshest_age: float | None = None
        freshest_asset: str | None = None
        freshest_ts: str | None = None

        for sig in signals:
            ts_str = sig.get("timestamp", "")
            if not ts_str:
                stale_count += 1
                continue
            try:
                ts = dt_mod.fromisoformat(ts_str.replace("Z", "+00:00"))
                age = (now - ts).total_seconds()
                if age <= freshness_threshold:
                    fresh_count += 1
                    if freshest_age is None or age < freshest_age:
                        freshest_age = age
                        freshest_asset = sig.get("asset", "?")
                        freshest_ts = ts_str
                else:
                    stale_count += 1
            except (ValueError, TypeError):
                stale_count += 1

        print(f"       Fresh signals (age <= {freshness_threshold}s): {fresh_count}")
        print(f"       Stale signals (age > {freshness_threshold}s):  {stale_count}")
        if freshest_asset:
            print(f"       Freshest: {freshest_asset} age={freshest_age:.0f}s ts={freshest_ts}")

        failures += 0 if check(
            f"Has fresh signals (age <= {freshness_threshold}s)", fresh_count > 0
        ) else 1

    except Exception as e:
        check("GET /signals/latest", False, str(e))
        return 1

    # ── Freshness / Scoring Eligibility ───────────────────────────────────
    print("\n--- Freshness / Scoring Eligibility Check ---")
    si_v2_src = repo_root / "self_improvement_v2" / "src"
    if si_v2_src.is_dir():
        sys.path.insert(0, str(si_v2_src))
    else:
        # Fallback: hardcoded path for VPS
        vps_path = Path("/home/hermes/projects/trading/self_improvement_v2/src")
        if vps_path.is_dir():
            sys.path.insert(0, str(vps_path))
        else:
            check("SI v2 source path found", False, f"Not found at {si_v2_src} or {vps_path}")
            return 1

    from si_v2.rainbow.client import RainbowClientConfig, RainbowSignalProviderClient  # type: ignore[import-untyped]

    config = RainbowClientConfig(
        enabled=True,
        mode="read_only",
        base_url=base_url,
        endpoint_path="/signals/latest",
        timeout_seconds=10,
    )
    client = RainbowSignalProviderClient.from_config(config)
    result = client.get_latest_signals()

    failures += 0 if check("Rainbow client SUCCESS", result.source == "read_only") else 1
    failures += 0 if check(f"Signals count >= 1 ({result.count})", result.count >= 1) else 1
    failures += 0 if check(f"No errors ({len(result.errors)})", len(result.errors) == 0) else 1

    import contextlib

    if result.signals:
        parsed_timestamps: list[dt_mod] = []
        for envelope in result.signals:
            ts_raw = envelope.get("timestamp_utc", "")
            if ts_raw:
                with contextlib.suppress(ValueError, TypeError):
                    parsed_timestamps.append(dt_mod.fromisoformat(ts_raw.replace("Z", "+00:00")))

        if parsed_timestamps:
            now_utc = dt_mod.now(UTC)
            freshest = max(parsed_timestamps)
            age_secs = int((now_utc - freshest).total_seconds())
            is_fresh = age_secs <= freshness_threshold

            failures += 0 if check(
                f"fresh={is_fresh}, age={age_secs}s, threshold={freshness_threshold}s", is_fresh
            ) else 1

            scoring = (
                result.source in ("read_only", "live")
                and result.count >= 1
                and len(result.errors) == 0
                and is_fresh
            )
            failures += 0 if check(f"Scoring eligible: {scoring}", scoring) else 1
            if not scoring:
                print("       Conditions:")
                print(f"         source in read_only/live: {result.source in ('read_only', 'live')} (={result.source})")
                print(f"         count >= 1: {result.count >= 1} (={result.count})")
                print(f"         errors == 0: {len(result.errors) == 0} (={len(result.errors)})")
                print(f"         fresh: {is_fresh} (age={age_secs}s)")

    # ── Safety Invariants ─────────────────────────────────────────────────
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

    check(
        f"can_execute=False + dry_run_only=True on all ({safety_ok}/{safety_n})",
        safety_ok == safety_n > 0,
    )
    failures += 0 if (safety_ok == safety_n > 0) else 1

    # ── Verdict ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    verdict = "GREEN ✅" if failures == 0 else f"RED ❌ ({failures} failure(s))"
    print(f"Verdict: {verdict}")
    print(f"{'=' * 50}\n")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
