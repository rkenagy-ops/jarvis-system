from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import gaps, memory


@pytest.fixture
def fresh_goals(monkeypatch):
    """An in-memory stand-in for the goals table."""
    store: list[dict] = []
    counter = {"n": 0}

    def add_goal(title, detail="", priority=0.5):
        counter["n"] += 1
        g = {"id": f"g{counter['n']}", "title": title, "detail": detail, "status": "open"}
        store.append(g)
        return g

    def list_goals(status="open"):
        if status is None:
            return list(store)
        return [g for g in store if g["status"] == status]

    def update_goal(goal_id, status):
        for g in store:
            if g["id"] == goal_id:
                g["status"] = status
                return True
        return False

    monkeypatch.setattr(memory, "add_goal", add_goal)
    monkeypatch.setattr(memory, "list_goals", list_goals)
    monkeypatch.setattr(memory, "update_goal", update_goal)
    monkeypatch.setattr(memory, "remember", lambda *a, **k: None)
    return store


def _all_closed(monkeypatch):
    for gap in gaps.GAPS:
        monkeypatch.setitem(gap, "probe", lambda: (True, "probe stubbed closed"))


# --- matching ----------------------------------------------------------------


def test_matches_own_title():
    gap = gaps.GAPS[0]
    assert gaps._matches(gap, gaps.GOAL_PREFIX + gap["title"])


def test_matches_jarvis_own_wording():
    """The real case: Jarvis logged these gaps under its own titles."""
    by_key = {g["key"]: g for g in gaps.GAPS}
    assert gaps._matches(by_key["trusted_confirm"], "Streamlined confirm tokens for trusted ops")
    assert gaps._matches(by_key["event_driven_autonomy"], "Event-driven autonomy instead of pure timers")
    assert gaps._matches(by_key["persistent_hud"], "A persistent visual HUD")
    assert gaps._matches(by_key["native_device_control"], "Native device control beyond the desktop bridge")


def test_matching_does_not_swallow_unrelated_goals():
    """Every keyword in a group must be present, or sync would close the wrong goals."""
    for gap in gaps.GAPS:
        for title in (
            "Run Daily Driver for a week",
            "Ship the options greeks work",
            "Review trust deed paperwork",
            "Buy a new device",
            "Confirm the dentist appointment",
        ):
            assert not gaps._matches(gap, title), f"{gap['key']} wrongly matched {title!r}"


def test_matching_ignores_empty_titles():
    assert not gaps._matches(gaps.GAPS[0], "")
    assert not gaps._matches(gaps.GAPS[0], None)


# --- audit -------------------------------------------------------------------


def test_audit_touches_no_goals(fresh_goals):
    gaps.audit()
    assert fresh_goals == [], "audit must be read-only"


def test_audit_survives_a_broken_probe(monkeypatch):
    def boom():
        raise RuntimeError("probe exploded")

    monkeypatch.setitem(gaps.GAPS[0], "probe", boom)
    out = gaps.audit()
    row = next(r for r in out["gaps"] if r["key"] == gaps.GAPS[0]["key"])
    assert row["closed"] is False
    assert "probe exploded" in row["evidence"]


# --- sync --------------------------------------------------------------------


def test_sync_adopts_a_pre_existing_goal(fresh_goals, monkeypatch):
    """The bug: sync keyed on its own title, so a goal Jarvis had already written
    was never found. sync made a second one and the original stayed open."""
    original = memory.add_goal("Event-driven autonomy instead of pure timers", "logged by Jarvis")
    _all_closed(monkeypatch)

    out = gaps.sync()

    assert original["status"] == "done", "the pre-existing goal must be closed, not orphaned"
    titles = [g["title"] for g in fresh_goals]
    assert len(titles) == len(set(titles)), "sync must not duplicate a goal it already matched"
    assert len(fresh_goals) == len(gaps.GAPS), "one goal per gap, not two"


def test_sync_reports_what_it_adopted(fresh_goals, monkeypatch):
    memory.add_goal("Persistent visual HUD", "logged by Jarvis")
    _all_closed(monkeypatch)
    out = gaps.sync()
    assert "Persistent visual HUD" in (out["adopted_existing_goals"] or [])


def test_sync_creates_goals_when_none_exist(fresh_goals, monkeypatch):
    _all_closed(monkeypatch)
    gaps.sync()
    assert len(fresh_goals) == len(gaps.GAPS)
    assert all(g["status"] == "done" for g in fresh_goals)


def test_sync_closes_every_duplicate_of_the_same_gap(fresh_goals, monkeypatch):
    """If duplicates already exist, all of them should move — otherwise one lingers."""
    a = memory.add_goal("Persistent visual HUD", "")
    b = memory.add_goal("Need a native HUD window", "")
    _all_closed(monkeypatch)
    gaps.sync()
    assert a["status"] == "done" and b["status"] == "done"


def test_sync_leaves_unrelated_goals_alone(fresh_goals, monkeypatch):
    daily = memory.add_goal("Run Daily Driver for a week", "")
    _all_closed(monkeypatch)
    gaps.sync()
    assert daily["status"] == "open", "sync must not touch goals no gap owns"


def test_sync_reopens_a_regressed_capability(fresh_goals, monkeypatch):
    _all_closed(monkeypatch)
    gaps.sync()
    assert all(g["status"] == "done" for g in fresh_goals)

    # capability disappears
    for gap in gaps.GAPS:
        monkeypatch.setitem(gap, "probe", lambda: (False, "capability removed"))
    out = gaps.sync()
    assert all(g["status"] == "open" for g in fresh_goals)
    assert out["goals_reopened"]


def test_sync_is_idempotent(fresh_goals, monkeypatch):
    _all_closed(monkeypatch)
    gaps.sync()
    count = len(fresh_goals)
    second = gaps.sync()
    assert len(fresh_goals) == count, "a second sync must not add goals"
    assert second["goals_closed"] == [], "nothing left to close"
    assert len(second["unchanged"]) == len(gaps.GAPS)


# --- diagnostics -------------------------------------------------------------


def test_goals_view_flags_unowned(fresh_goals):
    memory.add_goal("Run Daily Driver for a week", "")
    memory.add_goal("Persistent visual HUD", "")
    out = gaps.goals()
    assert "Run Daily Driver for a week" in out["unowned"]
    assert "Persistent visual HUD" not in out["unowned"]


def test_dispatch_surface():
    assert gaps.dispatch("audit")["ok"] is True
    assert "error" in gaps.dispatch("nonsense")
    assert "goals" in gaps.dispatch("nonsense")["actions"]
