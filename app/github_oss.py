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


def starter_pack(limit: int = 12) -> dict:
    ingested = []
    errors = []
    for repo in STARTER_PACK[: max(1, min(int(limit), len(STARTER_PACK)))]:
        try:
            ingested.append(ingest(repo))
        except Exception as exc:
            errors.append({"repo": repo, "error": str(exc)})
    return {"ingested": ingested, "errors": errors, "count": len(ingested)}


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
    if action == "awesome":
        return awesome(kwargs.get("name") or "public-apis", kwargs.get("query") or "", int(kwargs.get("limit") or 15))
    if action == "public_apis":
        return public_api_index(kwargs.get("query") or "", int(kwargs.get("limit") or 20))
    if action == "huggingface":
        return huggingface(kwargs.get("query") or "", kwargs.get("kind") or "models")
    if action == "youtube":
        return youtube_transcript(kwargs.get("url") or kwargs.get("query") or "")
    return {"error": f"Unknown oss action {action}", "actions": ["search", "readme", "ingest", "starter_pack", "awesome", "public_apis", "huggingface", "youtube"]}
