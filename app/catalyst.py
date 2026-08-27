"""News that moves a stock, and how long the move lasts.

A catalyst is the reason to buy a short-dated option rather than a long one. If a
company reports Thursday, an expiry that covers Thursday is the trade and anything
further out is paying for time you do not need. The whole point of a 7-day contract is
that something is going to happen inside seven days.

So this does three things: work out WHAT kind of news it is, work out WHEN the move
should happen, and - the part that decides whether the trade makes money - work out
whether the move persists long enough to sell into.

One trap dominates all of this and it is built in as a hard warning rather than a note.

    Buying premium into a SCHEDULED event and holding through it is one of the most
    reliable ways to be right about direction and still lose money.

Implied volatility is bid up ahead of a known event because nobody knows the outcome.
The moment it is announced the uncertainty is gone and IV collapses - often 30-50% on
an earnings print. A call bought the day before can be worth less the morning after
even when the stock gaps UP, because the volatility you paid for evaporated. This is
not an edge case. It is the default outcome, and it is why "the news was good and I
still lost" is the most common story in retail options.

Unscheduled news is the opposite: IV has not been bid up because nobody saw it coming,
so a surprise headline is the one case where buying premium into news is clean.
"""

from __future__ import annotations

import re
from typing import Any

# --- what kind of news, and what it implies about timing ----------------------
#
# horizon_days: when the move is expected to happen.
# persistence:  how long it tends to last, which decides whether there is anything to
#               sell into or whether it is a one-day gap that fades.
# scheduled:    is the date known in advance? If yes, IV is already bid up.
KINDS: dict[str, dict[str, Any]] = {
    "earnings_upcoming": {
        "horizon_days": 3,
        "persistence": "one to three sessions, then it fades into the next quarter",
        "scheduled": True,
        "why": "A dated print. The move happens on one specific morning.",
    },
    "earnings_result": {
        "horizon_days": 10,
        "persistence": "post-earnings drift runs for weeks in the direction of the surprise",
        "scheduled": False,
        "why": (
            "Already reported, so the volatility premium has been paid out. Drift after a "
            "surprise is one of the few effects that survives serious study."
        ),
    },
    "guidance": {
        "horizon_days": 10,
        "persistence": "weeks - it changes the forward numbers, not just one quarter",
        "scheduled": False,
        "why": "Raised or cut guidance re-rates the whole forward curve, not one print.",
    },
    "mna": {
        "horizon_days": 1,
        "persistence": "permanent step, then dead money at the deal price",
        "scheduled": False,
        "why": (
            "A bid re-prices the target instantly and then it stops moving. Options bought "
            "after the announcement are usually already too late."
        ),
    },
    "regulatory": {
        "horizon_days": 5,
        "persistence": "days to weeks depending on how material the approval is",
        "scheduled": False,
        "why": "Approvals and rejections are binary and large, especially in pharma.",
    },
    "product": {
        "horizon_days": 7,
        "persistence": "days - enthusiasm fades unless numbers follow",
        "scheduled": False,
        "why": "A launch moves sentiment quickly and revenue slowly.",
    },
    "legal": {
        "horizon_days": 5,
        "persistence": "days, unless the sum is material to earnings",
        "scheduled": False,
        "why": "Fines and settlements matter in proportion to the number.",
    },
    "macro_scheduled": {
        "horizon_days": 3,
        "persistence": "one to two sessions across the whole index",
        "scheduled": True,
        "why": "Fed, CPI and payrolls are dated, index-wide, and priced in advance.",
    },
    "geopolitical": {
        "horizon_days": 21,
        "persistence": "weeks to months - regimes, not events",
        "scheduled": False,
        "why": (
            "War, sanctions and supply disruption are conditions rather than moments. They "
            "move sectors - energy, defence, shipping - and they persist, which argues for "
            "MORE time rather than less."
        ),
    },
    "supply_chain": {
        "horizon_days": 14,
        "persistence": "weeks - it works through order books slowly",
        "scheduled": False,
        "why": "Shortages and disruptions show up in results a quarter later.",
    },
    "analyst": {
        "horizon_days": 2,
        "persistence": "a session or two at most",
        "scheduled": False,
        "why": "An upgrade is someone's opinion. It moves price briefly and rarely more.",
    },
}

