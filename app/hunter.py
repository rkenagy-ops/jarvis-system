"""The universe hunter: every liquid US stock, both directions, ranked by what pays.

broad_screen() in marketbeast.py proved the full market can be screened cheaply. This is
the desk that actually runs it all day, aggressively:

  - The whole Nasdaq/NYSE/AMEX directory, not an alphabetical first-2000 slice. A daily
    pass builds the LIQUID universe (price and dollar volume floors) so intraday passes
    only spend bandwidth on names that can actually be traded in size.
  - Longs AND shorts. Breakdowns and failed rallies make money too; a long-only scan
    sits out every down tape.
  - Ranked by expected payoff, not by how many indicators lit up: setup confidence,
    reward-to-risk, relative volume, whether the breakout radar agrees - multiplied by
    what journal.py has LEARNED about that setup and those conditions from her own
    closed trades. What has been paying rises; what has been bleeding sinks.
  - Coiled names (squeeze / NR7 / inside bar sitting on a 20-day extreme) are listed
    separately as "loading" - the breakouts of tomorrow, with trigger levels.

After the close, the day's top signals are logged to forward_tracker, so every call she
makes gets closed out honestly and studied by the journal. Intraday passes do not log,
because a half-formed daily bar is not a signal yet.

Nothing here places, sizes or confirms an order. It finds and ranks. Orders still go
through the risk governor and the confirm token like everything else.

    hunter action=hunt                    -> run a pass now (top longs, top shorts, loading)
    hunter action=last                    -> the most recent pass, no network
    hunter action=liquid refresh=true     -> rebuild the liquid universe
"""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any

from . import candles, config, forward_tracker, journal, markets, setups

LIQUID_PATH = config.DATA_DIR / "liquid_universe.json"
LAST_PATH = config.DATA_DIR / "hunt_last.json"
LIQUID_TTL = 24 * 3600
MIN_PRICE = 5.0
MIN_DOLLAR_VOLUME = 20_000_000
BATCH = 200
CONFIDENCE = {"high": 3.0, "medium": 2.0, "low": 1.0}


def session(now: dt.datetime | None = None) -> str:
    """US equity session in New York time: pre, regular, post or closed."""
    from . import risk

    moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(risk.MARKET_TZ)
    if moment.weekday() >= 5:
        return "closed"
    minutes = moment.hour * 60 + moment.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "pre"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "regular"
    if 16 * 60 <= minutes < 20 * 60:
        return "post"
    return "closed"


