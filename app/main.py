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
    # The event half of autonomy. beat() handles timers; this makes a vault edit
    # fire immediately instead of waiting for the next tick.
    from . import events as _events

    _events.watch_vault()
    # Subscribing is the half that was missing. The watcher has always run; without
    # this it emitted into an empty registry, so nothing was ever event-driven and
    # learning only happened when its timer came round.
    _events.wire_defaults()
except Exception:
    pass
try:
    from . import daily as daily_mod

    daily_mod.seed_owner()
except Exception:
    pass
try:
    # Reconcile the tracked capability goals against what is actually installed.
    # Nothing called this before, so a capability could ship and the goal stayed
    # open forever — which is precisely what kept happening. Runs last, after the
    # event sources are up, or the event-driven probe would read an empty registry.
    from . import gaps as _gaps

    _BOOT_GAPS = _gaps.sync()
except Exception as _exc:  # pragma: no cover - boot must never die on this
    _BOOT_GAPS = {"error": str(_exc)[:200]}

app = FastAPI(title="Super Jarvis", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")

_OPEN_PATHS = {
    "/",
    "/favicon.ico",
    "/api/health",
    "/api/health/full",
    "/api/voice/selftest",
    "/api/voice/log",
    "/api/tools/audit",
    "/api/guard/bootstrap",
    "/diag",
}


def _closest_route(path: str) -> str | None:
    """Did they just mistype it?

    "/api/voice/selftes" is not a route, so the guard correctly refused it and then
    sent the user off to git pull — for a missing letter. A near-miss against the real
    route table is a far more likely explanation than a stale process, and it is
    cheap to check.
    """
    import difflib

    candidates = {
        r.path
        for r in app.routes
        if getattr(r, "path", "").startswith("/api/") and "{" not in getattr(r, "path", "")
    }
    match = difflib.get_close_matches(_canonical(path), candidates, n=1, cutoff=0.8)
    return match[0] if match else None


def _canonical(path: str) -> str:
    """Trailing slashes are a typing habit, not a different endpoint.

    FastAPI would redirect /api/voice/log/ to /api/voice/log, but the guard runs before
    routing ever happens - so the slash version was rejected as an unknown path and the
    401 told the user to go and pull. Strip it before deciding anything.
    """
    return path[:-1] if len(path) > 1 and path.endswith("/") else path


def _route_exists(path: str) -> bool:
    """Does this build actually serve this path?

    The guard runs before routing, so a 401 cannot tell you whether the endpoint is
    token-protected or simply absent. That distinction is the whole point of the
    message: "needs a token" and "your process predates this route, pull and restart"
    are different problems, and blaming staleness for an ordinary guarded endpoint
    sends people chasing a pull they do not need.

    Matched against the compiled route regexes so parameterised routes
    (/api/thing/{id}) count as existing.
    """
    path = _canonical(path)
    for route in app.routes:
        rx = getattr(route, "path_regex", None)
        if rx is not None:
            if rx.fullmatch(path):
                return True
        elif _canonical(getattr(route, "path", "")) == path:
            return True
    return False


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
    if _canonical(path) in _OPEN_PATHS:
        return await call_next(request)
    if path.startswith("/api/"):
        given = request.headers.get("x-jarvis-token") or request.query_params.get("token")
        if not guard.token_ok(given):
            # "jarvis locked" alone sent people hunting for a crash that was not
            # there. Say what is missing and how to get it. The token itself is
            # never echoed — only the ways to obtain one.
            known = _route_exists(path)
            near = None if known else _closest_route(path)
            return JSONResponse(
                {
                    "error": "jarvis locked",
                    "reason": (
                        "This endpoint needs the fortress token."
                        if known
                        else f"No token supplied, and {path} is not a route on this build "
                        "(it is not an open path either)."
                    ),
                    "how_to_unlock": [
                        "Open the HUD at http://127.0.0.1:8787 — it carries the token for you.",
                        "Or append ?token=<JARVIS_TOKEN> to the URL.",
                        "Or send it as the x-jarvis-token header.",
                        "The token is JARVIS_TOKEN in .env, or GET /api/guard/bootstrap from this machine.",
                    ],
                    "open_paths": sorted(_OPEN_PATHS),
                    "hint": (
                        None
                        if known
                        else f"Did you mean {near}? That route exists on this build."
                        if near
                        else "If you expected this path to be open, the running process predates it — "
                        "git pull and restart, since the old build is still serving."
                    ),
                },
                status_code=401,
            )
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
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_secret: str | None = None
    ms_client_id: str | None = None
    ms_tenant: str | None = None
    ibkr_port: int | None = None
    ibkr_live: bool | None = None
    marketbeast_root: str | None = None
    publer_api_key: str | None = None
    publer_workspace_id: str | None = None
    klaviyo_api_key: str | None = None
    manychat_api_token: str | None = None
    clickfunnels_api_key: str | None = None
    clickfunnels_api_base: str | None = None


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


@app.get("/api/health/full")
def health_full() -> dict:
    """Deep check: which brain path is live and why, every voice prerequisite, subsystems.

    Deliberately on the open-paths list beside /api/health. When the brain is degraded
    the HUD chat is exactly what you cannot use to ask why, so this has to be reachable
    from a browser without one.
    """
    from . import health as health_mod

    return health_mod.check()


@app.get("/diag")
def diagnostics_page() -> Response:
    """The browser half of the diagnosis, which the server cannot see.

    /api/health/full and /api/voice/selftest both come back clean while the HUD still
    says nothing — because the remaining failures live in the browser: a stale token in
    localStorage, a suspended AudioContext, a refused microphone, a stream that closes
    without an event. This page runs the whole chain from inside the browser and prints
    a copyable result, instead of another round of guessing.
    """
    return Response(
        (config.WEB_DIR / "diag.html").read_text(encoding="utf-8"),
        media_type="text/html",
    )


@app.get("/api/voice/log")
def voice_log() -> dict:
    """The live-voice event log from this run, without fighting the console window.

    Open beside the other voice checks: copying a live, mid-stream console window is
    the last thing anyone should be asked to do while trying to work out why voice is
    silent.
    """
    from .voice_live import recent_log

    return recent_log()


@app.get("/api/voice/selftest")
async def voice_selftest(profile: str = "full") -> dict:
    """Ask xAI directly whether it accepts our live-voice session.

    Open beside the health checks on purpose: this is what you reach for when voice is
    the thing that is broken, and the whole point is that it works without the HUD.
    It makes one outbound socket to xAI and reads config; it changes nothing.
    """
    from .voice_live import VOICE_PROFILES, selftest

    if profile not in VOICE_PROFILES:
        return {"ok": False, "error": f"unknown profile {profile!r}", "profiles": list(VOICE_PROFILES)}
    return await selftest(profile=profile)


@app.get("/api/catalysts")
def api_catalysts(limit: int = 30, symbols: str = "") -> dict:
    """Tradeable catalysts on the world wires right now, with their expected horizons."""
    from . import catalyst as catalyst_mod

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] or None
    return catalyst_mod.scan(limit=limit, symbols=syms)


