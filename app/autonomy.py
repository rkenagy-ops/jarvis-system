from __future__ import annotations

import threading
import time
from typing import Any

from . import config, markets, memory

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_job(job: dict[str, Any]) -> str:
    name = job.get("name") or ""
    if name == "watchlist-scan" or "watchlist" in (job.get("prompt") or "").lower():
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
        memory.mark_job(job["id"], summary)
        return summary
    # Generic jobs without a model key just log the prompt as a reminder.
    note = f"Autonomy job '{name}' is due: {job.get('prompt')}"
    memory.remember(note, kind="job", tags=["autonomy"], importance=0.4, source_agent="jarvis")
    memory.mark_job(job["id"], note[:400])
    return note


def beat() -> list[str]:
    if not config.AUTONOMY_ENABLED:
        return []
    results = []
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
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="jarvis-autonomy", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def snapshot() -> dict[str, Any]:
    return {
        "enabled": config.AUTONOMY_ENABLED,
        "jobs": memory.list_jobs(),
        "goals": memory.list_goals("open"),
        "skills": memory.list_skills(),
        "account": markets.account(),
    }
