"""Morning engagement run — comment on a few worthwhile posts per network, per account.

Automatic ONLY where the network has an official comment/reply API:

    x           official  home timeline read + reply endpoint        -> auto
    threads     official  keyword search + reply_to_id               -> auto
    linkedin    official  Comments API, restricted partner scope     -> auto if granted
    instagram   NONE      cannot comment on other accounts' media    -> review queue
    facebook    NONE      no home feed read, publish_actions dead    -> review queue

Instagram and Facebook are not a gap to close with a browser driver. Meta exposes
no endpoint for commenting on somebody else's post, so the only implementations
that exist drive a logged-in browser or a reverse-engineered private API — which
is what stack.refuse_browser_farm() blocks, and what gets accounts action-blocked.
For those two, Jarvis drafts the comment and hands you a deep link; you tap send.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx

from . import brain, config, memory, xpost

X_API = "https://api.x.com/2"
THREADS_API = "https://graph.threads.net/v1.0"
LINKEDIN_API = "https://api.linkedin.com/v2"
GRAPH_API = "https://graph.facebook.com/v21.0"

UA = {"User-Agent": "SuperJarvis/6.1 (https://github.com/rkenagy-ops/jarvis-system)"}

# Networks whose official API can post a comment on somebody else's post.
AUTO_NETWORKS = frozenset({"x", "threads", "linkedin"})
# Networks that can only ever produce a review queue.
REVIEW_NETWORKS = frozenset({"instagram", "facebook"})
NETWORKS = AUTO_NETWORKS | REVIEW_NETWORKS

MAX_PER_NETWORK = 5
MIN_COMMENT_CHARS = 25
MAX_COMMENT_CHARS = 240
# Posts older than this are stale — commenting on them reads as bot behaviour.
MAX_POST_AGE_SEC = 36 * 3600

# Openers that mark a comment as generic filler. These are what platforms score as spam.
GENERIC_OPENERS = (
    "great post",
    "love this",
    "so true",
    "thanks for sharing",
    "well said",
    "couldn't agree more",
    "this is amazing",
    "nice post",
    "good stuff",
    "amazing content",
    "💯",
    "🔥🔥",
)


def capabilities() -> dict[str, Any]:
    """What can actually run unattended right now, and why not where it can't."""
    return {
        "x": {
            "auto": "x" in AUTO_NETWORKS and xpost.ready(),
            "official": True,
            "reason": None if xpost.ready() else "Needs X_API_KEY/SECRET + X_ACCESS_TOKEN/SECRET.",
        },
        "threads": {
            "auto": bool(config.THREADS_ACCESS_TOKEN and config.THREADS_USER_ID),
            "official": True,
            "reason": None
            if config.THREADS_ACCESS_TOKEN
            else "Needs THREADS_ACCESS_TOKEN + THREADS_USER_ID (scopes: threads_content_publish, threads_keyword_search).",
        },
        "linkedin": {
            "auto": bool(config.LINKEDIN_ACCESS_TOKEN and config.LINKEDIN_AUTHOR_URN),
            "official": True,
            "reason": "LinkedIn's Comments API needs restricted partner access; most apps are not granted it.",
        },
        "instagram": {
            "auto": False,
            "official": False,
            "reason": "Meta exposes no endpoint to comment on another account's media. Review queue only.",
        },
        "facebook": {
            "auto": False,
            "official": False,
            "reason": "No home-feed read since /me/home was removed; publish_actions was revoked in 2018. Review queue only.",
        },
    }


# --------------------------------------------------------------------------- discovery


def _fresh(created_at: float | None) -> bool:
    if not created_at:
        return True
    return (time.time() - created_at) <= MAX_POST_AGE_SEC


