"""Named market setups: detect them, explain them, and turn them into a sized trade plan.

markets.advise gives an ENTER/NO-GO verdict. This goes the other way — it names WHICH
setup is present, teaches what it is and what kills it, and hands back concrete levels
(entry, stop, target, share count from your risk budget) that drop straight into
ibkr.place_bracket.

    setups action=scan   symbol=AAPL          -> which setups are live right now
    setups action=teach  setup=trend_pullback -> what it is and how it fails
    setups action=plan   symbol=AAPL setup=trend_pullback risk=500

These are technical heuristics computed off daily bars. They describe what price has
already done and where a defined-risk trade would sit — not what happens next. Every
plan carries an explicit invalidation level for exactly that reason.
"""

from __future__ import annotations

from typing import Any

from . import markets

# --------------------------------------------------------------------------- teaching


CATALOG: dict[str, dict[str, str]] = {
    "trend_pullback": {
        "name": "Trend pullback",
        "idea": (
            "An established uptrend pauses and pulls back into its 20-day average. You are "
            "buying the pause, not the breakout, so your stop sits close and the reward-to-risk "
            "is better than chasing."
        ),
        "why": (
            "Trends move in steps. Pullbacks shake out weak holders while the higher-timeframe "
            "structure (price above the 50-day) is still intact."
        ),
        "trigger": "Price reclaims the prior day's high after tagging the 20-day average.",
        "invalidation": "A close below the 50-day average. The premise was 'trend intact' — that ends it.",
        "stop_rule": "Below the recent swing low, or 1.5x ATR under entry, whichever is tighter.",
        "target_rule": "The prior swing high first; measured move (depth of the base added to the breakout) beyond it.",
        "fails_when": (
            "The pullback is actually the start of a reversal. The tell is volume expanding on "
            "the down days rather than drying up."
        ),
    },
    "breakout_20d": {
        "name": "20-day breakout",
        "idea": "Price closes above its highest level in 20 sessions, ideally on heavier volume.",
        "why": "A new 20-day high means every buyer in that window is profitable — little overhead supply left to sell into.",
        "trigger": "Daily close above the 20-day high.",
        "invalidation": "A close back inside the range. A breakout that reverses is a failed breakout, not a discount.",
        "stop_rule": "Below the breakout level itself, or below the base low if the base is tight.",
        "target_rule": "Height of the base projected up from the breakout point.",
        "fails_when": (
            "Volume is light and the broader market is weak — those are the ones that snap back "
            "immediately. Breakouts work in bulk, not individually."
        ),
    },
    "oversold_in_uptrend": {
        "name": "Oversold in an uptrend",
        "idea": "RSI drops under 35 while price is still above the long-term average — a stretched pullback, not a downtrend.",
        "why": "Mean reversion has an edge only when the larger trend is up. Oversold in a downtrend just gets more oversold.",
        "trigger": "RSI turns back up from below 35 with price still above the 50-day.",
        "invalidation": "Losing the 50-day average closes the case.",
        "stop_rule": "Below the low of the oversold bar, or 2x ATR — these need room.",
        "target_rule": "Back to the 20-day average. This is a snapback, not a trend entry.",
        "fails_when": "You use it on a stock in a real downtrend. The 50-day filter exists to stop that.",
    },
    "momentum_cross": {
        "name": "MACD momentum cross",
        "idea": "The MACD line crosses above its signal while price holds above the 50-day.",
        "why": "Confirms that short-term momentum has turned up inside an intact longer-term trend.",
        "trigger": "MACD crosses signal from below.",
        "invalidation": "MACD crossing back down, or a close below the 50-day.",
        "stop_rule": "Below the swing low that formed before the cross.",
        "target_rule": "Prior high; trail with the 20-day once extended.",
        "fails_when": "Price is chopping sideways. MACD whipsaws badly in a range — the trend filter matters more than the cross.",
    },
    "range_fade": {
        "name": "Range fade",
        "idea": "No trend. Price is at the edge of a well-defined range, so you fade back toward the middle.",
        "why": "Most of the time markets are ranging, not trending. At the edges, the odds favour reversion.",
        "trigger": "Price tags the top or bottom of the 20-day range with the 20- and 50-day averages flat.",
        "invalidation": "A close outside the range — that is a breakout, and you are now on the wrong side of one.",
        "stop_rule": "Just beyond the range edge.",
        "target_rule": "The midpoint of the range.",
        "fails_when": "The range is about to resolve into a trend. This is the setup that hurts most when wrong — keep it small.",
    },
}


