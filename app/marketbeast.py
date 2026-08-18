"""Internal MarketBeast desk. Vendored from D:\\MARKETBEAST (v9 + v8)."""

from __future__ import annotations

import sys
import time
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
    fallback = VENDOR / "marketbeast hypertrader 8 - Copy" / "hypertrader"
    return fallback


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


def _pick(row: dict) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "option_type": row.get("option_type"),
        "strike": row.get("strike"),
        "option_price": row.get("option_price"),
        "delta": row.get("delta"),
        "itm_prob": row.get("itm_prob"),
        "expiration": row.get("expiration"),
        "dte": row.get("dte"),
        "iv": row.get("iv"),
        "score": row.get("score"),
        "option_score": row.get("option_score"),
        "combined_score": row.get("combined_score"),
        "price": row.get("price"),
        "rsi": row.get("rsi"),
    }


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
    }
    return mapping.get(uni)


def _score_calls(scanner, symbols: list[str], *, dte: int, top: int) -> list[dict]:
    picks = []
    for symbol in symbols:
        df = scanner.fetch_data(symbol)
        if df is None or len(df) < 20:
            continue
        try:
            analysis = scanner.analyze(symbol, df)
        except Exception:
            continue
        if analysis.get("direction") not in {"BULLISH", "NEUTRAL"}:
            continue
        opts = scanner.get_options_data(symbol, target_dte=dte)
        if not opts or not opts.get("preferred_calls"):
            continue
        best = opts["preferred_calls"][0]
        analysis.update(
            {
                "option_type": "CALL",
                "strike": best.get("strike"),
                "option_price": best.get("price"),
                "delta": best.get("delta"),
                "itm_prob": best.get("itm_prob"),
                "expiration": opts.get("expiration"),
                "dte": opts.get("dte"),
                "iv": opts.get("iv"),
                "option_score": best.get("score"),
                "combined_score": float(analysis.get("score") or 0) * 0.6 + float(best.get("score") or 0) / 100 * 0.4,
            }
        )
        picks.append(_pick(analysis))
    picks.sort(key=lambda x: float(x.get("combined_score") or 0), reverse=True)
    return picks[:top]


def _write_vault(picks: list[dict], universe: str) -> str | None:
    if not picks:
        return None
    day = date.today().isoformat()
    lines = [f"---\ntype: options\ndate: {day}\nuniverse: {universe}\n---\n", f"# MarketBeast calls {day} ({universe})\n"]
    for p in picks:
        lines.append(
            f"- {p.get('symbol')} {p.get('expiration')} {p.get('strike')}C @ {p.get('option_price')} "
            f"Δ{p.get('delta')} score={p.get('combined_score')}"
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
    key = f"{uni}:{top}:{dte}"
    now = time.time()
    if _cache["picks"] and _cache["key"] == key and now - float(_cache["at"] or 0) < 90:
        return {"ok": True, "cached": True, "universe": uni, "picks": _cache["picks"][:top], **ready()}
    sc = _load_scanner()
    scanner = sc.StockScanner()
    if uni == "full":
        rows = sc.find_best_options(scanner, top_n=top, target_dte=dte, direction_filter="bullish")
        picks = [_pick(r) for r in rows if (r.get("option_type") or "").upper() == "CALL"]
    elif uni in {"dow", "nasdaq", "sp500", "russell", "etfs"}:
        symbols = _sector_symbols(sc, uni) or []
        picks = _score_calls(scanner, list(symbols)[:80], dte=dte, top=top)
    else:
        picks = _score_calls(scanner, _liquid_symbols(), dte=dte, top=top)
    _cache.update(at=now, key=key, picks=picks)
    note = _write_vault(picks, uni)
    return {
        "ok": True,
        "cached": False,
        "universe": uni,
        "vault": note,
        "disclaimer": "Signals only. Not advice. Paper ticket or IBKR+confirm to buy.",
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
    calls = (opts.get("preferred_calls") or [])[:5]
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
