#!/usr/bin/env python3
"""
MCP Bitget CLI — Einfacher, zuverlässiger CLI für Paper-Trading.
Liest Portfolio aus State-Datei (kein MCP-Connection-Problem).
Startet MCP-Tool-Calls via frischer Subprocess-Verbindung.

Usage:
  python3 mcp_cli.py balance [USDT]
  python3 mcp_cli.py positions [symbol]
  python3 mcp_cli.py ticker SYMBOL
  python3 mcp_cli.py portfolio          # raw state file
  python3 mcp_cli.py order sell|buy SYMBOL amount [market|limit] [price]
"""

import json, sys, os, subprocess, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER = os.path.join(SCRIPT_DIR, "bitget_mcp_server.py")
PORTFOLIO_FILE = "/home/hermes/projects/trading/orchestrator/logs/mcp/bitget_mcp_portfolio.json"


def read_portfolio_raw():
    """Direct file read — zero latency, no MCP dependency."""
    try:
        if not os.path.exists(PORTFOLIO_FILE):
            return {"error": f"Portfolio file not found: {PORTFOLIO_FILE}"}
        return json.loads(open(PORTFOLIO_FILE).read())
    except Exception as e:
        return {"error": f"Failed to read portfolio: {e}"}


def cmd_balance(args):
    p = read_portfolio_raw()
    if "error" in p:
        print(json.dumps(p, indent=2))
        return

    bal = p.get("balance_usdt", 0)
    margin = round(sum(v.get("margin", 0) for v in p.get("positions", {}).values()), 4)
    upnl = round(_calc_upnl(p), 4)
    equity = round(bal + upnl, 2)

    print(json.dumps({
        "currency": args[0] if args else "USDT",
        "free": bal,
        "margin_locked": margin,
        "upnl": upnl,
        "equity": equity,
        "total_positions": len(p.get("positions", {})),
        "paper_mode": True, "dry_run": True,
    }, indent=2))


def _fetch_mark(symbol, fallback=0.0):
    """Fetch mark price via ccxt direct."""
    import ccxt
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
        ticker = ex.fetch_ticker(symbol)
        return ticker["last"]
    except Exception:
        return fallback


def _calc_upnl(p):
    """uPnL via direct ccxt ticker."""
    total = 0.0
    for sym, pos in p.get("positions", {}).items():
        entry = pos.get("entry_price", 0)
        size = pos.get("size", 0)
        mark = _fetch_mark(sym, fallback=entry)
        if pos.get("side") == "short":
            total += (entry - mark) * size
        else:
            total += (mark - entry) * size
    return total


def cmd_positions(args):
    p = read_portfolio_raw()
    if "error" in p:
        print(json.dumps(p, indent=2))
        return

    result = []
    for sym, pos in p.get("positions", {}).items():
        if pos.get("size", 0) <= 0:
            continue
        entry = pos.get("entry_price", 0)
        mark = _fetch_mark(sym, fallback=entry)
        side = pos.get("side", "long")
        upnl = round((entry - mark) * pos["size"] * (1 if side == "short" else -1), 2)
        liq = round(entry * (1.05 if side == "short" else 0.95), 2)

        result.append({
            "symbol": sym, "side": side, "size": pos["size"],
            "entry_price": entry, "mark_price": round(mark, 2),
            "unrealized_pnl": upnl, "margin_used": pos.get("margin", 0),
            "liquidation_price": liq, "paper_mode": True, "dry_run": True,
        })

    print(json.dumps(result, indent=2))


def cmd_ticker(args):
    if not args:
        print(json.dumps({"error": "symbol required"}), indent=2)
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
            "symbol": symbol, "last": t["last"],
            "bid": t.get("bid"), "ask": t.get("ask"),
            "high": t.get("high"), "low": t.get("low"),
            "volume": t.get("baseVolume"), "paper_mode": True,
        }, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def cmd_portfolio(_):
    p = read_portfolio_raw()
    # Clean trade_log for display (only show summary)
    if "trade_log" in p:
        p["trade_log"] = f"{len(p['trade_log'])} entries (use --verbose to see)"
    print(json.dumps(p, indent=2))


def cmd_order(args):
    if len(args) < 3:
        print(json.dumps({"error": "Usage: order sell|buy SYMBOL amount [type] [price]"}), indent=2)
        return
    side, symbol, amount = args[0], args[1], float(args[2])
    order_type = args[3] if len(args) > 3 else "market"
    price = float(args[4]) if len(args) > 4 else None

    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import stdio_client
        import asyncio

        async def place():
            async with stdio_client(["/usr/bin/python3", MCP_SERVER]) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("place_order", {
                        "symbol": symbol, "side": side,
                        "amount": amount, "order_type": order_type,
                        "price": price,
                    })
                    return result.content[0].text

        raw = asyncio.run(place())
        try:
            parsed = json.loads(raw)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(raw)
    except Exception as e:
        print(json.dumps({"error": f"Order failed: {e}"}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    dispatcher = {
        "balance": cmd_balance, "bal": cmd_balance, "b": cmd_balance,
        "positions": cmd_positions, "pos": cmd_positions, "p": cmd_positions,
        "ticker": cmd_ticker, "tick": cmd_ticker, "t": cmd_ticker,
        "portfolio": cmd_portfolio, "port": cmd_portfolio,
        "order": cmd_order, "ord": cmd_order, "o": cmd_order,
        "buy": lambda a: cmd_order(["buy", a[0], a[1]] + (a[2:] if len(a) > 2 else [])),
        "sell": lambda a: cmd_order(["sell", a[0], a[1]] + (a[2:] if len(a) > 2 else [])),
    }

    handler = dispatcher.get(cmd)
    if not handler:
        print(json.dumps({"error": f"Unknown: {cmd}"}))
        print(__doc__)
        sys.exit(1)
    handler(args)