def teach(setup: str = "") -> dict[str, Any]:
    key = (setup or "").strip().lower()
    if not key:
        return {
            "ok": True,
            "setups": [{"key": k, "name": v["name"], "idea": v["idea"]} for k, v in CATALOG.items()],
            "next": "setups action=teach setup=<key> for the full breakdown.",
        }
    entry = CATALOG.get(key)
    if not entry:
        return {"error": f"Unknown setup {key!r}.", "known": sorted(CATALOG)}
    return {"ok": True, "setup": key, **entry}


# --------------------------------------------------------------------------- maths


def _atr(bars: list[dict], period: int = 14) -> float | None:
    """Average true range — the volatility unit stops are measured in."""
    trs = []
    for i in range(1, len(bars)):
        high, low = bars[i].get("high"), bars[i].get("low")
        prev_close = bars[i - 1].get("close")
        if high is None or low is None or prev_close is None:
            continue
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    window = trs[-period:]
    return sum(window) / len(window)


def _swing_low(bars: list[dict], lookback: int = 10) -> float | None:
    lows = [b["low"] for b in bars[-lookback:] if b.get("low") is not None]
    return min(lows) if lows else None


def _swing_high(bars: list[dict], lookback: int = 20) -> float | None:
    highs = [b["high"] for b in bars[-lookback:] if b.get("high") is not None]
    return max(highs) if highs else None


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _avg_volume(bars: list[dict], period: int = 20) -> float | None:
    vols = [b["volume"] for b in bars[-period:] if b.get("volume")]
    return sum(vols) / len(vols) if vols else None


# --------------------------------------------------------------------------- detection


# The minimum history any detection needs before its indicators mean anything.
WARMUP_BARS = 60


def _context(symbol: str, range_: str = "1y") -> dict[str, Any]:
    hist = markets.history(symbol, range_)
    if hist.get("error"):
        return hist
    bars = [b for b in hist.get("bars") or [] if b.get("close") is not None]
    return context_from_bars(bars, symbol)


def context_from_bars(bars: list[dict], symbol: str) -> dict[str, Any]:
    """Everything detection needs, computed from a list of bars and nothing else.

    Split out of _context so the backtest can hand it bars[:i+1] and get the state of
    the world as of bar i. Every helper here slices from the end of what it is given,
    so truncating the list is all it takes to move back in time - and a detector that
    cannot see past the end of its input cannot peek at the future by accident.
    """
    if len(bars) < WARMUP_BARS:
        return {"error": f"Only {len(bars)} usable bars for {symbol}; need {WARMUP_BARS}+."}
    closes = [b["close"] for b in bars]
    stats = markets.indicators(closes)
    if stats.get("error"):
        return stats
    return {
        "ok": True,
        "symbol": symbol.upper(),
        "bars": bars,
        "closes": closes,
        "stats": stats,
        "atr": _atr(bars),
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "sma200": _sma(closes, 200),
        "avg_volume": _avg_volume(bars),
    }


def scan(symbol: str, range_: str = "1y") -> dict[str, Any]:
    """Which named setups are present on this symbol right now."""
    ctx = _context(symbol, range_)
    if not ctx.get("ok"):
        return ctx
    return detect(ctx)


