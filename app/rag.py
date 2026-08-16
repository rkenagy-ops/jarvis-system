"""Local vault RAG — chunked notes + FTS. Works without extra API keys."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from . import config, obsidian

_lock = threading.RLock()
TOKEN = re.compile(r"[a-z0-9]{3,}")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
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


def retrieve(query: str, limit: int = 6) -> list[dict]:
    init()
    q = (query or "").strip()
    if not q:
        return []
    hits: list[dict] = []
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT path, heading, text FROM vault_fts WHERE vault_fts MATCH ? LIMIT ?",
                (q, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            like = f"%{q}%"
            rows = conn.execute(
                "SELECT path, heading, text FROM vault_chunks WHERE text LIKE ? OR path LIKE ? LIMIT ?",
                (like, like, limit),
            ).fetchall()
        conn.close()
    for r in rows:
        hits.append({"path": r["path"], "heading": r["heading"], "text": (r["text"] or "")[:700]})
    return hits


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
