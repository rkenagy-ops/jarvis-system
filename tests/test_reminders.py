from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import autonomy, memory, reminders, skills


def test_timer_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(reminders, "PATH", tmp_path / "r.json")
    item = reminders.timer(0, "stand up")  # minutes max(1) — force due by rewriting
    items = reminders._load()
    items[0]["when"] = "2000-01-01T00:00:00+00:00"
    reminders._save(items)
    due = reminders.due()
    assert due and due[0]["title"] == "stand up"
    fired = []

    def fake_notify(title, body=""):
        fired.append(title)
        return {"ok": True}

    monkeypatch.setattr("app.desktop.notify", fake_notify)
    monkeypatch.setattr("app.obsidian.daily", lambda **k: None)
    monkeypatch.setattr("app.memory.remember", lambda *a, **k: None)
    out = reminders.fire_due()
    assert out and out[0]["title"] == "stand up"
    assert reminders.list_items(open_only=True) == []
    assert fired


def test_ensure_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "t.db")
    memory.init()
    autonomy.ensure_defaults()
    names = {j["name"] for j in memory.list_jobs()}
    assert "morning-briefing" in names
    assert "watchlist-scan" in names
    assert autonomy.ensure_defaults() == []


def test_skill_timer():
    assert skills.match("set a timer for 5 minutes")["id"] == "timer"


def test_briefing_job_not_treated_as_watchlist(monkeypatch):
    called = {"brief": False}

    monkeypatch.setattr(autonomy, "briefing", lambda **k: called.__setitem__("brief", True) or "BRIEF")
    monkeypatch.setattr(memory, "mark_job", lambda *a, **k: None)
    out = autonomy.run_job(
        {
            "id": "x",
            "name": "morning-briefing",
            "prompt": "Compile weather, watchlist, news, and open vault tasks.",
        }
    )
    assert called["brief"] is True
    assert out == "BRIEF"
