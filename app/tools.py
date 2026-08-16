from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config, github_client, memory
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
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


FUNCTION_TOOLS = [
    _fn(
        "memory_search",
        "Search the unlocked long-term memory for relevant facts, notes, and insights.",
        {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}},
        ["query"],
    ),
    _fn(
        "memory_remember",
        "Persist something important to long-term memory so every future agent can see it.",
        {
            "content": {"type": "string"},
            "kind": {"type": "string", "description": "note|preference|person|project|decision|insight"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number"},
        },
        ["content"],
    ),
    _fn(
        "memory_set_fact",
        "Upsert a durable key/value fact about the owner, projects, people, or preferences.",
        {"key": {"type": "string"}, "value": {"type": "string"}, "confidence": {"type": "number"}},
        ["key", "value"],
    ),
    _fn(
        "fetch_url",
        "Fetch a specific URL and return extracted text. Use after web search when you need the page itself.",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _fn(
        "github",
        "Operate on the owner's authenticated GitHub account.",
        {
            "action": {
                "type": "string",
                "enum": [
                    "whoami",
                    "list_repos",
                    "get_repo",
                    "list_issues",
                    "create_issue",
                    "comment_issue",
                    "list_pulls",
                    "get_file",
                    "search_code",
                    "search_issues",
                    "list_commits",
                    "create_repo",
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
            "name": {"type": "string", "description": "For create_repo"},
            "description": {"type": "string"},
            "private": {"type": "boolean"},
            "visibility": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        ["action"],
    ),
    _fn(
        "spawn_agents",
        "Run specialist agents in parallel against one mission. Use for multi-angle insight.",
        {
            "agents": {
                "type": "array",
                "items": {"type": "string", "enum": [a for a in AGENTS if a != "jarvis"]},
                "description": "1-4 specialists",
            },
            "task": {"type": "string", "description": "Clear mission for every spawned agent"},
        },
        ["agents", "task"],
    ),
]


def tools_for(agent_id: str, *, allow_spawn: bool = False) -> list[dict]:
    agent = AGENTS.get(agent_id) or AGENTS["jarvis"]
    out: list[dict] = []
    for tool in BUILTIN_TOOLS:
        if tool["type"] in agent.builtin_tools or agent_id == "jarvis":
            out.append(tool)
    for fn in FUNCTION_TOOLS:
        if fn["name"] == "spawn_agents" and not (allow_spawn and agent.can_spawn):
            continue
        if fn["name"] == "github" and agent_id not in ("jarvis", "sentinel"):
            continue
        out.append(fn)
    return out


def fetch_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"error": "Only http(s) URLs are allowed."}
    headers = {"User-Agent": "SuperJarvis/1.0 (+local assistant)"}
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
    if name == "fetch_url":
        return fetch_url(arguments.get("url") or "")
    if name == "github":
        action = arguments.get("action")
        payload = {k: v for k, v in arguments.items() if k != "action"}
        try:
            return github_client.dispatch(action, **payload)
        except Exception as exc:
            return {"error": str(exc)}
    if name == "spawn_agents":
        return {"error": "spawn_agents must be handled by the orchestrator"}
    return {"error": f"Unknown tool {name}"}


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)[:24000]
