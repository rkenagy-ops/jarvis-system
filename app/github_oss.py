"""Pull open-source projects and awesome-lists off GitHub into the vault."""

from __future__ import annotations

import re
from typing import Any

import httpx

from . import github_client, obsidian

UA = {"User-Agent": "SuperJarvis/2.3 (+https://github.com/rkenagy-ops/jarvis-system)"}

STARTER_PACK = [
    "public-apis/public-apis",
    "awesome-selfhosted/awesome-selfhosted",
    "vinta/awesome-python",
    "sindresorhus/awesome",
    "microsoft/markitdown",
    "n8n-io/n8n",
    "Stirling-Tools/Stirling-PDF",
    "jellyfin/jellyfin",
    "immich-app/immich",
    "gitroomhq/postiz-app",
    "obsidianmd/obsidian-releases",
    "coddingtonbear/obsidian-local-rest-api",
    "xai-org/xai-sdk-python",
    "xai-org/xai-cookbook",
    "ggerganov/whisper.cpp",
    "rhasspy/piper",
    "BerriAI/litellm",
    "langchain-ai/langchain",
    "run-llama/llama_index",
    "browser-use/browser-use",
    "unclecode/crawl4ai",
    "ytdl-org/youtube-dl",
    "yt-dlp/yt-dlp",
    "huggingface/transformers",
    "huggingface/huggingface_hub",
    "ccxt/ccxt",
    "freqtrade/freqtrade",
    "ranaroussi/yfinance",
    "adbar/trafilatura",
    "jsvine/pdfplumber",
    "explosion/spaCy",
    "numpy/numpy",
    "pandas-dev/pandas",
    "scikit-learn/scikit-learn",
    "streamlit/streamlit",
    "fastapi/fastapi",
    "encode/httpx",
]

BRAIN_PACK = [
    "microsoft/markitdown",
    "adbar/trafilatura",
    "unclecode/crawl4ai",
    "browser-use/browser-use",
    "mem0ai/mem0",
    "lancedb/lancedb",
    "chroma-core/chroma",
    "langchain-ai/langchain",
    "run-llama/llama_index",
    "infiniflow/ragflow",
    "modelcontextprotocol/servers",
    "BerriAI/litellm",
    "xai-org/xai-sdk-python",
    "xai-org/xai-cookbook",
    "huggingface/huggingface_hub",
    "ggerganov/llama.cpp",
    "ollama/ollama",
    "jsvine/pdfplumber",
    "explosion/spaCy",
    "nomic-ai/gpt4all",
]


AWESOME = {
    "public-apis": "public-apis/public-apis",
    "selfhosted": "awesome-selfhosted/awesome-selfhosted",
    "python": "vinta/awesome-python",
    "awesome": "sindresorhus/awesome",
}


def _split(repo: str) -> tuple[str, str]:
    repo = (repo or "").strip().removeprefix("https://github.com/").strip("/")
    if "/" not in repo:
        raise ValueError("Use owner/repo")
    owner, name = repo.split("/", 1)
    return owner, name.split("/")[0]


def search(query: str, limit: int = 10) -> dict:
    return {"query": query, "repos": github_client.search_repos(query, limit)}


def readme(repo: str) -> dict:
    owner, name = _split(repo)
    return github_client.get_readme(owner, name)


DESK_PACK = [
    "Polymarket/py-clob-client",
    "ccxt/ccxt",
    "freqtrade/freqtrade",
    "ranaroussi/yfinance",
    "kernc/backtesting.py",
    "mementum/backtrader",
    "rsheftel/pandas_market_calendars",
    "matplotlib/mplfinance",
    "gitroomhq/postiz-app",
    "n8n-io/n8n",
    "xai-org/xai-sdk-python",
    "modelcontextprotocol/servers",
]


def _ingest_many(repos: list[str], limit: int) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cap = max(1, min(int(limit), len(repos)))
    ingested, errors = [], []
    with ThreadPoolExecutor(max_workers=min(6, cap)) as pool:
        futs = {pool.submit(ingest, repo): repo for repo in repos[:cap]}
        for fut in as_completed(futs):
            repo = futs[fut]
            try:
                ingested.append(fut.result())
            except Exception as exc:
                errors.append({"repo": repo, "error": str(exc)[:200]})
    return {"ingested": ingested, "errors": errors, "count": len(ingested)}


