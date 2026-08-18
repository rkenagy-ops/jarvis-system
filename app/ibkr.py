"""Official Interactive Brokers via TWS / IB Gateway. Loopback only."""

from __future__ import annotations

import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import config

PORTS = {
    7497: "TWS paper",
    7496: "TWS live",
    4002: "Gateway paper",
    4001: "Gateway live",
}
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ibkr")
_lock = threading.Lock()


def host() -> str:
    return "127.0.0.1"


def port() -> int:
    if config.IBKR_LIVE:
        return int(config.IBKR_PORT or 7496)
    return int(config.IBKR_PORT or 7497)


def live_cash() -> bool:
    return bool(config.IBKR_LIVE) and config.TRADING_MODE == "live"


def port_open(p: int | None = None) -> bool:
    target = int(p or port())
    try:
        sock = socket.create_connection((host(), target), timeout=1.2)
        sock.close()
        return True
    except OSError:
        return False


def probe() -> dict[str, Any]:
    open_ports = {str(p): desc for p, desc in PORTS.items() if port_open(p)}
    return {
        "ok": bool(open_ports),
        "host": host(),
        "configured_port": port(),
        "live": live_cash(),
        "open": open_ports,
        "hint": "TWS or IB Gateway must be logged in. Edit → Global Config → API → Enable ActiveX and Socket Clients. Trusted IP 127.0.0.1. Paper=7497, live=7496.",
    }


def _call(fn: Callable[[Any], Any], *, timeout: float = 25.0) -> Any:
    def runner() -> Any:
        import asyncio

        from ib_insync import IB

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = IB()
        try:
            ib.connect(host(), port(), clientId=int(config.IBKR_CLIENT_ID or 7), timeout=6)
            return fn(ib)
        finally:
            try:
                if ib.isConnected():
                    ib.disconnect()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    with _lock:
        return _pool.submit(runner).result(timeout=timeout)


def account() -> dict[str, Any]:
    if not port_open():
        return {"error": "TWS/Gateway not listening", **probe()}

    def read(ib) -> dict[str, Any]:
        vals = {v.tag: v.value for v in ib.accountSummary()}
        positions = []
        for p in ib.positions():
            c = p.contract
            positions.append(
                {
                    "symbol": c.localSymbol or c.symbol,
                    "secType": c.secType,
                    "qty": float(p.position),
                    "avg_cost": float(p.avgCost or 0),
                }
            )
        return {
            "ok": True,
            "broker": "ibkr",
            "live": live_cash(),
            "port": port(),
            "account": vals.get("AccountType") or vals.get("AccountCode"),
            "net_liquidation": vals.get("NetLiquidation"),
            "available_funds": vals.get("AvailableFunds"),
            "buying_power": vals.get("BuyingPower"),
            "cushion": vals.get("Cushion"),
            "positions": positions[:40],
        }

    try:
        return _call(read)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def place_option(
    symbol: str,
    expiry: str,
    strike: float,
    right: str = "C",
    qty: int = 1,
    *,
    limit: float | None = None,
    confirm_token: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Buy/sell one option. Live TWS always needs a confirm token."""
    from . import memory

    symbol = (symbol or "").strip().upper()
    right = "C" if str(right).upper().startswith("C") else "P"
    qty = int(qty or 1)
    if qty == 0 or not symbol:
        return {"error": "symbol and non-zero qty required"}
    expiry = (expiry or "").replace("-", "")
    if len(expiry) != 8:
        return {"error": "expiry must be YYYYMMDD"}
    if (live_cash() or port() in {7496, 4001}) and not confirmed:
        if confirm_token:
            consumed = memory.consume_pending(confirm_token)
            if not consumed or consumed.get("kind") != "ibkr_option":
                return {"error": "Invalid or expired confirm token. No IBKR order sent."}
            confirmed = True
        else:
            pending = memory.create_pending(
                "ibkr_option",
                {
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": float(strike),
                    "right": right,
                    "qty": qty,
                    "limit": limit,
                },
                ttl_sec=180,
            )
            return {
                "blocked": True,
                "reason": "Live IBKR option order needs confirm_token. Paper TWS on 7497 does not.",
                **pending,
            }
    if not port_open():
        return {"error": "TWS/Gateway not listening", **probe()}

    def send(ib) -> dict[str, Any]:
        from ib_insync import LimitOrder, MarketOrder, Option

        contract = Option(symbol, expiry, float(strike), right, "SMART")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {"error": f"IBKR could not qualify {symbol} {expiry} {strike}{right}"}
        side = "BUY" if qty > 0 else "SELL"
        shares = abs(qty)
        order = LimitOrder(side, shares, float(limit)) if limit else MarketOrder(side, shares)
        trade = ib.placeOrder(qualified[0], order)
        ib.sleep(1.2)
        st = trade.orderStatus
        return {
            "ok": True,
            "broker": "ibkr",
            "live": live_cash() or port() in {7496, 4001},
            "order_id": trade.order.orderId,
            "symbol": symbol,
            "expiry": expiry,
            "strike": float(strike),
            "right": right,
            "qty": qty,
            "status": st.status,
            "filled": st.filled,
        }

    try:
        out = _call(send, timeout=35.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}
    if out.get("ok"):
        memory.remember(
            f"IBKR {out.get('status')} {qty} {symbol} {expiry} {strike}{right}",
            kind="trade",
            tags=["trade", "ibkr", symbol],
            importance=0.85,
            source_agent="trader",
        )
    return out
