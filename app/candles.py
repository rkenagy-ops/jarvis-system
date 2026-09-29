"""Read the candles: named candlestick patterns, where they formed, and whether a
breakout (up) or breakdown (down) is loading.

setups.py names the *structure* - trend, range, 20-day extremes. This reads the last
few bars themselves: who won the session, how decisively, and where on the chart it
happened. The same hammer means something at the bottom of a pullback into support and
almost nothing in the middle of a range, so every pattern here is graded by LOCATION and
by prior TREND, not just by its shape.

    candles action=read    symbol=NVDA          -> patterns on the last 3 bars, graded
    candles action=radar   symbol=NVDA          -> is a breakout / breakdown loading?
    candles action=teach   pattern=hammer       -> what it is, where it matters, how it fails

Everything takes bars and nothing else (read_bars / radar_bars), so setups.detect and
the backtest can use it on truncated history without any way to peek ahead.
"""

from __future__ import annotations

from typing import Any

from . import markets

# --------------------------------------------------------------------------- teaching

CATALOG: dict[str, dict[str, str]] = {
    "hammer": {
        "bias": "bull",
        "what": "Small body at the top of the bar, lower wick at least twice the body. Sellers drove it down; buyers took it all back.",
        "where": "After a decline, at support or the 20/50-day average. Mid-range it is noise.",
        "confirm": "Next bar trades above the hammer's high.",
        "fails_when": "The next bar closes below the hammer's low - the buyers who showed up are now trapped.",
    },
    "hanging_man": {
        "bias": "bear",
        "what": "The hammer's shape, but after an advance. Heavy selling intrabar at the top of a run.",
        "where": "Extended above the 20-day after a multi-day rally.",
        "confirm": "Next bar closes below the body. Unconfirmed, it is a warning, not a signal.",
        "fails_when": "Price simply makes a new high the next day - strong trends shrug these off.",
    },
    "shooting_star": {
        "bias": "bear",
        "what": "Small body at the bottom, long upper wick. Buyers pushed it up and got rejected hard.",
        "where": "After an advance, into resistance or a prior 20-day high.",
        "confirm": "Next bar trades below the star's low.",
        "fails_when": "It forms in a strong uptrend on light volume; the rejection had nobody behind it.",
    },
    "inverted_hammer": {
        "bias": "bull",
        "what": "Shooting-star shape after a decline: buyers tested higher for the first time in a while.",
        "where": "At the end of a downswing, into support.",
        "confirm": "Needs a strong green bar next. On its own it is the weakest of the reversal candles.",
        "fails_when": "The downtrend is steep; a single probe up does not turn it.",
    },
    "bullish_engulfing": {
        "bias": "bull",
        "what": "A green body that fully engulfs the prior red body. Control flipped from sellers to buyers inside one session.",
        "where": "After a pullback, at support. Best with volume above average.",
        "confirm": "Follow-through above the engulfing bar's high.",
        "fails_when": "It appears in a range with no prior decline - there was nothing to reverse.",
    },
    "bearish_engulfing": {
        "bias": "bear",
        "what": "A red body that fully engulfs the prior green body. Buyers lost control in one session.",
        "where": "After a rally, at resistance or a 20-day high.",
        "confirm": "Follow-through below the engulfing bar's low.",
        "fails_when": "Light volume in a strong uptrend; it is often just a shakeout.",
    },
    "piercing_line": {
        "bias": "bull",
        "what": "After a red bar, price gaps/opens lower then closes above the midpoint of the red body.",
        "where": "After a decline, at support.",
        "confirm": "Next bar clears the red bar's open.",
        "fails_when": "It closes back under the midpoint next day.",
    },
    "dark_cloud_cover": {
        "bias": "bear",
        "what": "After a green bar, price opens higher then closes below the midpoint of the green body.",
        "where": "After an advance, at resistance.",
        "confirm": "Next bar trades below the green bar's open.",
        "fails_when": "The trend is strong and the next bar reclaims the midpoint.",
    },
    "morning_star": {
        "bias": "bull",
        "what": "Three bars: a long red bar, a small indecisive bar, then a green bar closing deep into the first.",
        "where": "The bottom of a downswing. One of the more reliable reversal shapes.",
        "confirm": "The third bar itself is the confirmation; volume on it matters.",
        "fails_when": "The third bar's volume is lighter than the first's.",
    },
    "evening_star": {
        "bias": "bear",
        "what": "Three bars: a long green bar, a small indecisive bar, then a red bar closing deep into the first.",
        "where": "The top of an advance, at resistance.",
        "confirm": "The third bar is the confirmation.",
        "fails_when": "The broader market is ripping - single-name tops get overrun.",
    },
    "three_white_soldiers": {
        "bias": "bull",
        "what": "Three green bars, each closing higher, each opening inside the prior body, small upper wicks.",
        "where": "Coming off a base or a low. Momentum shift, not a top.",
        "confirm": "Holding above the first soldier's midpoint on any pullback.",
        "fails_when": "It is already extended - three big green bars at the top of a run are exhaustion.",
    },
    "three_black_crows": {
        "bias": "bear",
        "what": "Three red bars, each closing lower, each opening inside the prior body, small lower wicks.",
        "where": "Off a top or failing at resistance.",
        "confirm": "Rallies failing below the first crow's midpoint.",
        "fails_when": "Already deeply oversold at major support - that is capitulation, not a new trend.",
    },
    "bullish_marubozu": {
        "bias": "bull",
        "what": "A green bar that is nearly all body - opened near the low, closed near the high. Buyers in control all session.",
        "where": "Breaking out of a range or off support.",
        "confirm": "The next bar holds its midpoint.",
        "fails_when": "It closes right into a heavy resistance level.",
    },
    "bearish_marubozu": {
        "bias": "bear",
        "what": "A red bar that is nearly all body. Sellers in control from open to close.",
        "where": "Breaking down out of a range or off resistance.",
        "confirm": "The next bar stays below its midpoint.",
        "fails_when": "It prints straight into major support on climactic volume.",
    },
    "doji": {
        "bias": "neutral",
        "what": "Open and close nearly equal. Indecision - neither side won the session.",
        "where": "Meaningful only after a strong move, where indecision is itself a change.",
        "confirm": "Direction of the next bar's break of the doji's range.",
        "fails_when": "Read as a reversal on its own. It is a pause until the next bar says otherwise.",
    },
    "inside_bar": {
        "bias": "neutral",
        "what": "Today's whole range sits inside yesterday's. Volatility contracting - energy building.",
        "where": "Near a 20-day high or low, or right after a breakout (a 'flag').",
        "confirm": "Trade the break of the mother bar's high (long) or low (short).",
        "fails_when": "It breaks one way and reverses through the other side - that fakeout is a signal the other way.",
    },
    "nr7": {
        "bias": "neutral",
        "what": "Narrowest range of the last seven sessions. Compression tends to precede expansion.",
        "where": "Coiled near a 20-day extreme is where it matters.",
        "confirm": "The first decisive close outside the NR7 bar's range.",
        "fails_when": "Earnings or news is imminent - the expansion then comes as a gap you cannot enter.",
    },
}


