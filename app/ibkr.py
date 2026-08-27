"""Official Interactive Brokers TWS / IB Gateway — persistent loopback session (2026)."""

from __future__ import annotations

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
_probe_at = 0.0
_probe_val: dict[str, Any] | None = None


def _ib_names(*names: str) -> tuple:
    """Resolve names from the IBKR client library.

    ib_insync is archived upstream; ib-api-reloaded/ib_async is the maintained fork
    with the same API surface. Prefer ib_async, fall back to ib_insync so existing
    installs keep working untouched.
    """
    try:
        import ib_async as mod  # type: ignore
    except ImportError:  # pragma: no cover - depends on which is installed
        import ib_insync as mod  # type: ignore
    return tuple(getattr(mod, n) for n in names)


def ib_backend() -> str:
    """Which client library is actually in use — surfaced in probe()."""
    try:
        import ib_async  # type: ignore  # noqa: F401

        return "ib_async"
    except ImportError:
        try:
            import ib_insync  # type: ignore  # noqa: F401

            return "ib_insync (archived — pip install ib_async)"
        except ImportError:
            return "none installed"


def host() -> str:
    return "127.0.0.1"


def port_open(p: int) -> bool:
    try:
        sock = socket.create_connection((host(), int(p)), timeout=0.25)
        sock.close()
        return True
    except OSError:
        return False


def tws_state() -> dict[str, Any]:
    """Detect TWS.exe and its window title (Login vs fully loaded)."""
    running = False
    title = ""
    pid = None
    try:
        import csv
        import io
        import subprocess

        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq tws.exe", "/V", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=0x08000000,
        )
        rows = list(csv.reader(io.StringIO(r.stdout or "")))
        for row in rows[1:]:
            if not row or not str(row[0]).lower().startswith("tws"):
                continue
            running = True
            try:
                pid = int(row[1])
            except (IndexError, ValueError):
                pid = None
            title = row[-1] if row else ""
            break
    except Exception:
        pass
    login = running and "login" in (title or "").lower()
    return {
        "process": running,
        "pid": pid,
        "window": title,
        "login_screen": login,
        "path": r"C:\Jts\tws.exe",
    }


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
    return any(port_open(p) for p in LIVE_PORTS)


def live_cash() -> bool:
    return bool(config.IBKR_LIVE) and gateway_is_live()


def allow_live_orders() -> bool:
    return live_cash()


def busy() -> bool:
    return _busy.is_set()


def probe(*, force: bool = False) -> dict[str, Any]:
    global _probe_at, _probe_val
    now = time.time()
    if not force and _probe_val is not None and now - _probe_at < 2.5:
        return _probe_val
    open_ports = {str(p): desc for p, desc in PORTS.items() if port_open(p)}
    chosen = port()
    tws = tws_state()
    gateway_live = any(str(p) in open_ports for p in LIVE_PORTS)
    if open_ports:
        hint = "TWS API is listening. HUD IBKR account can sync. Live orders still need confirm_token."
    elif tws.get("login_screen"):
        hint = "TWS is open on the Login window. Enter username, password, and 2FA. API port 7496 only opens AFTER a full login."
    elif tws.get("process"):
        hint = "TWS is running but the API socket is closed. Edit → Global Configuration → API → Settings: Enable ActiveX and Socket Clients, Socket port 7496, Trusted IPs 127.0.0.1. Apply, then wait until 7496 listens."
    else:
        hint = r"Start C:\Jts\tws.exe, log in LIVE, then enable the API socket on 7496."
    out = {
        "ok": bool(open_ports),
        "host": host(),
        "configured_port": chosen,
        "port_name": PORTS.get(chosen, str(chosen)),
        "ibkr_live_flag": bool(config.IBKR_LIVE),
        "gateway_live": gateway_live,
        "live_orders": bool(config.IBKR_LIVE) and gateway_live,
        "session": {
            "connected": bool(_ib is not None and getattr(_ib, "isConnected", lambda: False)()),
            "client_id": int(config.IBKR_CLIENT_ID or 117),
            "port": _ib_port,
            "server": _ib_meta.get("server"),
        },
        "open": open_ports,
        "adapter": "persistent-tws-2026",
        "tws": tws,
        "tws_running": bool(tws.get("process") or open_ports),
        "tws_path": r"C:\Jts\tws.exe",
        "hint": hint,
    }
    _probe_val = out
    _probe_at = now
    return out


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
    (IB,) = _ib_names("IB")

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
            cid = int(config.IBKR_CLIENT_ID or 117)  # 7 is often TWS Master Client ID and will fail to connect
            if not _ib.isConnected() or _ib_port != p:
                if _ib.isConnected():
                    _ib.disconnect()
                _ib.connect(host(), p, clientId=cid, timeout=6)
                _ib_port = p
                try:
                    _ib_meta["server"] = getattr(_ib.client, "serverVersion", lambda: None)()
                except Exception:
                    _ib_meta["server"] = None
                try:
                    _ib.reqMarketDataType(1 if p in LIVE_PORTS else 3)
                except Exception:
                    pass
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


