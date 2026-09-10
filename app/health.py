"""Is Jarvis actually operational? One check, one payload, no guessing.

"Jarvis lost its voice and isn't responding" has half a dozen possible causes spread
across four subsystems, and each one fails quietly in its own way — a missing key, a
model that was never pulled, an expired credit balance, a websocket dependency. Working
that out by asking questions back and forth is slow.

This probes each subsystem for real and reports which path a request would actually take
right now, why, and what to do about it. Every probe is read-only and none of them raise:
a health check that can itself crash is worthless precisely when you need it.

    health action=check    everything
    health action=brain    just the LLM path
    health action=voice    just live voice
"""

from __future__ import annotations

import importlib
import platform
import sys
from typing import Any

from . import config


def _try(fn, default=None):
    """Probes must never raise — a broken check is worse than no check."""
    try:
        return fn()
    except Exception as exc:
        return default if default is not None else {"error": f"{type(exc).__name__}: {str(exc)[:150]}"}


def brain() -> dict[str, Any]:
    """Which path would a chat request take right now, and does it work?"""
    out: dict[str, Any] = {"offline_mode": bool(config.OFFLINE)}

    # --- Grok / xAI, the primary
    xai_key = bool(config.XAI_API_KEY)
    out["xai"] = {"key_set": xai_key}
    if xai_key:
        probe = _try(lambda: importlib.import_module("app.xai").probe(force=True), {})
        reason = probe.get("reason") if isinstance(probe, dict) else None
        out["xai"]["ok"] = bool(isinstance(probe, dict) and probe.get("ok"))
        out["xai"]["reason"] = reason
        if reason == "credits_or_auth":
            out["xai"]["fix"] = "The key was rejected (401/403). Out of credits, or the key was revoked or mistyped."
        elif reason == "no_key":
            out["xai"]["fix"] = "XAI_API_KEY is empty in .env."
        elif reason and reason != "ready":
            out["xai"]["fix"] = f"xAI answered but not with 200: {reason}. Usually transient; retry."
    else:
        out["xai"]["ok"] = False
        out["xai"]["reason"] = "no_key"
        out["xai"]["fix"] = "Set XAI_API_KEY in .env, or paste it in the HUD KEYS panel."

    # --- Ollama, the local fallback
    ol: dict[str, Any] = {"host": getattr(config, "OLLAMA_HOST", None)}
    probe = _try(lambda: importlib.import_module("app.ollama").probe(), {})
    if isinstance(probe, dict):
        ol["up"] = bool(probe.get("ok"))
        ol["models"] = probe.get("models")
        ol["reason"] = probe.get("reason") or probe.get("error")
    if not ol.get("up"):
        # "Ollama is not answering" covered two different problems with one sentence.
        # Nothing listening and someone else holding the port need opposite fixes.
        diag = _try(lambda: importlib.import_module("app.ollama").diagnose(), {})
        if isinstance(diag, dict) and diag.get("verdict"):
            ol["diagnosis"] = diag.get("verdict")
            ol["detail"] = diag.get("detail")
            ol["fix"] = diag.get("fix") or "Ollama is not answering."
        else:
            ol["fix"] = "Ollama is not answering. Start it, or install: winget install Ollama.Ollama"
    elif not ol.get("models"):
        ol["fix"] = f"Ollama is up but no model is pulled. Run: ollama pull {getattr(config, 'OLLAMA_MODEL', 'llama3.2')}"
    out["ollama"] = ol

    # --- which one actually gets used
    if config.OFFLINE:
        path, why = "free_brain", "OFFLINE is true in .env, so the network path is skipped entirely."
    elif out["xai"].get("ok"):
        path, why = "grok", "xAI answered its probe."
    elif ol.get("up") and ol.get("models"):
        path, why = "ollama", f"xAI unavailable ({out['xai'].get('reason')}), falling back to the local model."
    else:
        path, why = (
            "free_brain",
            f"xAI unavailable ({out['xai'].get('reason')}) and Ollama has no model — "
            "answers will be thin and tools will not be called.",
        )
    out["active_path"] = path
    out["why"] = why
    out["healthy"] = path in {"grok", "ollama"}
    return out


