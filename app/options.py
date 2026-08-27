"""Options selection with the parts that actually decide the outcome.

Most retail options money is not lost on direction. It is lost on three things that
happen before the thesis ever gets tested: paying a spread that eats the edge, buying
premium when premium is expensive, and sizing as if the contract were a lottery ticket.
This module is built around those three.

    options action=rank    symbol=AAPL bias=bullish   -> which contract, and why
    options action=iv      symbol=AAPL               -> is premium cheap or dear right now
    options action=size    symbol=AAPL ...           -> contracts from a risk budget
    options action=book                              -> portfolio greeks, aggregated

What it will not do is tell you a trade is good because the chart looks good. Every
candidate is scored on cost of entry, volatility regime and breakeven distance, and the
scoring is arithmetic you can check rather than a judgement you have to trust.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from typing import Any

from . import greeks, markets

# --- what makes a contract tradeable -----------------------------------------
#
# A 20%-wide bid/ask means you are down 10% the instant you fill, and you pay it again
# on the way out. No amount of being right about direction recovers that reliably.
MAX_SPREAD_PCT = 12.0
MIN_OPEN_INTEREST = 250
MIN_VOLUME = 25

# Weeklies decay fastest and give a thesis no time to work; LEAPs tie up capital and
# barely move on the move you predicted. This window is where directional trades live.
MIN_DTE = 21
MAX_DTE = 75

# Delta band for a directional long. Below this you are buying lottery tickets that
# expire worthless most of the time; above it you are paying for stock you could buy.
TARGET_DELTA = (0.35, 0.65)


def _dte(expiry: str) -> int | None:
    raw = (expiry or "").replace("-", "")
    if len(raw) != 8:
        return None
    try:
        day = dt.date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None
    return (day - dt.date.today()).days


def spread_pct(bid: float | None, ask: float | None) -> float | None:
    """The toll you pay to enter and leave, as a percentage of the mid."""
    if bid is None or ask is None or ask <= 0 or bid <= 0:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return round(100 * (ask - bid) / mid, 2)


def yang_zhang(bars: list[dict], window: int = 20) -> float | None:
    """Volatility that uses the whole bar, not just the close.

    Close-to-close throws away the open, high and low - which is to say it throws away
    most of what the day did. On a name that gaps and then reverses it can report calm
    while the range says otherwise, and every ITM probability we compute is only as good
    as the volatility feeding it. Yang-Zhang combines overnight gap, open-to-close drift
    and Rogers-Satchell intraday range, and is the standard estimator for exactly this.
    """
    rows = [b for b in bars[-(window + 1):]
            if all(b.get(k) for k in ("open", "high", "low", "close"))]
    if len(rows) < window + 1:
        return None

    overnight, openclose, rs = [], [], []
    for i in range(1, len(rows)):
        prev_c = rows[i - 1]["close"]
        o, h, l, c = rows[i]["open"], rows[i]["high"], rows[i]["low"], rows[i]["close"]
        if min(prev_c, o, h, l, c) <= 0:
            continue
        overnight.append(math.log(o / prev_c))
        openclose.append(math.log(c / o))
        rs.append(math.log(h / c) * math.log(h / o) + math.log(l / c) * math.log(l / o))

    n = len(rs)
    if n < 5:
        return None

    mu_o = sum(overnight) / n
    mu_c = sum(openclose) / n
    v_o = sum((x - mu_o) ** 2 for x in overnight) / (n - 1)
    v_c = sum((x - mu_c) ** 2 for x in openclose) / (n - 1)
    v_rs = sum(rs) / n

    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var = v_o + k * v_c + (1 - k) * v_rs
    if var <= 0:
        return None
    return math.sqrt(var * 252)


def iv_rank(symbol: str, *, range_: str = "1y") -> dict[str, Any]:
    """Is premium expensive or cheap for this name, by its own history?

    Implied vol has no absolute scale - 30% is cheap on one name and dear on another.
    What matters is where it sits in its own range, because that decides whether you
    want to be buying premium or selling it. Computed from realized volatility as a
    proxy: it is not the option-implied surface, and the output says so rather than
    implying a precision it does not have.
    """
    hist = markets.history(symbol, range_)
    if hist.get("error"):
        return hist
    bars = [b for b in (hist.get("bars") or []) if b.get("close")]
    closes = [b["close"] for b in bars]
    if len(closes) < 60:
        return {"error": f"Only {len(closes)} bars for {symbol}; need 60+ for a volatility range."}

    window = 20
    have_ohlc = all(all(b.get(k) for k in ("open", "high", "low")) for b in bars[-window - 1:])
    vols: list[float] = []
    if have_ohlc:
        for i in range(window + 1, len(bars) + 1):
            v = yang_zhang(bars[:i], window)
            if v:
                vols.append(v)
        estimator = "yang-zhang"
    if not vols:
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
        vols = [
            statistics.pstdev(rets[i - window : i]) * math.sqrt(252)
            for i in range(window, len(rets) + 1)
            if len(rets[i - window : i]) == window
        ]
        estimator = "close-to-close (no intraday range available)"
    if len(vols) < 30:
        return {"error": "Not enough history to place volatility in a range."}

    current, lo, hi = vols[-1], min(vols), max(vols)
    rank = 100 * (current - lo) / (hi - lo) if hi > lo else 50.0
    pctile = 100 * sum(1 for v in vols if v < current) / len(vols)

    if rank < 30:
        regime, stance = "cheap", "Premium is cheap by this name's own standard. Buying options is the side to be on."
    elif rank > 70:
        regime, stance = "expensive", (
            "Premium is dear. Long options here need a big move just to overcome what you paid - "
            "defined-risk spreads finance part of that."
        )
    else:
        regime, stance = "middling", "Premium is unremarkable. Neither buying nor selling has a volatility edge."

    return {
        "ok": True,
        "symbol": symbol.upper(),
        "realized_vol": round(current * 100, 1),
        "iv_rank": round(rank, 1),
        "iv_percentile": round(pctile, 1),
        "range": {"low": round(lo * 100, 1), "high": round(hi * 100, 1)},
        "regime": regime,
        "stance": stance,
        "estimator": estimator,
        "caveat": (
            "Realized volatility over 20 sessions, used as a stand-in for implied. Real IV rank "
            "needs the option surface from the broker; this is directionally right and not exact."
        ),
    }


def score_contract(
    *,
    spot: float,
    strike: float,
    expiry: str,
    right: str,
    bid: float | None = None,
    ask: float | None = None,
    iv: float | None = None,
    open_interest: int | None = None,
    volume: int | None = None,
    rate: float = 0.04,
) -> dict[str, Any]:
    """One contract, judged on the things that decide whether it can win."""
    dte = _dte(expiry)
    if dte is None:
        return {"error": "expiry must be YYYYMMDD or YYYY-MM-DD"}
    if dte <= 0:
        return {"error": "Contract has expired.", "dte": dte}

    mid = ((bid or 0) + (ask or 0)) / 2 if (bid and ask) else None
    sp = spread_pct(bid, ask)
    T = dte / 365.0
    sigma = iv if iv and iv > 0 else 0.30

    g = greeks.greeks(S=spot, K=strike, T=T, r=rate, sigma=sigma, right=right)
    if g.get("error"):
        return g
    delta = g.get("delta")

    # Breakeven is the number that makes a long option honest: it is the move required
    # before you make a cent, and it is always further than it feels.
    cost = mid if mid else g.get("price")
    if right.upper().startswith("C"):
        breakeven = strike + (cost or 0)
        move_needed = (breakeven - spot) / spot * 100 if spot else None
    else:
        breakeven = strike - (cost or 0)
        move_needed = (spot - breakeven) / spot * 100 if spot else None

    blockers: list[str] = []
    if sp is not None and sp > MAX_SPREAD_PCT:
        blockers.append(f"Bid/ask is {sp}% wide - you lose roughly half that on entry and again on exit.")
    if sp is None:
        blockers.append("No two-sided quote; cannot tell what entry costs.")
    if open_interest is not None and open_interest < MIN_OPEN_INTEREST:
        blockers.append(f"Open interest {open_interest} is thin - getting out may cost more than getting in.")
    if volume is not None and volume < MIN_VOLUME:
        blockers.append(f"Only {volume} traded today; this contract barely changes hands.")
    if dte < MIN_DTE:
        blockers.append(f"{dte} days to expiry - theta dominates and the thesis has no time to work.")
    if dte > MAX_DTE:
        blockers.append(f"{dte} days out - capital is tied up and the contract moves little on your move.")
    if delta is not None and not (TARGET_DELTA[0] <= abs(delta) <= TARGET_DELTA[1]):
        if abs(delta) < TARGET_DELTA[0]:
            blockers.append(f"Delta {round(delta, 2)} - this is a lottery ticket, it usually expires worthless.")
        else:
            blockers.append(f"Delta {round(delta, 2)} - you are paying option premium for something close to stock.")

    # greeks.greeks returns "theta" already per calendar day - reading a "theta_per_day"
    # key that does not exist made every contract look like it decayed for free, which
    # is precisely the cost a long option buyer most needs shown to them.
    theta_per_day = g.get("theta")
    daily_burn = abs(theta_per_day or 0) * 100
    cost_dollars = (cost or 0) * 100
    burn_pct = round(100 * daily_burn / cost_dollars, 2) if cost_dollars else None

    return {
        "ok": not blockers,
        "strike": strike,
        "expiry": expiry,
        "right": right.upper()[:1],
        "dte": dte,
        "mid": round(mid, 2) if mid else None,
        "spread_pct": sp,
        "delta": round(delta, 3) if delta is not None else None,
        "theta_per_day": theta_per_day,
        "daily_burn_pct": burn_pct,
        "vega": g.get("vega"),
        "gamma": g.get("gamma"),
        "breakeven": round(breakeven, 2),
        "move_needed_pct": round(move_needed, 2) if move_needed is not None else None,
        "cost_per_contract": round(cost_dollars, 2) if cost else None,
        "delta_shares": round((delta or 0) * 100, 1),
        "open_interest": open_interest,
        "volume": volume,
        "blockers": blockers or None,
        "verdict": (
            "Tradeable." if not blockers
            else f"{len(blockers)} problem(s) before direction even matters."
        ),
    }


def rank(symbol: str, chain: list[dict] | None = None, *, bias: str = "bullish", spot: float = 0.0) -> dict[str, Any]:
    """Score a chain and rank what survives. Bias picks the side, not the standard."""
    right = "C" if str(bias).lower().startswith("bull") else "P"

    if not spot:
        quote = markets.quote(symbol)
        spot = float(quote.get("price") or quote.get("last") or 0) if isinstance(quote, dict) else 0
    if not spot:
        return {"error": f"No spot price for {symbol}; cannot score a chain."}

    if not chain:
        return {
            "error": "No option chain supplied.",
            "how": (
                "Chain data comes from the broker: market action=ibkr mode=option_quotes with the "
                "strikes and expiries you want, then pass them here. This module scores a chain, "
                "it does not fetch one."
            ),
            "spot": spot,
        }

    scored = []
    for c in chain:
        out = score_contract(
            spot=spot,
            strike=float(c.get("strike") or 0),
            expiry=str(c.get("expiry") or ""),
            right=str(c.get("right") or right),
            bid=c.get("bid"), ask=c.get("ask"), iv=c.get("iv"),
            open_interest=c.get("open_interest"), volume=c.get("volume"),
        )
        if out.get("error"):
            continue
        scored.append(out)

    tradeable = [c for c in scored if c["ok"]]
    # Among contracts that clear the bar, prefer the cheapest required move: that is the
    # one that needs the least to be right about.
    tradeable.sort(key=lambda c: (abs(c["move_needed_pct"] or 999), c["spread_pct"] or 99))
    rejected = [c for c in scored if not c["ok"]]

    # The volatility read is advice on structure, not a gate on ranking. If it cannot be
    # fetched, the contract scores still stand on liquidity, delta and breakeven - which
    # are the filters that actually reject trades.
    try:
        vol = iv_rank(symbol)
    except Exception as exc:
        vol = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    structure = None
    if vol.get("ok"):
        structure = (
            "Long single-leg calls: premium is cheap, so paying it is the efficient way to be long."
            if vol["regime"] == "cheap" and right == "C"
            else "Consider a debit spread rather than a naked long: premium is dear and the short leg "
            "pays for part of it, at the cost of capping the upside."
            if vol["regime"] == "expensive"
            else "No volatility edge either way; let liquidity and breakeven decide."
        )

    return {
        "ok": True,
        "symbol": symbol.upper(),
        "spot": round(spot, 2),
        "bias": bias,
        "right": right,
        "considered": len(scored),
        "tradeable": len(tradeable),
        "best": tradeable[0] if tradeable else None,
        "ranked": tradeable[:5],
        "rejected": [{"strike": c["strike"], "expiry": c["expiry"], "why": c["blockers"]} for c in rejected[:8]],
        "volatility": vol if vol.get("ok") else None,
        "structure_advice": structure,
        "note": (
            "Nothing in this chain clears the liquidity, delta and expiry filters. That is a result, "
            "not a failure - the correct number of trades some days is zero."
            if not tradeable else None
        ),
    }


def size(*, risk_budget: float, cost_per_contract: float, stop_pct: float = 50.0) -> dict[str, Any]:
    """How many contracts, from a risk budget and where you would give up.

    Sized off what you would lose at the stop, not off the full premium - assuming total
    loss on every trade sizes every position at a fraction of what the thesis can bear.
    """
    if cost_per_contract <= 0:
        return {"error": "cost_per_contract must be positive."}
    if risk_budget <= 0:
        return {"error": "No risk budget."}
    loss_at_stop = cost_per_contract * (max(1.0, min(stop_pct, 100.0)) / 100.0)
    qty = int(risk_budget // loss_at_stop)
    return {
        "ok": qty > 0,
        "contracts": qty,
        "cost_per_contract": round(cost_per_contract, 2),
        "total_cost": round(qty * cost_per_contract, 2),
        "loss_at_stop_per_contract": round(loss_at_stop, 2),
        "total_risk": round(qty * loss_at_stop, 2),
        "stop_pct": stop_pct,
        "note": (
            f"Sized so a {stop_pct}% loss on the premium costs {round(qty * loss_at_stop, 2)}, "
            "not so total loss costs the budget."
            if qty else
            f"Risk budget {risk_budget} is smaller than one contract's stop loss "
            f"({round(loss_at_stop, 2)}). No position."
        ),
    }


def book() -> dict[str, Any]:
    """Aggregate greeks across open positions. What the portfolio actually is.

    Five separate bullish calls are one big long-delta bet with five theta bills. Netting
    them is the difference between a book and a collection of trades.
    """
    try:
        from . import ibkr

        out = ibkr.pnl()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:150]}"}
    if not out.get("ok"):
        return out

    positions = out.get("positions") or []
    options = [p for p in positions if (p.get("secType") or "").upper() in {"OPT", "FOP"}]
    stock = [p for p in positions if (p.get("secType") or "").upper() in {"STK", ""}]

    long_opts = sum(1 for p in options if (p.get("qty") or 0) > 0)
    short_opts = sum(1 for p in options if (p.get("qty") or 0) < 0)
    gross = sum(abs(float(p.get("market_value") or 0)) for p in positions)

    warnings = []
    if long_opts >= 4:
        warnings.append(
            f"{long_opts} long option positions. Each one pays theta every day; together that is a "
            "standing daily cost that needs the whole book to move, not just one name."
        )
    if len(stock) + len(options) and gross == 0:
        warnings.append("Positions report zero market value - quotes may be stale.")

    return {
        "ok": True,
        "option_positions": len(options),
        "long_options": long_opts,
        "short_options": short_opts,
        "stock_positions": len(stock),
        "gross_exposure": round(gross, 2),
        "unrealized": out.get("total_unrealized"),
        "realized": out.get("total_realized"),
        "positions": options,
        "warnings": warnings or None,
        "note": (
            "Per-position greeks need the option surface from the broker; this is the exposure "
            "shape. Use greeks action=analyze on a contract for its own numbers."
        ),
    }


def dispatch(action: str = "rank", **kwargs: Any) -> Any:
    act = (action or "rank").lower()
    symbol = str(kwargs.get("symbol") or "")
    if act in {"iv", "vol", "iv_rank", "regime"}:
        if not symbol:
            return {"error": "symbol required."}
        return iv_rank(symbol, range_=str(kwargs.get("range") or "1y"))
    if act in {"rank", "select", "pick", "chain"}:
        if not symbol:
            return {"error": "symbol required."}
        return rank(
            symbol,
            kwargs.get("chain"),
            bias=str(kwargs.get("bias") or "bullish"),
            spot=float(kwargs.get("spot") or 0),
        )
    if act in {"score", "contract"}:
        return score_contract(
            spot=float(kwargs.get("spot") or 0),
            strike=float(kwargs.get("strike") or 0),
            expiry=str(kwargs.get("expiry") or ""),
            right=str(kwargs.get("right") or "C"),
            bid=kwargs.get("bid"), ask=kwargs.get("ask"), iv=kwargs.get("iv"),
            open_interest=kwargs.get("open_interest"), volume=kwargs.get("volume"),
        )
    if act in {"size", "contracts"}:
        return size(
            risk_budget=float(kwargs.get("risk_budget") or kwargs.get("risk") or 0),
            cost_per_contract=float(kwargs.get("cost_per_contract") or 0),
            stop_pct=float(kwargs.get("stop_pct") or 50),
        )
    if act in {"book", "portfolio", "exposure"}:
        return book()
    return {"error": f"unknown options action {act}",
            "actions": ["rank", "iv", "score", "size", "book"]}
