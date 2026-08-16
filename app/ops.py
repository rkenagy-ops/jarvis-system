"""Content, social, blog, and sales ops. Drafts are free; live publish needs confirm or configured APIs."""

from __future__ import annotations

import html
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from . import config, memory, obsidian

PLATFORMS = ("x", "instagram", "facebook", "linkedin", "tiktok", "youtube", "pinterest", "threads", "blog", "amazon", "email")


def init() -> None:
    with memory._db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body_md TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'post',
                platforms TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                run_at REAL,
                published_at REAL,
                result TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                sku TEXT,
                asin TEXT,
                title TEXT NOT NULL,
                price REAL,
                url TEXT,
                bullets TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at REAL NOT NULL
            );
            """
        )


def md_to_html(md: str) -> str:
    text = md.replace("\r\n", "\n")
    out = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line:
            out.append("")
            continue
        if line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif re.match(r"^\d+\. ", line):
            out.append(f"<li>{_inline(re.sub(r'^\d+\. ', '', line))}</li>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    html_body = "\n".join(out)
    html_body = re.sub(r"(?:<li>.*?</li>\n?)+", lambda m: f"<ul>\n{m.group(0)}</ul>\n", html_body)
    return f"<!DOCTYPE html><html><body>\n{html_body}\n</body></html>"


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def draft(title: str, body_md: str, *, kind: str = "post", platforms: list[str] | None = None) -> dict:
    init()
    now = time.time()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "body_md": body_md,
        "body_html": md_to_html(body_md),
        "kind": kind,
        "platforms": json.dumps(platforms or ["x"]),
        "status": "draft",
        "run_at": None,
        "published_at": None,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    with memory._db() as conn:
        conn.execute(
            """INSERT INTO content(id,title,body_md,body_html,kind,platforms,status,run_at,published_at,result,created_at,updated_at)
               VALUES(:id,:title,:body_md,:body_html,:kind,:platforms,:status,:run_at,:published_at,:result,:created_at,:updated_at)""",
            item,
        )
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "draft"
    folder = {"blog": "Blog", "product": "Shop", "listing": "Shop"}.get(kind, "Content")
    obsidian.write_note(
        f"{folder}/{slug}.md",
        f"---\ntype: {kind}\nplatforms: {item['platforms']}\nstatus: draft\n---\n\n# {title}\n\n{body_md}\n",
    )
    item["platforms"] = platforms or ["x"]
    return item


def schedule(content_id: str, when_iso: str, platforms: list[str] | None = None) -> dict:
    init()
    when = _parse_when(when_iso)
    with memory._db() as conn:
        row = conn.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
        if not row:
            return {"error": "content not found"}
        plats = json.dumps(platforms) if platforms else row["platforms"]
        conn.execute(
            "UPDATE content SET status='scheduled', run_at=?, platforms=?, updated_at=? WHERE id=?",
            (when, plats, time.time(), content_id),
        )
    return {"ok": True, "id": content_id, "run_at": when, "when": datetime.fromtimestamp(when, timezone.utc).isoformat()}


def _parse_when(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return time.time() + 3600
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return time.time() + 3600


def list_content(status: str | None = None, limit: int = 40) -> list[dict]:
    init()
    with memory._db() as conn:
        if status:
            rows = conn.execute("SELECT * FROM content WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM content ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["platforms"] = json.loads(item.get("platforms") or "[]")
        out.append(item)
    return out


def get_content(content_id: str) -> dict | None:
    init()
    with memory._db() as conn:
        row = conn.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["platforms"] = json.loads(item.get("platforms") or "[]")
    return item


def publish(content_id: str, *, confirm_token: str | None = None) -> dict:
    item = get_content(content_id)
    if not item:
        return {"error": "content not found"}
    live_needed = any(p in {"x", "instagram", "facebook", "linkedin", "tiktok", "amazon"} for p in item["platforms"])
    if live_needed and not confirm_token:
        pending = memory.create_pending("publish", {"id": content_id}, ttl_sec=300)
        return {"blocked": True, "reason": "Live social/Amazon publish needs confirm_token.", **pending}
    if confirm_token:
        used = memory.consume_pending(confirm_token)
        if not used:
            return {"error": "Invalid or expired confirm token"}
    results = []
    for platform in item["platforms"]:
        results.append(_push(platform, item))
    now = time.time()
    with memory._db() as conn:
        conn.execute(
            "UPDATE content SET status='published', published_at=?, result=?, updated_at=? WHERE id=?",
            (now, json.dumps(results, default=str), now, content_id),
        )
    return {"ok": True, "id": content_id, "results": results}


def _push(platform: str, item: dict) -> dict:
    if platform == "blog":
        return _wordpress(item) if getattr(config, "WORDPRESS_URL", "") else _local_blog(item)
    if platform == "x":
        return _post_x(item)
    if platform in {"instagram", "facebook", "linkedin", "tiktok", "youtube", "pinterest", "threads"}:
        return _postiz(platform, item)
    if platform == "amazon":
        return {"platform": "amazon", "status": "draft-only", "note": "Listing saved. Connect SP-API for live catalog push."}
    if platform == "email":
        return {"platform": "email", "status": "queued", "note": "Email body stored. Add SMTP to send."}
    return {"platform": platform, "status": "queued-local"}


def _local_blog(item: dict) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", item["title"].lower()).strip("-")[:50]
    obsidian.write_note(f"Blog/{slug}.md", f"---\ntype: blog\nstatus: published\n---\n\n# {item['title']}\n\n{item['body_md']}\n")
    return {"platform": "blog", "status": "published-local", "path": f"Blog/{slug}.md"}


def _wordpress(item: dict) -> dict:
    url = config.WORDPRESS_URL.rstrip("/") + "/wp-json/wp/v2/posts"
    auth = (config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, auth=auth, json={"title": item["title"], "content": item["body_html"], "status": "draft"})
    if resp.status_code >= 400:
        return {"platform": "blog", "error": resp.text[:400]}
    data = resp.json()
    return {"platform": "blog", "status": "wp-draft", "link": data.get("link"), "id": data.get("id")}


def _post_x(item: dict) -> dict:
    token = getattr(config, "X_BEARER_TOKEN", "") or ""
    if not token:
        obsidian.write_note(
            f"Social/x-{item['id'][:8]}.md",
            f"# X draft\n\n{item['body_md'][:280]}\n",
        )
        return {"platform": "x", "status": "draft-vault", "note": "Set X_BEARER_TOKEN to post."}
    text = item["body_md"][:280]
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            "https://api.x.com/2/tweets",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"text": text},
        )
    if resp.status_code >= 400:
        return {"platform": "x", "error": resp.text[:400]}
    return {"platform": "x", "status": "posted", "data": resp.json()}


def _postiz(platform: str, item: dict) -> dict:
    if not config.POSTIZ_URL:
        obsidian.write_note(
            f"Social/{platform}-{item['id'][:8]}.md",
            f"---\nplatform: {platform}\n---\n\n# {item['title']}\n\n{item['body_md']}\n",
        )
        return {"platform": platform, "status": "draft-vault", "note": "Set POSTIZ_URL to auto-queue via Postiz."}
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            config.POSTIZ_URL.rstrip("/") + "/api/public/v1/posts",
            json={"platform": platform, "title": item["title"], "content": item["body_md"]},
        )
    return {"platform": platform, "status": resp.status_code, "body": resp.text[:300]}


def fire_due() -> list[dict]:
    init()
    now = time.time()
    with memory._db() as conn:
        rows = conn.execute("SELECT id FROM content WHERE status='scheduled' AND run_at IS NOT NULL AND run_at<=?", (now,)).fetchall()
    out = []
    for r in rows:
        out.append(publish(r["id"]))
    return out


def add_product(title: str, *, sku: str = "", asin: str = "", price: float | None = None, url: str = "", bullets: list[str] | None = None, description: str = "") -> dict:
    init()
    item = {
        "id": str(uuid.uuid4()),
        "sku": sku,
        "asin": asin,
        "title": title,
        "price": price,
        "url": url or (f"https://www.amazon.com/dp/{asin}" if asin else ""),
        "bullets": json.dumps(bullets or []),
        "description": description,
        "status": "draft",
        "created_at": time.time(),
    }
    with memory._db() as conn:
        conn.execute(
            """INSERT INTO products(id,sku,asin,title,price,url,bullets,description,status,created_at)
               VALUES(:id,:sku,:asin,:title,:price,:url,:bullets,:description,:status,:created_at)""",
            item,
        )
    item["bullets"] = bullets or []
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    bullets_md = "\n".join(f"- {b}" for b in (bullets or []))
    obsidian.write_note(
        f"Shop/{slug}.md",
        f"---\ntype: product\nasin: {asin}\nsku: {sku}\nprice: {price}\n---\n\n# {title}\n\n{description}\n\n{bullets_md}\n\n{item['url']}\n",
    )
    return item


def list_products(limit: int = 40) -> list[dict]:
    init()
    with memory._db() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["bullets"] = json.loads(item.get("bullets") or "[]")
        out.append(item)
    return out


def dashboard() -> dict:
    init()
    return {
        "platforms": list(PLATFORMS),
        "drafts": list_content("draft", 10),
        "scheduled": list_content("scheduled", 10),
        "published": list_content("published", 8),
        "products": list_products(10),
    }


def dispatch(action: str, **kwargs) -> Any:
    if action == "draft":
        plats = kwargs.get("platforms")
        if isinstance(plats, str):
            plats = [p.strip() for p in plats.split(",") if p.strip()]
        return draft(kwargs.get("title") or "Untitled", kwargs.get("body") or kwargs.get("body_md") or "", kind=kwargs.get("kind") or "post", platforms=plats)
    if action == "schedule":
        plats = kwargs.get("platforms")
        if isinstance(plats, str):
            plats = [p.strip() for p in plats.split(",") if p.strip()]
        return schedule(kwargs.get("id") or "", kwargs.get("when") or "", plats)
    if action == "list":
        return list_content(kwargs.get("status"), int(kwargs.get("limit") or 20))
    if action == "get":
        return get_content(kwargs.get("id") or "") or {"error": "not found"}
    if action == "publish":
        return publish(kwargs.get("id") or "", confirm_token=kwargs.get("confirm_token"))
    if action == "html":
        return {"html": md_to_html(kwargs.get("body") or "")}
    if action == "product":
        bullets = kwargs.get("bullets")
        if isinstance(bullets, str):
            bullets = [b.strip() for b in bullets.split(";") if b.strip()]
        return add_product(
            kwargs.get("title") or "Product",
            sku=kwargs.get("sku") or "",
            asin=kwargs.get("asin") or "",
            price=float(kwargs["price"]) if kwargs.get("price") not in (None, "") else None,
            url=kwargs.get("url") or "",
            bullets=bullets,
            description=kwargs.get("description") or "",
        )
    if action == "catalog":
        return list_products(int(kwargs.get("limit") or 20))
    if action == "dashboard":
        return dashboard()
    return {"error": f"Unknown ops action {action}"}
