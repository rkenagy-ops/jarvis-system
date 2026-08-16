from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import config

FOLDERS = (
    "Daily", "People", "Projects", "Markets", "Inbox", "Skills", "Memory",
    "Calendar", "Templates", "Sources", "Content", "Blog", "Social", "Shop",
)
WIKI = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG = re.compile(r"(?<!\w)#([A-Za-z][\w/-]*)")
FM = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def vault() -> Path:
    root = Path(config.VAULT_DIR)
    root.mkdir(exist_ok=True)
    return root.resolve()


def resolve(rel: str) -> Path:
    root = vault()
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel.endswith(".md") and "." not in Path(rel).name:
        rel = rel + ".md"
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Path escapes the Obsidian vault")
    return path


def init_vault() -> dict:
    root = vault()
    for folder in FOLDERS:
        (root / folder).mkdir(exist_ok=True)
    obsidian = root / ".obsidian"
    obsidian.mkdir(exist_ok=True)
    _write_if_missing(
        obsidian / "app.json",
        json.dumps({"legacyEditor": False, "livePreview": True, "showLineNumber": True}, indent=2),
    )
    _write_if_missing(
        obsidian / "core-plugins.json",
        json.dumps(
            [
                "file-explorer",
                "global-search",
                "switcher",
                "graph",
                "backlink",
                "outgoing-link",
                "tag-pane",
                "page-preview",
                "daily-notes",
                "templates",
                "note-composer",
                "command-palette",
                "markdown-importer",
                "outline",
                "word-count",
            ],
            indent=2,
        ),
    )
    _write_if_missing(
        obsidian / "daily-notes.json",
        json.dumps({"folder": "Daily", "format": "YYYY-MM-DD", "template": "Templates/Daily"}, indent=2),
    )
    _write_if_missing(
        "Templates/Daily.md",
        "---\ntype: daily\ndate: {{date}}\n---\n\n# {{date}}\n\n## Capture\n\n## Markets\n\n## Tasks\n- [ ] \n\n## Links\n",
    )
    _write_if_missing(
        "00 Home.md",
        "---\ntype: moc\ntags: [jarvis, home]\n---\n\n# Jarvis OS\n\nThis folder is an [Obsidian](https://obsidian.md) vault. Open it with **File → Open vault**.\n\n## Maps\n- [[Daily]]\n- [[Projects]]\n- [[People]]\n- [[Markets]]\n- [[Memory]]\n- [[Skills]]\n- [[Calendar]]\n- [[Inbox]]\n\n## How Jarvis uses this\nEvery remember/insight/goal can land here as markdown. Wikilinks stay intact. Optional: install [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) and set `OBSIDIAN_API_URL` if you want live-editor sync.\n",
    )
    _write_if_missing(
        "Projects/jarvis-system.md",
        "---\ntype: project\trepo: rkenagy-ops/jarvis-system\nstatus: active\n---\n\n# jarvis-system\n\nGitHub: https://github.com/rkenagy-ops/jarvis-system\n\n## Next\n- Keep paper trading until several reviews pass\n- Point `OBSIDIAN_VAULT` at this folder if you move it\n",
    )
    _write_if_missing(
        "People/Rhett Kenagy.md",
        "---\ntype: person\nrole: owner\n---\n\n# Rhett Kenagy\n\nOwner of [[00 Home]]. GitHub: `rkenagy-ops`.\n",
    )
    _write_if_missing(
        "Skills/briefing.md",
        "---\ntype: skill\n---\n\n# Briefing\n\n1. Pull watchlist quotes.\n2. Pull weather + headlines.\n3. List open vault tasks (`- [ ]`).\n4. Write into today's [[Daily]] note under Morning briefing.\n5. Do not trade.\n",
    )
    _write_if_missing(
        "Skills/markets.md",
        "---\ntype: skill\n---\n\n# Markets\n\nUse `market analyze` before any paper trade. State thesis, invalidation, and size. Confirm tokens for live/large.\n",
    )
    _write_if_missing(
        "Inbox/Getting started.md",
        "---\ntype: inbox\n---\n\n# Getting started\n\n- [ ] Open this vault in Obsidian\n- [ ] Add XAI_API_KEY in the HUD\n- [ ] Add a GitHub token\n- [ ] Ask Jarvis for a morning briefing\n",
    )
    return {"vault": str(root), "folders": list(FOLDERS)}