def hunt(*, top: int = 15, log: bool | None = None, refresh_liquid: bool = False) -> dict[str, Any]:
    started = time.time()
    phase = session()
    liquid = liquid_universe(refresh=refresh_liquid)
    symbols = liquid["symbols"]
    # Intraday the daily bar is still forming - refetch every 10 minutes so breakouts are
    # seen while they happen. Outside the session the bars are settled; reuse the cache.
    max_age = 600 if phase == "regular" else markets.OHLCV_CACHE_TTL
    learned = journal.weights()
    regime = forward_tracker.market_regime()
    should_log = (phase in {"post", "closed"}) if log is None else log

    ideas: list[dict[str, Any]] = []
    loading: list[dict[str, Any]] = []
    contexts: dict[str, dict[str, Any]] = {}
    errors = 0
    for i in range(0, len(symbols), BATCH):
        fetched = markets.history_batch(symbols[i : i + BATCH], "1y", max_age=max_age)
        for sym, hist in fetched.items():
            if hist.get("error"):
                errors += 1
                continue
            bars = [b for b in hist.get("bars") or [] if b.get("close") is not None]
            ctx = setups.context_from_bars(bars, sym)
            if not ctx.get("ok"):
                continue
            radar = candles.radar_bars(bars)
            for item in setups.detect(ctx).get("found") or []:
                idea = _score(ctx, item, radar, regime, learned)
                if idea:
                    ideas.append(idea)
                    contexts[sym] = ctx
            if radar.get("ok") and radar["status"] in {"coiled_near_high", "coiled_near_low"}:
                loading.append({
                    "symbol": sym,
                    "direction": radar["direction"],
                    "squeeze_percentile": radar.get("squeeze_percentile"),
                    "compression": radar.get("compression"),
                    "trigger": radar["long_trigger"] if radar["direction"] == "up" else radar["short_trigger"],
                    "stop": radar["long_stop"] if radar["direction"] == "up" else radar["short_stop"],
                    "atr_to_trigger": radar["atr_to_high"] if radar["direction"] == "up" else radar["atr_to_low"],
                })

    best = _best_per_symbol(ideas)
    longs = [x for x in best if x["side"] == "buy"][:top]
    shorts = [x for x in best if x["side"] == "sell"][:top]
    loading.sort(key=lambda x: (x.get("atr_to_trigger") or 9, x.get("squeeze_percentile") or 100))

    logged = 0
    if should_log:
        for idea in longs + shorts:
            ctx = contexts[idea["symbol"]]
            match = [f for f in setups.detect(ctx).get("found") or [] if f["setup"] == idea["setup"]]
            logged += len(forward_tracker.log_from_context(ctx, match, regime=regime, source="hunter")["logged"])

    result = {
        "ok": True,
        "session": phase,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "market": {"spy_above_50d": regime.get("up")},
        "universe": {"listed": liquid.get("listed"), "liquid": len(symbols), "source": liquid.get("source")},
        "errors": errors,
        "signals": len(ideas),
        "longs": longs,
        "shorts": shorts,
        "loading": loading[:top],
        "logged_to_tracker": logged,
        "learned_weights_from": learned.get("closed", 0),
        "elapsed_sec": round(time.time() - started, 1),
        "note": "Ranked candidates, not orders. Every order still passes the risk governor and a confirm token.",
    }
    _save(LAST_PATH, result)
    _publish(result)
    return result


def _score(
    ctx: dict[str, Any], item: dict[str, Any], radar: dict[str, Any], regime: dict[str, Any], learned: dict[str, Any],
) -> dict[str, Any] | None:
    levels = setups.levels_for(ctx, item["setup"])
    if not levels.get("ok"):
        return None
    side = levels["side"]
    risk = abs(levels["entry"] - levels["stop"])
    rr = abs(levels["target"] - levels["entry"]) / risk if risk else 0
    if rr < 1.2:
        return None  # not worth the slot, however pretty the chart
    context = forward_tracker.signal_context(ctx, item, levels, regime)
    tags = journal.conditions({"side": side, "setup": item["setup"], "context": context})
    mult = journal.multiplier(item["setup"], side, tags, learned)

    rvol = context.get("rvol") or 1.0
    radar_agrees = radar.get("ok") and (
        (side == "buy" and radar["status"].startswith("breaking_out"))
        or (side == "sell" and radar["status"].startswith("breaking_down"))
    )
    raw = CONFIDENCE.get(item.get("confidence"), 1.0) + min(rvol, 4.0) / 2 + (1.0 if radar_agrees else 0.0)
    if "against_market" in tags:
        raw *= 0.7
    score = round(raw * min(rr, 4.0) / 2 * mult, 3)
    return {
        "symbol": ctx["symbol"],
        "setup": item["setup"],
        "side": side,
        "score": score,
        "confidence": item.get("confidence"),
        "entry": levels["entry"],
        "stop": levels["stop"],
        "target": levels["target"],
        "r_multiple": round(rr, 2),
        "rvol": context.get("rvol"),
        "radar": radar.get("status") if radar.get("ok") else None,
        "candles": context.get("candles"),
        "conditions": sorted(tags),
        "learned_multiplier": mult,
        "plan": f"setups action=plan symbol={ctx['symbol']} setup={item['setup']} risk=<dollars>",
    }


