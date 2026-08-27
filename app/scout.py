"""Which option is the best trade right now — decided by what the stock actually does.

A 7-day and a 45-day contract cannot be compared on price, or on delta, or on gut feel.
They need a common currency, and there is one that requires no opinion at all:

    the move the contract needs, against how often this stock has ACTUALLY made a move
    that size over that exact horizon.

That is a base rate measured off real bars. It needs no view, no forecast and no
assumption about the shape of returns - which matters, because the model alternative
(N(d2)) assumes prices are lognormal, and real stocks gap, trend and have fat tails
that a lognormal flatly denies. Where the two disagree, the disagreement is itself the
information: the model is not wrong so much as it is describing a different stock.

So every candidate, at every expiry from 7 to 60 days, is scored on the same axis:

    empirical P(profit)  how often this name has cleared this breakeven in this many days
    model P(profit)      what Black-Scholes says, for comparison
    cost                 spread and premium, which come off the top either way
    edge_vs_model        where the two disagree, and by how much

Nothing here forecasts. It reports what has happened at this distance and this horizon,
counts it honestly, and says how thin the sample is - because a base rate from eleven
overlapping windows is not a probability, it is an anecdote with a decimal point.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import markets, options, probability

# Overlapping windows share bars, so they are not independent observations. 200 of them
# might carry the information of 20. That does not make the base rate useless - it makes
# the confidence interval wider than the count suggests, and it must be said out loud.
MIN_WINDOWS = 60
THIN_WINDOWS = 150


def move_base_rate(bars: list[dict], move_pct: float, horizon: int, *, direction: str = "up") -> dict[str, Any]:
    """How often has this name moved this far, this fast?

    Every overlapping window of `horizon` sessions, counting the fraction that closed at
    least `move_pct` away in `direction`. Uses closes for the endpoint and the running
    high/low for whether it ever got there, because an option can be sold on the way -
    you are not obliged to hold to expiry.
    """
    closes = [b["close"] for b in bars if b.get("close")]
    if horizon <= 0:
        return {"error": "horizon must be positive"}
    if len(closes) < horizon + MIN_WINDOWS:
        return {
            "error": (
                f"Only {len(closes)} bars; a {horizon}-day horizon needs at least "
                f"{horizon + MIN_WINDOWS} to produce a base rate worth quoting."
            )
        }

    up = direction == "up"
    target = move_pct / 100.0
    hit_close = 0
    hit_touch = 0
    windows = 0

    highs = [b.get("high") or b["close"] for b in bars if b.get("close")]
    lows = [b.get("low") or b["close"] for b in bars if b.get("close")]

    for i in range(len(closes) - horizon):
        start = closes[i]
        if start <= 0:
            continue
        windows += 1
        end = closes[i + horizon]
        moved = (end - start) / start if up else (start - end) / start
        if moved >= target:
            hit_close += 1
        # Did it EVER get there during the window?
        if up:
            best = max(highs[i + 1 : i + horizon + 1] or [start])
            touched = (best - start) / start
        else:
            worst = min(lows[i + 1 : i + horizon + 1] or [start])
            touched = (start - worst) / start
        if touched >= target:
            hit_touch += 1

    if not windows:
        return {"error": "No usable windows."}

    rate = hit_close / windows
    return {
        "ok": True,
        "base_rate": round(rate, 4),
        "touch_rate": round(hit_touch / windows, 4),
        "hits": hit_close,
        "windows": windows,
        "horizon_days": horizon,
        "move_pct": round(move_pct, 2),
        "direction": direction,
        "confidence": (
            "thin - treat as anecdote" if windows < THIN_WINDOWS else "reasonable"
        ),
        "caveat": (
            "Overlapping windows share bars, so they are not independent. The true "
            "confidence interval is wider than the window count implies."
        ),
    }


def evaluate(symbol: str, contract: dict, *, bars: list[dict] | None = None,
             range_: str = "3y") -> dict[str, Any]:
    """One contract, scored on what the stock has actually done."""
    if bars is None:
        hist = markets.history(symbol, range_)
        if hist.get("error"):
            return hist
        bars = [b for b in (hist.get("bars") or []) if b.get("close")]
    if not bars:
        return {"error": f"No price history for {symbol}."}

    spot = float(contract.get("spot") or bars[-1]["close"])
    scored = options.score_contract(
        spot=spot,
        strike=float(contract.get("strike") or 0),
        expiry=str(contract.get("expiry") or ""),
        right=str(contract.get("right") or "C"),
        bid=contract.get("bid"), ask=contract.get("ask"), iv=contract.get("iv"),
        open_interest=contract.get("open_interest"), volume=contract.get("volume"),
    )
    if scored.get("error"):
        return scored

    dte = scored["dte"]
    move_needed = scored["move_needed_pct"]
    is_call = scored["right"] == "C"
    # Calendar days to trading sessions: roughly 5 per 7.
    horizon = max(1, int(round(dte * 5 / 7)))

    empirical = move_base_rate(bars, move_needed, horizon, direction="up" if is_call else "down")

    iv = contract.get("iv") or 0.30
    premium = scored.get("mid") or 0
    model = probability.p_profit(
        spot, float(contract["strike"]), dte / 365.0, float(iv), float(premium or 0.01),
        right="C" if is_call else "P",
    ) if premium else {"error": "no premium"}

    emp = empirical.get("base_rate")
    mod = model.get("p_profit")
    disagreement = round(emp - mod, 4) if (emp is not None and mod is not None) else None

    read = None
    if disagreement is not None:
        if disagreement > 0.08:
            read = (
                "History clears this breakeven more often than the model expects. The lognormal "
                "assumption is understating this name's tail or its drift."
            )
        elif disagreement < -0.08:
            read = (
                "History clears this breakeven LESS often than the model expects. The option is "
                "priced for a move this stock has not reliably made."
            )
        else:
            read = "Model and history broadly agree on the odds."

    return {
        "ok": True,
        "symbol": symbol.upper(),
        "strike": scored["strike"],
        "expiry": scored["expiry"],
        "right": scored["right"],
        "dte": dte,
        "horizon": scored["horizon"],
        "cost_per_contract": scored["cost_per_contract"],
        "spread_pct": scored["spread_pct"],
        "daily_burn_pct": scored["daily_burn_pct"],
        "breakeven": scored["breakeven"],
        "move_needed_pct": move_needed,
        "delta": scored["delta"],
        "empirical": empirical if empirical.get("ok") else {"error": empirical.get("error")},
        "model_p_profit": mod,
        "empirical_p_profit": emp,
        "touch_rate": empirical.get("touch_rate"),
        "edge_vs_model": disagreement,
        # Two contracts can carry the same odds at very different prices. Odds alone
        # ranks them equal; this is what separates them, and it is usually the shorter
        # expiry that wins on it - the reason to prefer the longer one is surviving
        # being early, which is a real reason but a different one.
        "odds_per_100_risked": (
            round(emp / (scored["cost_per_contract"] / 100.0), 4)
            if emp and scored.get("cost_per_contract") else None
        ),
        "read": read,
        "tradeable": scored["ok"],
        "blockers": scored.get("blockers"),
    }


def _expiries(min_dte: int, max_dte: int, step: int = 7) -> list[str]:
    """Candidate expiry dates across the window, snapped to Fridays."""
    out, today = [], dt.date.today()
    d = min_dte
    while d <= max_dte:
        day = today + dt.timedelta(days=d)
        day += dt.timedelta(days=(4 - day.weekday()) % 7)  # next Friday
        iso = day.strftime("%Y%m%d")
        if iso not in out and (day - today).days <= max_dte:
            out.append(iso)
        d += step
    return out


def hunt(symbol: str, *, bias: str = "auto", min_dte: int = 7, max_dte: int = 60,
         range_: str = "3y", chain: list[dict] | None = None) -> dict[str, Any]:
    """The best available trade on one symbol, across the whole expiry window.

    With a broker chain, scores the real contracts. Without one, models a synthetic
    ladder so the SHAPE of the opportunity is visible - which expiry and which distance
    the history favours - and says plainly that the prices are theoretical.
    """
    hist = markets.history(symbol, range_)
    if hist.get("error"):
        return hist
    bars = [b for b in (hist.get("bars") or []) if b.get("close")]
    if len(bars) < 120:
        return {"error": f"Only {len(bars)} bars for {symbol}; need 120+ to measure base rates."}
    spot = bars[-1]["close"]

    vol = options.iv_rank(symbol, range_="1y")
    sigma = (vol.get("realized_vol") or 30.0) / 100.0 if vol.get("ok") else 0.30

    if bias == "auto":
        # Direction from the data, not from a standing preference: where is price
        # relative to its own trend?
        closes = [b["close"] for b in bars]
        sma50 = sum(closes[-50:]) / 50
        sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sma50
        bias = "bullish" if (spot > sma50 and sma50 >= sma200) else "bearish" if spot < sma50 else "bullish"
    is_call = bias.startswith("bull")
    right = "C" if is_call else "P"

    candidates: list[dict] = []
    if chain:
        candidates = list(chain)
        synthetic = False
    else:
        synthetic = True
        from . import greeks

        for expiry in _expiries(min_dte, max_dte):
            dte = (dt.date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:])) - dt.date.today()).days
            for pct in (0.0, 0.02, 0.05, 0.08):
                strike = round(spot * (1 + pct) if is_call else spot * (1 - pct), 0)
                theo = greeks.price(S=spot, K=strike, T=dte / 365.0, r=0.04, sigma=sigma, right=right)
                # greeks.price returns a bare float. An isinstance(dict) check here
                # silently dropped every candidate and the hunt found nothing at all.
                if isinstance(theo, dict):
                    mid = theo.get("price") if theo.get("ok", True) else None
                else:
                    try:
                        mid = float(theo)
                    except (TypeError, ValueError):
                        mid = None
                if not mid or mid <= 0.05:
                    continue
                candidates.append({
                    "strike": strike, "expiry": expiry, "right": right,
                    "bid": round(mid * 0.99, 2), "ask": round(mid * 1.01, 2),
                    "iv": sigma, "open_interest": 1000, "volume": 100, "spot": spot,
                })

    scored = []
    for c in candidates:
        c.setdefault("spot", spot)
        out = evaluate(symbol, c, bars=bars)
        if out.get("ok") and out.get("empirical_p_profit") is not None:
            scored.append(out)

    tradeable = [c for c in scored if c["tradeable"]]
    # Rank on what history says, then on what it costs to find out.
    tradeable.sort(key=lambda c: (c["empirical_p_profit"], -(c["spread_pct"] or 99)), reverse=True)

    # Same odds at a lower price is strictly better, and ranking on odds alone hides it.
    best_value = max(
        (c for c in tradeable if c.get("odds_per_100_risked")),
        key=lambda c: c["odds_per_100_risked"], default=None,
    )
    value_note = None
    if best_value and tradeable and best_value is not tradeable[0]:
        top = tradeable[0]
        gap = round((top["empirical_p_profit"] - best_value["empirical_p_profit"]) * 100, 1)
        value_note = (
            f"{best_value['dte']}d {best_value['strike']}{best_value['right']} gives "
            f"{best_value['empirical_p_profit'] * 100:.1f}% for ${best_value['cost_per_contract']}, against "
            f"{top['empirical_p_profit'] * 100:.1f}% for ${top['cost_per_contract']} on the top-ranked one - "
            f"{gap:+.1f} points of probability for "
            f"${round(top['cost_per_contract'] - best_value['cost_per_contract'], 2)} more. "
            "The longer expiry buys time to be early, which is worth something; decide whether it is worth that."
        )

    return {
        "ok": True,
        "symbol": symbol.upper(),
        "spot": round(spot, 2),
        "bias": bias,
        "bias_source": "trend vs 50/200-day" if bias else None,
        "window_dte": [min_dte, max_dte],
        "volatility": {k: vol.get(k) for k in ("realized_vol", "iv_rank", "regime", "estimator")} if vol.get("ok") else None,
        "considered": len(scored),
        "tradeable": len(tradeable),
        "best": tradeable[0] if tradeable else None,
        "best_value": best_value,
        "value_note": value_note,
        "ranked": tradeable[:8],
        "synthetic_prices": synthetic,
        "note": (
            "No broker chain supplied, so prices are Black-Scholes theoretical at realized vol. "
            "The RANKING is still informative - it shows which expiry and distance this name's own "
            "history favours - but the premiums are not quotes. Pass a real chain to trade off it."
            if synthetic else None
        ),
        "how_ranked": (
            "By empirical probability of clearing breakeven: how often this stock has actually "
            "made the required move over the required horizon, measured on overlapping windows of "
            "its own history. No forecast, no view."
        ),
    }


def dispatch(action: str = "hunt", **kwargs: Any) -> Any:
    act = (action or "hunt").lower()
    symbol = str(kwargs.get("symbol") or "")
    if act in {"hunt", "best", "scan", "find"}:
        if not symbol:
            return {"error": "symbol required."}
        return hunt(
            symbol,
            bias=str(kwargs.get("bias") or "auto"),
            min_dte=int(kwargs.get("min_dte") or 7),
            max_dte=int(kwargs.get("max_dte") or 60),
            range_=str(kwargs.get("range") or "3y"),
            chain=kwargs.get("chain"),
        )
    if act in {"base_rate", "odds", "history"}:
        hist = markets.history(symbol, str(kwargs.get("range") or "3y"))
        if hist.get("error"):
            return hist
        bars = [b for b in (hist.get("bars") or []) if b.get("close")]
        return move_base_rate(
            bars,
            float(kwargs.get("move_pct") or 5),
            int(kwargs.get("horizon") or 21),
            direction=str(kwargs.get("direction") or "up"),
        )
    if act in {"evaluate", "score"}:
        return evaluate(symbol, kwargs.get("contract") or {}, range_=str(kwargs.get("range") or "3y"))
    return {"error": f"unknown scout action {act}", "actions": ["hunt", "base_rate", "evaluate"]}
