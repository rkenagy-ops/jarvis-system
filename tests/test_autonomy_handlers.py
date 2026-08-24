"""The guard that would have caught bot-21 shipping without a handler."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import autonomy, bots


def test_every_bot_has_a_handler():
    """A bot in SPECS with no handler silently falls through to the LLM fallback,
    where it describes doing its job instead of doing it."""
    names = {name for name, _, _ in bots.SPECS}
    missing = names - set(autonomy.JOB_HANDLERS)
    assert not missing, f"bots with no handler: {sorted(missing)}"


def test_all_handlers_are_callable():
    for name, handler in autonomy.JOB_HANDLERS.items():
        assert callable(handler), f"{name} handler is not callable"


def test_registry_runs_before_the_legacy_chain(monkeypatch):
    marks = {}
    monkeypatch.setattr(autonomy.memory, "mark_job", lambda jid, s: marks.update({"id": jid, "summary": s}))
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-21-engage", lambda: "ENGAGED")

    out = autonomy.run_job({"id": "j1", "name": "bot-21-engage", "prompt": "whatever"})
    assert out == "ENGAGED"
    assert marks["summary"] == "ENGAGED"


def test_handler_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(autonomy.memory, "mark_job", lambda *a, **k: None)

    def boom():
        raise RuntimeError("tws down")

    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-17-ibkr-watch", boom)
    out = autonomy.run_job({"id": "j2", "name": "bot-17-ibkr-watch", "prompt": ""})
    assert "failed" in out and "tws down" in out


def test_engage_handler_calls_the_real_runner(monkeypatch):
    from app import engage

    called = {}

    def fake_run(**kwargs):
        called["ran"] = True
        return {"ok": True, "posted": [1, 2], "queued_for_review": [3]}

    monkeypatch.setattr(engage, "run", fake_run)
    out = autonomy._h_engage()
    assert called.get("ran") is True
    assert "2 posted" in out and "1 queued" in out


def test_engage_handler_reports_failure(monkeypatch):
    from app import engage

    monkeypatch.setattr(engage, "run", lambda **k: {"ok": False, "error": "no creds"})
    assert "no creds" in autonomy._h_engage()


def test_learn_handler_calls_the_cycle(monkeypatch):
    from app import learning

    monkeypatch.setattr(learning, "cycle", lambda: {"summary": "Learned 2 repos"})
    assert autonomy._h_learn() == "Learned 2 repos"


def test_aliases_still_resolve(monkeypatch):
    monkeypatch.setattr(autonomy.memory, "mark_job", lambda *a, **k: None)
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "morning-briefing", lambda: "BRIEF")
    out = autonomy.run_job({"id": "j3", "name": "bot-01-briefing", "prompt": ""})
    assert out == "BRIEF"
