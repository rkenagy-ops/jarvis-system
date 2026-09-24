"""Does what setups.detect() finds actually pay, going forward — on data it has not seen?

backtest.py answers "did this setup ever work historically." That is necessary but not
sufficient: a catalog tuned by eye against years of the same history can look good on
that history and still be overfit to it. The only thing that actually proves a setup
still works is watching it fire on new bars in real time and honestly recording what
happened.

This module never places an order, never touches IBKR, never sizes a position, and
never adjusts a risk limit. It only watches what setups.scan() already finds on symbols
you point it at, logs the plan setups.levels_for() computed at the moment each signal
fired, and later walks that plan forward against real bars using backtest._simulate —
the exact same fill/exit engine the historical backtest runs. That reuse is deliberate:
a live result and a historical result must never be able to quietly diverge because one
side reimplemented the rules. Nothing here reads MAX_DAILY_LOSS, MAX_TRADE_NOTIONAL,
IBKR_LIVE, or any other trading/risk switch — those stay exactly as configured.

    forward_tracker action=scan    symbols=AAPL,MSFT     -> log any newly-detected setups
    forward_tracker action=update                        -> walk every open signal forward
    forward_tracker action=stats   setup=trend_pullback   -> live win rate / expectancy
    forward_tracker action=open                           -> currently open signals
    forward_tracker action=compare setup=trend_pullback   -> live stats next to the historical backtest
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterable

from . import backtest, config, markets, setups

_lock = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    setup TEXT NOT NULL,
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    signal_date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    fill REAL,
    exit_price REAL,
    exit_date TEXT,
    outcome TEXT,
    r REAL,
    bars_held INTEGER,
    UNIQUE(symbol, setup, signal_date)
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


@contextmanager
def _db() -> Iterable[sqlite3.Connection]:
    """One connection per unit of work, always closed, serialized by a lock.

    A left-open connection after a caught exception is exactly how an earlier version
    of this file could deadlock the database on the very next write — a lock that
    outlives its transaction blocks every connection after it, not just its own.
    """
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def log_new_signals(symbols: list[str] | None = None, *, range_: str = "1y") -> dict[str, Any]:
    """Scan symbols with the SAME setups.scan() the live desk uses; log anything new.

    Keyed on (symbol, setup, signal_date), so re-running this after the same day's bar
    has already been logged is a no-op — it can never double-count one day's fire.
    """
    syms = [s.strip().upper() for s in (symbols or config.WATCHLIST) if s.strip()]
    logged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for symbol in syms:
        try:
            found = setups.scan(symbol, range_)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not found.get("ok") or not found.get("found"):
            continue
        hist = markets.history(symbol, range_)
        bars = [b for b in (hist.get("bars") or []) if b.get("close") is not None]
        if not bars:
            continue
        ctx = setups.context_from_bars(bars, symbol)
        if not ctx.get("ok"):
            continue
        signal_date = bars[-1].get("date") or date.today().isoformat()
        for item in found["found"]:
            key = item["setup"]
            levels = setups.levels_for(ctx, key)
            if not levels.get("ok"):
                continue
            try:
                with _db() as conn:
                    conn.execute(
                        "INSERT INTO forward_signals "
                        "(symbol, setup, side, entry, stop, target, signal_date, logged_at, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                        (
                            symbol, key, levels["side"], levels["entry"], levels["stop"], levels["target"],
                            signal_date, datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                logged.append({"symbol": symbol, "setup": key, "signal_date": signal_date, **levels})
            except sqlite3.IntegrityError:
                skipped.append({"symbol": symbol, "setup": key, "reason": "already logged for this session"})
    return {
        "ok": True,
        "scanned": len(syms),
        "logged": len(logged),
        "skipped": len(skipped),
        "errors": errors,
        "signals": logged,
    }


def update_open(*, range_: str = "2y") -> dict[str, Any]:
    """Walk every open signal forward against bars fetched since it fired.

    Uses backtest._simulate directly — the identical fill/exit code the historical
    backtest runs on the same setups — so nothing here can drift from what backtest.py
    would say about the same trade.
    """
    with _db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM forward_signals WHERE status = 'open'").fetchall()]

    closed: list[dict[str, Any]] = []
    unfilled: list[dict[str, Any]] = []
    still_open: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for row in rows:
        symbol = row["symbol"]
        try:
            hist = markets.history(symbol, range_)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
            continue
        bars = [b for b in (hist.get("bars") or []) if b.get("close") is not None]
        try:
            start_i = next(i for i, b in enumerate(bars) if b.get("date") == row["signal_date"])
        except StopIteration:
            # The signal date has rolled out of the fetched window (range_ too short
            # for how old this signal is). Leave it open rather than guess.
            still_open.append({"symbol": symbol, "setup": row["setup"], "signal_date": row["signal_date"]})
            continue

        if len(bars) <= start_i + backtest.ENTRY_VALID_BARS:
            # Not enough bars have printed yet since the signal fired to know if it
            # even filled. Genuinely still pending — check again next run.
            still_open.append({"symbol": symbol, "setup": row["setup"], "signal_date": row["signal_date"]})
            continue

        trade = backtest._simulate(bars, start_i + 1, row["side"], row["entry"], row["stop"], row["target"])
        if trade is None:
            # Its fill window has closed and price never reached the entry. This
            # never became a trade — mark it terminal so it stops being rechecked
            # forever, but keep it out of win-rate stats (it never happened).
            with _db() as conn:
                conn.execute("UPDATE forward_signals SET status='unfilled' WHERE id=?", (row["id"],))
            unfilled.append({"symbol": symbol, "setup": row["setup"], "signal_date": row["signal_date"]})
            continue

        with _db() as conn:
            conn.execute(
                "UPDATE forward_signals SET status='closed', fill=?, exit_price=?, exit_date=?, "
                "outcome=?, r=?, bars_held=? WHERE id=?",
                (trade["fill"], trade["exit"], trade["exit_date"], trade["outcome"], trade["r"],
                 trade["bars_held"], row["id"]),
            )
        closed.append({"symbol": symbol, "setup": row["setup"], **trade})

    return {
        "ok": True,
        "closed": len(closed),
        "unfilled": len(unfilled),
        "still_open": len(still_open),
        "errors": errors,
        "results": closed,
    }


def stats(setup: str | None = None) -> dict[str, Any]:
    """Live expectancy/win-rate per setup, from closed forward-tracked signals only."""
    with _db() as conn:
        if setup:
            rows = conn.execute(
                "SELECT * FROM forward_signals WHERE status='closed' AND setup=?", (setup,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM forward_signals WHERE status='closed'").fetchall()
        trades = [dict(r) for r in rows]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        grouped.setdefault(t["setup"], []).append(t)
    by_setup = {key: backtest._metrics(ts) for key, ts in grouped.items()}
    return {"ok": True, "by_setup": by_setup, "total_closed": len(trades)}


def open_signals() -> dict[str, Any]:
    with _db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM forward_signals WHERE status='open' ORDER BY logged_at DESC"
        ).fetchall()]
    return {"ok": True, "count": len(rows), "signals": rows}


def compare(setup: str) -> dict[str, Any]:
    """Live forward stats next to the historical backtest, for the same setup.

    This is the number that actually matters: not whether a setup once worked, but
    whether it is still working on bars it has never seen. Historical expectancy is
    pooled across symbols, weighted by trade count, since R is already normalized
    per trade and comparable across names.
    """
    key = (setup or "").strip().lower()
    if key not in setups.CATALOG:
        return {"error": f"Unknown setup {key!r}.", "known": sorted(setups.CATALOG)}

    with _db() as conn:
        symbols = [r["symbol"] for r in conn.execute(
            "SELECT DISTINCT symbol FROM forward_signals WHERE setup=?", (key,)
        ).fetchall()]

    live = stats(key).get("by_setup", {}).get(key) or {"trades": 0, "note": "No closed live signals yet."}

    hist_by_symbol: dict[str, Any] = {}
    total_trades, weighted_r = 0, 0.0
    for sym in symbols:
        out = backtest.run(sym, key)
        if not out.get("ok"):
            continue
        m = out["metrics"]
        n = m.get("trades") or 0
        hist_by_symbol[sym] = {
            "trades": n, "win_rate": m.get("win_rate"), "expectancy_r": m.get("expectancy_r"),
        }
        e = m.get("expectancy_r")
        if n and e is not None:
            total_trades += n
            weighted_r += e * n
    hist_expectancy = round(weighted_r / total_trades, 3) if total_trades else None

    verdict = "Not enough closed live signals yet for a live-vs-historical read."
    live_n = live.get("trades") or 0
    live_e = live.get("expectancy_r")
    if live_n >= 5 and hist_expectancy is not None and live_e is not None:
        if live_e >= hist_expectancy - 0.1:
            verdict = f"Live ({live_e}R over {live_n} trades) is tracking or beating the historical read ({hist_expectancy}R)."
        else:
            verdict = f"Live ({live_e}R over {live_n} trades) is running below the historical read ({hist_expectancy}R) — watch this one closely."
    elif live_n:
        verdict = f"Only {live_n} closed live trade(s) so far — too few to compare against history with confidence."

    return {
        "ok": True,
        "setup": key,
        "symbols_tracked": symbols,
        "live": live,
        "historical": {"pooled_expectancy_r": hist_expectancy, "pooled_trades": total_trades, "by_symbol": hist_by_symbol},
        "verdict": verdict,
    }


def dispatch(action: str = "open", **kwargs: Any) -> Any:
    act = (action or "open").lower()
    if act in {"scan", "log"}:
        symbols = kwargs.get("symbols")
        if isinstance(symbols, str):
            symbols = [s for s in symbols.split(",") if s.strip()]
        return log_new_signals(symbols, range_=str(kwargs.get("range") or kwargs.get("range_") or "1y"))
    if act == "update":
        return update_open(range_=str(kwargs.get("range") or kwargs.get("range_") or "2y"))
    if act in {"stats", "results"}:
        setup = kwargs.get("setup")
        return stats(str(setup).lower() if setup else None)
    if act == "open":
        return open_signals()
    if act == "compare":
        setup = str(kwargs.get("setup") or "")
        if not setup:
            return {"error": "setup required."}
        return compare(setup)
    return {"error": f"unknown forward_tracker action {act}", "actions": ["scan", "update", "stats", "open", "compare"]}
