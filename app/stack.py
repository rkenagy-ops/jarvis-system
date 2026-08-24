"""Official growth stack: Publer, Klaviyo, ManyChat, ClickFunnels.

No browser hamburger, no multi-account feed commenting, no unofficial IG login.
Live posts/sends still need confirm_token.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from . import config, desktop, memory, obsidian

PUBLER = "https://app.publer.com/api/v1"
KLAVIYO = "https://a.klaviyo.com/api"
MANYCHAT = "https://api.manychat.com"
UA = {"User-Agent": "SuperJarvis/6.1 (https://github.com/rkenagy-ops/jarvis-system)", "Accept": "application/json"}


def refuse_browser_farm() -> dict[str, Any]:
    return {
        "blocked": True,
        "reason": (
            "Jarvis will not open Instagram/Facebook, hit the hamburger, switch accounts, "
            "or auto-comment the feed. That is unofficial multi-account farming. "
            "Use Publer API (official) + confirm_token, or comment yourself in the real app."
        ),
    }


def publer_ready() -> bool:
    return bool(getattr(config, "PUBLER_API_KEY", "") and getattr(config, "PUBLER_WORKSPACE_ID", ""))


def klaviyo_ready() -> bool:
    return bool(getattr(config, "KLAVIYO_API_KEY", ""))


def manychat_ready() -> bool:
    return bool(getattr(config, "MANYCHAT_API_TOKEN", ""))


def clickfunnels_ready() -> bool:
    return bool(getattr(config, "CLICKFUNNELS_API_KEY", ""))


def status() -> dict[str, Any]:
    return {
        "publer": publer_ready(),
        "klaviyo": klaviyo_ready(),
        "manychat": manychat_ready(),
        "clickfunnels": clickfunnels_ready(),
        "wordpress": bool(config.WORDPRESS_URL and config.WORDPRESS_APP_PASSWORD),
        "postiz": bool(config.POSTIZ_URL),
        "x_oauth": bool(config.X_API_KEY and config.X_ACCESS_TOKEN),
        "ibkr_live_flag": bool(config.IBKR_LIVE),
        "note": "Official APIs only. Live social/email/funnels need confirm_token. Live IBKR still needs TWS + confirm.",
        "refused": "No hamburger account-switch, no feed auto-comment bots.",
    }


def _publer_headers() -> dict[str, str]:
    return {
        **UA,
        "Authorization": f"Bearer-API {config.PUBLER_API_KEY}",
        "Publer-Workspace-Id": config.PUBLER_WORKSPACE_ID,
        "Content-Type": "application/json",
    }


def publer(action: str = "me", **kwargs: Any) -> dict[str, Any]:
    if not publer_ready():
        return {
            "ok": False,
            "need": ["PUBLER_API_KEY", "PUBLER_WORKSPACE_ID"],
            "hint": "Publer Business/Enterprise: Settings → API & Webhooks → generate key. Paste in KEYS.",
            "docs": "https://publer.com/docs/",
        }
    act = (action or "me").lower()
    try:
        with httpx.Client(timeout=20.0, headers=_publer_headers()) as client:
            if act in {"me", "status"}:
                r = client.get(f"{PUBLER}/me")
                r.raise_for_status()
                return {"ok": True, "me": r.json()}
            if act in {"accounts", "workspaces"}:
                r = client.get(f"{PUBLER}/accounts")
                r.raise_for_status()
                return {"ok": True, "accounts": r.json()}
            if act in {"posts", "list"}:
                r = client.get(f"{PUBLER}/posts", params={"state": kwargs.get("state") or "scheduled"})
                r.raise_for_status()
                return {"ok": True, "posts": r.json()}
            if act in {"schedule", "draft", "publish"}:
                return publer_schedule(
                    text=str(kwargs.get("text") or kwargs.get("body") or kwargs.get("title") or ""),
                    account_id=str(kwargs.get("account_id") or ""),
                    network=str(kwargs.get("network") or kwargs.get("platform") or "facebook"),
                    when=kwargs.get("when"),
                    live=act == "publish",
                    confirm_token=kwargs.get("confirm_token"),
                )
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"error": f"unknown publer action {act}"}


def publer_schedule(
    *,
    text: str,
    account_id: str,
    network: str = "facebook",
    when: str | None = None,
    live: bool = False,
    confirm_token: str | None = None,
) -> dict[str, Any]:
    if live or (when and not str(when).lower() in {"draft", ""}):
        if not confirm_token:
            pending = memory.create_pending(
                "publer_post",
                {"text": text[:2000], "account_id": account_id, "network": network, "when": when, "live": live},
                ttl_sec=300,
            )
            return {"blocked": True, "reason": "Live/scheduled Publer post needs confirm_token.", **pending}
        used = memory.consume_pending(confirm_token)
        if not used or used.get("kind") != "publer_post":
            return {"error": "Invalid or expired confirm token. No Publer post sent."}
        payload = used.get("payload") or {}
        text = payload.get("text") or text
        account_id = payload.get("account_id") or account_id
        network = payload.get("network") or network
        when = payload.get("when") or when
        live = bool(payload.get("live") or live)
    if not publer_ready():
        return {"ok": False, "need": ["PUBLER_API_KEY"]}
    if not account_id:
        return {"error": "Publer account_id required (from action=accounts)."}
    state = "scheduled" if when and not live else ("draft" if not live else "scheduled")
    body: dict[str, Any] = {
        "bulk": {
            "state": state,
            "posts": [
                {
                    "networks": {network: {"type": "status", "text": text[:2200]}},
                    "accounts": [{"id": account_id, **({"scheduled_at": when} if when else {})}],
                }
            ],
        }
    }
    if live and not when:
        # Immediate publish endpoint
        url = f"{PUBLER}/posts/schedule/publish"
        body["bulk"]["state"] = "scheduled"
    else:
        url = f"{PUBLER}/posts/schedule"
    try:
        with httpx.Client(timeout=25.0, headers=_publer_headers()) as client:
            r = client.post(url, json=body)
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:400], "status": r.status_code}
        data = r.json()
        return {"ok": True, "job_id": data.get("job_id"), "state": state, "network": network}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def klaviyo(action: str = "lists", **kwargs: Any) -> dict[str, Any]:
    if not klaviyo_ready():
        return {
            "ok": False,
            "need": ["KLAVIYO_API_KEY"],
            "hint": "Klaviyo → Settings → API keys. Paste in KEYS.",
            "docs": "https://developers.klaviyo.com/",
        }
    headers = {**UA, "Authorization": f"Klaviyo-API-Key {config.KLAVIYO_API_KEY}", "revision": "2024-10-15"}
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            if action in {"lists", "status", "me"}:
                r = client.get(f"{KLAVIYO}/lists")
                r.raise_for_status()
                return {"ok": True, "lists": r.json()}
            if action in {"metrics", "digest"}:
                r = client.get(f"{KLAVIYO}/metrics")
                r.raise_for_status()
                return {"ok": True, "metrics": r.json()}
            if action in {"campaigns"}:
                r = client.get(f"{KLAVIYO}/campaigns")
                r.raise_for_status()
                return {"ok": True, "campaigns": r.json()}
            if action in {"send", "campaign_send"}:
                return {
                    "blocked": True,
                    "reason": "Live Klaviyo campaign send needs a confirm_token and an explicit campaign id. Not auto-blasted.",
                }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"error": f"unknown klaviyo action {action}"}


def manychat(action: str = "info", **kwargs: Any) -> dict[str, Any]:
    if not manychat_ready():
        return {
            "ok": False,
            "need": ["MANYCHAT_API_TOKEN"],
            "hint": "ManyChat → Settings → API. Paste token in KEYS.",
            "docs": "https://manychat.github.io/dynamic_block_docs/",
        }
    headers = {**UA, "Authorization": f"Bearer {config.MANYCHAT_API_TOKEN}"}
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            if action in {"info", "status", "me", "page"}:
                r = client.get(f"{MANYCHAT}/fb/page/getInfo")
                r.raise_for_status()
                return {"ok": True, "page": r.json()}
            if action in {"send", "message"}:
                return {
                    "blocked": True,
                    "reason": "Live ManyChat sends need confirm_token. Use the ManyChat UI or confirm a specific subscriber send.",
                }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"error": f"unknown manychat action {action}"}


def clickfunnels(action: str = "status", **kwargs: Any) -> dict[str, Any]:
    key = getattr(config, "CLICKFUNNELS_API_KEY", "")
    base = (getattr(config, "CLICKFUNNELS_API_BASE", "") or "").rstrip("/")
    if not key:
        return {
            "ok": False,
            "need": ["CLICKFUNNELS_API_KEY", "CLICKFUNNELS_API_BASE"],
            "hint": "ClickFunnels 2.0 API token + workspace base URL (https://ACCOUNT.myclickfunnels.com). Paste in KEYS.",
            "docs": "https://developers.clickfunnels.com/",
        }
    headers = {**UA, "Authorization": f"Bearer {key}"}
    url = (base or "https://api.clickfunnels.com") + "/api/v2/workspaces"
    try:
        with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
            r = client.get(url)
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:400], "status": r.status_code}
        return {"ok": True, "data": r.json() if "json" in (r.headers.get("content-type") or "") else r.text[:800]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def dashboards() -> dict[str, Any]:
    """Open official dashboards in the local browser. Not a feed-comment bot."""
    urls = {
        "publer": "https://app.publer.com",
        "klaviyo": "https://www.klaviyo.com/login",
        "manychat": "https://app.manychat.com",
        "clickfunnels": "https://app.clickfunnels.com",
        "wordpress": (config.WORDPRESS_URL.rstrip("/") + "/wp-admin") if config.WORDPRESS_URL else "https://wordpress.org",
    }
    opened = []
    for name, url in urls.items():
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            opened.append(desktop.open_url(url))
    return {"ok": True, "opened": opened, "note": "Dashboards only. You log in. Jarvis does not drive the hamburger."}


def dispatch(action: str = "status", **kwargs: Any) -> dict[str, Any]:
    act = (action or "status").lower()
    if act in {"comment", "hamburger", "switch_account", "feed", "engage"}:
        return refuse_browser_farm()
    if act in {"status", "ready"}:
        return status()
    if act in {"dashboards", "open"}:
        return dashboards()
    if act.startswith("publer") or act in {"accounts", "schedule"}:
        inner = act.split("_", 1)[-1] if "_" in act else (kwargs.get("mode") or "me")
        if act == "accounts":
            inner = "accounts"
        if act == "schedule":
            inner = "schedule"
        return publer(inner, **kwargs)
    if act.startswith("klaviyo"):
        return klaviyo(act.split("_", 1)[-1] if "_" in act else (kwargs.get("mode") or "lists"), **kwargs)
    if act.startswith("manychat") or act in {"manychat"}:
        return manychat(kwargs.get("mode") or "info", **kwargs)
    if act.startswith("click") or act in {"funnels", "clickfunnels"}:
        return clickfunnels(kwargs.get("mode") or "status", **kwargs)
    if act == "klaviyo":
        return klaviyo(kwargs.get("mode") or "lists", **kwargs)
    return status()
