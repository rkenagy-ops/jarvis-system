from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config, github_client, markets, memory, widgets, workspace
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
    _fn("news_headlines", "Read an RSS feed (default BBC).", {"feed": {"type": "string"}}),
    _fn("weather", "Current weather via Open-Meteo.", {"lat": {"type": "number"}, "lon": {"type": "number"}, "place": {"type": "string"}}),
    _fn("calc", "Exact arithmetic.", {"expression": {"type": "string"}}, ["expression"]),
    _fn("now", "Current UTC time.", {}),
    _fn(
        "workspace",
        "Sandboxed files in ./workspace. Actions: list, read, write, analyze.",
        {"action": {"type": "string", "enum": ["list", "read", "write", "analyze"]}, "path": {"type": "string"}, "content": {"type": "string"}},
        ["action"],
    ),
    _fn(
        "market",
        "Stocks/crypto: quote, history, analyze (RSI/SMA/MACD/vol), watchlist, account, trade, confirm.",
        {
            "action": {"type": "string", "enum": ["quote", "history", "analyze", "watchlist", "account", "trade", "confirm"]},
            "symbol": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "qty": {"type": "number"},
            "range": {"type": "string"},
            "symbols": {"type": "string"},
            "confirm_token": {"type": "string"},
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
]

_MARKET_AGENTS = {"jarvis", "trader", "oracle", "analyst"}
_GITHUB_AGENTS = {"jarvis", "sentinel"}
_FILE_AGENTS = {"jarvis", "forge", "analyst", "archivist"}


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
        if name == "workspace" and agent_id not in _FILE_AGENTS:
            continue
        out.append(fn)
    return out


def fetch_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"error": "Only http(s) URLs are allowed."}
    headers = {"User-Agent": "SuperJarvis/1.2 (+local assistant)"}
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
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
        return widgets.news(arguments.get("feed") or "https://feeds.bbci.co.uk/news/rss.xml")
    if name == "weather":
        return widgets.dispatch("weather", **arguments)
    if name == "calc":
        return widgets.calc(arguments.get("expression") or "0")
    if name == "now":
        return widgets.now()
    if name == "workspace":
        return workspace.dispatch(arguments.get("action") or "list", **{k: v for k, v in arguments.items() if k != "action"})
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
