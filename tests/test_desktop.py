from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import desktop, redact, room, skills


def test_redact_secrets():
    raw = "key xai-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 mail me@x.com 555-123-4567"
    out = redact.redact(raw)
    assert "xai-ABCDEF" not in out
    assert "me@x.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_claude_app_url(monkeypatch):
    monkeypatch.setattr(desktop, "open_url", lambda url: {"ok": True, "opened": url})
    out = desktop.claude_github_app()
    assert out["ok"] is True
    assert "github.com/apps/claude" in out["app"]
    assert "ANTHROPIC_API_KEY" in " ".join(out["next"])


def test_open_rejects_file():
    assert "error" in desktop.open_url("file:///C:/Windows/system32/cmd.exe")


def test_open_app_rejects_unknown():
    out = desktop.open_app("cmd")
    assert "error" in out
    assert "notepad" in out["allowed"]


def test_situation():
    s = desktop.situation()
    assert "UTC" in s and "Wake word" in s and "Local" in s


def test_joke_and_skills():
    assert "joke" in desktop.joke()
    caps = desktop.capabilities()
    ids = {s["id"] for s in caps["skills"]}
    assert {"youtube", "screenshot", "remind", "room"} <= ids
    assert "briefing" in skills.help_text().lower() or "brief" in skills.help_text().lower()


def test_room_rolling(tmp_path, monkeypatch):
    monkeypatch.setattr(room, "ROOM_PATH", tmp_path / "room.json")
    room.clear()
    room.hear("alice", "picnic tomorrow if the weather holds")
    room.hear("bob", "jarvis what do you think")
    ctx = room.context()
    assert "picnic" in ctx and "bob" in ctx
    assert skills.match("what do you think")["id"] == "room"
