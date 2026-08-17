from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import brain, ollama


def test_as_tools():
    fns = [
        {
            "type": "function",
            "name": "wiki",
            "description": "Wikipedia",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
    ]
    out = ollama.as_tools(fns)
    assert out[0]["function"]["name"] == "wiki"


def test_fallback_uses_ollama(monkeypatch):
    monkeypatch.setattr(ollama, "probe", lambda force=False: {"ok": True, "reason": "ready"})
    monkeypatch.setattr(
        ollama,
        "chat",
        lambda messages, tools=None, timeout=180: {"text": "local hello", "tool_calls": []},
    )
    monkeypatch.setattr(ollama, "as_tools", lambda fns: [])
    monkeypatch.setattr(brain, "_compose_mind", lambda *a, **k: "mind")
    out = brain._think_ollama("hi", session_id="t", agent_id="jarvis", persist_user=False, emit=None)
    assert out["brain"] == "ollama"
    assert "local" in out["text"]


def test_fallback_to_free_when_ollama_down(monkeypatch):
    from app import config, free_brain

    monkeypatch.setattr(config, "OFFLINE", True)
    monkeypatch.setattr(ollama, "probe", lambda force=False: {"ok": False, "reason": "down"})
    monkeypatch.setattr(free_brain, "handle", lambda text, emit=None: {"text": "free path", "calls": [], "brain": "free"})
    out = brain._think_fallback("hello", session_id="t", agent_id="jarvis", persist_user=False, emit=None, why="offline")
    assert out["brain"] == "offline"
    assert "free" in out["text"]
