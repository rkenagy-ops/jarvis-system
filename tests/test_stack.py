from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import bots, stack, tools


def test_refuse_hamburger():
    out = stack.refuse_browser_farm()
    assert out.get("blocked") is True
    assert "hamburger" in out["reason"].lower()
    assert stack.dispatch("comment").get("blocked") is True
    assert stack.dispatch("hamburger").get("blocked") is True


def test_status_without_keys():
    st = stack.status()
    assert "publer" in st
    assert st.get("refused")


def test_publer_schedule_needs_confirm(monkeypatch):
    monkeypatch.setattr(stack, "publer_ready", lambda: True)
    monkeypatch.setattr(stack.config, "PUBLER_API_KEY", "x")
    monkeypatch.setattr(stack.config, "PUBLER_WORKSPACE_ID", "ws")
    monkeypatch.setattr(
        stack.memory,
        "create_pending",
        lambda *a, **k: {"confirm_token": "tok", "kind": "publer_post"},
    )
    out = stack.publer_schedule(text="hi", account_id="abc", when="2026-09-01T12:00:00Z", live=False)
    assert out.get("blocked") is True
    assert out.get("confirm_token") == "tok"


def test_twenty_bots():
    assert len(bots.SPECS) == 20
    names = [s[0] for s in bots.SPECS]
    assert names[0].startswith("bot-01")
    assert names[-1].startswith("bot-20")
    assert len(set(names)) == 20


def test_stack_tool_on_jarvis():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "stack" in names
