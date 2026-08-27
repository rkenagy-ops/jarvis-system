"""Did this setup ever actually work? Walk it forward over real bars and count.

setups.py will happily hand you an ENTER with an entry, a stop and a target, and no
evidence whatsoever that the pattern has ever paid. A rationale is not a hit rate. This
replays the same detector over history and reports what the trade would have done.

Two properties matter more than any statistic it prints.

The first is that it runs the SAME code. detect() and levels_for() are the functions
scan() and plan() call, handed a truncated bar list instead of the live one. A backtest
that reimplements the rules measures a strategy nobody trades, and it will usually
flatter itself.

The second is no look-ahead. Detection at bar i sees bars[:i+1] and nothing else - the
helpers all slice from the end of what they are given, so truncation is the whole
mechanism. Simulation then walks bars[i+1:]. Every number here is worthless if that
boundary leaks, so it is enforced structurally and tested directly.

    backtest action=run    symbol=AAPL setup=trend_pullback
    backtest action=sweep  symbol=AAPL                        -> every setup, ranked
    backtest action=verify symbol=AAPL setup=breakout_20d     -> does today's plan have a record?
"""

from __future__ import annotations

from typing import Any

from . import markets, setups

# A signal is a limit/stop order that is good for one session. If price never reaches
# the entry on the next bar, the trade simply did not happen - counting it as a fill at
# some later, better price is how backtests start lying.
ENTRY_VALID_BARS = 1

# Nobody holds a busted daily setup forever. Anything still open here is closed at the
# market and booked at whatever R that came to.
MAX_HOLD_BARS = 60


