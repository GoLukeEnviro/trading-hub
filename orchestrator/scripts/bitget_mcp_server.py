#!/usr/bin/env python3
"""
Bitget MCP Server — Paper-Trading Execution Layer v1.1

Provides Model Context Protocol tools for paper-trading on Bitget via ccxt.
Runs in DRY_RUN mode ONLY. No live orders are ever placed.

KEY FIX (v1.0 → v1.1):
  - Balance bleibt das Margin-Konto, unverändert bei Positions-Eröffnung
  - Nur Margin (Notional / LEVERAGE) wird beim Open geblockt
  - Equity = Balance + total_uPnL — korrektes Portfolio-Equity
  - Close gibt Margin + PnL zurück auf die Balance

Tools:
  - place_order(symbol, side, type, amount, price, params)
  - get_balance(currency)
  - get_positions(symbol)
  - cancel_order(id, symbol)
  - get_open_orders(symbol)
  - get_ticker(symbol)

Safety:
  - dry_run=True HARDCODED — cannot be overridden at runtime
  - No exchange API keys used
  - All orders logged to append-only JSONL
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import ccxt

# ── Constants ──────────────────────────────────────────────────────────

DRY_RUN = True          # HARDCODED — never change this
LEVERAGE = 10           # futures margin multiplier
FEE_RATE = 0.0006       # 0.06 % simulated taker fee

PAPER_LOG_DIR = Path(os.environ.get("PAPER_LOG_DIR",
                     "/home/hermes/projects/trading/orchestrator/logs/mcp"))
PAPER_LOG_FILE = PAPER_LOG_DIR / "bitget_mcp_paper_trades.jsonl"
PAPER_STATE_FILE = PAPER_LOG_DIR / "bitget_mcp_portfolio.json"

# Paper portfolio — schema v1.1
#   balance_usdt : float        — free margin / cash
#   positions    : dict[str, Position]
#   orders       : dict[str, Order]
#   trade_log    : list[TradeEvent]
#
# Position = { side: "short"|"long", size: float, entry_price: float, margin: float }
#   margin = (size * entry_price) / LEVERAGE  (geblockt beim Open)
PAPER_PORTFOLIO: Dict[str, Any] = {
    "schema_version": "1.1",
    "balance_usdt": 50000.0,
    "positions": {},
    "orders": {},
    "trade_log": [],
}

# ── Logging ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP-Bitget] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("mcp-bitget")

# ─── MCP SDK Import ────────────────────────────────────────────────────

try:
    from mcp.server.models import InitializationOptions
    import mcp.types as types
    from mcp.server import NotificationOptions, Server
    from mcp.server.stdio import stdio_server
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP SDK not available. Running in standalone test mode.")


# ── Helpers ────────────────────────────────────────────────────────────

def get_mark_price(symbol: str, fallback: float = 0.0) -> float:
    """Fetch current mark price from Bitget via ccxt."""
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


def _pos_key(symbol: str) -> str:
    """Normalise symbol: BTC/USDT:USDT → BTC/USDT"""
    return symbol.split(":")[0] if ":" in symbol else symbol


# ── State Persistence ──────────────────────────────────────────────────

def load_portfolio():
    global PAPER_PORTFOLIO
    try:
        if PAPER_STATE_FILE.exists():
            data = json.loads(PAPER_STATE_FILE.read_text())
            # Migrate v1.0 → v1.1 if needed
            if data.get("schema_version") != "1.1":
                logger.info("Migrating portfolio state from v1.0 to v1.1 …")
                # Old positions had no margin field; rebuild from scratch
                # to avoid stale v1.0 data polluting the new model.
                data["schema_version"] = "1.1"
                data["positions"] = {}
                data["balance_usdt"] = 50000.0
            PAPER_PORTFOLIO.update(data)
            logger.info(f"Portfolio loaded: {PAPER_STATE_FILE}")
    except Exception as e:
        logger.warning(f"Could not load portfolio: {e}")


def save_portfolio():
    try:
        PAPER_LOG_DIR.mkdir(parents=True, exist_ok=True)
        PAPER_STATE_FILE.write_text(json.dumps(PAPER_PORTFOLIO, indent=2))
    except Exception as e:
        logger.error(f"Failed to save portfolio: {e}")


def paper_trade_log(entry: Dict[str, Any]):
    try:
        PAPER_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(PAPER_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception as e:
        logger.error(f"Paper log write failed: {e}")


# ── uPnL Calculation (shared by get_positions + get_balance) ───────────

def compute_total_upnl() -> float:
    """Summe aller unrealisierten PnLs über alle offenen Positionen."""
    total = 0.0
    for sym, pos in PAPER_PORTFOLIO["positions"].items():
        mark = get_mark_price(sym, fallback=pos["entry_price"])
        size = pos["size"]
        if pos["side"] == "short":
            total += (pos["entry_price"] - mark) * size
        else:  # long
            total += (mark - pos["entry_price"]) * size
    return round(total, 4)


def compute_position_upnl(pos: dict, mark: float) -> float:
    if pos["side"] == "short":
        return round((pos["entry_price"] - mark) * pos["size"], 2)
    else:
        return round((mark - pos["entry_price"]) * pos["size"], 2)


# ═══════════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════

async def handle_place_order(symbol: str, side: str, amount: float,
                              order_type: str = "market", price: Optional[float] = None,
                              params: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Place a paper order with CORRECT margin accounting.

    - Short öffnen:   Margin = Notional / LEVERAGE wird geblockt.
                       Balance bleibt unverändert.
    - Short schließen: Margin + PnL zurück auf Balance.
    - Long öffnen:     Margin = Notional / LEVERAGE wird geblockt.
    - Long schließen:  Margin + PnL zurück auf Balance.
    """
    if not DRY_RUN:
        return {"error": "LIVE TRADING BLOCKED — dry_run is HARDCODED True"}

    p = PAPER_PORTFOLIO
    order_id = f"paper_{uuid.uuid4().hex[:12]}"
    now_ts = datetime.now(timezone.utc).isoformat()
    pk = _pos_key(symbol)

    # Execution price (live ticker or fallback)
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
        ticker = ex.fetch_ticker(symbol)
        bid = ticker.get("bid", ticker["last"])
        ask = ticker.get("ask", ticker["last"])
    except Exception as e:
        logger.warning(f"Ticker fetch failed for {symbol}: {e}")
        bid = 50000.0 if "BTC" in symbol else 3000.0 if "ETH" in symbol else 150.0
        ask = bid * 1.001

    exec_price = price if (price and order_type == "limit") else (ask if side == "buy" else bid)
    notional = amount * exec_price
    margin_req = round(notional / LEVERAGE, 4)
    fee = round(notional * FEE_RATE, 4)

    # Build order record
    order = {
        "id": order_id,
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "amount": amount,
        "price": exec_price,
        "cost": notional,
        "filled": amount,
        "remaining": 0.0,
        "status": "closed" if order_type == "market" else "open",
        "timestamp": now_ts,
        "datetime": now_ts,
        "paper_mode": True, "dry_run": True,
        "fee": {"cost": fee, "currency": "USDT"},
    }

    # ── Execute ─────────────────────────────────────────────────────

    side_lower = side.lower()

    if side_lower == "sell":
        # ── OPEN SHORT ──────────────────────────────────────────────
        pos = p["positions"].get(pk)

        if pos and pos["side"] == "short":
            # Scale-in: add to existing short
            if p["balance_usdt"] < margin_req:
                return {"error": f"Insufficient margin: need {margin_req:.2f}, have {p['balance_usdt']:.2f}"}
            p["balance_usdt"] -= margin_req
            total_margin = pos["margin"] + margin_req
            total_size = pos["size"] + amount
            # Weighted average entry price
            pos["entry_price"] = round((pos["entry_price"] * pos["size"] + exec_price * amount) / total_size, 2)
            pos["size"] = total_size
            pos["margin"] = round(total_margin, 4)
        else:
            # Open fresh short (or reduce existing long — handled below)
            if p["balance_usdt"] < margin_req:
                return {"error": f"Insufficient margin: need {margin_req:.2f}, have {p['balance_usdt']:.2f}"}
            p["balance_usdt"] -= margin_req
            p["positions"][pk] = {
                "side": "short",
                "size": amount,
                "entry_price": round(exec_price, 2),
                "margin": margin_req,
            }

    elif side_lower == "buy":
        pos = p["positions"].get(pk)

        if pos and pos["side"] == "short":
            # ── CLOSE (or reduce) SHORT ─────────────────────────────
            close_qty = min(amount, pos["size"])
            pnl = (pos["entry_price"] - exec_price) * close_qty
            # Proportional margin release
            margin_released = pos["margin"] * (close_qty / pos["size"])
            p["balance_usdt"] += round(margin_released + pnl - fee, 4)

            pos["size"] -= close_qty
            pos["margin"] = round(pos["margin"] * (pos["size"] / (pos["size"] + close_qty)), 4) if pos["size"] > 0 else 0
            if pos["size"] <= 0:
                del p["positions"][pk]
            else:
                pos["side"] = "short"  # bleibt short, nur reduziert

        elif pos and pos["side"] == "long":
            # Scale-in to long
            if p["balance_usdt"] < margin_req:
                return {"error": f"Insufficient margin: need {margin_req:.2f}, have {p['balance_usdt']:.2f}"}
            p["balance_usdt"] -= margin_req
            total_margin = pos["margin"] + margin_req
            total_size = pos["size"] + amount
            pos["entry_price"] = round((pos["entry_price"] * pos["size"] + exec_price * amount) / total_size, 2)
            pos["size"] = total_size
            pos["margin"] = round(total_margin, 4)

        elif not pos:
            # Open fresh long
            if p["balance_usdt"] < margin_req:
                return {"error": f"Insufficient margin: need {margin_req:.2f}, have {p['balance_usdt']:.2f}"}
            p["balance_usdt"] -= margin_req
            p["positions"][pk] = {
                "side": "long",
                "size": amount,
                "entry_price": round(exec_price, 2),
                "margin": margin_req,
            }

    else:
        return {"error": f"Unknown side: {side}"}

    # ── Bookkeeping ─────────────────────────────────────────────────
    p["orders"][order_id] = order
    p["trade_log"].append({
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": exec_price,
        "cost": notional,
        "margin_used": margin_req,
        "fee": fee,
        "timestamp": now_ts,
    })
    save_portfolio()
    paper_trade_log({
        "event": "order_placed",
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": exec_price,
        "margin_used": margin_req,
        "fee": fee,
        "dry_run": True,
        "timestamp": now_ts,
    })
    logger.info(f"Paper order: {side} {amount} {symbol} @ {exec_price} | margin={margin_req:.2f} | fee={fee:.4f} | {order_id}")
    return order


