"""Internal MarketBeast desk. v9 engine + Super Jarvis quality layer.

v10 correction: this module was choosing and grading contracts without calling this
repo's own greeks.py or probability.py, and without cross-checking picks against
catalyst.py's news feed. All three already existed and worked - they just weren't wired
in here, which is exactly the gap greeks.py's own docstring calls out ("place_option()
and marketbeast pick contracts and send orders without computing a single greek").
Concretely, that meant:

  - gamma, theta, vega were never computed or shown - only whatever raw "delta" the
    vendored scanner happened to report.
  - the probability shown was the vendored scanner's itm_prob (or delta used as a
    stand-in), both of which probability.py's docstring shows overstate the real odds
    of the trade paying off by roughly half again. p_profit (breakeven-adjusted) is the
    number that is actually about the money.
  - a pick could be graded A the day before an earnings print with the position held
    straight through an IV crush, because nothing checked the news wire at all.

This version computes real greeks and p_profit per contract (falling back to the
vendored fields only when there isn't enough data to solve for IV), and cross-checks
the final picks against catalyst.py so a scheduled event landing inside the contract's
life gets flagged and downgraded rather than silently graded on greeks alone. Nothing
about the IBKR live-quote overlay, order placement, or paper-trading path changed -
this only touches how a contract is scored before it ever gets that far.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from . import config, greeks, obsidian, probability

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


def _real_metrics(
    *, spot: float, strike: float, dte: float, right: str, premium: float | None, iv_hint: float | None
) -> dict[str, Any]:
    """Full delta/gamma/theta/vega plus the breakeven-adjusted probability of profit,
    computed from this repo's own greeks.py / probability.py rather than trusting
    whatever the vendored scanner happened to populate.

    Prefers a real IV when the chain provided one; otherwise solves for it from the
    quoted premium (the same Newton-then-bisection routine greeks.implied_vol already
    uses everywhere else in this codebase). Returns {} rather than raising if there
    isn't enough data to solve either way - a contract with a missing IV and no premium
    still gets picked, it just won't carry gamma/theta/vega for that one row.
    """
    if not (spot and strike and dte and dte > 0):
        return {}
    days = float(dte)
    sigma = float(iv_hint) if iv_hint else None
    out: dict[str, Any] = {}

    g = None
    if sigma and sigma > 0:
        g = greeks.greeks(spot, strike, days / 365.0, sigma=sigma, right=right)
    elif premium:
        solved = greeks.implied_vol(float(premium), spot, strike, days / 365.0, right=right)
        if solved.get("ok"):
            sigma = solved["iv"]
            g = greeks.greeks(spot, strike, days / 365.0, sigma=sigma, right=right)

    if g and g.get("ok"):
        out.update(
            {"gamma": g["gamma"], "theta": g["theta"], "vega": g["vega"], "delta_bs": g["delta"], "iv_used": sigma}
        )

    if sigma and premium:
        pp = probability.p_profit(spot, strike, days / 365.0, sigma, float(premium), right=right)
        if pp.get("ok"):
            out.update({"p_profit": pp["p_profit"], "p_itm": pp["p_itm"], "breakeven_pop": pp["breakeven"]})
    elif sigma:
        pi = probability.p_itm(spot, strike, days / 365.0, sigma, right=right)
        if pi.get("ok"):
            out["p_itm"] = pi["p_itm"]

    return out


def grade(pick: dict[str, Any]) -> str:
    """A = liquid + sane delta + odds and decay that actually hold up. WATCH = junk,
    too wide, bleeding too fast in theta, or a real probability of profit too low -
    whichever of those this pick has data for.
    """
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

    # Theta: how much of the premium bleeds away per day regardless of direction.
    theta, mid = pick.get("theta"), _num(pick.get("option_price"))
    if theta is not None and mid:
        if abs(_num(theta)) / mid > 0.05:
            score -= 1

    # p_profit is the breakeven-adjusted probability of profit - always <= delta and
    # itm_prob, per probability.py. Grading on it directly (when it's available) closes
    # the exact gap that module's docstring warns about.
    p_profit = pick.get("p_profit")
    if p_profit is not None:
        if p_profit >= 0.45:
            score += 1
        elif p_profit < 0.25:
            score -= 1

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
        "delta_bs": row.get("delta_bs"),
        "gamma": row.get("gamma"),
        "theta": row.get("theta"),
        "vega": row.get("vega"),
        "itm_prob": row.get("itm_prob"),
        # p_itm/p_profit come from probability.py when there was enough data to solve
        # for IV; fall back to the vendored itm_prob so a row is never worse off than
        # before this change, just less precise.
        "p_itm": row.get("p_itm") if row.get("p_itm") is not None else row.get("itm_prob"),
        "p_profit": row.get("p_profit"),
        "iv_used": row.get("iv_used"),
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
        # A put breaks even BELOW the strike. Adding the debit for both sides quietly
        # reported every put's breakeven on the wrong side of the strike.
        "breakeven": (
            round(strike - debit, 2)
            if strike and debit and str(row.get("option_type") or "CALL").upper().startswith("P")
            else round(strike + debit, 2) if strike and debit else None
        ),
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
    return out


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


def broad_screen(*, max_symbols: int | None = None, shortlist: int = 40,
                  batch_size: int = 200, range_: str = "6mo") -> dict[str, Any]:
    """Cheap first pass over the REAL full-market universe (thousands of tickers,
    from universe.full() - not the vendored scanner's 273-symbol list), scored on
    plain technical setups, to produce a shortlist worth the expensive per-symbol
    options-chain analysis the vendored scanner does.

    This is the actual answer to "scan thousands of stocks": nothing does a full
    options-chain pull on thousands of names every cycle - that is what pushed the
    universe cap to 220 in the first place. What scales is a batched, cached
    technical screen that narrows thousands down to the handful actually worth the
    slow path, the same way a real trading desk's scanner works.
    """
    from . import markets, setups

    uni = universe_mod().full()
    symbols = uni.get("symbols") or []
    cap = max_symbols if max_symbols is not None else config.MARKETBEAST_MAX_UNIVERSE
    if cap:
        symbols = symbols[:cap]

    scored: list[dict[str, Any]] = []
    errors = 0
    for i in range(0, len(symbols), max(1, batch_size)):
        chunk = symbols[i : i + batch_size]
        fetched = markets.history_batch(chunk, range_)
        for sym, hist in fetched.items():
            if hist.get("error"):
                errors += 1
                continue
            bars = [b for b in (hist.get("bars") or []) if b.get("close") is not None]
            ctx = setups.context_from_bars(bars, sym)
            if not ctx.get("ok"):
                continue
            found = setups.detect(ctx).get("found") or []
            if not found:
                continue
            # Rank by how many setups fired and how confident the strongest one is,
            # not by anything options-related - that filter comes later, only for
            # names that clear this bar.
            weight = {"high": 3, "medium": 2, "low": 1}
            score = sum(weight.get(f.get("confidence"), 1) for f in found)
            scored.append({
                "symbol": sym,
                "score": score,
                "setups": [f["setup"] for f in found],
                "last": ctx["closes"][-1],
                "rsi14": (ctx["stats"] or {}).get("rsi14"),
                "trend": (ctx["stats"] or {}).get("trend"),
            })

    scored.sort(key=lambda r: r["score"], reverse=True)
    return {
        "ok": True,
        "universe_source": uni.get("source"),
        "universe_size": uni.get("count"),
        "scanned": len(symbols),
        "errors": errors,
        "candidates": len(scored),
        "shortlist": scored[:shortlist],
    }


def universe_mod():
    """Indirection point so tests can monkeypatch the universe source cleanly."""
    from . import universe

    return universe


def _analyze_one(scanner, symbol: str, dte: int, *, allow_puts: bool = True) -> dict | None:
    """One symbol, one side, chosen by the scanner's own read of direction.

    This used to drop every bearish symbol on the floor and only ever look at
    preferred_calls - while the scanner underneath had been scoring both directions and
    populating preferred_puts the whole time. Half the signal was computed and discarded
    before anything downstream could see it. A bearish read now buys a put instead of
    producing nothing.
    """
    df = scanner.fetch_data(symbol)
    if df is None or len(df) < 20:
        return None
    try:
        analysis = scanner.analyze(symbol, df)
    except Exception:
        return None

    direction = (analysis.get("direction") or "").upper()
    if direction == "BEARISH":
        if not allow_puts:
            return None
        side, key = "PUT", "preferred_puts"
    elif direction in {"BULLISH", "NEUTRAL"}:
        side, key = "CALL", "preferred_calls"
    else:
        return None

    opts = scanner.get_options_data(symbol, target_dte=dte)
    if not opts or not opts.get(key):
        return None
    best = opts[key][0]
    analysis.update(
        {
            "option_type": side,
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
    analysis.update(
        _real_metrics(
            spot=_num(analysis.get("price")),
            strike=_num(best.get("strike")),
            dte=_num(opts.get("dte")),
            right="P" if side == "PUT" else "C",
            premium=best.get("price"),
            iv_hint=best.get("iv") or opts.get("iv"),
        )
    )
    return enrich(analysis, best)


def _score_calls(scanner, symbols: list[str], *, dte: int, top: int, allow_puts: bool = True) -> list[dict]:
    picks: list[dict] = []
    workers = min(8, max(2, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(_analyze_one, scanner, symbol, dte, allow_puts=allow_puts): symbol
            for symbol in symbols
        }
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

        if ibkr.busy() or not ibkr.port_open(ibkr.port()):
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


def _attach_catalysts(picks: list[dict], dte: int) -> list[dict]:
    """Cross today's picks against the news wire (catalyst.py) so a pick riding into a
    scheduled-event IV crush gets flagged instead of silently graded A on greeks alone.

    catalyst.py's own warning is the reason this exists: buying premium into a known
    event and holding through it is one of the most reliable ways to be right about
    direction and still lose money, because the IV that was bid up ahead of the event
    deflates the moment it happens. If the wire shows a scheduled catalyst landing
    inside this contract's DTE window, that's exactly the setup - so it gets downgraded
    to WATCH rather than left looking like a clean A/B pick.

    Fails safe: any error talking to the news feed (offline, feed down, parsing issue)
    leaves picks untouched rather than blocking the scan.
    """
    if not picks:
        return picks
    try:
        from . import catalyst

        symbols = sorted({p.get("symbol") for p in picks if p.get("symbol")})
        found = catalyst.scan(limit=80, symbols=symbols)
        by_symbol: dict[str, dict] = {}
        for item in found.get("with_tickers") or []:
            for t in item.get("tickers") or []:
                by_symbol.setdefault(t, item)
    except Exception:
        return picks

    for p in picks:
        hit = by_symbol.get(p.get("symbol"))
        if not hit:
            continue
        p["catalyst"] = {
            "headline": hit.get("headline"),
            "kind": hit.get("kind"),
            "direction": hit.get("direction"),
            "scheduled": hit.get("scheduled"),
            "horizon_days": hit.get("horizon_days"),
        }
        contract_dte = _num(p.get("dte"), float(dte))
        horizon_days = hit.get("horizon_days")
        if hit.get("scheduled") and horizon_days is not None and horizon_days <= contract_dte:
            p["iv_crush_risk"] = True
            p["grade"] = "WATCH"
            p["buyable"] = False

    picks.sort(key=lambda x: (x.get("buyable"), _num(x.get("combined_score"))), reverse=True)
    return picks


def _write_vault(picks: list[dict], universe: str) -> str | None:
    if not picks:
        return None
    day = date.today().isoformat()
    lines = [
        f"---\ntype: options\ndate: {day}\nuniverse: {universe}\nlayer: super-5.6\n---\n",
        f"# MarketBeast picks {day} ({universe})\n",
        "Grade A/B = liquid enough to ticket. C/WATCH = look only.\n",
    ]
    for p in picks:
        flag = "BUYABLE" if p.get("buyable") else "WATCH"
        crush = f" ⚠ IV-crush risk: {p['catalyst']['headline']}" if p.get("iv_crush_risk") and p.get("catalyst") else ""
        lines.append(
            f"- [{p.get('grade')}/{flag}] {p.get('symbol')} {p.get('expiration')} "
            f"{p.get('strike')}{'P' if (p.get('option_type') or 'CALL').upper().startswith('P') else 'C'} "
            f"@ {p.get('option_price')} "
            f"spread={p.get('spread')} Δ{p.get('delta')} Θ{p.get('theta')} Γ{p.get('gamma')} "
            f"p_profit={p.get('p_profit')} "
            f"max_loss={p.get('max_loss')} be={p.get('breakeven')} via {p.get('quote_source')}{crush}"
        )
    rel = f"Markets/{day}-calls.md"
    try:
        obsidian.write_note(rel, "\n".join(lines) + "\n")
        return rel
    except Exception:
        return None


def best_calls(*, top: int = 8, universe: str = "liquid", dte: int = 7,
               allow_puts: bool = True) -> dict[str, Any]:
    """Best contracts across the universe, either side.

    The name is historical - it returns puts too now, because the scanner was always
    scoring both directions and the wrapper was discarding half of them. allow_puts=False
    restores the old calls-only behaviour for a strictly long book.
    """
    top = max(3, min(int(top or 8), 20))
    dte = max(2, min(int(dte or 7), 45))
    uni = (universe or "liquid").lower()
    # v71: cache key bumped so picks cached under the old (pre-greeks/probability/
    # catalyst) scoring are never served after this change - they're missing fields a
    # client may now expect.
    key = f"{uni}:{top}:{dte}:{allow_puts}:v71"
    now = time.time()
    if _cache["picks"] and _cache["key"] == key and now - float(_cache["at"] or 0) < 90:
        return {"ok": True, "cached": True, "universe": uni, "picks": _cache["picks"][:top], **ready()}
    sc = _load_scanner()
    scanner = sc.StockScanner()
    screen = None
    if uni == "liquid":
        symbols = _liquid_symbols()
    elif uni in {"market", "thousands", "everything"}:
        # The real full-market universe (thousands of tickers via universe.py), cheaply
        # screened first (broad_screen) so only names that already show a live setup
        # go through the expensive per-symbol options-chain analysis below. Scanning
        # thousands of names through the options path directly is not a cap that can
        # just be raised - see broad_screen's docstring.
        screen = broad_screen(range_="6mo")
        symbols = [c["symbol"] for c in screen.get("shortlist") or []] or _liquid_symbols()
    else:
        symbols = list(_sector_symbols(sc, uni) or _liquid_symbols())
        if uni == "full":
            pass  # 273 vendored symbols, uncapped - see universe="market" for real scale
    picks = _score_calls(scanner, symbols, dte=dte, top=max(top, 10), allow_puts=allow_puts)
    picks = _overlay_ibkr(picks)
    picks = _attach_catalysts(picks, dte)[:top]
    _cache.update(at=now, key=key, picks=picks)
    note = _write_vault(picks, uni)
    buyable = [p for p in picks if p.get("buyable")]
    return {
        "ok": True,
        "cached": False,
        "universe": uni,
        "scanned": len(symbols),
        "broad_screen": {"universe_size": screen.get("universe_size"), "source": screen.get("universe_source"),
                          "screened": screen.get("scanned"), "candidates": screen.get("candidates")} if screen else None,
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
    calls = []
    for c in raw:
        row = {**analysis, "option_type": "CALL", "expiration": opts.get("expiration"), "dte": opts.get("dte"),
               "option_price": c.get("price"), **c}
        row.update(
            _real_metrics(
                spot=_num(analysis.get("price")),
                strike=_num(c.get("strike")),
                dte=_num(opts.get("dte")),
                right="C",
                premium=c.get("price"),
                iv_hint=c.get("iv") or opts.get("iv"),
            )
        )
        calls.append(enrich(row, c))
    calls = _overlay_ibkr(calls)
    calls = _attach_catalysts(calls, dte)
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
