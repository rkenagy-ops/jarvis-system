"""One-shot reminders and timers that autonomy actually fires."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config

PATH = config.DATA_DIR / "reminders.json"


def _load() -> list[dict]:
    if not PATH.exists():
        return []
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return list(data.get("items") or [])
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    PATH.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")


def add(title: str, when: str = "", *, minutes: int = 0, kind: str = "reminder") -> dict:
    when_iso = (when or "").strip()
    if minutes:
        when_iso = (datetime.now(timezone.utc) + timedelta(minutes=int(minutes))).isoformat()
    if not when_iso:
        when_iso = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    item = {
        "id": uuid.uuid4().hex[:10],
        "title": (title or "Reminder").strip()[:200],
        "when": when_iso,
        "kind": kind,
        "fired": False,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    items = _load()
    items.append(item)
    _save(items)
    return item


def timer(minutes: int, title: str = "Timer") -> dict:
    mins = max(1, int(minutes or 1))
    return add(title or f"{mins} minute timer", minutes=mins, kind="timer")


def list_items(*, open_only: bool = False, limit: int = 30) -> list[dict]:
    rows = _load()
    if open_only:
        rows = [r for r in rows if not r.get("fired")]
    rows.sort(key=lambda r: r.get("when") or "")
    return rows[:limit]


def due(*, now: float | None = None) -> list[dict]:
    stamp = now if now is not None else time.time()
    out = []
    for item in _load():
        if item.get("fired"):
            continue
        try:
            when = datetime.fromisoformat(item["when"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when.timestamp() <= stamp:
                out.append(item)
        except Exception:
            continue
    return out


def mark_fired(item_id: str) -> bool:
    items = _load()
    ok = False
    for item in items:
        if item.get("id") == item_id:
            item["fired"] = True
            item["fired_at"] = datetime.now(timezone.utc).isoformat()
            ok = True
    if ok:
        _save(items)
    return ok


def dismiss(item_id: str) -> bool:
    return mark_fired(item_id)


def fire_due() -> list[dict]:
    from . import desktop, memory, obsidian

    fired = []
    for item in due():
        title = item.get("title") or "Reminder"
        try:
            desktop.notify("Jarvis", title)
        except Exception:
            pass
        try:
            obsidian.daily(append=f"- [x] Fired {item.get('kind')}: {title}")
        except Exception:
            pass
        try:
            memory.remember(f"Fired {item.get('kind')}: {title}", kind="reminder", tags=["autonomy"], importance=0.45)
        except Exception:
            pass
        mark_fired(item["id"])
        fired.append(item)
    return fired


def snapshot() -> dict[str, Any]:
    open_items = list_items(open_only=True)
    return {"open": open_items, "due": due(), "count": len(open_items)}
