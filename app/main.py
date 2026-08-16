from __future__ import annotations

import json
import uuid
from fastapi import FastAPI, File, Form, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, config, github_client, memory, xai
from .agents import list_public
from .brain import think, think_events
from .voice_live import handle_live

memory.init()

app = FastAPI(title="Super Jarvis", version=__version__)
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    agent: str = "jarvis"


class SettingsIn(BaseModel):
    xai_api_key: str | None = None
    github_token: str | None = None
    github_username: str | None = None
    voice: str | None = None
    owner_name: str | None = None


class RememberIn(BaseModel):
    content: str
    kind: str = "note"
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.6


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__, **config.status()}


@app.get("/api/status")
def status() -> dict:
    github = None
    if config.GITHUB_TOKEN:
        try:
            github = github_client.whoami()
        except Exception as exc:
            github = {"error": str(exc)}
    return {
        **config.status(),
        "github": github,
        "agents": list_public(),
        "memory": memory.dashboard(),
        "voices": [
            "orion", "eve", "atlas", "ara", "leo", "luna", "rex", "iris",
            "helios", "celeste", "sirius", "aurora", "zenith",
        ],
    }


@app.post("/api/settings")
def save_settings(body: SettingsIn) -> dict:
    updates = {}
    if body.xai_api_key:
        updates["XAI_API_KEY"] = body.xai_api_key
    if body.github_token:
        updates["GITHUB_TOKEN"] = body.github_token
    if body.github_username:
        updates["GITHUB_USERNAME"] = body.github_username
    if body.voice:
        updates["JARVIS_VOICE"] = body.voice
    if body.owner_name:
        updates["JARVIS_OWNER_NAME"] = body.owner_name
    if updates:
        config.save_env(updates)
    if config.GITHUB_TOKEN and not config.GITHUB_USERNAME:
        try:
            me = github_client.whoami()
            if me.get("login"):
                config.save_env({"GITHUB_USERNAME": me["login"]})
        except Exception:
            pass
    return {"ok": True, **config.status()}


@app.get("/api/agents")
def agents() -> dict:
    return {"agents": list_public()}


@app.get("/api/memory")
def memory_dash() -> dict:
    return memory.dashboard()


@app.post("/api/memory")
def memory_write(body: RememberIn) -> dict:
    return memory.remember(body.content, kind=body.kind, tags=body.tags, importance=body.importance, source_agent="user")


@app.get("/api/memory/search")
def memory_search(q: str = "", limit: int = 12) -> dict:
    return {"results": memory.search(q, limit=limit)}


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    session_id = body.session_id or str(uuid.uuid4())
    result = think(body.message, session_id=session_id, agent_id=body.agent or "jarvis")
    result["session_id"] = session_id
    return result


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())

    def gen():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        for event in think_events(body.message, session_id, body.agent or "jarvis"):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/voice/stt")
async def stt(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    text = xai.transcribe(data, filename=file.filename or "audio.webm", mime=file.content_type or "audio/webm")
    return {"text": text}


@app.post("/api/voice/tts")
async def tts(text: str = Form(...), voice: str | None = Form(None)) -> Response:
    audio = xai.speak(text, voice_id=voice)
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/api/voice/session")
def voice_session() -> dict:
    return xai.ephemeral_token(300)


@app.websocket("/ws/live")
async def live(ws: WebSocket, session_id: str = "live", voice: str | None = None) -> None:
    await handle_live(ws, session_id, voice)


@app.get("/api/github/me")
def github_me() -> dict:
    try:
        return github_client.whoami()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    run()
