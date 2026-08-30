"""Local, offline speech-to-text via the docker-compose 'whisper' service.

xai.transcribe() (app/xai.py) is the primary STT path: it needs XAI_API_KEY and a
working call to api.x.ai. health.voice() said outright that when that path is down,
voice has nowhere else to go. docker-compose.yml already provisions a whisper ASR
container (onerahmet/openai-whisper-asr-webservice, loopback-bound at
WHISPER_BASE_URL) and .env.example already documents the URL — nothing in app/ ever
called it. This wires it in as a fallback for POST /api/voice/stt (one spoken turn,
transcribed to text and handed to the normal brain.think() waterfall, which already
falls back to Ollama/free_brain on its own) — not a replacement for the live realtime
socket in app/voice_live.py, which is a different, bidirectional-audio problem this
does not attempt to solve.

    docker compose up whisper

Caveat, stated plainly: this has not been exercised against a running whisper
container from the environment that wrote it — there is none here to test against.
The /asr endpoint contract (multipart 'audio_file', ?output=json returning
{"text": ...}) matches the onerahmet/openai-whisper-asr-webservice image named in
docker-compose.yml as of when this was written; worth a smoke test against the real
container before relying on it.
"""

from __future__ import annotations

import httpx

from . import config


def available() -> bool:
    """Is the local whisper ASR container actually answering right now?

    A cheap GET against the base URL, not a real transcription — meant for health
    checks and for deciding whether the fallback is worth attempting at all. Never
    raises: an unreachable container is a normal, expected state (nobody runs
    `docker compose up whisper` unless they want the fallback), not an error.
    """
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(config.WHISPER_BASE_URL)
        return resp.status_code < 500
    except Exception:
        return False


def transcribe(file_bytes: bytes, filename: str = "audio.webm", mime: str = "audio/webm") -> str:
    """POST audio to the local whisper-asr-webservice container, get text back.

    Runs entirely on loopback per docker-compose.yml's port binding — no API key, no
    outbound call, no audio leaving the machine. Raises on failure rather than
    swallowing it, same as app.xai.transcribe(), so the caller decides how to report it.
    """
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{config.WHISPER_BASE_URL.rstrip('/')}/asr",
            params={"output": "json"},
            files={"audio_file": (filename, file_bytes, mime)},
        )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("text") or "").strip()
