"""Internal MarketBeast desk. v9 engine + Super Jarvis quality layer."""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from . import config, obsidian

_cache: dict[str, Any] = {"at": 0.0, "key": "", "picks": []}
VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "marketbeast"


def root() -> Path:
    configured = Path(config.MARKETBEAST_ROOT or "").expanduser()
    if (configured / "scanner.py").is_file():
        return configured
    primary = VENDOR / "hypertrader"
    if (primary / "scanner.py").is_file():
        return primary
    return VENDOR / "marketbeast hypertrader 8 - Copy" / "hypertrader"


def ready() -> dict[str, Any]:
    r = root()
    scanner = r / "scanner.py"
    v8 = VENDOR / "marketbeast hypertrader 8 - Copy" / "hypertrader" / "scanner.py"
    v9 = VENDOR / "hypertrader" / "scanner.py"
    return {
        "ok": scanner.is_file(),
        "root": str(r),
        "scanner": str(scanner) if scanner.is_file() else None,
        "v9": v9.is_file(),
        "v8": v8.is_file(),
        "engine": "v9" if r.name == "hypertrader" and "Copy" not in str(r) else "v8",
        "layer": "super-5.6",
    }


def _load_scanner():
    info = ready()
    if not info["ok"]:
        raise FileNotFoundError(f"MarketBeast scanner.py not found at {info['root']}")
    path = str(root())
    if path not in sys.path:
        sys.path.insert(0, path)
    import importlib

    if "scanner" in sys.modules:
        return importlib.reload(sys.modules["scanner"])
    import scanner as sc  # type: ignore

    return sc


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def grade(pick: dict[str, Any]) -> str:
    """A = liquid + sane delta. WATCH = junk or too wide."""
    score = 0
    spread = pick.get("spread")
    if spread is not None:
        if spread <= 0.06:
            score += 2
        elif spread <= 0.10:
            score += 1
        elif spread > 0.18:
            score -= 2
    oi = int(pick.get("oi") or 0)
    if oi >= 500:
        score += 2
    elif oi >= 80:
        score += 1
    delta = abs(_num(pick.get("delta")))
    if 0.35 <= delta <= 0.60:
        score += 2
    elif 0.25 <= delta <= 0.70:
        score += 1
    if _num(pick.get("combined_score")) >= 0.7:
        score += 1
    if _num(pick.get("option_price")) < 0.15:
        score -= 2
    if score >= 6:
        return "A"
    if score >= 4:
        return "B"
    if score >= 2:
        return "C"
    return "WATCH"


def enrich(row: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    extra = extra or {}
    bid = _num(extra.get("bid") if extra.get("bid") is not None else row.get("bid"))
    ask = _num(extra.get("ask") if extra.get("ask") is not None else row.get("ask"))
    mid = _num(row.get("option_price"))
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread = (ask - bid) / ask
    else:
        spread = None
    strike = _num(row.get("strike"))
    debit = mid
    spot = _num(row.get("price"))
    out = {
        "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "option_type": row.get("option_type") or "CALL",
        "moneyness": extra.get("type") or row.get("moneyness"),
        "strike": strike or None,
        "option_price": debit or None,
        "bid": bid or None,
        "ask": ask or None,
        "spread": round(spread, 4) if spread is not None else None,
        "delta": row.get("delta"),
        "itm_prob": row.get("itm_prob"),
        "expiration": row.get("expiration"),
        "dte": row.get("dte"),
        "iv": row.get("iv"),
        "oi": int(extra.get("oi") or row.get("oi") or 0),
        "volume": int(extra.get("volume") or row.get("volume") or 0),
        "score": row.get("score"),
        "option_score": extra.get("score") or row.get("option_score"),
        "combined_score": row.get("combined_score"),
        "price": spot or None,
        "rsi": row.get("rsi"),
        "breakeven": round(strike + debit, 2) if strike and debit else None,
        "max_loss": round(debit * 100, 2) if debit else None,
        "reason": extra.get("reason") or row.get("reason"),
        "quote_source": extra.get("source") or "yahoo",
    }
    out["grade"] = grade(out)
    out["buyable"] = out["grade"] in {"A", "B"}
    return out


def _liquid_symbols() -> list[str]:
    extra = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "AMD", "AVGO", "GOOGL"]
    out: list[str] = []
    for s in list(config.WATCHLIST) + extra:
        u = s.strip().upper()
        if u and u not in out and "-USD" not in u and not u.startswith("^"):
            out.append(u)
    return out[:16]


