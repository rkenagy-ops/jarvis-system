"""Daily Driver — the OS loop Super Jarvis exists to run."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import config, memory, obsidian, reminders, skills, widgets

OBSIDIAN_CANDIDATES = (
    Path.home() / "AppData/Local/Obsidian/Obsidian.exe",
    Path.home() / "AppData/Local/Programs/obsidian/Obsidian.exe",
    Path(r"C:\Program Files\Obsidian\Obsidian.exe"),
    Path(r"C:\Program Files\Obsidian\Obsidian\Obsidian.exe"),
)


def obsidian_exe() -> str | None:
    found = shutil.which("obsidian")
    if found:
        return found
    for path in OBSIDIAN_CANDIDATES:
        if path.is_file():
            return str(path)
    return None


def seed_owner() -> dict:
    """Write the working notes. Safe to re-run; replaces stubs."""
    obsidian.init_vault()
    notes = {
        "00 Home.md": """---
type: moc
tags: [jarvis, home]
---

# Jarvis OS

This folder is the source of truth. Super Jarvis reads and writes it. Open it in Obsidian: **File → Open folder as vault**.

## Today
- [[Daily]]
- Run **BRIEFING** in the HUD or say “Jarvis, start my day.”

## Maps
- [[People/Rhett Kenagy]]
- [[Projects/jarvis-system]]
- [[Inbox/Getting started]]
- [[Skills/daily-driver]]
- [[Skills/fortress]]
- [[Markets]]
- [[Calendar]]
- [[Memory]]

## How this works
SQLite is the fast index. Markdown here is what you keep. Wikilinks stay intact.
""",
        "People/Rhett Kenagy.md": """---
type: person
role: owner
github: rkenagy-ops
---

# Rhett Kenagy

Owner of [[00 Home]] and [[Projects/jarvis-system]].

