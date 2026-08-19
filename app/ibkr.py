"""Official Interactive Brokers TWS / IB Gateway — persistent loopback session (2026)."""

from __future__ import annotations

import asyncio
import queue
import socket
import threading
import time
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

_jobs: queue.Queue = queue.Queue()
_worker_once = threading.Lock()
_worker_started = False
_busy = threading.Event()
_ib = None
_ib_port: int | None = None
_ib_meta: dict[str, Any] = {}


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
    return bool(config.IBKR_LIVE) and gateway_is_live()


def allow_live_orders() -> bool:
    return live_cash()


def busy() -> bool:
    return _busy.is_set()


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
        "session": {
            "connected": bool(_ib is not None and getattr(_ib, "isConnected", lambda: False)()),
            "client_id": int(config.IBKR_CLIENT_ID or 7),
            "port": _ib_port,
            "server": _ib_meta.get("server"),
        },
        "open": open_ports,
        "adapter": "persistent-tws-2026",
        "hint": "Live TWS 7496 / paper 7497. API on, Trusted IP 127.0.0.1. Live orders still need confirm_token.",
    }


def _ensure_worker() -> None:
    global _worker_started
    with _worker_once:
        if _worker_started:
            return
        t = threading.Thread(target=_worker, name="ibkr-tws", daemon=True)
        t.start()
        _worker_started = True


def _worker() -> None:
    global _ib, _ib_port, _ib_meta
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from ib_insync import IB

    _ib = IB()
    while True:
        try:
            job, box, ev = _jobs.get(timeout=0.25)
        except queue.Empty:
            if _ib is not None and _ib.isConnected():
                try:
                    _ib.waitOnUpdate(timeout=0.2)
                except Exception:
                    pass
            continue
        _busy.set()
        try:
            p = port()
            cid = int(config.IBKR_CLIENT_ID or 7)
            if not _ib.isConnected() or _ib_port != p:
                if _ib.isConnected():
                    _ib.disconnect()
                _ib.connect(host(), p, clientId=cid, timeout=4)
                _ib_port = p
                try:
                    _ib_meta["server"] = getattr(_ib.client, "serverVersion", lambda: None)()
                except Exception:
                    _ib_meta["server"] = None
            box["r"] = job(_ib)
        except Exception as exc:
            box["e"] = exc
            try:
                if _ib is not None and _ib.isConnected():
                    _ib.disconnect()
            except Exception:
                pass
            _ib_port = None
        finally:
            _busy.clear()
            ev.set()


def _call(fn: Callable[[Any], Any], *, timeout: float = 12.0, block: bool = True) -> Any:
    if not block and busy():
        return None
    _ensure_worker()
    box: dict[str, Any] = {}
    ev = threading.Event()
    _jobs.put((fn, box, ev))
    if not ev.wait(timeout):
        raise TimeoutError("IBKR TWS call timed out")
    if "e" in box:
        raise box["e"]
    return box.get("r")


def _wait_status(ib, trade, seconds: float = 6.0) -> Any:
    deadline = time.time() + seconds
    pending = {"PendingSubmit", "PreSubmitted", "ApiPending", ""}
    while time.time() < deadline:
        st = (trade.orderStatus.status or "").strip()
        if st and st not in pending:
            return trade.orderStatus
        ib.waitOnUpdate(timeout=0.4)
    return trade.orderStatus


