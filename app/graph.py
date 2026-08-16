"""Knowledge graph from Obsidian wikilinks — cheap brain expansion."""

from __future__ import annotations

import re
from collections import defaultdict

from . import obsidian

WIKI = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def build() -> dict:
    root = obsidian.vault()
    edges: list[tuple[str, str]] = []
    nodes: set[str] = set()
    for path in root.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        src = path.stem
        nodes.add(src)
        text = path.read_text(encoding="utf-8", errors="replace")
        for dest in WIKI.findall(text):
            dest = dest.strip()
            if dest:
                nodes.add(dest)
                edges.append((src, dest))
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "adj": {k: sorted(v) for k, v in adj.items()},
    }


def neighbors(name: str, limit: int = 8) -> list[str]:
    g = build()
    return (g["adj"].get(name) or g["adj"].get(name.replace(".md", "")) or [])[:limit]


def pack(query: str, *, max_chars: int = 1200) -> str:
    g = build()
    q = (query or "").lower()
    hits = [n for n in g["adj"] if q and q in n.lower()][:6]
    if not hits:
        top = sorted(g["adj"], key=lambda n: len(g["adj"][n]), reverse=True)[:6]
        hits = top
    lines = ["# KNOWLEDGE GRAPH", f"nodes={g['nodes']} edges={g['edges']}"]
    for n in hits:
        nbr = ", ".join(g["adj"].get(n, [])[:6])
        lines.append(f"- [[{n}]] → {nbr}")
    return "\n".join(lines)[:max_chars]
