"""Polymarket public desk — Gamma API only. One book. No extra accounts. No wallet keys."""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import obsidian

GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "SuperJarvis/6.0 (+https://github.com/rkenagy-ops/jarvis-system)", "Accept": "application/json"}


def kelly(p: float, price: float, *, fraction: float = 0.25, cap: float = 0.10) -> dict[str, Any]:
    """Quarter-Kelly on a binary YES share priced in [0,1]. Cap 10% of bankroll."""
    try:
        p = float(p)
        price = float(price)
    except (TypeError, ValueError):
        return {"f": 0.0, "edge": None, "reason": "bad inputs"}
    if price <= 0.02 or price >= 0.98 or p <= 0 or p >= 1:
        return {"f": 0.0, "edge": round(p - price, 4) if 0 < price < 1 else None, "reason": "no bet — extreme or invalid price"}
    b = (1.0 - price) / price
    f_star = p - (1.0 - p) / b
    f = max(0.0, min(cap, f_star * fraction))
    return {
        "edge": round(p - price, 4),
        "odds": round(b, 4),
        "kelly_full": round(f_star, 4),
        "kelly_frac": round(f, 4),
        "fraction": fraction,
        "f": round(f, 4),
        "reason": "positive edge" if f > 0 else "no edge — stand down",
    }


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _parse(row: dict) -> dict[str, Any] | None:
    question = (row.get("question") or row.get("title") or row.get("slug") or "").strip()
    if not question:
        return None
    prices = _loads(row.get("outcomePrices") or [])
    outcomes = _loads(row.get("outcomes") or ["Yes", "No"])
    if not isinstance(prices, list):
        prices = []
    yes = None
    try:
        yes = float(prices[0]) if prices else None
    except (TypeError, ValueError, IndexError):
        yes = None
    vol = 0.0
    for key in ("volume24hr", "volume", "volumeNum"):
        try:
            vol = float(row.get(key) or 0)
            if vol:
                break
        except (TypeError, ValueError):
            continue
    liq = 0.0
    try:
        liq = float(row.get("liquidity") or row.get("liquidityNum") or 0)
    except (TypeError, ValueError):
        liq = 0.0
    return {
        "id": row.get("id") or row.get("conditionId"),
        "question": question[:220],
        "slug": row.get("slug"),
        "url": f"https://polymarket.com/event/{row.get('slug')}" if row.get("slug") else "https://polymarket.com",
        "outcomes": outcomes if isinstance(outcomes, list) else ["Yes", "No"],
        "yes": yes,
        "implied": round(yes, 4) if yes is not None else None,
        "volume_24h": round(vol, 2),
        "liquidity": round(liq, 2),
        "closed": bool(row.get("closed")),
        "source": "polymarket-gamma",
    }