def account() -> dict[str, Any]:
    if not port_open(port()):
        return {"error": "TWS/Gateway not listening", **probe()}

    def read(ib) -> dict[str, Any]:
        try:
            ib.reqAccountSummary()
        except Exception:
            pass
        ib.sleep(0.8)
        summary = {}
        try:
            for item in ib.accountSummary():
                summary[item.tag] = item.value
        except Exception:
            pass
        vals = {v.tag: v.value for v in ib.accountValues()}
        merged = {**vals, **summary}
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
        open_tr = []
        try:
            for t in ib.openTrades()[:12]:
                open_tr.append(
                    {
                        "id": t.order.orderId,
                        "symbol": getattr(t.contract, "localSymbol", None) or t.contract.symbol,
                        "status": t.orderStatus.status,
                    }
                )
        except Exception:
            pass
        return {
            "ok": True,
            "broker": "ibkr",
            "adapter": "persistent-tws-2026",
            "live": allow_live_orders(),
            "gateway_live": gateway_is_live(),
            "port": port(),
            "port_name": PORTS.get(port()),
            "accounts": managed[:4],
            "account": (managed[0] if managed else None)
            or merged.get("AccountCode")
            or merged.get("AccountType"),
            "net_liquidation": merged.get("NetLiquidation"),
            "total_cash": merged.get("TotalCashValue"),
            "available_funds": merged.get("AvailableFunds"),
            "buying_power": merged.get("BuyingPower"),
            "cushion": merged.get("Cushion"),
            "positions": positions[:40],
            "open_trades": open_tr,
            "can_trade": True,
            "confirm_for_live": gateway_is_live(),
        }

    try:
        return _call(read, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def option_quotes(specs: list[dict]) -> dict[str, dict]:
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
                ticker = ib.reqMktData(qualified[0], "", True, False)
                ib.sleep(0.7)
                bid = float(ticker.bid or 0) if ticker.bid == ticker.bid and ticker.bid else 0.0
                ask = float(ticker.ask or 0) if ticker.ask == ticker.ask and ticker.ask else 0.0
                last = float(ticker.last or 0) if ticker.last == ticker.last and ticker.last else 0.0
                try:
                    ib.cancelMktData(qualified[0])
                except Exception:
                    pass
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


def _need_confirm(kind: str, payload: dict, *, confirmed: bool, confirm_token: str | None) -> dict | None:
    from . import memory

    if not gateway_is_live() or confirmed:
        return None
    if confirm_token:
        consumed = memory.consume_pending(confirm_token)
        if not consumed or consumed.get("kind") != kind:
            return {"error": "Invalid or expired confirm token. No IBKR order sent."}
        return None
    pending = memory.create_pending(kind, payload, ttl_sec=180)
    try:
        memory.set_fact("ibkr.last_confirm", pending["confirm_token"], source_agent="trader")
    except Exception:
        pass
    return {
        "blocked": True,
        "reason": "LIVE TWS. Reply confirm with this confirm_token to send the order.",
        **pending,
    }


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
    from . import memory

    symbol = (symbol or "").strip().upper()
    right = "C" if str(right).upper().startswith("C") else "P"
    qty = int(qty or 1)
    if qty == 0 or not symbol:
        return {"error": "symbol and non-zero qty required"}
    expiry = (expiry or "").replace("-", "")
    if len(expiry) != 8:
        return {"error": "expiry must be YYYYMMDD"}
    gate = _need_confirm(
        "ibkr_option",
        {"symbol": symbol, "expiry": expiry, "strike": float(strike), "right": right, "qty": qty, "limit": limit},
        confirmed=confirmed,
        confirm_token=confirm_token,
    )
    if gate:
        return gate
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
        order = LimitOrder(side, shares, float(limit), tif="DAY") if limit else MarketOrder(side, shares, tif="DAY")
        trade = ib.placeOrder(qualified[0], order)
        st = _wait_status(ib, trade)
        return {
            "ok": True,
            "broker": "ibkr",
            "adapter": "persistent-tws-2026",
            "live": gateway_is_live(),
            "order_id": trade.order.orderId,
            "symbol": symbol,
            "expiry": expiry,
            "strike": float(strike),
            "right": right,
            "qty": qty,
            "status": st.status,
            "filled": st.filled,
            "avg_fill": st.avgFillPrice,
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
    gate = _need_confirm(
        "ibkr_stock",
        {"symbol": symbol, "side": side, "qty": qty, "limit": limit},
        confirmed=confirmed,
        confirm_token=confirm_token,
    )
    if gate:
        return gate
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
        order = (
            LimitOrder(side.upper(), qty, float(limit), tif="DAY")
            if limit
            else MarketOrder(side.upper(), qty, tif="DAY")
        )
        trade = ib.placeOrder(qualified[0], order)
        st = _wait_status(ib, trade)
        return {
            "ok": True,
            "broker": "ibkr",
            "adapter": "persistent-tws-2026",
            "live": gateway_is_live(),
            "order_id": trade.order.orderId,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "status": st.status,
            "filled": st.filled,
            "avg_fill": st.avgFillPrice,
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