def detect(ctx: dict[str, Any]) -> dict[str, Any]:
    """The detection rules themselves, over a context and nothing else.

    scan() runs this on the newest bar; the backtest runs the very same function on
    every historical bar. That is deliberate: a backtest that reimplements the rules
    is measuring a strategy nobody trades.
    """
    bars, closes, stats = ctx["bars"], ctx["closes"], ctx["stats"]
    last = closes[-1]
    sma20, sma50 = ctx["sma20"], ctx["sma50"]
    atr = ctx["atr"]
    rsi = stats.get("rsi14")
    high20, low20 = stats.get("high_20"), stats.get("low_20")
    macd, signal = stats.get("macd"), stats.get("macd_signal")
    avg_vol = ctx["avg_volume"]
    last_vol = bars[-1].get("volume")

    found: list[dict[str, Any]] = []

    # Trend pullback: uptrend intact, price has come back to the 20-day, RSI cooled.
    if sma20 and sma50 and last > sma50 and rsi is not None:
        near_sma20 = abs(last - sma20) <= (atr or 0) * 1.0 if atr else False
        if near_sma20 and 38 <= rsi <= 58:
            found.append(
                {
                    "setup": "trend_pullback",
                    "confidence": "high" if last > sma20 else "medium",
                    "evidence": {
                        "above_sma50": True,
                        "distance_to_sma20_atr": round(abs(last - sma20) / atr, 2) if atr else None,
                        "rsi14": round(rsi, 1),
                    },
                }
            )

    # 20-day breakout, ideally with volume behind it.
    if high20 and last >= high20:
        heavy = bool(avg_vol and last_vol and last_vol > avg_vol * 1.2)
        found.append(
            {
                "setup": "breakout_20d",
                "confidence": "high" if heavy else "low",
                "evidence": {
                    "high_20": round(high20, 2),
                    "volume_vs_avg": round(last_vol / avg_vol, 2) if (avg_vol and last_vol) else None,
                    "note": None if heavy else "Volume is not confirming — this is the failure-prone version.",
                },
            }
        )

    # Oversold, but only where the long trend is still up.
    if rsi is not None and rsi < 35 and sma50 and last > sma50:
        found.append(
            {
                "setup": "oversold_in_uptrend",
                "confidence": "medium",
                "evidence": {"rsi14": round(rsi, 1), "above_sma50": True},
            }
        )

    # Momentum cross with a trend filter.
    if macd is not None and signal is not None and macd > signal and sma50 and last > sma50:
        found.append(
            {
                "setup": "momentum_cross",
                "confidence": "medium",
                "evidence": {"macd": round(macd, 3), "signal": round(signal, 3)},
            }
        )

    # Range fade: flat averages, price at an edge.
    if sma20 and sma50 and high20 and low20:
        flat = abs(sma20 - sma50) / sma50 < 0.02
        at_top = last >= high20 * 0.99
        at_bottom = last <= low20 * 1.01
        if flat and (at_top or at_bottom):
            found.append(
                {
                    "setup": "range_fade",
                    "side": "sell" if at_top else "buy",
                    "confidence": "low",
                    "evidence": {"high_20": round(high20, 2), "low_20": round(low20, 2), "averages_flat": True},
                }
            )

    for item in found:
        item["name"] = CATALOG[item["setup"]]["name"]
        item["invalidation"] = CATALOG[item["setup"]]["invalidation"]

    return {
        "ok": True,
        "symbol": ctx["symbol"],
        "last": round(last, 2),
        "atr14": round(atr, 2) if atr else None,
        "context": {
            "sma20": round(sma20, 2) if sma20 else None,
            "sma50": round(sma50, 2) if sma50 else None,
            "sma200": round(ctx["sma200"], 2) if ctx["sma200"] else None,
            "rsi14": round(rsi, 1) if rsi is not None else None,
            "trend": stats.get("trend"),
        },
        "found": found,
        "count": len(found),
        "next": "setups action=plan symbol=... setup=... risk=<dollars> for sized levels.",
    }


# --------------------------------------------------------------------------- planning


def levels_for(ctx: dict[str, Any], key: str) -> dict[str, Any]:
    """Entry, stop and target for one setup, from a context and nothing else.

    Extracted from plan() for the same reason detect() was extracted from scan(): the
    backtest has to size its historical trades with the identical rules the live plan
    uses, or the hit rate it reports belongs to some other strategy.
    """
    if key not in CATALOG:
        return {"error": f"Unknown setup {key!r}.", "known": sorted(CATALOG)}
    bars, closes, stats = ctx["bars"], ctx["closes"], ctx["stats"]
    last = closes[-1]
    atr = ctx["atr"]
    sma20 = ctx["sma20"]
    if not atr:
        return {"error": "Not enough data to compute ATR; cannot size a stop."}

    high20, low20 = stats.get("high_20"), stats.get("low_20")
    swing_low = _swing_low(bars) or (last - 2 * atr)
    swing_high = _swing_high(bars) or (last + 2 * atr)

    side = "buy"
    if key == "trend_pullback":
        entry = round(bars[-1].get("high") or last, 2)
        stop = round(max(swing_low, entry - 1.5 * atr), 2)
        target = round(swing_high, 2)
    elif key == "breakout_20d":
        entry = round(max(last, high20 or last), 2)
        stop = round(min(swing_low, entry - 1.5 * atr), 2)
        base_height = (high20 - low20) if (high20 and low20) else 2 * atr
        target = round(entry + base_height, 2)
    elif key == "oversold_in_uptrend":
        entry = round(last, 2)
        stop = round(min(bars[-1].get("low") or last, entry - 2 * atr), 2)
        target = round(sma20 or (entry + 2 * atr), 2)
    elif key == "momentum_cross":
        entry = round(last, 2)
        stop = round(swing_low, 2)
        target = round(swing_high, 2)
    else:  # range_fade
        at_top = high20 and last >= high20 * 0.99
        side = "sell" if at_top else "buy"
        mid = ((high20 or last) + (low20 or last)) / 2
        entry = round(last, 2)
        if side == "sell":
            stop = round((high20 or last) + 0.5 * atr, 2)
            target = round(mid, 2)
        else:
            stop = round((low20 or last) - 0.5 * atr, 2)
            target = round(mid, 2)

    if abs(entry - stop) <= 0:
        return {"error": "Computed a zero-width stop; refusing to produce levels."}
    return {"ok": True, "side": side, "entry": entry, "stop": stop, "target": target, "atr": atr}


