from __future__ import annotations

import json
import logging
import time
from collections import deque
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from . import config, memory, tools
from .agents import conductor_system
from .brain import _parse_args, _run_tool

# Voice failures used to reach only the browser console. The server log is what
# gets pasted when something is wrong, and it said nothing about voice at all.
log = logging.getLogger("jarvis.voice")


class _Ring(logging.Handler):
    """Keep the last N voice log lines in memory so a URL can show them.

    The server console is where these lines land, and a live console window mid-stream
    is a miserable thing to scroll and copy out of - which is exactly what you are
    asked to do at the worst moment. Holding them here costs nothing and turns the
    diagnosis into opening a page.
    """

    def __init__(self, limit: int = 300) -> None:
        super().__init__()
        self.lines: deque[str] = deque(maxlen=limit)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
            self.lines.append(f"{stamp} {record.levelname} {record.getMessage()}")
        except Exception:
            pass  # a logging handler that raises would take the socket down with it


RING = _Ring()
log.addHandler(RING)
log.setLevel(logging.INFO)


def recent_log() -> dict[str, Any]:
    """What xAI has actually sent on this run, in order, newest last."""
    lines = list(RING.lines)
    return {
        "lines": lines,
        "count": len(lines),
        "note": (
            "Empty means live voice has not been started since the server booted - "
            "press the live button and say one sentence, then reload this."
            if not lines
            else "Look for 'response.created'. If it never appears, xAI is not generating "
            "a response for your turn. If 'binary audio frames' appears, the audio is "
            "arriving in that encoding."
        ),
    }


def _websockets():
    """Import the client library on demand.

    This used to be a module-level import, and main.py imports this module at the top
    of its own import block — so a missing or broken `websockets` did not merely
    disable voice, it stopped the whole app from starting. That is the difference
    between "Jarvis lost her voice" and "Jarvis is not responding", and it made the
    two indistinguishable. Worse, health.voice() reports exactly this condition and
    could never run to report it. Now the failure stays inside voice, and the answer
    arrives over the socket that asked for it.
    """
    import websockets  # noqa: PLC0415 - deliberately deferred

    return websockets


def session_config(session_id: str, voice: str | None = None) -> dict[str, Any]:
    mind = memory.snapshot(session_id, max_chars=8000)
    instructions = conductor_system(mind) + (
        "\nYou are speaking aloud as a beautiful, educated woman — calm, clear, unhurried."
        "\nKeep turns tight — two sentences unless asked for more. Trade advice: first word ENTER or NO-GO, then one reason."
        "\nNever repeat a sentence you just said. Do not restate the user's question. Do not read tables or JSON aloud."
        "\nUse tools when the question needs the live world, markets, or GitHub. For should-I-enter, call market action=advise."
        "\nPronounce GitHub as Git Hub. Pronounce J.A.R.V.I.S. as Jarvis."
    )
    fn_tools = [t for t in tools.FUNCTION_TOOLS if t["name"] != "spawn_agents"]
    return {
        "type": "session.update",
        "session": {
            "voice": voice or config.VOICE,
            "instructions": instructions,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.75,
                "silence_duration_ms": 550,
                "prefix_padding_ms": 280,
                # Stated outright rather than left to the server default. Auto-response
                # after a committed turn is the single thing standing between "she
                # transcribed me" and "she answered me", and a default is not something
                # to be relying on for it.
                "create_response": True,
                "interrupt_response": True,
            },
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
            },
            "tools": [
                {"type": "web_search"},
                {"type": "x_search"},
                *fn_tools,
            ],
            "resumption": {"enabled": True},
        },
    }