def _write_if_missing(rel: str | Path, content: str) -> None:
    path = rel if isinstance(rel, Path) else (vault() / rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def list_notes(folder: str = "", limit: int = 80) -> dict:
    root = vault()
    base = resolve(folder) if folder and not folder.endswith(".md") else (root / folder if folder else root)
    if folder and folder.endswith(".md"):
        base = resolve(folder).parent
    if not base.exists():
        return {"error": "folder not found", "folder": folder}
    notes = []
    for path in sorted(base.rglob("*.md")):
        if ".obsidian" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        notes.append({"path": rel, "title": path.stem, "bytes": path.stat().st_size, "mtime": path.stat().st_mtime})
        if len(notes) >= limit:
            break
    return {"folder": folder or ".", "count": len(notes), "notes": notes}


def read_note(rel: str) -> dict:
    path = resolve(rel)
    if not path.is_file():
        return {"error": "note not found", "path": rel}
    text = path.read_text(encoding="utf-8")
    return {
        "path": path.relative_to(vault()).as_posix(),
        "text": text[:40000],
        "links": WIKI.findall(text),
        "tags": TAG.findall(text),
    }


def write_note(rel: str, content: str, *, mode: str = "replace") -> dict:
    path = resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")
    else:
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    rel_out = path.relative_to(vault()).as_posix()
    try:
        from . import rag

        rag.index_note(rel_out, path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return {"ok": True, "path": rel_out, "bytes": path.stat().st_size}


def daily(day: str | None = None, append: str | None = None) -> dict:
    day = day or date.today().isoformat()
    rel = f"Daily/{day}.md"
    path = resolve(rel)
    if not path.exists():
        write_note(
            rel,
            f"---\ntype: daily\ndate: {day}\ntags: [daily]\n---\n\n# {day}\n\n## Capture\n\n## Markets\n\n## Tasks\n",
        )
    if append:
        write_note(rel, append, mode="append")
    return read_note(rel)


def search(query: str, limit: int = 20) -> dict:
    q = (query or "").lower().strip()
    if not q:
        return {"results": []}
    hits = []
    root = vault()
    for path in root.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if q in text.lower() or q in path.name.lower():
            idx = text.lower().find(q)
            snippet = text[max(0, idx - 80) : idx + 160].replace("\n", " ")
            hits.append({"path": path.relative_to(root).as_posix(), "snippet": snippet})
            if len(hits) >= limit:
                break
    return {"query": query, "results": hits}


def backlinks(name: str) -> dict:
    needle = name.replace(".md", "")
    found = []
    root = vault()
    for path in root.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle.lower() in [l.lower() for l in WIKI.findall(text)]:
            found.append(path.relative_to(root).as_posix())
    return {"target": needle, "backlinks": found}


def capture_memory(kind: str, content: str, tags: list[str] | None = None) -> dict:
    init_vault()
    day = date.today().isoformat()
    stamp = datetime.now(timezone.utc).strftime("%H:%M")
    tag_s = " ".join(f"#{t}" for t in (tags or [kind])[:6])
    line = f"- {stamp} ({kind}) {content.strip()[:800]} {tag_s}".rstrip()
    daily(day, append=line)
    slug = re.sub(r"[^a-z0-9]+", "-", (content[:40] or kind).lower()).strip("-") or kind
    rel = f"Memory/{day}-{slug}.md"
    body = f"---\ntype: memory\nkind: {kind}\ndate: {day}\ntags: [{', '.join(tags or [kind])}]\n---\n\n# {kind}\n\n{content.strip()}\n\n## Links\n- [[{day}]]\n"
    return write_note(rel, body)


TASK_RE = re.compile(r"^(\s*)- \[([ xX])\] (.*)$")


def list_tasks(*, open_only: bool = True, limit: int = 40) -> list[dict]:
    init_vault()
    tasks = []
    root = vault()
    for folder in ("Daily", "Inbox", "Projects", "Calendar", "People"):
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, start=1):
                m = TASK_RE.match(line)
                if not m:
                    continue
                done = m.group(2).lower() == "x"
                if open_only and done:
                    continue
                tasks.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "line": i,
                        "text": m.group(3).strip(),
                        "done": done,
                    }
                )
                if len(tasks) >= limit:
                    return tasks
    return tasks


