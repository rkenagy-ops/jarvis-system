"""The governor is the last thing between a strategy and the account.

Every test here is about a way the limit could fail to bind. A risk limit that can be
restarted away, argued past, or that counts only realized losses is not a limit - it is
a number in a status panel that gets discovered in hindsight.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import risk


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Keep the tally in memory so tests never touch the real ledger."""
    store: dict[str, str] = {}
    monkeypatch.setattr(risk.memory, "set_fact",
                        lambda k, v, **kw: store.__setitem__(k, v) or {"ok": True})
    monkeypatch.setattr(risk.memory, "get_facts",
                        lambda: [{"key": k, "value": v} for k, v in store.items()])
    monkeypatch.setattr(risk.memory, "remember", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(risk, "_broker_pnl", lambda: {"reachable": False, "reason": "test"})
    yield store


# --- the limit has to actually bind ------------------------------------------


def test_a_fresh_day_allows_trading():
    assert risk.check(1000)["allowed"] is True


def test_reaching_the_limit_blocks_and_halts():
    risk.record(pnl=-25_000, notional=25_000, symbol="TEST")
    out = risk.check(1000)
    assert out["allowed"] is False
    assert risk.state()["halted"] is True


def test_the_halt_survives_a_restart(_isolate):
    """Turn it off and on again must never be a way to resume after a bad day."""
    risk.halt("limit hit")
    # A restart is a fresh module read of the same persisted store.
    assert risk.state()["halted"] is True
    assert risk.check(100)["allowed"] is False


def test_only_an_explicit_resume_clears_a_halt():
    risk.halt("bad day")
    assert risk.check(100)["allowed"] is False
    risk.resume("reviewed and continuing")
    assert risk.check(100)["allowed"] is True


def test_there_is_no_override_argument():
    """A gate with a bypass parameter gets bypassed exactly once, at the worst moment."""
    import inspect

    params = set(inspect.signature(risk.check).parameters)
    for banned in ("force", "override", "confirmed", "bypass", "admin"):
        assert banned not in params, f"check() must not accept {banned}"


# --- unrealized losses count --------------------------------------------------


def test_open_losses_count_against_the_day(monkeypatch):
    """A position down 20k that you have not closed has still lost 20k."""
    monkeypatch.setattr(risk, "_broker_pnl", lambda: {
        "reachable": True, "realized": 0.0, "unrealized": -20_000.0, "positions": 1})
    assert risk.day_loss()["loss"] == 20_000.0


def test_open_profit_does_not_buy_extra_room(monkeypatch):
    """Unrealized gains are not money until they are. They must not raise the ceiling."""
    monkeypatch.setattr(risk, "_broker_pnl", lambda: {
        "reachable": True, "realized": -5_000.0, "unrealized": 50_000.0, "positions": 1})
    assert risk.day_loss()["loss"] == 5_000.0, "an open winner must not offset a realized loss"


def test_the_worse_ledger_wins(monkeypatch):
    """A gap in either ledger must never read as a good day."""
    risk.record(pnl=-18_000, notional=1000, symbol="OURS")
    monkeypatch.setattr(risk, "_broker_pnl", lambda: {
        "reachable": True, "realized": -100.0, "unrealized": 0.0, "positions": 0})
    assert risk.day_loss()["loss"] == 18_000.0, "the worse of the two sources must be used"


def test_an_unreachable_broker_falls_back_to_our_tally(monkeypatch):
    risk.record(pnl=-9_000, notional=1000, symbol="X")
    monkeypatch.setattr(risk, "_broker_pnl", lambda: {"reachable": False, "reason": "down"})
    out = risk.day_loss()
    assert out["loss"] == 9_000.0
    assert "internal tally only" in out["source"], "it must say the broker was not consulted"


# --- per-trade and cumulative caps -------------------------------------------


def test_an_oversized_order_is_refused():
    out = risk.check(30_000)
    assert out["allowed"] is False
    assert "exceeds the per-trade cap" in out["reason"]


def test_an_order_larger_than_the_remaining_budget_is_refused():
    risk.record(pnl=-23_000, notional=1000, symbol="X")
    out = risk.check(5_000)
    assert out["allowed"] is False
    assert "remains" in out["reason"]


def test_config_cannot_raise_the_hard_ceiling(monkeypatch):
    """A limit a config file can widen is a suggestion."""
    monkeypatch.setattr(risk.config, "MAX_DAILY_LOSS", 10_000_000, raising=False)
    assert risk.max_daily_loss() == risk.HARD_MAX_DAILY_LOSS
    monkeypatch.setattr(risk.config, "MAX_TRADE_NOTIONAL", 999_999, raising=False)
    assert risk.max_trade_notional() == risk.HARD_MAX_TRADE_NOTIONAL


def test_config_can_lower_the_ceiling(monkeypatch):
    monkeypatch.setattr(risk.config, "MAX_DAILY_LOSS", 5_000, raising=False)
    assert risk.max_daily_loss() == 5_000


def test_a_garbage_config_value_falls_back_to_the_hard_ceiling(monkeypatch):
    monkeypatch.setattr(risk.config, "MAX_DAILY_LOSS", "not a number", raising=False)
    assert risk.max_daily_loss() == risk.HARD_MAX_DAILY_LOSS


# --- behavioural stops --------------------------------------------------------


def test_a_losing_streak_stands_the_desk_down():
    for _ in range(risk.MAX_CONSECUTIVE_LOSSES):
        risk.record(pnl=-100, notional=1000, symbol="X")
    assert risk.state()["halted"] is True


def test_a_win_resets_the_streak():
    risk.record(pnl=-100, notional=100, symbol="X")
    risk.record(pnl=-100, notional=100, symbol="X")
    risk.record(pnl=50, notional=100, symbol="X")
    assert risk.state()["consecutive_losses"] == 0


def test_the_trade_count_is_capped():
    for _ in range(risk.HARD_MAX_TRADES_PER_DAY):
        risk.record(pnl=1, notional=10, symbol="X")
    assert risk.check(100)["allowed"] is False


# --- sizing shrinks as the day worsens ---------------------------------------


def test_the_budget_shrinks_after_losses():
    first = risk.budget()["risk"]
    risk.record(pnl=-15_000, notional=1000, symbol="X")
    assert risk.budget()["risk"] < first


def test_no_budget_once_halted():
    risk.halt("stop")
    assert risk.budget()["risk"] == 0.0


# --- the day boundary ---------------------------------------------------------


def test_the_day_rolls_in_market_time():
    import datetime as dt

    late_utc = dt.datetime(2026, 3, 5, 2, 30, tzinfo=dt.timezone.utc)  # 21:30 NY the day before
    assert risk.trading_day(late_utc) == "2026-03-04"


def test_a_new_day_resets_the_tally(monkeypatch):
    risk.record(pnl=-20_000, notional=1000, symbol="X")
    assert risk.state()["loss_today"] == 20_000.0
    monkeypatch.setattr(risk, "trading_day", lambda now=None: "2099-01-01")
    assert risk.state()["loss_today"] == 0.0


def test_a_new_day_does_not_clear_a_halt(monkeypatch):
    """The tally rolls; the decision to stop does not roll with it."""
    risk.halt("blew the limit")
    monkeypatch.setattr(risk, "trading_day", lambda now=None: "2099-01-01")
    assert risk.state()["halted"] is True


def test_dispatch_surface():
    assert "error" in risk.dispatch("nonsense")
    assert "halted" in risk.dispatch("state")
