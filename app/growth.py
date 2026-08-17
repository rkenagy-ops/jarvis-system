"""Self-upgrade: hunt GitHub/web OSS, ingest what we can use, grow skills."""

from __future__ import annotations

from datetime import date
from typing import Any

from . import github_oss, memory, obsidian

GROWTH_PACK = [
    "leon-ai/leon",
    "langchain-ai/langgraph",
    "letta-ai/letta",
    "getzep/graphiti",
    "deepset-ai/haystack",
    "langgenius/dify",
    "Shubhamsaboo/awesome-llm-apps",
    "topoteretes/awesome-ai-memory",
    "crewAIInc/crewAI",
    "microsoft/autogen",
    "lastmile-ai/mcp-agent",
    "all-hands-ai/OpenHands",
    "stanford-oval/storm",
    "agentscope-ai/QwenPaw",
    "ComposioHQ/composio",
    "getzep/zep",
    "modelcontextprotocol/servers",
    "mem0ai/mem0",
]

HUNT = (
    "mcp server python tools assistant",
    "self-improving agent memory RAG",
    "open source personal AI assistant",
)


def already() -> set[str]:
    root = obsidian.vault() / "Sources" / "github"
    if not root.exists():
        return set()
    names = set()
    for path in root.glob("*.md"):
        names.add(path.stem.replace("-", "/", 1))
    return names


def pack(limit: int = 10) -> dict:
    stems = {p.stem for p in (obsidian.vault() / "Sources" / "github").glob("*.md")} if (obsidian.vault() / "Sources" / "github").exists() else set()
    ingested, errors, skipped = [], [], []
    for repo in GROWTH_PACK:
        if len(ingested) >= max(1, int(limit)):
            break
        if repo.replace("/", "-") in stems:
            skipped.append(repo)
            continue
        try:
            ingested.append(github_oss.ingest(repo))
            stems.add(repo.replace("/", "-"))
        except Exception as exc:
            errors.append({"repo": repo, "error": str(exc)})
    return {"ingested": ingested, "errors": errors, "skipped": skipped, "count": len(ingested), "pack": "growth"}


def hunt(limit: int = 6) -> dict:
    repos = []
    for q in HUNT:
        try:
            hit = github_oss.search(q, 4)
            for row in hit.get("repos") or []:
                name = row.get("full_name") or ""
                if name and name not in {r.get("full_name") for r in repos}:
                    repos.append(row)
        except Exception:
            continue
        if len(repos) >= limit:
            break
    return {"query": list(HUNT), "repos": repos[:limit]}


def cycle(limit: int = 6) -> dict[str, Any]:
    """One self-upgrade beat: hunt, ingest new, write a growth note, learn a skill."""
    hunted = hunt(limit)
    have_stems = {p.stem for p in (obsidian.vault() / "Sources" / "github").glob("*.md")} if (obsidian.vault() / "Sources" / "github").exists() else set()
    ingested, errors = [], []
    for row in hunted.get("repos") or []:
        name = row.get("full_name") or ""
        stem = name.replace("/", "-")
        if not name or stem in have_stems:
            continue
        try:
            ingested.append(github_oss.ingest(name))
            have_stems.add(stem)
        except Exception as exc:
            errors.append({"repo": name, "error": str(exc)})
        if len(ingested) >= 3:
            break
    packed = pack(max(0, 4 - len(ingested)))
    ingested.extend(packed.get("ingested") or [])
    errors.extend(packed.get("errors") or [])
    lines = [
        f"# Self-upgrade {date.today().isoformat()}",
        "",
        f"Ingested {len(ingested)} repos. Errors {len(errors)}.",
        "",
    ]
    for item in ingested:
        lines.append(f"- [[{item.get('vault', '').replace('.md', '')}]] {item.get('repo')}")
    for err in errors[:6]:
        lines.append(f"- skip {err.get('repo')}: {err.get('error')}")
    body = "\n".join(lines) + "\n"
    note = obsidian.write_note(f"Memory/{date.today().isoformat()}-self-upgrade.md", body)
    memory.upsert_skill(
        "self-upgrade",
        "Hunt GitHub for assistant/RAG/MCP/memory repos. Ingest READMEs into Sources/github. "
        "Steal playbooks, not stacks. Skip unofficial messaging and 0.0.0.0 binds. Write a Memory growth note.",
    )
    memory.remember(
        f"Self-upgrade ingested {[i.get('repo') for i in ingested]}",
        kind="growth",
        tags=["oss", "upgrade"],
        importance=0.55,
        source_agent="steward",
    )
    return {"ok": True, "ingested": ingested, "errors": errors, "hunted": hunted.get("repos"), "note": note.get("path")}


def plugins() -> dict:
    from . import obsidian as ob

    books = ob.playbooks()
    return {"plugins": books, "count": len(books)}
