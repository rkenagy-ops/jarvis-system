"""'Ollama is not answering' covered two problems that need opposite fixes.

Nothing listening means start Ollama. Something else holding the port means starting
Ollama will not help until you find out what has it. The probe collapsed both into
"down", so the reported fix was wrong half the time.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import ollama


def test_nothing_listening_is_named_as_such(monkeypatch):
    import socket

    def refuse(*a, **k):
        raise ConnectionRefusedError("nope")

    monkeypatch.setattr(socket, "create_connection", refuse)
    out = ollama.diagnose()
    assert out["verdict"] == "nothing_listening"
    assert out["listening"] is False
    assert "start it" in out["fix"].lower() or "not running" in out["fix"].lower()


def test_a_stranger_on_the_port_is_distinguished(monkeypatch):
    """Something answers, but not like Ollama. Starting Ollama will not fix this."""
    import socket

    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: FakeSock())

    class FakeResp:
        status_code = 200
        text = "<html>Some other service entirely</html>"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return FakeResp()

    monkeypatch.setattr(ollama.httpx, "Client", lambda **k: FakeClient())
    out = ollama.diagnose()
    assert out["verdict"] == "port_taken"
    assert out["listening"] is True
    assert "11434" in out["fix"], "the fix has to name the port to look up"
    assert "Get-NetTCPConnection" in out["fix"], "give the command, not a description of it"


def test_a_real_ollama_is_recognised(monkeypatch):
    import socket

    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: FakeSock())

    class FakeResp:
        status_code = 200
        text = '{"models": [{"name": "llama3.2"}]}'

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return FakeResp()

    monkeypatch.setattr(ollama.httpx, "Client", lambda **k: FakeClient())
    assert ollama.diagnose()["verdict"] == "ollama"


def test_diagnose_never_raises(monkeypatch):
    """It runs inside a health check. A diagnostic that crashes is worthless."""
    import socket

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert isinstance(ollama.diagnose(), dict)


def test_health_surfaces_the_diagnosis(monkeypatch):
    from app import health

    monkeypatch.setattr(health.config, "OFFLINE", False)
    out = health.brain()["ollama"]
    if not out.get("up"):
        assert out.get("diagnosis") in {"nothing_listening", "port_taken"}
        assert out.get("fix")