def ingest(repo: str) -> dict:
    owner, name = _split(repo)
    meta = github_client.get_repo(owner, name)
    doc = github_client.get_readme(owner, name)
    body = f"""---
type: source
repo: {owner}/{name}
url: {meta.get('html_url')}
---

# {owner}/{name}

{meta.get('description') or ''}

GitHub: {meta.get('html_url')}

## README

{doc.get('text') or '_no readme_'}
"""
    path = f"Sources/github/{owner}-{name}.md"
    written = obsidian.write_note(path, body)
    return {"ok": True, "vault": written.get("path"), "repo": f"{owner}/{name}", "url": meta.get("html_url")}


JARVIS_PACK = [
    "isair/jarvis",
    "GauravSingh9356/J.A.R.V.I.S",
    "kishanrajput23/Jarvis-Desktop-Voice-Assistant",
    "ethanplusai/jarvis",
    "llm-guy/jarvis",
    "Dipeshpal/Jarvis_AI",
    "gia-guar/JARVIS-ChatGPT",
    "AnubhavChaturvedi-GitHub/jarvis-ai-assistant",
    "Priler/jarvis",
    "swapagarwal/JARVIS-on-Messenger",
    "Gladiator07/JARVIS",
    "AlexandreSajus/JARVIS",
    "Melissa-AI/Melissa-Core",
    "BolisettySujith/J.A.R.V.I.S",
    "akshayaggarwal99/jarvis-ai-assistant",
    "projectswithdigambar/jarvis",
]


def growth_pack(limit: int = 10) -> dict:
    from . import growth

    return growth.pack(limit)


def jarvis_pack(limit: int = 16) -> dict:
    out = _ingest_many(JARVIS_PACK, limit)
    out["pack"] = "jarvis"
    return out


def desk_pack(limit: int = 12) -> dict:
    """Markets + social README ingest. Playbooks, not cloned stacks."""
    out = _ingest_many(DESK_PACK, limit)
    out["pack"] = "desk"
    out["note"] = "READMEs only. No clone, no extra Polymarket accounts, no unofficial social login."
    return out


STACK_PACK = [
    "klaviyo/klaviyo-api-python",
    "gitroomhq/postiz-app",
]


def stack_pack(limit: int = 4) -> dict:
    out = _ingest_many(STACK_PACK, limit)
    out["pack"] = "stack"
    out["note"] = "Official API READMEs. Publer docs are on publer.com/docs (not a GitHub clone)."
    return out


CAPABILITY_PACK = [
    "erdewit/ib_insync",
    "ib-api-reloaded/ib_async",
    "OpenBB-finance/OpenBB",
    "alpacahq/alpaca-py",
    "stripe/stripe-python",
    "twilio/twilio-python",
    "ramnes/notion-sdk-py",
    "SYSTRAN/faster-whisper",
    "yt-dlp/yt-dlp",
    "microsoft/playwright-python",
    "slackapi/python-slack-sdk",
    "praw-dev/praw",
    "pola-rs/polars",
    "python-pillow/Pillow",
    "py-pdf/pypdf",
    "kkroening/ffmpeg-python",
    "duckdb/duckdb",
    "collective/icalendar",
    "home-assistant/core",
    "resend/resend-python",
    "anthropics/claude-code-action",
]


def capability_pack(limit: int = 16) -> dict:
    """Hunt-selected official SDKs. Playbooks for 'handle more of what Rhett throws' — not every repo on GitHub."""
    out = _ingest_many(CAPABILITY_PACK, limit)
    out["pack"] = "capability"
    out["note"] = (
        "READMEs only. Playwright is for opening official dashboards, not hamburger feed-commenting. "
        "IB/Alpaca live still needs confirm_token. She cannot literally do everything."
    )
    return out


SOCIAL_PACK = [
    "InstaPy/InstaPy",
    "GramAddict/bot",
    "vvselijah/Claudegram",
    "instaloader/instaloader",
    "althonos/InstaLooter",
    "subzeroid/instagrapi",
]


def social_pack(limit: int = 8) -> dict:
    """Instagram OSS READMEs. Playbooks only — no unofficial login, no like/follow bots."""
    out = _ingest_many(SOCIAL_PACK, limit)
    out["pack"] = "social"
    out["note"] = (
        "READMEs only. InstaPy/GramAddict/instagrapi are unofficial bots — Jarvis will not log in, "
        "farm follows, or scrape private accounts. Claudegram + Meta Graph API is the official path. "
        "instaloader/instalooter inform public-media playbooks; live IG still goes through content+confirm."
    )
    return out


def brain_pack(limit: int = 10) -> dict:
    out = _ingest_many(BRAIN_PACK, limit)
    out["pack"] = "brain"
    return out


def starter_pack(limit: int = 12) -> dict:
    out = _ingest_many(STARTER_PACK, limit)
    out["pack"] = "starter"
    return out


