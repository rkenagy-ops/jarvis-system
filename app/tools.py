from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from . import catalog, config, github_client, github_oss, markets, memory, obsidian, opensource, ops, widgets, workspace
from .agents import AGENTS

BUILTIN_TOOLS = [
    {"type": "web_search", "enable_image_understanding": True, "enable_image_search": True},
    {"type": "x_search", "enable_image_understanding": True, "enable_video_understanding": True},
    {"type": "code_interpreter"},
]


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []},
    }


FUNCTION_TOOLS = [
    _fn("memory_search", "Search long-term memory.", {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    _fn(
        "memory_remember",
        "Persist something so every future agent can see it.",
        {
            "content": {"type": "string"},
            "kind": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number"},
        },
        ["content"],
    ),
    _fn("memory_set_fact", "Upsert a durable key/value fact.", {"key": {"type": "string"}, "value": {"type": "string"}, "confidence": {"type": "number"}}, ["key", "value"]),
    _fn("skill_learn", "Add or update a reusable playbook in the growing skill library.", {"name": {"type": "string"}, "playbook": {"type": "string"}}, ["name", "playbook"]),
    _fn("goal_add", "Track an open mission.", {"title": {"type": "string"}, "detail": {"type": "string"}, "priority": {"type": "number"}}, ["title"]),
    _fn("goal_update", "Update a goal status: open|done|blocked.", {"id": {"type": "string"}, "status": {"type": "string"}}, ["id", "status"]),
    _fn(
        "schedule_job",
        "Run a prompt on a timer (autonomy). every_sec is interval.",
        {"name": {"type": "string"}, "prompt": {"type": "string"}, "every_sec": {"type": "integer"}},
        ["name", "prompt"],
    ),
    _fn("fetch_url", "Fetch a URL and extract text.", {"url": {"type": "string"}}, ["url"]),
    _fn("wiki", "Wikipedia summary.", {"query": {"type": "string"}}, ["query"]),
    _fn("news_headlines", "Read an RSS feed (default BBC) or the live multi-source feed if feed=live.", {"feed": {"type": "string"}}),
    _fn(
        "feeds",
        "Live Yahoo Finance quotes plus BBC/NPR/Yahoo/HN headlines. Cached ~20s.",
        {"force": {"type": "boolean"}},
    ),
    _fn("weather", "Current weather via Open-Meteo.", {"lat": {"type": "number"}, "lon": {"type": "number"}, "place": {"type": "string"}}),
    _fn("calc", "Exact arithmetic.", {"expression": {"type": "string"}}, ["expression"]),
    _fn("now", "Current UTC time.", {}),
    _fn(
        "workspace",
        "Sandboxed files in ./workspace. Actions: list, read, write, analyze, find.",
        {"action": {"type": "string", "enum": ["list", "read", "write", "analyze", "find"]}, "path": {"type": "string"}, "content": {"type": "string"}, "query": {"type": "string"}},
        ["action"],
    ),
    _fn(
        "market",
        "Markets: quote, history, analyze, watchlist, scan, intel, advise, ticket, account, broker, trade, confirm, ibkr, options, poly. Advise = ENTER/NO-GO breakdown. poly = Polymarket public Gamma scan/bounce (one book, paper Kelly, no extra accounts, no wallet keys). IBKR live still needs confirm_token.",
        {
            "action": {"type": "string", "enum": ["quote", "history", "analyze", "watchlist", "scan", "intel", "advise", "ticket", "account", "broker", "trade", "confirm", "ibkr", "options", "poly"]},
            "universe": {"type": "string"},
            "symbol": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "qty": {"type": "number"},
            "range": {"type": "string"},
            "symbols": {"type": "string"},
            "confirm_token": {"type": "string"},
            "universe": {"type": "string"},
            "dte": {"type": "integer"},
            "expiry": {"type": "string"},
            "strike": {"type": "number"},
            "right": {"type": "string"},
            "top": {"type": "integer"},
            "mode": {"type": "string"},
            "limit": {"type": "number"},
        },
        ["action"],
    ),
    _fn(
        "obsidian",
        "Obsidian vault (local markdown PKM). Actions: list, read, write, append, search, daily, backlinks, capture, tasks, toggle_task, playbooks.",
        {
            "action": {"type": "string", "enum": ["list", "read", "write", "append", "search", "daily", "backlinks", "capture", "tasks", "toggle_task", "playbooks"]},
            "line": {"type": "integer"},
            "done": {"type": "boolean"},
            "open_only": {"type": "boolean"},
            "path": {"type": "string"},
            "content": {"type": "string"},
            "query": {"type": "string"},
            "date": {"type": "string"},
            "kind": {"type": "string"},
            "mode": {"type": "string"},
            "limit": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        ["action"],
    ),
    _fn(
        "integrate",
        "Open-source adapters from the GitHub scaffold: crawl, pdf, calendar_add, calendar_list, n8n, jellyfin, immich, postiz, status.",
        {
            "action": {
                "type": "string",
                "enum": ["crawl", "pdf", "calendar_add", "calendar_list", "n8n", "jellyfin", "immich", "postiz", "status"],
            },
            "url": {"type": "string"},
            "path": {"type": "string"},
            "title": {"type": "string"},
            "when": {"type": "string"},
            "detail": {"type": "string"},
            "payload": {"type": "string"},
            "max_pages": {"type": "integer"},
        },
        ["action"],
    ),
    _fn(
        "github",
        "Operate on the owner's GitHub account (rkenagy-ops).",
        {
            "action": {
                "type": "string",
                "enum": [
                    "whoami", "list_repos", "get_repo", "list_issues", "create_issue", "comment_issue",
                    "list_pulls", "get_file", "search_code", "search_issues", "list_commits", "create_repo",
                    "search_repos", "readme",
                ],
            },
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "path": {"type": "string"},
            "ref": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "number": {"type": "integer"},
            "query": {"type": "string"},
            "state": {"type": "string"},
            "limit": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "private": {"type": "boolean"},
            "visibility": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        ["action"],
    ),
    _fn(
        "spawn_agents",
        "Run specialist agents in parallel.",
        {
            "agents": {"type": "array", "items": {"type": "string", "enum": [a for a in AGENTS if a != "jarvis"]}},
            "task": {"type": "string"},
        },
        ["agents", "task"],
    ),
    _fn(
        "imagine",
        "Generate an image with Grok Imagine and save it under workspace/images plus a vault Sources note.",
        {"prompt": {"type": "string"}, "filename": {"type": "string"}},
        ["prompt"],
    ),
    _fn(
        "catalog",
        "Call a free/open public API. Sources: " + ", ".join(catalog.SOURCES),
        {
            "source": {"type": "string", "enum": list(catalog.SOURCES)},
            "query": {"type": "string", "description": "Search term, URL, symbol, CVE, domain, or country code"},
        },
        ["source"],
    ),
    _fn(
        "vault_rag",
        "Semantic/FTS retrieval over the Obsidian vault chunks. Use before answering questions about prior notes, people, or projects.",
        {"query": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    _fn(
        "desktop",
        "PC/room assistant: open URL/app, YouTube, maps, google, notify, sysinfo, screenshot, clipboard, joke, note, remind, timer, find, plan_day, email_draft, situation, skills.",
        {
            "action": {
                "type": "string",
                "enum": [
                    "open", "app", "youtube", "maps", "google", "notify", "sysinfo",
                    "email_draft", "email_send", "screenshot", "clipboard", "joke", "note", "remind",
                    "timer", "find", "plan_day", "skills", "situation", "vault", "daily", "calendar_sync",
                    "claude_app",
                ],
            },
            "url": {"type": "string"},
            "app": {"type": "string"},
            "query": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "when": {"type": "string"},
            "minutes": {"type": "integer"},
            "mode": {"type": "string"},
            "name": {"type": "string"},
        },
        ["action"],
    ),
    _fn(
        "meeting",
        "File meeting minutes (Meetily's job, our vault). Actions: file, list. Paste a transcript or notes; extracts decisions and action items into vault/Meetings/.",
        {
            "action": {"type": "string", "enum": ["file", "list"]},
            "title": {"type": "string"},
            "transcript": {"type": "string"},
            "notes": {"type": "string"},
            "attendees": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["action"],
    ),
    _fn(
        "extract",
        "Ingest a URL or local file into the vault as markdown (trafilatura/Jina/markitdown/pypdf).",
        {"action": {"type": "string", "enum": ["url", "file"]}, "url": {"type": "string"}, "path": {"type": "string"}},
        ["action"],
    ),
    _fn(
        "content",
        "Content studio: draft/schedule/list/get/publish rich-text posts, blogs, social, Amazon listings. Also product/catalog/dashboard/html.",
        {
            "action": {
                "type": "string",
                "enum": ["draft", "schedule", "list", "get", "publish", "html", "product", "catalog", "dashboard"],
            },
            "title": {"type": "string"},
            "body": {"type": "string"},
            "kind": {"type": "string", "description": "post|blog|caption|email|listing"},
            "platforms": {"type": "string", "description": "comma list: x,instagram,linkedin,tiktok,youtube,facebook,pinterest,threads,blog,amazon,email"},
            "id": {"type": "string"},
            "when": {"type": "string", "description": "ISO datetime"},
            "confirm_token": {"type": "string"},
            "status": {"type": "string"},
            "sku": {"type": "string"},
            "asin": {"type": "string"},
            "price": {"type": "number"},
            "url": {"type": "string"},
            "bullets": {"type": "string"},
            "description": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["action"],
    ),
    _fn(
        "oss",
        "Pull open-source from GitHub: search, readme, ingest, starter_pack, brain_pack (RAG/memory/LLM repos), awesome, public_apis, huggingface, youtube.",
        {
            "action": {
                "type": "string",
                "enum": ["search", "readme", "ingest", "starter_pack", "brain_pack", "jarvis_pack", "desk_pack", "social_pack", "stack_pack", "capability_pack", "growth_pack", "self_upgrade", "awesome", "public_apis", "huggingface", "youtube"],
            },
            "query": {"type": "string"},
            "repo": {"type": "string", "description": "owner/repo"},
            "name": {"type": "string", "description": "awesome list key: public-apis|selfhosted|python|awesome"},
            "url": {"type": "string"},
            "limit": {"type": "integer"},
            "kind": {"type": "string"},
        },
        ["action"],
    ),
    _fn(
        "stack",
        (
            "Official growth stack: Publer, Klaviyo, ManyChat, ClickFunnels, dashboards, bots. "
            "action=comment automates the follow-up ('first') comment on a post YOU publish via the "
            "Publer API - it needs account_id + text + comment. Live schedule/publish/comment needs "
            "confirm_token. Still refuses hamburger account-switching, feed-comment farming, and "
            "commenting on other people's posts."
        ),
        {
            "action": {
                "type": "string",
                "enum": [
                    "status", "dashboards", "bots",
                    "publer", "accounts", "schedule", "job_status",
                    "klaviyo", "manychat", "clickfunnels",
                    "comment", "hamburger",
                ],
            },
            "mode": {"type": "string"},
            "text": {"type": "string"},
            "body": {"type": "string"},
            "account_id": {"type": "string"},
            "network": {"type": "string"},
            "platform": {"type": "string"},
            "when": {"type": "string"},
            "confirm_token": {"type": "string"},
            "comment": {
                "type": "string",
                "description": "Follow-up/first comment posted on your own post after it publishes.",
            },
            "comments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Several follow-up comments, in order.",
            },
            "comment_delay": {
                "type": "integer",
                "description": "Minutes to wait after the post publishes before the follow-up comment.",
            },
            "job_id": {"type": "string", "description": "Publer job id returned by schedule/publish."},
        },
        ["action"],
    ),
    _fn(
        "oss",
        (
            "Unrestricted open-source access: fetch, read, grep, vendor or ingest ANY public "
            "GitHub repo - no allowlist, no curated pack, real source rather than just the README. "
            "install runs pip on a fetched repo and takes a confirm_token."
        ),
        {
            "action": {
                "type": "string",
                "enum": ["status", "search", "fetch", "tree", "read", "grep", "vendor", "ingest", "install"],
            },
            "repo": {"type": "string", "description": "owner/name of any public repo."},
            "query": {"type": "string", "description": "search terms for action=search."},
            "pattern": {"type": "string", "description": "regex for action=grep."},
            "path": {"type": "string", "description": "file path inside the repo for action=read."},
            "subdir": {"type": "string"},
            "glob": {"type": "string"},
            "ref": {"type": "string", "description": "branch/tag/sha. Defaults to the default branch."},
            "package": {"type": "string", "description": "pip package name for action=install."},
            "force": {"type": "boolean", "description": "re-download even if already fetched."},
            "limit": {"type": "integer"},
            "max_files": {"type": "integer"},
            "confirm_token": {"type": "string"},
        },
        ["action"],
    ),
    _fn(
        "engage",
        (
            "Morning engagement run: find worthwhile posts and comment on them. Auto-posts only where "
            "the network has an official reply API (X, Threads, LinkedIn-if-granted). Instagram and "
            "Facebook have no such endpoint, so those are drafted into a review queue instead."
        ),
        {
            "action": {
                "type": "string",
                "enum": ["status", "run", "draft", "queue", "done"],
            },
            "networks": {
                "type": "string",
                "description": "Comma separated: x,threads,linkedin,instagram,facebook. Default all.",
            },
            "per_network": {"type": "integer", "description": "How many posts per network (1-5)."},
            "topics": {"type": "string", "description": "Comma separated topics/hashtags for discovery."},
            "dry_run": {"type": "boolean", "description": "Draft everything, post nothing."},
            "post_id": {"type": "string"},
            "network": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["action"],
    ),
]

_GITHUB_AGENTS = {"jarvis", "sentinel", "scout"}
_FILE_AGENTS = {"jarvis", "forge", "analyst", "archivist", "steward"}
_MARKET_AGENTS = {"jarvis", "trader", "oracle", "analyst", "watcher"}
_STACK_AGENTS = {"jarvis", "social", "merch", "publisher", "scheduler", "trader", "steward"}


def tools_for(agent_id: str, *, allow_spawn: bool = False) -> list[dict]:
    agent = AGENTS.get(agent_id) or AGENTS["jarvis"]
    out: list[dict] = []
    for tool in BUILTIN_TOOLS:
        if tool["type"] in agent.builtin_tools or agent_id == "jarvis":
            out.append(tool)
    for fn in FUNCTION_TOOLS:
        name = fn["name"]
        if name == "spawn_agents" and not (allow_spawn and agent.can_spawn):
            continue
        if name == "github" and agent_id not in _GITHUB_AGENTS:
            continue
        if name == "market" and agent_id not in _MARKET_AGENTS:
            continue
        if name == "stack" and agent_id not in _STACK_AGENTS:
            continue
        if name == "engage" and agent_id not in _STACK_AGENTS:
            continue
        if name == "workspace" and agent_id not in _FILE_AGENTS:
            continue
        if name == "obsidian" and agent_id not in {"jarvis", "archivist", "strategist", "analyst", "trader", "scribe", "publisher"}:
            continue
        if name == "content" and agent_id not in {
            "jarvis", "scribe", "social", "merch", "publisher", "scheduler", "designer", "strategist",
        }:
            continue
        out.append(fn)
    return out


def fetch_url(url: str) -> dict:
    from . import guard

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"error": "Only http(s) URLs are allowed."}
    if not guard.allow_url(url):
        return {"error": "Blocked private/loopback URL"}
    try:
        resp = guard.fetch_public(url, headers={"User-Agent": "SuperJarvis/3.1 (+local assistant)"})
    except Exception as exc:
        return {"error": str(exc)}
    text = resp.text
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"url": str(resp.url), "status": resp.status_code, "text": text[:12000]}


def execute(name: str, arguments: dict[str, Any], *, session_id: str, agent_id: str) -> Any:
    if name == "memory_search":
        return memory.search(arguments.get("query") or "", limit=int(arguments.get("limit") or 10))
    if name == "memory_remember":
        return memory.remember(
            arguments.get("content") or "",
            kind=arguments.get("kind") or "note",
            tags=arguments.get("tags") or [],
            importance=float(arguments.get("importance") or 0.6),
            source_agent=agent_id,
        )
    if name == "memory_set_fact":
        return memory.set_fact(
            arguments.get("key") or "",
            arguments.get("value") or "",
            confidence=float(arguments.get("confidence") or 0.85),
            source_agent=agent_id,
        )
    if name == "skill_learn":
        return memory.upsert_skill(arguments.get("name") or "", arguments.get("playbook") or "")
    if name == "goal_add":
        return memory.add_goal(arguments.get("title") or "", arguments.get("detail") or "", float(arguments.get("priority") or 0.5))
    if name == "goal_update":
        ok = memory.update_goal(arguments.get("id") or "", arguments.get("status") or "open")
        return {"ok": ok}
    if name == "schedule_job":
        return memory.add_job(arguments.get("name") or "job", arguments.get("prompt") or "", int(arguments.get("every_sec") or 1800))
    if name == "fetch_url":
        return fetch_url(arguments.get("url") or "")
    if name == "wiki":
        return widgets.wiki(arguments.get("query") or "")
    if name == "news_headlines":
        feed = arguments.get("feed") or "https://feeds.bbci.co.uk/news/rss.xml"
        if str(feed).lower() in {"live", "feeds", "all"}:
            from . import feeds as feeds_mod

            return {"items": feeds_mod.snapshot().get("news") or []}
        return widgets.news(feed)
    if name == "feeds":
        from . import feeds as feeds_mod

        return feeds_mod.snapshot(force=bool(arguments.get("force")))
    if name == "weather":
        return widgets.dispatch("weather", **arguments)
    if name == "calc":
        return widgets.calc(arguments.get("expression") or "0")
    if name == "now":
        return widgets.now()
    if name == "workspace":
        return workspace.dispatch(arguments.get("action") or "list", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "obsidian":
        return obsidian.dispatch(arguments.get("action") or "list", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "integrate":
        return opensource.dispatch(arguments.get("action") or "status", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "imagine":
        from . import xai as xai_mod

        return xai_mod.imagine(arguments.get("prompt") or "", filename=arguments.get("filename"))
    if name == "catalog":
        return catalog.call(arguments.get("source") or "", arguments.get("query") or "")
    if name == "oss":
        return github_oss.dispatch(arguments.get("action") or "search", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "desktop":
        from . import desktop as desktop_mod

        return desktop_mod.dispatch(arguments.get("action") or "situation", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "meeting":
        from . import meetings as meetings_mod

        return meetings_mod.dispatch(arguments.get("action") or "file", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "extract":
        from . import extract as extract_mod

        return extract_mod.dispatch(arguments.get("action") or "url", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "content":
        return ops.dispatch(arguments.get("action") or "dashboard", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "oss":
        from . import oss as oss_mod

        return oss_mod.dispatch(
            arguments.get("action") or "status",
            **{k: v for k, v in arguments.items() if k != "action"},
        )
    if name == "engage":
        from . import engage as engage_mod

        return engage_mod.dispatch(
            arguments.get("action") or "status",
            **{k: v for k, v in arguments.items() if k != "action"},
        )
    if name == "stack":
        from . import bots, stack

        act = arguments.get("action") or "status"
        if act == "bots":
            return bots.roster()
        return stack.dispatch(act, **{k: v for k, v in arguments.items() if k != "action"})
    if name == "vault_rag":
        from . import rag as rag_mod

        return {"hits": rag_mod.retrieve(arguments.get("query") or "", int(arguments.get("limit") or 6))}
    if name == "market":
        return markets.dispatch(arguments.get("action") or "quote", **{k: v for k, v in arguments.items() if k != "action"})
    if name == "github":
        try:
            return github_client.dispatch(arguments.get("action"), **{k: v for k, v in arguments.items() if k != "action"})
        except Exception as exc:
            return {"error": str(exc)}
    if name == "spawn_agents":
        return {"error": "spawn_agents must be handled by the orchestrator"}
    return {"error": f"Unknown tool {name}"}


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)[:24000]
