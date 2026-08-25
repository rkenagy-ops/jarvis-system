"""Black-Scholes greeks and implied volatility.

place_option() and marketbeast pick contracts and send orders without computing a
single greek. That means position size is guesswork: two 1-lots with the same premium
can carry wildly different directional exposure, and nothing in the system could tell
them apart. A 0.15-delta contract and a 0.85-delta contract are not the same trade.

Implemented directly rather than pulling a library, because the whole model is about
sixty lines of stdlib maths and a dependency that fails to install on Windows is worth
more trouble than it saves. py_vollib and opengreeks are indexed if you later want a
faster or better-validated engine; this is the one that always works.

Conventions, since they differ between sources:
  theta  per calendar DAY, not per year. Traders quote it that way.
  vega   per 1 volatility POINT (a move from 20% to 21%), not per 1.0.
  rho    per 1 interest-rate point.
  T      in years. days_to_expiry / 365.
"""

from __future__ import annotations

import math
from typing import Any

# A contract is 100 shares. Getting this wrong is the classic sizing error.
CONTRACT_MULTIPLIER = 100

MAX_ITER = 100
IV_TOLERANCE = 1e-6
MIN_VOL, MAX_VOL = 1e-4, 5.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _right(right: str) -> str:
    return "C" if str(right or "C").upper().startswith("C") else "P"


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> tuple[float, float]:
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    return d1, d1 - vt


def _validate(S: float, K: float, T: float, sigma: float | None = None) -> str | None:
    if S <= 0:
        return "spot must be positive"
    if K <= 0:
        return "strike must be positive"
    if T <= 0:
        return "time to expiry must be positive (expired options have no greeks)"
    if sigma is not None and sigma <= 0:
        return "volatility must be positive"
    return None


def price(
    S: float, K: float, T: float, r: float = 0.045, sigma: float = 0.2, right: str = "C", q: float = 0.0
) -> float:
    """Black-Scholes-Merton fair value for one share of the option."""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc, carry = math.exp(-r * T), math.exp(-q * T)
    if _right(right) == "C":
        return S * carry * _norm_cdf(d1) - K * disc * _norm_cdf(d2)
    return K * disc * _norm_cdf(-d2) - S * carry * _norm_cdf(-d1)


def greeks(
    S: float, K: float, T: float, r: float = 0.045, sigma: float = 0.2, right: str = "C", q: float = 0.0
) -> dict[str, Any]:
    """Every greek for one share. Multiply by 100 for a contract."""
    err = _validate(S, K, T, sigma)
    if err:
        return {"error": err}

    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc, carry = math.exp(-r * T), math.exp(-q * T)
    pdf = _norm_pdf(d1)
    sqrt_t = math.sqrt(T)
    call = _right(right) == "C"

    delta = carry * (_norm_cdf(d1) if call else _norm_cdf(d1) - 1.0)
    gamma = carry * pdf / (S * sigma * sqrt_t)
    vega = S * carry * pdf * sqrt_t

    # Theta per year, then converted to per day below.
    term = -(S * carry * pdf * sigma) / (2 * sqrt_t)
    if call:
        theta_y = term - r * K * disc * _norm_cdf(d2) + q * S * carry * _norm_cdf(d1)
        rho = K * T * disc * _norm_cdf(d2)
    else:
        theta_y = term + r * K * disc * _norm_cdf(-d2) - q * S * carry * _norm_cdf(-d1)
        rho = -K * T * disc * _norm_cdf(-d2)

    return {
        "ok": True,
        "price": round(price(S, K, T, r, sigma, right, q), 4),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega / 100.0, 4),  # per 1 vol point
        "theta": round(theta_y / 365.0, 4),  # per day
        "rho": round(rho / 100.0, 4),  # per 1 rate point
        "d1": round(d1, 4),
        "d2": round(d2, 4),
        "inputs": {"S": S, "K": K, "T": round(T, 6), "r": r, "sigma": sigma, "right": _right(right), "q": q},
    }


