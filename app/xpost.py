"""Official X post via OAuth 1.0a user context. Bearer is app-only and usually cannot tweet."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

import httpx

from . import config


def ready() -> bool:
    return bool(
        config.X_API_KEY
        and config.X_API_SECRET
        and config.X_ACCESS_TOKEN
        and config.X_ACCESS_SECRET
    )


def _enc(s: str) -> str:
    return quote(str(s), safe="~-._")


def oauth1_header(method: str, url: str, extra: dict | None = None) -> str:
    oauth = {
        "oauth_consumer_key": config.X_API_KEY,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": config.X_ACCESS_TOKEN,
        "oauth_version": "1.0",
    }
    merged = {**oauth, **(extra or {})}
    bits = "&".join(f"{_enc(k)}={_enc(merged[k])}" for k in sorted(merged))
    base = f"{method.upper()}&{_enc(url)}&{_enc(bits)}"
    key = f"{_enc(config.X_API_SECRET)}&{_enc(config.X_ACCESS_SECRET)}"
    sig = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    inner = ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))
    return f"OAuth {inner}"


def tweet(text: str) -> dict:
    text = (text or "").strip()[:280]
    if not text:
        return {"error": "empty tweet"}
    url = "https://api.x.com/2/tweets"
    if ready():
        headers = {
            "Authorization": oauth1_header("POST", url),
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, headers=headers, json={"text": text})
        if resp.status_code >= 400:
            return {"platform": "x", "error": resp.text[:400], "auth": "oauth1"}
        return {"platform": "x", "status": "posted", "auth": "oauth1", "data": resp.json()}
    if config.X_BEARER_TOKEN:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {config.X_BEARER_TOKEN}", "Content-Type": "application/json"},
                json={"text": text},
            )
        if resp.status_code >= 400:
            return {
                "platform": "x",
                "error": resp.text[:400],
                "auth": "bearer",
                "note": "App bearer usually cannot tweet. Add X_API_KEY / SECRET / ACCESS_TOKEN / ACCESS_SECRET.",
            }
        return {"platform": "x", "status": "posted", "auth": "bearer", "data": resp.json()}
    return {"platform": "x", "status": "draft-only", "note": "No X user tokens. WordPress is the live channel."}
