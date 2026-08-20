from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

import time

from . import config


class XAIError(RuntimeError):
    pass


_probe: dict[str, Any] = {"ok": None, "reason": "untested", "checked": 0.0}


def probe(*, force: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force and _probe["ok"] is not None and now - _probe["checked"] < 90:
        return _probe
    if not config.XAI_API_KEY:
        _probe.update(ok=False, reason="no_key", checked=now)
        return _probe
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(
                f"{config.XAI_BASE}/responses",
                headers=_headers(),
                json={"model": config.MODEL, "input": "ok"},
            )
        if resp.status_code == 200:
            _probe.update(ok=True, reason="ready", checked=now)
        elif resp.status_code in {401, 403}:
            _probe.update(ok=False, reason="credits_or_auth", checked=now)
        else:
            # Unknown — let Grok try; free fallback still catches errors.
            _probe.update(ok=True, reason=f"http_{resp.status_code}", checked=now)
    except Exception:
        _probe.update(ok=False, reason="network", checked=now)
    return _probe


def _headers() -> dict[str, str]:
    if not config.XAI_API_KEY:
        raise XAIError("XAI_API_KEY is not set. Add your SpaceXAI key from https://console.x.ai")
    return {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}


def responses_create(payload: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{config.XAI_BASE}/responses", headers=_headers(), json=payload)
    if resp.status_code >= 400:
        raise XAIError(f"xAI {resp.status_code}: {resp.text[:1200]}")
    return resp.json()


def responses_stream(payload: dict[str, Any], timeout: float = 180.0) -> Iterator[dict[str, Any]]:
    body = dict(payload)
    body["stream"] = True
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", f"{config.XAI_BASE}/responses", headers=_headers(), json=body) as resp:
            if resp.status_code >= 400:
                raise XAIError(f"xAI {resp.status_code}: {resp.read().decode('utf-8', 'replace')[:1200]}")
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue


def transcribe(file_bytes: bytes, filename: str = "audio.webm", mime: str = "audio/webm") -> str:
    if not config.XAI_API_KEY:
        raise XAIError("XAI_API_KEY is not set.")
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}"}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{config.XAI_BASE}/stt",
            headers=headers,
            files={"file": (filename, file_bytes, mime)},
        )
    if resp.status_code >= 400:
        raise XAIError(f"STT {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    return data.get("text") or data.get("transcript") or ""


def spoken_excerpt(text: str, limit: int = 180) -> str:
    """Short spoken turn. Cuts lag — two sentences, no dumps."""
    import re

    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", raw)
    cleaned = re.sub(r"[#*_>`]+", " ", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    out = []
    for part in parts:
        if not part:
            continue
        low = part.lower()
        if any(low == prev.lower() or prev.lower().endswith(low) for prev in out):
            continue
        out.append(part)
        if len(" ".join(out)) >= limit or len(out) >= 2:
            break
    spoken = " ".join(out).strip()
    return spoken[:limit]


def speak(text: str, voice_id: str | None = None, language: str = "en") -> bytes:
    spoken = spoken_excerpt(text)
    payload = {
        "text": spoken or "Ready.",
        "voice_id": voice_id or config.VOICE,
        "language": language,
    }
    with httpx.Client(timeout=18.0) as client:
        resp = client.post(f"{config.XAI_BASE}/tts", headers=_headers(), json=payload)
    if resp.status_code >= 400:
        raise XAIError(f"TTS {resp.status_code}: {resp.text[:800]}")
    return resp.content


def ephemeral_token(seconds: int = 300) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{config.XAI_BASE}/realtime/client_secrets",
            headers=_headers(),
            json={"expires_after": {"seconds": seconds}},
        )
    if resp.status_code >= 400:
        raise XAIError(f"ephemeral {resp.status_code}: {resp.text[:800]}")
    return resp.json()


def imagine(prompt: str, filename: str | None = None) -> dict[str, Any]:
    payload = {"model": "grok-imagine-image-2.0", "prompt": prompt, "n": 1}
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(f"{config.XAI_BASE}/images/generations", headers=_headers(), json=payload)
    if resp.status_code >= 400:
        raise XAIError(f"imagine {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    item = (data.get("data") or [{}])[0]
    url = item.get("url")
    b64 = item.get("b64_json")
    out_dir = config.WORKSPACE_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = filename or f"imagine-{abs(hash(prompt)) % 10**8}.png"
    if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        name += ".png"
    dest = out_dir / name
    if url:
        img = httpx.get(url, timeout=60.0)
        img.raise_for_status()
        dest.write_bytes(img.content)
    elif b64:
        import base64

        dest.write_bytes(base64.b64decode(b64))
    else:
        return {"error": "No image payload", "raw": data}
    try:
        from . import obsidian

        obsidian.write_note(
            f"Sources/{dest.stem}.md",
            f"---\ntype: image\n---\n\n# {prompt[:80]}\n\n![[{dest.as_posix()}]]\n\nPrompt: {prompt}\n",
        )
    except Exception:
        pass
    return {"ok": True, "path": str(dest), "prompt": prompt, "url": url}


def extract_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return str(response["output_text"])
    chunks: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    chunks.append(part["text"])
                elif isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    return "".join(chunks).strip()


def extract_function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for item in response.get("output") or []:
        if item.get("type") in ("function_call", "custom_tool_call"):
            calls.append(
                {
                    "call_id": item.get("call_id") or item.get("id"),
                    "name": item.get("name"),
                    "arguments": item.get("arguments") or "{}",
                }
            )
    return calls
