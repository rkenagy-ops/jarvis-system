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
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                playbook TEXT NOT NULL,
                uses INTEGER NOT NULL DEFAULT 0,
                last_used REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                detail TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                priority REAL NOT NULL DEFAULT 0.5,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                every_sec INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run REAL,
                last_result TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            );
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
        if not conn.execute("SELECT 1 FROM skills LIMIT 1").fetchone():
            now = time.time()
            seeds = [
                ("research", "Search web + X, fetch primary sources, separate fact/rumor, cite."),
                ("github", "Use github tool against rkenagy-ops. Never invent repo state."),
                ("markets", "Pull quotes/history, compute indicators, paper-trade only unless confirm token is used."),
                ("data", "Load workspace files, profile columns, summarize risk and anomalies."),
                ("memory", "Write durable facts and skills after every useful lesson."),
            ]
            for name, playbook in seeds:
                conn.execute(
                    "INSERT INTO skills(id, name, playbook, uses, last_used, created_at) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), name, playbook, 0, now, now),
                )
        if not conn.execute("SELECT 1 FROM jobs LIMIT 1").fetchone():
            now = time.time()
            conn.execute(
                "INSERT INTO jobs(id, name, prompt, every_sec, enabled, last_run, last_result, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    "watchlist-scan",
                    "Scan the watchlist. Note movers > 1.5% on the day. Write a short market pulse to memory. Do not trade.",
                    900,
                    1,
                    None,
                    None,
                    now,
                ),
            )
        if not conn.execute("SELECT 1 FROM jobs WHERE name=?", ("morning-briefing",)).fetchone():
            conn.execute(
                "INSERT INTO jobs(id, name, prompt, every_sec, enabled, last_run, last_result, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    "morning-briefing",
                    "Compile weather, watchlist, news, and open vault tasks into today's daily note.",
                    21600,
                    1,
                    None,
                    None,
                    time.time(),
                ),
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
    from .redact import redact

    content = redact(content.strip())
    item = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "content": content,
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
    try:
        from . import obsidian

        obsidian.capture_memory(kind, content, tags or [kind])
    except Exception:
        pass
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
    from .redact import redact

    content = redact(content)
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages(id, session_id, role, content, agent, created_at) VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, role, content, agent, time.time()),
        )
    try:
        from . import room

        who = "owner" if role == "user" else (agent or "jarvis")
        room.hear(who, content)
    except Exception:
        pass


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
    skills = list_skills()
    goals = list_goals("open")
    parts = ["# SHARED MIND — full unlocked memory (all agents read this)"]
    if facts:
        parts.append("## Durable facts")
        for f in facts[:80]:
            parts.append(f"- {f['key']}: {f['value']} (conf {f['confidence']:.2f})")
    if skills:
        parts.append("## Growing skills")
        for s in skills[:16]:
            parts.append(f"- {s['name']} (uses {s['uses']}): {s['playbook']}")
    if goals:
        parts.append("## Open goals")
        for g in goals[:12]:
            parts.append(f"- [{g['priority']:.1f}] {g['title']}: {g.get('detail') or ''}")
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


def upsert_skill(name: str, playbook: str) -> dict:
    now = time.time()
    name = name.strip().lower()
    with _db() as conn:
        row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute(
                "UPDATE skills SET playbook=?, uses=uses+1, last_used=? WHERE name=?",
                (playbook, now, name),
            )
        else:
            conn.execute(
                "INSERT INTO skills(id, name, playbook, uses, last_used, created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), name, playbook, 1, now, now),
            )
    return {"name": name, "playbook": playbook}


def bump_skill(name: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE skills SET uses=uses+1, last_used=? WHERE name=?",
            (time.time(), name.strip().lower()),
        )


def list_skills() -> list[dict]:
    with _db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM skills ORDER BY uses DESC, last_used DESC").fetchall()]