def toggle_task(rel: str, line: int, done: bool | None = None) -> dict:
    path = resolve(rel)
    if not path.is_file():
        return {"error": "note not found"}
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = int(line) - 1
    if idx < 0 or idx >= len(lines):
        return {"error": "line out of range"}
    m = TASK_RE.match(lines[idx])
    if not m:
        return {"error": "that line is not a task"}
    mark = "x" if (True if done is None else done) else " "
    if done is None:
        mark = " " if m.group(2).lower() == "x" else "x"
    lines[idx] = f"{m.group(1)}- [{mark}] {m.group(3)}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": rel, "line": line, "done": mark == "x", "text": m.group(3)}


def playbooks() -> list[dict]:
    init_vault()
    out = []
    folder = vault() / "Skills"
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        out.append({"name": path.stem, "title": title, "playbook": text[:1500], "path": f"Skills/{path.name}"})
    return out


def context_pack(query: str = "", *, max_chars: int = 4500) -> str:
    init_vault()
    parts = ["# OBSIDIAN VAULT"]
    day = daily()
    parts.append("## Today's note")
    parts.append((day.get("text") or "")[:1200])
    open_tasks = list_tasks(open_only=True, limit=12)
    if open_tasks:
        parts.append("## Open tasks")
        for t in open_tasks:
            parts.append(f"- ({t['path']}:{t['line']}) {t['text']}")
    books = playbooks()
    if books:
        parts.append("## Vault playbooks")
        for b in books[:8]:
            parts.append(f"- {b['name']}: {b['title']}")
    if query:
        hits = search(query, limit=6).get("results") or []
        if hits:
            parts.append("## Vault hits for this request")
            for h in hits:
                parts.append(f"- {h['path']}: {h.get('snippet') or ''}")
    text = "\n".join(parts)
    return text[:max_chars]


def dispatch(action: str, **kwargs) -> Any:
    init_vault()
    if action in {"list", "ls"}:
        return list_notes(kwargs.get("path") or kwargs.get("folder") or "", int(kwargs.get("limit") or 80))
    if action == "read":
        return read_note(kwargs.get("path") or "")
    if action == "write":
        return write_note(kwargs.get("path") or "", kwargs.get("content") or "", mode=kwargs.get("mode") or "replace")
    if action == "append":
        return write_note(kwargs.get("path") or "", kwargs.get("content") or "", mode="append")
    if action == "search":
        return search(kwargs.get("query") or "", int(kwargs.get("limit") or 20))
    if action == "daily":
        return daily(kwargs.get("date"), kwargs.get("content"))
    if action == "backlinks":
        return backlinks(kwargs.get("path") or kwargs.get("name") or "")
    if action == "capture":
        return capture_memory(kwargs.get("kind") or "note", kwargs.get("content") or "", kwargs.get("tags"))
    if action == "tasks":
        return {"tasks": list_tasks(open_only=str(kwargs.get("open_only", True)).lower() != "false")}
    if action == "toggle_task":
        done = kwargs.get("done")
        if isinstance(done, str):
            done = done.lower() in {"1", "true", "yes", "x"}
        return toggle_task(kwargs.get("path") or "", int(kwargs.get("line") or 0), done)
    if action == "playbooks":
        return {"playbooks": playbooks()}
    return {"error": f"Unknown obsidian action {action}"}
