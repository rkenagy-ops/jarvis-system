"""Losing voice must not mean losing Jarvis.

`voice_live` used to `import websockets` at module scope, and `main` imports
`voice_live` at the top of its own import block. So a missing or broken websockets
did not disable voice — it stopped the server from starting at all, which is why
"lost her voice" and "isn't responding" arrived as one symptom. It also meant
health.voice(), whose whole job is to report this, could never run to report it.
"""

import builtins
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("fastapi")


def _hide_websockets(monkeypatch):
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name == "websockets" or name.startswith("websockets."):
            raise ModuleNotFoundError("No module named 'websockets'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    monkeypatch.delitem(sys.modules, "websockets", raising=False)


def test_voice_live_imports_without_websockets(monkeypatch):
    _hide_websockets(monkeypatch)
    monkeypatch.delitem(sys.modules, "app.voice_live", raising=False)
    mod = importlib.import_module("app.voice_live")
    assert hasattr(mod, "handle_live"), "the module must still expose its entry point"


def test_the_websockets_import_is_deferred():
    """A module-level import here is what coupled voice to the whole server."""
    src = (ROOT / "app" / "voice_live.py").read_text(encoding="utf-8")
    top = [
        line
        for line in src.splitlines()
        if line.startswith("import websockets") or line.startswith("from websockets")
    ]
    assert not top, f"websockets must not be imported at module scope: {top}"


def test_missing_websockets_is_reported_over_the_socket(monkeypatch):
    """The failure has to arrive where it was asked for, naming the fix."""
    import asyncio

    from app import voice_live

    _hide_websockets(monkeypatch)

    sent: list[dict] = []
    closed: list[bool] = []

    class FakeWS:
        async def accept(self):
            return None

        async def send_json(self, payload):
            sent.append(payload)

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(voice_live.config, "XAI_API_KEY", "key")
    asyncio.run(voice_live.handle_live(FakeWS(), "s1"))

    assert closed, "the socket must be closed, not left hanging"
    assert sent and sent[0]["type"] == "error"
    assert "websockets" in sent[0]["message"]
    assert "pip install websockets" in sent[0]["message"], "say how to fix it"


def test_health_can_still_report_the_missing_package(monkeypatch):
    """The point of deferring: the check that names this problem now gets to run."""
    from app import health

    _hide_websockets(monkeypatch)
    out = health.voice()
    assert out["ok"] is False
    assert any("websockets" in b for b in out["blockers"])


def test_auto_response_is_declared_not_assumed():
    """Auto-response after a committed turn is what separates "she transcribed me"
    from "she answered me". Leaving it to a server default is how you get a session
    that hears perfectly and never speaks."""
    from app import voice_live

    td = voice_live.session_config("s")["session"]["turn_detection"]
    assert td["create_response"] is True
    assert td["interrupt_response"] is True


def test_the_session_still_carries_the_tools():
    """No tools in the session means she answers but never runs anything."""
    from app import voice_live

    names = {t.get("name") or t.get("type") for t in voice_live.session_config("s")["session"]["tools"]}
    assert "web_search" in names
    assert len(names) > 10, "the function tools must ride along with the voice session"
    assert "spawn_agents" not in names, "voice must not spawn a swarm mid-sentence"
