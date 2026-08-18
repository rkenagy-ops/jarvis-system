"""Meeting minutes → vault. Steal Meetily's job, not the stack."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from . import memory, obsidian

ACTION_LINE = re.compile(
    r"(?i)^\s*(?:[-*]\s*\[[ xX]\]\s+|(?:todo|action(?:\s*item)?|follow[- ]?up)\s*[:\-]\s+)(.+)$"
)
DECISION_LINE = re.compile(
    r"(?i)^\s*(?:[-*]\s*)?(?:decision|decided|agreed|we will|resolution)\s*[:\-]?\s+(.+)$"
)
ATTENDEE_LINE = re.compile(r"(?i)^\s*(?:attendees|present|who)\s*[:\-]\s*(.+)$")
TITLE_LINE = re.compile(r"(?i)^\s*(?:title|meeting|subject)\s*[:\-]\s*(.+)$")


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "meeting").lower()).strip("-")
    return (s[:48] or "meeting")


def parse(transcript: str, *, title: str = "", attendees: str = "") -> dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        return {"error": "empty transcript"}
    found_title = (title or "").strip()
    found_att = (attendees or "").strip()
    actions: list[str] = []
    decisions: list[str] = []
    body_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            body_lines.append("")
            continue
        tm = TITLE_LINE.match(line)
        if tm and not found_title:
            found_title = tm.group(1).strip()
            continue
        am = ATTENDEE_LINE.match(line)
        if am and not found_att:
            found_att = am.group(1).strip()
            continue
        dm = DECISION_LINE.match(line)
        if dm:
            decisions.append(dm.group(1).strip())
            continue
        xm = ACTION_LINE.match(line)
        if xm:
            item = xm.group(1).strip()
            if item and item not in actions:
                actions.append(item)
            continue
        body_lines.append(line)
    if not found_title:
        first = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "Untitled meeting")
        found_title = first[:80]
    notes = "\n".join(body_lines).strip()
    return {
        "title": found_title,
        "attendees": found_att,
        "decisions": decisions,
        "actions": actions,
        "notes": notes or text[:4000],
    }


def file_minutes(transcript: str, *, title: str = "", attendees: str = "") -> dict[str, Any]:
    parsed = parse(transcript, title=title, attendees=attendees)
    if parsed.get("error"):
        return parsed
    obsidian.init_vault()
    day = date.today().isoformat()
    stamp = datetime.now().strftime("%H%M")
    slug = _slug(parsed["title"])
    rel = f"Meetings/{day}-{stamp}-{slug}.md"
    action_md = "\n".join(f"- [ ] {a}" for a in parsed["actions"]) or "- [ ] "
    decision_md = "\n".join(f"- {d}" for d in parsed["decisions"]) or "- (none captured)"
    att = parsed["attendees"] or "unlisted"
    body = (
        f"---\ntype: meeting\ndate: {day}\ntitle: {parsed['title']}\n"
        f"attendees: {att}\ntags: [meeting]\n---\n\n"
        f"# {parsed['title']}\n\n"
        f"- Date: {day}\n- Attendees: {att}\n\n"
        f"## Decisions\n{decision_md}\n\n"
        f"## Action items\n{action_md}\n\n"
        f"## Notes\n\n{parsed['notes']}\n\n"
        f"## Links\n- [[{day}]]\n"
    )
    written = obsidian.write_note(rel, body)
    obsidian.daily(append=f"## Meeting: {parsed['title']}\n- [[{written['path'].replace('.md', '')}]]")
    try:
        memory.remember(
            f"Meeting filed: {parsed['title']} ({len(parsed['actions'])} actions)",
            kind="meeting",
            tags=["meeting"],
            importance=0.65,
            source_agent="liaison",
        )
    except Exception:
        pass
    return {
        "ok": True,
        "path": written["path"],
        "title": parsed["title"],
        "attendees": att,
        "decisions": parsed["decisions"],
        "actions": parsed["actions"],
        "count_actions": len(parsed["actions"]),
    }


def list_recent(limit: int = 8) -> dict[str, Any]:
    obsidian.init_vault()
    root = obsidian.vault() / "Meetings"
    if not root.exists():
        return {"meetings": []}
    notes = sorted(root.glob("*.md"), reverse=True)
    out = []
    for path in notes[: max(1, min(int(limit), 30))]:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        out.append({"path": path.relative_to(obsidian.vault()).as_posix(), "title": title})
    return {"meetings": out}


def dispatch(action: str, **kwargs: Any) -> dict[str, Any]:
    if action in {"file", "minutes", "save"}:
        return file_minutes(
            kwargs.get("transcript") or kwargs.get("notes") or kwargs.get("body") or "",
            title=kwargs.get("title") or "",
            attendees=kwargs.get("attendees") or "",
        )
    if action == "list":
        return list_recent(int(kwargs.get("limit") or 8))
    return {"error": f"unknown meeting action {action}"}
