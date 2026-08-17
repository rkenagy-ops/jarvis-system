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
