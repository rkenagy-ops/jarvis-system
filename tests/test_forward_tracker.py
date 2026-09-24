"""Forward tracking must never touch orders, risk limits, or IBKR - it only watches what
setups.detect() finds and records what happened to it, using backtest's own fill/exit
engine so a live number and a historical number can never come from two different
rulebooks.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import backtest, forward_tracker, markets, setups


def _bars(prices, *, start_date="2024-01-01"):
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


def _insert(symbol, setup, side, entry, stop, target, signal_date):
    with forward_tracker._db() as conn:
        conn.execute(
            "INSERT INTO forward_signals "
            "(symbol, setup, side, entry, stop, target, signal_date, logged_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
            (symbol, setup, side, entry, stop, target, signal_date, "2024-01-01T00:00:00+00:00"),
        )


def _status(symbol):
    with forward_tracker._db() as conn:
        row = conn.execute("SELECT status FROM forward_signals WHERE symbol=?", (symbol,)).fetchone()
    return row["status"] if row else None


# --- logging ------------------------------------------------------------------


def test_a_new_signal_is_logged_with_the_real_levels(monkeypatch):
    bars = _bars([100 + i * 0.05 for i in range(90)])
    monkeypatch.setattr(setups, "scan", lambda symbol, range_="1y": {
        "ok": True, "found": [{"setup": "trend_pullback"}],
    })
    monkeypatch.setattr(markets, "history", lambda symbol, range_="1y": {"bars": bars})

    out = forward_tracker.log_new_signals(["ZFWD1"])
    assert out["ok"] and out["logged"] == 1
    row = out["signals"][0]
    assert row["symbol"] == "ZFWD1" and row["setup"] == "trend_pullback"
    assert row["entry"] and row["stop"] and row["target"]


def test_the_same_days_signal_is_never_logged_twice(monkeypatch):
    bars = _bars([100 + i * 0.05 for i in range(90)])
    monkeypatch.setattr(setups, "scan", lambda symbol, range_="1y": {
        "ok": True, "found": [{"setup": "trend_pullback"}],
    })
    monkeypatch.setattr(markets, "history", lambda symbol, range_="1y": {"bars": bars})

    forward_tracker.log_new_signals(["ZFWD2"])
    second = forward_tracker.log_new_signals(["ZFWD2"])
    assert second["logged"] == 0 and second["skipped"] == 1


def test_no_setups_found_logs_nothing(monkeypatch):
    monkeypatch.setattr(setups, "scan", lambda symbol, range_="1y": {"ok": True, "found": []})
    out = forward_tracker.log_new_signals(["ZFWD_NONE"])
    assert out["ok"] and out["logged"] == 0


# --- forward walking, via backtest's own engine --------------------------------


def test_update_open_closes_a_signal_via_backtests_own_simulator(monkeypatch):
    bars = [
        {"date": "2024-02-01", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
        {"date": "2024-02-02", "open": 100, "high": 105, "low": 99, "close": 104, "volume": 1},
        {"date": "2024-02-03", "open": 105, "high": 112, "low": 104, "close": 111, "volume": 1},
    ]
    monkeypatch.setattr(markets, "history", lambda symbol, range_="2y": {"bars": bars})
    _insert("ZFWD3", "breakout_20d", "buy", 100.0, 95.0, 110.0, "2024-02-01")

    out = forward_tracker.update_open()
    assert out["closed"] == 1
    trade = out["results"][0]
    assert trade["outcome"] == "target"

    # Same engine backtest.py itself is tested against must produce the identical trade.
    expected = backtest._simulate(bars, 1, "buy", 100.0, 95.0, 110.0)
    assert trade["r"] == expected["r"] and trade["outcome"] == expected["outcome"]
    assert _status("ZFWD3") == "closed"


def test_an_entry_that_never_fills_is_marked_unfilled_not_left_open_forever(monkeypatch):
    bars = [
        {"date": "2024-03-01", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
        {"date": "2024-03-02", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"date": "2024-03-03", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
    ]
    monkeypatch.setattr(markets, "history", lambda symbol, range_="2y": {"bars": bars})
    _insert("ZFWD4", "breakout_20d", "buy", 500.0, 490.0, 520.0, "2024-03-01")

    out = forward_tracker.update_open()
    assert out["unfilled"] == 1
    assert _status("ZFWD4") == "unfilled"

    # And it must stop being rechecked forever once it's terminal.
    again = forward_tracker.update_open()
    assert again["closed"] == 0 and again["unfilled"] == 0


def test_a_freshly_fired_signal_with_no_new_bars_yet_stays_open(monkeypatch):
    bars = [{"date": "2024-04-01", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1}]
    monkeypatch.setattr(markets, "history", lambda symbol, range_="2y": {"bars": bars})
    _insert("ZFWD5", "breakout_20d", "buy", 100.0, 95.0, 110.0, "2024-04-01")

    out = forward_tracker.update_open()
    assert out["still_open"] >= 1
    assert _status("ZFWD5") == "open"


# --- stats: same expectancy math as backtest.py --------------------------------


def test_stats_reuses_backtests_own_metrics_math():
    with forward_tracker._db() as conn:
        for i, (r, outcome) in enumerate([(2.0, "target"), (-1.0, "stop")]):
            conn.execute(
                "INSERT INTO forward_signals (symbol, setup, side, entry, stop, target, signal_date, "
                "logged_at, status, fill, exit_price, exit_date, outcome, r, bars_held) "
                "VALUES (?,?,?,?,?,?,?,?, 'closed', ?, ?, ?, ?, ?, ?)",
                (f"ZFWD6{i}", "momentum_cross", "buy", 100.0, 95.0, 110.0, "2024-05-01",
                 "2024-01-01T00:00:00+00:00", 100.0, 105.0, "2024-05-02", outcome, r, 2),
            )

    out = forward_tracker.stats("momentum_cross")
    m = out["by_setup"]["momentum_cross"]
    assert m["expectancy_r"] == 0.5
    assert m["win_rate"] == 50.0


# --- dispatch is read-only and network-safe by default -------------------------


def test_dispatch_defaults_to_a_read_only_action_with_no_network_side_effects(monkeypatch):
    called = {"history": False}

    def fake_history(symbol, range_="1y"):
        called["history"] = True
        return {"bars": []}

    monkeypatch.setattr(markets, "history", fake_history)
    out = forward_tracker.dispatch()
    assert out["ok"] is True
    assert called["history"] is False, "the default action must never hit the network"


def test_unknown_action_reports_known_actions():
    out = forward_tracker.dispatch("nonsense")
    assert "error" in out and "scan" in out["actions"]
