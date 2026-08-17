"""Microsoft Graph: calendar read + mail send. Device-code login. Public client, no secret."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from . import config

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = "offline_access User.Read Calendars.Read Mail.Send"
_lock = threading.Lock()
_device: dict[str, Any] = {}


def tenant() -> str:
    return (config.MS_TENANT or "consumers").strip() or "consumers"


def client_id() -> str:
    return (config.MS_CLIENT_ID or "").strip()


def ready() -> bool:
    return bool(client_id() and config.MS_REFRESH_TOKEN)


def _token_url() -> str:
    return f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0/token"


def start_device() -> dict[str, Any]:
    if not client_id():
        return {
            "ok": False,
            "error": "Set MS_CLIENT_ID first (Azure app, public client, Calendars.Read + Mail.Send + offline_access).",
            "help": "https://portal.azure.com → App registrations → New → Accounts in any org and personal Microsoft accounts → Authentication → Allow public client flows = Yes",
        }
    url = f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0/devicecode"
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, data={"client_id": client_id(), "scope": SCOPE})
    if resp.status_code >= 400:
        return {"ok": False, "error": resp.text[:400]}
    data = resp.json()
    with _lock:
        _device.update(data, started=time.time())
    threading.Thread(target=_poll, daemon=True).start()
    return {
        "ok": True,
        "user_code": data.get("user_code"),
        "verification_uri": data.get("verification_uri") or "https://microsoft.com/devicelogin",
        "expires_in": data.get("expires_in"),
        "message": data.get("message"),
    }


def _poll() -> None:
    interval = int(_device.get("interval") or 5)
    code = _device.get("device_code")
    if not code:
        return
    deadline = time.time() + int(_device.get("expires_in") or 900)
    while time.time() < deadline:
        time.sleep(max(3, interval))
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    _token_url(),
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "client_id": client_id(),
                        "device_code": code,
                    },
                )
            data = resp.json()
        except Exception:
            continue
        if data.get("refresh_token"):
            config.save_env({"MS_REFRESH_TOKEN": data["refresh_token"]})
            if data.get("access_token"):
                with _lock:
                    _device["access"] = data["access_token"]
                    _device["access_exp"] = time.time() + int(data.get("expires_in") or 3600)
                    _device["done"] = True
            return
        err = data.get("error")
        if err and err not in {"authorization_pending", "slow_down"}:
            with _lock:
                _device["error"] = data.get("error_description") or err
            return
        if err == "slow_down":
            interval += 5


def access_token() -> str | None:
    with _lock:
        tok = _device.get("access")
        exp = float(_device.get("access_exp") or 0)
        if tok and time.time() < exp - 60:
            return tok
    if not config.MS_REFRESH_TOKEN or not client_id():
        return None
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            _token_url(),
            data={
                "grant_type": "refresh_token",
                "client_id": client_id(),
                "refresh_token": config.MS_REFRESH_TOKEN,
                "scope": SCOPE,
            },
        )
    data = resp.json()
    if data.get("refresh_token"):
        config.save_env({"MS_REFRESH_TOKEN": data["refresh_token"]})
    tok = data.get("access_token")
    if tok:
        with _lock:
            _device["access"] = tok
            _device["access_exp"] = time.time() + int(data.get("expires_in") or 3600)
    return tok


def _get(path: str, params: dict | None = None) -> dict:
    token = access_token()
    if not token:
        return {"error": "Microsoft not signed in. Start device login."}
    with httpx.Client(timeout=25.0) as client:
        resp = client.get(
            GRAPH + path,
            headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'},
            params=params,
        )
    if resp.status_code >= 400:
        return {"error": f"graph {resp.status_code}", "detail": resp.text[:300]}
    return resp.json()


def me() -> dict:
    return _get("/me")


def calendar_today(hours: int = 24) -> dict:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=max(12, hours))
    data = _get(
        "/me/calendarView",
        {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": "subject,start,end,location,isAllDay,organizer",
            "$orderby": "start/dateTime",
            "$top": "20",
        },
    )
    if data.get("error"):
        return data
    events = []
    for ev in data.get("value") or []:
        events.append(
            {
                "subject": ev.get("subject"),
                "start": (ev.get("start") or {}).get("dateTime"),
                "end": (ev.get("end") or {}).get("dateTime"),
                "where": ((ev.get("location") or {}).get("displayName")),
            }
        )
    return {"ok": True, "events": events, "count": len(events)}


def send_mail(to: str, subject: str, body: str) -> dict:
    token = access_token()
    if not token:
        return {"error": "Microsoft not signed in."}
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
    }
    with httpx.Client(timeout=25.0) as client:
        resp = client.post(
            GRAPH + "/me/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        return {"error": f"graph {resp.status_code}", "detail": resp.text[:400]}
    return {"ok": True, "to": to, "subject": subject}


def status() -> dict:
    st = {
        "client_id_set": bool(client_id()),
        "signed_in": ready(),
        "tenant": tenant(),
        "device_pending": bool(_device.get("user_code") and not _device.get("done")),
        "user_code": _device.get("user_code") if not _device.get("done") else None,
        "verification_uri": _device.get("verification_uri") if not _device.get("done") else None,
        "device_error": _device.get("error"),
    }
    if ready():
        who = me()
        st["me"] = who.get("displayName") or who.get("userPrincipalName") or who.get("mail")
        if who.get("error"):
            st["graph_error"] = who.get("error")
    return st
