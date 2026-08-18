from __future__ import annotations

import json
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from . import config, memory, tools, xai
from .agents import conductor_system
from .brain import _parse_args


def session_config(session_id: str, voice: str | None = None) -> dict[str, Any]:
    mind = memory.snapshot(session_id, max_chars=8000)
    instructions = conductor_system(mind) + (
        "\nYou are speaking aloud as a beautiful, educated woman — calm, clear, unhurried."
        "\nKeep turns tight — two to four sentences unless asked for more."
        "\nNever repeat a sentence you just said. Do not restate the user's question."
        "\nUse tools when the question needs the live world or GitHub."
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
                "silence_duration_ms": 900,
                "prefix_padding_ms": 280,
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


async def handle_live(ws: WebSocket, session_id: str, voice: str | None = None) -> None:
    await ws.accept()
    if not config.XAI_API_KEY:
        await ws.send_json({"type": "error", "message": "XAI_API_KEY is not set."})
        await ws.close()
        return

    url = f"{config.XAI_REALTIME}?model={config.VOICE_MODEL or 'grok-voice-think-fast-2.0'}"
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}"}
    pending: dict[str, dict[str, Any]] = {}

    try:
        async with websockets.connect(url, additional_headers=headers, max_size=8_000_000) as upstream:
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

            async def pump_down() -> None:
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        await ws.send_bytes(raw)
                        continue
                    event = json.loads(raw)
                    etype = event.get("type")
                    if etype in ("response.output_audio.delta", "response.audio.delta"):
                        await ws.send_json({"type": "audio", "data": event.get("delta")})
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
                    elif etype == "response.function_call_arguments.done":
                        name = event.get("name")
                        call_id = event.get("call_id")
                        args = _parse_args(event.get("arguments"))
                        pending[call_id] = {"name": name, "args": args}
                        await ws.send_json({"type": "tool_call", "name": name, "arguments": args})
                        try:
                            result = tools.execute(name, args, session_id=session_id, agent_id="jarvis")
                        except Exception as exc:
                            result = {"error": str(exc)}
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
                        await upstream.send(json.dumps({"type": "response.create"}))
                    elif etype == "error":
                        await ws.send_json({"type": "error", "message": event.get("error") or event})
                    elif etype in ("session.updated", "session.created", "conversation.created"):
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
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