def teach(pattern: str = "") -> dict[str, Any]:
    key = (pattern or "").strip().lower()
    if not key:
        return {
            "ok": True,
            "patterns": [{"key": k, "bias": v["bias"], "what": v["what"]} for k, v in CATALOG.items()],
            "rule": "A pattern is only as good as where it forms. Reversal candles need a prior move to reverse and a level to reverse at.",
            "next": "candles action=teach pattern=<key>",
        }
    entry = CATALOG.get(key)
    if not entry:
        return {"error": f"Unknown pattern {key!r}.", "known": sorted(CATALOG)}
    return {"ok": True, "pattern": key, **entry}


# --------------------------------------------------------------------------- shape maths


def _parts(bar: dict) -> dict[str, float] | None:
    o, h, l, c = bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close")
    if None in (o, h, l, c) or h < l:
        return None
    rng = h - l
    return {
        "o": o, "h": h, "l": l, "c": c,
        "range": rng,
        "body": abs(c - o),
        "upper": h - max(o, c),
        "lower": min(o, c) - l,
        "green": c > o,
        "red": c < o,
        "mid": (o + c) / 2,
    }


def _prior_trend(bars: list[dict], end: int, lookback: int = 5) -> str:
    """Direction of the move INTO bar `end` (exclusive): 'up', 'down' or 'flat'."""
    start = end - lookback
    if start < 0:
        return "flat"
    first, last = bars[start].get("close"), bars[end - 1].get("close")
    if not first or not last:
        return "flat"
    change = last / first - 1
    if change > 0.02:
        return "up"
    if change < -0.02:
        return "down"
    return "flat"


