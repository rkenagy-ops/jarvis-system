from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import local_voice


def test_available_false_when_unreachable(monkeypatch):
    """A refused connection must report False, never raise — same discipline as
    health.py's probes: a broken/absent container is a normal state, not a crash."""
    monkeypatch.setattr(local_voice.config, "WHISPER_BASE_URL", "http://127.0.0.1:1")
    assert local_voice.available() is False


def test_transcribe_strips_and_returns_text(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "  hello jarvis  "}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(local_voice.httpx, "Client", FakeClient)
    assert local_voice.transcribe(b"fake-audio") == "hello jarvis"


def test_transcribe_defaults_to_empty_string(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(local_voice.httpx, "Client", FakeClient)
    assert local_voice.transcribe(b"fake-audio") == ""