# Ordered: the first match wins, so the more specific patterns come first.
PATTERNS: list[tuple[str, str]] = [
    ("earnings_upcoming", r"\b(to report|will report|ahead of earnings|earnings (?:on|due|preview|next week)|reports? (?:on )?(?:monday|tuesday|wednesday|thursday|friday))\b"),
    ("earnings_result", r"\b(beats?|misses?|topped|fell short|reported (?:q[1-4]|quarterly|earnings)|earnings (?:beat|miss)|profit (?:rose|fell|jumped|slumped))\b"),
    ("guidance", r"\b(raises? (?:its )?(?:full[- ]year |fy)?(?:guidance|outlook|forecast)|cuts? (?:its )?(?:guidance|outlook|forecast)|lowers? (?:guidance|outlook)|guides? (?:higher|lower)|upgrades? (?:its )?outlook)\b"),
    ("mna", r"\b(acquires?|acquisition|to buy|takeover|merger|buyout|bid for|agrees? to purchase|stake in)\b"),
    ("regulatory", r"\b(fda|approval|approved|rejects?|rejected|clearance|antitrust|regulator|probe|investigation|sanctions? on)\b"),
    ("macro_scheduled", r"\b(federal reserve|fed (?:meeting|decision|chair)|fomc|cpi|inflation data|jobs report|payrolls|rate (?:decision|cut|hike)|ecb|bank of japan)\b"),
    ("geopolitical", r"\b(war|invasion|strikes?|ceasefire|conflict|missile|blockade|opec|embargo|tariffs?|trade war|troops)\b"),
    ("supply_chain", r"\b(shortage|supply chain|production halt|factory|shipping|freight|chip supply|bottleneck|export controls?)\b"),
    ("product", r"\b(launch(?:es|ed)?|unveil(?:s|ed)?|announces? (?:new|the)|releases? (?:new|its)|debuts?|introduces?)\b"),
    ("legal", r"\b(lawsuit|sues?|settlement|fined?|court|ruling|verdict|class action)\b"),
    ("analyst", r"\b(upgrade[sd]?|downgrade[sd]?|price target|initiat(?:es|ed) coverage|overweight|underweight|buy rating)\b"),
]

BULLISH = re.compile(
    r"\b(beat|beats|tops|topped|surge[sd]?|soar[sd]?|jump[sd]?|rally|rallies|rose|gains?|record|"
    r"raise[sd]?|upgrade[sd]?|approval|approved|wins?|strong|boom|breakthrough|expand[sd]?)\b", re.I)
BEARISH = re.compile(
    r"\b(miss(?:es|ed)?|plunge[sd]?|slump[sd]?|tumble[sd]?|fell|falls?|drops?|cuts?|downgrade[sd]?|"
    r"reject(?:s|ed)?|probe|lawsuit|fined?|weak|warn(?:s|ed|ing)?|halt(?:s|ed)?|recall)\b", re.I)


def classify(headline: str) -> dict[str, Any]:
    """What kind of news is this, and what does it imply about timing?"""
    text = (headline or "").strip()
    if not text:
        return {"error": "empty headline"}

    kind = None
    for name, pattern in PATTERNS:
        if re.search(pattern, text, re.I):
            kind = name
            break
    if not kind:
        return {
            "ok": True,
            "headline": text[:200],
            "kind": None,
            "tradeable": False,
            "why": "No recognisable catalyst. Most headlines are not tradeable events.",
        }

    spec = KINDS[kind]
    bull = len(BULLISH.findall(text))
    bear = len(BEARISH.findall(text))
    direction = "bullish" if bull > bear else "bearish" if bear > bull else "unclear"

    return {
        "ok": True,
        "headline": text[:200],
        "kind": kind,
        "direction": direction,
        "horizon_days": spec["horizon_days"],
        "persistence": spec["persistence"],
        "scheduled": spec["scheduled"],
        "why": spec["why"],
        "tradeable": direction != "unclear",
        "confidence": "high" if abs(bull - bear) >= 2 else "low" if direction == "unclear" else "medium",
    }