def _simulate(bars: list[dict], start: int, side: str, entry: float, stop: float, target: float) -> dict[str, Any] | None:
    """Walk one trade forward from the bar after the signal. None means it never filled."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    fill_i = None
    fill = None
    for j in range(start, min(start + ENTRY_VALID_BARS, len(bars))):
        bar = bars[j]
        high, low, open_ = bar.get("high"), bar.get("low"), bar.get("open")
        if high is None or low is None:
            continue
        if side == "buy" and high >= entry:
            # A gap through the entry fills at the open, not at the price you wanted.
            fill = max(entry, open_) if open_ is not None else entry
            fill_i = j
            break
        if side == "sell" and low <= entry:
            fill = min(entry, open_) if open_ is not None else entry
            fill_i = j
            break
    if fill_i is None:
        return None

    for j in range(fill_i, min(fill_i + MAX_HOLD_BARS, len(bars))):
        bar = bars[j]
        high, low = bar.get("high"), bar.get("low")
        if high is None or low is None:
            continue
        hit_stop = low <= stop if side == "buy" else high >= stop
        hit_target = high >= target if side == "buy" else low <= target
        if hit_stop and hit_target:
            # Both levels traded in one bar and daily data cannot say which came first.
            # Book the loss. The alternative is a backtest that wins its coin flips.
            hit_target = False
        if hit_stop:
            exit_px, outcome = stop, "stop"
        elif hit_target:
            exit_px, outcome = target, "target"
        else:
            continue
        gain = (exit_px - fill) if side == "buy" else (fill - exit_px)
        return {
            "outcome": outcome,
            "entry_date": bars[fill_i].get("date"),
            "exit_date": bar.get("date"),
            "fill": round(fill, 2),
            "exit": round(exit_px, 2),
            "r": round(gain / risk, 2),
            "bars_held": j - fill_i + 1,
        }

    last_i = min(fill_i + MAX_HOLD_BARS, len(bars)) - 1
    if last_i <= fill_i:
        return None  # ran out of history; an unfinished trade is not a result
    close = bars[last_i].get("close")
    if close is None:
        return None
    gain = (close - fill) if side == "buy" else (fill - close)
    return {
        "outcome": "timeout",
        "entry_date": bars[fill_i].get("date"),
        "exit_date": bars[last_i].get("date"),
        "fill": round(fill, 2),
        "exit": round(close, 2),
        "r": round(gain / risk, 2),
        "bars_held": last_i - fill_i + 1,
    }


def _metrics(trades: list[dict]) -> dict[str, Any]:
    """What the trades add up to. Expectancy is the number that decides anything."""
    if not trades:
        return {"trades": 0, "note": "No signals fired in this window."}

    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    equity, peak, drawdown = 0.0, 0.0, 0.0
    streak, worst_streak = 0, 0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        streak = streak + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, streak)

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100 * len(wins) / len(trades), 1),
        "expectancy_r": round(sum(rs) / len(rs), 3),
        "total_r": round(sum(rs), 2),
        "avg_win_r": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss_r": round(-gross_loss / len(losses), 2) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "max_drawdown_r": round(drawdown, 2),
        "max_consecutive_losses": worst_streak,
        "avg_bars_held": round(sum(t["bars_held"] for t in trades) / len(trades), 1),
        "timeouts": sum(1 for t in trades if t["outcome"] == "timeout"),
    }


def _verdict(m: dict[str, Any]) -> str:
    n = m.get("trades") or 0
    if not n:
        return "No signals — this setup never fired here. That is not evidence either way."
    if n < 10:
        return f"Only {n} trades. Too few to conclude anything; treat the numbers as anecdote."
    e = m["expectancy_r"]
    if e <= 0:
        return f"Negative expectancy ({e}R per trade) over {n} trades. This setup lost money on this symbol."
    if e < 0.1:
        return f"Barely positive ({e}R per trade). Commissions and slippage would likely eat this."
    return f"Positive expectancy: {e}R per trade over {n} trades, worst drawdown {m['max_drawdown_r']}R."


def run(symbol: str, setup: str, *, range_: str = "5y") -> dict[str, Any]:
    """Replay one setup over history on one symbol."""
    key = (setup or "").strip().lower()
    if key not in setups.CATALOG:
        return {"error": f"Unknown setup {key!r}.", "known": sorted(setups.CATALOG)}

    hist = markets.history(symbol, range_)
    if hist.get("error"):
        return hist
    bars = [b for b in (hist.get("bars") or []) if b.get("close") is not None]
    if len(bars) < setups.WARMUP_BARS + 30:
        return {
            "error": f"Only {len(bars)} bars for {symbol}. Need at least "
            f"{setups.WARMUP_BARS + 30} to warm the indicators and still have history to test."
        }

    trades: list[dict] = []
    signals = 0
    busy_until = -1
    for i in range(setups.WARMUP_BARS - 1, len(bars) - 1):
        if i < busy_until:
            continue  # one position at a time; pyramiding is a different strategy
        # Detection sees the past only. This slice is the whole no-look-ahead mechanism.
        ctx = setups.context_from_bars(bars[: i + 1], symbol)
        if not ctx.get("ok"):
            continue
        found = setups.detect(ctx).get("found") or []
        if not any(f["setup"] == key for f in found):
            continue
        signals += 1
        levels = setups.levels_for(ctx, key)
        if not levels.get("ok"):
            continue
        trade = _simulate(bars, i + 1, levels["side"], levels["entry"], levels["stop"], levels["target"])
        if not trade:
            continue
        trade["setup"] = key
        trades.append(trade)
        busy_until = i + 1 + trade["bars_held"]

    metrics = _metrics(trades)
    return {
        "ok": True,
        "symbol": symbol.upper(),
        "setup": key,
        "name": setups.CATALOG[key]["name"],
        "range": range_,
        "bars_tested": len(bars) - setups.WARMUP_BARS,
        "signals": signals,
        "filled": len(trades),
        "unfilled": signals - len(trades),
        "metrics": metrics,
        "verdict": _verdict(metrics),
        "trades": trades[-20:],
        "assumptions": {
            "entry": f"Stop order good for {ENTRY_VALID_BARS} bar(s); a gap through it fills at the open.",
            "same_bar_stop_and_target": "Counted as a loss - daily bars cannot say which came first.",
            "max_hold": f"{MAX_HOLD_BARS} bars, then out at the close.",
            "costs": "No commission or slippage. Subtract roughly 0.05R per trade for a realistic read.",
            "overlap": "One position at a time.",
        },
    }


def sweep(symbol: str, *, range_: str = "5y") -> dict[str, Any]:
    """Every setup on one symbol, ranked by expectancy."""
    results = []
    for key in sorted(setups.CATALOG):
        out = run(symbol, key, range_=range_)
        if not out.get("ok"):
            results.append({"setup": key, "error": out.get("error")})
            continue
        m = out["metrics"]
        results.append({
            "setup": key,
            "name": out["name"],
            "trades": m.get("trades", 0),
            "win_rate": m.get("win_rate"),
            "expectancy_r": m.get("expectancy_r"),
            "profit_factor": m.get("profit_factor"),
            "max_drawdown_r": m.get("max_drawdown_r"),
            "verdict": out["verdict"],
        })
    ranked = sorted(
        results,
        key=lambda r: (r.get("expectancy_r") is not None, r.get("expectancy_r") or -99),
        reverse=True,
    )
    usable = [r for r in ranked if (r.get("trades") or 0) >= 10 and (r.get("expectancy_r") or 0) > 0]
    return {
        "ok": True,
        "symbol": symbol.upper(),
        "range": range_,
        "ranked": ranked,
        "best": usable[0]["setup"] if usable else None,
        "note": (
            f"{len(usable)} setup(s) cleared 10+ trades with positive expectancy."
            if usable
            else "Nothing here cleared 10+ trades with positive expectancy. On this symbol, none of "
            "these patterns has earned a position."
        ),
    }


def verify(symbol: str, setup: str, *, range_: str = "5y", risk: float = 0.0) -> dict[str, Any]:
    """Today's plan, with its historical record attached.

    This is the one worth calling before putting money on a setup: it pairs the live
    levels with what the same rules did on the same symbol, so an ENTER arrives with
    evidence or with an explicit admission that there is none.
    """
    live = setups.plan(symbol, setup, risk)
    if not live.get("ok"):
        return live
    record = run(symbol, setup, range_=range_)
    if not record.get("ok"):
        return {"ok": True, "plan": live, "history": None, "warning": record.get("error")}

    m = record["metrics"]
    n = m.get("trades") or 0
    e = m.get("expectancy_r")
    if n < 10:
        confidence = "untested"
        advice = f"Only {n} historical trades. The levels are sound; the edge is unproven."
    elif e is not None and e > 0.1:
        confidence = "supported"
        advice = f"{n} trades at {e}R expectancy. The plan has a record behind it."
    else:
        confidence = "contradicted"
        advice = (
            f"{n} trades at {e}R expectancy - this setup has not paid on {symbol.upper()}. "
            "The levels are still valid as structure, but history is against the premise."
        )
    return {
        "ok": True,
        "symbol": symbol.upper(),
        "setup": setup,
        "confidence": confidence,
        "advice": advice,
        "plan": live,
        "history": {
            "trades": n,
            "win_rate": m.get("win_rate"),
            "expectancy_r": e,
            "profit_factor": m.get("profit_factor"),
            "max_drawdown_r": m.get("max_drawdown_r"),
            "max_consecutive_losses": m.get("max_consecutive_losses"),
        },
        "verdict": record["verdict"],
        "assumptions": record["assumptions"],
    }


def dispatch(action: str = "run", **kwargs: Any) -> Any:
    act = (action or "run").lower()
    symbol = str(kwargs.get("symbol") or "")
    setup = str(kwargs.get("setup") or "")
    range_ = str(kwargs.get("range") or kwargs.get("range_") or "5y")
    risk = float(kwargs.get("risk") or 0)
    if act in {"run", "test", "backtest"}:
        if not symbol or not setup:
            return {"error": "symbol and setup required.", "known": sorted(setups.CATALOG)}
        return run(symbol, setup, range_=range_)
    if act in {"sweep", "all", "rank"}:
        if not symbol:
            return {"error": "symbol required."}
        return sweep(symbol, range_=range_)
    if act in {"verify", "check", "evidence"}:
        if not symbol or not setup:
            return {"error": "symbol and setup required."}
        return verify(symbol, setup, range_=range_, risk=risk)
    return {"error": f"unknown backtest action {act}", "actions": ["run", "sweep", "verify"]}