def _avg_range(bars: list[dict], end: int, period: int = 14) -> float | None:
    ranges = [p["range"] for p in (_parts(b) for b in bars[max(0, end - period) : end]) if p]
    return sum(ranges) / len(ranges) if ranges else None


def _shapes_at(bars: list[dict], i: int) -> list[str]:
    """Every pattern that completes ON bar i. Looks at bars[..i] only."""
    cur = _parts(bars[i])
    if not cur or cur["range"] <= 0:
        return []
    prev = _parts(bars[i - 1]) if i >= 1 else None
    prev2 = _parts(bars[i - 2]) if i >= 2 else None
    trend = _prior_trend(bars, i)
    avg_rng = _avg_range(bars, i) or cur["range"]
    found: list[str] = []

    body, rng = cur["body"], cur["range"]
    small_body = body <= 0.35 * rng

    if body <= 0.1 * rng:
        found.append("doji")
    elif small_body and cur["lower"] >= 2 * body and cur["upper"] <= 0.25 * rng:
        if trend == "down":
            found.append("hammer")
        elif trend == "up":
            found.append("hanging_man")
    elif small_body and cur["upper"] >= 2 * body and cur["lower"] <= 0.25 * rng:
        if trend == "up":
            found.append("shooting_star")
        elif trend == "down":
            found.append("inverted_hammer")

    if body >= 0.9 * rng and rng >= avg_rng:
        found.append("bullish_marubozu" if cur["green"] else "bearish_marubozu")

    if prev:
        top, bot = max(cur["o"], cur["c"]), min(cur["o"], cur["c"])
        ptop, pbot = max(prev["o"], prev["c"]), min(prev["o"], prev["c"])
        if cur["green"] and prev["red"] and top >= ptop and bot <= pbot and body > prev["body"]:
            found.append("bullish_engulfing")
        if cur["red"] and prev["green"] and top >= ptop and bot <= pbot and body > prev["body"]:
            found.append("bearish_engulfing")
        if prev["red"] and cur["green"] and cur["o"] < prev["c"] and prev["mid"] < cur["c"] < prev["o"]:
            found.append("piercing_line")
        if prev["green"] and cur["red"] and cur["o"] > prev["c"] and prev["o"] < cur["c"] < prev["mid"]:
            found.append("dark_cloud_cover")
        if cur["h"] < prev["h"] and cur["l"] > prev["l"]:
            found.append("inside_bar")

    if prev and prev2:
        long_first = prev2["body"] >= 0.6 * prev2["range"] and prev2["range"] >= avg_rng * 0.8
        small_mid = prev["body"] <= 0.35 * max(prev["range"], 1e-9)
        if long_first and small_mid and prev2["red"] and cur["green"] and cur["c"] > prev2["mid"]:
            found.append("morning_star")
        if long_first and small_mid and prev2["green"] and cur["red"] and cur["c"] < prev2["mid"]:
            found.append("evening_star")
        trio = [prev2, prev, cur]
        if all(p["green"] for p in trio) and prev["c"] > prev2["c"] and cur["c"] > prev["c"] \
                and prev2["o"] <= prev["o"] <= prev2["c"] and prev["o"] <= cur["o"] <= prev["c"] \
                and all(p["upper"] <= 0.3 * p["range"] for p in trio):
            found.append("three_white_soldiers")
        if all(p["red"] for p in trio) and prev["c"] < prev2["c"] and cur["c"] < prev["c"] \
                and prev2["c"] <= prev["o"] <= prev2["o"] and prev["c"] <= cur["o"] <= prev["o"] \
                and all(p["lower"] <= 0.3 * p["range"] for p in trio):
            found.append("three_black_crows")

    if i >= 6:
        window = [_parts(b) for b in bars[i - 6 : i + 1]]
        if all(window) and rng <= min(p["range"] for p in window):
            found.append("nr7")
    return found


# --------------------------------------------------------------------------- reading