def _best_per_symbol(ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for idea in ideas:
        key = (idea["symbol"], idea["side"])
        if key not in best or idea["score"] > best[key]["score"]:
            best[key] = idea
    return sorted(best.values(), key=lambda x: x["score"], reverse=True)


# --------------------------------------------------------------------------- universe


def liquid_universe(*, refresh: bool = False) -> dict[str, Any]:
    """Every listed symbol that clears the price and dollar-volume floors.

    Built from the full directory (universe.full()) once a day. Falls back to the whole
    directory, capped, when there is no liquid list yet and the build fails.
    """
    cached = _load(LIQUID_PATH)
    if cached and not refresh and time.time() - cached.get("at", 0) < LIQUID_TTL and cached.get("symbols"):
        return cached

    from . import universe

    full = universe.full()
    listed = full.get("symbols") or []
    liquid: list[str] = []
    for i in range(0, len(listed), BATCH):
        fetched = markets.history_batch(listed[i : i + BATCH], "1y")
        for sym, hist in fetched.items():
            bars = [b for b in hist.get("bars") or [] if b.get("close") is not None and b.get("volume")]
            if len(bars) < 20:
                continue
            last = bars[-1]["close"]
            dollar_vol = sum(b["close"] * b["volume"] for b in bars[-20:]) / 20
            if last >= MIN_PRICE and dollar_vol >= MIN_DOLLAR_VOLUME:
                liquid.append(sym)
    if not liquid:
        return cached or {"symbols": listed[: config.MARKETBEAST_MAX_UNIVERSE], "listed": len(listed),
                          "source": "unfiltered_fallback", "at": 0}
    out = {"symbols": sorted(set(liquid)), "listed": len(listed), "source": full.get("source"), "at": time.time()}
    _save(LIQUID_PATH, out)
    return out


# --------------------------------------------------------------------------- output


def _publish(result: dict[str, Any]) -> None:
    lines = [
        f"---\ntype: hunt\nsession: {result['session']}\n---\n",
        f"# Universe hunt {result['at'][:16]}Z ({result['session']})\n",
        f"Liquid universe {result['universe']['liquid']} of {result['universe']['listed']} listed. "
        f"SPY above 50-day: {result['market']['spy_above_50d']}. {result['signals']} raw signals.\n",
    ]
    for title, rows in (("Longs", result["longs"]), ("Shorts", result["shorts"])):
        lines.append(f"\n## {title}\n")
        lines.extend(
            f"- **{r['symbol']}** {r['setup']} score {r['score']} | entry {r['entry']} stop {r['stop']} "
            f"target {r['target']} ({r['r_multiple']}R) rvol {r['rvol']} radar {r['radar']}"
            + (f" candles {','.join(r['candles'])}" if r.get("candles") else "")
            for r in rows
        )
    if result["loading"]:
        lines.append("\n## Loading (coiled at an extreme)\n")
        lines.extend(
            f"- {r['symbol']} {r['direction']} trigger {r['trigger']} stop {r['stop']} "
            f"({r['atr_to_trigger']} ATR away, squeeze pct {r['squeeze_percentile']})"
            for r in result["loading"]
        )
    try:
        from . import obsidian

        obsidian.write_note("Markets/hunt.md", "\n".join(lines) + "\n")
    except Exception:
        pass
    top = [r["symbol"] for r in (result["longs"][:5] + result["shorts"][:5])]
    if not top:
        return
    try:
        from . import events

        events.emit("market.signal", {"source": "hunter", "tickers": top, "session": result["session"]}, coalesce=True)
    except Exception:
        pass


def last() -> dict[str, Any]:
    return _load(LAST_PATH) or {"ok": False, "note": "No hunt has run yet. hunter action=hunt runs one."}


def _load(path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _save(path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def dispatch(action: str = "last", **kwargs: Any) -> Any:
    act = (action or "last").lower()
    if act in {"hunt", "scan", "run"}:
        return hunt(top=int(kwargs.get("top") or 15), refresh_liquid=bool(kwargs.get("refresh")))
    if act in {"last", "latest"}:
        return last()
    if act in {"liquid", "universe"}:
        out = liquid_universe(refresh=bool(kwargs.get("refresh")))
        return {"ok": True, "count": len(out["symbols"]), "listed": out.get("listed"), "source": out.get("source")}
    if act == "session":
        return {"ok": True, "session": session()}
    return {"error": f"unknown hunter action {act}", "actions": ["hunt", "last", "liquid", "session"]}
