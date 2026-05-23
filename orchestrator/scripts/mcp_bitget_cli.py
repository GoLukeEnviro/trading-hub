#!/usr/bin/env python3
"""
MCP Bitget Paper Trading CLI - Frische stdio-Verbindung pro Aufruf
So umgehen wir den ClosedResourceError im Native-MCP-Client.

Usage:
  python3 mcp_bitget_cli.py balance [USDT]
  python3 mcp_bitget_cli.py positions [symbol]
  python3 mcp_bitget_cli.py ticker BTC/USDT:USDT
  python3 mcp_bitget_cli.py order sell BTC/USDT:USDT 0.01 [market|limit] [price]
  python3 mcp_bitget_cli.py buy BTC/USDT:USDT 0.01 [market]
  python3 mcp_bitget_cli.py sell BTC/USDT:USDT 0.01 [market]
"""

import json
import sys
import os
import subprocess

# ── Config ──────────────────────────────────────────────────────────
MCP_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "bitget_mcp_server.py"
)
PORTFOLIO_FILE = "/home/hermes/projects/trading/orchestrator/logs/mcp/bitget_mcp_portfolio.json"


def call_mcp(method: str, params: dict = None) -> dict:
    """Schickt einen JSON-RPC Request an den MCP-Server via stdio und gibt Antwort zurück."""
    if params is None:
        params = {}

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    proc = subprocess.run(
        ["/usr/bin/python3", MCP_SCRIPT, "--cli"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=15,
        env={**os.environ, "PAPER_LOG_DIR": "/home/hermes/projects/trading/orchestrator/logs/mcp"}
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip() if proc.stderr else ""
        return {"error": f"MCP process exited with code {proc.returncode}: {stderr[:500]}"}

    # Parse response - letzte Zeile ist JSON
    lines = proc.stdout.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return {"error": f"No JSON response found in output: {proc.stdout[:500]}"}


def read_portfolio() -> dict:
    """Liest Portfolio direkt aus der State-Datei (kein MCP nötig)."""
    try:
        if not os.path.exists(PORTFOLIO_FILE):
            return {"error": f"Portfolio file not found: {PORTFOLIO_FILE}"}
        return json.loads(open(PORTFOLIO_FILE).read())
    except Exception as e:
        return {"error": str(e)}


def cmd_balance(args):
    currency = args[0] if args else "USDT"
    portfolio = read_portfolio()
    if "error" in portfolio:
        print(json.dumps(portfolio, indent=2))
        return

    balance = portfolio.get("balance_usdt", 0)
    total_margin = sum(p.get("margin", 0) for p in portfolio.get("positions", {}).values())
    total_upnl = _compute_total_upnl(portfolio)
    equity = round(balance + total_upnl, 2)

    result = {
        "currency": currency,
        "free": balance,
        "margin_locked": round(total_margin, 4),
        "upnl": round(total_upnl, 4),
        "equity": equity,
        "total_positions": len(portfolio.get("positions", {})),
        "paper_mode": True,
        "dry_run": True,
    }
    print(json.dumps(result, indent=2))


def _compute_total_upnl(portfolio) -> float:
    import ccxt
    total = 0.0
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
    except Exception:
        return total

    for sym, pos in portfolio.get("positions", {}).items():
        try:
            ticker = ex.fetch_ticker(sym)
            mark = ticker["last"]
        except Exception:
            mark = pos.get("entry_price", 0)
        size = pos.get("size", 0)
        entry = pos.get("entry_price", 0)
        if pos.get("side") == "short":
            total += (entry - mark) * size
        else:
            total += (mark - entry) * size
    return total


def cmd_positions(args):
    portfolio = read_portfolio()
    if "error" in portfolio:
        print(json.dumps(portfolio, indent=2))
        return

    import ccxt
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
    except Exception:
        ex = None

    result = []
    for sym, pos in portfolio.get("positions", {}).items():
        if pos.get("size", 0) <= 0:
            continue

        entry = pos.get("entry_price", 0)
        if ex:
            try:
                ticker = ex.fetch_ticker(sym)
                mark = ticker["last"]
            except Exception:
                mark = entry
        else:
            mark = entry

        if pos.get("side") == "short":
            upnl = round((entry - mark) * pos["size"], 2)
        else:
            upnl = round((mark - entry) * pos["size"], 2)

        result.append({
            "symbol": sym,
            "side": pos.get("side"),
            "size": pos.get("size"),
            "entry_price": entry,
            "mark_price": round(mark, 2),
            "unrealized_pnl": upnl,
            "margin_used": pos.get("margin", 0),
            "paper_mode": True,
            "dry_run": True,
        })

    print(json.dumps(result, indent=2))


def cmd_ticker(args):
    if not args:
        print(json.dumps({"error": "symbol required"}))
        return
    symbol = args[0]
    
    import ccxt
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
        t = ex.fetch_ticker(symbol)
        print(json.dumps({
            "symbol": symbol,
            "last": t["last"],
            "bid": t.get("bid"),
            "ask": t.get("ask"),
            "high": t.get("high"),
            "low": t.get("low"),
            "volume": t.get("baseVolume"),
            "timestamp": t["timestamp"],
            "paper_mode": True,
        }, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def cmd_order(args):
    # order <side> <symbol> <amount> [type] [price]
    if len(args) < 3:
        print(json.dumps({"error": "Usage: order <side> <symbol> <amount> [type] [price]"}))
        return
    side = args[0]
    symbol = args[1]
    amount = float(args[2])
    order_type = args[3] if len(args) > 3 else "market"
    price = float(args[4]) if len(args) > 4 else None

    # Call via MCP
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client
    from mcp.types import CallToolRequest
    import asyncio

    async def _call():
        import json as _json
        async with stdio_client(
            _json.dumps({
                "command": "/usr/bin/python3",
                "args": [MCP_SCRIPT],
                "env": {"PAPER_LOG_DIR": "/home/hermes/projects/trading/orchestrator/logs/mcp"}
            })
        ) as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.call_tool("place_order", {
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "order_type": order_type,
                    "price": price,
                })
                return result

    try:
        result = asyncio.run(_call())
        print(result)
    except Exception as e:
        print(json.dumps({"error": str(e)}))


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd in ("balance", "bal", "b"):
        cmd_balance(args)
    elif cmd in ("positions", "pos", "p"):
        cmd_positions(args)
    elif cmd in ("ticker", "tick", "t"):
        cmd_ticker(args)
    elif cmd in ("order", "ord", "o"):
        cmd_order(args)
    elif cmd in ("buy",):
        # buy = close short or open long
        cmd_order(["buy", args[0], args[1]] + (args[2:] if len(args) > 2 else []))
    elif cmd in ("sell",):
        # sell = open short or close long
        cmd_order(["sell", args[0], args[1]] + (args[2:] if len(args) > 2 else []))
    elif cmd == "portfolio":
        print(json.dumps(read_portfolio(), indent=2))
    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        print(__doc__)
        sys.exit(1)