def _sector_symbols(sc, universe: str) -> list[str] | None:
    uni = universe.lower()
    mapping = {
        "dow": getattr(sc, "DOW_30", None),
        "nasdaq": getattr(sc, "NASDAQ_100", None),
        "sp500": getattr(sc, "SP500_TOP_100", None),
        "russell": getattr(sc, "RUSSELL_2000_TOP", None),
        "etfs": list(getattr(sc, "ETFS", {}) or {}),
        "full": getattr(sc, "FULL_MARKET", None),
    }
    return mapping.get(uni)


def _analyze_one(scanner, symbol: str, dte: int) -> dict | None:
    df = scanner.fetch_data(symbol)
    if df is None or len(df) < 20:
        return None
    try:
        analysis = scanner.analyze(symbol, df)
    except Exception:
        return None
    if analysis.get("direction") not in {"BULLISH", "NEUTRAL"}:
        return None
    opts = scanner.get_options_data(symbol, target_dte=dte)
    if not opts or not opts.get("preferred_calls"):
        return None
    best = opts["preferred_calls"][0]
    analysis.update(
        {
            "option_type": "CALL",
            "strike": best.get("strike"),
            "option_price": best.get("price"),
            "bid": best.get("bid"),
            "ask": best.get("ask"),
            "delta": best.get("delta"),
            "itm_prob": best.get("itm_prob"),
            "expiration": opts.get("expiration"),
            "dte": opts.get("dte"),
            "iv": opts.get("iv"),
            "oi": best.get("oi"),
            "volume": best.get("volume"),
            "option_score": best.get("score"),
            "combined_score": float(analysis.get("score") or 0) * 0.6 + float(best.get("score") or 0) / 100 * 0.4,
            "moneyness": best.get("type"),
            "reason": best.get("reason"),
        }
    )
    return enrich(analysis, best)


def _score_calls(scanner, symbols: list[str], *, dte: int, top: int) -> list[dict]:
    picks: list[dict] = []
    workers = min(8, max(2, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_analyze_one, scanner, symbol, dte): symbol for symbol in symbols}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                picks.append(row)
    picks.sort(key=lambda x: (x.get("buyable"), _num(x.get("combined_score"))), reverse=True)
    return picks[:top]


def _overlay_ibkr(picks: list[dict]) -> list[dict]:
    if not picks:
        return picks
    try:
        from . import ibkr

        if not ibkr.port_open():
            return picks
        specs = [
            {
                "symbol": p.get("symbol"),
                "expiry": p.get("expiration"),
                "strike": p.get("strike"),
                "right": "C",
            }
            for p in picks[:6]
        ]
        quotes = ibkr.option_quotes(specs)
    except Exception:
        return picks
    for p in picks:
        expiry = str(p.get("expiration") or "").replace("-", "")
        key = f"{p.get('symbol')}-{expiry}-{_num(p.get('strike')):g}C"
        q = quotes.get(key)
        if not q:
            continue
        p["bid"] = q.get("bid") or p.get("bid")
        p["ask"] = q.get("ask") or p.get("ask")
        if q.get("mid"):
            p["option_price"] = q["mid"]
        if p.get("bid") and p.get("ask"):
            ask = _num(p["ask"])
            p["spread"] = round((_num(p["ask"]) - _num(p["bid"])) / ask, 4) if ask else p.get("spread")
        p["max_loss"] = round(_num(p.get("option_price")) * 100, 2)
        if p.get("strike") and p.get("option_price"):
            p["breakeven"] = round(_num(p["strike"]) + _num(p["option_price"]), 2)
        p["quote_source"] = "ibkr"
        p["grade"] = grade(p)
        p["buyable"] = p["grade"] in {"A", "B"}
    picks.sort(key=lambda x: (x.get("buyable"), _num(x.get("combined_score"))), reverse=True)
    return picks


