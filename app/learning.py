"""Learn from open source: find repos that fill a capability gap, read them, keep what's useful.

app/oss.py removed the allowlist — any public repo, real source. This is the thing that
uses it on a schedule (bot-22-learn) instead of waiting to be asked.

Each cycle:
  1. pick the topics Jarvis is weakest on (or the ones you name)
  2. search GitHub for repos on that topic
  3. skip anything already learned — the ledger lives in memory, so a cycle never
     re-ingests the same repo and the corpus grows instead of churning
  4. fetch the actual source, ingest it into the vault, reindex the RAG
  5. write down what changed

The point is the RAG index: once a repo's source is in there, every agent can retrieve
from it. That is what "learning" means here — not fine-tuning, retrieval over code
Jarvis has actually read.

Fetching and reading are unrestricted. Nothing here installs or executes what it pulls;
oss.install stays a separate, deliberate, confirm-gated act.
"""

from __future__ import annotations

import time
from typing import Any

from . import memory, oss, repo_index

# What Jarvis wants to get better at, and the search that finds it.
TOPICS: dict[str, str] = {
    "trading": "interactive brokers python trading stars:>200",
    "backtesting": "python backtesting framework stars:>1000",
    "observability": "llm tracing observability python stars:>500",
    "market_data": "market data python library stars:>500",
    "prediction_markets": "prediction market api python stars:>50",
    "agents": "llm agent framework python stars:>1000",
    "memory": "llm long term memory vector store python stars:>500",
    "retrieval": "rag retrieval pipeline python stars:>500",
    "scheduling": "task scheduler python stars:>500",
    "social": "social media api python stars:>200",
    "scraping": "web scraping extraction python stars:>1000",
    "voice": "speech to text python stars:>1000",
    "data": "dataframe analytics python stars:>2000",
    "automation": "workflow automation python stars:>1000",
    "options": "options pricing greeks implied volatility python stars:>200",
    "risk": "portfolio risk metrics drawdown python stars:>500",
    "security": "secret scanning credential detection stars:>1000",
    "interface": "python native desktop gui framework stars:>1000",
}

LEDGER_KEY = "learning.ingested"
MAX_REPOS_PER_CYCLE = 3
MAX_FILES_PER_REPO = 30


def _ledger() -> list[str]:
    for fact in memory.get_facts():
        if fact.get("key") == LEDGER_KEY:
            return [r for r in (fact.get("value") or "").split(",") if r]
    return []


def _remember_repo(repo: str) -> None:
    seen = _ledger()
    if repo in seen:
        return
    seen.append(repo)
    # Keep the ledger bounded; oldest entries fall off first.
    memory.set_fact(LEDGER_KEY, ",".join(seen[-300:]), confidence=1.0, source_agent="jarvis")


def learned() -> dict[str, Any]:
    seen = _ledger()
    return {"ok": True, "count": len(seen), "repos": seen}


def search_available() -> bool:
    """GitHub's search API needs a token; codeload (fetching) does not."""
    try:
        from . import github_client

        return bool(github_client.resolve_token())
    except Exception:
        return False


def candidates(topic: str, limit: int = 5) -> dict[str, Any]:
    """Repos on a topic that haven't been ingested yet.

    The curated index comes first and needs no credentials. GitHub search is layered
    on top when a token exists — it widens the pool, it is not required for one.
    """
    seen = set(_ledger())
    picks: list[dict[str, Any]] = []

    for entry in repo_index.for_topic(topic):
        if entry["repo"] not in seen:
            picks.append({"repo": entry["repo"], "why": entry["why"], "source": "index", "priority": entry["priority"]})

    searched = False
    search_error = None
    if len(picks) < limit and search_available():
        found = oss.search(TOPICS.get(topic) or topic, limit=limit * 3)
        if found.get("ok"):
            searched = True
            known = {p["repo"] for p in picks}
            for r in found.get("repos") or []:
                repo = r.get("repo")
                if repo and repo not in seen and repo not in known:
                    picks.append({"repo": repo, "stars": r.get("stars"), "source": "search", "priority": 9})
        else:
            search_error = found.get("error")

    picks.sort(key=lambda p: p.get("priority", 9))
    return {
        "ok": True,
        "topic": topic,
        "candidates": picks[:limit],
        "searched": searched,
        "search_error": search_error,
        "index_only": not searched,
    }


def study(repo: str, *, max_files: int = MAX_FILES_PER_REPO) -> dict[str, Any]:
    """Fetch one repo's source and put it in the vault where the RAG can reach it."""
    if not oss._valid(repo):
        return {"error": f"{repo!r} must look like owner/name."}

    fetched = oss.fetch(repo)
    if not fetched.get("ok"):
        return fetched

    ingested = oss.ingest(repo, max_files=max_files)
    if not ingested.get("ok"):
        return ingested

    _remember_repo(repo)
    memory.remember(
        f"Studied {repo}: {ingested.get('files_ingested')} files into {ingested.get('vault')}",
        kind="learning",
        tags=["learning", "oss", repo],
        importance=0.7,
        source_agent="jarvis",
    )
    return {
        "ok": True,
        "repo": repo,
        "files_fetched": fetched.get("files"),
        "files_ingested": ingested.get("files_ingested"),
        "vault": ingested.get("vault"),
    }


