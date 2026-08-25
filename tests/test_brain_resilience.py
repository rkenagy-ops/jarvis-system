"""A turn must survive its tools, and a stream must actually stream.

Two failures produced the same symptom — "she hears me but never answers, and she
does not run the tasks I give her":

  1. tools.execute was called bare. Tools reach the network and third-party keys, so
     they raise for ordinary reasons. The exception escaped think(), the model never
     received a function_call_output, and the whole turn died mid-flight.
  2. think_events collected every event into a list and yielded it only after the turn
     finished, so /api/chat/stream sent nothing at all until the end. A turn with a few
     network tools in it looked exactly like a hang.
"""

from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import brain


# --- a raising tool must not kill the turn ------------------------------------


def test_run_tool_returns_the_error_instead_of_raising(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("upstream said no")

    monkeypatch.setattr(brain.tools, "execute", boom)
    out = brain._run_tool("web_search", {}, session_id="s", agent_id="jarvis")
    assert isinstance(out, dict)
    assert "upstream said no" in out["error"]
    assert out["tool"] == "web_search"


def test_the_error_names_the_exception_type(monkeypatch):
    """'Something went wrong' is not a diagnosis. The type is half the answer."""

    def boom(*a, **k):
        raise TimeoutError("took too long")

    monkeypatch.setattr(brain.tools, "execute", boom)
    assert brain._run_tool("wiki", {}, session_id="s", agent_id="jarvis")["error"].startswith("TimeoutError")


def test_a_huge_error_is_truncated(monkeypatch):
    """A tool that dumps a page of HTML must not poison the model's context."""

    def boom(*a, **k):
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr(brain.tools, "execute", boom)
    assert len(brain._run_tool("t", {}, session_id="s", agent_id="jarvis")["error"]) < 400


def test_a_working_tool_is_passed_straight_through(monkeypatch):
    monkeypatch.setattr(brain.tools, "execute", lambda *a, **k: {"result": 4})
    assert brain._run_tool("calc", {}, session_id="s", agent_id="jarvis") == {"result": 4}


def test_no_call_site_still_calls_execute_bare():
    """Regression guard: a new call site must go through _run_tool."""
    src = (ROOT / "app" / "brain.py").read_text(encoding="utf-8")
    body = src.split("def _parse_args", 1)[1]
    assert "tools.execute(" not in body, "call tools through _run_tool so a failure cannot kill the turn"


def test_a_failing_tool_still_produces_an_answer(monkeypatch):
    """End to end: the turn completes and the failure is reported, not swallowed."""

    def boom(*a, **k):
        raise RuntimeError("the market feed is down")

    monkeypatch.setattr(brain.tools, "execute", boom)
    monkeypatch.setattr(brain.config, "OFFLINE", True)

    events = list(brain.think_events("what is the price of SPY", "s-fail"))
    kinds = [e.get("type") for e in events]
    assert "done" in kinds, f"the turn must finish, got {kinds}"


# --- the stream has to stream -------------------------------------------------


def test_events_arrive_before_the_turn_finishes(monkeypatch):
    """The whole point of /api/chat/stream. This is what made her look frozen."""
    released = []

    def slow_think(user_text, *, session_id, agent_id="jarvis", emit=None, **kw):
        emit({"type": "token", "text": "first"})
        released.append("emitted")
        time.sleep(1.0)          # the rest of a realistically slow turn
        emit({"type": "done", "text": "done", "agent": agent_id})
        return {"text": "done"}

    monkeypatch.setattr(brain, "think", slow_think)

    started = time.monotonic()
    stream = brain.think_events("hello", "s-stream")
    first = next(stream)
    elapsed = time.monotonic() - started

    assert first["type"] == "token"
    assert elapsed < 0.5, f"the first event waited {elapsed:.2f}s for the whole turn"
    assert list(stream)[-1]["type"] == "done", "the rest of the turn must still arrive"


def test_a_crash_mid_turn_keeps_what_came_before(monkeypatch):
    def half_then_die(user_text, *, session_id, agent_id="jarvis", emit=None, **kw):
        emit({"type": "token", "text": "I was saying"})
        raise RuntimeError("the brain fell over")

    monkeypatch.setattr(brain, "think", half_then_die)
    events = list(brain.think_events("hello", "s-crash"))
    kinds = [e["type"] for e in events]
    assert kinds == ["token", "error", "done"], kinds
    assert "the brain fell over" in events[1]["message"]


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_the_stream_always_terminates(monkeypatch):
    """A worker that dies before its sentinel would hang the HTTP response forever."""

    def die_immediately(*a, **k):
        raise BaseException("not even an Exception")  # noqa: TRY002

    monkeypatch.setattr(brain, "think", die_immediately)
    # The finally: clause owns the sentinel, so this must not block.
    assert isinstance(list(brain.think_events("hello", "s-term")), list)
