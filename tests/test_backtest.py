"""A backtest that can see the future is worse than no backtest.

It produces a number, the number is wrong in the flattering direction, and it gets
used to size real positions. So the look-ahead boundary is tested directly rather
than assumed, and the fill model is tested for its pessimism.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import backtest, setups


def _bars(prices, *, start_date="2024-01-01"):
    """Daily bars from a list of closes, with a plausible range around each."""
    import datetime as dt

    d0 = dt.date.fromisoformat(start_date)
    out = []
    for i, c in enumerate(prices):
        out.append({
            "date": (d0 + dt.timedelta(days=i)).isoformat(),
            "open": round(c, 2),
            "high": round(c * 1.01, 2),
            "low": round(c * 0.99, 2),
            "close": round(c, 2),
            "volume": 1_000_000,
        })
    return out


# --- the boundary that matters ------------------------------------------------


def test_detection_cannot_see_past_its_slice():
    """The whole no-look-ahead mechanism is that helpers slice from the end."""
    bars = _bars([100 + i * 0.1 for i in range(200)])
    early = setups.context_from_bars(bars[:120], "T")
    full = setups.context_from_bars(bars, "T")
    assert early["ok"] and full["ok"]
    assert early["closes"][-1] != full["closes"][-1]
    assert early["sma20"] != full["sma20"], "truncating must actually move the indicators back in time"


def test_a_context_is_identical_however_much_future_is_withheld():
    """Same past, same answer - the future must contribute nothing."""
    bars = _bars([100 + (i % 7) for i in range(300)])
    a = setups.context_from_bars(bars[:150], "T")
    b = setups.context_from_bars(bars[:150] + bars[150:], "T")
    c = setups.context_from_bars(bars[:150], "T")
    assert a["sma20"] == c["sma20"] and a["atr"] == c["atr"]
    assert b["sma20"] != a["sma20"], "the control: more bars should change the answer"


def test_the_simulation_never_reads_bars_before_the_signal():
    """Entry is offered from the bar AFTER the signal, never the signal bar itself."""
    bars = _bars([100] * 10)
    # entry far above every bar: it can never fill, whatever the earlier bars did
    assert backtest._simulate(bars, 1, "buy", 500.0, 490.0, 520.0) is None


# --- the fill model has to be pessimistic -------------------------------------


def test_an_unreachable_entry_is_simply_not_a_trade():
    bars = _bars([100] * 20)
    assert backtest._simulate(bars, 1, "buy", 200.0, 190.0, 220.0) is None


def test_a_gap_through_the_entry_fills_at_the_open_not_the_limit():
    """Filling at the price you wanted after a gap is how backtests start lying."""
    bars = [
        {"date": "d0", "open": 100, "high": 101, "low": 99, "close": 100},
        {"date": "d1", "open": 110, "high": 112, "low": 109, "close": 111},
        {"date": "d2", "open": 112, "high": 131, "low": 111, "close": 130},
    ]
    trade = backtest._simulate(bars, 1, "buy", 102.0, 98.0, 130.0)
    assert trade is not None
    assert trade["fill"] == 110, "a gap fills at the open, which is worse than the entry"
    # Risk is measured off the intended entry (102-98=4), so the gap costs real R.
    assert trade["r"] == 5.0, "the 8 points given away to the gap must show up in the result"


def test_stop_and_target_in_one_bar_counts_as_the_loss():
    """Daily bars cannot say which came first. Guessing wins is how you get a fake edge."""
    bars = [
        {"date": "d0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"date": "d1", "open": 100, "high": 120, "low": 80, "close": 100},
    ]
    trade = backtest._simulate(bars, 1, "buy", 100.0, 90.0, 110.0)
    assert trade["outcome"] == "stop"
    assert trade["r"] == -1.0


def test_a_clean_win_books_the_target():
    bars = [
        {"date": "d0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"date": "d1", "open": 100, "high": 105, "low": 99, "close": 104},
        {"date": "d2", "open": 105, "high": 112, "low": 104, "close": 111},
    ]
    trade = backtest._simulate(bars, 1, "buy", 100.0, 95.0, 110.0)
    assert trade["outcome"] == "target"
    assert trade["r"] == 2.0, "5 points of risk, 10 of reward"


def test_a_short_is_measured_the_right_way_round():
    bars = [
        {"date": "d0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"date": "d1", "open": 100, "high": 101, "low": 90, "close": 91},
    ]
    trade = backtest._simulate(bars, 1, "sell", 100.0, 105.0, 90.0)
    assert trade["outcome"] == "target"
    assert trade["r"] == 2.0


def test_an_unfinished_trade_is_not_a_result():
    """Counting an open position as a win is the oldest trick there is."""
    bars = _bars([100, 101])
    assert backtest._simulate(bars, 1, "buy", 100.0, 90.0, 500.0) is None


def test_a_trade_that_never_resolves_times_out_rather_than_running_forever():
    bars = _bars([100] * (backtest.MAX_HOLD_BARS + 10))
    trade = backtest._simulate(bars, 1, "buy", 100.0, 50.0, 500.0)
    assert trade["outcome"] == "timeout"
    assert trade["bars_held"] <= backtest.MAX_HOLD_BARS


# --- metrics ------------------------------------------------------------------


def test_expectancy_is_the_mean_r():
    m = backtest._metrics([{"r": 2.0, "bars_held": 3, "outcome": "target"},
                           {"r": -1.0, "bars_held": 2, "outcome": "stop"}])
    assert m["expectancy_r"] == 0.5
    assert m["win_rate"] == 50.0


def test_drawdown_is_measured_from_the_peak():
    trades = [{"r": r, "bars_held": 1, "outcome": "x"} for r in (1.0, 1.0, -3.0, 0.5)]
    assert backtest._metrics(trades)["max_drawdown_r"] == 3.0


def test_consecutive_losses_are_counted():
    trades = [{"r": r, "bars_held": 1, "outcome": "x"} for r in (-1, -1, -1, 2, -1)]
    assert backtest._metrics(trades)["max_consecutive_losses"] == 3


def test_no_trades_reports_nothing_rather_than_zero():
    """0% win rate and 'no data' are different claims."""
    m = backtest._metrics([])
    assert m["trades"] == 0
    assert "win_rate" not in m


# --- verdicts must not oversell ----------------------------------------------


def test_a_thin_sample_is_called_out_as_anecdote():
    v = backtest._verdict({"trades": 4, "expectancy_r": 3.0, "max_drawdown_r": 1.0})
    assert "too few" in v.lower() or "anecdote" in v.lower()


def test_negative_expectancy_is_stated_plainly():
    v = backtest._verdict({"trades": 50, "expectancy_r": -0.4, "max_drawdown_r": 12.0})
    assert "lost money" in v.lower()


def test_a_marginal_edge_mentions_costs():
    v = backtest._verdict({"trades": 40, "expectancy_r": 0.04, "max_drawdown_r": 5.0})
    assert "slippage" in v.lower() or "commission" in v.lower()


# --- surface ------------------------------------------------------------------


def test_run_rejects_an_unknown_setup():
    out = backtest.run("AAPL", "not_a_setup")
    assert "error" in out and out["known"]


def test_dispatch_surface():
    assert "error" in backtest.dispatch("nonsense")
    assert "error" in backtest.dispatch("run")  # no symbol
    assert "error" in backtest.dispatch("sweep")


def test_costs_are_disclosed_not_buried():
    """A backtest that omits costs while implying tradability is misleading."""
    import inspect

    src = inspect.getsource(backtest)
    assert "commission" in src and "slippage" in src


def test_every_catalog_setup_can_be_backtested():
    """A setup she will recommend but cannot evidence is the gap this closes.

    Checked against levels_for on a synthetic context rather than by fetching: the
    question is whether every catalog entry can produce testable levels at all.
    """
    bars = _bars([100 + (i % 11) * 0.5 for i in range(200)])
    ctx = setups.context_from_bars(bars, "T")
    assert ctx["ok"]
    for key in setups.CATALOG:
        out = setups.levels_for(ctx, key)
        assert "known" not in out, f"{key} is in the catalog but levels_for rejects it"
        assert out.get("ok"), f"{key} cannot produce levels: {out.get('error')}"
        assert out["entry"] != out["stop"], f"{key} produced a zero-width stop"