def _write_vault(picks: list[dict], universe: str) -> str | None:
    if not picks:
        return None
    day = date.today().isoformat()
    lines = [
        f"---\ntype: options\ndate: {day}\nuniverse: {universe}\nlayer: super-5.6\n---\n",
        f"# MarketBeast calls {day} ({universe})\n",
        "Grade A/B = liquid enough to ticket. C/WATCH = look only.\n",
    ]
    for p in picks:
        flag = "BUYABLE" if p.get("buyable") else "WATCH"
        lines.append(
            f"- [{p.get('grade')}/{flag}] {p.get('symbol')} {p.get('expiration')} "
            f"{p.get('strike')}C @ {p.get('option_price')} "
            f"spread={p.get('spread')} Δ{p.get('delta')} "
            f"max_loss={p.get('max_loss')} be={p.get('breakeven')} via {p.get('quote_source')}"
        )
    rel = f"Markets/{day}-calls.md"
    try:
        obsidian.write_note(rel, "\n".join(lines) + "\n")
        return rel
    except Exception:
        return None


def best_calls(*, top: int = 8, universe: str = "liquid", dte: int = 7) -> dict[str, Any]:
    top = max(3, min(int(top or 8), 20))
    dte = max(2, min(int(dte or 7), 45))
    uni = (universe or "liquid").lower()
    key = f"{uni}:{top}:{dte}:v56"
    now = time.time()
    if _cache["picks"] and _cache["key"] == key and now - float(_cache["at"] or 0) < 90:
        return {"ok": True, "cached": True, "universe": uni, "picks": _cache["picks"][:top], **ready()}
    sc = _load_scanner()
    scanner = sc.StockScanner()
    if uni == "liquid":
        symbols = _liquid_symbols()
    else:
        symbols = list(_sector_symbols(sc, uni) or _liquid_symbols())
        if uni == "full":
            symbols = symbols[:220]
        elif uni in {"nasdaq", "sp500"}:
            symbols = symbols[:80]
    picks = _score_calls(scanner, symbols, dte=dte, top=max(top, 10))
    picks = _overlay_ibkr(picks)[:top]
    _cache.update(at=now, key=key, picks=picks)
    note = _write_vault(picks, uni)
    buyable = [p for p in picks if p.get("buyable")]
    return {
        "ok": True,
        "cached": False,
        "universe": uni,
        "scanned": len(symbols),
        "buyable": len(buyable),
        "vault": note,
        "disclaimer": "Signals only. Grade A/B can paper-ticket. Live IBKR still needs TWS + confirm.",
        "picks": picks,
        **ready(),
    }


def deep(symbol: str, *, dte: int = 7) -> dict[str, Any]:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"error": "symbol required"}
    sc = _load_scanner()
    scanner = sc.StockScanner()
    df = scanner.fetch_data(symbol)
    if df is None:
        return {"error": f"no data for {symbol}"}
    analysis = scanner.analyze(symbol, df)
    opts = scanner.get_options_data(symbol, target_dte=dte) or {}
    raw = (opts.get("preferred_calls") or [])[:5]
    calls = [enrich({**analysis, "option_type": "CALL", "expiration": opts.get("expiration"), "dte": opts.get("dte"), "option_price": c.get("price"), **c}, c) for c in raw]
    calls = _overlay_ibkr(calls)
    return {
        "ok": True,
        "symbol": symbol,
        "analysis": {k: analysis.get(k) for k in ("price", "direction", "score", "rsi", "change_1d", "change_1w")},
        "calls": calls,
        "expiration": opts.get("expiration"),
        "dte": opts.get("dte"),
    }


def paper_buy(symbol: str, expiry: str, strike: float, *, debit: float, qty: int = 1) -> dict[str, Any]:
    from . import markets

    return markets.paper_option_buy(symbol, expiry, strike, right="C", qty=qty, debit=debit)


def dispatch(action: str, **kwargs: Any) -> dict[str, Any]:
    act = (action or "calls").lower()
    if act in {"calls", "best", "scan", "options"}:
        return best_calls(
            top=int(kwargs.get("top") or kwargs.get("qty") or 8),
            universe=str(kwargs.get("universe") or "liquid"),
            dte=int(kwargs.get("dte") or 7),
        )
    if act == "deep":
        return deep(kwargs.get("symbol") or kwargs.get("query") or "", dte=int(kwargs.get("dte") or 7))
    if act in {"paper", "paper_buy"}:
        return paper_buy(
            kwargs.get("symbol") or "",
            kwargs.get("expiry") or "",
            float(kwargs.get("strike") or 0),
            debit=float(kwargs.get("debit") or kwargs.get("option_price") or 0),
            qty=int(kwargs.get("qty") or 1),
        )
    if act == "book":
        from . import markets

        return {"ok": True, "options": markets.list_paper_options()}
    if act == "status":
        return ready()
    return {"error": f"unknown marketbeast action {act}"}
