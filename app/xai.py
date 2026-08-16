from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from . import config


class XAIError(RuntimeError):
    pass


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


def speak(text: str, voice_id: str | None = None, language: str = "en") -> bytes:
    payload = {
        "text": text[:4000],
        "voice_id": voice_id or config.VOICE,
        "language": language,
    }
    with httpx.Client(timeout=60.0) as client:
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