def awesome(name: str = "public-apis", query: str = "", limit: int = 15) -> dict:
    repo = AWESOME.get((name or "public-apis").lower()) or name
    doc = readme(repo)
    text = doc.get("text") or ""
    rows = []
    q = (query or "").lower()
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| api"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        blob = " ".join(cols).lower()
        if q and q not in blob:
            continue
        rows.append({"name": cols[0], "description": cols[1], "extra": cols[2:]})
        if len(rows) >= limit:
            break
    return {"list": repo, "query": query, "matches": rows, "readme_url": doc.get("html_url")}


def public_api_index(query: str = "", limit: int = 20) -> dict:
    url = "https://public-api-lists.github.io/public-api-lists/api/all.json"
    with httpx.Client(timeout=30.0, headers=UA, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    entries = data if isinstance(data, list) else data.get("entries") or data.get("apis") or []
    q = (query or "").lower()
    hits = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        blob = " ".join(str(item.get(k) or "") for k in ("API", "Name", "name", "Description", "description", "Category", "category", "Link", "url")).lower()
        if q and q not in blob:
            continue
        hits.append(item)
        if len(hits) >= limit:
            break
    return {"source": "public-api-lists", "query": query, "count": len(hits), "results": hits}


def huggingface(query: str, kind: str = "models") -> dict:
    kind = kind if kind in {"models", "datasets", "spaces"} else "models"
    with httpx.Client(timeout=20.0, headers=UA) as client:
        resp = client.get(f"https://huggingface.co/api/{kind}", params={"search": query, "limit": 8})
        resp.raise_for_status()
        data = resp.json()
    out = []
    for row in data[:8]:
        out.append(
            {
                "id": row.get("id") or row.get("modelId"),
                "downloads": row.get("downloads"),
                "likes": row.get("likes"),
                "pipeline": row.get("pipeline_tag"),
                "url": f"https://huggingface.co/{row.get('id') or row.get('modelId')}",
            }
        )
    return {"source": "huggingface", "kind": kind, "results": out}


def youtube_transcript(url: str) -> dict:
    vid = url
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{6,})", url)
    if m:
        vid = m.group(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        rows = YouTubeTranscriptApi.get_transcript(vid)
        text = " ".join(r.get("text") or "" for r in rows)
        return {"source": "youtube", "video": vid, "text": text[:15000]}
    except Exception as exc:
        return {"error": str(exc), "hint": "pip install youtube-transcript-api", "video": vid}


def dispatch(action: str, **kwargs) -> Any:
    if action == "search":
        return search(kwargs.get("query") or kwargs.get("q") or "", int(kwargs.get("limit") or 10))
    if action == "readme":
        return readme(kwargs.get("repo") or "")
    if action == "ingest":
        return ingest(kwargs.get("repo") or "")
    if action in {"starter", "starter_pack"}:
        return starter_pack(int(kwargs.get("limit") or 12))
    if action in {"brain", "brain_pack"}:
        return brain_pack(int(kwargs.get("limit") or 10))
    if action in {"jarvis", "jarvis_pack"}:
        return jarvis_pack(int(kwargs.get("limit") or 16))
    if action in {"desk", "desk_pack"}:
        return desk_pack(int(kwargs.get("limit") or 12))
    if action in {"social", "social_pack", "instagram_pack"}:
        return social_pack(int(kwargs.get("limit") or 8))
    if action in {"stack", "stack_pack", "funnel_pack"}:
        return stack_pack(int(kwargs.get("limit") or 4))
    if action in {"capability", "capability_pack", "anything", "hunt"}:
        return capability_pack(int(kwargs.get("limit") or 16))
    if action in {"growth", "growth_pack"}:
        return growth_pack(int(kwargs.get("limit") or 10))
    if action in {"upgrade", "self_upgrade"}:
        from . import growth

        return growth.cycle(int(kwargs.get("limit") or 6))
    if action == "awesome":
        return awesome(kwargs.get("name") or "public-apis", kwargs.get("query") or "", int(kwargs.get("limit") or 15))
    if action == "public_apis":
        return public_api_index(kwargs.get("query") or "", int(kwargs.get("limit") or 20))
    if action == "huggingface":
        return huggingface(kwargs.get("query") or "", kwargs.get("kind") or "models")
    if action == "youtube":
        return youtube_transcript(kwargs.get("url") or kwargs.get("query") or "")
    return {"error": f"Unknown oss action {action}", "actions": ["search", "readme", "ingest", "starter_pack", "brain_pack", "jarvis_pack", "desk_pack", "social_pack", "stack_pack", "capability_pack", "growth_pack", "self_upgrade", "awesome", "public_apis", "huggingface", "youtube"]}
