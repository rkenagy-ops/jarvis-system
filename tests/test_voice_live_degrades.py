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


# --- the silent-turn failure --------------------------------------------------

SRC = (ROOT / "app" / "voice_live.py").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


def test_a_committed_turn_that_draws_no_response_gets_nudged():
    """The exact symptom: the socket is up, the turn commits, the transcript of what
    you said comes back, and no response is ever generated. Nothing in the protocol
    reports that, so ask for the response outright rather than hang."""
    assert "async def nudge_after_commit" in SRC
    assert "def arm_nudge" in SRC
    assert '"type": "response.create"' in SRC


def test_the_nudge_is_armed_from_every_end_of_turn_signal():
    for signal in (
        "conversation.item.input_audio_transcription.completed",
        "input_audio_buffer.committed",
        "input_audio_buffer.speech_stopped",
    ):
        assert signal in SRC, f"{signal} should arm the nudge"


def test_a_real_response_cancels_the_nudge():
    """Nudging over a response already in flight would talk over her."""
    assert 'if etype == "response.created"' in SRC
    assert 'state["nudge"].cancel()' in SRC


def test_upstream_event_types_are_logged_once_each():
    """The server log is the only record of what xAI actually sends. It said nothing."""
    assert "seen_types" in SRC
    assert 'log.info("xai realtime event: %s", etype)' in SRC


def test_voice_tools_go_through_the_shared_wrapper():
    assert "_run_tool(name, args" in SRC
    assert "tools.execute(" not in SRC, "voice must use the same guarded tool path as chat"


def test_the_client_consumes_binary_frames():
    """The server forwards them with send_bytes. Nothing received them, so if xAI
    delivers audio as binary rather than base64 deltas, that was every word she spoke."""
    assert "await ws.send_bytes(raw)" in SRC, "the server still forwards binary"
    assert "function playPcmBuffer" in JS
    assert 'ws.binaryType = "arraybuffer"' in JS
    assert "playPcmBuffer(m.data)" in JS, "binary frames must reach the player"


def test_both_audio_paths_share_one_scheduler():
    """Two schedulers would mean two clocks, which is the bug we just fixed."""
    assert JS.count("state.playTime += audio.duration") == 1


def test_the_voice_log_is_readable_from_a_url():
    """Copying a live console window mid-stream is the last thing to ask of anyone
    trying to work out why voice is silent."""
    from app import main as main_mod
    from fastapi.testclient import TestClient

    assert "/api/voice/log" in main_mod._OPEN_PATHS
    client = TestClient(main_mod.app, base_url="http://127.0.0.1")
    body = client.get("/api/voice/log").json()
    assert "lines" in body and isinstance(body["lines"], list)
    assert body["note"], "an empty log must explain that it is empty, not just look broken"


def test_the_ring_actually_captures_what_is_logged():
    from app import voice_live

    voice_live.log.info("xai realtime event: response.created")
    assert any("response.created" in line for line in voice_live.RING.lines)


def test_the_ring_is_bounded():
    """An unbounded buffer on a long-running server is a slow leak."""
    from app import voice_live

    assert voice_live.RING.lines.maxlen and voice_live.RING.lines.maxlen <= 1000


def test_a_broken_log_record_cannot_take_down_the_socket():
    """Scoped to our handler. Other handlers on the chain are not ours to promise for."""
    import logging

    from app import voice_live

    class Exploding:
        def __str__(self):
            raise RuntimeError("nope")

    record = logging.LogRecord("jarvis.voice", logging.INFO, __file__, 1, "%s", (Exploding(),), None)
    voice_live.RING.emit(record)  # must not raise
