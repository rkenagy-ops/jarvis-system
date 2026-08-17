from __future__ import annotations

import threading
import time
from typing import Any

from . import config, markets, memory, obsidian, widgets

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_job(job: dict[str, Any]) -> str:
    name = job.get("name") or ""
    prompt = (job.get("prompt") or "").lower()
    if name in {"morning-briefing", "briefing"} or "briefing" in prompt:
        summary = briefing()
        memory.mark_job(job["id"], summary[:400])
        return summary
    if name in {"self-upgrade", "growth"} or "self-upgrade" in prompt or "growth pack" in prompt:
        from . import growth

        result = growth.cycle(6)
        summary = f"Self-upgrade: ingested {result.get('count') if 'count' in result else len(result.get('ingested') or [])} — {result.get('note')}"
        memory.mark_job(job["id"], summary[:400])
        return summary
    if name == "watchlist-scan" or prompt.strip().startswith("scan the watchlist"):
        quotes = markets.watchlist()
        movers = []
        for q in quotes:
            pct = q.get("change_pct")
            if pct is None:
                continue
            if abs(pct) >= 1.5:
                movers.append(f"{q['symbol']} {pct:+.2f}% @ {q.get('price')}")
        summary = "Market pulse: " + (", ".join(movers) if movers else "no >1.5% movers on watchlist")
        memory.remember(summary, kind="pulse", tags=["market", "autonomy"], importance=0.55, source_agent="trader")
        try:
            obsidian.daily(append=f"## Market pulse\n{summary}")
        except Exception:
            pass
        memory.mark_job(job["id"], summary)
        return summary
    from . import xai

    if xai.probe().get("ok") and job.get("prompt"):
        from .brain import think

        result = think(job["prompt"], session_id=f"job-{job['id']}", persist_user=False)
        summary = (result.get("text") or "")[:1500]
        memory.remember(summary, kind="job", tags=["autonomy", name], importance=0.5, source_agent="jarvis")
        try:
            obsidian.daily(append=f"## Job {name}\n{summary}")
        except Exception:
            pass
        memory.mark_job(job["id"], summary[:400])
        return summary
    note = f"Autonomy job '{name}' is due: {job.get('prompt')}"
    memory.remember(note, kind="job", tags=["autonomy"], importance=0.4, source_agent="jarvis")
    memory.mark_job(job["id"], note[:400])
    return note


def briefing(*, use_grok: bool = True) -> str:
    quotes = []
    try:
        quotes = markets.watchlist()
    except Exception:
        pass
    movers = []
    for q in quotes:
        if q.get("price") is None:
            continue
        pct = q.get("change_pct")
        bit = f"{q['symbol']} {q['price']}"
        if pct is not None:
            bit += f" ({pct:+.2f}%)"
        movers.append(bit)
    wx = {}
    try:
        wx = widgets.weather()
    except Exception:
        pass
    news = {}
    try:
        from . import feeds

        news = {"items": [{"title": t} for t in feeds.headlines(6)]}
    except Exception:
        try:
            news = widgets.news()
        except Exception:
            news = {}
    tasks = obsidian.list_tasks(open_only=True, limit=8)
    headlines = [i.get("title") for i in (news.get("items") or [])[:4] if i.get("title")]
    temp = ((wx.get("current") or {}).get("temperature_2m"))
    lines = [
        "## Morning briefing",
        f"- Weather: {temp} C" if temp is not None else "- Weather: n/a",
        "- Markets: " + (", ".join(movers[:8]) if movers else "n/a"),
        "- News: " + ("; ".join(headlines) if headlines else "n/a"),
        "- Open tasks: " + ("; ".join(t["text"] for t in tasks) if tasks else "none"),
    ]
    try:
        goals = memory.list_goals("open")
        if goals:
            lines.append("- Goals: " + "; ".join(g.get("title") or "" for g in goals[:5]))
    except Exception:
        pass
    try:
        from . import reminders

        due = reminders.list_items(open_only=True, limit=5)
        if due:
            lines.append("- Coming up: " + "; ".join(f"{r['title']} @ {r['when'][:16]}" for r in due))
    except Exception:
        pass
    try:
        from . import daily as daily_mod

        yest = daily_mod.yesterday_excerpt()
        if yest:
            lines.append("- Yesterday: " + " ".join((yest.get("excerpt") or "").split())[:220])
    except Exception:
        pass
    raw = "\n".join(lines)
    text = raw
    if use_grok:
        try:
            from . import xai

            if xai.probe().get("ok"):
                resp = xai.responses_create(
                    {
                        "model": config.MODEL,
                        "input": [
                            {
                                "role": "system",
                                "content": "You are J.A.R.V.I.S. Write a tight morning brief for Rhett. Use the facts. Flag risk. No fluff. Markdown. 8-14 lines.",
                            },
                            {"role": "user", "content": raw},
                        ],
                    }
                )
                grok = xai.extract_text(resp)
                if grok:
                    text = "## Morning briefing\n" + grok
        except Exception:
            text = raw
    try:
        obsidian.daily(append=text)
    except Exception:
        pass
    memory.remember(text, kind="briefing", tags=["autonomy", "briefing"], importance=0.7, source_agent="jarvis")
    return text


def ensure_defaults() -> list[dict]:
    """Seed the jobs that make Jarvis live without a click."""
    have = {j.get("name") for j in memory.list_jobs()}
    seeded = []
    specs = [
        ("morning-briefing", "Write the morning briefing to today's daily note.", 86400),
        ("watchlist-scan", "Scan the watchlist for 1.5% movers.", 1800),
        ("self-upgrade", "Hunt GitHub for OSS Super Jarvis can absorb. Ingest new READMEs. Do not clone stacks.", 21600),
    ]
    for name, prompt, every in specs:
        if name in have:
            continue
        job = memory.add_job(name, prompt, every)
        memory.mark_job(job["id"], "seeded — waiting first interval")
        seeded.append(job)
    return seeded


def beat() -> list[str]:
    if not config.AUTONOMY_ENABLED:
        return []
    results = []
    try:
        from . import reminders

        for item in reminders.fire_due():
            results.append(f"fired {item.get('kind')}: {item.get('title')}")
    except Exception as exc:
        results.append(f"reminder-error {exc}")
    try:
        from . import ops

        for item in ops.fire_due():
            results.append(f"publish {item}")
    except Exception as exc:
        results.append(f"publish-error {exc}")
    for job in memory.due_jobs():
        try:
            results.append(run_job(job))
        except Exception as exc:
            memory.mark_job(job["id"], f"error: {exc}")
            results.append(str(exc))
    return results


def _loop() -> None:
    while not _stop.wait(20):
        try:
            beat()
        except Exception:
            continue


def start() -> None:
    global _thread
    markets.init()
    try:
        ensure_defaults()
    except Exception:
        pass
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="jarvis-autonomy", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def snapshot() -> dict[str, Any]:
    due = []
    try:
        from . import reminders

        due = reminders.snapshot()
    except Exception:
        due = {}
    return {
        "enabled": config.AUTONOMY_ENABLED,
        "jobs": memory.list_jobs(),
        "goals": memory.list_goals("open"),
        "skills": memory.list_skills(),
        "account": markets.account(),
        "reminders": due,
    }