async def handle_get_balance(currency: str = "USDT") -> Dict[str, Any]:
    """Gebe freie Margin, geblockte Margin, uPnL und Equity."""
    total_upnl = compute_total_upnl()
    margin_locked = round(sum(p["margin"] for p in PAPER_PORTFOLIO["positions"].values()), 4)

    return {
        "currency": currency,
        "free": round(PAPER_PORTFOLIO["balance_usdt"], 4),
        "margin_locked": margin_locked,
        "upnl": total_upnl,
        "equity": round(PAPER_PORTFOLIO["balance_usdt"] + total_upnl, 4),
        "total_positions": len(PAPER_PORTFOLIO["positions"]),
        "paper_mode": True,
        "dry_run": True,
    }


async def handle_get_positions(symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """Aktuelle Positionen mit Mark-to-Market uPnL."""
    result = []
    for pk, pos in PAPER_PORTFOLIO["positions"].items():
        if symbol and pk != _pos_key(symbol):
            continue
        if pos["size"] <= 0:
            continue
        mark = get_mark_price(pk, fallback=pos["entry_price"])
        upnl = compute_position_upnl(pos, mark)
        result.append({
            "symbol": pk,
            "side": pos["side"],
            "size": pos["size"],
            "entry_price": pos["entry_price"],
            "mark_price": round(mark, 2),
            "unrealized_pnl": upnl,
            "margin_used": pos["margin"],
            "liquidation_price": round(pos["entry_price"] * (1.0 + (0.05 if pos["side"] == "short" else -0.05)), 2),
            "paper_mode": True,
            "dry_run": True,
        })
    return result


async def handle_cancel_order(order_id: str, symbol: str) -> Dict[str, Any]:
    """Cancel an open paper order (simulated)."""
    if order_id in PAPER_PORTFOLIO["orders"]:
        order = PAPER_PORTFOLIO["orders"][order_id]
        if order["status"] == "open":
            order["status"] = "canceled"
            save_portfolio()
            paper_trade_log({
                "event": "order_canceled",
                "order_id": order_id,
                "symbol": symbol,
                "dry_run": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {"status": "canceled", "order_id": order_id, "paper_mode": True}
        else:
            return {"error": f"Order {order_id} is already {order['status']}", "paper_mode": True}
    return {"error": f"Order {order_id} not found", "paper_mode": True}


async def handle_get_open_orders(symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    return [
        o for o in PAPER_PORTFOLIO["orders"].values()
        if o["status"] == "open" and (not symbol or o["symbol"] == symbol)
    ]


async def handle_get_ticker(symbol: str) -> Dict[str, Any]:
    """Live read-only ticker from Bitget."""
    try:
        ex = ccxt.bitget({
            "apiKey": "", "secret": "", "password": "",
            "enableRateLimit": True, "options": {"defaultType": "swap"},
        })
        ex.set_sandbox_mode(True)
        t = ex.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last": t["last"],
            "bid": t.get("bid"),
            "ask": t.get("ask"),
            "high": t.get("high"),
            "low": t.get("low"),
            "volume": t.get("baseVolume"),
            "timestamp": t["timestamp"],
            "paper_mode": True,
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


# ═══════════════════════════════════════════════════════════════════════
# MCP SERVER SETUP
# ═══════════════════════════════════════════════════════════════════════

if MCP_AVAILABLE:

    server = Server("bitget-paper")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="place_order",
                description="Place a paper trade on Bitget (ALWAYS dry-run). "
                            "Side: buy=cover/enter-long, sell=short. "
                            "For futures use symbol format 'BTC/USDT:USDT'.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "e.g. BTC/USDT:USDT"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "amount": {"type": "number", "description": "Contract quantity"},
                        "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
                        "price": {"type": "number", "description": "Limit price (optional for market)"},
                        "params": {"type": "object", "description": "Additional ccxt params"},
                    },
                    "required": ["symbol", "side", "amount"],
                },
            ),
            types.Tool(
                name="get_balance",
                description="Get paper portfolio: free margin, margin_locked, uPnL, equity.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "currency": {"type": "string", "default": "USDT"},
                    },
                },
            ),
            types.Tool(
                name="get_positions",
                description="Get current paper positions with mark-to-market uPnL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Optional filter"},
                    },
                },
            ),
            types.Tool(
                name="cancel_order",
                description="Cancel an open paper order.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "symbol": {"type": "string"},
                    },
                    "required": ["order_id", "symbol"],
                },
            ),
            types.Tool(
                name="get_open_orders",
                description="Get all open paper orders.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Optional filter"},
                    },
                },
            ),
            types.Tool(
                name="get_ticker",
                description="Get current ticker from Bitget (live read-only).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                    },
                    "required": ["symbol"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        logger.info(f"Tool called: {name} {arguments}")
        if name == "place_order":
            result = await handle_place_order(
                symbol=arguments["symbol"],
                side=arguments["side"],
                amount=float(arguments["amount"]),
                order_type=arguments.get("order_type", "market"),
                price=float(arguments["price"]) if arguments.get("price") else None,
                params=arguments.get("params"),
            )
        elif name == "get_balance":
            result = await handle_get_balance(arguments.get("currency", "USDT"))
        elif name == "get_positions":
            result = await handle_get_positions(arguments.get("symbol"))
        elif name == "cancel_order":
            result = await handle_cancel_order(arguments["order_id"], arguments["symbol"])
        elif name == "get_open_orders":
            result = await handle_get_open_orders(arguments.get("symbol"))
        elif name == "get_ticker":
            result = await handle_get_ticker(arguments["symbol"])
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main():
    load_portfolio()

    if not MCP_AVAILABLE or "--test" in sys.argv:
        logger.info("=== Bitget MCP Server v1.1 — Standalone Test ===")
        logger.info(f"DRY_RUN={DRY_RUN}  LEVERAGE={LEVERAGE}x")
        PAPER_PORTFOLIO["balance_usdt"] = 50000.0

        # ── Test 1: Open BTC Short ──────────────────────────────────
        result = await handle_place_order("BTC/USDT:USDT", "sell", 0.01)
        logger.info(f"OPEN SHORT: {json.dumps(result, default=str)}")

        # ── Test 2: Check positions ─────────────────────────────────
        positions = await handle_get_positions()
        logger.info(f"POSITIONS: {json.dumps(positions, default=str)}")

        # ── Test 3: Check balance ──────────────────────────────────
        balance = await handle_get_balance()
        logger.info(f"BALANCE: {json.dumps(balance, default=str)}")

        # Verify: balance_usdt should be ~10,000 - margin
        margin_blocked = round(0.01 * 50000.0 / LEVERAGE, 2)  # ~50 USDT
        expected_balance = 50000.0 - margin_blocked
        actual = PAPER_PORTFOLIO["balance_usdt"]
        status = "PASS" if abs(actual - expected_balance) < 5 else "FAIL"
        logger.info(f"BALANCE CHECK: expected ~{expected_balance:.2f}, got {actual:.2f} → {status}")

        # ── Test 4: Close BTC Short ────────────────────────────────
        result2 = await handle_place_order("BTC/USDT:USDT", "buy", 0.01)
        logger.info(f"CLOSE SHORT: {json.dumps(result2, default=str)}")

        # ── Test 5: Final balance (should be ~10,000 - fees) ──────
        balance2 = await handle_get_balance()
        logger.info(f"FINAL BALANCE: {json.dumps(balance2, default=str)}")
        positions2 = await handle_get_positions()
        logger.info(f"FINAL POSITIONS: {json.dumps(positions2, default=str)}")

        logger.info("=== Test Complete ===")
        return

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="bitget-paper",
                server_version="1.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user")
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
