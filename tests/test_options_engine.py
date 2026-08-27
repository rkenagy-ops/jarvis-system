"""The filters exist because this is where options money is actually lost.

Not on direction - on paying a spread that eats the edge, buying premium when premium
is dear, and sizing a contract like a lottery ticket. A scorer that waves those through
is worse than none, because it lends arithmetic to a bad trade.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import options

GOOD = dict(spot=100, strike=100, expiry="2099-01-15", right="C",
            bid=4.50, ask=4.65, iv=0.30, open_interest=5000, volume=800)


def _at(days: int, **over):
    """A contract `days` out from today, so tests do not rot."""
    import datetime as dt

    kw = dict(GOOD)
    kw["expiry"] = (dt.date.today() + dt.timedelta(days=days)).strftime("%Y%m%d")
    kw.update(over)
    return kw


def test_a_sane_contract_passes():
    out = options.score_contract(**_at(45))
    assert out["ok"] is True and not out["blockers"]


def test_a_wide_spread_is_rejected():
    out = options.score_contract(**_at(45, bid=4.00, ask=5.20))
    assert out["ok"] is False
    assert any("wide" in b for b in out["blockers"])


def test_a_far_otm_lottery_ticket_is_rejected():
    out = options.score_contract(**_at(45, strike=140, bid=0.10, ask=0.12))
    assert out["ok"] is False
    assert any("lottery" in b for b in out["blockers"])


def test_a_deep_itm_contract_is_rejected_as_expensive_stock():
    out = options.score_contract(**_at(45, strike=60, bid=40.0, ask=40.4))
    assert out["ok"] is False
    assert any("close to stock" in b for b in out["blockers"])


def test_an_expiring_contract_is_rejected():
    out = options.score_contract(**_at(4, bid=1.10, ask=1.15))
    assert out["ok"] is False
    assert any("theta dominates" in b for b in out["blockers"])


def test_an_illiquid_contract_is_rejected():
    out = options.score_contract(**_at(45, open_interest=20, volume=2))
    assert out["ok"] is False
    assert any("open interest" in b.lower() for b in out["blockers"])


def test_a_missing_quote_is_a_blocker_not_a_pass():
    """No quote means unknown cost, and unknown cost is not the same as acceptable."""
    out = options.score_contract(**_at(45, bid=None, ask=None))
    assert out["ok"] is False
    assert any("two-sided" in b for b in out["blockers"])


# --- the numbers a long buyer most needs shown to them ------------------------


def test_theta_is_real_and_negative_for_a_long_option():
    """Reading a key that did not exist made every contract look like it decayed free."""
    out = options.score_contract(**_at(45))
    assert out["theta_per_day"] is not None and out["theta_per_day"] < 0
    assert out["daily_burn_pct"] > 0


def test_shorter_dated_options_burn_faster():
    near = options.score_contract(**_at(25, bid=3.30, ask=3.40))
    far = options.score_contract(**_at(60, bid=5.20, ask=5.35))
    assert near["daily_burn_pct"] > far["daily_burn_pct"]


def test_breakeven_is_above_the_strike_for_a_call():
    """The move required before you make a cent is always further than it feels."""
    out = options.score_contract(**_at(45))
    assert out["breakeven"] > out["strike"]
    assert out["move_needed_pct"] > 0


def test_breakeven_is_below_the_strike_for_a_put():
    out = options.score_contract(**_at(45, right="P", strike=100, bid=4.2, ask=4.35))
    assert out["breakeven"] < out["strike"]


def test_an_expired_contract_is_refused():
    assert "error" in options.score_contract(**_at(-5))


# --- sizing -------------------------------------------------------------------


def test_sizing_uses_the_stop_not_the_full_premium():
    """Assuming total loss on every trade sizes everything at a fraction of the thesis."""
    out = options.size(risk_budget=5000, cost_per_contract=465, stop_pct=50)
    assert out["contracts"] == 21
    assert out["total_risk"] <= 5000


def test_a_budget_too_small_for_one_contract_is_no_position():
    out = options.size(risk_budget=50, cost_per_contract=465, stop_pct=50)
    assert out["contracts"] == 0
    assert out["ok"] is False


def test_a_tighter_stop_allows_more_contracts():
    loose = options.size(risk_budget=5000, cost_per_contract=465, stop_pct=100)
    tight = options.size(risk_budget=5000, cost_per_contract=465, stop_pct=25)
    assert tight["contracts"] > loose["contracts"]


def test_sizing_refuses_nonsense():
    assert "error" in options.size(risk_budget=1000, cost_per_contract=0)
    assert "error" in options.size(risk_budget=0, cost_per_contract=100)


# --- ranking ------------------------------------------------------------------


def test_rank_without_a_chain_says_where_a_chain_comes_from():
    out = options.rank("AAPL", None, spot=100)
    assert "error" in out and "market action=ibkr" in out["how"]


def test_rank_puts_the_least_demanding_trade_first():
    chain = [
        dict(strike=100, expiry=_at(45)["expiry"], right="C", bid=4.50, ask=4.65, iv=0.30, open_interest=5000, volume=800),
        dict(strike=110, expiry=_at(45)["expiry"], right="C", bid=1.40, ask=1.50, iv=0.30, open_interest=5000, volume=800),
    ]
    out = options.rank("TEST", chain, spot=100)
    if out.get("tradeable"):
        assert out["best"]["strike"] == 100, "the contract needing the smaller move should rank first"


def test_rejecting_everything_is_a_valid_answer():
    """Some days the correct number of trades is zero, and it must say so."""
    chain = [dict(strike=140, expiry=_at(45)["expiry"], right="C", bid=0.05, ask=0.12,
                  iv=0.30, open_interest=5, volume=0)]
    out = options.rank("TEST", chain, spot=100)
    assert out["tradeable"] == 0
    assert "zero" in (out.get("note") or "")


def test_dispatch_surface():
    assert "error" in options.dispatch("nonsense")
    assert "error" in options.dispatch("iv")  # no symbol


# --- volatility estimation ----------------------------------------------------


def test_yang_zhang_sees_range_that_close_to_close_misses():
    """A name that gaps and reverses looks calm on closes alone. Every ITM probability
    we compute is only as good as the volatility feeding it."""
    import math
    import statistics

    px, bars = 100.0, []
    for i in range(60):
        o = px * (1 + (0.02 if i % 2 else -0.02))
        h, l = o * 1.03, o * 0.97
        c = px  # every close identical: close-to-close sees zero volatility
        bars.append({"open": o, "high": h, "low": l, "close": c})

    yz = options.yang_zhang(bars, 20)
    closes = [b["close"] for b in bars]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    cc = statistics.pstdev(rets[-20:]) * math.sqrt(252)

    assert cc < 0.001, "the control: identical closes look like zero volatility"
    assert yz > 0.2, "the range says otherwise, and that is the number that matters"


def test_yang_zhang_needs_a_full_window():
    assert options.yang_zhang([{"open": 1, "high": 1, "low": 1, "close": 1}] * 5, 20) is None


def test_yang_zhang_survives_a_bad_bar():
    bars = [{"open": 100, "high": 101, "low": 99, "close": 100} for _ in range(40)]
    bars[10] = {"open": 0, "high": 0, "low": 0, "close": 0}
    assert options.yang_zhang(bars, 20) is not None
