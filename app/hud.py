"""Persistent native HUD window, instead of a browser tab you must remember to keep open.

The HUD is a FastAPI app on 127.0.0.1:8787. That works, but it lives in a tab: close it
by accident and Jarvis is still running with nothing showing it. This wraps the same page
in a real OS window with its own taskbar entry.

    python -m app.hud            # against an already-running Jarvis
    hud action=launch            # from the HUD itself, opens a detached window

pywebview is the light option — it renders the existing page in the platform webview, so
there is no second UI to maintain and the HUD stays one codebase. nicegui is accepted as
an alternative if that is what is installed.

The window is opened as a DETACHED SUBPROCESS by default. pywebview must own the main
thread on macOS and Windows, and uvicorn already owns it in the server process, so
launching in-process would deadlock one or the other.

Untested caveat, stated plainly: the actual window has never been opened by the author of
this file — it cannot be, from a headless Linux container. Everything around it (backend
selection, URL construction, token handling, subprocess launch, failure paths) is tested;
the pixels are not.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from . import config, guard

TITLE = "Super Jarvis"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 860


def backend() -> str | None:
    """Which native-window library is available, preferring the lighter one."""
    try:
        import webview  # noqa: F401

        return "pywebview"
    except ImportError:
        pass
    try:
        import nicegui  # noqa: F401

        return "nicegui"
    except ImportError:
        return None


def available() -> bool:
    return backend() is not None


def hud_url(with_token: bool = True) -> str:
    """The local HUD address, carrying the guard token so the window is not bounced."""
    host = "127.0.0.1"
    port = getattr(config, "PORT", 8787) or 8787
    url = f"http://{host}:{port}/"
    if with_token:
        try:
            token = guard.token()
        except Exception:
            token = ""
        if token:
            url = f"{url}?token={token}"
    return url


def launch(url: str = "", *, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> dict[str, Any]:
    """Open the window and block until it is closed. Must run on the main thread."""
    which = backend()
    if not which:
        return {
            "ok": False,
            "error": "No native-window library installed.",
            "fix": "pip install pywebview",
        }

    target = url or hud_url()
    if which == "pywebview":
        import webview

        webview.create_window(TITLE, target, width=width, height=height, text_select=True)
        webview.start()
        return {"ok": True, "backend": which, "url": target, "closed": True}

    # nicegui has no "wrap an existing page in a native window" primitive as direct as
    # pywebview's; opening it natively still needs pywebview underneath, so say so
    # rather than pretending nicegui alone is enough.
    return {
        "ok": False,
        "backend": which,
        "error": "nicegui is installed but native-window mode still needs pywebview.",
        "fix": "pip install pywebview",
    }


def launch_detached(url: str = "") -> dict[str, Any]:
    """Open the window in its own process.

    pywebview wants the main thread, and uvicorn already has it in the server process,
    so a detached child is the only way to open the window from a running Jarvis.
    """
    if not available():
        return {"ok": False, "error": "No native-window library installed.", "fix": "pip install pywebview"}

    target = url or hud_url()
    creationflags = 0
    if os.name == "nt":
        # Do not flash a console window on Windows.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.hud", target],
            cwd=str(config.ROOT),
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "error": f"could not start window process: {str(exc)[:200]}"}

    return {"ok": True, "backend": backend(), "pid": proc.pid, "url": target, "detached": True}


def status() -> dict[str, Any]:
    which = backend()
    return {
        "ok": True,
        "backend": which,
        "available": which is not None,
        "url": hud_url(with_token=False),
        "note": (
            "hud action=launch opens a native window in its own process."
            if which
            else "Install pywebview for a persistent native window: pip install pywebview"
        ),
    }


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    if act in {"status", "check"}:
        return status()
    if act in {"launch", "open", "window"}:
        return launch_detached(str(kwargs.get("url") or ""))
    return {"error": f"unknown hud action {act}", "actions": ["status", "launch"]}


if __name__ == "__main__":  # pragma: no cover - entry point, needs a display
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    result = launch(target)
    if not result.get("ok"):
        print(result.get("error"), file=sys.stderr)
        print(result.get("fix", ""), file=sys.stderr)
        sys.exit(1)
