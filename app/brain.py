from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from . import config, free_brain, memory, tools, xai
from .agents import AGENTS, conductor_system, get, specialist_system

EventFn = Callable[[dict[str, Any]], None]


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _consume_stream(payload: dict[str, Any], emit: EventFn | None) -> dict[str, Any]:
    text_parts: list[str] = []
    calls: dict[str, dict[str, Any]] = {}
    response_id = None
    citations: list[str] = []
    final: dict[str, Any] = {}

    for event in xai.responses_stream(payload):
        etype = event.get("type") or ""
        if event.get("id") and etype in ("response.created", "response.in_progress"):
            response_id = event.get("id") or (event.get("response") or {}).get("id")
        resp = event.get("response")
        if isinstance(resp, dict):
            final = resp
            response_id = resp.get("id") or response_id
            if resp.get("citations"):
                citations = resp["citations"]

        if etype in ("response.output_text.delta", "response.text.delta"):
            delta = event.get("delta") or ""
            if delta:
                text_parts.append(delta)
                if emit:
                    emit({"type": "token", "text": delta})
        elif etype == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") in ("function_call", "custom_tool_call"):
                cid = item.get("call_id") or item.get("id")
                calls[cid] = {"call_id": cid, "name": item.get("name"), "arguments": item.get("arguments") or ""}
        elif etype in ("response.function_call_arguments.delta",):
            cid = event.get("call_id")
            if cid in calls:
                calls[cid]["arguments"] += event.get("delta") or ""
        elif etype in ("response.function_call_arguments.done",):
            cid = event.get("call_id") or event.get("item_id")
            calls[cid] = {
                "call_id": cid,
                "name": event.get("name") or (calls.get(cid) or {}).get("name"),
                "arguments": event.get("arguments") or (calls.get(cid) or {}).get("arguments") or "",
            }
            if emit:
                emit({"type": "tool_call", "name": calls[cid]["name"], "arguments": _parse_args(calls[cid]["arguments"])})
        elif etype == "response.completed":
            final = event.get("response") or final
            response_id = (final or {}).get("id") or response_id

    if not final:
        # fallback non-stream
        final = xai.responses_create({k: v for k, v in payload.items() if k != "stream"})
        response_id = final.get("id")
        text = xai.extract_text(final)
        if text and emit:
            emit({"type": "token", "text": text})
        return {
            "id": response_id,
            "text": text,
            "calls": xai.extract_function_calls(final),
            "citations": final.get("citations") or [],
            "raw": final,
        }

    text = "".join(text_parts).strip() or xai.extract_text(final)
    extracted = xai.extract_function_calls(final)
    merged = list(calls.values()) if calls else extracted
    if not merged:
        merged = extracted
    return {
        "id": response_id or final.get("id"),
        "text": text,
        "calls": merged,
        "citations": citations or final.get("citations") or [],
        "raw": final,
    }


def _run_model(
    *,
    agent_id: str,
    input_items: list[dict[str, Any]],
    allow_spawn: bool,
    emit: EventFn | None,
    previous_response_id: str | None = None,
) -> dict[str, Any]:
    agent = get(agent_id)
    payload: dict[str, Any] = {
        "model": agent.model or config.MODEL,
        "input": input_items,
        "tools": tools.tools_for(agent_id, allow_spawn=allow_spawn),
        "store": True,
    }
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    return _consume_stream(payload, emit)


def _handle_spawn(task: str, agent_ids: list[str], session_id: str, emit: EventFn | None) -> list[dict[str, Any]]:
    chosen = [a for a in agent_ids if a in AGENTS and a != "jarvis"][:8]
    if not chosen:
        return [{"error": "No valid specialists requested."}]
    if emit:
        emit({"type": "swarm", "agents": chosen, "task": task})

    def run_one(aid: str) -> dict[str, Any]:
        if emit:
            emit({"type": "agent_start", "agent": aid})
        result = think(
            task,
            session_id=session_id,
            agent_id=aid,
            allow_spawn=False,
            persist_user=False,
            emit=lambda ev: emit({**ev, "agent": aid}) if emit else None,
        )
        insight = result.get("text") or ""
        memory.add_insight(aid, insight[:1200], session_id=session_id, evidence=task, confidence=0.75)
        if emit:
            emit({"type": "insight", "agent": aid, "text": insight})
            emit({"type": "agent_done", "agent": aid})
        return {"agent": aid, "text": insight, "citations": result.get("citations") or []}

    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(chosen))) as pool:
        futs = {pool.submit(run_one, aid): aid for aid in chosen}
        for fut in as_completed(futs):
            try:
                out.append(fut.result())
            except Exception as exc:
                out.append({"agent": futs[fut], "error": str(exc)})
    return out


