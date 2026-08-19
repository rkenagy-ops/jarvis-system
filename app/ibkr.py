"""Official Interactive Brokers via TWS / IB Gateway. Loopback only."""

from __future__ import annotations

import itertools
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
LIVE_PORTS = {7496, 4001}
PAPER_PORTS = {7497, 4002}
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ibkr")
_lock = threading.Lock()
_cids = itertools.count(80)


def host() -> str:
    return "127.0.0.1"


def port_open(p: int) -> bool:
    try:
        sock = socket.create_connection((host(), int(p)), timeout=0.8)
        sock.close()
        return True
    except OSError:
        return False


def port() -> int:
    """Prefer an actually open TWS socket. Live 7496/4001 when IBKR_LIVE or that's what's running."""
    explicit = int(config.IBKR_PORT or 0)
    if explicit and port_open(explicit):
        return explicit
    live_first = bool(config.IBKR_LIVE) or (explicit in LIVE_PORTS)
    order = [7496, 4001, 7497, 4002] if live_first else [7497, 4002, 7496, 4001]
    for p in order:
        if port_open(p):
            return p
    if explicit:
        return explicit
    return 7496 if config.IBKR_LIVE else 7497


def gateway_is_live() -> bool:
    return port() in LIVE_PORTS


def live_cash() -> bool:
    """True when we are allowed to send real-money IBKR orders."""
    return bool(config.IBKR_LIVE) and gateway_is_live()


def allow_live_orders() -> bool:
    return live_cash()


def busy() -> bool:
    return _lock.locked()


def probe() -> dict[str, Any]:
    open_ports = {str(p): desc for p, desc in PORTS.items() if port_open(p)}
    chosen = port()
    return {
        "ok": bool(open_ports),
        "host": host(),
        "configured_port": chosen,
        "port_name": PORTS.get(chosen, str(chosen)),
        "ibkr_live_flag": bool(config.IBKR_LIVE),
        "gateway_live": gateway_is_live(),
        "live_orders": allow_live_orders(),
        "open": open_ports,
        "hint": "Live TWS port 7496. Paper 7497. Enable API + Trusted IP 127.0.0.1. KEYS → IBKR_LIVE=true for real cash (still confirm).",
    }


def _call(fn: Callable[[Any], Any], *, timeout: float = 12.0, block: bool = True) -> Any:
    def runner() -> Any:
        import asyncio

        from ib_insync import IB

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = IB()
        cid = next(_cids) % 40 + 80
        try:
            ib.connect(host(), port(), clientId=cid, timeout=4)
            ib.sleep(0.4)
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

    if not block:
        if not _lock.acquire(blocking=False):
            return None
        try:
            return _pool.submit(runner).result(timeout=timeout)
        finally:
            _lock.release()
    with _lock:
        return _pool.submit(runner).result(timeout=timeout)