@app.get("/api/scout")
def api_scout(symbol: str, bias: str = "auto", min_dte: int = 7, max_dte: int = 60) -> dict:
    """Best option trade on a symbol across the 7-60 DTE window, ranked on base rates."""
    from . import scout as scout_mod

    return scout_mod.hunt(symbol, bias=bias, min_dte=min_dte, max_dte=max_dte)


@app.get("/api/risk")
def api_risk() -> dict:
    """Where today stands against the daily loss limit, and whether trading is halted."""
    from . import risk as risk_mod

    return risk_mod.state()


@app.post("/api/risk/halt")
def api_risk_halt(reason: str = "manual kill switch") -> dict:
    """Stop all new orders now. Closing positions is never blocked.

    A POST with no token requirement beyond the fortress guard, deliberately: the kill
    switch has to be reachable in a hurry, and every second spent finding a credential
    is a second the position is still open.
    """
    from . import risk as risk_mod

    return risk_mod.halt(reason)


@app.post("/api/risk/resume")
def api_risk_resume(reason: str = "") -> dict:
    """Clear a halt. A human decision, never automatic."""
    from . import risk as risk_mod

    return risk_mod.resume(reason)


@app.get("/api/backtest")
def api_backtest(symbol: str, setup: str = "", action: str = "sweep", range: str = "5y") -> dict:
    """Historical record for a setup, or every setup on a symbol ranked by expectancy."""
    from . import backtest as backtest_mod

    return backtest_mod.dispatch(action, symbol=symbol, setup=setup, range=range)