def read_bars(bars: list[dict], *, lookback: int = 3) -> dict[str, Any]:
    """Patterns completing on the last `lookback` bars, graded by where they formed."""
    bars = [b for b in bars if b.get("close") is not None]
    if len(bars) < 25:
        return {"error": f"Need 25+ bars to read candles in context; have {len(bars)}."}
    closes = [b["close"] for b in bars]
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    # Prior 20-bar extremes, excluding today: support and resistance the candle is reacting to.
    hi20 = max(b.get("high") or b["close"] for b in bars[-21:-1])
    lo20 = min(b.get("low") or b["close"] for b in bars[-21:-1])
    atr = _avg_range(bars, len(bars)) or 0
    vols = [b.get("volume") or 0 for b in bars[-21:-1]]
    avg_vol = sum(vols) / len(vols) if any(vols) else None

    out: list[dict[str, Any]] = []
    for i in range(len(bars) - lookback, len(bars)):
        for key in _shapes_at(bars, i):
            bias = CATALOG[key]["bias"]
            bar = bars[i]
            low, high = bar.get("low") or bar["close"], bar.get("high") or bar["close"]
            at_support = atr and (low - lo20 <= atr or abs(low - sma20) <= 0.5 * atr)
            at_resistance = atr and (hi20 - high <= atr or abs(high - sma20) <= 0.5 * atr)
            vol = bar.get("volume")
            heavy = bool(avg_vol and vol and vol >= 1.3 * avg_vol)

            score = 1
            reasons = []
            if bias == "bull" and at_support:
                score += 1
                reasons.append("formed at support")
            if bias == "bear" and at_resistance:
                score += 1
                reasons.append("formed at resistance")
            if heavy:
                score += 1
                reasons.append("volume above average")
            if bias == "bull" and sma50 and closes[-1] > sma50:
                score += 1
                reasons.append("with the larger trend (above 50-day)")
            if bias == "bear" and sma50 and closes[-1] < sma50:
                score += 1
                reasons.append("with the larger trend (below 50-day)")
            out.append({
                "pattern": key,
                "bias": bias,
                "date": bar.get("date"),
                "bars_ago": len(bars) - 1 - i,
                "strength": "strong" if score >= 3 else "moderate" if score == 2 else "weak",
                "score": score,
                "why": reasons or ["shape only - no location or volume confirmation"],
                "confirm": CATALOG[key]["confirm"],
            })

    bull = sum(p["score"] for p in out if p["bias"] == "bull")
    bear = sum(p["score"] for p in out if p["bias"] == "bear")
    return {
        "ok": True,
        "patterns": out,
        "bull_score": bull,
        "bear_score": bear,
        "lean": "bull" if bull > bear else "bear" if bear > bull else "neutral",
    }


