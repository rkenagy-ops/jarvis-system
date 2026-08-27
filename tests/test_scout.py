"""Comparing a 7-day and a 45-day contract needs a common currency.

The one used here needs no opinion: the move the contract requires, against how often
this stock has actually made a move that size over that exact horizon. Measured off
real bars, so it carries the fat tails, drift and skew that a lognormal denies.

The tests that matter most are the honesty ones - that a thin sample says it is thin,
that overlapping windows are disclosed as dependent, and that theoretical prices are
never passed off as quotes.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import scout


def _bars(n=600, drift=0.0006, vol=0.012, seed=5):
    import datetime as dt
    import random

    rng = random.Random(seed)
    px, out, d0 = 100.0, [], dt.date(2022, 1, 1)
    for i in range(n):
        px *= 1 + rng.gauss(drift, vol)
        out.append({"date": (d0 + dt.timedelta(days=i)).isoformat(), "open": round(px, 2),
                    "high": round(px * 1.008, 2), "low": round(px * 0.992, 2),
                    "close": round(px, 2), "volume": 1_000_000})
    return out


# --- the base rate itself -----------------------------------------------------


def test_a_bigger_move_is_rarer():
    bars = _bars()
    small = scout.move_base_rate(bars, 2, 21)["base_rate"]
    big = scout.move_base_rate(bars, 10, 21)["base_rate"]
    assert big < small


def test_a_longer_horizon_makes_the_same_move_likelier():
    """This is the whole reason 7 DTE and 45 DTE cannot be compared on price."""
    bars = _bars()
    near = scout.move_base_rate(bars, 5, 5)["base_rate"]
    far = scout.move_base_rate(bars, 5, 40)["base_rate"]
    assert far > near


def test_touching_a_level_is_commoner_than_closing_past_it():
    """You can sell an option on the way; you are not obliged to hold to expiry."""
    out = scout.move_base_rate(_bars(), 5, 21)
    assert out["touch_rate"] >= out["base_rate"]


def test_a_thin_sample_says_so_rather_than_quoting_a_probability():
    """A base rate from a handful of windows is an anecdote with a decimal point."""
    out = scout.move_base_rate(_bars(120), 3, 21)
    if out.get("ok"):
        assert out["confidence"] == "thin - treat as anecdote"


def test_too_little_history_is_refused_outright():
    assert "error" in scout.move_base_rate(_bars(30), 3, 21)


def test_overlapping_windows_are_disclosed_as_dependent():
    """200 overlapping windows do not carry the information of 200 observations."""
    out = scout.move_base_rate(_bars(), 5, 21)
    assert "not independent" in out["caveat"]


def test_direction_is_respected():
    """On a name that drifts up, up-moves must be commoner than down-moves."""
    bars = _bars(drift=0.0015, vol=0.008)
    up = scout.move_base_rate(bars, 5, 30, direction="up")["base_rate"]
    down = scout.move_base_rate(bars, 5, 30, direction="down")["base_rate"]
    assert up > down


def test_a_bad_horizon_is_refused():
    assert "error" in scout.move_base_rate(_bars(), 5, 0)


# --- ranking across the whole window -----------------------------------------


def test_the_hunt_spans_the_whole_dte_window(monkeypatch):
    from app import markets

    bars = _bars(900)
    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": bars})
    out = scout.hunt("TEST")
    assert out["ok"] and out["considered"] > 0, "the synthetic ladder must produce candidates"
    dtes = {c["dte"] for c in out["ranked"]}
    assert min(dtes) < 20 and max(dtes) > 35, f"the window should span short and long: {sorted(dtes)}"


def test_the_data_picks_the_direction_not_a_standing_preference(monkeypatch):
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900, drift=0.0018, vol=0.008)})
    assert scout.hunt("TEST")["bias"] == "bullish"
    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900, drift=-0.0018, vol=0.008)})
    assert scout.hunt("TEST")["bias"] == "bearish"


def test_theoretical_prices_are_never_passed_off_as_quotes(monkeypatch):
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900)})
    out = scout.hunt("TEST")
    assert out["synthetic_prices"] is True
    assert "not quotes" in out["note"]


def test_same_odds_at_a_lower_price_is_surfaced(monkeypatch):
    """Ranking on odds alone hides that a cheaper expiry bought the same chance."""
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900)})
    out = scout.hunt("TEST")
    if out["tradeable"] > 1:
        assert out["best_value"] is not None
        assert out["best_value"]["odds_per_100_risked"] >= out["best"]["odds_per_100_risked"]


def test_the_ranking_explains_itself(monkeypatch):
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900)})
    out = scout.hunt("TEST")
    assert "No forecast, no view" in out["how_ranked"]


def test_disagreement_with_the_model_is_reported_both_ways(monkeypatch):
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(900)})
    out = scout.hunt("TEST")
    for c in out["ranked"]:
        assert c["edge_vs_model"] is not None
        assert c["read"], "a disagreement with no explanation is just a number"


def test_too_little_history_refuses_to_hunt(monkeypatch):
    from app import markets

    monkeypatch.setattr(markets, "history", lambda s, r="3y": {"bars": _bars(50)})
    assert "error" in scout.hunt("TEST")


def test_dispatch_surface():
    assert "error" in scout.dispatch("nonsense")
    assert "error" in scout.dispatch("hunt")