def _not_listening_error() -> dict[str, Any]:
    info = probe(force=True)
    tws = info.get("tws") or {}
    if tws.get("login_screen"):
        msg = (
            "TWS is sitting on the Login window — that is why IBKR is not syncing. "
            "Finish username, password, and 2FA. The API socket (7496 live / 7497 paper) "
            "does not open until TWS is fully loaded."
        )
    elif tws.get("process"):
        msg = (
            "TWS is running but port 7496 is not listening. In TWS: Edit → Global Configuration "
            "→ API → Settings. Check Enable ActiveX and Socket Clients. Socket port 7496. "
            "Trusted IPs: 127.0.0.1. Uncheck Read-Only API if you want live orders. Apply."
        )
    else:
        msg = (
            r"Trader Workstation is not running. Start C:\Jts\tws.exe, log in LIVE, "
            "wait until the window is fully loaded. API port 7496 must listen."
        )
    return {"error": msg, **info}


def account() -> dict[str, Any]:
    if not any(port_open(p) for p in PORTS):
        return _not_listening_error()

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
            "can_trade": allow_live_orders(),
            "confirm_for_live": gateway_is_live(),
            "permissions": "live-confirm" if allow_live_orders() else "blocked-until-tws-live",
        }

    try:
        return _call(read, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def option_quotes(specs: list[dict]) -> dict[str, dict]:
    if not specs or busy() or not port_open(port()):
        return {}

    def read(ib) -> dict[str, dict]:
        (Option,) = _ib_names("Option")

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


# Order kinds that reduce exposure. The governor never blocks these - a halt must not
# be able to trap a position.
RISK_EXEMPT = frozenset({"ibkr_close", "ibkr_cancel"})


def _estimate_notional(kind: str, payload: dict) -> float:
    """Roughly what this order puts at stake, for the risk gate.

    Deliberately errs high. An option contract is 100 shares, and where no price is
    known we fall back to the strike, because a gate that under-estimates exposure is
    worse than one that occasionally refuses a legitimate order.
    """
    qty = abs(float(payload.get("qty") or 0))
    if kind == "ibkr_option":
        px = payload.get("limit") or payload.get("strike") or 0
        return qty * abs(float(px or 0)) * 100
    px = payload.get("limit") or payload.get("entry") or payload.get("price") or 0
    return qty * abs(float(px or 0))


def _risk_gate(kind: str, payload: dict) -> dict | None:
    """The governor, ahead of every other check. No bypass, by design.

    This sits before the confirm-token and trust-grant logic on purpose: a standing
    grant authorises a KIND of order, it does not authorise exceeding the day's loss
    limit. Confirmed=True does not skip it either - an explicit human confirm is
    consent to a trade, not consent to trade past the limit that was set precisely so
    a bad day has a floor.
    """
    if kind in RISK_EXEMPT:
        # Closing and cancelling REDUCE exposure. Gating them would mean a halt traps
        # you in a losing position at precisely the moment you most need out, which
        # would turn the safety rail into the hazard.
        return None
    if not gateway_is_live():
        return None  # paper: the governor is about real money
    try:
        from . import risk
    except Exception:
        return None  # never let an import problem here block the desk entirely
    verdict = risk.check(_estimate_notional(kind, payload), kind=kind)
    if verdict.get("allowed"):
        return None
    return {
        "error": "Blocked by the risk governor. No order sent.",
        "reason": verdict.get("reason"),
        "halted": verdict.get("halted", False),
        "risk": verdict.get("state"),
        "fix": verdict.get("fix"),
    }


def _need_confirm(kind: str, payload: dict, *, confirmed: bool, confirm_token: str | None) -> dict | None:
    from . import memory

    # Ahead of everything, including confirmed=True and standing grants.
    blocked = _risk_gate(kind, payload)
    if blocked:
        return blocked

    if not gateway_is_live() or confirmed:
        return None
    if confirm_token:
        consumed = memory.consume_pending(confirm_token)
        if not consumed or consumed.get("kind") != kind:
            return {"error": "Invalid or expired confirm token. No IBKR order sent."}
        return None

    # A standing grant can cover this without a token — bounded by kind, symbol,
    # order value, use count and expiry, and audited either way. With no grants
    # live (the default) this is a no-op and everything below still runs.
    from . import trust

    verdict = trust.check_and_spend(kind, payload)
    if verdict.get("trusted"):
        return None

    pending = memory.create_pending(kind, payload, ttl_sec=180)
    try:
        memory.set_fact("ibkr.last_confirm", pending["confirm_token"], source_agent="trader")
    except Exception:
        pass
    return {
        "blocked": True,
        "reason": "LIVE TWS. Reply confirm with this confirm_token to send the order.",
        "trust": verdict.get("reason"),
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
        LimitOrder, MarketOrder, Option = _ib_names("LimitOrder", "MarketOrder", "Option")

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
        LimitOrder, MarketOrder, Stock = _ib_names("LimitOrder", "MarketOrder", "Stock")

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


def open_orders() -> dict[str, Any]:
    """Working orders you can still cancel or amend."""
    if not port_open(port()):
        return _not_listening_error()

    def read(ib) -> dict[str, Any]:
        rows = []
        for t in ib.openTrades():
            c, o, st = t.contract, t.order, t.orderStatus
            rows.append(
                {
                    "order_id": o.orderId,
                    "symbol": c.localSymbol or c.symbol,
                    "secType": c.secType,
                    "action": o.action,
                    "qty": float(o.totalQuantity or 0),
                    "order_type": o.orderType,
                    "limit": float(o.lmtPrice) if o.lmtPrice else None,
                    "stop": float(o.auxPrice) if o.auxPrice else None,
                    "status": st.status,
                    "filled": float(st.filled or 0),
                    "remaining": float(st.remaining or 0),
                }
            )
        return {"ok": True, "count": len(rows), "orders": rows, "live": gateway_is_live()}

    try:
        return _call(read, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def cancel_order(order_id: int | str = 0, *, all_orders: bool = False) -> dict[str, Any]:
    """Cancel one working order, or everything at once.

    Cancelling reduces exposure, so unlike placing it is not confirm-gated — being
    unable to pull an order quickly is its own risk.
    """
    if not port_open(port()):
        return _not_listening_error()
    try:
        wanted = int(order_id or 0)
    except (TypeError, ValueError):
        return {"error": "order_id must be numeric."}
    if not wanted and not all_orders:
        return {"error": "Pass order_id=<id> or all_orders=true."}

    def send(ib) -> dict[str, Any]:
        cancelled, missed = [], []
        for t in ib.openTrades():
            if all_orders or t.order.orderId == wanted:
                try:
                    ib.cancelOrder(t.order)
                    cancelled.append(t.order.orderId)
                except Exception as exc:
                    missed.append({"order_id": t.order.orderId, "error": str(exc)[:120]})
        ib.sleep(0.5)
        if not cancelled and not missed:
            return {"ok": False, "error": f"No open order matching {wanted or 'any'}."}
        return {"ok": True, "cancelled": cancelled, "failed": missed}

    try:
        out = _call(send, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}
    if out.get("ok"):
        from . import memory

        memory.remember(
            f"IBKR cancelled orders {out.get('cancelled')}",
            kind="trade",
            tags=["trade", "ibkr", "cancel"],
            importance=0.7,
            source_agent="trader",
        )
    return out


def place_bracket(
    symbol: str,
    side: str,
    qty: float,
    entry: float,
    stop: float,
    target: float,
    *,
    confirm_token: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Entry with a stop-loss and take-profit attached as one OCA bracket.

    The stop rides in with the entry rather than being placed afterwards, so a fill
    is never left sitting there unprotected if the follow-up call fails.
    """
    from . import memory

    symbol = (symbol or "").strip().upper()
    side = (side or "buy").lower()
    try:
        qty, entry, stop, target = float(qty), float(entry), float(stop), float(target)
    except (TypeError, ValueError):
        return {"error": "qty, entry, stop and target must all be numeric."}
    if not symbol or qty <= 0 or side not in {"buy", "sell"}:
        return {"error": "Need symbol, buy/sell, and qty > 0."}
    if min(entry, stop, target) <= 0:
        return {"error": "entry, stop and target must be positive prices."}

    # A bracket whose stop is on the wrong side of entry is not a bracket.
    if side == "buy" and not (stop < entry < target):
        return {"error": f"For a buy, need stop < entry < target (got {stop} / {entry} / {target})."}
    if side == "sell" and not (target < entry < stop):
        return {"error": f"For a sell, need target < entry < stop (got {target} / {entry} / {stop})."}

    gate = _need_confirm(
        "ibkr_bracket",
        {"symbol": symbol, "side": side, "qty": qty, "entry": entry, "stop": stop, "target": target},
        confirmed=confirmed,
        confirm_token=confirm_token,
    )
    if gate:
        return gate
    if config.IBKR_LIVE and not gateway_is_live():
        return {"error": "IBKR_LIVE is on but TWS is paper. Log into live TWS (port 7496).", **probe()}
    if not port_open(port()):
        return _not_listening_error()

    def send(ib) -> dict[str, Any]:
        (Stock,) = _ib_names("Stock")

        contract = Stock(symbol, "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {"error": f"IBKR could not qualify {symbol}"}
        action = "BUY" if side == "buy" else "SELL"
        bracket = ib.bracketOrder(action, qty, limitPrice=entry, takeProfitPrice=target, stopLossPrice=stop)
        placed = [ib.placeOrder(qualified[0], o) for o in bracket]
        parent = placed[0]
        st = _wait_status(ib, parent)
        return {
            "ok": True,
            "broker": "ibkr",
            "live": gateway_is_live(),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry": entry,
            "stop": stop,
            "target": target,
            "order_ids": [t.order.orderId for t in placed],
            "parent_status": st.status,
            "risk_per_share": round(abs(entry - stop), 4),
            "reward_per_share": round(abs(target - entry), 4),
            "r_multiple": round(abs(target - entry) / abs(entry - stop), 2) if entry != stop else None,
        }

    try:
        out = _call(send, timeout=20.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}
    if out.get("ok"):
        memory.remember(
            f"IBKR bracket {side} {qty} {symbol} entry {entry} stop {stop} target {target}",
            kind="trade",
            tags=["trade", "ibkr", symbol, "bracket"],
            importance=0.9,
            source_agent="trader",
        )
    return out


def close_position(
    symbol: str,
    *,
    confirm_token: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Flatten an open stock position at market."""
    from . import memory

    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"error": "symbol required."}
    if not port_open(port()):
        return _not_listening_error()

    def read_pos(ib) -> dict[str, Any]:
        for p in ib.positions():
            c = p.contract
            if (c.localSymbol or c.symbol or "").upper() == symbol and float(p.position) != 0:
                return {"qty": float(p.position), "secType": c.secType}
        return {}

    try:
        held = _call(read_pos, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}
    if not held:
        return {"ok": False, "error": f"No open position in {symbol}."}

    qty = held["qty"]
    gate = _need_confirm(
        "ibkr_close",
        {"symbol": symbol, "qty": qty},
        confirmed=confirmed,
        confirm_token=confirm_token,
    )
    if gate:
        return {**gate, "closing": {"symbol": symbol, "qty": qty}}

    def send(ib) -> dict[str, Any]:
        MarketOrder, Stock = _ib_names("MarketOrder", "Stock")

        contract = Stock(symbol, "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {"error": f"IBKR could not qualify {symbol}"}
        # Long position -> sell to flat; short -> buy to flat.
        action = "SELL" if qty > 0 else "BUY"
        trade = ib.placeOrder(qualified[0], MarketOrder(action, abs(qty), tif="DAY"))
        st = _wait_status(ib, trade)
        return {
            "ok": True,
            "symbol": symbol,
            "closed_qty": abs(qty),
            "action": action,
            "order_id": trade.order.orderId,
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
            f"IBKR flattened {symbol} ({out.get('closed_qty')})",
            kind="trade",
            tags=["trade", "ibkr", symbol, "close"],
            importance=0.85,
            source_agent="trader",
        )
    return out


def pnl() -> dict[str, Any]:
    """Realized and unrealized P&L per position."""
    if not port_open(port()):
        return _not_listening_error()

    def read(ib) -> dict[str, Any]:
        rows, realized, unrealized = [], 0.0, 0.0
        for item in ib.portfolio():
            c = item.contract
            u = float(item.unrealizedPNL or 0)
            r = float(item.realizedPNL or 0)
            unrealized += u
            realized += r
            rows.append(
                {
                    "symbol": c.localSymbol or c.symbol,
                    "secType": c.secType,
                    "qty": float(item.position or 0),
                    "avg_cost": float(item.averageCost or 0),
                    "market_price": float(item.marketPrice or 0),
                    "market_value": float(item.marketValue or 0),
                    "unrealized": round(u, 2),
                    "realized": round(r, 2),
                }
            )
        rows.sort(key=lambda r: r["unrealized"])
        return {
            "ok": True,
            "live": gateway_is_live(),
            "positions": rows,
            "total_unrealized": round(unrealized, 2),
            "total_realized": round(realized, 2),
        }

    try:
        return _call(read, timeout=12.0)
    except Exception as exc:
        return {"error": str(exc)[:300], **probe()}


def permissions() -> dict[str, Any]:
    """What Super Jarvis is allowed to do against TWS right now. Never asks for IBKR passwords."""
    info = probe()
    trading = allow_live_orders()
    info.update(
        {
            "ok": bool(info.get("ok")),
            "can_trade": trading,
            "needs_confirm": True,
            "read_only": not trading,
            "market_data": "live" if trading else ("delayed" if info.get("ok") else "none"),
            "stocks": trading,
            "options": trading,
            "broker": "ibkr",
            "client_library": ib_backend(),
            "note": (
                "Live IBKR stock and option orders are armed. Each send still needs confirm_token. "
                "Do not paste IBKR usernames or passwords into Jarvis."
                if trading
                else info.get("hint")
            ),
        }
    )
    return info


def stock_quotes(symbols: list[str]) -> dict[str, dict]:
    if not symbols or busy() or not port_open(port()):
        return {}

    def read(ib) -> dict[str, dict]:
        (Stock,) = _ib_names("Stock")

        out: dict[str, dict] = {}
        for raw in symbols[:8]:
            symbol = (raw or "").upper().strip()
            if not symbol or symbol.startswith("^") or "-USD" in symbol:
                continue
            try:
                qualified = ib.qualifyContracts(Stock(symbol, "SMART", "USD"))
                if not qualified:
                    continue
                ticker = ib.reqMktData(qualified[0], "", True, False)
                ib.sleep(0.5)
                last = float(ticker.last or 0) if ticker.last == ticker.last and ticker.last else 0.0
                bid = float(ticker.bid or 0) if ticker.bid == ticker.bid and ticker.bid else 0.0
                ask = float(ticker.ask or 0) if ticker.ask == ticker.ask and ticker.ask else 0.0
                try:
                    ib.cancelMktData(qualified[0])
                except Exception:
                    pass
                out[symbol] = {"bid": bid, "ask": ask, "last": last or ((bid + ask) / 2 if bid and ask else 0), "source": "ibkr"}
            except Exception:
                continue
        return out

    try:
        return _call(read, timeout=8.0, block=False) or {}
    except Exception:
        return {}


def dispatch(action: str = "account", **kwargs: Any) -> dict[str, Any]:
    act = (action or "account").lower()
    if act in {"probe", "status"}:
        return probe()
    if act in {"permissions", "permit", "can_trade"}:
        return permissions()
    if act in {"quote", "quotes"}:
        symbols = kwargs.get("symbols") or kwargs.get("symbol") or ""
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]
        return {"ok": True, "quotes": stock_quotes(list(symbols))}
    if act in {"account", "summary"}:
        return account()
    if act in {"orders", "open_orders", "working"}:
        return open_orders()
    if act in {"cancel", "kill", "pull"}:
        return cancel_order(
            kwargs.get("order_id") or 0,
            all_orders=bool(kwargs.get("all_orders") or kwargs.get("all")),
        )
    if act in {"pnl", "positions"}:
        return pnl()
    if act in {"bracket", "bracket_order"}:
        return place_bracket(
            kwargs.get("symbol") or "",
            kwargs.get("side") or "buy",
            float(kwargs.get("qty") or 0),
            float(kwargs.get("entry") or 0),
            float(kwargs.get("stop") or 0),
            float(kwargs.get("target") or 0),
            confirm_token=kwargs.get("confirm_token"),
        )
    if act in {"close", "flatten", "exit"}:
        return close_position(
            kwargs.get("symbol") or "",
            confirm_token=kwargs.get("confirm_token"),
        )
    if act in {"option", "options", "call", "put", "ticket"}:
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
