"""Event-driven triggers: fire a job when something happens, not on the next tick.

autonomy.beat() polls. A vault edit at 09:01 is noticed whenever the loop next comes
round, and a job due while Jarvis was closed is simply missed. That is fine for a
market scan and wrong for anything reactive.

This adds the other half. Jobs subscribe to named events; emit() runs the matching
ones straight away, through the same JOB_HANDLERS registry the timers use — so an
event-fired job and a timer-fired job are the same code path, with the same audit
trail in mark_job.

    events.subscribe("vault.changed", "bot-19-rag")
    events.emit("vault.changed", {"path": "Markets/2026-08-24.md"})

Sources are things that generate events on their own. The file watcher uses watchdog
when installed and falls back to a polling thread when it is not, so this degrades
rather than breaking — but a polling fallback is still polling, and status() says so
plainly rather than implying the watcher is live.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import config, memory

# event name -> job names to run
SUBSCRIPTIONS: dict[str, list[str]] = {}
# source name -> {"kind": ..., "detail": ..., "running": bool}
SOURCES: dict[str, dict[str, Any]] = {}

_lock = threading.RLock()
_watchers: list[Any] = []
_stop = threading.Event()

# Events that fire with no subscriber are still worth recording — a silent no-op
# looks identical to a broken watcher.
_recent: list[dict[str, Any]] = []
MAX_RECENT = 50

# Editors write in bursts — one save can fire several filesystem events. Source-generated
# emits coalesce inside this window so a subscribed job runs once, not six times. Manual
# emit() ignores it: if you asked for it explicitly, you meant it.
COALESCE_SEC = 5.0
_last_fired: dict[str, float] = {}


def subscribe(event: str, job_name: str) -> dict[str, Any]:
    event = (event or "").strip().lower()
    job_name = (job_name or "").strip()
    if not event or not job_name:
        return {"error": "event and job_name required."}

    from . import autonomy

    if job_name not in autonomy.JOB_HANDLERS:
        return {
            "error": f"{job_name!r} is not a known job.",
            "known": sorted(autonomy.JOB_HANDLERS)[:20],
        }
    with _lock:
        subs = SUBSCRIPTIONS.setdefault(event, [])
        if job_name not in subs:
            subs.append(job_name)
    return {"ok": True, "event": event, "job": job_name, "subscribers": len(SUBSCRIPTIONS[event])}


def unsubscribe(event: str, job_name: str = "") -> dict[str, Any]:
    event = (event or "").strip().lower()
    with _lock:
        if event not in SUBSCRIPTIONS:
            return {"ok": False, "error": f"no subscriptions for {event!r}"}
        if not job_name:
            removed = len(SUBSCRIPTIONS.pop(event))
            return {"ok": True, "removed": removed}
        subs = SUBSCRIPTIONS[event]
        if job_name in subs:
            subs.remove(job_name)
            return {"ok": True, "removed": 1}
    return {"ok": False, "error": f"{job_name} was not subscribed to {event}"}


def emit(event: str, payload: dict[str, Any] | None = None, *, coalesce: bool = False) -> dict[str, Any]:
    """Run every job subscribed to this event, now.

    coalesce=True is for automatic sources: a burst of filesystem events becomes one
    job run. Manual calls never coalesce.
    """
    event = (event or "").strip().lower()
    payload = payload or {}
    if not event:
        return {"error": "event required."}

    from . import autonomy

    with _lock:
        if coalesce:
            last = _last_fired.get(event, 0.0)
            if time.time() - last < COALESCE_SEC:
                return {"ok": True, "event": event, "jobs_run": 0, "results": [], "coalesced": True}
        _last_fired[event] = time.time()
        jobs = list(SUBSCRIPTIONS.get(event) or [])

    results = []
    for job_name in jobs:
        handler = autonomy.JOB_HANDLERS.get(job_name)
        if not handler:
            results.append({"job": job_name, "error": "handler disappeared"})
            continue
        try:
            summary = handler()
        except Exception as exc:
            summary = f"{job_name} failed: {type(exc).__name__}: {str(exc)[:200]}"
        results.append({"job": job_name, "summary": str(summary)[:400]})

    record = {
        "event": event,
        "payload": payload,
        "jobs_run": len(results),
        "at": time.time(),
    }
    with _lock:
        _recent.insert(0, record)
        del _recent[MAX_RECENT:]

    if results:
        memory.remember(
            f"Event {event} fired {len(results)} job(s): {', '.join(r['job'] for r in results)}",
            kind="event",
            tags=["events", event],
            importance=0.5,
            source_agent="jarvis",
        )

    return {
        "ok": True,
        "event": event,
        "jobs_run": len(results),
        "results": results,
        "note": None if results else f"No job is subscribed to {event!r}.",
    }


# --------------------------------------------------------------------------- sources


def _watchdog_available() -> bool:
    try:
        import watchdog  # noqa: F401

        return True
    except ImportError:
        return False


def _start_watchdog(path: Path, event: str) -> bool:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        return False

    class Handler(FileSystemEventHandler):
        def on_any_event(self, ev):  # noqa: ANN001
            if getattr(ev, "is_directory", False):
                return
            emit(event, {"path": str(getattr(ev, "src_path", "")), "change": ev.event_type}, coalesce=True)

    observer = Observer()
    observer.schedule(Handler(), str(path), recursive=True)
    observer.daemon = True
    observer.start()
    _watchers.append(observer)
    return True


def _start_polling(path: Path, event: str, interval: float = 30.0) -> None:
    """Fallback when watchdog is absent. Still polling — status() says so."""

    def loop() -> None:
        seen: dict[str, float] = {}
        while not _stop.is_set():
            try:
                for f in path.rglob("*.md"):
                    try:
                        mtime = f.stat().st_mtime
                    except OSError:
                        continue
                    key = str(f)
                    if key in seen and mtime > seen[key]:
                        emit(event, {"path": key, "change": "modified"}, coalesce=True)
                    seen[key] = mtime
            except Exception:
                pass
            _stop.wait(interval)

    t = threading.Thread(target=loop, name="events-poll", daemon=True)
    t.start()
    _watchers.append(t)


def watch_vault(event: str = "vault.changed") -> dict[str, Any]:
    """Fire an event whenever a vault note changes."""
    vault = Path(getattr(config, "VAULT_DIR", "") or (config.ROOT / "vault"))
    if not vault.exists():
        return {"error": f"vault not found at {vault}"}

    if "vault" in SOURCES:
        return {"ok": True, "already_running": True, **SOURCES["vault"]}

    _stop.clear()
    if _start_watchdog(vault, event):
        SOURCES["vault"] = {"kind": "watchdog", "detail": f"native filesystem events on {vault}", "running": True, "event": event}
    else:
        _start_polling(vault, event)
        SOURCES["vault"] = {
            "kind": "polling",
            "detail": f"30s polling on {vault} — install watchdog for real events",
            "running": True,
            "event": event,
        }
    return {"ok": True, **SOURCES["vault"]}


def stop_all() -> dict[str, Any]:
    _stop.set()
    stopped = 0
    for w in list(_watchers):
        try:
            if hasattr(w, "stop"):
                w.stop()
            stopped += 1
        except Exception:
            pass
    _watchers.clear()
    SOURCES.clear()
    _last_fired.clear()
    return {"ok": True, "stopped": stopped}


def status() -> dict[str, Any]:
    with _lock:
        subs = {k: list(v) for k, v in SUBSCRIPTIONS.items()}
        recent = list(_recent[:10])
    return {
        "ok": True,
        "subscriptions": subs,
        "subscription_count": sum(len(v) for v in subs.values()),
        "sources": SOURCES,
        "watchdog_installed": _watchdog_available(),
        "recent_events": recent,
        "note": (
            "Sources generate events on their own; emit() can also be called directly "
            "(from a webhook, a tool, or another job)."
        ),
    }


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    if act in {"status", "list"}:
        return status()
    if act == "subscribe":
        return subscribe(str(kwargs.get("event") or ""), str(kwargs.get("job") or kwargs.get("job_name") or ""))
    if act == "unsubscribe":
        return unsubscribe(str(kwargs.get("event") or ""), str(kwargs.get("job") or kwargs.get("job_name") or ""))
    if act in {"emit", "fire", "trigger"}:
        return emit(str(kwargs.get("event") or ""), kwargs.get("payload") or {})
    if act in {"watch", "watch_vault"}:
        return watch_vault(str(kwargs.get("event") or "vault.changed"))
    if act in {"stop", "stop_all"}:
        return stop_all()
    return {
        "error": f"unknown events action {act}",
        "actions": ["status", "subscribe", "unsubscribe", "emit", "watch", "stop"],
    }