@app.get("/api/tools/audit")
def tools_audit() -> dict:
    """Is the tool payload we hand the model actually well formed?

    Two tools were declared under the name "oss" with mutually exclusive action enums.
    A duplicate name passes session validation and then breaks generation, and it had
    already happened once before in this file with "universe". Worth a check that runs.
    """
    from collections import Counter

    from . import tools as tools_mod

    names = [t.get("name") for t in tools_mod.FUNCTION_TOOLS]
    dupes = {n: c for n, c in Counter(names).items() if c > 1}
    return {
        "ok": not dupes,
        "count": len(names),
        "duplicates": dupes or None,
        "payload_bytes": len(tools_mod.dumps(tools_mod.FUNCTION_TOOLS)),
        "note": (
            "Two entries sharing a name give the model conflicting schemas for one function."
            if dupes
            else "No duplicate function names."
        ),
    }


@app.get("/api/status")
def status() -> dict:
    github = None
    try:
        github = github_client.whoami()
    except Exception as exc:
        github = {
            "error": str(exc)[:240],
            "hint": "Repo is already https://github.com/rkenagy-ops/jarvis-system — do not Import. Run gh auth login or paste a repo-scoped token in KEYS.",
            "repo": "rkenagy-ops/jarvis-system",
        }
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
    if body.x_api_key:
        updates["X_API_KEY"] = body.x_api_key
    if body.x_api_secret:
        updates["X_API_SECRET"] = body.x_api_secret
    if body.x_access_token:
        updates["X_ACCESS_TOKEN"] = body.x_access_token
    if body.x_access_secret:
        updates["X_ACCESS_SECRET"] = body.x_access_secret
    if body.ms_client_id:
        updates["MS_CLIENT_ID"] = body.ms_client_id
    if body.ms_tenant:
        updates["MS_TENANT"] = body.ms_tenant
    if body.ibkr_port:
        updates["IBKR_PORT"] = str(int(body.ibkr_port))
    if body.ibkr_live is True:
        updates["IBKR_LIVE"] = "true"
    if body.ibkr_live is False:
        updates["IBKR_LIVE"] = "false"
    if body.marketbeast_root:
        updates["MARKETBEAST_ROOT"] = body.marketbeast_root
    if body.publer_api_key:
        updates["PUBLER_API_KEY"] = body.publer_api_key
    if body.publer_workspace_id:
        updates["PUBLER_WORKSPACE_ID"] = body.publer_workspace_id
    if body.klaviyo_api_key:
        updates["KLAVIYO_API_KEY"] = body.klaviyo_api_key
    if body.manychat_api_token:
        updates["MANYCHAT_API_TOKEN"] = body.manychat_api_token
    if body.clickfunnels_api_key:
        updates["CLICKFUNNELS_API_KEY"] = body.clickfunnels_api_key
    if body.clickfunnels_api_base:
        updates["CLICKFUNNELS_API_BASE"] = body.clickfunnels_api_base
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
    """Transcribe one spoken turn: xAI first, a local whisper container if it isn't reachable.

    xai.transcribe() needs XAI_API_KEY and a live call to api.x.ai — the same
    dependency chat has. When that path is unavailable (no key, JARVIS_OFFLINE=true, or
    the call itself fails), fall back to the whisper container docker-compose.yml
    already provisions (see app/local_voice.py) instead of returning nothing. This is
    the REST single-turn endpoint, not the live realtime socket in app/voice_live.py —
    that one is a different, bidirectional-streaming problem this does not solve.
    """
    data = await file.read()
    filename = file.filename or "audio.webm"
    mime = file.content_type or "audio/webm"
    xai_error = "xai unavailable (no key, or OFFLINE is true)"
    if config.XAI_API_KEY and not config.OFFLINE:
        try:
            text = xai.transcribe(data, filename=filename, mime=mime)
            return {"text": text, "source": "xai"}
        except Exception as exc:
            # Fall through to the local whisper container rather than failing outright.
            xai_error = str(exc)[:200]

    from . import local_voice

    if not local_voice.available():
        return {
            "text": "",
            "error": (
                f"No STT path available. xAI: {xai_error}. Local whisper not reachable at "
                f"{config.WHISPER_BASE_URL} — run: docker compose up whisper"
            ),
        }
    text = local_voice.transcribe(data, filename=filename, mime=mime)
    return {"text": text, "source": "local_whisper"}


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