def implied_vol(
    market_price: float, S: float, K: float, T: float, r: float = 0.045, right: str = "C", q: float = 0.0
) -> dict[str, Any]:
    """Back out the volatility the market is pricing in.

    Newton-Raphson, falling back to bisection. Newton is fast but its vega denominator
    collapses far from the money, so it can diverge exactly where deep OTM contracts
    live — which is where a lot of these trades sit.
    """
    err = _validate(S, K, T)
    if err:
        return {"error": err}
    if market_price <= 0:
        return {"error": "market price must be positive"}

    # No volatility can price below intrinsic; asking is a data problem, not a solve.
    carry, disc = math.exp(-q * T), math.exp(-r * T)
    intrinsic = max(0.0, (S * carry - K * disc) if _right(right) == "C" else (K * disc - S * carry))
    if market_price < intrinsic - 1e-8:
        return {
            "error": f"price {market_price} is below intrinsic {intrinsic:.4f}; no volatility can produce it",
            "intrinsic": round(intrinsic, 4),
        }

    sigma = 0.25
    for _ in range(MAX_ITER):
        theo = price(S, K, T, r, sigma, right, q)
        diff = theo - market_price
        if abs(diff) < IV_TOLERANCE:
            return {"ok": True, "iv": round(sigma, 6), "iv_pct": round(sigma * 100, 2), "method": "newton"}
        d1, _ = _d1_d2(S, K, T, r, sigma, q)
        vega = S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)
        if vega < 1e-8:
            break
        sigma -= diff / vega
        if not (MIN_VOL < sigma < MAX_VOL):
            break

    lo, hi = MIN_VOL, MAX_VOL
    for _ in range(MAX_ITER):
        mid = (lo + hi) / 2
        diff = price(S, K, T, r, mid, right, q) - market_price
        if abs(diff) < IV_TOLERANCE:
            return {"ok": True, "iv": round(mid, 6), "iv_pct": round(mid * 100, 2), "method": "bisection"}
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return {"error": "implied volatility did not converge", "last": round((lo + hi) / 2, 6)}


def analyze(
    *,
    symbol: str = "",
    spot: float,
    strike: float,
    days: float,
    right: str = "C",
    premium: float | None = None,
    sigma: float | None = None,
    rate: float = 0.045,
    dividend: float = 0.0,
    qty: int = 1,
) -> dict[str, Any]:
    """The whole picture for one contract, in the units a trade actually uses."""
    if days <= 0:
        return {"error": "days to expiry must be positive"}
    T = days / 365.0

    iv_info = None
    if sigma is None:
        if premium is None:
            return {"error": "give either sigma (to price it) or premium (to solve for IV)."}
        iv_info = implied_vol(premium, spot, strike, T, rate, right, dividend)
        if not iv_info.get("ok"):
            return iv_info
        sigma = iv_info["iv"]

    g = greeks(spot, strike, T, rate, sigma, right, dividend)
    if not g.get("ok"):
        return g

    contracts = abs(int(qty)) or 1
    shares = contracts * CONTRACT_MULTIPLIER
    theo = g["price"]
    mark = premium if premium is not None else theo

    moneyness = spot / strike
    call = _right(right) == "C"
    if abs(moneyness - 1) < 0.02:
        position = "at the money"
    elif (call and moneyness > 1) or (not call and moneyness < 1):
        position = "in the money"
    else:
        position = "out of the money"

    notes = []
    if abs(g["delta"]) < 0.20:
        notes.append(
            f"Delta {g['delta']} — a low-probability contract. Most of the premium is time value, "
            "and it decays whether or not you are right about direction."
        )
    if g["theta"] * shares < -0.02 * mark * shares:
        notes.append(
            f"Theta costs about {abs(g['theta'] * shares):.2f} per day on this position, "
            f"roughly {abs(g['theta'] / mark) * 100:.1f}% of premium daily."
        )
    if days < 7:
        notes.append(f"{days:.0f} days to expiry — gamma and theta both accelerate sharply from here.")
    if premium is not None and theo > 0:
        edge = (premium - theo) / theo
        if abs(edge) > 0.15:
            notes.append(
                f"Mark {premium} vs model {theo} ({edge:+.0%}). Either the model inputs are off "
                "(check the rate and any dividend) or the market disagrees with this volatility."
            )

    return {
        "ok": True,
        "symbol": symbol.upper() or None,
        "contract": f"{symbol.upper()} {strike}{_right(right)} {days:.0f}d" if symbol else None,
        "position": position,
        "moneyness": round(moneyness, 4),
        "days_to_expiry": days,
        "iv": iv_info,
        "sigma_used": round(sigma, 6),
        "per_share": {k: g[k] for k in ("price", "delta", "gamma", "vega", "theta", "rho")},
        "per_contract": {
            "price": round(theo * CONTRACT_MULTIPLIER, 2),
            "delta": round(g["delta"] * CONTRACT_MULTIPLIER, 2),
            "gamma": round(g["gamma"] * CONTRACT_MULTIPLIER, 4),
            "vega": round(g["vega"] * CONTRACT_MULTIPLIER, 2),
            "theta": round(g["theta"] * CONTRACT_MULTIPLIER, 2),
        },
        "position_totals": {
            "contracts": contracts,
            "cost": round(mark * shares, 2),
            "max_loss": round(mark * shares, 2),
            "delta_shares": round(g["delta"] * shares, 1),
            "theta_per_day": round(g["theta"] * shares, 2),
            "vega_per_vol_point": round(g["vega"] * shares, 2),
        },
        "notes": notes,
        "note": (
            "Delta-shares is the equivalent stock exposure — that is the number to size against, "
            "not the contract count."
        ),
    }


