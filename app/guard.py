"""Fortress: Super Jarvis stays private. The brain may go out; the HUD must not come in."""

from __future__ import annotations

import ipaddress
import secrets
import socket
from urllib.parse import urljoin, urlparse

import httpx

from . import config

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "0.0.0.0"}
_mem_token = ""


def is_loopback_ip(host: str) -> bool:
    h = (host or "").split("%")[0].strip("[]")
    if h in LOOPBACK_HOSTS or h in {"testclient"}:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def host_ok(host_header: str) -> bool:
    host = (host_header or "").split(":")[0].strip().lower()
    if host in LOOPBACK_HOSTS:
        return True
    extra = (config.JARVIS_PUBLIC_HOST or "").strip().lower()
    if extra and host == extra and config.JARVIS_ALLOW_LAN:
        return True
    return False


def bind_host() -> str:
    host = (config.HOST or "127.0.0.1").strip()
    if host in LOOPBACK_HOSTS:
        return "127.0.0.1" if host == "localhost" else host
    if config.JARVIS_ALLOW_LAN and token():
        return host
    return "127.0.0.1"


def token() -> str:
    global _mem_token
    if config.JARVIS_TOKEN:
        return config.JARVIS_TOKEN
    if not _mem_token:
        _mem_token = secrets.token_urlsafe(24)
    return _mem_token


def persist_token() -> str:
    t = token()
    if not config.JARVIS_TOKEN:
        config.save_env({"JARVIS_TOKEN": t})
    return t


def token_ok(given: str | None) -> bool:
    expected = token()
    if not expected:
        return True
    return secrets.compare_digest((given or "").strip(), expected)


def allow_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().strip("[]")
    if host in BLOCKED_HOSTS or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return _public_ip(ip)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            return False
        if not _public_ip(ip):
            return False
    return True


def _public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return False
    return str(ip) not in {"169.254.169.254"}


def fetch_public(url: str, *, timeout: float = 25.0, headers: dict | None = None) -> httpx.Response:
    current = url
    hdrs = headers or {"User-Agent": "SuperJarvis/3.1"}
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=hdrs) as client:
        for _ in range(5):
            if not allow_url(current):
                raise ValueError("Blocked private/loopback URL")
            resp = client.get(current)
            if resp.is_redirect:
                loc = resp.headers.get("location")
                if not loc:
                    return resp
                current = urljoin(current, loc)
                continue
            return resp
    raise ValueError("Too many redirects")


def posture() -> dict:
    bound = bind_host()
    return {
        "bind": bound,
        "configured_host": config.HOST,
        "loopback_only": bound in LOOPBACK_HOSTS,
        "lan_allowed": bool(config.JARVIS_ALLOW_LAN),
        "token_set": bool(token()),
        "offline": bool(config.OFFLINE),
        "vpn_note": "VPN protects your outbound path on public Wi-Fi. It is not a substitute for loopback bind.",
        "model": "private HUD + outbound APIs" if not config.OFFLINE else "offline free-brain",
    }