def _iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def discover_x(limit: int = 10) -> dict[str, Any]:
    """Your real home timeline, via the official reverse-chronological endpoint."""
    if not xpost.ready():
        return {"ok": False, "need": ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]}
    try:
        me_url = f"{X_API}/users/me"
        with httpx.Client(timeout=20.0, headers=UA) as client:
            me = client.get(me_url, headers={"Authorization": xpost.oauth1_header("GET", me_url)})
            if me.status_code >= 400:
                return {"ok": False, "error": me.text[:300], "status": me.status_code}
            user = (me.json() or {}).get("data") or {}
            uid = user.get("id")
            if not uid:
                return {"ok": False, "error": "Could not resolve X user id."}

            url = f"{X_API}/users/{uid}/timelines/reverse_chronological"
            params = {
                "max_results": str(max(5, min(100, limit * 4))),
                "tweet.fields": "created_at,public_metrics,author_id,conversation_id",
                "expansions": "author_id",
                "user.fields": "username,name",
            }
            resp = client.get(
                url,
                params=params,
                headers={"Authorization": xpost.oauth1_header("GET", url, params)},
            )
        if resp.status_code >= 400:
            return {"ok": False, "error": resp.text[:300], "status": resp.status_code}
        payload = resp.json() or {}
        authors = {u["id"]: u for u in ((payload.get("includes") or {}).get("users") or [])}
        posts = []
        for t in payload.get("data") or []:
            if t.get("author_id") == uid:
                continue  # never comment on your own post
            author = authors.get(t.get("author_id")) or {}
            handle = author.get("username") or ""
            metrics = t.get("public_metrics") or {}
            posts.append(
                {
                    "network": "x",
                    "id": t.get("id"),
                    "text": t.get("text") or "",
                    "author": handle,
                    "created_at": _iso_to_epoch(t.get("created_at")),
                    "score": (metrics.get("like_count", 0) + 3 * metrics.get("reply_count", 0)),
                    "permalink": f"https://x.com/{handle or 'i'}/status/{t.get('id')}",
                }
            )
        return {"ok": True, "posts": posts}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def discover_threads(limit: int = 10, topics: str | None = None) -> dict[str, Any]:
    """Threads has no home-feed read; keyword search is the official discovery path."""
    token = config.THREADS_ACCESS_TOKEN
    if not token:
        return {"ok": False, "need": ["THREADS_ACCESS_TOKEN"]}
    terms = [t.strip() for t in (topics or config.ENGAGE_TOPICS or "").split(",") if t.strip()]
    if not terms:
        return {"ok": False, "error": "Set ENGAGE_TOPICS (comma separated) so Threads search has a query."}
    posts: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=20.0, headers=UA) as client:
            for term in terms[:3]:
                resp = client.get(
                    f"{THREADS_API}/keyword_search",
                    params={
                        "q": term,
                        "search_type": "TOP",
                        "fields": "id,text,username,timestamp,permalink",
                        "access_token": token,
                    },
                )
                if resp.status_code >= 400:
                    continue
                for item in (resp.json() or {}).get("data") or []:
                    if item.get("username") and item["username"] == config.THREADS_USER_ID:
                        continue
                    posts.append(
                        {
                            "network": "threads",
                            "id": item.get("id"),
                            "text": item.get("text") or "",
                            "author": item.get("username") or "",
                            "created_at": _iso_to_epoch(item.get("timestamp")),
                            "score": 1,
                            "permalink": item.get("permalink") or "",
                            "topic": term,
                        }
                    )
        return {"ok": True, "posts": posts[: limit * 3]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def discover_instagram(limit: int = 10, topics: str | None = None) -> dict[str, Any]:
    """Hashtag search is the only official IG discovery. Comments still can't be posted here."""
    token, uid = config.IG_ACCESS_TOKEN, config.IG_USER_ID
    if not (token and uid):
        return {"ok": False, "need": ["IG_ACCESS_TOKEN", "IG_USER_ID"]}
    tags = [t.strip().lstrip("#") for t in (topics or config.ENGAGE_TOPICS or "").split(",") if t.strip()]
    if not tags:
        return {"ok": False, "error": "Set ENGAGE_TOPICS so the hashtag search has something to look up."}
    posts: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=20.0, headers=UA) as client:
            for tag in tags[:3]:
                found = client.get(
                    f"{GRAPH_API}/ig_hashtag_search",
                    params={"user_id": uid, "q": tag, "access_token": token},
                )
                if found.status_code >= 400:
                    continue
                data = (found.json() or {}).get("data") or []
                if not data:
                    continue
                media = client.get(
                    f"{GRAPH_API}/{data[0]['id']}/top_media",
                    params={
                        "user_id": uid,
                        "fields": "id,caption,permalink,like_count,comments_count,timestamp",
                        "access_token": token,
                    },
                )
                if media.status_code >= 400:
                    continue
                for item in (media.json() or {}).get("data") or []:
                    posts.append(
                        {
                            "network": "instagram",
                            "id": item.get("id"),
                            "text": item.get("caption") or "",
                            "author": "",
                            "created_at": _iso_to_epoch(item.get("timestamp")),
                            "score": item.get("like_count", 0) + 3 * item.get("comments_count", 0),
                            "permalink": item.get("permalink") or "",
                            "topic": tag,
                        }
                    )
        return {"ok": True, "posts": posts[: limit * 3]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


DISCOVERY = {
    "x": discover_x,
    "threads": discover_threads,
    "instagram": discover_instagram,
}


# --------------------------------------------------------------------------- drafting


def _is_generic(text: str) -> bool:
    low = text.strip().lower()
    return any(low.startswith(opener) for opener in GENERIC_OPENERS)


def draft_comment(post: dict[str, Any], *, voice: str | None = None, session_id: str = "engage") -> dict[str, Any]:
    """Draft one specific, on-topic comment. Generic filler is rejected, not sent."""
    voice = voice or config.ENGAGE_VOICE or (
        f"{config.OWNER_NAME}, operator of a business account. Plain, direct, no hype."
    )
    body = (post.get("text") or "").strip()
    if not body:
        return {"ok": False, "error": "Post has no text to respond to."}

    prompt = (
        f"You are drafting ONE public comment as: {voice}\n\n"
        f"The post ({post.get('network')}, by @{post.get('author') or 'unknown'}):\n"
        f"\"\"\"\n{body[:1200]}\n\"\"\"\n\n"
        "Rules:\n"
        f"- {MIN_COMMENT_CHARS}-{MAX_COMMENT_CHARS} characters. One or two sentences.\n"
        "- Respond to the SPECIFIC claim or detail in this post. Reference it concretely.\n"
        "- Add something: an experience, a number, a qualification, a real question.\n"
        "- No opener like 'Great post' / 'Love this' / 'So true'. No emoji spam. No hashtags.\n"
        "- Do not pitch, link, or mention your own product.\n"
        "- If you have nothing substantive to add, reply with exactly: SKIP\n\n"
        "Output only the comment text."
    )
    try:
        result = brain.think(prompt, session_id=session_id, allow_spawn=False, persist_user=False)
    except Exception as exc:
        return {"ok": False, "error": f"draft failed: {str(exc)[:200]}"}

    text = (result.get("text") or "").strip().strip('"')
    if not text or text.upper().startswith("SKIP"):
        return {"ok": False, "skip": True, "reason": "Nothing substantive to add."}
    if len(text) < MIN_COMMENT_CHARS:
        return {"ok": False, "skip": True, "reason": f"Draft too thin ({len(text)} chars)."}
    if _is_generic(text):
        return {"ok": False, "skip": True, "reason": "Draft was generic filler."}
    return {"ok": True, "comment": text[:MAX_COMMENT_CHARS]}


# --------------------------------------------------------------------------- replying


def reply_x(post_id: str, text: str) -> dict[str, Any]:
    if not xpost.ready():
        return {"ok": False, "error": "X user tokens missing."}
    url = f"{X_API}/tweets"
    try:
        with httpx.Client(timeout=20.0, headers=UA) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": xpost.oauth1_header("POST", url),
                    "Content-Type": "application/json",
                },
                json={"text": text[:280], "reply": {"in_reply_to_tweet_id": post_id}},
            )
        if resp.status_code >= 400:
            return {"ok": False, "error": resp.text[:300], "status": resp.status_code}
        return {"ok": True, "data": resp.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def reply_threads(post_id: str, text: str) -> dict[str, Any]:
    token, uid = config.THREADS_ACCESS_TOKEN, config.THREADS_USER_ID
    if not (token and uid):
        return {"ok": False, "error": "Threads token/user id missing."}
    try:
        with httpx.Client(timeout=25.0, headers=UA) as client:
            created = client.post(
                f"{THREADS_API}/{uid}/threads",
                params={
                    "media_type": "TEXT",
                    "text": text[:500],
                    "reply_to_id": post_id,
                    "access_token": token,
                },
            )
            if created.status_code >= 400:
                return {"ok": False, "error": created.text[:300], "status": created.status_code}
            container = (created.json() or {}).get("id")
            if not container:
                return {"ok": False, "error": "Threads did not return a container id."}
            published = client.post(
                f"{THREADS_API}/{uid}/threads_publish",
                params={"creation_id": container, "access_token": token},
            )
        if published.status_code >= 400:
            return {"ok": False, "error": published.text[:300], "status": published.status_code}
        return {"ok": True, "data": published.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def reply_linkedin(post_urn: str, text: str) -> dict[str, Any]:
    token, actor = config.LINKEDIN_ACCESS_TOKEN, config.LINKEDIN_AUTHOR_URN
    if not (token and actor):
        return {"ok": False, "error": "LinkedIn token/author urn missing."}
    try:
        with httpx.Client(timeout=20.0, headers=UA) as client:
            resp = client.post(
                f"{LINKEDIN_API}/socialActions/{quote(post_urn, safe='')}/comments",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "Content-Type": "application/json",
                },
                json={"actor": actor, "message": {"text": text[:1250]}},
            )
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": resp.text[:300],
                "status": resp.status_code,
                "hint": "403 here usually means the Comments API scope was never granted to this app.",
            }
        return {"ok": True, "data": resp.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


REPLIERS = {"x": reply_x, "threads": reply_threads, "linkedin": reply_linkedin}


# --------------------------------------------------------------------------- the run


def _select(posts: list[dict[str, Any]], network: str, want: int) -> list[dict[str, Any]]:
    fresh = [
        p
        for p in posts
        if p.get("id")
        and (p.get("text") or "").strip()
        and _fresh(p.get("created_at"))
        and not memory.already_engaged(network, str(p["id"]))
    ]
    fresh.sort(key=lambda p: p.get("score") or 0, reverse=True)
    return fresh[:want]


def run(
    *,
    networks: Any = None,
    per_network: int | None = None,
    dry_run: bool = False,
    topics: str | None = None,
) -> dict[str, Any]:
    """One morning pass. Auto-posts where official; queues IG/FB for review."""
    if isinstance(networks, str):
        networks = [n.strip().lower() for n in networks.split(",") if n.strip()]
    selected = [n for n in (networks or sorted(NETWORKS)) if n in NETWORKS]
    unknown = [n for n in (networks or []) if n not in NETWORKS]

    want = per_network or config.ENGAGE_MAX_PER_NETWORK or 3
    want = max(1, min(MAX_PER_NETWORK, int(want)))

    used_today = len([e for e in memory.engagements_since(86400) if e.get("status") == "posted"])
    budget = max(0, (config.ENGAGE_DAILY_CAP or 15) - used_today)

    caps = capabilities()
    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "daily_cap_remaining": budget,
        "networks": {},
        "queued_for_review": [],
        "posted": [],
    }
    if unknown:
        report["unknown_networks"] = unknown

    for network in selected:
        cap = caps.get(network) or {}
        entry: dict[str, Any] = {"auto": bool(cap.get("auto")), "official": bool(cap.get("official"))}

        discover = DISCOVERY.get(network)
        if not discover:
            entry["skipped"] = cap.get("reason") or f"No discovery adapter for {network}."
            report["networks"][network] = entry
            continue

        found = discover(limit=want, topics=topics) if network != "x" else discover(limit=want)
        if not found.get("ok"):
            entry["skipped"] = found.get("error") or f"missing: {found.get('need')}"
            report["networks"][network] = entry
            continue

        picks = _select(found.get("posts") or [], network, want)
        entry["candidates"] = len(found.get("posts") or [])
        entry["selected"] = len(picks)
        entry["results"] = []

        for post in picks:
            if budget <= 0:
                entry["results"].append({"post": post.get("permalink"), "skipped": "daily cap reached"})
                continue

            drafted = draft_comment(post, session_id=f"engage-{network}")
            if not drafted.get("ok"):
                entry["results"].append(
                    {"post": post.get("permalink"), "skipped": drafted.get("reason") or drafted.get("error")}
                )
                continue
            comment = drafted["comment"]

            # Instagram / Facebook: no official write path, so this can only be queued.
            if network in REVIEW_NETWORKS:
                memory.record_engagement(
                    network,
                    str(post["id"]),
                    status="queued",
                    comment=comment,
                    permalink=post.get("permalink") or "",
                )
                item = {
                    "network": network,
                    "post_id": post["id"],
                    "permalink": post.get("permalink"),
                    "comment": comment,
                    "why_manual": cap.get("reason"),
                }
                report["queued_for_review"].append(item)
                entry["results"].append({"post": post.get("permalink"), "queued": True})
                continue

            if dry_run or not cap.get("auto"):
                entry["results"].append(
                    {
                        "post": post.get("permalink"),
                        "comment": comment,
                        "would_post": True,
                        "blocked_by": None if dry_run else cap.get("reason"),
                    }
                )
                continue

            sent = (REPLIERS[network])(str(post["id"]), comment)
            if sent.get("ok"):
                budget -= 1
                memory.record_engagement(
                    network,
                    str(post["id"]),
                    status="posted",
                    comment=comment,
                    permalink=post.get("permalink") or "",
                )
                report["posted"].append(
                    {"network": network, "permalink": post.get("permalink"), "comment": comment}
                )
                entry["results"].append({"post": post.get("permalink"), "posted": True})
            else:
                entry["results"].append({"post": post.get("permalink"), "error": sent.get("error")})

        report["networks"][network] = entry

    report["summary"] = (
        f"{len(report['posted'])} posted, {len(report['queued_for_review'])} queued for review, "
        f"{budget} of today's cap left."
    )
    return report