- GitHub: [rkenagy-ops](https://github.com/rkenagy-ops)
- Prefers concise briefings
- Locale: Houston unless he says otherwise
- Trading: paper until several reviews pass. Live fills need a confirm token.
- Publish: drafts in Content Studio. Live social/Amazon stay confirm-gated.

## Standing orders
- Do not expose the HUD past 127.0.0.1
- Do not start Docker just to feel complete
- Persist lessons into this vault
""",
        "Projects/jarvis-system.md": """---
type: project
repo: rkenagy-ops/jarvis-system
status: active
---

# jarvis-system

GitHub: https://github.com/rkenagy-ops/jarvis-system

Local HUD: http://127.0.0.1:8787 (fortress / loopback).

## Now (3.2 Daily Driver)
- Use the vault every morning
- Paper markets only
- One live publish channel later — not nine

## Later (not now)
- One official social/WordPress pipe with confirm
- Optional Ollama fallback
- Tailscale to this PC if a phone is needed — still no public port

## Explicitly parked
Docker, n8n, Postiz — see [[Skills/why-not-docker]].
""",
        "Inbox/Getting started.md": """---
type: inbox
---

# Getting started

- [x] Add XAI_API_KEY
- [x] Connect GitHub (rkenagy-ops via gh)
- [x] Fortress on (loopback + token)
- [x] Open this vault in Obsidian (HUD **VAULT** button)
- [x] Hit **BRIEFING** once for real
- [x] Add one real task to today's daily note
""",
        "Templates/Daily.md": """---
type: daily
date: {{date}}
---

# {{date}}

## Briefing

## Capture

## Markets

## Tasks
- [ ]

## Links
- [[People/Rhett Kenagy]]
- [[Projects/jarvis-system]]
""",
        "Skills/briefing.md": """---
type: skill
---

# Briefing

1. Weather, watchlist, headlines.
2. Open vault tasks and due reminders.
3. Open goals.
4. Yesterday's daily note, if any.
5. Write into today's [[Daily]] note.
6. Do not trade.
""",
        "Skills/daily-driver.md": """---
type: skill
name: daily-driver
---

# Daily Driver

This is the current phase.

1. **VAULT** opens the Obsidian folder.
2. **BRIEFING** writes weather, markets, tasks, reminders, goals.
3. Say “Jarvis, start my day.”
4. Capture facts on [[People/Rhett Kenagy]] — not in chat history.
""",
        "Skills/why-not-docker.md": """---
type: skill
name: why-not-docker
---

# Why we parked Docker, n8n, and Postiz

They are real tools. They are the wrong *next* tool.

## Docker compose in this repo
The file starts LiteLLM, n8n, Whisper, Piper, Stirling. Super Jarvis already has:
- Grok STT/TTS (no Whisper/Piper containers)
- local PDF extract (no Stirling required)
- autonomy jobs (no n8n required)
- content drafts in the vault (no Postiz required)

Those containers publish extra ports. Default Compose binds `0.0.0.0`, which punches a hole in fortress. If you ever start them, ports are pinned to `127.0.0.1` now.

## n8n
A visual workflow box for *other people's* SaaS. We already fire briefings, watchlist pulses, reminders, and confirm-gated publishes in-process. n8n earns its keep when there is a *specific* webhook (Shopify, a form, a CRM) — not as atmosphere.

## Postiz
A second app, second login stack, second database, for a social queue. Studio already drafts captions/blogs/listings. Live post still needs official OAuth + a confirm token. Adding Postiz before one official channel works is another control plane with nothing to queue.

## When we will turn them on
- **n8n**: you name a real trigger (“when this form lands, draft a listing”).
- **Postiz**: after one official network publishes with confirm, and you want a calendar UI.
- **Docker**: only to run *that* named service, loopback-bound.
""",
    }
    written = []
    always = {
        "Inbox/Getting started.md",
        "Templates/Daily.md",
        "Skills/briefing.md",
        "Skills/daily-driver.md",
        "Skills/why-not-docker.md",
    }
    stub_marks = (
        "Owner of [[00 Home]]. GitHub: `rkenagy-ops`.",
        "This folder is an [Obsidian](https://obsidian.md) vault.",
        "Point `OBSIDIAN_VAULT` at this folder",
        "Keep paper trading until several reviews pass",
    )
    for rel, body in notes.items():
        path = obsidian.vault() / rel
        if path.is_file() and rel not in always:
            existing = path.read_text(encoding="utf-8", errors="replace")
            if "seed: lock" in existing:
                continue
            if not any(m in existing for m in stub_marks) and len(existing) > 400:
                continue
        obsidian.write_note(rel, body)
        written.append(rel)
    memory.set_fact("owner.name", "Rhett", confidence=0.99, source_agent="daily")
    memory.set_fact("owner.locale", "Houston", confidence=0.8, source_agent="daily")
    memory.set_fact("owner.briefing", "concise", confidence=0.85, source_agent="daily")
    if not any(g.get("title") == "Run Daily Driver for a week" for g in memory.list_goals("open")):
        memory.add_goal("Run Daily Driver for a week", "Briefing + vault every morning. No Docker until a named job needs it.", 0.8)
    return {"ok": True, "notes": written}


def yesterday_excerpt() -> dict | None:
    day = (date.today() - timedelta(days=1)).isoformat()
    rel = f"Daily/{day}.md"
    try:
        path = obsidian.resolve(rel)
    except Exception:
        return None
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"path": rel, "excerpt": text[:800]}


def pack() -> dict[str, Any]:
    obsidian.init_vault()
    day = obsidian.daily()
    tasks = obsidian.list_tasks(open_only=True, limit=10)
    goals = memory.list_goals("open")
    wx = {}
    try:
        wx = widgets.weather()
    except Exception as exc:
        wx = {"error": str(exc)}
    return {
        "greeting": skills.greeting(),
        "now": widgets.now(),
        "daily": {"path": day.get("path"), "chars": len(day.get("text") or "")},
        "weather": wx,
        "tasks": tasks,
        "goals": [{"title": g.get("title"), "detail": g.get("detail")} for g in goals[:6]],
        "reminders": reminders.list_items(open_only=True, limit=6),
        "yesterday": yesterday_excerpt(),
        "obsidian_installed": bool(obsidian_exe()),
        "vault": str(obsidian.vault()),
    }


def open_vault() -> dict:
    root = obsidian.vault()
    exe = obsidian_exe()
    uri = "obsidian://open?path=" + quote(str(root))
    if exe:
        try:
            subprocess.Popen([exe, str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "via": "exe", "path": str(root), "exe": exe}
        except Exception:
            pass
    try:
        webbrowser.open(uri)
    except Exception:
        pass
    try:
        subprocess.Popen(["explorer.exe", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "via": "explorer", "path": str(root), "obsidian_installed": bool(exe), "uri": uri}
    except Exception as exc:
        return {"error": str(exc), "path": str(root)}
