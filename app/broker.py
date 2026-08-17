"""Official Alpaca brokerage. Paper endpoint by default. Live cash needs confirm + ALPACA_LIVE."""

from __future__ import annotations

from typing import Any

import httpx

from . import config

PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"


def configured() -> bool:
    return bool(config.ALPACA_KEY_ID and config.ALPACA_SECRET_KEY)


def live_cash() -> bool:
    return bool(config.ALPACA_LIVE) and config.TRADING_MODE == "live"


def base() -> str:
    return LIVE_BASE if live_cash() else PAPER_BASE


def _headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": config.ALPACA_KEY_ID,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }


def status() -> dict[str, Any]:
    if not configured():
        return {
            "configured": False,
            "mode": "local-paper",
            "hint": "Set ALPACA_KEY_ID and ALPACA_SECRET_KEY. ALPACA_LIVE=true is real money and still needs a confirm token.",
        }
    return {"configured": True, "mode": "alpaca-live" if live_cash() else "alpaca-paper", "base": base()}


def account() -> dict[str, Any]:
    if not configured():
        return {"error": "Alpaca keys not set", **status()}
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(base() + "/v2/account", headers=_headers())
    if resp.status_code >= 400:
        return {"error": f"alpaca {resp.status_code}", "detail": resp.text[:400], **status()}
    data = resp.json()
    return {
        "ok": True,
        **status(),
        "id": data.get("id"),
        "status": data.get("status"),
        "cash": data.get("cash"),
        "equity": data.get("equity"),
        "buying_power": data.get("buying_power"),
        "portfolio_value": data.get("portfolio_value"),
        "pattern_day_trader": data.get("pattern_day_trader"),
    }


def submit_market(symbol: str, side: str, qty: float) -> dict[str, Any]:
    if not configured():
        return {"error": "Alpaca keys not set"}
    body = {
        "symbol": symbol.replace("-USD", "USD").replace("=X", ""),
        "qty": str(qty),
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(base() + "/v2/orders", headers=_headers(), json=body)
    if resp.status_code >= 400:
        return {"error": f"alpaca {resp.status_code}", "detail": resp.text[:600], "sent": body, **status()}
    data = resp.json()
    return {
        "ok": True,
        **status(),
        "broker": "alpaca",
        "order_id": data.get("id"),
        "symbol": data.get("symbol"),
        "side": data.get("side"),
        "qty": data.get("qty"),
        "status": data.get("status"),
        "submitted_at": data.get("submitted_at"),
    }