def account() -> dict[str, Any]:
    if not port_open(port()):
        return {"error": "TWS/Gateway not listening", **probe()}

    def read(ib) -> dict[str, Any]:
        ib.sleep(0.6)
        vals = {v.tag: v.value for v in ib.accountValues()}
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
        managed = []
        try:
            managed = list(ib.managedAccounts())
        except Exception:
            pass
        return {
            "ok": True,
            "broker": "ibkr",
            "live": allow_live_orders(),
            "gateway_live": gateway_is_live(),
            "port": port(),
            "port_name": PORTS.get(port()),
            "accounts": managed[:4],
            "account": (managed[0] if managed else None) or vals.get("AccountType") or vals.get("AccountCode"),
            "net_liquidation": vals.get("NetLiquidation"),
            "available_funds": vals.get("AvailableFunds"),
            "buying_power": vals.get("BuyingPower"),
            "cushion": vals.get("Cushion"),
            "positions": positions[:40],
            "can_trade": True,
            "confirm_for_live": gateway_is_live(),
        }

    try:
        return _call(read, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def option_quotes(specs: list[dict]) -> dict[str, dict]:
    """Live bid/ask for a few contracts. Empty if TWS is down."""
    if not specs or busy() or not port_open(port()):
        return {}

    def read(ib) -> dict[str, dict]:
        from ib_insync import Option

        out: dict[str, dict] = {}
        for spec in specs[:8]:
            symbol = (spec.get("symbol") or "").upper()
            expiry = str(spec.get("expiry") or spec.get("expiration") or "").replace("-", "")
            try:
                strike = float(spec.get("strike") or 0)
            except (TypeError, ValueError):
                continue
            right = "C" if str(spec.get("right") or spec.get("option_type") or "C").upper().startswith("C") else "P"
            if not symbol or len(expiry) != 8 or strike <= 0:
                continue
            try:
                contract = Option(symbol, expiry, strike, right, "SMART")
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    continue
                ticker = ib.reqMktData(qualified[0], "", False, False)
                ib.sleep(1.0)
                bid = float(ticker.bid or 0) if ticker.bid and ticker.bid == ticker.bid else 0.0
                ask = float(ticker.ask or 0) if ticker.ask and ticker.ask == ticker.ask else 0.0
                last = float(ticker.last or 0) if ticker.last and ticker.last == ticker.last else 0.0
                ib.cancelMktData(qualified[0])
                key = f"{symbol}-{expiry}-{strike:g}{right}"
                mid = (bid + ask) / 2 if bid and ask else last
                out[key] = {"bid": bid, "ask": ask, "last": last, "mid": mid, "source": "ibkr"}
            except Exception:
                continue
        return out

    try:
        out = _call(read, timeout=12.0, block=False)
        return out or {}
    except Exception:
        return {}


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
    if gateway_is_live() and not confirmed:
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
            try:
                memory.set_fact("ibkr.last_confirm", pending["confirm_token"], source_agent="trader")
            except Exception:
                pass
            return {
                "blocked": True,
                "reason": "LIVE TWS. Reply confirm with this confirm_token to send the option order.",
                **pending,
            }
    if config.IBKR_LIVE and not gateway_is_live():
        return {"error": "IBKR_LIVE is on but TWS is paper. Log into live TWS (port 7496) and enable API.", **probe()}
    if not port_open(port()):
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
            "live": gateway_is_live(),
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
        out = _call(send, timeout=15.0)
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


def place_stock(
    symbol: str,
    side: str,
    qty: float,
    *,
    limit: float | None = None,
    confirm_token: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    from . import memory

    symbol = (symbol or "").strip().upper()
    side = (side or "buy").lower()
    qty = float(qty or 0)
    if not symbol or qty <= 0 or side not in {"buy", "sell"}:
        return {"error": "Need symbol, buy/sell, and qty > 0"}
    if gateway_is_live() and not confirmed:
        if confirm_token:
            consumed = memory.consume_pending(confirm_token)
            if not consumed or consumed.get("kind") != "ibkr_stock":
                return {"error": "Invalid or expired confirm token. No IBKR order sent."}
            confirmed = True
        else:
            pending = memory.create_pending(
                "ibkr_stock",
                {"symbol": symbol, "side": side, "qty": qty, "limit": limit},
                ttl_sec=180,
            )
            try:
                memory.set_fact("ibkr.last_confirm", pending["confirm_token"], source_agent="trader")
            except Exception:
                pass
            return {
                "blocked": True,
                "reason": "LIVE TWS. Reply confirm with this confirm_token to send the stock order.",
                **pending,
            }
    if config.IBKR_LIVE and not gateway_is_live():
        return {"error": "IBKR_LIVE is on but TWS is paper. Log into live TWS (port 7496).", **probe()}
    if not port_open(port()):
        return {"error": "TWS/Gateway not listening", **probe()}

    def send(ib) -> dict[str, Any]:
        from ib_insync import LimitOrder, MarketOrder, Stock

        contract = Stock(symbol, "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {"error": f"IBKR could not qualify stock {symbol}"}
        order = LimitOrder(side.upper(), qty, float(limit)) if limit else MarketOrder(side.upper(), qty)
        trade = ib.placeOrder(qualified[0], order)
        ib.sleep(1.2)
        st = trade.orderStatus
        return {
            "ok": True,
            "broker": "ibkr",
            "live": gateway_is_live(),
            "order_id": trade.order.orderId,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "status": st.status,
            "filled": st.filled,
        }

    try:
        out = _call(send, timeout=15.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}
    if out.get("ok"):
        memory.remember(
            f"IBKR {out.get('status')} {side} {qty} {symbol}",
            kind="trade",
            tags=["trade", "ibkr", symbol],
            importance=0.85,
            source_agent="trader",
        )
    return out


def dispatch(action: str = "account", **kwargs: Any) -> dict[str, Any]:
    act = (action or "account").lower()
    if act in {"probe", "status"}:
        return probe()
    if act in {"account", "summary"}:
        return account()
    if act in {"option", "options", "call", "put"}:
        return place_option(
            kwargs.get("symbol") or "",
            kwargs.get("expiry") or "",
            float(kwargs.get("strike") or 0),
            kwargs.get("right") or "C",
            int(kwargs.get("qty") or 1),
            limit=kwargs.get("limit"),
            confirm_token=kwargs.get("confirm_token"),
        )
    if act in {"order", "trade", "stock", "buy", "sell"}:
        return place_stock(
            kwargs.get("symbol") or "",
            kwargs.get("side") or ("buy" if act == "buy" else "sell" if act == "sell" else "buy"),
            float(kwargs.get("qty") or 0),
            limit=kwargs.get("limit"),
            confirm_token=kwargs.get("confirm_token"),
        )
    if kwargs.get("expiry") and kwargs.get("strike"):
        return place_option(
            kwargs.get("symbol") or "",
            kwargs.get("expiry") or "",
            float(kwargs.get("strike") or 0),
            kwargs.get("right") or "C",
            int(kwargs.get("qty") or 1),
            limit=kwargs.get("limit"),
            confirm_token=kwargs.get("confirm_token"),
        )
    if kwargs.get("symbol") and kwargs.get("side"):
        return place_stock(
            kwargs.get("symbol") or "",
            kwargs.get("side") or "buy",
            float(kwargs.get("qty") or 0),
            limit=kwargs.get("limit"),
            confirm_token=kwargs.get("confirm_token"),
        )
    return account()