def add_goal(title: str, detail: str = "", priority: float = 0.5) -> dict:
    now = time.time()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "detail": detail.strip(),
        "status": "open",
        "priority": priority,
        "created_at": now,
        "updated_at": now,
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO goals(id, title, detail, status, priority, created_at, updated_at)
               VALUES(:id,:title,:detail,:status,:priority,:created_at,:updated_at)""",
            item,
        )
    remember(f"Goal: {title} — {detail}", kind="goal", tags=["goal"], importance=0.7, source_agent="jarvis")
    return item


def update_goal(goal_id: str, status: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "UPDATE goals SET status=?, updated_at=? WHERE id=?",
            (status, time.time(), goal_id),
        )
        return cur.rowcount > 0


def list_goals(status: str | None = "open") -> list[dict]:
    with _db() as conn:
        if status:
            rows = conn.execute("SELECT * FROM goals WHERE status=? ORDER BY priority DESC, updated_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY updated_at DESC LIMIT 30").fetchall()
    return [dict(r) for r in rows]


def add_job(name: str, prompt: str, every_sec: int = 1800, enabled: bool = True) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "prompt": prompt,
        "every_sec": int(every_sec),
        "enabled": 1 if enabled else 0,
        "last_run": None,
        "last_result": None,
        "created_at": time.time(),
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO jobs(id, name, prompt, every_sec, enabled, last_run, last_result, created_at)
               VALUES(:id,:name,:prompt,:every_sec,:enabled,:last_run,:last_result,:created_at)""",
            item,
        )
    return item


def list_jobs() -> list[dict]:
    with _db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY name").fetchall()]


def due_jobs() -> list[dict]:
    now = time.time()
    with _db() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE enabled=1").fetchall()
    out = []
    for r in rows:
        job = dict(r)
        last = job.get("last_run") or 0
        if now - last >= int(job["every_sec"]):
            out.append(job)
    return out


def mark_job(job_id: str, result: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE jobs SET last_run=?, last_result=? WHERE id=?",
            (time.time(), result[:2000], job_id),
        )


def set_job_enabled(job_id: str, enabled: bool) -> bool:
    with _db() as conn:
        cur = conn.execute("UPDATE jobs SET enabled=? WHERE id=?", (1 if enabled else 0, job_id))
        return cur.rowcount > 0


def create_pending(kind: str, payload: dict, ttl_sec: int = 300) -> dict:
    now = time.time()
    item = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "payload": json.dumps(payload),
        "created_at": now,
        "expires_at": now + ttl_sec,
        "used": 0,
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO pending_actions(id, kind, payload, created_at, expires_at, used)
               VALUES(:id,:kind,:payload,:created_at,:expires_at,:used)""",
            item,
        )
    return {"confirm_token": item["id"], "expires_in_sec": ttl_sec, "kind": kind, "payload": payload}


def consume_pending(token: str) -> dict | None:
    now = time.time()
    with _db() as conn:
        row = conn.execute("SELECT * FROM pending_actions WHERE id=?", (token,)).fetchone()
        if not row:
            return None
        item = dict(row)
        if item["used"] or item["expires_at"] < now:
            return None
        conn.execute("UPDATE pending_actions SET used=1 WHERE id=?", (token,))
    item["payload"] = json.loads(item["payload"])
    return item


def learn_from_turn(user_text: str, assistant_text: str, calls: list[dict] | None = None) -> None:
    calls = calls or []
    names = [c.get("name") for c in calls if c.get("name")]
    mapping = {
        "github": "github",
        "market": "markets",
        "market_quote": "markets",
        "market_history": "markets",
        "market_analyze": "markets",
        "paper_trade": "markets",
        "workspace": "data",
        "obsidian": "memory",
        "imagine": "data",
        "integrate": "research",
        "catalog": "research",
        "oss": "github",
        "analyze_file": "data",
        "workspace_read": "data",
        "fetch_url": "research",
        "wiki": "research",
        "news_headlines": "research",
    }
    for n in names:
        if n in mapping:
            bump_skill(mapping[n])
    snippet = (user_text or "")[:240]
    reply = (assistant_text or "")[:400]
    if snippet and reply:
        remember(
            f"Q: {snippet}\nA: {reply}",
            kind="episode",
            tags=["episode"] + names[:4],
            importance=0.45,
            source_agent="archivist",
        )


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
        "skills": list_skills(),
        "goals": list_goals("open"),
        "jobs": list_jobs(),
    }
