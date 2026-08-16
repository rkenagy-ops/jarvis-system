"""Ingest URLs and files into the vault using OSS extractors."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import catalog, config, obsidian, opensource


def from_url(url: str) -> dict:
    text = ""
    via = ""
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) or ""
        via = "trafilatura"
    except Exception:
        pass
    if not text:
        j = catalog.call("jina", url)
        text = j.get("text") or ""
        via = "jina"
    if not text:
        crawled = opensource.crawl(url, max_pages=1)
        pages = crawled.get("pages") or []
        text = (pages[0].get("text") if pages else "") or ""
        via = "crawl"
    if not text:
        return {"error": "Could not extract", "url": url}
    title = (text.split("\n", 1)[0] or "source")[:80]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    path = f"Sources/web/{slug}.md"
    obsidian.write_note(path, f"---\ntype: source\nurl: {url}\nvia: {via}\n---\n\n# {title}\n\n{text[:12000]}\n")
    return {"ok": True, "path": path, "via": via, "chars": len(text)}


def from_file(rel: str) -> dict:
    path = Path(rel)
    if not path.is_absolute():
        for base in (config.WORKSPACE_DIR, config.VAULT_DIR):
            cand = (base / rel).resolve()
            if cand.is_file():
                path = cand
                break
    if not path.is_file():
        return {"error": "file not found"}
    text = ""
    via = ""
    try:
        from markitdown import MarkItDown

        text = MarkItDown().convert(str(path)).text_content or ""
        via = "markitdown"
    except Exception:
        pass
    if not text and path.suffix.lower() == ".pdf":
        pdf = opensource.extract_pdf(str(path))
        text = pdf.get("text") or ""
        via = pdf.get("via") or "pdf"
    if not text:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            via = "text"
        except Exception as exc:
            return {"error": str(exc)}
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[:50]
    dest = f"Sources/files/{slug}.md"
    obsidian.write_note(dest, f"---\ntype: file\nsource: {path.name}\nvia: {via}\n---\n\n# {path.name}\n\n{text[:15000]}\n")
    return {"ok": True, "path": dest, "via": via, "chars": len(text)}


def dispatch(action: str, **kwargs) -> Any:
    if action == "url":
        return from_url(kwargs.get("url") or "")
    if action == "file":
        return from_file(kwargs.get("path") or "")
    return {"error": "url or file"}