def think(
    user_text: str,
    *,
    session_id: str,
    agent_id: str = "jarvis",
    allow_spawn: bool = True,
    persist_user: bool = True,
    emit: EventFn | None = None,
    max_rounds: int = 8,
) -> dict[str, Any]:
    user_text = (user_text or "").strip()
    if not user_text:
        return {"text": "I am listening.", "agent": agent_id, "citations": [], "calls": []}
    if persist_user:
        memory.add_message(session_id, "user", user_text)

    if config.OFFLINE:
        if emit:
            emit({"type": "status", "text": "offline mode — free APIs only"})
        result = free_brain.handle(user_text, emit=emit)
        final = result.get("text") or "Offline brain had nothing to add."
        memory.add_message(session_id, "assistant", final, agent=agent_id)
        if persist_user and agent_id == "jarvis":
            memory.learn_from_turn(user_text, final, result.get("calls") or [])
        if emit:
            emit({"type": "done", "agent": agent_id, "text": final, "citations": [], "calls": result.get("calls") or [], "brain": "offline"})
        return {"text": final, "agent": agent_id, "citations": [], "calls": result.get("calls") or [], "brain": "offline"}

    probe = xai.probe()
    if not probe.get("ok"):
        if emit:
            emit({"type": "status", "text": f"grok offline ({probe.get('reason')}) — free APIs"})
        result = free_brain.handle(user_text, emit=emit)
        final = result.get("text") or "Free brain had nothing to add."
        memory.add_message(session_id, "assistant", final, agent=agent_id)
        if persist_user and agent_id == "jarvis":
            memory.learn_from_turn(user_text, final, result.get("calls") or [])
        if emit:
            emit({"type": "done", "agent": agent_id, "text": final, "citations": [], "calls": result.get("calls") or [], "brain": "free"})
        return {"text": final, "agent": agent_id, "citations": [], "calls": result.get("calls") or [], "brain": "free"}

    mind = memory.snapshot(session_id)
    try:
        from . import desktop

        mind = desktop.situation() + "\n\n" + mind
    except Exception:
        pass
    try:
        from . import room

        mind = room.context() + "\n\n" + mind
    except Exception:
        pass
    try:
        from . import obsidian

        mind = mind + "\n\n" + obsidian.context_pack(user_text)
    except Exception:
        pass
    try:
        from . import rag

        pack = rag.pack(user_text)
        if pack:
            mind = mind + "\n\n" + pack
    except Exception:
        pass
    try:
        from . import graph, router

        mind = mind + "\n\n" + router.hint(user_text) + "\n\n" + graph.pack(user_text)
    except Exception:
        pass

    try:
        return _think_grok(
            user_text,
            session_id=session_id,
            agent_id=agent_id,
            allow_spawn=allow_spawn,
            persist_user=persist_user,
            emit=emit,
            max_rounds=max_rounds,
            mind=mind,
        )
    except xai.XAIError as exc:
        if emit:
            emit({"type": "status", "text": f"grok error — free APIs ({exc})"})
        xai._probe.update(ok=False, reason="credits_or_auth", checked=__import__("time").time())
        result = free_brain.handle(user_text, emit=emit)
        final = result.get("text") or str(exc)
        memory.add_message(session_id, "assistant", final, agent=agent_id)
        if emit:
            emit({"type": "done", "agent": agent_id, "text": final, "citations": [], "calls": result.get("calls") or [], "brain": "free"})
        return {"text": final, "agent": agent_id, "citations": [], "calls": result.get("calls") or [], "brain": "free"}


def _think_grok(
    user_text: str,
    *,
    session_id: str,
    agent_id: str,
    allow_spawn: bool,
    persist_user: bool,
    emit: EventFn | None,
    max_rounds: int,
    mind: str,
) -> dict[str, Any]:
    if agent_id == "jarvis":
        system = conductor_system(mind)
    else:
        system = specialist_system(agent_id, mind)

    if emit:
        emit({"type": "agent_start", "agent": agent_id})
        emit({"type": "status", "text": f"{get(agent_id).name} online — mind loaded"})

    input_items: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]

    all_calls: list[dict[str, Any]] = []
    citations: list[Any] = []
    last_text = ""
    previous = None

    for _round in range(max_rounds):
        result = _run_model(
            agent_id=agent_id,
            input_items=input_items,
            allow_spawn=allow_spawn and agent_id == "jarvis",
            emit=emit,
            previous_response_id=previous,
        )
        previous = result.get("id")
        last_text = result.get("text") or last_text
        citations.extend(result.get("citations") or [])
        calls = [c for c in (result.get("calls") or []) if c.get("name")]
        if not calls:
            break

        outputs: list[dict[str, Any]] = []
        for call in calls:
            args = _parse_args(call.get("arguments"))
            name = call["name"]
            all_calls.append({"name": name, "arguments": args})
            if name == "spawn_agents" and allow_spawn and agent_id == "jarvis":
                spawned = _handle_spawn(args.get("task") or user_text, args.get("agents") or [], session_id, emit)
                payload = spawned
            else:
                payload = tools.execute(name, args, session_id=session_id, agent_id=agent_id)
            if emit:
                emit({"type": "tool_result", "name": name, "result": payload})
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.get("call_id"),
                    "output": tools.dumps(payload),
                }
            )
        input_items = outputs

    final = last_text or ("I finished the tool work." if all_calls else "I'm here. What should we do?")
    memory.add_message(session_id, "assistant", final, agent=agent_id)
    if persist_user and agent_id == "jarvis":
        memory.learn_from_turn(user_text, final, all_calls)
    if emit:
        emit({"type": "done", "agent": agent_id, "text": final, "citations": citations, "calls": all_calls})
    return {"text": final, "agent": agent_id, "citations": citations, "calls": all_calls, "brain": "grok"}


def think_events(user_text: str, session_id: str, agent_id: str = "jarvis") -> Iterator[dict[str, Any]]:
    queue: list[dict[str, Any]] = []

    def emit(ev: dict[str, Any]) -> None:
        queue.append(ev)

    try:
        think(user_text, session_id=session_id, agent_id=agent_id, emit=emit)
    except Exception as exc:
        queue.append({"type": "error", "message": str(exc)})
        queue.append({"type": "done", "text": f"I hit a problem: {exc}", "agent": agent_id})

    yield from queue
