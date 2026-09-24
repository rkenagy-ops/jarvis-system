"""Daily P&L, visible - not a target. No goal percentage, no progress bar, and nothing
here caps a good day. This only reports what already happened; it changes nothing and
gates nothing. The risk governor (app/risk.py) is still the only thing that can stop a
trade, and it still only ever gates losses - this module cannot touch it.

risk.py keeps today's tally in one fact that gets overwritten when the trading day
rolls, so there was no history to look back over. This adds the one thing that was
actually missing: an append-only daily log, so "how has she actually been doing"
has an answer longer than one day.

    pnl_dashboard action=dashboard   -> the full picture: today, trend, setup expectancy
    pnl_dashboard action=snapshot    -> record today's numbers as they stand right now
    pnl_dashboard action=history     -> the raw daily log
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from . import config


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_pnl_log (
            day TEXT PRIMARY KEY,
            realized REAL NOT NULL,
            unrealized REAL,
            trades INTEGER NOT NULL,
            consecutive_losses INTEGER NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    return conn


def snapshot() -> dict[str, Any]:
    """Record today's numbers as they stand right now.

    Safe to call as often as you like - it upserts today's row (keyed on the same
    market-day boundary risk.py uses), so calling it fifty times today still leaves
    exactly one row for today, and never touches any other day's history.
    """
    from . import risk

    loss = risk.day_loss()
    state = risk.state()
    day = loss["day"]

    unrealized = None
    try:
        from . import ibkr

        p = ibkr.pnl()
        if p.get("ok"):
            unrealized = p.get("total_unrealized")
    except Exception:
        pass

    conn = _db()
    try:
        conn.execute(
            "INSERT INTO daily_pnl_log (day, realized, unrealized, trades, consecutive_losses, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET realized=excluded.realized, unrealized=excluded.unrealized, "
            "trades=excluded.trades, consecutive_losses=excluded.consecutive_losses, updated_at=excluded.updated_at",
            (day, loss["net"], unrealized, state["trades_today"], state["consecutive_losses"], time.time()),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "day": day,
        "realized": loss["net"],
        "unrealized": unrealized,
        "trades": state["trades_today"],
    }


def history(days: int = 30) -> list[dict[str, Any]]:
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_pnl_log ORDER BY day DESC LIMIT ?", (int(days),)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def dashboard(days: int = 30) -> dict[str, Any]:
    """Everything in one place: today's live number, the trailing record, and which
    setups are actually contributing to it. No target anywhere in this - a good day
    is reported exactly like any other day, not measured against a number.
    """
    today = snapshot()
    hist = history(days)

    total_realized = round(sum(r["realized"] or 0.0 for r in hist), 2)
    green_days = sum(1 for r in hist if (r["realized"] or 0.0) > 0)
    red_days = sum(1 for r in hist if (r["realized"] or 0.0) < 0)
    flat_days = len(hist) - green_days - red_days
    best_day = max(hist, key=lambda r: r["realized"] or 0.0, default=None)
    worst_day = min(hist, key=lambda r: r["realized"] or 0.0, default=None)

    # Oldest first, running total - a curve, not a countdown to anything.
    curve = []
    running = 0.0
    for r in reversed(hist):
        running += r["realized"] or 0.0
        curve.append({"day": r["day"], "realized": r["realized"], "cumulative": round(running, 2)})

    setup_expectancy: dict[str, Any] = {}
    try:
        from . import forward_tracker

        setup_expectancy = forward_tracker.stats().get("by_setup") or {}
    except Exception:
        pass

    return {
        "ok": True,
        "today": today,
        "window_days": len(hist),
        "total_realized": total_realized,
        "green_days": green_days,
        "red_days": red_days,
        "flat_days": flat_days,
        "best_day": best_day,
        "worst_day": worst_day,
        "equity_curve": curve,
        "setup_expectancy": setup_expectancy,
        "note": (
            "Reporting only - there is no daily target here and nothing caps a good day. "
            "The risk governor (app/risk.py) is the only thing that can stop a trade, and "
            "it only ever gates losses."
        ),
    }


def dispatch(action: str = "dashboard", **kwargs: Any) -> Any:
    act = (action or "dashboard").lower()
    if act in {"dashboard", "check", "report"}:
        return dashboard(days=int(kwargs.get("days") or 30))
    if act == "snapshot":
        return snapshot()
    if act == "history":
        return {"ok": True, "days": history(int(kwargs.get("days") or 30))}
    return {"error": f"unknown pnl_dashboard action {act}", "actions": ["dashboard", "snapshot", "history"]}
