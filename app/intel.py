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


def advise(*, top: int = 6, dte: int = 7) -> dict[str, Any]:
    """Full public+IBKR desk briefing. Not dark pools or every paid wire."""
    from datetime import date

    from . import obsidian

    scanned = scan("all", threshold=1.0)
    quotes = {q.get("symbol"): q for q in (scanned.get("quotes") or []) if q.get("symbol")}
    for extra in TAPE:
        if extra not in quotes:
            quotes[extra] = markets.quote(extra)
    snap = feeds.snapshot()
    reg = regime(quotes)
    spy = markets.analyze("SPY")
    fg = _fear_greed()
    beast = _beast(top, dte)
    picks = list(beast.get("picks") or [])
    try:
        from . import ibkr

        perm = ibkr.permissions()
        acct = None
        if perm.get("ok") and not ibkr.busy():
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(ibkr.account)
                try:
                    acct = fut.result(timeout=8)
                except Exception:
                    acct = None
            if acct and acct.get("error"):
                acct = None
    except Exception:
        perm = {"can_trade": False, "ok": False}
        acct = None
    bp = None
    if acct:
        bp = _num(acct.get("buying_power")) or _num(acct.get("available_funds"))
    ideas = _ideas(reg["bias"], picks, spy, bp)
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
            f"---\ntype: desk\ndate: {day}\nbias: {reg['bias']}\n---\n",
            f"# Desk {day} — {reg['bias']}\n",
            f"{reg['why']}\n",
        ]
        for idea in ideas:
            lines.append(f"- [{idea.get('grade')}] {idea.get('action')} {idea.get('symbol')} — {idea.get('thesis')}")
        rel = f"Markets/{day}-desk.md"
        obsidian.write_note(rel, "\n".join(lines) + "\n")
        note = rel
    except Exception:
        note = None
    return {
        "ok": True,
        "role": "desk-analyst",
        "disclaimer": "Public Yahoo + RSS + MarketBeast + IBKR overlay when TWS listens. Not Level 2, dark pools, or every paid wire. Advice, not a fill.",
        "regime": reg,
        "fear_greed": fg,
        "tape": tape,
        "sectors": sectors[:11],
        "spy": {"quote": spy.get("quote"), "stats": spy.get("stats")},
        "movers": scanned.get("movers") or [],
        "news": [{"source": n.get("source"), "title": n.get("title")} for n in news],
        "options": picks[:top],
        "ideas": ideas,
        "ibkr": {
            "can_trade": bool((perm or {}).get("can_trade")),
            "live": bool((perm or {}).get("gateway_live")),
            "hint": (perm or {}).get("hint") or (perm or {}).get("note"),
            "net_liquidation": (acct or {}).get("net_liquidation") if acct else None,
            "buying_power": (acct or {}).get("buying_power") if acct else None,
            "positions": ((acct or {}).get("positions") or [])[:12] if acct else [],
        },
        "vault": note,
        "next": (
            "TWS live. Say confirm on a ticket to send."
            if (perm or {}).get("can_trade")
            else "Log into TWS on the desktop (not here). Port 7496 must listen before live tickets."
        ),
    }
