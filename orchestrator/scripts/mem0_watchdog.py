#!/usr/bin/env python3
"""
Mem0 Local Stack Watchdog v4.6 — richer Telegram report.
Runs every 2h and emits a compact infra-focused status snapshot.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

MEM0_BASE = os.environ.get("MEM0_BASE_URL", "")
MEM0_CONTAINER = os.environ.get("MEM0_CONTAINER_NAME", "hermes-mem0-local-api")
MEM0_PORT = int(os.environ.get("MEM0_PORT", "8787"))
TIMEOUT = 10
ALERTS = []
CHECKS = {}


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def resolve_mem0_url():
    if MEM0_BASE:
        return MEM0_BASE
    try:
        result = subprocess.run(
            ["docker", "inspect", MEM0_CONTAINER, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ips = [ip.strip() for ip in result.stdout.strip().split() if ip.strip()]
        if ips:
            for ip in ips:
                if ip.startswith("172.18."):
                    return f"http://{ip}:{MEM0_PORT}"
            return f"http://{ips[0]}:{MEM0_PORT}"
    except Exception:
        pass
    return f"http://mem0-local-api:{MEM0_PORT}"


def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def check_api_health(base_url):
    try:
        status, body = http_get(f"{base_url}/health")
        data = json.loads(body)
        CHECKS["api"] = f"ok ({status})"
        CHECKS["backend"] = data.get("backend", "unknown")
        CHECKS["vector_store"] = data.get("vector_store", "unknown")
        CHECKS["embedder"] = f"{data.get('embedder_provider', 'unknown')}/{data.get('embedder_model', 'unknown')}"
        return data
    except Exception as exc:
        CHECKS["api"] = f"FAIL ({type(exc).__name__})"
        ALERTS.append(f"API unreachable: {exc}")
        return None


def check_memory_totals(base_url):
    try:
        _, body = http_get(f"{base_url}/memories/all?user_id=luke-hermes&limit=5000", timeout=30)
        data = json.loads(body)
        results = data.get("result", {}).get("results", [])
        total = len(results)
        CHECKS["total_memories"] = total
        if total < 100:
            ALERTS.append(f"Memory count suspiciously low: {total}")
    except Exception as exc:
        CHECKS["total_memories"] = "FAIL"
        ALERTS.append(f"Memory count check failed: {exc}")


def build_report(base_url):
    status = "ALERT" if ALERTS else "OK"
    suggestions = []
    if ALERTS:
        suggestions.append("Mem0 API/Qdrant sofort prüfen")
    if CHECKS.get("total_memories") == "FAIL":
        suggestions.append("/memories/all Endpoint debuggen")
    if not suggestions:
        suggestions = ["Keine Sofortaktion nötig", "Nur Trend auf Memory-Wachstum beobachten"]

    lines = [
        f"🧠 Mem0 Watchdog — {ts()} | {status}",
        "",
        "PROFITABILITÄT",
        "• n/a — Infra/Memory-Report",
        "",
        "FLEET STATUS",
        f"• API: {CHECKS.get('api', 'unknown')} | backend={CHECKS.get('backend', 'unknown')}",
        f"• Vector: {CHECKS.get('vector_store', 'unknown')} | Embedder: {CHECKS.get('embedder', 'unknown')}",
        "",
        "SIGNAL",
        f"• Base URL: {base_url}",
        f"• total_memories={CHECKS.get('total_memories', 'unknown')}",
        "",
        "SAFETY",
        f"• Alerts: {len(ALERTS)}",
        f"• {'; '.join(ALERTS[:2]) if ALERTS else 'Qdrant + API + embedder erreichbar'}",
        "",
        "VORSCHLÄGE",
    ]
    for item in suggestions[:2]:
        lines.append(f"• {item}")
    return "\n".join(lines)


def main():
    base_url = resolve_mem0_url()
    check_api_health(base_url)
    check_memory_totals(base_url)
    print(build_report(base_url))
    sys.exit(0)


if __name__ == "__main__":
    main()