def size_by_risk(
    *, spot: float, strike: float, days: float, premium: float, risk_budget: float, right: str = "C", rate: float = 0.045
) -> dict[str, Any]:
    """How many contracts fit a dollar risk budget.

    A long option's max loss is the premium, so the count follows directly — the useful
    part is what delta exposure that quietly buys you.
    """
    if premium <= 0:
        return {"error": "premium must be positive"}
    if risk_budget <= 0:
        return {"error": "risk budget must be positive"}

    per_contract = premium * CONTRACT_MULTIPLIER
    contracts = int(risk_budget // per_contract)
    if contracts < 1:
        return {
            "ok": True,
            "contracts": 0,
            "reason": f"one contract costs {per_contract:.2f}, over the {risk_budget:.2f} budget",
        }

    detail = analyze(
        spot=spot, strike=strike, days=days, right=right, premium=premium, rate=rate, qty=contracts
    )
    if not detail.get("ok"):
        return detail
    return {
        "ok": True,
        "contracts": contracts,
        "cost": round(contracts * per_contract, 2),
        "max_loss": round(contracts * per_contract, 2),
        "budget_used_pct": round(contracts * per_contract / risk_budget * 100, 1),
        "delta_shares": detail["position_totals"]["delta_shares"],
        "theta_per_day": detail["position_totals"]["theta_per_day"],
        "iv_pct": (detail.get("iv") or {}).get("iv_pct"),
        "note": (
            f"{contracts} contracts carry the directional exposure of "
            f"{detail['position_totals']['delta_shares']:.0f} shares."
        ),
    }


def dispatch(action: str = "analyze", **kwargs: Any) -> Any:
    act = (action or "analyze").lower()
    try:
        if act in {"analyze", "greeks", "contract"}:
            return analyze(
                symbol=str(kwargs.get("symbol") or ""),
                spot=float(kwargs.get("spot") or kwargs.get("price") or 0),
                strike=float(kwargs.get("strike") or 0),
                days=float(kwargs.get("days") or kwargs.get("dte") or 0),
                right=str(kwargs.get("right") or "C"),
                premium=float(kwargs["premium"]) if kwargs.get("premium") is not None else None,
                sigma=float(kwargs["sigma"]) if kwargs.get("sigma") is not None else None,
                rate=float(kwargs.get("rate") or 0.045),
                dividend=float(kwargs.get("dividend") or 0.0),
                qty=int(kwargs.get("qty") or 1),
            )
        if act in {"iv", "implied_vol", "implied"}:
            return implied_vol(
                float(kwargs.get("premium") or 0),
                float(kwargs.get("spot") or 0),
                float(kwargs.get("strike") or 0),
                float(kwargs.get("days") or 0) / 365.0,
                float(kwargs.get("rate") or 0.045),
                str(kwargs.get("right") or "C"),
                float(kwargs.get("dividend") or 0.0),
            )
        if act in {"size", "size_by_risk"}:
            return size_by_risk(
                spot=float(kwargs.get("spot") or 0),
                strike=float(kwargs.get("strike") or 0),
                days=float(kwargs.get("days") or 0),
                premium=float(kwargs.get("premium") or 0),
                risk_budget=float(kwargs.get("risk") or kwargs.get("risk_budget") or 0),
                right=str(kwargs.get("right") or "C"),
                rate=float(kwargs.get("rate") or 0.045),
            )
    except (TypeError, ValueError) as exc:
        return {"error": f"bad numeric input: {exc}"}
    return {"error": f"unknown greeks action {act}", "actions": ["analyze", "iv", "size"]}