def _get(path: str, params: dict | None = None) -> Any:
    with httpx.Client(timeout=12.0, headers=UA, follow_redirects=True) as client:
        resp = client.get(f"{GAMMA}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


def scan(*, query: str = "", limit: int = 12) -> dict[str, Any]:
    """Hottest active markets. Public Gamma — no wallet."""
    limit = max(4, min(int(limit or 12), 24))
    rows: list[dict] = []
    q = (query or "").strip()
    try:
        if q:
            data = _get("/public-search", {"q": q})
            if isinstance(data, dict):
                rows = list(data.get("markets") or data.get("events") or [])
            elif isinstance(data, list):
                rows = data
        if not rows:
            data = _get(
                "/markets",
                {
                    "closed": "false",
                    "limit": str(limit),
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
            rows = data if isinstance(data, list) else list((data or {}).get("markets") or [])
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "markets": [], "hint": "Gamma API public read failed."}
    markets = []
    seen = set()
    needle = q.lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _parse(row)
        if not parsed or parsed["id"] in seen:
            continue
        if needle and needle not in (parsed["question"] + " " + str(parsed.get("slug") or "")).lower():
            continue
        seen.add(parsed["id"])
        markets.append(parsed)
        if len(markets) >= limit:
            break
    markets.sort(key=lambda m: float(m.get("volume_24h") or 0), reverse=True)
    return {
        "ok": True,
        "count": len(markets),
        "query": q,
        "markets": markets,
        "note": "Public odds only. Jarvis will not open extra Polymarket accounts or hold wallet keys.",
    }


def bounce(*, query: str = "", limit: int = 8, bankroll: float = 1000.0) -> dict[str, Any]:
    """Rotate attention across hot books. One account. Paper Kelly. No live CLOB from Jarvis."""
    raw = scan(query=query, limit=max(limit, 12))
    if not raw.get("ok"):
        return raw
    ideas = []
    for m in raw.get("markets") or []:
        yes = m.get("yes")
        if yes is None:
            continue
        # Without a proprietary model, fair ≈ market. Flag only fat books / extremes for human review.
        # Slight mean-reversion prior: fade 0.85+ and 0.15- unless volume is thin.
        if yes >= 0.88:
            p_hat = min(0.97, yes - 0.03)
            side = "NO / fade favorite"
        elif yes <= 0.12:
            p_hat = max(0.03, yes + 0.03)
            side = "YES / fade longshot"
        else:
            p_hat = yes
            side = "WATCH — market is the fair"
        k = kelly(p_hat, yes if side.startswith("YES") else (1 - yes if side.startswith("NO") else yes))
        if side.startswith("WATCH"):
            k = {"f": 0.0, "edge": 0.0, "reason": "no model edge — do not force a bet"}
        dollar = round(float(bankroll) * float(k.get("f") or 0), 2)
        ideas.append(
            {
                **m,
                "side": side,
                "p_hat": round(p_hat, 4),
                "kelly": k,
                "paper_usd": dollar,
                "enter": bool(k.get("f") and k["f"] > 0 and dollar >= 5),
                "verdict": "PAPER" if (k.get("f") or 0) > 0 else "NO-GO",
            }
        )
    ideas.sort(key=lambda r: (r.get("enter"), r.get("volume_24h") or 0), reverse=True)
    enters = [i for i in ideas if i.get("enter")]
    spoken = (
        f"Polymarket: {len(enters)} paper edges on the board. Do not open extra accounts."
        if enters
        else "Polymarket: no-go. No model edge — watch the tape, one book only."
    )
    note = None
    try:
        from datetime import date

        lines = [
            f"---\ntype: polymarket\ndate: {date.today().isoformat()}\n---\n",
            f"# Polymarket bounce {date.today().isoformat()}\n",
            "One account. Public Gamma. Paper Kelly. No wallet keys in Jarvis.\n",
        ]
        for i in ideas[:8]:
            lines.append(
                f"- [{i.get('verdict')}] {i.get('question')} yes={i.get('yes')} "
                f"{i.get('side')} ${i.get('paper_usd')} ({i.get('url')})"
            )
        rel = f"Markets/{date.today().isoformat()}-polymarket.md"
        obsidian.write_note(rel, "\n".join(lines) + "\n")
        note = rel
    except Exception:
        note = None
    return {
        "ok": True,
        "spoken": spoken[:180],
        "verdict": "PAPER" if enters else "NO-GO",
        "enter": bool(enters),
        "ideas": ideas[:limit],
        "vault": note,
        "disclaimer": "Prediction-market research. Live fills belong in official Polymarket with YOUR wallet. Jarvis will not bounce extra accounts or custody keys.",
    }


PRIMER = {
    "price_is_probability": (
        "A YES share settles at $1 if the event happens and $0 if it doesn't. So a price of "
        "0.62 IS the market's 62% probability. You are never betting on the event — you are "
        "betting your probability estimate is better than the crowd's."
    ),
    "edge": (
        "Edge = your probability minus the price. Buy YES at 0.62 only if you genuinely think "
        "it's above 62%. If you can't say why your number differs, you have no edge and the "
        "correct size is zero."
    ),
    "where_edge_comes_from": (
        "Three places, realistically: you know something the market hasn't priced (news, "
        "domain expertise), the market is thin and mispriced by inattention, or there is a "
        "structural bias — longshots are chronically overpriced, heavy favourites underpriced."
    ),
    "kelly": (
        "Kelly gives the bet size that maximises long-run growth: f = p - (1-p)/b, where b is "
        "the payoff odds (1-price)/price. Full Kelly is far too aggressive when your probability "
        "estimate is itself uncertain — and yours always is. This system uses quarter-Kelly and "
        "caps any single position at 10% of bankroll."
    ),
    "when_not_to_bet": (
        "Most of the time. If your estimate is within a couple of points of the price, the edge "
        "is inside your own error bars. Forcing a bet there is how bankrolls bleed out."
    ),
    "costs": (
        "The quoted price is not your fill. Thin books have wide spreads, and crossing the spread "
        "on both entry and exit can eat several points of edge. Check volume before assuming your "
        "size gets filled at the screen price."
    ),
    "resolution_risk": (
        "You are also betting on the resolution wording, not just the real-world outcome. Read the "
        "resolution criteria before sizing — ambiguous sources and disputes are a real loss mode "
        "that has nothing to do with being right."
    ),
}


def explain(topic: str = "") -> dict[str, Any]:
    key = (topic or "").strip().lower()
    if not key:
        return {
            "ok": True,
            "primer": PRIMER,
            "order": [
                "price_is_probability",
                "edge",
                "where_edge_comes_from",
                "kelly",
                "costs",
                "resolution_risk",
                "when_not_to_bet",
            ],
            "next": "poly action=evaluate price=0.62 p=0.70 bankroll=1000 to work a real number.",
        }
    if key not in PRIMER:
        return {"error": f"Unknown topic {key!r}.", "known": sorted(PRIMER)}
    return {"ok": True, "topic": key, "explanation": PRIMER[key]}


def evaluate(*, price: float, p: float, bankroll: float = 1000.0, question: str = "") -> dict[str, Any]:
    """Work a single market end to end using YOUR probability, showing every step.

    bounce() has no model — it says so — and without your own estimate there is no edge to
    size. This is where you supply one and see exactly what it implies.
    """
    try:
        price = float(price)
        p = float(p)
        bankroll = float(bankroll)
    except (TypeError, ValueError):
        return {"error": "price, p and bankroll must be numeric."}
    if not 0 < price < 1:
        return {"error": "price is a YES share in (0,1) — e.g. 0.62 for 62 cents."}
    if not 0 < p < 1:
        return {"error": "p is your probability in (0,1) — e.g. 0.70 for 70%."}
    if bankroll <= 0:
        return {"error": "bankroll must be positive."}

    edge = p - price
    side = "YES" if edge > 0 else "NO"
    # Sizing is always done on the side you would actually take.
    entry_price = price if side == "YES" else 1 - price
    p_side = p if side == "YES" else 1 - p
    k = kelly(p_side, entry_price)

    stake = round(bankroll * float(k.get("f") or 0), 2)
    shares = int(stake / entry_price) if entry_price > 0 and stake > 0 else 0
    thin_edge = abs(edge) < 0.03

    verdict = "NO-GO"
    reason = ""
    if thin_edge:
        reason = (
            f"Your {p:.0%} is only {abs(edge):.1%} from the market's {price:.0%}. That is inside "
            "the error bar on your own estimate — no bet."
        )
    elif not k.get("f"):
        reason = k.get("reason") or "Kelly returned zero."
    elif stake < 5:
        reason = f"Kelly says {stake} — too small to be worth the spread."
    else:
        verdict = "PAPER"
        reason = (
            f"{side} at {entry_price:.2f}, {abs(edge):.1%} edge. Quarter-Kelly sizes this at "
            f"{stake} of a {bankroll:.0f} bankroll."
        )

    return {
        "ok": True,
        "question": question or None,
        "market_price": round(price, 4),
        "market_implied_prob": f"{price:.1%}",
        "your_prob": f"{p:.1%}",
        "edge": round(edge, 4),
        "side": side,
        "entry_price": round(entry_price, 4),
        "kelly": k,
        "stake_usd": stake if verdict == "PAPER" else 0.0,
        "shares": shares if verdict == "PAPER" else 0,
        "max_loss": stake if verdict == "PAPER" else 0.0,
        "payoff_if_right": round(shares * (1 - entry_price), 2) if verdict == "PAPER" else 0.0,
        "verdict": verdict,
        "reasoning": reason,
        "check_before_sizing": [
            "Read the resolution criteria — you are betting on the wording, not just the outcome.",
            "Check 24h volume; a thin book will not fill this at the screen price.",
            "Write down WHY your number differs from the market. If you can't, there is no edge.",
        ],
        "disclaimer": (
            "Paper sizing only. Live fills go through official Polymarket with your own wallet — "
            "Jarvis does not custody keys or open extra accounts."
        ),
    }


def dispatch(action: str = "scan", **kwargs: Any) -> dict[str, Any]:
    act = (action or "scan").lower()
    if act in {"explain", "teach", "primer", "learn"}:
        return explain(str(kwargs.get("topic") or ""))
    if act in {"evaluate", "eval", "size", "edge"}:
        return evaluate(
            price=kwargs.get("price") or 0,
            p=kwargs.get("p") or kwargs.get("prob") or kwargs.get("p_hat") or 0,
            bankroll=float(kwargs.get("bankroll") or 1000.0),
            question=str(kwargs.get("question") or ""),
        )
    if act in {"kelly", "size"}:
        return kelly(float(kwargs.get("p") or kwargs.get("prob") or 0), float(kwargs.get("price") or 0))
    if act in {"bounce", "rotate", "grow"}:
        return bounce(
            query=str(kwargs.get("query") or kwargs.get("q") or kwargs.get("symbol") or ""),
            limit=int(kwargs.get("limit") or kwargs.get("top") or 8),
            bankroll=float(kwargs.get("bankroll") or kwargs.get("qty") or 1000),
        )
    return scan(
        query=str(kwargs.get("query") or kwargs.get("q") or kwargs.get("symbol") or ""),
        limit=int(kwargs.get("limit") or kwargs.get("top") or 12),
    )