def voice() -> dict[str, Any]:
    """Live voice needs more than a key. Check each prerequisite separately."""
    checks: dict[str, Any] = {}

    checks["websockets_installed"] = _try(
        lambda: bool(importlib.import_module("websockets")), False
    ) is not False
    checks["xai_key_set"] = bool(config.XAI_API_KEY)
    checks["realtime_url"] = getattr(config, "XAI_REALTIME", None)
    checks["voice_model"] = getattr(config, "VOICE_MODEL", None) or "grok-voice-think-fast-2.0"
    checks["voice"] = getattr(config, "VOICE", None)
    checks["offline"] = bool(config.OFFLINE)
    # Informational only — deliberately does not affect "ok"/"blockers" below. This is
    # the offline fallback for the single-turn POST /api/voice/stt endpoint (see
    # app/local_voice.py), not for the live realtime socket this function is otherwise
    # describing, so it would be misleading to let it clear a live-voice blocker.
    checks["local_whisper_configured"] = bool(getattr(config, "WHISPER_BASE_URL", None))
    checks["local_whisper_available"] = _try(
        lambda: importlib.import_module("app.local_voice").available(), False
    )

    blockers = []
    if not checks["websockets_installed"]:
        blockers.append("websockets is not installed — pip install websockets")
    if not checks["xai_key_set"]:
        blockers.append("XAI_API_KEY is not set; voice_live refuses the socket without it")
    if checks["offline"]:
        blockers.append("OFFLINE is true, so the realtime socket is never opened")
    if not checks["realtime_url"]:
        blockers.append("XAI_REALTIME is not configured")

    # A rejected key kills voice exactly as dead as a missing one, and looks different.
    if checks["xai_key_set"]:
        probe = _try(lambda: importlib.import_module("app.xai").probe(force=True), {})
        if isinstance(probe, dict) and not probe.get("ok"):
            blockers.append(
                f"XAI_API_KEY is set but was rejected ({probe.get('reason')}) — "
                "voice uses the same credential as chat, so it fails with it"
            )

    return {
        "ok": not blockers,
        "checks": checks,
        "blockers": blockers or None,
        "endpoint": "/api/voice/live (websocket)",
        "note": (
            "Live voice is a websocket to xAI realtime. It needs the same XAI_API_KEY as chat, "
            "so if chat is degraded voice is usually down for the same reason. Separately, "
            "POST /api/voice/stt (one spoken turn, not the live socket) falls back to a local "
            f"whisper container at {getattr(config, 'WHISPER_BASE_URL', '')} — "
            + ("reachable right now." if checks["local_whisper_available"] else "not reachable right now (docker compose up whisper).")
        ),
    }


def subsystems() -> dict[str, Any]:
    """Everything else, briefly."""
    out: dict[str, Any] = {}

    out["memory"] = _try(
        lambda: {
            "ok": True,
            "facts": len(importlib.import_module("app.memory").get_facts()),
            "open_goals": len(importlib.import_module("app.memory").list_goals("open")),
        }
    )
    out["autonomy"] = _try(
        lambda: {
            "enabled": bool(config.AUTONOMY_ENABLED),
            "jobs": len(importlib.import_module("app.memory").list_jobs()),
            "handlers": len(importlib.import_module("app.autonomy").JOB_HANDLERS),
        }
    )
    out["events"] = _try(
        lambda: {
            "sources": {
                k: v.get("kind") for k, v in (getattr(importlib.import_module("app.events"), "SOURCES", {}) or {}).items()
            },
            "subscriptions": sum(
                len(v) for v in (getattr(importlib.import_module("app.events"), "SUBSCRIPTIONS", {}) or {}).values()
            ),
        }
    )
    out["ibkr"] = _try(
        lambda: {
            "client_library": importlib.import_module("app.ibkr").ib_backend(),
            "live": bool(config.IBKR_LIVE),
        }
    )
    out["vault"] = _try(
        lambda: {"path": str(config.VAULT_DIR), "exists": config.VAULT_DIR.exists()}
    )
    out["rag"] = _try(lambda: {"ok": bool(importlib.import_module("app.rag"))})
    out["tools"] = _try(
        lambda: {"count": len(importlib.import_module("app.tools").tools_for("jarvis", allow_spawn=True))}
    )
    return out


def check() -> dict[str, Any]:
    """The whole picture, with the headline first."""
    b = brain()
    v = voice()
    subs = subsystems()

    problems = []
    if not b.get("healthy"):
        problems.append(f"Brain degraded: {b.get('why')}")
    if not v.get("ok"):
        problems.extend(f"Voice: {x}" for x in (v.get("blockers") or []))
    if not (subs.get("events") or {}).get("sources"):
        problems.append("No event sources running — vault changes will not fire jobs.")

    return {
        "ok": not problems,
        "verdict": (
            "Fully operational."
            if not problems
            else f"{len(problems)} problem(s) — see 'problems'."
        ),
        "problems": problems or None,
        "brain": b,
        "voice": v,
        "subsystems": subs,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "version": _try(lambda: importlib.import_module("app").__version__, "?"),
        },
    }


def dispatch(action: str = "check", **kwargs: Any) -> Any:
    act = (action or "check").lower()
    if act in {"check", "all", "status", "full"}:
        return check()
    if act in {"brain", "llm", "chat"}:
        return brain()
    if act in {"voice", "live", "speech"}:
        return voice()
    if act in {"subsystems", "subs"}:
        return subsystems()
    return {"error": f"unknown health action {act}", "actions": ["check", "brain", "voice", "subsystems"]}
