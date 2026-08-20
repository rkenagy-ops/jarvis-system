"""News + market desk. Public wires and Yahoo — not literally every venue on earth."""

from __future__ import annotations

import re
import time
from typing import Any

from . import feeds, markets

_scan_cache: dict[str, Any] = {}

UNIVERSES: dict[str, list[str]] = {
    "core": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "BTC-USD"],
    "indices": ["^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"],
    "sectors": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"],
    "mega": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "BRK-B"],
    "fx": ["EURUSD=X", "GBPUSD=X", "JPY=X"],
    "commod": ["GC=F", "CL=F", "SI=F", "NG=F"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
}

ALIASES = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "amazon": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "bitcoin": "BTC-USD",
    "ether": "ETH-USD",
    "ethereum": "ETH-USD",
    "oil": "CL=F",
    "gold": "GC=F",
    "fed": "SPY",
    "s&p": "SPY",
    "nasdaq": "QQQ",
}


def universe(name: str = "all") -> list[str]:
    if name == "all" or not name:
        seen, out = set(), []
        for rows in UNIVERSES.values():
            for s in rows:
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        return out
    return list(UNIVERSES.get(name, UNIVERSES["core"]))


def scan(name: str = "all", *, threshold: float = 1.5) -> dict[str, Any]:
    key = f"{name}:{threshold}"
    hit = _scan_cache.get(key)
    if hit and time.time() - hit["at"] < 30:
        return hit["data"]
    symbols = universe(name)
    quotes = markets.watchlist(symbols)
    movers = []
    for q in quotes:
        pct = q.get("change_pct")
        if isinstance(pct, (int, float)) and abs(pct) >= threshold:
            movers.append(q)
    movers.sort(key=lambda q: abs(float(q.get("change_pct") or 0)), reverse=True)
    data = {
        "universe": name,
        "count": len(quotes),
        "threshold": threshold,
        "movers": movers,
        "quotes": quotes,
    }
    _scan_cache[key] = {"at": time.time(), "data": data}
    return data


