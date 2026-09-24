"""Visibility only: snapshot/history/dashboard must never gate a trade, cap a good
day, or reference any daily target. risk.py is still the only thing that can stop
an order, and it still only gates losses.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import pnl_dashboard, risk


def _fake_day_loss(day, net):
    return lambda: {"loss": abs(min(0.0, net)), "net": net, "source": "test", "day": day}


def _fake_state(trades=1, consecutive_losses=0):
    return lambda: {"trades_today": trades, "consecutive_losses": consecutive_losses}


def test_snapshot_upserts_todays_row_without_duplicating(monkeypatch):
    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-09-24", 500.0))
    monkeypatch.setattr(risk, "state", _fake_state(trades=3))

    first = pnl_dashboard.snapshot()
    second = pnl_dashboard.snapshot()
    assert first["realized"] == 500.0 and second["realized"] == 500.0

    rows = pnl_dashboard.history(30)
    matching = [r for r in rows if r["day"] == "2026-09-24"]
    assert len(matching) == 1, "one snapshot call after another must update, not insert a second row"


def test_a_very_profitable_day_is_recorded_exactly_as_reported_no_cap(monkeypatch):
    """The whole point: nothing here should behave differently for a huge green day
    than an ordinary one.
    """
    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-09-25", 48000.0))
    monkeypatch.setattr(risk, "state", _fake_state(trades=9))

    out = pnl_dashboard.snapshot()
    assert out["realized"] == 48000.0

    rows = pnl_dashboard.history(30)
    row = next(r for r in rows if r["day"] == "2026-09-25")
    assert row["realized"] == 48000.0


def test_history_orders_newest_first_and_respects_the_limit(monkeypatch):
    for day, net in [("2026-08-01", 10.0), ("2026-08-02", -5.0), ("2026-08-03", 20.0)]:
        monkeypatch.setattr(risk, "day_loss", _fake_day_loss(day, net))
        monkeypatch.setattr(risk, "state", _fake_state())
        pnl_dashboard.snapshot()

    rows = pnl_dashboard.history(2)
    assert len(rows) == 2
    assert rows[0]["day"] >= rows[1]["day"]


def test_dashboard_computes_green_red_flat_and_a_running_curve(monkeypatch):
    test_days = {"2026-07-01": 100.0, "2026-07-02": -40.0, "2026-07-03": 0.0}
    for day, net in test_days.items():
        monkeypatch.setattr(risk, "day_loss", _fake_day_loss(day, net))
        monkeypatch.setattr(risk, "state", _fake_state())
        pnl_dashboard.snapshot()

    # Final snapshot call inside dashboard() itself, for "today".
    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-07-03", 0.0))
    monkeypatch.setattr(risk, "state", _fake_state())

    out = pnl_dashboard.dashboard(days=30)
    # The shared test DB may carry rows from other tests in this session, so only
    # assert on the slice this test actually wrote.
    curve = [c for c in out["equity_curve"] if c["day"] in test_days]
    assert len(curve) == 3
    assert curve[0]["day"] < curve[1]["day"] < curve[2]["day"], "oldest first"
    realized_by_day = {c["day"]: c["realized"] for c in curve}
    assert realized_by_day == test_days
    assert out["green_days"] >= 1
    assert out["red_days"] >= 1
    assert out["flat_days"] >= 1


def test_dashboard_pulls_setup_expectancy_from_forward_tracker(monkeypatch):
    from app import forward_tracker

    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-06-01", 10.0))
    monkeypatch.setattr(risk, "state", _fake_state())
    monkeypatch.setattr(forward_tracker, "stats", lambda: {"by_setup": {"trend_pullback": {"expectancy_r": 0.5}}})

    out = pnl_dashboard.dashboard(days=30)
    assert out["setup_expectancy"]["trend_pullback"]["expectancy_r"] == 0.5


def test_dashboard_note_states_there_is_no_target_or_cap(monkeypatch):
    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-06-02", 10.0))
    monkeypatch.setattr(risk, "state", _fake_state())

    out = pnl_dashboard.dashboard(days=30)
    note = out["note"].lower()
    assert "no daily target" in note or "no target" in note
    assert "cap" in note


def test_dispatch_routes_actions(monkeypatch):
    monkeypatch.setattr(risk, "day_loss", _fake_day_loss("2026-06-03", 10.0))
    monkeypatch.setattr(risk, "state", _fake_state())

    assert pnl_dashboard.dispatch("dashboard")["ok"] is True
    assert pnl_dashboard.dispatch("snapshot")["ok"] is True
    assert pnl_dashboard.dispatch("history")["ok"] is True
    err = pnl_dashboard.dispatch("nonsense")
    assert "error" in err
