from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, autonomy, catalog, config, feeds, github_client, github_oss, guard, markets, memory, obsidian, ollama as ollama_mod, opensource, ops, rag, widgets, workspace, xai
from .agents import list_public
from .brain import think, think_events
from .voice_live import handle_live

memory.init()
ops.init()
markets.init()
obsidian.init_vault()
rag.init()
try:
    rag.reindex_vault()
except Exception:
    pass
autonomy.start()
try:
    from . import daily as daily_mod

    daily_mod.seed_owner()
except Exception:
    pass

app = FastAPI(title="Super Jarvis", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")

_OPEN_PATHS = {"/", "/favicon.ico", "/api/health", "/api/guard/bootstrap"}


@app.middleware("http")
async def fortress(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static"):
        return await call_next(request)
    if not guard.host_ok(request.headers.get("host") or ""):
        return JSONResponse({"error": "bad host"}, status_code=403)
    if path == "/api/guard/bootstrap":
        client = request.client.host if request.client else ""
        if not guard.is_loopback_ip(client):
            return JSONResponse({"error": "bootstrap only from this machine"}, status_code=403)
        return await call_next(request)
    if path in _OPEN_PATHS:
        return await call_next(request)
    if path.startswith("/api/"):
        given = request.headers.get("x-jarvis-token") or request.query_params.get("token")
        if not guard.token_ok(given):
            return JSONResponse({"error": "jarvis locked"}, status_code=401)
    return await call_next(request)


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
    trading_mode: str | None = None
    wordpress_url: str | None = None
    wordpress_user: str | None = None
    wordpress_app_password: str | None = None
    x_bearer_token: str | None = None
    postiz_url: str | None = None
    alpaca_key_id: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_live: bool | None = None


class TradeIn(BaseModel):
    symbol: str
    side: str
    qty: float
    confirm_token: str | None = None


class ConfirmIn(BaseModel):
    token: str


class JobIn(BaseModel):
    name: str
    prompt: str
    every_sec: int = 1800


class GoalIn(BaseModel):
    title: str
    detail: str = ""
    priority: float = 0.5


class NoteIn(BaseModel):
    path: str
    content: str
    mode: str = "replace"


class TaskToggleIn(BaseModel):
    path: str
    line: int
    done: bool | None = None


class RememberIn(BaseModel):
    content: str
    kind: str = "note"
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.6


class ContentIn(BaseModel):
    title: str
    body: str
    kind: str = "post"
    platforms: list[str] = Field(default_factory=lambda: ["x"])


class ScheduleIn(BaseModel):
    id: str
    when: str
    platforms: list[str] | None = None


class PublishIn(BaseModel):
    id: str
    confirm_token: str | None = None


class ProductIn(BaseModel):
    title: str
    sku: str = ""
    asin: str = ""
    price: float | None = None
    url: str = ""
    bullets: list[str] = Field(default_factory=list)
    description: str = ""


class RoomHearIn(BaseModel):
    who: str = "room"
    text: str


class ReminderIn(BaseModel):
    title: str
    minutes: int = 0
    when: str = ""
    kind: str = "reminder"


class ReminderIdIn(BaseModel):
    id: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


def _brain_name() -> tuple[str, str]:
    if not config.OFFLINE and xai.probe().get("ok"):
        return "grok", xai.probe().get("reason") or "ready"
    ol = ollama_mod.probe()
    if ol.get("ok"):
        return "ollama", ol.get("reason") or "ready"
    if config.OFFLINE:
        return "offline", "ollama_down"
    return "free", xai.probe().get("reason") or "no_grok"


@app.post("/api/brain/refresh")
def brain_refresh() -> dict:
    xai.probe(force=True)
    ollama_mod.probe(force=True)
    name, reason = _brain_name()
    return {"brain": name, "reason": reason, "ollama": ollama_mod.probe()}


@app.get("/api/health")
def health() -> dict:
    name, reason = _brain_name()
    return {
        "ok": True,
        "version": __version__,
        **config.status(),
        "brain": name,
        "brain_reason": reason,
        "ollama": ollama_mod.probe(),
        "fortress": guard.posture(),
    }


@app.get("/api/status")
def status() -> dict:
    github = None
    if config.GITHUB_TOKEN:
        try:
            github = github_client.whoami()
        except Exception as exc:
            github = {"error": str(exc)}
    name, reason = _brain_name()
    return {
        **config.status(),
        "brain": name,
        "brain_reason": reason,
        "ollama": ollama_mod.probe(),
        "github": github,
        "agents": list_public(),
        "memory": memory.dashboard(),
        "fortress": guard.posture(),
        "online": not config.OFFLINE,
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
    if body.trading_mode in {"paper", "live"}:
        updates["TRADING_MODE"] = body.trading_mode
    if body.wordpress_url:
        updates["WORDPRESS_URL"] = body.wordpress_url
    if body.wordpress_user:
        updates["WORDPRESS_USER"] = body.wordpress_user
    if body.wordpress_app_password:
        updates["WORDPRESS_APP_PASSWORD"] = body.wordpress_app_password
    if body.x_bearer_token:
        updates["X_BEARER_TOKEN"] = body.x_bearer_token
    if body.postiz_url:
        updates["POSTIZ_URL"] = body.postiz_url
    if body.alpaca_key_id:
        updates["ALPACA_KEY_ID"] = body.alpaca_key_id
    if body.alpaca_secret_key:
        updates["ALPACA_SECRET_KEY"] = body.alpaca_secret_key
    if body.alpaca_live is True:
        updates["ALPACA_LIVE"] = "true"
    if body.alpaca_live is False:
        updates["ALPACA_LIVE"] = "false"
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
    try:
        result = think(body.message, session_id=session_id, agent_id=body.agent or "jarvis")
    except Exception as exc:
        return {"text": f"I hit a problem: {exc}", "session_id": session_id, "brain": "free", "error": str(exc)}
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
async def live(ws: WebSocket, session_id: str = "live", voice: str | None = None, token: str | None = None) -> None:
    if not guard.token_ok(token):
        await ws.close(code=4401)
        return
    await handle_live(ws, session_id, voice)


@app.get("/api/markets")
def markets_dash() -> dict:
    snap = feeds.snapshot()
    return {"watchlist": snap.get("quotes") or markets.watchlist(), "account": markets.account(), "updated": snap.get("updated")}


@app.get("/api/feeds")
def api_feeds() -> dict:
    return feeds.snapshot()


@app.get("/api/intel")
def api_intel() -> dict:
    from . import intel

    return intel.desk()


@app.get("/api/feeds/stream")
def api_feeds_stream() -> StreamingResponse:
    def gen():
        while True:
            payload = json.dumps(feeds.snapshot(), default=str)
            yield f"data: {payload}\n\n"
            time.sleep(20)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/markets/quote")
def markets_quote(symbol: str) -> dict:
    return markets.quote(symbol)


@app.get("/api/markets/analyze")
def markets_analyze(symbol: str, range: str = "6mo") -> dict:
    return markets.analyze(symbol, range)


@app.post("/api/markets/trade")
def markets_trade(body: TradeIn) -> dict:
    return markets.paper_trade(body.symbol, body.side, body.qty, confirm_token=body.confirm_token)


@app.post("/api/markets/confirm")
def markets_confirm(body: ConfirmIn) -> dict:
    return markets.confirm_trade(body.token)


@app.get("/api/autonomy")
def autonomy_dash() -> dict:
    return autonomy.snapshot()


@app.post("/api/autonomy/job")
def autonomy_job(body: JobIn) -> dict:
    return memory.add_job(body.name, body.prompt, body.every_sec)


@app.post("/api/goals")
def goals_add(body: GoalIn) -> dict:
    return memory.add_goal(body.title, body.detail, body.priority)


@app.post("/api/briefing")
def run_briefing() -> dict:
    text = autonomy.briefing()
    return {"ok": True, "text": text}


@app.get("/api/daily")
def api_daily() -> dict:
    from . import daily as daily_mod

    return daily_mod.pack()


@app.post("/api/daily/seed")
def api_daily_seed() -> dict:
    from . import daily as daily_mod

    return daily_mod.seed_owner()


@app.post("/api/daily/vault")
def api_daily_vault() -> dict:
    from . import daily as daily_mod

    return daily_mod.open_vault()


@app.post("/api/growth")
def api_growth() -> dict:
    from . import growth

    return growth.cycle(6)


@app.get("/api/ollama")
def api_ollama() -> dict:
    return ollama_mod.probe(force=True)


@app.post("/api/ollama/pull")
def api_ollama_pull() -> dict:
    return ollama_mod.pull()


@app.get("/api/tasks")
def tasks_list() -> dict:
    return {"tasks": obsidian.list_tasks(open_only=True)}


@app.post("/api/tasks/toggle")
def tasks_toggle(body: TaskToggleIn) -> dict:
    return obsidian.toggle_task(body.path, body.line, body.done)


@app.get("/api/vault")
def vault_list(folder: str = "") -> dict:
    return obsidian.list_notes(folder)


@app.get("/api/vault/search")
def vault_search(q: str) -> dict:
    return obsidian.search(q)


@app.get("/api/rag")
def rag_search(q: str) -> dict:
    return {"query": q, "hits": rag.retrieve(q)}


@app.post("/api/rag/reindex")
def rag_reindex() -> dict:
    return rag.reindex_vault()


@app.get("/api/vault/note")
def vault_note(path: str) -> dict:
    return obsidian.read_note(path)


@app.post("/api/vault/note")
def vault_write(body: NoteIn) -> dict:
    return obsidian.write_note(body.path, body.content, mode=body.mode)


@app.get("/api/vault/daily")
def vault_daily() -> dict:
    return obsidian.daily()


@app.get("/api/ops")
def ops_dash() -> dict:
    return ops.dashboard()


@app.post("/api/ops/draft")
def ops_draft(body: ContentIn) -> dict:
    return ops.draft(body.title, body.body, kind=body.kind, platforms=body.platforms)


@app.post("/api/ops/schedule")
def ops_schedule(body: ScheduleIn) -> dict:
    return ops.schedule(body.id, body.when, body.platforms)


@app.post("/api/ops/publish")
def ops_publish(body: PublishIn) -> dict:
    return ops.publish(body.id, confirm_token=body.confirm_token)


@app.post("/api/ops/product")
def ops_product(body: ProductIn) -> dict:
    return ops.add_product(
        body.title, sku=body.sku, asin=body.asin, price=body.price,
        url=body.url, bullets=body.bullets, description=body.description,
    )


@app.get("/api/opensource")
def opensource_status() -> dict:
    data = opensource.status()
    data["catalog"] = catalog.list_sources()
    return data


@app.get("/api/oss")
def oss_index() -> dict:
    return {"starter_pack": github_oss.STARTER_PACK, "awesome": list(github_oss.AWESOME)}


@app.get("/api/oss/search")
def oss_search(q: str, limit: int = 8) -> dict:
    return github_oss.search(q, limit)


@app.post("/api/oss/ingest")
def oss_ingest(repo: str) -> dict:
    return github_oss.ingest(repo)


@app.get("/api/catalog")
def catalog_list() -> dict:
    return {"sources": catalog.list_sources()}


@app.get("/api/catalog/{source}")
def catalog_call(source: str, q: str = "") -> dict:
    return catalog.call(source, q)


@app.get("/api/workspace")
def workspace_list(path: str = ".") -> dict:
    return workspace.list_files(path)


@app.post("/api/workspace/upload")
async def workspace_upload(file: UploadFile = File(...), dest: str = Form("inbox")) -> dict:
    name = Path(file.filename or "upload.bin").name
    rel = f"{dest.rstrip('/')}/{name}"
    data = await file.read()
    path = workspace.resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"ok": True, "path": rel, "bytes": len(data)}


@app.get("/api/widgets/weather")
def widget_weather() -> dict:
    return widgets.weather()


@app.get("/api/widgets/news")
def widget_news() -> dict:
    return widgets.news()


@app.get("/api/skills")
def api_skills() -> dict:
    from . import desktop, skills

    return {"skills": skills.catalog(), "help": skills.help_text(), "apps": desktop.ALLOWED_APPS}


@app.get("/api/room")
def api_room() -> dict:
    from . import room

    return {"context": room.context(), "lines": room.lines()}


@app.post("/api/room/hear")
def api_room_hear(body: RoomHearIn) -> dict:
    from . import room

    return room.hear(body.who, body.text)


@app.get("/api/reminders")
def api_reminders() -> dict:
    from . import reminders

    return reminders.snapshot()


@app.post("/api/reminders")
def api_reminders_add(body: ReminderIn) -> dict:
    from . import desktop

    if body.kind == "timer" or (body.minutes and not body.when):
        return desktop.timer(body.minutes or 5, body.title)
    return desktop.remind(body.title, body.when, body.minutes)


@app.post("/api/reminders/dismiss")
def api_reminders_dismiss(body: ReminderIdIn) -> dict:
    from . import reminders

    return {"ok": reminders.dismiss(body.id)}


@app.get("/api/widgets/now")
def widget_now() -> dict:
    return widgets.now()


@app.get("/api/github/me")
def github_me() -> dict:
    try:
        return github_client.whoami()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/guard/bootstrap")
def guard_bootstrap() -> dict:
    return {"token": guard.token(), "fortress": guard.posture()}


def run() -> None:
    import uvicorn

    guard.persist_token()
    config.save_env({"OLLAMA_HOST": config.OLLAMA_HOST, "OLLAMA_MODEL": config.OLLAMA_MODEL})
    host = guard.bind_host()
    uvicorn.run("app.main:app", host=host, port=config.PORT, reload=False)


if __name__ == "__main__":
    run()