def _tickers_in(text: str) -> list[str]:
    low = (text or "").lower()
    hits = []
    for word, sym in ALIASES.items():
        if word in low and sym not in hits:
            hits.append(sym)
    for m in re.findall(r"\b([A-Z]{1,5})\b", text or ""):
        if m in {"AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "SPY", "QQQ", "JPM", "AVGO"} and m not in hits:
            hits.append(m)
    return hits


def desk(*, threshold: float = 1.5) -> dict[str, Any]:
    snap = feeds.snapshot()
    scanned = scan("all", threshold=threshold)
    news = snap.get("news") or []
    linked = []
    for item in news:
        ticks = _tickers_in(item.get("title") or "")
        if ticks:
            linked.append({**item, "tickers": ticks})
    return {
        "updated": snap.get("updated"),
        "movers": scanned["movers"][:12],
        "scanned": scanned["count"],
        "news": news[:16],
        "linked": linked[:12],
        "sources": snap.get("sources") or [],
        "note": "Public Yahoo + RSS desk. Not every dark-pool print or paywalled wire.",
    }


TAPE = ["SPY", "QQQ", "IWM", "DIA", "^VIX", "^TNX", "GC=F", "CL=F", "BTC-USD"]


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def regime(quotes: dict[str, dict]) -> dict[str, Any]:
    """Desk bias from VIX, SPY/QQQ tape, and XLK vs XLU leadership."""
    vix = _num((quotes.get("^VIX") or {}).get("price"))
    spy_pct = _num((quotes.get("SPY") or {}).get("change_pct"), 0.0) or 0.0
    qqq_pct = _num((quotes.get("QQQ") or {}).get("change_pct"), 0.0) or 0.0
    xlk = _num((quotes.get("XLK") or {}).get("change_pct"), 0.0) or 0.0
    xlu = _num((quotes.get("XLU") or {}).get("change_pct"), 0.0) or 0.0
    if vix is not None and vix >= 26:
        bias = "risk-off"
        why = f"VIX {vix:.1f} is elevated — do not chase calls."
    elif vix is not None and vix <= 16 and spy_pct >= 0 and xlk >= xlu:
        bias = "risk-on"
        why = f"VIX {vix:.1f}, SPY {spy_pct:+.2f}%, tech leading utilities."
    elif spy_pct <= -1.2 or (vix is not None and vix >= 20 and spy_pct < 0):
        bias = "cautious"
        why = f"Tape is heavy (SPY {spy_pct:+.2f}%, VIX {vix})."
    else:
        bias = "mixed"
        why = "No clean regime. Trade smaller or wait for A-grade only."
    return {
        "bias": bias,
        "vix": vix,
        "spy_pct": round(spy_pct, 2),
        "qqq_pct": round(qqq_pct, 2),
        "xlk_vs_xlu": round(xlk - xlu, 2),
        "why": why,
    }


def _fear_greed() -> dict[str, Any] | None:
    try:
        from . import catalog

        raw = catalog.call("fear_greed")
        row = (raw.get("data") or [None])[0] or {}
        if not row:
            return None
        return {
            "value": int(float(row.get("value") or 0)),
            "label": row.get("value_classification"),
            "as_of": row.get("timestamp"),
        }
    except Exception:
        return None


def _beast(top: int, dte: int) -> dict[str, Any]:
    try:
        from concurrent.futures import ThreadPoolExecutor

        from . import marketbeast

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(marketbeast.best_calls, top=top, universe="liquid", dte=dte)
            return fut.result(timeout=22)
    except Exception as exc:
        return {"ok": False, "picks": [], "error": str(exc)[:200]}


def decide(
    *,
    regime: dict[str, Any],
    fear_greed: dict[str, Any] | None,
    spy: dict[str, Any],
    picks: list[dict],
    ibkr: dict[str, Any],
    breadth: dict[str, Any] | None = None,
    symbol: str | None = None,
    name: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GO / NO-GO with a factor breakdown. Force NO-GO on risk-off."""
    bias = (regime or {}).get("bias") or "mixed"
    vix = _num((regime or {}).get("vix"))
    stats = (spy or {}).get("stats") or {}
    trend = stats.get("trend")
    rsi = _num(stats.get("rsi14"))
    fg_val = _num((fear_greed or {}).get("value"))
    buyable = [p for p in (picks or []) if p.get("buyable")]
    best = buyable[0] if buyable else None
    if symbol and name:
        named = [p for p in ((name.get("calls") or []) if isinstance(name, dict) else []) if p.get("buyable")]
        if named:
            best = named[0]
            buyable = named
        direction = ((name.get("analysis") or {}) if isinstance(name, dict) else {}).get("direction")
    else:
        direction = None

    factors: list[dict[str, Any]] = []

    def add(factor: str, ok: bool, detail: str) -> None:
        factors.append({"factor": factor, "pass": bool(ok), "detail": detail})

    add("Regime", bias == "risk-on", (regime or {}).get("why") or bias)
    add("VIX", vix is not None and vix < 22, f"VIX {vix}" if vix is not None else "VIX n/a")
    add("SPY trend", trend == "up" and (rsi is None or rsi < 72), f"trend={trend} RSI={rsi}")
    if breadth:
        up, n = int(breadth.get("up") or 0), int(breadth.get("n") or 0)
        add("Breadth", n > 0 and up >= n / 2, f"{up}/{n} names green")
    if fear_greed:
        add("Fear/greed", fg_val is not None and 25 <= fg_val <= 70, f"{fear_greed.get('label')} ({fg_val})")
    add("Options A/B", bool(best), f"{len(buyable)} buyable graded calls" if buyable else "no A/B calls")
    if symbol:
        bull = str(direction or "").upper() in {"BULLISH", "UP"}
        add(f"{symbol} setup", bull and bool(best), f"direction={direction or 'n/a'} best={best.get('grade') if best else 'none'}")
    add("IBKR", bool((ibkr or {}).get("can_trade")), (ibkr or {}).get("hint") or "TWS not live")

    forced_off = bias == "risk-off" or (vix is not None and vix >= 26)
    name_fail = bool(symbol) and not (str(direction or "").upper() in {"BULLISH", "UP"} and best)
    cautious_block = bias == "cautious" and not (best and best.get("grade") == "A" and trend == "up")
    enter = (not forced_off) and (not name_fail) and (not cautious_block) and bool(best) and bias in {"risk-on", "mixed"}
    if bias == "mixed" and best and best.get("grade") != "A":
        enter = False
    verdict = "ENTER" if enter else "NO-GO"
    if enter and best:
        headline = (
            f"ENTER {best.get('symbol')} {best.get('expiration')} {best.get('strike')}C "
            f"grade {best.get('grade')} — 1 contract, max loss ${best.get('max_loss')}."
        )
        spoken = (
            f"Enter. {best.get('symbol')} {best.get('strike')} call, grade {best.get('grade')}. "
            f"Invalidation is VIX through 26."
        )
    elif forced_off:
        headline = "NO-GO. Do not enter a new long. Risk-off tape — wait."
        spoken = f"No-go. Do not enter. {(regime or {}).get('why') or 'Tape is risk-off.'}"
    elif symbol:
        headline = f"NO-GO on {symbol}. Setup is not A-grade in this regime."
        spoken = f"No-go on {symbol}. Do not enter this name right now."
    else:
        headline = "NO-GO. No A-grade ticket in this regime. Stay flat."
        spoken = "No-go. Do not enter. No A-grade setup — stay flat."
    spoken = " ".join(spoken.split())[:180]
    return {
        "enter": enter,
        "verdict": verdict,
        "headline": headline,
        "spoken": spoken,
        "breakdown": factors,
        "candidate": best,
        "symbol": symbol or (best.get("symbol") if best else None),
    }


def _ideas(bias: str, picks: list[dict], spy: dict, buying_power: float | None) -> list[dict]:
    size = (
        f"<= 1% of IBKR buying power (~${buying_power * 0.01:.0f}) or 1 contract"
        if buying_power and buying_power > 0
        else "1 contract (or paper 1% of 100k) until TWS live net liq is in"
    )
    invalid = "Stand down if SPY loses the session low or VIX spikes through 26."
    if bias == "risk-off":
        return [
            {
                "action": "STAND DOWN",
                "symbol": "SPY",
                "vehicle": "cash",
                "grade": "WATCH",
                "ready": False,
                "thesis": "Risk-off tape. No new long calls. Preserve cash; wait for VIX to cool.",
                "invalidation": "Revisit if VIX < 20 and SPY reclaims VWAP/SMA20.",
                "size": "flat",
            }
        ]
    ideas: list[dict] = []
    for p in picks:
        if not p.get("buyable"):
            continue
        ideas.append(
            {
                "action": "BUY CALL",
                "symbol": p.get("symbol"),
                "vehicle": "option",
                "grade": p.get("grade"),
                "ready": bool(p.get("buyable")),
                "expiry": p.get("expiration"),
                "strike": p.get("strike"),
                "right": "C",
                "debit": p.get("option_price"),
                "delta": p.get("delta"),
                "spread": p.get("spread"),
                "breakeven": p.get("breakeven"),
                "max_loss": p.get("max_loss"),
                "thesis": (
                    f"{p.get('symbol')} {p.get('expiration')} {p.get('strike')}C grade {p.get('grade')} "
                    f"— liquid, delta {p.get('delta')}, max loss ${p.get('max_loss')}."
                ),
                "invalidation": invalid,
                "size": size,
                "quote_source": p.get("quote_source"),
            }
        )
        if len(ideas) >= 4:
            break
    if not ideas:
        rsi = _num((spy.get("stats") or {}).get("rsi14"))
        trend = (spy.get("stats") or {}).get("trend")
        ideas.append(
            {
                "action": "WATCH SPY",
                "symbol": "SPY",
                "vehicle": "stock",
                "grade": "C",
                "ready": False,
                "thesis": f"No A/B calls. SPY trend={trend} RSI={rsi}. Do not force a ticket.",
                "invalidation": invalid,
                "size": "flat",
            }
        )
    return ideas


def advise(*, top: int = 6, dte: int = 7, symbol: str | None = None) -> dict[str, Any]:
    """Full public+IBKR desk. Returns ENTER / NO-GO with a factor breakdown."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date

    from . import obsidian

    symbol = (symbol or "").strip().upper() or None
    try:
        from . import ibkr

        perm_fn = ibkr.permissions
        acct_fn = ibkr.account
        ib_busy = ibkr.busy
        ib_ok_port = lambda: any(ibkr.port_open(p) for p in ibkr.PORTS)
    except Exception:
        perm_fn = lambda: {"can_trade": False, "ok": False}
        acct_fn = lambda: None
        ib_busy = lambda: True
        ib_ok_port = lambda: False

    name_job = None
    poly_desk: dict[str, Any] = {"ok": False, "ideas": []}
    with ThreadPoolExecutor(max_workers=8) as pool:
        f_scan = pool.submit(scan, "all", threshold=1.0)
        f_feed = pool.submit(feeds.snapshot)
        f_spy = pool.submit(markets.analyze, "SPY")
        f_fg = pool.submit(_fear_greed)
        f_beast = pool.submit(_beast, top, dte)
        f_perm = pool.submit(perm_fn)
        from . import poly as poly_mod

        f_poly = pool.submit(poly_mod.bounce, query=symbol or "", limit=6)
        if symbol:
            from . import marketbeast

            name_job = pool.submit(marketbeast.deep, symbol, dte=dte)
        scanned = f_scan.result()
        snap = f_feed.result()
        spy = f_spy.result()
        fg = f_fg.result()
        beast = f_beast.result()
        perm = f_perm.result() or {"can_trade": False, "ok": False}
        try:
            poly_desk = f_poly.result(timeout=12)
        except Exception:
            poly_desk = {"ok": False, "ideas": []}
        name = None
        if name_job:
            try:
                name = name_job.result(timeout=18)
            except Exception as exc:
                name = {"error": str(exc)[:160], "symbol": symbol}

    quotes = {q.get("symbol"): q for q in (scanned.get("quotes") or []) if q.get("symbol")}
    for extra in TAPE:
        if extra not in quotes:
            quotes[extra] = markets.quote(extra)
    reg = regime(quotes)
    picks = list(beast.get("picks") or [])
    acct = None
    if perm.get("ok") and not ib_busy() and ib_ok_port():
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                acct = pool.submit(acct_fn).result(timeout=8)
            if acct and acct.get("error"):
                acct = None
        except Exception:
            acct = None
    bp = None
    if acct:
        bp = _num(acct.get("buying_power")) or _num(acct.get("available_funds"))
    chg = [q for q in quotes.values() if isinstance(q.get("change_pct"), (int, float))]
    breadth = {"up": sum(1 for q in chg if q["change_pct"] > 0), "n": len(chg)}
    ibkr_block = {
        "can_trade": bool(perm.get("can_trade")),
        "live": bool(perm.get("gateway_live")),
        "hint": perm.get("hint") or perm.get("note"),
        "net_liquidation": (acct or {}).get("net_liquidation") if acct else None,
        "buying_power": (acct or {}).get("buying_power") if acct else None,
        "positions": ((acct or {}).get("positions") or [])[:12] if acct else [],
    }
    ideas = _ideas(reg["bias"], picks if not symbol else (name.get("calls") if isinstance(name, dict) else []) or picks, spy, bp)
    decision = decide(
        regime=reg,
        fear_greed=fg,
        spy=spy,
        picks=picks if not symbol else ((name or {}).get("calls") if isinstance(name, dict) else []) or [],
        ibkr=ibkr_block,
        breadth=breadth,
        symbol=symbol,
        name=name if isinstance(name, dict) else None,
    )
    if not decision["enter"]:
        ideas = [
            {
                "action": "STAND DOWN",
                "symbol": symbol or "SPY",
                "vehicle": "cash",
                "grade": "WATCH",
                "ready": False,
                "thesis": decision["headline"],
                "invalidation": "Revisit when regime is risk-on and an A-grade call appears.",
                "size": "flat",
            }
        ] + [i for i in ideas if i.get("ready")][:2]
    sectors = []
    for sym in UNIVERSES["sectors"]:
        q = quotes.get(sym) or {}
        if q.get("change_pct") is None:
            continue
        sectors.append({"symbol": sym, "change_pct": round(float(q["change_pct"]), 2), "price": q.get("price")})
    sectors.sort(key=lambda r: abs(r["change_pct"]), reverse=True)
    tape = []
    for sym in TAPE:
        q = quotes.get(sym) or {}
        tape.append({"symbol": sym, "price": q.get("price"), "change_pct": q.get("change_pct"), "source": q.get("source")})
    news = (snap.get("news") or [])[:10]
    note = None
    try:
        day = date.today().isoformat()
        lines = [
            f"---\ntype: desk\ndate: {day}\nbias: {reg['bias']}\nverdict: {decision['verdict']}\n---\n",
            f"# Desk {day} — {decision['verdict']} ({reg['bias']})\n",
            f"{decision['headline']}\n",
        ]
        for fac in decision.get("breakdown") or []:
            mark = "PASS" if fac.get("pass") else "FAIL"
            lines.append(f"- [{mark}] {fac.get('factor')}: {fac.get('detail')}")
        rel = f"Markets/{day}-desk.md"
        obsidian.write_note(rel, "\n".join(lines) + "\n")
        note = rel
    except Exception:
        note = None
    return {
        "ok": True,
        "role": "desk-analyst",
        "disclaimer": "Public Yahoo + RSS + MarketBeast + IBKR overlay when TWS listens. Not Level 2, dark pools, or every paid wire. Advice, not a fill.",
        "enter": decision["enter"],
        "verdict": decision["verdict"],
        "headline": decision["headline"],
        "spoken": decision["spoken"],
        "decision": decision,
        "symbol": symbol,
        "name": ({k: (name or {}).get(k) for k in ("symbol", "analysis", "calls", "error")} if name else None),
        "regime": reg,
        "fear_greed": fg,
        "breadth": breadth,
        "tape": tape,
        "sectors": sectors[:11],
        "spy": {"quote": spy.get("quote"), "stats": spy.get("stats")},
        "movers": scanned.get("movers") or [],
        "news": [{"source": n.get("source"), "title": n.get("title")} for n in news],
        "options": picks[:top],
        "polymarket": {
            "verdict": (poly_desk or {}).get("verdict"),
            "ideas": ((poly_desk or {}).get("ideas") or [])[:4],
            "note": (poly_desk or {}).get("disclaimer"),
        },
        "ideas": ideas,
        "ibkr": ibkr_block,
        "vault": note,
        "next": (
            "ENTER is a ticket, not a fill. Say confirm to send via TWS."
            if decision["enter"] and perm.get("can_trade")
            else "NO-GO — do not enter. Log into TWS on the desktop if you still want a live ticket later."
        ),
    }
