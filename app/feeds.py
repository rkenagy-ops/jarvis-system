"""Live public feeds — Yahoo Finance quotes + news wires. Outbound only."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from . import config, markets
from . import guard

NEWS_FEEDS = {
    "bbc": "https://feeds.bbci.co.uk/news/rss.xml",
    "bbc_business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "npr": "https://feeds.npr.org/1001/rss.xml",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "hn": "https://hnrss.org/frontpage",
}

TTL_SEC = 20
_cache: dict[str, Any] = {"at": 0.0, "data": None}


def _parse_feed(xml: str, source: str) -> list[dict]:
    root = ET.fromstring(xml)
    items: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title:
            continue
        items.append(
            {
                "source": source,
                "title": title,
                "link": link,
                "when": (item.findtext("pubDate") or item.findtext("updated") or "").strip(),
            }
        )
    atom = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{atom}entry"):
        title = (entry.findtext(f"{atom}title") or "").strip()
        link_el = entry.find(f"{atom}link")
        href = (link_el.get("href") if link_el is not None else "") or ""
        if not title:
            continue
        items.append(
            {
                "source": source,
                "title": title,
                "link": href,
                "when": (entry.findtext(f"{atom}updated") or entry.findtext(f"{atom}published") or "").strip(),
            }
        )
    return items[:12]


def _pull_news(source: str, url: str) -> list[dict]:
    if not guard.allow_url(url):
        return []
    try:
        resp = guard.fetch_public(url, timeout=12.0, headers={"User-Agent": "SuperJarvis/3.3"})
        return _parse_feed(resp.text, source)
    except Exception:
        return []


def _quotes() -> list[dict]:
    symbols = list(config.WATCHLIST)
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(markets.quote, s): s for s in symbols}
        for fut in as_completed(futs):
            try:
                out.append(fut.result())
            except Exception as exc:
                out.append({"symbol": futs[fut], "error": str(exc)})
    order = {s: i for i, s in enumerate(symbols)}
    out.sort(key=lambda q: order.get(q.get("symbol") or "", 99))
    return out


def snapshot(*, force: bool = False) -> dict[str, Any]:
    now = time.time()
    cached = _cache.get("data")
    if cached and not force and now - float(_cache.get("at") or 0) < TTL_SEC:
        return cached
    buckets: dict[str, list[dict]] = {name: [] for name in NEWS_FEEDS}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_pull_news, name, url): name for name, url in NEWS_FEEDS.items()}
        qfut = pool.submit(_quotes)
        for fut, name in futs.items():
            buckets[name] = fut.result() or []
        quotes = qfut.result()
    seen: set[str] = set()
    unique: list[dict] = []
    idx = 0
    while len(unique) < 24:
        progressed = False
        for name in NEWS_FEEDS:
            rows = buckets.get(name) or []
            if idx >= len(rows):
                continue
            item = rows[idx]
            key = (item.get("title") or "").lower()
            progressed = True
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
            if len(unique) >= 24:
                break
        if not progressed:
            break
        idx += 1
    data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ttl_sec": TTL_SEC,
        "quotes": quotes,
        "news": unique,
        "sources": list(NEWS_FEEDS),
    }
    _cache["at"] = now
    _cache["data"] = data
    return data


def headlines(limit: int = 8) -> list[str]:
    return [n.get("title") or "" for n in (snapshot().get("news") or [])[:limit] if n.get("title")]
