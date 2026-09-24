"""Is she actually ready to trade when the bell rings? A status report, not a lever.

This never raises a limit, clears a halt, or places anything - it only reads the same
state the risk governor and IBKR adapter already keep, and says plainly what would
stop an order from going out right now. The fix for anything it finds is a human
decision (resume trading, fix a config value, start TWS), never something this module
does on its own.

    premarket action=check   -> the full readiness report
"""

from __future__ import annotations

from typing import Any

from . import config


def readiness() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    from . import ibkr

    probe = ibkr.probe()
    ibkr_ok = bool(probe.get("ok"))
    if not ibkr_ok:
        blockers.append(f"TWS/Gateway is not listening: {probe.get('hint')}")

    from . import risk

    r = risk.state()
    if r.get("halted"):
        blockers.append(
            f"Trading is halted from a prior session: {r.get('halt_reason')}. "
            "This does not clear itself - call risk action=resume only after deciding "
            "the halt reason no longer applies."
        )
    if r.get("remaining", 0) <= 0 and not r.get("halted"):
        blockers.append(f"Daily loss budget already at {r.get('loss_today')} of {r.get('limit')} for {r.get('day')}.")

    if risk.max_daily_loss() <= 0:
        blockers.append("MAX_DAILY_LOSS is configured at zero or invalid - the risk governor would refuse every order.")
    if risk.max_trade_notional() <= 0:
        blockers.append("MAX_TRADE_NOTIONAL is configured at zero or invalid - the risk governor would refuse every order.")

    if not config.WATCHLIST:
        warnings.append("Watchlist is empty.")

    from . import markets

    probe_symbol = (config.WATCHLIST[0] if config.WATCHLIST else "SPY")
    q = markets.quote(probe_symbol)
    data_ok = not q.get("error")
    if not data_ok:
        warnings.append(f"Quote check on {probe_symbol} failed: {q.get('error')}")

    universe_status: dict[str, Any] = {}
    try:
        from . import universe

        universe_status = universe.status()
        if universe_status.get("stale"):
            warnings.append("Full-market universe cache is stale - broad_screen will refetch it on next use.")
    except Exception as exc:
        warnings.append(f"Could not check universe cache: {exc}")

    open_orders: list[dict] | None = None
    open_positions: int | None = None
    if ibkr_ok:
        try:
            oo = ibkr.open_orders()
            if oo.get("ok"):
                open_orders = oo.get("orders") or []
        except Exception:
            pass
        try:
            acct = ibkr.account()
            if acct.get("ok"):
                open_positions = len(acct.get("positions") or [])
        except Exception:
            pass

    ready = not blockers
    return {
        "ok": True,
        "ready": ready,
        "verdict": (
            "Ready for market open - nothing found that would block an order."
            if ready
            else f"{len(blockers)} blocker(s) found - resolve before the bell."
        ),
        "blockers": blockers,
        "warnings": warnings,
        "ibkr": {
            "connected": ibkr_ok,
            "live": probe.get("gateway_live"),
            "port_name": probe.get("port_name"),
        },
        "risk": r,
        "data_sources": {"quote_check_symbol": probe_symbol, "quote_check_ok": data_ok},
        "universe_cache": universe_status,
        "open_orders": open_orders,
        "open_positions": open_positions,
        "watchlist": config.WATCHLIST,
    }


def dispatch(action: str = "check", **kwargs: Any) -> Any:
    act = (action or "check").lower()
    if act in {"check", "readiness", "status"}:
        return readiness()
    return {"error": f"unknown premarket action {act}", "actions": ["check"]}
