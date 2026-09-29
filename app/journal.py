"""Learn from every trade: post-mortem each closed signal, name the mistake, and feed
what she learns back into how she ranks the next one.

forward_tracker records every setup she calls, the exact levels, and the conditions it
fired under; backtest's engine then closes it honestly against real bars. That is the
raw material. This is the part that turns it into judgment:

  1. review   - each newly closed signal gets a diagnosis. Not every loss is a mistake:
                a well-placed stop getting hit is the cost of doing business. A loss that
                chased an extended move, fought the market, or bought a light-volume
                breakout is a mistake, and gets named as one.
  2. insights - expectancy by setup, by side, and by condition ("light volume",
                "against the market", "candle-confirmed"...). A condition that keeps
                losing becomes a rule; one that keeps winning becomes an edge.
  3. weights  - those numbers become ranking multipliers the universe hunter applies to
                every new candidate. Setups that are paying get pushed up; ones that are
                bleeding get pushed down. Shrunk toward neutral until the sample is real,
                so a hot streak of four trades does not rewrite her playbook.
  4. daily    - review + a lessons note in the vault + the top lessons written to memory,
                so the brain retrieves them the next time she reasons about a trade.

Nothing here places, sizes or blocks an order, or touches a risk limit. It changes what
she looks at first, and what she says about it.

    journal action=review     -> diagnose newly closed signals
    journal action=insights   -> what's working, what's bleeding, learned rules
    journal action=weights    -> the ranking multipliers currently in force
    journal action=daily      -> review + write lessons to vault and memory
    journal action=mistakes   -> the most recent diagnosed mistakes
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from . import backtest, forward_tracker, memory, obsidian

# How many trades before a number is allowed to move her ranking at full strength.
# Below this it is shrunk toward neutral: n / (n + SHRINK).
SHRINK = 10
MIN_RULE_TRADES = 8
WEIGHTS_KEY = "journal.weights"

MISTAKES = {
    "fought_the_market": "Took the trade against the broad market (long under SPY's 50-day, or short above it).",
    "chased_extension": "Entered more than 2 ATR away from the 20-day average - bought the top of the move or sold the hole.",
    "light_volume_break": "Breakout/breakdown on volume under 1.2x average. No participation, no follow-through.",
    "ignored_opposing_candle": "A strong candle pointing the other way was on the chart at entry.",
    "stop_in_the_noise": "Stop under 1 ATR from entry - normal daily noise took it out.",
    "poor_reward_risk": "Target was under 1.5R. Even a good read cannot pay for the losers at that ratio.",
    "dead_money": "Went nowhere for the full hold. Capital parked that could have been working elsewhere.",
}

BREAK_SETUPS = {"breakout_20d", "breakdown_20d", "squeeze_breakout"}


# --------------------------------------------------------------------------- review


def diagnose(signal: dict[str, Any]) -> dict[str, Any]:
    """Why did this trade do what it did? Works off the context logged at signal time."""
    ctx = _context(signal)
    side = signal.get("side") or "buy"
    r = signal.get("r") or 0.0
    tags = conditions(signal)

    mistakes: list[str] = []
    if "against_market" in tags:
        mistakes.append("fought_the_market")
    if "extended" in tags:
        mistakes.append("chased_extension")
    if "light_volume" in tags and signal.get("setup") in BREAK_SETUPS:
        mistakes.append("light_volume_break")
    if "candle_against" in tags:
        mistakes.append("ignored_opposing_candle")
    if "tight_stop" in tags and signal.get("outcome") == "stop":
        mistakes.append("stop_in_the_noise")
    if "low_rr" in tags:
        mistakes.append("poor_reward_risk")
    if signal.get("outcome") == "timeout" and abs(r) < 0.5:
        mistakes.append("dead_money")

    if r > 0:
        verdict = "win"
        lesson = (
            f"{signal['setup']} {side} on {signal['symbol']} paid {r:+.2f}R"
            + (f" despite {', '.join(mistakes)} - do not mistake luck for edge." if mistakes else " - clean execution, repeat it.")
        )
    elif mistakes:
        verdict = "mistake"
        lesson = f"{signal['setup']} {side} on {signal['symbol']} lost {r:+.2f}R. Avoidable: " + " ".join(MISTAKES[m] for m in mistakes)
    else:
        verdict = "cost_of_business"
        lesson = (
            f"{signal['setup']} {side} on {signal['symbol']} lost {r:+.2f}R with nothing wrong at entry. "
            "The stop did its job. Take the next one the same way."
        )
    return {
        "id": signal.get("id"),
        "symbol": signal.get("symbol"),
        "setup": signal.get("setup"),
        "side": side,
        "r": r,
        "outcome": signal.get("outcome"),
        "verdict": verdict,
        "mistakes": mistakes,
        "conditions": sorted(tags),
        "lesson": lesson,
        "context": ctx,
    }


def conditions(signal: dict[str, Any]) -> set[str]:
    """Condition tags for a signal, from its logged context. Shared by review and by the
    live ranker, so what she learns and what she applies are the same vocabulary."""
    ctx = _context(signal)
    side = signal.get("side") or "buy"
    tags: set[str] = set()
    market_up = ctx.get("market_up")
    if market_up is not None:
        with_market = market_up if side == "buy" else not market_up
        tags.add("with_market" if with_market else "against_market")
    ext = ctx.get("extension_atr")
    if ext is not None and ((side == "buy" and ext > 2) or (side == "sell" and ext < -2)):
        tags.add("extended")
    rvol = ctx.get("rvol")
    if rvol is not None:
        tags.add("heavy_volume" if rvol >= 1.5 else "light_volume" if rvol < 1.2 else "normal_volume")
    if ctx.get("candles"):
        tags.add("candle_confirmed")
    if ctx.get("candles_against"):
        tags.add("candle_against")
    stop_atr = ctx.get("stop_atr")
    if stop_atr is not None and stop_atr < 1.0:
        tags.add("tight_stop")
    rr = ctx.get("r_multiple")
    if rr is not None and rr < 1.5:
        tags.add("low_rr")
    if ctx.get("confidence"):
        tags.add(f"confidence_{ctx['confidence']}")
    return tags


def review(*, limit: int = 500) -> dict[str, Any]:
    """Diagnose every closed signal that has not been reviewed yet. Each is studied once."""
    with forward_tracker._db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM forward_signals WHERE status='closed' AND reviewed=0 ORDER BY exit_date LIMIT ?", (limit,),
        ).fetchall()]
    reviews = [diagnose(row) for row in rows]
    with forward_tracker._db() as conn:
        conn.executemany(
            "UPDATE forward_signals SET reviewed=1, lesson=? WHERE id=?",
            [(json.dumps({k: rv[k] for k in ("verdict", "mistakes", "lesson")}), rv["id"]) for rv in reviews],
        )
    counts: dict[str, int] = {}
    for rv in reviews:
        counts[rv["verdict"]] = counts.get(rv["verdict"], 0) + 1
    return {"ok": True, "reviewed": len(reviews), "verdicts": counts, "reviews": reviews}


# --------------------------------------------------------------------------- insights


def insights() -> dict[str, Any]:
    """What is paying, what is bleeding, and which conditions have earned a rule."""
    with forward_tracker._db() as conn:
        closed = [dict(r) for r in conn.execute("SELECT * FROM forward_signals WHERE status='closed'").fetchall()]

    by_setup: dict[str, list[dict]] = {}
    by_condition: dict[str, list[dict]] = {}
    mistake_cost: dict[str, float] = {}
    for t in closed:
        by_setup.setdefault(f"{t['setup']}:{t['side']}", []).append(t)
        for tag in conditions(t):
            by_condition.setdefault(tag, []).append(t)
        verdict = _stored_lesson(t)
        for m in verdict.get("mistakes") or []:
            if (t.get("r") or 0) < 0:
                mistake_cost[m] = round(mistake_cost.get(m, 0.0) + t["r"], 2)

    setups_view = {k: backtest._metrics(v) for k, v in by_setup.items()}
    cond_view = {k: backtest._metrics(v) for k, v in by_condition.items()}

    rules = [
        f"AVOID {tag}: {m['expectancy_r']}R/trade over {m['trades']} trades."
        for tag, m in cond_view.items()
        if m.get("trades", 0) >= MIN_RULE_TRADES and m["expectancy_r"] < -0.2
    ]
    edges = [
        f"FAVOR {tag}: {m['expectancy_r']:+}R/trade over {m['trades']} trades."
        for tag, m in cond_view.items()
        if m.get("trades", 0) >= MIN_RULE_TRADES and m["expectancy_r"] > 0.3
    ]
    ranked = sorted(
        ((k, m) for k, m in setups_view.items() if m.get("trades")),
        key=lambda km: km[1]["expectancy_r"], reverse=True,
    )
    return {
        "ok": True,
        "closed": len(closed),
        "overall": backtest._metrics(closed),
        "by_setup": setups_view,
        "best": [k for k, m in ranked[:3] if m["expectancy_r"] > 0],
        "worst": [k for k, m in ranked[-3:] if m["expectancy_r"] < 0],
        "by_condition": cond_view,
        "rules": rules,
        "edges": edges,
        "mistake_cost_r": dict(sorted(mistake_cost.items(), key=lambda kv: kv[1])),
    }


def weights(*, refresh: bool = False) -> dict[str, Any]:
    """Ranking multipliers learned from live results. 1.0 = neutral.

    setup:side -> 1 + shrunk expectancy, clamped to [0.3, 2.0]
    condition  -> same idea, only for conditions with a real sample
    """
    if not refresh:
        cached = _load_weights()
        if cached:
            return cached
    view = insights()
    setup_w = {k: _weight(m) for k, m in view["by_setup"].items() if m.get("trades")}
    cond_w = {
        k: _weight(m) for k, m in view["by_condition"].items()
        if m.get("trades", 0) >= MIN_RULE_TRADES and not k.startswith("confidence_")
    }
    out = {"ok": True, "setups": setup_w, "conditions": cond_w, "closed": view["closed"], "day": date.today().isoformat()}
    memory.set_fact(WEIGHTS_KEY, json.dumps(out), confidence=1.0, source_agent="trader")
    return out


def multiplier(setup: str, side: str, tags: set[str], learned: dict[str, Any] | None = None) -> float:
    """The combined learned multiplier for one candidate."""
    learned = learned or weights()
    m = float((learned.get("setups") or {}).get(f"{setup}:{side}", 1.0))
    for tag in tags:
        m *= float((learned.get("conditions") or {}).get(tag, 1.0))
    return round(max(0.2, min(m, 3.0)), 3)


def mistakes(limit: int = 15) -> dict[str, Any]:
    with forward_tracker._db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM forward_signals WHERE reviewed=1 AND lesson IS NOT NULL ORDER BY exit_date DESC LIMIT ?",
            (limit * 4,),
        ).fetchall()]
    out = []
    for row in rows:
        lesson = _stored_lesson(row)
        if lesson.get("verdict") != "mistake":
            continue
        out.append({"symbol": row["symbol"], "setup": row["setup"], "r": row["r"], "exit_date": row["exit_date"], **lesson})
        if len(out) >= limit:
            break
    return {"ok": True, "count": len(out), "mistakes": out, "glossary": MISTAKES}


# --------------------------------------------------------------------------- daily


def daily() -> dict[str, Any]:
    """The end-of-day study session: review, recompute weights, write it all down."""
    rv = review()
    view = insights()
    learned = weights(refresh=True)

    day = date.today().isoformat()
    lines = [
        f"---\ntype: lessons\ndate: {day}\n---\n",
        f"# Trading lessons {day}\n",
        f"Closed signals all-time: {view['closed']}. Reviewed today: {rv['reviewed']} {rv['verdicts']}.\n",
    ]
    overall = view["overall"]
    if overall.get("trades"):
        lines.append(
            f"**Overall:** {overall['expectancy_r']:+}R/trade, win rate {overall['win_rate']}%, "
            f"profit factor {overall.get('profit_factor')}, total {overall['total_r']:+}R.\n"
        )
    if view["best"]:
        lines.append("**Paying:** " + ", ".join(view["best"]))
    if view["worst"]:
        lines.append("**Bleeding:** " + ", ".join(view["worst"]))
    if view["rules"] or view["edges"]:
        lines.append("\n## Rules learned\n" + "\n".join(f"- {r}" for r in view["rules"] + view["edges"]))
    if view["mistake_cost_r"]:
        lines.append("\n## What mistakes cost\n" + "\n".join(
            f"- {m}: {cost}R - {MISTAKES.get(m, '')}" for m, cost in view["mistake_cost_r"].items()
        ))
    todays = [r for r in rv["reviews"] if r["verdict"] != "win"][:10] + [r for r in rv["reviews"] if r["verdict"] == "win"][:5]
    if todays:
        lines.append("\n## Trade by trade\n" + "\n".join(f"- [{r['verdict']}] {r['lesson']}" for r in todays))

    note = f"Markets/Lessons/{day}.md"
    try:
        obsidian.write_note(note, "\n".join(lines) + "\n")
    except Exception:
        note = None

    for text in (view["rules"] + view["edges"])[:5] + [r["lesson"] for r in rv["reviews"] if r["verdict"] == "mistake"][:5]:
        memory.remember(text, kind="lesson", tags=["trading", "lesson", "journal"], importance=0.8, source_agent="trader")

    return {
        "ok": True,
        "reviewed": rv["reviewed"],
        "verdicts": rv["verdicts"],
        "rules": view["rules"],
        "edges": view["edges"],
        "weights": learned,
        "vault": note,
    }


# --------------------------------------------------------------------------- helpers


def _weight(m: dict[str, Any]) -> float:
    n = m.get("trades") or 0
    e = m.get("expectancy_r") or 0.0
    return round(max(0.3, min(1.0 + e * n / (n + SHRINK), 2.0)), 3)


def _context(signal: dict[str, Any]) -> dict[str, Any]:
    raw = signal.get("context")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}


def _stored_lesson(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(row.get("lesson") or "{}")
    except (TypeError, ValueError):
        return {}


def _load_weights() -> dict[str, Any] | None:
    for fact in memory.get_facts():
        if fact.get("key") != WEIGHTS_KEY:
            continue
        try:
            data = json.loads(fact.get("value") or "{}")
        except (TypeError, ValueError):
            return None
        return data if data.get("day") == date.today().isoformat() else None
    return None


def dispatch(action: str = "insights", **kwargs: Any) -> Any:
    act = (action or "insights").lower()
    if act == "review":
        return review()
    if act in {"insights", "stats", "report"}:
        return insights()
    if act == "weights":
        return weights(refresh=bool(kwargs.get("refresh")))
    if act in {"daily", "study", "learn"}:
        return daily()
    if act in {"mistakes", "errors"}:
        return mistakes(int(kwargs.get("limit") or 15))
    return {"error": f"unknown journal action {act}", "actions": ["review", "insights", "weights", "daily", "mistakes"]}
