"""How often does this actually finish in the money — and how often does it pay?

Those are different questions and the gap between them is where option buyers lose
money without noticing. Three numbers get confused constantly:

  delta        N(d1)   ~ the hedge ratio. Routinely used as "probability ITM". It is
                        not; d1 > d2 always, so delta OVERSTATES it, every time.
  P(ITM)       N(d2)   ~ the chance of finishing past the STRIKE.
  P(profit)    N(d2')  ~ the chance of finishing past the BREAKEVEN, which is the
                        strike plus everything you paid.

Only the third one is the odds on your money. A call that finishes a cent in the money
is a total loss for the buyer, and it counts as a win in the first two. On a 45-day ATM
call the three typically read something like 0.54 / 0.50 / 0.36 — so picking contracts
on delta and calling it a 54% shot overstates the real odds by about half again.

One more thing this module refuses to fake. Under the pricing model the market uses,
the expected value of any option is zero net of premium: that is what makes the price
the price. A positive expectancy comes entirely from your view differing from the
market's - a higher drift, or a belief that implied vol is mispriced. So edge() asks
for that view explicitly rather than inventing one and handing back a number that looks
like free money.
"""

from __future__ import annotations

import math
from typing import Any


def _n(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _guard(S: float, K: float, T: float, sigma: float) -> str | None:
    if S <= 0 or K <= 0:
        return "Spot and strike must both be positive."
    if T <= 0:
        return "Time to expiry must be positive; an expired option has no probability left."
    if sigma <= 0:
        return "Volatility must be positive."
    return None


def p_itm(S: float, K: float, T: float, sigma: float, *, r: float = 0.04, q: float = 0.0,
          right: str = "C", drift: float | None = None) -> dict[str, Any]:
    """Chance of finishing past the strike.

    drift=None uses the risk-neutral rate, which is what an option price implies and
    the honest default. Pass a real-world expected return to ask the different question
    "how often does this land if I am right about the trend" - and treat the answer as
    conditional on being right, which is the part people forget.
    """
    err = _guard(S, K, T, sigma)
    if err:
        return {"error": err}
    mu = r - q if drift is None else drift
    d2 = (math.log(S / K) + (mu - 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    call = _n(d2)
    value = call if str(right).upper().startswith("C") else 1.0 - call
    return {
        "ok": True,
        "p_itm": round(value, 4),
        "d2": round(d2, 4),
        "measure": "risk-neutral" if drift is None else f"real-world drift {drift:.2%}",
    }


def p_profit(S: float, K: float, T: float, sigma: float, premium: float, *, r: float = 0.04,
             q: float = 0.0, right: str = "C", drift: float | None = None) -> dict[str, Any]:
    """Chance of finishing past BREAKEVEN. The only one of the three about your money."""
    err = _guard(S, K, T, sigma)
    if err:
        return {"error": err}
    if premium <= 0:
        return {"error": "Premium must be positive; without it breakeven is just the strike."}

    is_call = str(right).upper().startswith("C")
    breakeven = K + premium if is_call else K - premium
    if breakeven <= 0:
        return {"error": "Breakeven is at or below zero; the put cannot lose."}

    itm = p_itm(S, K, T, sigma, r=r, q=q, right=right, drift=drift)
    be = p_itm(S, breakeven, T, sigma, r=r, q=q, right=right, drift=drift)
    if be.get("error"):
        return be

    mu = r - q if drift is None else drift
    d1 = (math.log(S / K) + (mu + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    delta = _n(d1) if is_call else _n(d1) - 1.0

    move_needed = (breakeven - S) / S if is_call else (S - breakeven) / S
    return {
        "ok": True,
        "p_profit": be["p_itm"],
        "p_itm": itm["p_itm"],
        "delta": round(delta, 4),
        "breakeven": round(breakeven, 2),
        "move_needed_pct": round(move_needed * 100, 2),
        "measure": be["measure"],
        "gap": {
            "delta_minus_p_itm": round(abs(delta) - itm["p_itm"], 4),
            "p_itm_minus_p_profit": round(itm["p_itm"] - be["p_itm"], 4),
            "note": (
                "Delta always reads higher than the real chance of finishing in the money, and "
                "finishing in the money is not the same as making money. The number that matters "
                "is p_profit."
            ),
        },
    }


def p_touch(S: float, K: float, T: float, sigma: float, *, r: float = 0.04, q: float = 0.0) -> dict[str, Any]:
    """Chance price TOUCHES the level before expiry, not just closes past it.

    Roughly twice the chance of finishing there, and it is the number that matters for
    a stop: a stop is hit on the way past, not at the bell.
    """
    err = _guard(S, K, T, sigma)
    if err:
        return {"error": err}
    mu = r - q - 0.5 * sigma * sigma
    vol_t = sigma * math.sqrt(T)
    log_ratio = math.log(K / S)
    a = (-abs(log_ratio) + mu * T) / vol_t
    b = (-abs(log_ratio) - mu * T) / vol_t
    exponent = 2 * mu * abs(log_ratio) / (sigma * sigma)
    # Cap the exponent: a far barrier overflows the exp and the answer there is ~0 anyway.
    scale = math.exp(min(exponent, 700.0))
    prob = min(1.0, max(0.0, _n(a) + scale * _n(b)))
    return {
        "ok": True,
        "p_touch": round(prob, 4),
        "level": K,
        "note": "Probability of trading through the level at any point, not of closing past it.",
    }


def edge(S: float, K: float, T: float, sigma: float, premium: float, *, r: float = 0.04,
         q: float = 0.0, right: str = "C", expected_move_pct: float | None = None,
         expected_vol: float | None = None) -> dict[str, Any]:
    """What this trade is worth, given a view you supply.

    Without a view there is nothing to compute. At the market's own implied vol and
    drift, the expected value of any option is zero net of premium - that is what makes
    the price the price. So this asks what you think differs, and prices that. If you
    have no such view, the honest expected value of buying premium is negative by the
    spread, and it says so rather than inventing an edge.
    """
    err = _guard(S, K, T, sigma)
    if err:
        return {"error": err}
    if premium <= 0:
        return {"error": "Premium must be positive."}

    is_call = str(right).upper().startswith("C")
    if expected_move_pct is None and expected_vol is None:
        base = p_profit(S, K, T, sigma, premium, r=r, q=q, right=right)
        return {
            "ok": True,
            "expected_value": None,
            "p_profit": base.get("p_profit"),
            "verdict": (
                "No view supplied, so there is no edge to compute. At the market's own implied "
                "volatility the expected value of this contract is zero before costs and negative "
                "after them. Buying it is a bet that the market's assumption is wrong - say how, "
                "with expected_move_pct or expected_vol, and this can price it."
            ),
        }

    drift = None
    if expected_move_pct is not None:
        # Annualise the move the user expects over the life of the option.
        drift = math.log(1 + expected_move_pct / 100.0) / T
    vol = expected_vol if expected_vol and expected_vol > 0 else sigma

    # Expected payoff under the user's own view, by numerical integration over the
    # terminal lognormal. Simple, transparent, and easy to check by hand.
    mu = (drift if drift is not None else r - q) - 0.5 * vol * vol
    steps, span = 400, 5.0
    total = 0.0
    lo, hi = -span, span
    step = (hi - lo) / steps
    for i in range(steps):
        z = lo + step * (i + 0.5)
        ST = S * math.exp(mu * T + vol * math.sqrt(T) * z)
        payoff = max(0.0, ST - K) if is_call else max(0.0, K - ST)
        density = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        total += payoff * density * step

    ev_per_share = total * math.exp(-r * T) - premium
    ev_contract = ev_per_share * 100
    return {
        "ok": True,
        "expected_payoff": round(total, 4),
        "premium": round(premium, 4),
        "expected_value_per_share": round(ev_per_share, 4),
        "expected_value_per_contract": round(ev_contract, 2),
        "edge_pct_of_premium": round(100 * ev_per_share / premium, 1),
        "view": {
            "expected_move_pct": expected_move_pct,
            "expected_vol": expected_vol,
            "implied_vol": sigma,
            "drift_annualised": round(drift, 4) if drift is not None else None,
        },
        "verdict": (
            f"Positive expectancy of {round(ev_contract, 2)} per contract - but ONLY if your view "
            "is right. This is arithmetic on your assumption, not evidence for it."
            if ev_per_share > 0
            else f"Negative expectancy of {round(ev_contract, 2)} per contract even on your own view. "
            "The premium is too high for the move you expect."
        ),
        "caveat": "Excludes commission and the bid/ask you cross on both sides.",
    }


def compare(S: float, T: float, sigma: float, strikes: list[float], premiums: list[float] | None = None,
            *, r: float = 0.04, right: str = "C") -> dict[str, Any]:
    """Rank strikes by the odds that matter, side by side with the ones that flatter."""
    rows = []
    for i, K in enumerate(strikes):
        prem = premiums[i] if premiums and i < len(premiums) else None
        if prem:
            out = p_profit(S, K, T, sigma, prem, r=r, right=right)
            if out.get("error"):
                continue
            rows.append({
                "strike": K, "premium": prem,
                "delta": out["delta"], "p_itm": out["p_itm"], "p_profit": out["p_profit"],
                "breakeven": out["breakeven"], "move_needed_pct": out["move_needed_pct"],
            })
        else:
            out = p_itm(S, K, T, sigma, r=r, right=right)
            if out.get("error"):
                continue
            rows.append({"strike": K, "p_itm": out["p_itm"], "premium": None})
    rows.sort(key=lambda x: x.get("p_profit") if x.get("p_profit") is not None else x.get("p_itm", 0), reverse=True)
    return {
        "ok": True,
        "spot": S,
        "right": right,
        "ranked": rows,
        "best": rows[0] if rows else None,
        "note": (
            "Ranked on p_profit where a premium was given, p_itm otherwise. Compare the delta "
            "column against p_profit to see how much picking on delta would have flattered the odds."
        ),
    }


def dispatch(action: str = "profit", **kwargs: Any) -> Any:
    act = (action or "profit").lower()
    S = float(kwargs.get("spot") or kwargs.get("S") or 0)
    K = float(kwargs.get("strike") or kwargs.get("K") or 0)
    T = float(kwargs.get("T") or 0) or (float(kwargs.get("dte") or 0) / 365.0)
    sigma = float(kwargs.get("iv") or kwargs.get("sigma") or 0)
    r = float(kwargs.get("r") or 0.04)
    right = str(kwargs.get("right") or "C")
    premium = float(kwargs.get("premium") or 0)

    if act in {"itm", "p_itm"}:
        return p_itm(S, K, T, sigma, r=r, right=right, drift=kwargs.get("drift"))
    if act in {"profit", "p_profit", "pop"}:
        return p_profit(S, K, T, sigma, premium, r=r, right=right, drift=kwargs.get("drift"))
    if act in {"touch", "p_touch"}:
        return p_touch(S, K, T, sigma, r=r)
    if act in {"edge", "ev", "value"}:
        return edge(S, K, T, sigma, premium, r=r, right=right,
                    expected_move_pct=kwargs.get("expected_move_pct"),
                    expected_vol=kwargs.get("expected_vol"))
    if act in {"compare", "strikes", "ladder"}:
        return compare(S, T, sigma, kwargs.get("strikes") or [], kwargs.get("premiums"), r=r, right=right)
    return {"error": f"unknown probability action {act}",
            "actions": ["itm", "profit", "touch", "edge", "compare"]}
