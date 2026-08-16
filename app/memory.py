from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterable

from . import config
from .config import DB_PATH

_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def _db() -> Iterable[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0.5,
                source_agent TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                last_used REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.8,
                source_agent TEXT,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                agent TEXT NOT NULL,
                claim TEXT NOT NULL,
                evidence TEXT,
                confidence REAL NOT NULL DEFAULT 0.7,
                created_at REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content, tags, kind, source_agent, content='memories', content_rowid='rowid'
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_insights_session ON insights(session_id, created_at);
            """
        )
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
              INSERT INTO memory_fts(rowid, content, tags, kind, source_agent)
              VALUES (new.rowid, new.content, new.tags, new.kind, COALESCE(new.source_agent, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
              INSERT INTO memory_fts(memory_fts, rowid, content, tags, kind, source_agent)
              VALUES ('delete', old.rowid, old.content, old.tags, old.kind, COALESCE(old.source_agent, ''));
            END;
            """
        )
        if not conn.execute("SELECT 1 FROM facts LIMIT 1").fetchone():
            conn.execute(
                "INSERT INTO facts(key, value, confidence, source_agent, updated_at) VALUES(?,?,?,?,?)",
                ("owner.name", config.OWNER_NAME, 0.99, "system", time.time()),
            )


def remember(
    content: str,
    *,
    kind: str = "note",
    tags: list[str] | None = None,
    importance: float = 0.6,
    source_agent: str | None = None,
    metadata: dict | None = None,
) -> dict:
    now = time.time()
    item = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "content": content.strip(),
        "tags": json.dumps(tags or []),
        "importance": max(0.0, min(1.0, importance)),
        "source_agent": source_agent,
        "metadata": json.dumps(metadata or {}),
        "created_at": now,
        "last_used": now,
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO memories (id, kind, content, tags, importance, source_agent, metadata, created_at, last_used)
               VALUES (:id, :kind, :content, :tags, :importance, :source_agent, :metadata, :created_at, :last_used)""",
            item,
        )
    item["tags"] = tags or []
    item["metadata"] = metadata or {}
    return item


def set_fact(key: str, value: str, *, confidence: float = 0.85, source_agent: str | None = None) -> dict:
    now = time.time()
    with _db() as conn:
        conn.execute(
            """INSERT INTO facts(key, value, confidence, source_agent, updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, confidence=excluded.confidence,
               source_agent=excluded.source_agent, updated_at=excluded.updated_at""",
            (key.strip(), value.strip(), confidence, source_agent, now),
        )
    return {"key": key, "value": value, "confidence": confidence}


def get_facts() -> list[dict]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM facts ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def search(query: str, *, limit: int = 12) -> list[dict]:
    query = (query or "").strip()
    with _db() as conn:
        if query:
            try:
                rows = conn.execute(
                    """SELECT m.* FROM memories m
                       JOIN memory_fts f ON f.rowid = m.rowid
                       WHERE memory_fts MATCH ?
                       ORDER BY m.importance DESC, m.last_used DESC LIMIT ?""",
                    (query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                like = f"%{query}%"
                rows = conn.execute(
                    """SELECT * FROM memories
                       WHERE content LIKE ? OR tags LIKE ? OR kind LIKE ?
                       ORDER BY importance DESC, last_used DESC LIMIT ?""",
                    (like, like, like, limit),
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY importance DESC, last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE memories SET last_used=? WHERE id=?",
                [(time.time(), i) for i in ids],
            )
    out = []
    for r in rows:
        item = dict(r)
        item["tags"] = json.loads(item.get("tags") or "[]")
        item["metadata"] = json.loads(item.get("metadata") or "{}")
        out.append(item)
    return out


def add_message(session_id: str, role: str, content: str, agent: str | None = None) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages(id, session_id, role, content, agent, created_at) VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, role, content, agent, time.time()),
        )


def recent_messages(session_id: str, limit: int = 24) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def add_insight(
    agent: str,
    claim: str,
    *,
    session_id: str | None = None,
    evidence: str | None = None,
    confidence: float = 0.7,
) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "agent": agent,
        "claim": claim,
        "evidence": evidence,
        "confidence": confidence,
        "created_at": time.time(),
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO insights(id, session_id, agent, claim, evidence, confidence, created_at)
               VALUES(:id,:session_id,:agent,:claim,:evidence,:confidence,:created_at)""",
            item,
        )
    remember(
        f"[{agent}] {claim}",
        kind="insight",
        tags=["insight", agent],
        importance=min(1.0, 0.5 + confidence / 2),
        source_agent=agent,
        metadata={"evidence": evidence or ""},
    )
    return item


def recent_insights(session_id: str | None = None, limit: int = 20) -> list[dict]:
    with _db() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM insights WHERE session_id=? OR session_id IS NULL ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM insights ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def forget(memory_id: str) -> bool:
    with _db() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return cur.rowcount > 0


def snapshot(session_id: str, *, max_chars: int = 18000) -> str:
    """Unlocked shared mind: every agent sees the same facts, memories, insights."""
    facts = get_facts()
    mems = search("", limit=40)
    insights = recent_insights(session_id, limit=16)
    history = recent_messages(session_id, limit=18)
    parts = ["# SHARED MIND — full unlocked memory (all agents read this)"]
    if facts:
        parts.append("## Durable facts")
        for f in facts[:80]:
            parts.append(f"- {f['key']}: {f['value']} (conf {f['confidence']:.2f})")
    if mems:
        parts.append("## Long-term memories")
        for m in mems:
            parts.append(f"- [{m['kind']}/{m.get('source_agent') or 'jarvis'}] {m['content']}")
    if insights:
        parts.append("## Recent agent insights")
        for i in insights:
            parts.append(f"- {i['agent']}: {i['claim']}")
    if history:
        parts.append("## Session transcript")
        for msg in history:
            agent = f"/{msg['agent']}" if msg.get("agent") else ""
            parts.append(f"- {msg['role']}{agent}: {msg['content'][:800]}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n...[truncated]"
    return text


def dashboard() -> dict[str, Any]:
    with _db() as conn:
        mem_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        fact_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        insight_count = conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(DISTINCT session_id) FROM messages").fetchone()[0]
    return {
        "memories": mem_count,
        "facts": fact_count,
        "insights": insight_count,
        "sessions": session_count,
        "recent_memories": search("", limit=8),
        "facts_list": get_facts()[:20],
        "recent_insights": recent_insights(limit=10),
    }