async def selftest(timeout: float = 12.0) -> dict[str, Any]:
    """Open the real realtime socket, send our real session config, report the answer.

    health.voice() checks prerequisites — a key, a URL, the package. It cannot tell you
    whether xAI *accepted* the session, and that is the failure that looks like "she
    hears me but never answers": the transcript comes back because the socket is up,
    while the session.update that carries the voice and the 38 tools was rejected, so
    no response is ever generated. This asks the question directly.
    """
    if not config.XAI_API_KEY:
        return {"ok": False, "stage": "config", "error": "XAI_API_KEY is not set."}
    if config.OFFLINE:
        return {"ok": False, "stage": "config", "error": "OFFLINE is true, so the socket is never opened."}
    try:
        websockets = _websockets()
    except Exception as exc:
        return {"ok": False, "stage": "import", "error": f"websockets will not import: {exc}"}

    import asyncio

    loop = asyncio.get_running_loop()
    url = f"{config.XAI_REALTIME}?model={config.VOICE_MODEL or 'grok-voice-think-fast-2.0'}"
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}"}
    seen: list[str] = []
    try:
        async with websockets.connect(url, additional_headers=headers, max_size=8_000_000) as upstream:
            cfg = session_config("selftest")
            await upstream.send(json.dumps(cfg))
            deadline = loop.time() + timeout
            while loop.time() < deadline:
                remaining = deadline - loop.time()
                raw = await asyncio.wait_for(upstream.recv(), timeout=max(0.1, remaining))
                if isinstance(raw, bytes):
                    continue
                event = json.loads(raw)
                etype = event.get("type") or ""
                seen.append(etype)
                if etype == "session.updated":
                    return {
                        "ok": True,
                        "stage": "session",
                        "events": seen,
                        "tools_offered": len(cfg["session"]["tools"]),
                        "voice": cfg["session"]["voice"],
                        "note": "xAI accepted the session. If voice is still silent the problem is in the browser: microphone permission, or the tab is muted.",
                    }
                if etype == "error":
                    return {
                        "ok": False,
                        "stage": "session",
                        "events": seen,
                        "error": event.get("error") or event,
                        "note": "The socket opened but xAI rejected our session config, so no response is ever generated. That is why she transcribes you and never answers.",
                    }
    except Exception as exc:
        return {"ok": False, "stage": "connect", "events": seen, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    return {"ok": False, "stage": "session", "events": seen, "error": f"No session.updated within {timeout}s."}


async def handle_live(ws: WebSocket, session_id: str, voice: str | None = None) -> None:
    await ws.accept()
    if not config.XAI_API_KEY:
        await ws.send_json({"type": "error", "message": "XAI_API_KEY is not set."})
        await ws.close()
        return

    try:
        websockets = _websockets()
    except Exception as exc:
        await ws.send_json({
            "type": "error",
            "message": (
                f"Live voice needs the websockets package and it will not import ({exc}). "
                "Run: .venv\\Scripts\\python.exe -m pip install websockets"
            ),
        })
        await ws.close()
        return

    url = f"{config.XAI_REALTIME}?model={config.VOICE_MODEL or 'grok-voice-think-fast-2.0'}"
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}"}
    pending: dict[str, dict[str, Any]] = {}

    try:
        async with websockets.connect(url, additional_headers=headers, max_size=8_000_000) as upstream:
            log.info("live voice connected to %s", config.XAI_REALTIME)
            await upstream.send(json.dumps(session_config(session_id, voice)))
            await ws.send_json({"type": "ready", "voice": voice or config.VOICE})

            async def pump_up() -> None:
                try:
                    while True:
                        message = await ws.receive()
                        if message.get("type") == "websocket.disconnect":
                            break
                        if message.get("bytes"):
                            await upstream.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": __import__("base64").b64encode(message["bytes"]).decode("ascii"),
                            }))
                            continue
                        raw = message.get("text")
                        if not raw:
                            continue
                        event = json.loads(raw)
                        etype = event.get("type")
                        if etype == "audio":
                            await upstream.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": event.get("data") or "",
                            }))
                        elif etype == "text" and event.get("text"):
                            memory.add_message(session_id, "user", event["text"])
                            await upstream.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": event["text"]}],
                                },
                            }))
                            await upstream.send(json.dumps({"type": "response.create"}))
                        elif etype == "config":
                            await upstream.send(json.dumps(session_config(session_id, event.get("voice"))))
                except WebSocketDisconnect:
                    return

            # The nudge below exists because of the exact symptom this file kept
            # producing: the socket is up, the turn commits, the transcript of what you
            # said comes back — and no response is ever generated. Auto-response after a
            # committed turn is requested in the session config, but if it does not
            # happen there is nothing in the protocol that tells you so. Asking for the
            # response outright after a short grace period turns a silent hang into a
            # reply, and logs that it was needed.
            import asyncio as _asyncio

            state = {"response_active": False, "nudge": None}

            async def nudge_after_commit() -> None:
                try:
                    await _asyncio.sleep(2.0)
                except _asyncio.CancelledError:
                    return
                if state["response_active"]:
                    return
                log.warning(
                    "no response 2s after the turn committed - asking for one explicitly. "
                    "create_response in turn_detection is not being honoured."
                )
                await upstream.send(json.dumps({"type": "response.create"}))

            def arm_nudge() -> None:
                if state["nudge"] and not state["nudge"].done():
                    state["nudge"].cancel()
                state["nudge"] = _asyncio.create_task(nudge_after_commit())

            async def pump_down() -> None:
                audio_kind = None
                seen_types: set[str] = set()
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        # xAI may deliver audio as binary rather than base64 deltas. The
                        # server forwarded these and the HUD had no consumer for them, so
                        # they were parsed as JSON, threw, and were dropped. Relayed with
                        # a marker so the client knows to play them as PCM16.
                        if "binary-audio" not in seen_types:
                            seen_types.add("binary-audio")
                            log.info("xai realtime is sending binary audio frames (%d bytes)", len(raw))
                        await ws.send_bytes(raw)
                        continue
                    event = json.loads(raw)
                    etype = event.get("type") or ""
                    if etype not in seen_types:
                        seen_types.add(etype)
                        log.info("xai realtime event: %s", etype)
                    if etype == "response.created":
                        state["response_active"] = True
                        if state["nudge"] and not state["nudge"].done():
                            state["nudge"].cancel()
                    elif etype in ("response.done", "response.completed", "response.cancelled"):
                        state["response_active"] = False
                    if etype in ("response.output_audio.delta", "response.audio.delta"):
                        if audio_kind and audio_kind != etype:
                            continue
                        audio_kind = etype
                        await ws.send_json({"type": "audio", "data": event.get("delta")})
                    elif etype in ("response.done", "response.completed"):
                        audio_kind = None
                    elif etype in (
                        "response.output_audio_transcript.delta",
                        "response.audio_transcript.delta",
                    ):
                        await ws.send_json({"type": "assistant_delta", "text": event.get("delta") or ""})
                    elif etype in (
                        "response.output_audio_transcript.done",
                        "response.audio_transcript.done",
                    ):
                        text = event.get("transcript") or ""
                        if text:
                            memory.add_message(session_id, "assistant", text, agent="jarvis")
                        await ws.send_json({"type": "assistant", "text": text})
                    elif etype == "conversation.item.input_audio_transcription.completed":
                        text = event.get("transcript") or ""
                        if text:
                            memory.add_message(session_id, "user", text)
                        await ws.send_json({"type": "user", "text": text})
                        arm_nudge()
                    elif etype in ("input_audio_buffer.committed", "input_audio_buffer.speech_stopped"):
                        arm_nudge()
                    elif etype == "response.function_call_arguments.done":
                        name = event.get("name")
                        call_id = event.get("call_id")
                        args = _parse_args(event.get("arguments"))
                        pending[call_id] = {"name": name, "args": args}
                        await ws.send_json({"type": "tool_call", "name": name, "arguments": args})
                        result = _run_tool(name, args, session_id=session_id, agent_id="jarvis")
                        await ws.send_json({"type": "tool_result", "name": name, "result": result})
                        await upstream.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": tools.dumps(result),
                            },
                        }))
                        # Wait is handled client-side; request continuation.
                        state["response_active"] = False
                        await upstream.send(json.dumps({"type": "response.create"}))
                    elif etype == "error":
                        detail = event.get("error") or event
                        log.error("xai realtime error: %s", detail)
                        await ws.send_json({"type": "error", "message": detail})
                    elif etype in ("session.updated", "session.created", "conversation.created"):
                        log.info("xai realtime %s", etype)
                        await ws.send_json({"type": "status", "event": etype})

            import asyncio

            up = asyncio.create_task(pump_up())
            down = asyncio.create_task(pump_down())
            done, pending_tasks = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending_tasks:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, (WebSocketDisconnect, websockets.ConnectionClosed)):
                    await ws.send_json({"type": "error", "message": str(exc)})
    except Exception as exc:
        log.exception("live voice failed: %s", exc)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
