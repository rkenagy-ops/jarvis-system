"""Skill catalog distilled from the best GitHub Jarvis programs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

# id, phrases, description, borrowed-from
SKILLS: list[dict[str, Any]] = [
    {"id": "brief", "phrases": ("brief", "briefing", "morning", "plan my day"), "desc": "Morning briefing + plan the day from weather, tasks, calendar", "src": "ethanplusai/jarvis"},
    {"id": "weather", "phrases": ("weather",), "desc": "Current weather (Open-Meteo)", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "news", "phrases": ("news", "headlines", "live feed"), "desc": "Live BBC/NPR/Yahoo/HN + Yahoo Finance tape", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "wiki", "phrases": ("wiki", "who is", "what is"), "desc": "Wikipedia person/topic lookup", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "time", "phrases": ("what time", "the time", "date", "utc"), "desc": "Local + UTC time", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "youtube", "phrases": ("youtube", "play "), "desc": "Play / search YouTube", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "maps", "phrases": ("map", "where is", "navigate"), "desc": "Maps + geocode", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "google", "phrases": ("google", "search google", "search the web"), "desc": "Open a Google search", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "open", "phrases": ("open ",), "desc": "Open http(s) URL or a whitelisted app", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "note", "phrases": ("take a note", "save a note", "remember this"), "desc": "Capture a note to the vault inbox", "src": "ethanplusai/jarvis"},
    {"id": "remind", "phrases": ("remind me", "reminder"), "desc": "Reminder that autonomy fires with a toast", "src": "ethanplusai/jarvis"},
    {"id": "timer", "phrases": ("timer", "set a timer"), "desc": "Countdown timer that toasts when due", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "define", "phrases": ("define ", "what does"), "desc": "English dictionary", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "translate", "phrases": ("translate",), "desc": "Translate via MyMemory", "src": "desktop Jarvis crowd"},
    {"id": "find", "phrases": ("find file", "find "), "desc": "Find files in vault + workspace", "src": "Melissa-AI/Melissa-Core"},
    {"id": "screenshot", "phrases": ("screenshot", "capture the screen"), "desc": "Screenshot to workspace/images", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "joke", "phrases": ("joke", "make me laugh"), "desc": "Dry one-liner", "src": "kishanrajput23/Jarvis-Desktop-Voice-Assistant"},
    {"id": "sysinfo", "phrases": ("system info", "cpu", "battery", "disk"), "desc": "Host CPU/RAM/disk/battery", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "clipboard", "phrases": ("clipboard",), "desc": "Read or set the clipboard", "src": "desktop Jarvis crowd"},
    {"id": "notify", "phrases": ("notify", "toast"), "desc": "Windows toast notification", "src": "isair/jarvis"},
    {"id": "email", "phrases": ("email", "draft an email"), "desc": "Email draft to vault (no silent send)", "src": "GauravSingh9356/J.A.R.V.I.S"},
    {"id": "room", "phrases": ("what do you think", "room"), "desc": "Answer from rolling room context", "src": "isair/jarvis"},
    {"id": "redact", "phrases": (), "desc": "Secrets redacted before disk", "src": "isair/jarvis"},
    {"id": "wake", "phrases": ("jarvis",), "desc": "Wake word anywhere in the sentence", "src": "isair/jarvis"},
    {"id": "markets", "phrases": ("watchlist", "quote", "buy", "sell", "yahoo"), "desc": "Yahoo Finance quotes + paper trades", "src": "super-jarvis"},
    {"id": "vault", "phrases": ("vault", "obsidian"), "desc": "Obsidian PKM + RAG", "src": "super-jarvis"},
    {"id": "oss", "phrases": ("github", "ingest", "open source"), "desc": "Search and ingest GitHub OSS", "src": "super-jarvis"},
    {"id": "meeting", "phrases": ("meeting minutes", "file these notes", "action items", "meeting notes"), "desc": "File meeting minutes + action items to vault/Meetings", "src": "Zackriya-Solutions/meetily"},
]


def catalog() -> list[dict]:
    return [
        {"id": s["id"], "desc": s["desc"], "src": s["src"], "phrases": list(s["phrases"])}
        for s in SKILLS
    ]


def match(text: str) -> dict | None:
    low = (text or "").lower()
    for skill in SKILLS:
        if any(p and p in low for p in skill["phrases"]):
            return {"id": skill["id"], "desc": skill["desc"], "src": skill["src"]}
    return None


def help_text() -> str:
    lines = ["Best of GitHub Jarvis — I can:"]
    for s in SKILLS:
        lines.append(f"- {s['id']}: {s['desc']}")
    lines.append("Say the wake word Jarvis anywhere in a sentence. Live publish still needs a confirm token.")
    return "\n".join(lines)


def greeting() -> str:
    hour = datetime.now().astimezone().hour
    if hour < 5:
        when = "working late"
    elif hour < 12:
        when = "good morning"
    elif hour < 17:
        when = "good afternoon"
    elif hour < 21:
        when = "good evening"
    else:
        when = "good night"
    return f"{when.capitalize()}. J.A.R.V.I.S. online."
