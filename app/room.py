"""Rolling room context — from isair/jarvis 'third person in the room'."""

from __future__ import annotations

import json
import time
from typing import Any

from . import config
from .redact import redact

ROOM_PATH = config.DATA_DIR / "room.json"
MAX_LINES = 16


def _load() -> list[dict]:
    if not ROOM_PATH.exists():
        return []
    try:
        data = json.loads(ROOM_PATH.read_text(encoding="utf-8"))
        return list(data.get("lines") or [])
    except Exception:
        return []


def _save(lines: list[dict]) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    ROOM_PATH.write_text(json.dumps({"lines": lines[-MAX_LINES:]}, indent=2), encoding="utf-8")


def hear(who: str, text: str) -> dict[str, Any]:
    clean = redact((text or "").strip())
    if not clean:
        return {"ok": False, "error": "empty"}
    speaker = (who or "owner")[:24]
    lines = _load()
    if lines and lines[-1].get("who") == speaker and lines[-1].get("text") == clean:
        return {"ok": True, "dup": True, "count": len(lines)}
    lines.append({"t": time.time(), "who": speaker, "text": clean[:400]})
    _save(lines)
    return {"ok": True, "count": min(len(lines), MAX_LINES)}


def lines(limit: int = 12) -> list[dict]:
    return _load()[-max(1, min(int(limit), MAX_LINES)) :]


def context() -> str:
    rows = lines(12)
    if not rows:
        return "# ROOM\n- Quiet. No recent overheard lines."
    out = ["# ROOM (rolling — last overheard / spoken)"]
    for row in rows:
        out.append(f"- {row.get('who')}: {row.get('text')}")
    out.append("If the owner says 'what do you think?' answer from this room thread.")
    return "\n".join(out)


def clear() -> dict:
    _save([])
    return {"ok": True, "cleared": True}
