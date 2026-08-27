"""Three numbers that get confused, and the gap where the money goes.

delta = N(d1) is routinely quoted as "probability ITM". It is not, and it is always
higher. P(ITM) = N(d2) is the chance of finishing past the strike. P(profit) is the
chance of finishing past BREAKEVEN, which is the only one about your money - a call
that finishes a cent in the money is a total loss for the buyer and counts as a win in
the other two.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import probability as pr

S, T, VOL = 100.0, 45 / 365, 0.30


def test_delta_always_overstates_the_chance_of_finishing_itm():
    """d1 > d2 always, so this holds for every strike. It is why the confusion costs money."""
    for K in (80, 90, 100, 110, 120):
        out = pr.p_profit(S, K, T, VOL, 2.0)
        assert abs(out["delta"]) > out["p_itm"], f"delta must exceed p_itm at strike {K}"


def test_finishing_itm_is_not_the_same_as_making_money():
    out = pr.p_profit(S, 100, T, VOL, 4.575)
    assert out["p_profit"] < out["p_itm"]
    assert out["gap"]["p_itm_minus_p_profit"] > 0


def test_the_premium_is_what_separates_them():
    """A bigger premium means a further breakeven means worse odds. Always."""
    cheap = pr.p_profit(S, 100, T, VOL, 1.0)["p_profit"]
    dear = pr.p_profit(S, 100, T, VOL, 8.0)["p_profit"]
    assert dear < cheap


def test_an_atm_call_is_roughly_a_coin_flip_to_finish_itm():
    out = pr.p_itm(S, 100, T, VOL)
    assert 0.45 < out["p_itm"] < 0.55


def test_deep_itm_is_nearly_certain_and_far_otm_nearly_hopeless():
    assert pr.p_itm(S, 50, T, VOL)["p_itm"] > 0.95
    assert pr.p_itm(S, 200, T, VOL)["p_itm"] < 0.05


def test_calls_and_puts_are_complementary_at_the_same_strike():
    c = pr.p_itm(S, 105, T, VOL, right="C")["p_itm"]
    p = pr.p_itm(S, 105, T, VOL, right="P")["p_itm"]
    assert abs((c + p) - 1.0) < 1e-6


def test_a_put_breaks_even_below_the_strike():
    out = pr.p_profit(S, 100, T, VOL, 4.0, right="P")
    assert out["breakeven"] == 96.0


def test_more_time_means_more_chance_of_a_far_strike_paying():
    near = pr.p_itm(S, 120, 10 / 365, VOL)["p_itm"]
    far = pr.p_itm(S, 120, 180 / 365, VOL)["p_itm"]
    assert far > near


def test_touching_is_likelier_than_finishing_past():
    """A stop is hit on the way past, not at the bell. This is the number for stops."""
    touch = pr.p_touch(S, 110, T, VOL)["p_touch"]
    finish = pr.p_itm(S, 110, T, VOL)["p_itm"]
    assert touch > finish


def test_a_distant_barrier_does_not_overflow():
    """The exponent in the touch formula explodes on far barriers; it must be capped."""
    out = pr.p_touch(S, 10_000, T, VOL)
    assert out["ok"] and 0.0 <= out["p_touch"] <= 1.0


# --- refusing to invent an edge ----------------------------------------------


def test_no_view_means_no_edge_is_claimed():
    """At the market's own vol the EV of any option is zero net of premium. Say so."""
    out = pr.edge(S, 100, T, VOL, 4.575)
    assert out["expected_value"] is None
    assert "no edge to compute" in out["verdict"].lower()


def test_a_view_produces_an_edge_that_is_conditional_and_says_so():
    out = pr.edge(S, 100, T, VOL, 4.575, expected_move_pct=8.0)
    assert out["expected_value_per_contract"] > 0
    assert "if your view is right" in out["verdict"].lower()


def test_a_weak_view_does_not_justify_an_expensive_option():
    out = pr.edge(S, 100, T, VOL, 12.0, expected_move_pct=1.0)
    assert out["expected_value_per_contract"] < 0
    assert "too high" in out["verdict"].lower()


def test_costs_are_disclosed():
    out = pr.edge(S, 100, T, VOL, 4.575, expected_move_pct=8.0)
    assert "commission" in out["caveat"] and "bid/ask" in out["caveat"]


# --- guards -------------------------------------------------------------------


def test_an_expired_option_has_no_probability_left():
    assert "error" in pr.p_itm(S, 100, 0, VOL)


def test_zero_volatility_is_refused():
    assert "error" in pr.p_itm(S, 100, T, 0)


def test_profit_without_a_premium_is_refused():
    """Without a premium, breakeven is just the strike and the question is meaningless."""
    assert "error" in pr.p_profit(S, 100, T, VOL, 0)


def test_compare_ranks_on_the_number_that_matters():
    out = pr.compare(S, T, VOL, [95, 100, 105], [7.5, 4.575, 2.4])
    assert out["ranked"][0]["p_profit"] >= out["ranked"][-1]["p_profit"]
    assert all("delta" in row for row in out["ranked"]), "show delta beside it to expose the gap"


def test_dispatch_surface():
    assert "error" in pr.dispatch("nonsense")
    assert pr.dispatch("itm", spot=100, strike=100, dte=45, iv=0.3)["ok"]