@app.get("/api/ibkr")
def api_ibkr() -> dict:
    from . import ibkr

    return ibkr.account()


@app.get("/api/ibkr/status")
def api_ibkr_status() -> dict:
    from . import ibkr

    return ibkr.probe()


@app.get("/api/options")
def api_options(top: int = 8, universe: str = "liquid", dte: int = 7) -> dict:
    from . import marketbeast

    return marketbeast.best_calls(top=top, universe=universe, dte=dte)


@app.get("/api/desk")
def api_desk(top: int = 6, dte: int = 7) -> dict:
    from . import intel

    return intel.advise(top=top, dte=dte)


@app.get("/api/poly")
def api_poly(q: str = "", limit: int = 8) -> dict:
    from . import poly

    if q:
        return poly.scan(query=q, limit=limit)
    return poly.bounce(limit=limit)


@app.get("/api/stack")
def api_stack() -> dict:
    from . import stack

    return stack.status()


@app.get("/api/bots")
def api_bots() -> dict:
    from . import bots

    return bots.roster()


class OptionOrderIn(BaseModel):
    symbol: str
    expiry: str
    strike: float
    right: str = "C"
    qty: int = 1
    limit: float | None = None
    confirm_token: str | None = None


@app.post("/api/ibkr/option")
def api_ibkr_option(body: OptionOrderIn) -> dict:
    from . import ibkr

    return ibkr.place_option(
        body.symbol,
        body.expiry,
        body.strike,
        body.right,
        body.qty,
        limit=body.limit,
        confirm_token=body.confirm_token,
    )


class StockOrderIn(BaseModel):
    symbol: str
    side: str = "buy"
    qty: float = 1
    limit: float | None = None
    confirm_token: str | None = None


@app.post("/api/ibkr/order")
def api_ibkr_stock(body: StockOrderIn) -> dict:
    from . import ibkr

    return ibkr.place_stock(
        body.symbol,
        body.side,
        body.qty,
        limit=body.limit,
        confirm_token=body.confirm_token,
    )


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


@app.get("/api/finish")
def api_finish() -> dict:
    from . import finish

    return finish.checklist()


@app.get("/api/wordpress")
def api_wordpress() -> dict:
    from . import ops

    return ops.wordpress_probe()


@app.post("/api/backup")
def api_backup() -> dict:
    from . import backup

    return backup.run()


@app.get("/api/microsoft")
def api_ms() -> dict:
    from . import msgraph

    return msgraph.status()


@app.post("/api/microsoft/login")
def api_ms_login() -> dict:
    from . import msgraph

    return msgraph.start_device()


@app.get("/api/microsoft/calendar")
def api_ms_cal() -> dict:
    from . import msgraph

    return msgraph.calendar_today()


@app.post("/api/microsoft/sync")
def api_ms_sync() -> dict:
    from . import msgraph

    return msgraph.sync_calendar()


class MailIn(BaseModel):
    to: str
    subject: str
    body: str = ""


@app.post("/api/microsoft/send")
def api_ms_send(body: MailIn) -> dict:
    from . import msgraph

    return msgraph.send_mail(body.to, body.subject, body.body)


@app.post("/api/rag/embed")
def api_rag_embed() -> dict:
    return rag.embed_vault()


@app.get("/api/ollama")
def api_ollama() -> dict:
    return ollama_mod.probe(force=True)


@app.post("/api/ollama/pull")
def api_ollama_pull() -> dict:
    return ollama_mod.pull()


@app.get("/api/tasks")
def tasks_list() -> dict:
    return {"tasks": obsidian.list_tasks(open_only=True)}


class MeetingIn(BaseModel):
    title: str = ""
    transcript: str = ""
    attendees: str = ""


@app.post("/api/meetings")
def api_meeting_file(body: MeetingIn) -> dict:
    from . import meetings as meetings_mod

    return meetings_mod.file_minutes(body.transcript, title=body.title, attendees=body.attendees)


@app.get("/api/meetings")
def api_meeting_list() -> dict:
    from . import meetings as meetings_mod

    return meetings_mod.list_recent()


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