def radar_bars(bars: list[dict]) -> dict[str, Any]:
    """Is a breakout (up) or breakdown (down) happening or loading on the last bar?

    Three ingredients, the way a tape reader looks at it:
      - compression: Bollinger bandwidth near its lowest in ~6 months (a squeeze),
        or an NR7 / inside bar on the last session
      - position: how close price sits to the prior 20-day high or low, in ATRs
      - participation: today's volume against its 20-day average
    """
    bars = [b for b in bars if b.get("close") is not None]
    if len(bars) < 60:
        return {"error": f"Need 60+ bars for the breakout radar; have {len(bars)}."}
    closes = [b["close"] for b in bars]
    last = bars[-1]
    close = last["close"]
    atr = _avg_range(bars, len(bars)) or 0
    prior = bars[-21:-1]
    hi20 = max(b.get("high") or b["close"] for b in prior)
    lo20 = min(b.get("low") or b["close"] for b in prior)
    sma50 = sum(closes[-50:]) / 50
    vols = [b.get("volume") or 0 for b in prior]
    avg_vol = sum(vols) / len(vols) if any(vols) else None
    rvol = round((last.get("volume") or 0) / avg_vol, 2) if avg_vol else None

    squeeze_pct = squeeze_percentile(closes)
    squeeze = squeeze_pct is not None and squeeze_pct <= 20
    shapes = _shapes_at(bars, len(bars) - 1)
    coiled = squeeze or "nr7" in shapes or "inside_bar" in shapes

    dist_hi = round((hi20 - close) / atr, 2) if atr else None
    dist_lo = round((close - lo20) / atr, 2) if atr else None
    heavy = rvol is not None and rvol >= 1.5

    if close > hi20:
        status, direction = ("breaking_out" if heavy else "breaking_out_light_volume"), "up"
    elif close < lo20:
        status, direction = ("breaking_down" if heavy else "breaking_down_light_volume"), "down"
    elif coiled and dist_hi is not None and dist_hi <= 0.75 and close >= sma50:
        status, direction = "coiled_near_high", "up"
    elif coiled and dist_lo is not None and dist_lo <= 0.75 and close <= sma50:
        status, direction = "coiled_near_low", "down"
    elif coiled:
        status, direction = "coiled_mid_range", "either"
    else:
        status, direction = "none", "none"

    buffer = 0.1 * atr
    return {
        "ok": True,
        "status": status,
        "direction": direction,
        "close": round(close, 2),
        "prior_20d_high": round(hi20, 2),
        "prior_20d_low": round(lo20, 2),
        "atr": round(atr, 2),
        "atr_to_high": dist_hi,
        "atr_to_low": dist_lo,
        "rvol": rvol,
        "squeeze": squeeze,
        "squeeze_percentile": squeeze_pct,
        "compression": [s for s in shapes if s in {"nr7", "inside_bar"}],
        "long_trigger": round(hi20 + buffer, 2),
        "long_stop": round(max(lo20, hi20 - 1.5 * atr), 2) if atr else None,
        "short_trigger": round(lo20 - buffer, 2),
        "short_stop": round(min(hi20, lo20 + 1.5 * atr), 2) if atr else None,
        "rule": (
            "Real breakouts close outside the range on 1.5x+ volume and hold the next day. "
            "A breakout that closes back inside the range is a failed breakout - flip bias or stand aside."
        ),
    }


def squeeze_percentile(closes: list[float], *, lookback: int = 126, recent: int = 5) -> float | None:
    """Where the tightest Bollinger bandwidth of the last `recent` bars ranks among the
    last ~6 months. Low percentile = coiled. Slices fixed 20-bar windows, so the backtest
    can call it on every bar without quadratic copying."""
    widths = [
        w for w in (_bandwidth(closes[j - 19 : j + 1]) for j in range(max(19, len(closes) - lookback), len(closes))) if w
    ]
    if len(widths) < 20:
        return None
    tight = min(widths[-recent:])
    return round(100 * sum(1 for w in widths if w <= tight) / len(widths), 1)


def _bandwidth(closes: list[float], period: int = 20) -> float | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    if not mean:
        return None
    sd = (sum((c - mean) ** 2 for c in window) / period) ** 0.5
    return 4 * sd / mean


# --------------------------------------------------------------------------- live


def read(symbol: str, range_: str = "6mo") -> dict[str, Any]:
    bars = _bars(symbol, range_)
    if isinstance(bars, dict):
        return bars
    out = read_bars(bars)
    return {**out, "symbol": symbol.upper()} if out.get("ok") else out


def radar(symbol: str, range_: str = "1y") -> dict[str, Any]:
    bars = _bars(symbol, range_)
    if isinstance(bars, dict):
        return bars
    out = radar_bars(bars)
    return {**out, "symbol": symbol.upper()} if out.get("ok") else out


def _bars(symbol: str, range_: str) -> list[dict] | dict[str, Any]:
    if not symbol:
        return {"error": "symbol required."}
    hist = markets.history_cached(symbol, range_, max_age=900)
    if hist.get("error"):
        return hist
    return [b for b in hist.get("bars") or [] if b.get("close") is not None]


def dispatch(action: str = "read", **kwargs: Any) -> Any:
    act = (action or "read").lower()
    symbol = str(kwargs.get("symbol") or "").strip().upper()
    if act in {"teach", "explain", "list", "catalog"}:
        return teach(str(kwargs.get("pattern") or ""))
    if act in {"read", "patterns", "scan"}:
        return read(symbol, str(kwargs.get("range") or "6mo"))
    if act in {"radar", "breakout", "breakouts"}:
        return radar(symbol, str(kwargs.get("range") or "1y"))
    return {"error": f"unknown candles action {act}", "actions": ["read", "radar", "teach"]}
