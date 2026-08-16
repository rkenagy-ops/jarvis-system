"""Adapters for the original GitHub scaffold services — all optional, all local-first."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

from . import config, obsidian

UA = {"User-Agent": "SuperJarvis/2.0 (+https://github.com/rkenagy-ops/jarvis-system)"}


def crawl(url: str, max_pages: int = 5) -> dict:
    from . import guard

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"error": "Only http(s) URLs"}
    if not guard.allow_url(url):
        return {"error": "Blocked private/loopback URL"}
    max_pages = max(1, min(int(max_pages or 5), 8))
    seen: set[str] = set()
    queue = [url]
    pages = []
    host = parsed.netloc
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=UA) as client:
        while queue and len(pages) < max_pages:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            try:
                resp = client.get(current)
            except Exception as exc:
                pages.append({"url": current, "error": str(exc)})
                continue
            html = resp.text
            text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
            text = re.sub(r"(?is)<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            pages.append({"url": str(resp.url), "status": resp.status_code, "text": text[:6000]})
            for href in re.findall(r'href=["\']([^"\']+)["\']', html):
                abs_url = urljoin(current, href).split("#")[0]
                p = urlparse(abs_url)
                if p.netloc == host and p.scheme in {"http", "https"} and abs_url not in seen:
                    queue.append(abs_url)
    return {"seed": url, "pages": pages, "count": len(pages)}


def extract_pdf(path: str) -> dict:
    file = Path(path)
    if not file.is_absolute():
        for base in (config.WORKSPACE_DIR, config.VAULT_DIR):
            candidate = (base / path).resolve()
            if candidate.is_file():
                file = candidate
                break
    root_ok = any(
        file == root or root in file.parents
        for root in (config.WORKSPACE_DIR.resolve(), config.VAULT_DIR.resolve())
    )
    if not file.is_file() or not root_ok:
        return {"error": "PDF must live in workspace/ or vault/"}
    if config.STIRLING_URL:
        try:
            with httpx.Client(timeout=30.0, headers=UA) as client:
                resp = client.post(
                    config.STIRLING_URL.rstrip("/") + "/api/v1/convert/pdf/text",
                    files={"fileInput": (file.name, file.read_bytes(), "application/pdf")},
                )
            if resp.status_code < 400:
                return {"path": str(file), "via": "stirling-pdf", "text": resp.text[:20000]}
        except Exception:
            pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
        return {"path": str(file), "pages": len(reader.pages), "via": "pypdf", "text": text[:20000]}
    except Exception as exc:
        return {"error": f"PDF extract failed: {exc}", "hint": "pip install pypdf or set STIRLING_URL"}


def calendar_add(title: str, when: str, detail: str = "") -> dict:
    obsidian.init_vault()
    rel = f"Calendar/{when[:10]}.md"
    note = f"- [ ] **{title}** — {when}\n  {detail}".rstrip()
    if not (obsidian.vault() / rel).exists():
        obsidian.write_note(rel, f"---\ntype: calendar\ndate: {when[:10]}\n---\n\n# {when[:10]}\n\n")
    obsidian.write_note(rel, note, mode="append")
    events = _events_path()
    rows = json.loads(events.read_text(encoding="utf-8")) if events.exists() else []
    item = {"title": title, "when": when, "detail": detail, "created": datetime.now(timezone.utc).isoformat()}
    rows.append(item)
    events.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return item


def calendar_list(limit: int = 20) -> dict:
    events = _events_path()
    rows = json.loads(events.read_text(encoding="utf-8")) if events.exists() else []
    rows = sorted(rows, key=lambda r: r.get("when") or "")
    return {"events": rows[:limit]}


def _events_path() -> Path:
    obsidian.init_vault()
    return obsidian.vault() / "Calendar" / "events.json"


def n8n_trigger(payload: dict | None = None) -> dict:
    if not config.N8N_WEBHOOK_URL:
        return {"error": "N8N_WEBHOOK_URL is not set", "hint": "Run docker compose and paste a webhook URL"}
    with httpx.Client(timeout=20.0, headers=UA) as client:
        resp = client.post(config.N8N_WEBHOOK_URL, json=payload or {"source": "jarvis"})
    return {"status": resp.status_code, "body": resp.text[:2000]}


def _probe(url: str, headers: dict | None = None) -> dict:
    if not url:
        return {"configured": False}
    try:
        with httpx.Client(timeout=8.0, headers={**UA, **(headers or {})}, follow_redirects=True) as client:
            resp = client.get(url)
        return {"configured": True, "url": url, "status": resp.status_code, "ok": resp.status_code < 500}
    except Exception as exc:
        return {"configured": True, "url": url, "error": str(exc)}


def jellyfin() -> dict:
    if not config.JELLYFIN_URL:
        return {"configured": False, "project": "https://github.com/jellyfin/jellyfin"}
    headers = {}
    if config.JELLYFIN_API_KEY:
        headers["X-Emby-Token"] = config.JELLYFIN_API_KEY
    return _probe(config.JELLYFIN_URL.rstrip("/") + "/System/Info/Public", headers)


def immich() -> dict:
    if not config.IMMICH_URL:
        return {"configured": False, "project": "https://github.com/immich-app/immich"}
    headers = {}
    if config.IMMICH_API_KEY:
        headers["x-api-key"] = config.IMMICH_API_KEY
    return _probe(config.IMMICH_URL.rstrip("/") + "/api/server/ping", headers)


def postiz() -> dict:
    if not config.POSTIZ_URL:
        return {"configured": False, "project": "https://github.com/gitroomhq/postiz-app"}
    return _probe(config.POSTIZ_URL)


def status() -> dict:
    return {
        "obsidian_vault": str(config.VAULT_DIR),
        "obsidian_api": bool(config.OBSIDIAN_API_URL),
        "n8n": bool(config.N8N_WEBHOOK_URL),
        "jellyfin": jellyfin(),
        "immich": immich(),
        "postiz": postiz(),
        "stirling": bool(config.STIRLING_URL),
        "projects": {
            "obsidian": "https://obsidian.md",
            "local_rest_api": "https://github.com/coddingtonbear/obsidian-local-rest-api",
            "n8n": "https://github.com/n8n-io/n8n",
            "stirling_pdf": "https://github.com/Stirling-Tools/Stirling-PDF",
            "jellyfin": "https://github.com/jellyfin/jellyfin",
            "immich": "https://github.com/immich-app/immich",
            "postiz": "https://github.com/gitroomhq/postiz-app",
            "crawl": "same-origin HTTP crawler (crawl4ai-compatible fallback)",
        },
    }


def dispatch(action: str, **kwargs) -> Any:
    if action == "crawl":
        return crawl(kwargs.get("url") or "", int(kwargs.get("max_pages") or 5))
    if action == "pdf":
        return extract_pdf(kwargs.get("path") or "")
    if action == "calendar_add":
        return calendar_add(kwargs.get("title") or "event", kwargs.get("when") or date.today().isoformat(), kwargs.get("detail") or "")
    if action == "calendar_list":
        return calendar_list(int(kwargs.get("limit") or 20))
    if action == "n8n":
        payload = kwargs.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {"text": payload}
        return n8n_trigger(payload)
    if action == "jellyfin":
        return jellyfin()
    if action == "immich":
        return immich()
    if action == "postiz":
        return postiz()
    if action == "status":
        return status()
    return {"error": f"Unknown integrate action {action}"}
