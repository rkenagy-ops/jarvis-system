"""Score the last briefing against the live desk — STEWARD's yardstick."""

from __future__ import annotations

from datetime import date
from typing import Any

from . import intel, memory, obsidian


def score(briefing_text: str) -> dict[str, Any]:
    desk = {}
    try:
        desk = intel.desk()
    except Exception as exc:
        desk = {"error": str(exc), "movers": [], "news": []}
    movers = [m.get("symbol") for m in (desk.get("movers") or []) if m.get("symbol")]
    text = (briefing_text or "").upper()
    hit = [s for s in movers if s.replace("-USD", "").replace("=X", "").replace("^", "")[:4] in text or s in text]
    news_n = len(desk.get("news") or [])
    score_n = (len(hit) / len(movers)) if movers else 1.0
    body = (
        f"# Briefing eval {date.today().isoformat()}\n\n"
        f"- Movers scanned: {', '.join(movers[:8]) or 'none'}\n"
        f"- Mentioned in briefing: {', '.join(hit) or 'none'}\n"
        f"- Coverage: {score_n:.0%} ({len(hit)}/{len(movers) or 0})\n"
        f"- Headlines in desk: {news_n}\n"
    )
    note = obsidian.write_note(f"Memory/{date.today().isoformat()}-briefing-eval.md", body)
    memory.remember(body, kind="eval", tags=["eval", "briefing"], importance=0.4, source_agent="steward")
    return {"ok": True, "score": score_n, "hit": hit, "movers": movers, "path": note.get("path")}
