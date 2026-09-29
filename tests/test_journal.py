"""The journal must tell a mistake from the cost of doing business, study each closed
trade exactly once, and only let a real sample move the hunter's ranking."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import forward_tracker, journal


def _closed(symbol, setup, side, r, outcome, context, exit_date="2024-03-01"):
    with forward_tracker._db() as conn:
        conn.execute(
            "INSERT INTO forward_signals (symbol, setup, side, entry, stop, target, signal_date, logged_at, "
            "status, outcome, r, exit_date, bars_held, fill, exit_price, context) "
            "VALUES (?, ?, ?, 100, 95, 110, ?, 'x', 'closed', ?, ?, ?, 3, 100, 100, ?)",
            (symbol, setup, side, f"2024-02-{abs(hash(symbol)) % 27 + 1:02d}", outcome, r, exit_date, json.dumps(context)),
        )


CLEAN = {"market_up": True, "extension_atr": 0.5, "rvol": 1.8, "stop_atr": 1.5, "r_multiple": 2.5, "candles": ["hammer"]}


def test_a_clean_loss_is_cost_of_business_not_a_mistake():
    out = journal.diagnose({"symbol": "A", "setup": "trend_pullback", "side": "buy", "r": -1.0,
                            "outcome": "stop", "context": CLEAN})
    assert out["verdict"] == "cost_of_business" and not out["mistakes"]


def test_chasing_and_fighting_the_market_are_named():
    ctx = {**CLEAN, "market_up": False, "extension_atr": 3.1, "rvol": 0.8}
    out = journal.diagnose({"symbol": "B", "setup": "breakout_20d", "side": "buy", "r": -1.0,
                            "outcome": "stop", "context": ctx})
    assert out["verdict"] == "mistake"
    assert {"fought_the_market", "chased_extension", "light_volume_break"} <= set(out["mistakes"])


def test_a_short_is_judged_against_the_market_the_other_way_round():
    out = journal.diagnose({"symbol": "C", "setup": "breakdown_20d", "side": "sell", "r": -1.0,
                            "outcome": "stop", "context": {**CLEAN, "market_up": True, "extension_atr": -0.5}})
    assert "fought_the_market" in out["mistakes"]


def test_review_studies_each_closed_trade_once():
    _closed("ZJR1", "trend_pullback", "buy", -1.0, "stop", CLEAN)
    first = journal.review()
    assert any(r["symbol"] == "ZJR1" for r in first["reviews"])
    second = journal.review()
    assert not any(r["symbol"] == "ZJR1" for r in second["reviews"])


def test_weights_shrink_a_small_sample_and_push_a_real_one():
    few = journal._weight({"trades": 2, "expectancy_r": 1.0})
    many = journal._weight({"trades": 40, "expectancy_r": 1.0})
    bleeding = journal._weight({"trades": 40, "expectancy_r": -1.0})
    assert 1.0 < few < many
    assert bleeding < 1.0
    assert journal._weight({"trades": 500, "expectancy_r": -9}) == 0.3


def test_a_losing_condition_becomes_a_rule_and_lowers_the_multiplier():
    for i in range(10):
        _closed(f"ZJL{i}", "momentum_cross", "buy", -1.0, "stop", {**CLEAN, "rvol": 0.7})
    view = journal.insights()
    assert any("light_volume" in rule for rule in view["rules"])
    learned = journal.weights(refresh=True)
    assert journal.multiplier("momentum_cross", "buy", {"light_volume"}, learned) < 1.0


def test_dispatch_rejects_unknown_actions():
    assert "error" in journal.dispatch("nope")
