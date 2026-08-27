"""Local Ollama brain — loopback only. Grok stays primary."""

from __future__ import annotations

import time
from typing import Any

import httpx

from . import config

_probe: dict[str, Any] = {"ok": None, "reason": "untested", "checked": 0.0, "models": []}


def base() -> str:
    return (config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")


def model() -> str:
    return config.OLLAMA_MODEL or "llama3.2"


def diagnose() -> dict[str, Any]:
    """Is Ollama not running, or is something else sitting on its port?

    probe() collapses every failure into "down", and those two cases need opposite
    fixes: one is "start Ollama", the other is "something already owns 11434 and
    starting Ollama will not help until you find out what". Telling them apart takes a
    raw socket and costs nothing.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(base())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 11434)

    try:
        with socket.create_connection((host, port), timeout=2.0):
            listening = True
    except OSError as exc:
        return {
            "listening": False,
            "host": host,
            "port": port,
            "verdict": "nothing_listening",
            "detail": f"Nothing is accepting connections on {host}:{port} ({exc.__class__.__name__}).",
            "fix": "Ollama is not running. Start it, or install: winget install Ollama.Ollama",
        }

    # Something is there. Is it Ollama?
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(base() + "/api/tags")
        body = resp.text[:200]
        if resp.status_code < 400 and "models" in body:
            return {
                "listening": listening,
                "host": host,
                "port": port,
                "verdict": "ollama",
                "detail": "Ollama is answering on its own port.",
            }
        return {
            "listening": listening,
            "host": host,
            "port": port,
            "verdict": "port_taken",
            "status": resp.status_code,
            "body": body,
            "detail": (
                f"Something is listening on {host}:{port} but it does not answer /api/tags "
                f"like Ollama (HTTP {resp.status_code}). The port is taken by another service."
            ),
            "fix": (
                f"Find the owner:  Get-NetTCPConnection -LocalPort {port} -State Listen | "
                "Select-Object OwningProcess | ForEach-Object { Get-Process -Id $_.OwningProcess }  "
                "Then stop it, or point OLLAMA_HOST at a free port in .env."
            ),
        }
    except Exception as exc:
        return {
            "listening": listening,
            "host": host,
            "port": port,
            "verdict": "port_taken",
            "detail": (
                f"Something holds {host}:{port} but does not speak HTTP the way Ollama does "
                f"({type(exc).__name__}). The port is taken by another service."
            ),
            "fix": (
                f"Find the owner:  Get-NetTCPConnection -LocalPort {port} -State Listen | "
                "Select-Object OwningProcess | ForEach-Object { Get-Process -Id $_.OwningProcess }  "
                "Then stop it, or point OLLAMA_HOST at a free port in .env."
            ),
        }


def probe(*, force: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force and _probe["ok"] is not None and now - float(_probe["checked"] or 0) < 30:
        return _probe
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(base() + "/api/tags")
        if resp.status_code >= 400:
            _probe.update(ok=False, reason=f"http_{resp.status_code}", checked=now, models=[])
            return _probe
        names = [m.get("name") for m in (resp.json().get("models") or []) if m.get("name")]
        wanted = model()
        has = any(n == wanted or n.startswith(wanted + ":") for n in names)
        _probe.update(
            ok=bool(names),
            reason="ready" if has else ("no_model" if names else "empty"),
            checked=now,
            models=names,
            model=wanted,
            has_model=has,
        )
    except Exception as exc:
        _probe.update(ok=False, reason="down", checked=now, models=[], error=str(exc)[:200])
    return _probe


def embed(text: str, *, model: str | None = None) -> list[float]:
    tag = model or config.OLLAMA_EMBED_MODEL or "nomic-embed-text"
    snippet = (text or "")[:4000]
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(base() + "/api/embed", json={"model": tag, "input": snippet})
        if resp.status_code >= 400:
            resp = client.post(base() + "/api/embeddings", json={"model": tag, "prompt": snippet})
    if resp.status_code >= 400:
        raise RuntimeError(f"embed {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    vec = data.get("embedding")
    if not vec and data.get("embeddings"):
        vec = data["embeddings"][0]
    return [float(x) for x in (vec or [])]


def chat(messages: list[dict], *, tools: list[dict] | None = None, timeout: float = 180.0) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model(), "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(base() + "/api/chat", json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"ollama {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    msg = data.get("message") or {}
    return {
        "text": msg.get("content") or "",
        "tool_calls": msg.get("tool_calls") or [],
        "model": data.get("model") or model(),
        "raw": data,
    }


def as_tools(fn_tools: list[dict]) -> list[dict]:
    out = []
    for t in fn_tools:
        if t.get("type") != "function":
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.get("name"),
                    "description": t.get("description") or "",
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def pull(name: str | None = None) -> dict:
    tag = name or model()
    with httpx.Client(timeout=600.0) as client:
        resp = client.post(base() + "/api/pull", json={"name": tag, "stream": False})
    if resp.status_code >= 400:
        return {"ok": False, "error": resp.text[:500], "model": tag}
    return {"ok": True, "model": tag, "status": resp.json()}