# --------------------------------------------------------------------------- review queue


def queue(limit: int = 25) -> dict[str, Any]:
    """Drafted IG/FB comments waiting for you to send them by hand."""
    rows = memory.engagements_by_status("queued", limit=limit)
    return {
        "ok": True,
        "count": len(rows),
        "note": "Meta has no API for commenting on other accounts' posts. Open the link, paste, send.",
        "items": [
            {
                "network": r.get("network"),
                "post_id": r.get("post_id"),
                "permalink": r.get("permalink"),
                "comment": r.get("comment"),
            }
            for r in rows
        ],
    }


def mark_done(network: str, post_id: str) -> dict[str, Any]:
    if not (network and post_id):
        return {"error": "network and post_id required."}
    memory.record_engagement(network, str(post_id), status="done")
    return {"ok": True, "network": network, "post_id": post_id, "status": "done"}


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    if act in {"status", "capabilities", "ready"}:
        return {"ok": True, "capabilities": capabilities(), "daily_cap": config.ENGAGE_DAILY_CAP}
    if act in {"queue", "review", "pending"}:
        return queue(int(kwargs.get("limit") or 25))
    if act in {"done", "mark_done"}:
        return mark_done(str(kwargs.get("network") or ""), str(kwargs.get("post_id") or ""))
    if act in {"run", "morning", "engage"}:
        return run(
            networks=kwargs.get("networks") or kwargs.get("network"),
            per_network=kwargs.get("per_network") or kwargs.get("count"),
            dry_run=bool(kwargs.get("dry_run")),
            topics=kwargs.get("topics"),
        )
    if act in {"draft", "preview"}:
        return run(
            networks=kwargs.get("networks") or kwargs.get("network"),
            per_network=kwargs.get("per_network") or kwargs.get("count"),
            dry_run=True,
            topics=kwargs.get("topics"),
        )
    return {"error": f"unknown engage action {act}", "actions": ["status", "run", "draft", "queue", "done"]}
