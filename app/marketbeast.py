"""Run Rhett's HyperTrader / MarketBeast scanner. Signals only — no silent orders."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from . import config

_cache: dict[str, Any] = {"at": 0.0, "key": "", "picks": []}


def root() -> Path:
    return Path(config.MARKETBEAST_ROOT or "").expanduser()


def ready() -> dict[str, Any]:
    r = root()
    scanner = r / "scanner.py"
    return {
        "ok": scanner.is_file(),
        "root": str(r),
        "scanner": str(scanner) if scanner.is_file() else None,
    }


def _load_scanner():
    info = ready()
    if not info["ok"]:
        raise FileNotFoundError(f"MarketBeast scanner.py not found at {info['root']}")
    path = str(root())
    if path not in sys.path:
        sys.path.insert(0, path)
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


def best_calls(*, top: int = 8, universe: str = "liquid", dte: int = 7) -> dict[str, Any]:
    """Call the owner's scanner. universe=liquid is up-to-the-minute; full is the 250-name MarketBeast pass."""
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
        picks = [_pick(r) for r in rows if r.get("option_type") == "CALL"]
    else:
        picks = []
        for symbol in _liquid_symbols():
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
                    "combined_score": float(analysis.get("score") or 0) * 0.6
                    + float(best.get("score") or 0) / 100 * 0.4,
                }
            )
            picks.append(_pick(analysis))
        picks.sort(key=lambda x: float(x.get("combined_score") or 0), reverse=True)
        picks = picks[:top]
    _cache.update(at=now, key=key, picks=picks)
    return {
        "ok": True,
        "cached": False,
        "universe": uni,
        "disclaimer": "Signals only. Not advice. Live IBKR fills need TWS + confirm token.",
        "picks": picks,
        **ready(),
    }
