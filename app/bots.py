"""Twenty named scheduled bots. Each is an autonomy job with its own interval and task.

None of them drive Instagram hamburger comments or silent IBKR fills.
"""

from __future__ import annotations

from typing import Any

from . import memory

# 20 bots. Names must stay stable so we don't duplicate on restart.
SPECS: list[tuple[str, str, int]] = [
    ("bot-01-briefing", "Write the morning briefing to today's daily note.", 86400),
    ("bot-02-watchlist", "Scan the watchlist for 1.5% movers.", 1800),
    ("bot-03-desk", "Full desk briefing: tape, VIX, MarketBeast, IBKR, Polymarket. ENTER/NO-GO. No live order.", 14400),
    ("bot-04-options", "MarketBeast liquid calls. Write vault/Markets. Do not place IBKR orders.", 3600),
    ("bot-05-poly", "Scan Polymarket public Gamma. Paper Kelly. One account.", 7200),
    ("bot-06-calendar", "Sync Outlook calendar into vault/Calendar and reminders.", 1800),
    ("bot-07-upgrade", "Hunt GitHub OSS. Ingest READMEs. Do not clone stacks.", 21600),
    ("bot-08-backup", "Zip vault and SQLite mind to workspace/backups.", 604800),
    ("bot-09-news", "Pull live feeds and flag headlines that mention watchlist tickers.", 2400),
    ("bot-10-social-draft", "Draft one social caption for X+LinkedIn. Save via content tool. Do not publish.", 43200),
    ("bot-11-blog-draft", "Draft one blog outline into vault/Blog. WordPress draft only if keys work.", 86400),
    ("bot-12-publer", "Check Publer status/accounts if keys exist. Do not publish without confirm.", 21600),
    ("bot-13-klaviyo", "Pull Klaviyo lists/metrics if key exists. Do not send campaigns.", 21600),
    ("bot-14-manychat", "Pull ManyChat page info if token exists. Do not blast subscribers.", 21600),
    ("bot-15-clickfunnels", "Probe ClickFunnels API if key exists. Do not change funnels live.", 21600),
    ("bot-16-wordpress", "Probe WordPress REST. If CF blocks, note paste-in-wp-admin. No silent live posts.", 21600),
    ("bot-17-ibkr-watch", "Probe IBKR TWS. Report port/login. Do not place live orders.", 1800),
    ("bot-18-eval", "Score the latest briefing eval into Memory.", 86400),
    ("bot-19-rag", "Reindex vault embeddings if Ollama embed is up.", 21600),
    ("bot-20-finish", "Write finish checklist snapshot to daily note.", 86400),
    (
        "bot-21-engage",
        "Morning engagement: engage action=run. Comment on 2-5 posts per network. "
        "Auto-posts only on X/Threads/LinkedIn (official reply APIs). Instagram and Facebook "
        "are drafted into the review queue — Meta has no endpoint for commenting on others' posts.",
        86400,
    ),
    (
        "bot-22-learn",
        "Learn from open source: search GitHub for repos filling a capability gap, read the "
        "actual source, ingest it into the vault and reindex the RAG so every agent can "
        "retrieve from it. Skips anything already studied. Never installs what it pulls.",
        43200,
    ),
    (
        "bot-23-gaps",
        "Reconcile tracked capability goals against what is actually installed. Probes each "
        "capability and closes or reopens its goal from the evidence, so a shipped capability "
        "stops being reported as an open gap.",
        21600,
    ),
]


def seed() -> list[dict]:
    have = {j.get("name") for j in memory.list_jobs()}
    seeded = []
    for name, prompt, every in SPECS:
        if name in have:
            continue
        job = memory.add_job(name, prompt, every)
        memory.mark_job(job["id"], "seeded bot — waiting first interval")
        seeded.append(job)
    return seeded


def roster() -> dict[str, Any]:
    jobs = {j.get("name"): j for j in memory.list_jobs()}
    rows = []
    for name, prompt, every in SPECS:
        j = jobs.get(name) or {}
        rows.append(
            {
                "name": name,
                "prompt": prompt,
                "every_sec": every,
                "enabled": j.get("enabled", False) if j else False,
                "seeded": bool(j),
                "last_result": (j.get("last_result") or "")[:160],
            }
        )
    return {"ok": True, "count": len(SPECS), "bots": rows}