def plan(symbol: str, setup: str, risk: float = 0.0, *, range_: str = "1y") -> dict[str, Any]:
    """Turn a setup into entry / stop / target and a share count sized off your risk budget."""
    key = (setup or "").strip().lower()
    if key not in CATALOG:
        return {"error": f"Unknown setup {key!r}.", "known": sorted(CATALOG)}

    ctx = _context(symbol, range_)
    if not ctx.get("ok"):
        return ctx
    levels = levels_for(ctx, key)
    if levels.get("error"):
        return levels

    closes, stats = ctx["closes"], ctx["stats"]
    last = closes[-1]
    atr = ctx["atr"]
    sma50 = ctx["sma50"]
    side, entry, stop, target = levels["side"], levels["entry"], levels["stop"], levels["target"]
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return {"error": "Computed a zero-width stop; refusing to produce a plan."}

    reward_per_share = abs(target - entry)
    r_multiple = round(reward_per_share / risk_per_share, 2)

    shares = None
    if risk and risk > 0:
        shares = int(risk // risk_per_share)

    warnings = []
    if r_multiple < 1.5:
        warnings.append(f"Reward-to-risk is only {r_multiple}R. Most setups need 2R+ to be worth the slot.")
    if side == "buy" and sma50 and last < sma50:
        warnings.append("Price is below the 50-day — the trend filter this setup relies on is not there.")
    if shares == 0:
        warnings.append(f"Risk budget of {risk} is smaller than one share's risk ({risk_per_share:.2f}).")

    teaching = CATALOG[key]
    return {
        "ok": True,
        "symbol": ctx["symbol"],
        "setup": key,
        "name": teaching["name"],
        "side": side,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_per_share": round(risk_per_share, 2),
        "reward_per_share": round(reward_per_share, 2),
        "r_multiple": r_multiple,
        "shares": shares,
        "total_risk": round(shares * risk_per_share, 2) if shares else None,
        "atr14": round(atr, 2),
        "invalidation": teaching["invalidation"],
        "stop_rule": teaching["stop_rule"],
        "target_rule": teaching["target_rule"],
        "fails_when": teaching["fails_when"],
        "warnings": warnings,
        "place": (
            f"market action=ibkr mode=bracket symbol={ctx['symbol']} side={side} "
            f"qty={shares or '<qty>'} entry={entry} stop={stop} target={target}"
        ),
        "note": "Levels from daily bars. This describes a defined-risk structure, not a forecast.",
    }


def dispatch(action: str = "scan", **kwargs: Any) -> Any:
    act = (action or "scan").lower()
    symbol = str(kwargs.get("symbol") or "")
    if act in {"teach", "explain", "catalog", "list"}:
        return teach(str(kwargs.get("setup") or ""))
    if act in {"scan", "detect", "find"}:
        if not symbol:
            return {"error": "symbol required."}
        return scan(symbol, str(kwargs.get("range") or kwargs.get("range_") or "1y"))
    if act in {"plan", "trade", "size"}:
        if not symbol:
            return {"error": "symbol required."}
        return plan(
            symbol,
            str(kwargs.get("setup") or ""),
            float(kwargs.get("risk") or 0),
            range_=str(kwargs.get("range") or kwargs.get("range_") or "1y"),
        )
    return {"error": f"unknown setups action {act}", "actions": ["scan", "teach", "plan"]}
