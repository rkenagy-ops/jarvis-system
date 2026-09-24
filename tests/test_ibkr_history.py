"""'She could use the charts from the live TWS feed' - reqHistoricalData against the
same session the platform's own charts are drawn from, not a third-party endpoint.
Read-only: never touches an order or a position.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import ibkr, markets


class _FakeBar:
    def __init__(self, date, o, h, l, c, v):
        self.date = date
        self.open, self.high, self.low, self.close, self.volume = o, h, l, c, v


class _FakeStock:
    def __init__(self, symbol, exchange, currency):
        self.symbol = symbol


def _fake_ib_names(*names):
    return tuple(_FakeStock if n == "Stock" else None for n in names)


def test_history_bars_converts_ibkr_bars_to_the_shared_bar_shape(monkeypatch):
    class FakeIB:
        @staticmethod
        def qualifyContracts(contract):
            return [contract]

        @staticmethod
        def reqHistoricalData(contract, **kwargs):
            return [
                _FakeBar("2024-01-02", 99.0, 101.0, 98.0, 100.0, 1_000_000),
                _FakeBar("2024-01-03", 100.0, 103.0, 99.0, 101.5, 1_200_000),
            ]

    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "busy", lambda: False)
    monkeypatch.setattr(ibkr, "_ib_names", _fake_ib_names)
    monkeypatch.setattr(ibkr, "_call", lambda fn, **k: fn(FakeIB()))

    out = ibkr.history_bars("AAPL", "1y")
    assert out["source"] == "ibkr"
    assert out["bars"][-1]["close"] == 101.5
    assert out["bars"][-1]["date"] == "2024-01-03"
    assert out["bars"][0]["date"] == "2024-01-02"


def test_history_bars_reports_unreachable_tws_as_an_error_not_an_exception(monkeypatch):
    monkeypatch.setattr(ibkr, "port_open", lambda p: False)
    out = ibkr.history_bars("AAPL", "1y")
    assert "error" in out


def test_history_bars_rejects_crypto_and_index_symbols(monkeypatch):
    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "busy", lambda: False)
    assert "error" in ibkr.history_bars("BTC-USD", "1y")
    assert "error" in ibkr.history_bars("^VIX", "1y")


def test_history_bars_reports_no_data_as_an_error(monkeypatch):
    class FakeIB:
        @staticmethod
        def qualifyContracts(contract):
            return [contract]

        @staticmethod
        def reqHistoricalData(contract, **kwargs):
            return []

    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "busy", lambda: False)
    monkeypatch.setattr(ibkr, "_ib_names", _fake_ib_names)
    monkeypatch.setattr(ibkr, "_call", lambda fn, **k: fn(FakeIB()))

    out = ibkr.history_bars("ZZZZZZ", "1y")
    assert "error" in out


# --- markets.history() tries IBKR first, falls through cleanly -----------------


def test_markets_history_prefers_ibkr_when_reachable(monkeypatch):
    from app import ibkr as ibkr_mod

    monkeypatch.setattr(ibkr_mod, "busy", lambda: False)
    monkeypatch.setattr(ibkr_mod, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr_mod, "history_bars", lambda symbol, range_: {
        "symbol": symbol, "bars": [{"date": "2024-01-02", "close": 55.0}], "count": 1, "source": "ibkr",
    })

    out = markets.history("AAPL", "1y")
    assert out["source"] == "ibkr"
    assert out["bars"][0]["close"] == 55.0


def test_markets_history_falls_through_to_yahoo_when_ibkr_has_nothing(monkeypatch):
    from app import ibkr as ibkr_mod

    monkeypatch.setattr(ibkr_mod, "busy", lambda: False)
    monkeypatch.setattr(ibkr_mod, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr_mod, "history_bars", lambda symbol, range_: {"error": "no data"})
    monkeypatch.setattr(markets, "_yahoo_history", lambda symbol, range_: {
        "symbol": symbol, "bars": [{"date": "2024-01-02", "close": 42.0}], "count": 1, "source": "yahoo",
    })

    out = markets.history("AAPL", "1y")
    assert out["source"] == "yahoo"


def test_markets_history_skips_ibkr_entirely_when_tws_is_closed(monkeypatch):
    from app import ibkr as ibkr_mod

    monkeypatch.setattr(ibkr_mod, "port_open", lambda p: False)
    called = {"ibkr": False}
    monkeypatch.setattr(ibkr_mod, "history_bars", lambda symbol, range_: called.update(ibkr=True) or {})
    monkeypatch.setattr(markets, "_yahoo_history", lambda symbol, range_: {
        "symbol": symbol, "bars": [{"date": "2024-01-02", "close": 1.0}], "count": 1, "source": "yahoo",
    })

    markets.history("AAPL", "1y")
    assert called["ibkr"] is False, "no TWS running means don't even try the IBKR path"


def test_markets_history_an_ibkr_exception_never_breaks_the_fallback(monkeypatch):
    from app import ibkr as ibkr_mod

    monkeypatch.setattr(ibkr_mod, "busy", lambda: False)
    monkeypatch.setattr(ibkr_mod, "port_open", lambda p: True)

    def boom(symbol, range_):
        raise RuntimeError("TWS died mid-request")

    monkeypatch.setattr(ibkr_mod, "history_bars", boom)
    monkeypatch.setattr(markets, "_yahoo_history", lambda symbol, range_: {
        "symbol": symbol, "bars": [{"date": "2024-01-02", "close": 1.0}], "count": 1, "source": "yahoo",
    })

    out = markets.history("AAPL", "1y")
    assert out["source"] == "yahoo"
