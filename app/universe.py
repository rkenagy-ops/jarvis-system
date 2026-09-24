"""Where 'the full market' actually comes from.

marketbeast.py's notion of the "full" universe was the vendored scanner's own
FULL_MARKET list - DOW 30 + a top-100ish slice of Nasdaq and the S&P plus the top of
the Russell 2000 plus a handful of ETFs. That is 273 names total, hardcoded in
scanner.py. Raising a truncation limit on top of that changes nothing: you cannot
scan thousands of stocks from a list of 273.

This module is the actual "thousands" source: Nasdaq publishes the full list of every
symbol listed on Nasdaq and on the other US exchanges it trades, for free, with no key,
no auth, updated daily - nasdaqlisted.txt and otherlisted.txt. Combined that is on the
order of several thousand tickers. It is cached (this doesn't change intraday) and
falls back to the vendored scanner's 273-symbol list if the fetch ever fails, so a
network hiccup degrades the scan rather than breaking it.

    universe action=full                 -> the full cached ticker list
    universe action=refresh              -> force a re-fetch from Nasdaq
    universe action=status               -> when it was last fetched, how many symbols, which source
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from . import config

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SuperJarvis/1.0"}
_CACHE_PATH = config.DATA_DIR / "universe_cache.json"
_CACHE_TTL = 24 * 3600  # the symbol directory changes at most once a day

_NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def _parse_nasdaqlisted(text: str) -> list[str]:
    """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"""
    out = []
    lines = text.strip().splitlines()
    for line in lines[1:]:  # header
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 4:
            continue
        symbol, test_issue = parts[0].strip(), parts[3].strip()
        if symbol and test_issue != "Y":
            out.append(symbol)
    return out


def _parse_otherlisted(text: str) -> list[str]:
    """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"""
    out = []
    lines = text.strip().splitlines()
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol, test_issue = parts[0].strip(), parts[6].strip()
        if symbol and test_issue != "Y":
            out.append(symbol)
    return out


def _fetch_one(url: str) -> str:
    with httpx.Client(timeout=20.0, headers=_UA) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _fallback_universe() -> list[str]:
    """The vendored scanner's own curated list - always available, no network."""
    try:
        from . import marketbeast

        sc = marketbeast._load_scanner()
        return sorted(set(getattr(sc, "FULL_MARKET", []) or []))
    except Exception:
        return []


def _fetch_from_nasdaq() -> list[str]:
    a = _parse_nasdaqlisted(_fetch_one(_NASDAQ_LISTED))
    b = _parse_otherlisted(_fetch_one(_OTHER_LISTED))
    symbols = sorted(set(a) | set(b))
    # Symbols with a class-share suffix (BRK.A style, or the 5th-letter suffixes
    # Nasdaq encodes for warrants/units/rights) aren't tradeable through a plain
    # equity quote the way this scanner fetches them - drop anything that isn't a
    # clean 1-5 letter ticker.
    return [s for s in symbols if s.isalpha() and 1 <= len(s) <= 5]


def _read_cache() -> dict[str, Any] | None:
    if not _CACHE_PATH.is_file():
        return None
    try:
        import json

        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "symbols" not in data:
            return None
        return data
    except Exception:
        return None


def _write_cache(symbols: list[str], source: str) -> None:
    import json

    payload = {"symbols": symbols, "source": source, "fetched_at": time.time()}
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass  # a cache write failure should never break the scan that triggered it


def full(*, force: bool = False) -> dict[str, Any]:
    """The full ticker universe, cached, Nasdaq-sourced, safety-net-backed.

    force=True skips the cache and re-fetches. Either way this never raises - a
    total failure returns the vendored 273-symbol fallback rather than an empty
    universe, since scanning nothing is a worse failure mode than scanning less.
    """
    if not force:
        cached = _read_cache()
        if cached and (time.time() - cached.get("fetched_at", 0)) < _CACHE_TTL:
            return {"ok": True, "symbols": cached["symbols"], "count": len(cached["symbols"]),
                     "source": cached.get("source"), "cached": True}

    try:
        symbols = _fetch_from_nasdaq()
        if symbols:
            _write_cache(symbols, "nasdaq")
            return {"ok": True, "symbols": symbols, "count": len(symbols), "source": "nasdaq", "cached": False}
    except Exception as exc:
        nasdaq_err = f"{type(exc).__name__}: {exc}"
    else:
        nasdaq_err = "Nasdaq symbol directory returned nothing usable"

    # Nasdaq fetch failed - stale cache beats no cache, fallback list beats stale cache
    # only if there is no cache at all.
    cached = _read_cache()
    if cached and cached.get("symbols"):
        return {"ok": True, "symbols": cached["symbols"], "count": len(cached["symbols"]),
                 "source": cached.get("source"), "cached": True, "warning": f"Nasdaq fetch failed ({nasdaq_err}); serving stale cache."}

    fallback = _fallback_universe()
    return {"ok": True, "symbols": fallback, "count": len(fallback), "source": "vendored_fallback",
             "cached": False, "warning": f"Nasdaq fetch failed ({nasdaq_err}); using the {len(fallback)}-symbol vendored list."}


def status() -> dict[str, Any]:
    cached = _read_cache()
    if not cached:
        return {"ok": True, "cached": False, "note": "No universe fetched yet."}
    age = time.time() - cached.get("fetched_at", 0)
    return {
        "ok": True,
        "cached": True,
        "source": cached.get("source"),
        "count": len(cached.get("symbols") or []),
        "age_sec": round(age),
        "stale": age > _CACHE_TTL,
    }


def dispatch(action: str = "full", **kwargs: Any) -> Any:
    act = (action or "full").lower()
    if act in {"full", "all", "market"}:
        return full(force=bool(kwargs.get("force")))
    if act == "refresh":
        return full(force=True)
    if act == "status":
        return status()
    return {"error": f"unknown universe action {act}", "actions": ["full", "refresh", "status"]}