def iv_crush_warning(kind: str | None) -> dict[str, Any] | None:
    """The warning that matters more than any signal this module produces.

    A scheduled event has its uncertainty priced in beforehand. When the event happens
    the uncertainty disappears and the premium with it - which is why the stock can gap
    your way and the option still loses.
    """
    if not kind or not KINDS.get(kind, {}).get("scheduled"):
        return None
    return {
        "severe": True,
        "what": "Implied volatility collapse after a scheduled event.",
        "why": (
            "The date is known, so IV is already bid up. The moment the result is out the "
            "uncertainty is resolved and the premium deflates - commonly 30-50% on an earnings "
            "print. A long option can be worth LESS the morning after even if the stock gapped "
            "in your favour, because you paid for volatility that no longer exists."
        ),
        "what_to_do": [
            "Buy the move BEFORE the event and sell into the run-up, not through the print.",
            "Or wait until after the announcement, when the premium has already deflated and "
            "post-event drift is still ahead of you.",
            "Or use a spread, where the short leg is sold at the same inflated volatility you "
            "are buying - which is what makes the crush cancel out.",
        ],
        "never": "Do not buy a naked long option the day before a scheduled print and hold through it.",
    }


def reaction_history(bars: list[dict], *, threshold_pct: float = 4.0, follow: int = 5) -> dict[str, Any]:
    """Does news actually move this name, and does the move stick?

    Finds historical shock days - a gap or range far outside the ordinary - and measures
    what happened over the following sessions. This is the empirical half: a catalyst is
    only worth a short-dated option if this name's shocks PERSIST. Some stocks gap and
    keep going; some gap and fill it by Wednesday, and on those a 7-day contract is a
    losing trade even when the news is real.
    """
    rows = [b for b in bars if b.get("close") and b.get("open")]
    if len(rows) < 120:
        return {"error": f"Only {len(rows)} bars; need 120+ to find shock days."}

    gaps = []
    for i in range(1, len(rows)):
        prev_c, o = rows[i - 1]["close"], rows[i]["open"]
        if prev_c > 0:
            gaps.append(abs(o - prev_c) / prev_c * 100)
    if not gaps:
        return {"error": "No usable gaps."}

    typical = sorted(gaps)[len(gaps) // 2]
    shocks = []
    for i in range(1, len(rows) - follow):
        prev_c, o, c = rows[i - 1]["close"], rows[i]["open"], rows[i]["close"]
        if prev_c <= 0:
            continue
        gap = (o - prev_c) / prev_c * 100
        if abs(gap) < max(threshold_pct, typical * 3):
            continue
        day_move = (c - prev_c) / prev_c * 100
        after = (rows[i + follow]["close"] - c) / c * 100
        shocks.append({
            "date": rows[i].get("date"),
            "gap_pct": round(gap, 2),
            "day_pct": round(day_move, 2),
            "next_days_pct": round(after, 2),
            "continued": (after > 0) == (gap > 0),
        })

    if not shocks:
        return {
            "ok": True,
            "shocks": 0,
            "verdict": (
                f"No shock days above {max(threshold_pct, typical * 3):.1f}% in this history. "
                "This name does not gap on news, which argues against buying short-dated options "
                "for a catalyst that may not move it."
            ),
        }

    continued = sum(1 for s in shocks if s["continued"])
    follow_through = continued / len(shocks)
    avg_gap = sum(abs(s["gap_pct"]) for s in shocks) / len(shocks)
    avg_after = sum(s["next_days_pct"] for s in shocks if s["gap_pct"] > 0) / max(
        1, sum(1 for s in shocks if s["gap_pct"] > 0))

    return {
        "ok": True,
        "shocks": len(shocks),
        "typical_gap_pct": round(typical, 2),
        "avg_shock_gap_pct": round(avg_gap, 2),
        "follow_through_rate": round(follow_through, 3),
        "avg_move_after_up_gap_pct": round(avg_after, 2),
        "follow_days": follow,
        "examples": shocks[-5:],
        "verdict": (
            f"Shocks continue in the same direction {follow_through * 100:.0f}% of the time over "
            f"the next {follow} sessions. There is something to sell into."
            if follow_through > 0.55
            else f"Shocks continue only {follow_through * 100:.0f}% of the time - this name gaps and "
            f"then fades. A short-dated option bought on the news is fighting that."
        ),
        "caveat": (
            f"Shock days are inferred from gaps above {max(threshold_pct, typical * 3):.1f}%, not "
            "from an event calendar. Some are news, some are the whole market moving."
        ),
    }


def horizon(headline: str, bars: list[dict] | None = None) -> dict[str, Any]:
    """Headline in, suggested expiry window out - with the reasons and the warnings."""
    read = classify(headline)
    if not read.get("ok") or not read.get("kind"):
        return read

    days = read["horizon_days"]
    # Cover the event and a few sessions past it. An expiry that lands ON the event date
    # gives the move no room to be a day late, which they routinely are.
    suggested = [max(7, days + 3), max(14, days + 14)]
    crush = iv_crush_warning(read["kind"])

    history = None
    if bars:
        history = reaction_history(bars)
        if history.get("ok") and history.get("shocks") and history.get("follow_through_rate", 1) < 0.5:
            suggested = [max(7, days), max(10, days + 5)]

    return {
        **read,
        "suggested_dte": suggested,
        "reasoning": (
            f"{read['why']} Expect the move within about {days} days; {read['persistence']}. "
            f"An expiry {suggested[0]}-{suggested[1]} days out covers the event with room for it "
            "to be late, without paying for months you do not need."
        ),
        "iv_crush": crush,
        "history": history,
        "note": (
            "Persistence is what decides whether a short-dated option works. A stock that gaps "
            "and fades gives you nothing to sell into no matter how right the news was."
        ),
    }


def scan(*, limit: int = 40, symbols: list[str] | None = None) -> dict[str, Any]:
    """Sweep the wires and return what looks like a tradeable catalyst."""
    from . import feeds, intel

    snap = feeds.snapshot()
    items = snap.get("news") or []
    found = []
    for item in items[:limit * 3]:
        title = item.get("title") or ""
        read = classify(title)
        if not read.get("ok") or not read.get("kind") or not read.get("tradeable"):
            continue
        tickers = intel._tickers_in(title)
        if symbols:
            tickers = [t for t in tickers if t in symbols]
            if not tickers:
                continue
        found.append({
            "headline": title[:180],
            "source": item.get("source"),
            "published": item.get("published"),
            "link": item.get("link"),
            "kind": read["kind"],
            "direction": read["direction"],
            "confidence": read["confidence"],
            "horizon_days": read["horizon_days"],
            "scheduled": read["scheduled"],
            "tickers": tickers,
            "iv_crush_risk": bool(read["scheduled"]),
        })
        if len(found) >= limit:
            break

    named = [f for f in found if f["tickers"]]
    return {
        "ok": True,
        "scanned": len(items),
        "catalysts": found,
        "with_tickers": named,
        "count": len(found),
        "sources": len(feeds.NEWS_FEEDS),
        "note": (
            "Headline pattern matching, not an event calendar - it finds what the wires are "
            "saying, not what is scheduled. Anything marked scheduled=true carries IV crush risk "
            "and should not be bought as a naked long through the event."
            if found else "Nothing on the wires that reads as a tradeable catalyst right now."
        ),
    }


def dispatch(action: str = "scan", **kwargs: Any) -> Any:
    act = (action or "scan").lower()
    if act in {"scan", "wires", "news"}:
        syms = kwargs.get("symbols")
        if isinstance(syms, str):
            syms = [s.strip().upper() for s in syms.split(",") if s.strip()]
        return scan(limit=int(kwargs.get("limit") or 40), symbols=syms)
    if act in {"classify", "read"}:
        return classify(str(kwargs.get("headline") or ""))
    if act in {"horizon", "dte", "expiry"}:
        bars = None
        symbol = str(kwargs.get("symbol") or "")
        if symbol:
            from . import markets

            hist = markets.history(symbol, str(kwargs.get("range") or "3y"))
            bars = [b for b in (hist.get("bars") or []) if b.get("close")]
        return horizon(str(kwargs.get("headline") or ""), bars)
    if act in {"reaction", "history", "shocks"}:
        from . import markets

        hist = markets.history(str(kwargs.get("symbol") or ""), str(kwargs.get("range") or "3y"))
        if hist.get("error"):
            return hist
        return reaction_history([b for b in (hist.get("bars") or []) if b.get("close")])
    return {"error": f"unknown catalyst action {act}",
            "actions": ["scan", "classify", "horizon", "reaction"]}
