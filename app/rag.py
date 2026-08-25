"""Local vault RAG — chunked notes + FTS. Works without extra API keys."""

from __future__ import annotations

import json
import re
import sqlite3
import threading

from . import config, obsidian

_lock = threading.RLock()
TOKEN = re.compile(r"[a-z0-9]{3,}")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
    with _lock:
        conn = _conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS vault_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                heading TEXT,
                text TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(path, heading, text, content='vault_chunks', content_rowid='id');
            CREATE TRIGGER IF NOT EXISTS vault_chunks_ai AFTER INSERT ON vault_chunks BEGIN
              INSERT INTO vault_fts(rowid, path, heading, text) VALUES (new.id, new.path, new.heading, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS vault_chunks_ad AFTER DELETE ON vault_chunks BEGIN
              INSERT INTO vault_fts(vault_fts, rowid, path, heading, text) VALUES ('delete', old.id, old.path, old.heading, old.text);
            END;
            CREATE TABLE IF NOT EXISTS vault_embed (
                chunk_id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                heading TEXT,
                text TEXT NOT NULL,
                vec TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()


def _chunk(text: str, size: int = 900) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^#{1,3} ", text)
    heads = re.findall(r"(?m)^#{1,3} (.+)$", text)
    chunks: list[tuple[str, str]] = []
    if len(parts) <= 1:
        body = text.strip()
        for i in range(0, max(len(body), 1), size):
            piece = body[i : i + size].strip()
            if piece:
                chunks.append(("", piece))
        return chunks
    # first part is pre-heading
    if parts[0].strip():
        chunks.append(("", parts[0].strip()[:size]))
    for i, body in enumerate(parts[1:]):
        head = heads[i] if i < len(heads) else ""
        body = body.strip()
        for j in range(0, max(len(body), 1), size):
            piece = body[j : j + size].strip()
            if piece:
                chunks.append((head, piece))
    return chunks


def index_note(rel: str, text: str) -> int:
    init()
    rel = rel.replace("\\", "/")
    chunks = _chunk(text)
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM vault_chunks WHERE path=?", (rel,))
        for head, piece in chunks:
            conn.execute("INSERT INTO vault_chunks(path, heading, text) VALUES(?,?,?)", (rel, head, piece))
        conn.commit()
        n = len(chunks)
        conn.close()
    return n


def reindex_vault() -> dict:
    init()
    root = obsidian.vault()
    counted = 0
    files = 0
    for path in root.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        counted += index_note(rel, path.read_text(encoding="utf-8", errors="replace"))
        files += 1
    return {"files": files, "chunks": counted}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_vault(*, limit_files: int = 200) -> dict:
    """Build local vectors via Ollama. No-op if the embed model is missing."""
    init()
    from . import ollama as ol

    try:
        vec = ol.embed("ping")
        if not vec:
            return {"ok": False, "reason": "empty_embed"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:200]}
    n = 0
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM vault_embed")
        rows = conn.execute("SELECT id, path, heading, text FROM vault_chunks LIMIT ?", (limit_files * 8,)).fetchall()
        conn.close()
    conn = _conn()
    try:
        for r in rows:
            try:
                v = ol.embed((r["text"] or "")[:1500])
            except Exception:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO vault_embed(chunk_id, path, heading, text, vec) VALUES(?,?,?,?,?)",
                (r["id"], r["path"], r["heading"], r["text"], json.dumps(v)),
            )
            n += 1
            if n % 25 == 0:
                conn.commit()
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "vectors": n}


def retrieve(query: str, limit: int = 6) -> list[dict]:
    init()
    q = (query or "").strip()
    if not q:
        return []
    tokens = TOKEN.findall(q.lower())
    fts_q = " OR ".join(tokens) if tokens else q
    hits: list[dict] = []
    seen: set[str] = set()
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT path, heading, text FROM vault_fts WHERE vault_fts MATCH ? LIMIT ?",
                (fts_q, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            like = f"%{q}%"
            rows = conn.execute(
                "SELECT path, heading, text FROM vault_chunks WHERE text LIKE ? OR path LIKE ? LIMIT ?",
                (like, like, limit),
            ).fetchall()
        embeds = conn.execute("SELECT path, heading, text, vec FROM vault_embed").fetchall()
        conn.close()
    for r in rows:
        key = f"{r['path']}:{r['heading']}"
        seen.add(key)
        hits.append({"path": r["path"], "heading": r["heading"], "text": (r["text"] or "")[:700], "via": "fts"})
    if embeds:
        try:
            from . import ollama as ol
            import json

            qv = ol.embed(q)
            ranked = []
            for r in embeds:
                try:
                    vv = json.loads(r["vec"])
                except Exception:
                    continue
                ranked.append((_cosine(qv, vv), r))
            ranked.sort(key=lambda x: x[0], reverse=True)
            for score, r in ranked[:limit]:
                key = f"{r['path']}:{r['heading']}"
                if key in seen or score < 0.25:
                    continue
                hits.append(
                    {
                        "path": r["path"],
                        "heading": r["heading"],
                        "text": (r["text"] or "")[:700],
                        "via": "embed",
                        "score": round(score, 3),
                    }
                )
                if len(hits) >= limit + 3:
                    break
        except Exception:
            pass
    return hits[: max(limit, 6)]


def pack(query: str, *, max_chars: int = 3500) -> str:
    hits = retrieve(query, limit=6)
    if not hits:
        return ""
    parts = ["# VAULT RAG"]
    for h in hits:
        head = f" / {h['heading']}" if h.get("heading") else ""
        parts.append(f"## {h['path']}{head}\n{h['text']}")
    text = "\n\n".join(parts)
    return text[:max_chars]