def cycle(
    *,
    topics: Any = None,
    max_repos: int = MAX_REPOS_PER_CYCLE,
    reindex: bool = True,
) -> dict[str, Any]:
    """One learning pass. Safe to run on a schedule — already-learned repos are skipped."""
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(",") if t.strip()]
    wanted = list(topics or TOPICS.keys())

    started = time.time()
    has_search = search_available()
    studied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for topic in wanted:
        if len(studied) >= max_repos:
            break
        found = candidates(topic, limit=3)
        if not found.get("ok"):
            skipped.append({"topic": topic, "reason": found.get("error") or "discovery failed"})
            continue
        picks = found.get("candidates") or []
        if not picks:
            skipped.append({"topic": topic, "reason": "nothing new — everything indexed for this topic is already studied"})
            continue

        for pick in picks:
            if len(studied) >= max_repos:
                break
            out = study(pick["repo"])
            if out.get("ok"):
                studied.append({**out, "topic": topic, "stars": pick.get("stars")})
                break  # one repo per topic per cycle keeps the corpus broad
            skipped.append({"topic": topic, "repo": pick["repo"], "reason": out.get("error")})

    reindexed = None
    if reindex and studied:
        try:
            from . import rag

            rag.reindex_vault()
            reindexed = True
        except Exception as exc:
            reindexed = f"reindex failed: {str(exc)[:150]}"

    total_files = sum(s.get("files_ingested") or 0 for s in studied)
    if studied:
        summary = (
            f"Learned {len(studied)} repo(s), {total_files} files"
            + (", reindexed" if reindexed is True else "")
            + f". {len(_ledger())} studied all-time."
        )
    else:
        summary = f"Nothing new to learn ({len(_ledger())} repos already studied)."

    return {
        "ok": True,
        "summary": summary,
        "studied": studied,
        "skipped": skipped,
        "reindexed": reindexed,
        "search_enabled": has_search,
        "discovery": "index + GitHub search" if has_search else "curated index only",
        "elapsed_sec": round(time.time() - started, 1),
        "total_learned": len(_ledger()),
    }


def hubs(max_repos: int = 3) -> dict[str, Any]:
    """Ingest the awesome-list indexes. Small, and each one maps a whole field."""
    seen = set(_ledger())
    done, failed = [], []
    for entry in repo_index.HUBS:
        if len(done) >= max_repos:
            break
        if entry["repo"] in seen:
            continue
        out = study(entry["repo"], max_files=8)
        if out.get("ok"):
            done.append({**out, "why": entry["why"]})
        else:
            failed.append({"repo": entry["repo"], "reason": out.get("error")})
    return {
        "ok": True,
        "summary": f"Ingested {len(done)} hub index(es).",
        "hubs": done,
        "failed": failed,
        "remaining": [h["repo"] for h in repo_index.HUBS if h["repo"] not in set(_ledger())],
    }


def index() -> dict[str, Any]:
    """What the curated index holds, and how much of it has been studied."""
    seen = set(_ledger())
    rows = repo_index.summary()
    rows["studied"] = sorted(r for r in repo_index.all_repos() if r in seen)
    rows["unstudied"] = sorted(r for r in repo_index.all_repos() if r not in seen)
    rows["search_enabled"] = search_available()
    if not rows["search_enabled"]:
        rows["search_note"] = (
            "No GITHUB_TOKEN, so GitHub search is off — the curated index is the whole "
            "discovery pool. Fetching itself needs no credentials."
        )
    return rows


def gaps() -> dict[str, Any]:
    """Which topics have no studied repo behind them yet."""
    seen = _ledger()
    covered = {}
    for fact in memory.search("Studied", limit=200):
        content = fact.get("content") or ""
        for topic in TOPICS:
            if topic in content.lower():
                covered[topic] = covered.get(topic, 0) + 1
    return {
        "ok": True,
        "topics": sorted(TOPICS),
        "studied_repos": len(seen),
        "uncovered": [t for t in TOPICS if t not in covered],
        "next": "learning action=cycle topics=<topic> to fill one in.",
    }


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    if act in {"status", "learned", "ledger"}:
        return learned()
    if act in {"topics", "gaps"}:
        return gaps()
    if act in {"index", "catalog", "repos"}:
        return index()
    if act in {"hubs", "awesome"}:
        return hubs(int(kwargs.get("max_repos") or 3))
    if act in {"candidates", "find"}:
        return candidates(str(kwargs.get("topic") or ""), int(kwargs.get("limit") or 5))
    if act in {"study", "read"}:
        return study(
            str(kwargs.get("repo") or ""),
            max_files=int(kwargs.get("max_files") or MAX_FILES_PER_REPO),
        )
    if act in {"cycle", "run", "learn"}:
        return cycle(
            topics=kwargs.get("topics") or kwargs.get("topic"),
            max_repos=int(kwargs.get("max_repos") or MAX_REPOS_PER_CYCLE),
            reindex=kwargs.get("reindex") is not False,
        )
    return {
        "error": f"unknown learning action {act}",
        "actions": ["status", "index", "hubs", "gaps", "candidates", "study", "cycle"],
    }
