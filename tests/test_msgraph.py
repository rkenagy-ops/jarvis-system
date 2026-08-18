from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import msgraph, rag


def test_ms_not_ready_without_keys(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MS_CLIENT_ID", "")
    monkeypatch.setattr(config, "MS_REFRESH_TOKEN", "")
    assert msgraph.ready() is False
    out = msgraph.start_device()
    assert out.get("ok") is False


def test_cosine():
    assert rag._cosine([1, 0], [1, 0]) == 1
    assert rag._cosine([1, 0], [0, 1]) == 0


def test_send_mail_blocked(monkeypatch):
    monkeypatch.setattr(msgraph, "access_token", lambda: None)
    out = msgraph.send_mail("a@b.com", "hi", "body")
    assert "error" in out


def test_sync_calendar_seeds_reminder(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import obsidian, reminders

    monkeypatch.setattr(msgraph, "ready", lambda: True)
    start = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    monkeypatch.setattr(
        msgraph,
        "calendar_range",
        lambda hours=72: {
            "ok": True,
            "events": [{"subject": "Standup", "start": start, "end": start, "where": "", "all_day": False}],
            "count": 1,
        },
    )
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(reminders, "PATH", tmp_path / "reminders.json")
    out = msgraph.sync_calendar()
    assert out["ok"]
    assert out["reminders_added"] == 1
    assert reminders.has_open("Outlook: Standup")
    again = msgraph.sync_calendar()
    assert again["reminders_added"] == 0
