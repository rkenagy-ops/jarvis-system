"""Route work to the smallest useful set of specialists."""

from __future__ import annotations

RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("tweet", "instagram", "linkedin", "tiktok", "caption", "social"), ["social", "scribe", "scheduler"]),
    (("blog", "wordpress", "article", "newsletter"), ["publisher", "scribe"]),
    (("amazon", "asin", "listing", "sku", "product", "shopify"), ["merch", "scribe"]),
    (("trade", "stock", "nvda", "spy", "rsi", "portfolio"), ["trader", "critic"]),
    (("github", "repo", "pull request", "issue"), ["sentinel", "forge"]),
    (("code", "bug", "python", "function"), ["forge", "critic"]),
    (("vault", "remember", "obsidian", "note"), ["archivist"]),
    (("image", "logo", "thumbnail", "imagine"), ["designer"]),
    (("schedule", "calendar", "week of content"), ["scheduler", "social", "scribe"]),
    (("research", "arxiv", "news", "what is"), ["oracle"]),
    (("youtube", "maps", "open website", "notify", "email", "screenshot", "reminder", "plan my day"), ["scribe"]),
]


def suggest(text: str, *, limit: int = 4) -> list[str]:
    low = (text or "").lower()
    picked: list[str] = []
    for keys, agents in RULES:
        if any(k in low for k in keys):
            for a in agents:
                if a not in picked:
                    picked.append(a)
        if len(picked) >= limit:
            break
    return picked[:limit]


def hint(text: str) -> str:
    agents = suggest(text)
    if not agents:
        return "Recommended specialists: none — handle solo unless the job is multi-domain."
    return "Recommended specialists (spawn only if parallel value): " + ", ".join(agents)
