from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import autonomy, events


@pytest.fixture(autouse=True)
def clean_bus():
    events.SUBSCRIPTIONS.clear()
    events.SOURCES.clear()
    events._recent.clear()
    events._last_fired.clear()
    yield
    events.SUBSCRIPTIONS.clear()
    events.SOURCES.clear()
    events._recent.clear()
    events._last_fired.clear()


def test_subscribe_rejects_unknown_job():
    out = events.subscribe("vault.changed", "bot-99-nonexistent")
    assert "error" in out
    assert "known" in out


def test_subscribe_requires_both_args():
    assert "error" in events.subscribe("", "bot-19-rag")
    assert "error" in events.subscribe("vault.changed", "")


def test_subscribe_is_idempotent():
    events.subscribe("vault.changed", "bot-19-rag")
    out = events.subscribe("vault.changed", "bot-19-rag")
    assert out["subscribers"] == 1


def test_emit_runs_subscribed_jobs(monkeypatch):
    ran = []
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-19-rag", lambda: ran.append("rag") or "reindexed")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)

    events.subscribe("vault.changed", "bot-19-rag")
    out = events.emit("vault.changed", {"path": "x.md"})
    assert out["ok"] and out["jobs_run"] == 1
    assert ran == ["rag"]
    assert out["results"][0]["summary"] == "reindexed"


def test_emit_with_no_subscriber_is_explicit(monkeypatch):
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    out = events.emit("nothing.listening")
    assert out["jobs_run"] == 0
    assert "No job is subscribed" in out["note"]


def test_emit_isolates_a_failing_job(monkeypatch):
    """One job blowing up must not stop the others on the same event."""
    ran = []

    def boom():
        raise RuntimeError("ollama down")

    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-19-rag", boom)
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-20-finish", lambda: ran.append("finish") or "ok")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)

    events.subscribe("vault.changed", "bot-19-rag")
    events.subscribe("vault.changed", "bot-20-finish")
    out = events.emit("vault.changed")

    assert out["jobs_run"] == 2
    assert ran == ["finish"]
    summaries = " ".join(r["summary"] for r in out["results"])
    assert "ollama down" in summaries


def test_emit_requires_an_event_name():
    assert "error" in events.emit("")


def test_unsubscribe_one_and_all():
    events.subscribe("vault.changed", "bot-19-rag")
    events.subscribe("vault.changed", "bot-20-finish")
    assert events.unsubscribe("vault.changed", "bot-19-rag")["removed"] == 1
    assert events.unsubscribe("vault.changed")["removed"] == 1
    assert "vault.changed" not in events.SUBSCRIPTIONS


def test_unsubscribe_unknown_event():
    assert events.unsubscribe("never.registered")["ok"] is False


def test_recent_events_are_recorded(monkeypatch):
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    events.emit("a.b")
    events.emit("c.d")
    recent = events.status()["recent_events"]
    assert [r["event"] for r in recent[:2]] == ["c.d", "a.b"]


def test_recent_is_bounded(monkeypatch):
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    for i in range(events.MAX_RECENT + 20):
        events.emit(f"e.{i}")
    assert len(events._recent) == events.MAX_RECENT


def test_status_reports_watchdog_honestly():
    st = events.status()
    assert isinstance(st["watchdog_installed"], bool)
    assert st["sources"] == {}


def test_autonomy_exposes_the_event_half(monkeypatch):
    """gaps._probe_event_driven looks for autonomy.emit backed by app/events."""
    assert hasattr(autonomy, "emit")
    assert hasattr(autonomy, "subscribe")

    ran = []
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-20-finish", lambda: ran.append("x") or "done")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    autonomy.subscribe("test.event", "bot-20-finish")
    out = autonomy.emit("test.event")
    assert out["jobs_run"] == 1
    assert ran == ["x"]


def test_watch_vault_registers_a_source(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(events.config, "VAULT_DIR", vault)
    # don't actually start a thread or observer
    monkeypatch.setattr(events, "_start_watchdog", lambda p, e: True)

    out = events.watch_vault()
    assert out["ok"] and out["running"] is True
    assert "vault" in events.SOURCES

    again = events.watch_vault()
    assert again.get("already_running") is True


def test_watch_vault_falls_back_to_polling(tmp_path, monkeypatch):
    """No watchdog must degrade to polling, and say so rather than implying otherwise."""
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(events.config, "VAULT_DIR", vault)
    monkeypatch.setattr(events, "_start_watchdog", lambda p, e: False)
    monkeypatch.setattr(events, "_start_polling", lambda p, e, interval=30.0: None)

    out = events.watch_vault()
    assert out["kind"] == "polling"
    assert "install watchdog" in out["detail"]


def test_watch_vault_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(events.config, "VAULT_DIR", tmp_path / "does-not-exist")
    assert "error" in events.watch_vault()


def test_dispatch_surface():
    assert events.dispatch("status")["ok"] is True
    assert "error" in events.dispatch("bogus")


def test_source_bursts_coalesce(monkeypatch):
    """One save fires several filesystem events; the subscribed job must run once."""
    ran = []
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-19-rag", lambda: ran.append(1) or "ok")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    events.subscribe("vault.changed", "bot-19-rag")

    for _ in range(6):
        events.emit("vault.changed", {"path": "a.md"}, coalesce=True)

    assert len(ran) == 1, "a burst should collapse to one run"


def test_manual_emit_never_coalesces(monkeypatch):
    """If you asked for it explicitly, you meant it."""
    ran = []
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-19-rag", lambda: ran.append(1) or "ok")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    events.subscribe("vault.changed", "bot-19-rag")

    events.emit("vault.changed")
    events.emit("vault.changed")
    assert len(ran) == 2


def test_coalesce_is_per_event(monkeypatch):
    ran = []
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-19-rag", lambda: ran.append(1) or "ok")
    monkeypatch.setattr(events.memory, "remember", lambda *a, **k: None)
    events.subscribe("a.one", "bot-19-rag")
    events.subscribe("b.two", "bot-19-rag")

    events.emit("a.one", coalesce=True)
    events.emit("b.two", coalesce=True)
    assert len(ran) == 2, "different events must not suppress each other"
