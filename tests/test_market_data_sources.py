"""markets.history() bars were missing 'date' entirely on every real (non-test) call -
backtest.py and forward_tracker.py both key signals off it. Also covers the Stooq
fallback (Yahoo's unauthenticated chart endpoint 403s/rate-limits in practice) and the
OHLCV cache/batch path that makes scanning more than a handful of symbols survivable.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import markets


class _FakeResponse:
    def __init__(self, *, json_data=None, text_data=None, status=200):
        self._json = json_data
        self.text = text_data or ""
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def __call__(self, *a, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None):
        return self._response


def _yahoo_payload(dates_and_closes):
    ts = []
    closes = []
    opens = []
    highs = []
    lows = []
    vols = []
    for date_s, close in dates_and_closes:
        import datetime as dt

        t = int(dt.datetime.combine(dt.date.fromisoformat(date_s), dt.time(), tzinfo=dt.timezone.utc).timestamp())
        ts.append(t)
        closes.append(close)
        opens.append(close - 0.5)
        highs.append(close + 1)
        lows.append(close - 1)
        vols.append(1_000_000)
    return {
        "chart": {
            "result": [{
                "timestamp": ts,
                "indicators": {"quote": [{"close": closes, "open": opens, "high": highs, "low": lows, "volume": vols}]},
            }]
        }
    }


# --- the date bug --------------------------------------------------------------


def test_yahoo_bars_carry_a_real_iso_date(monkeypatch):
    payload = _yahoo_payload([("2024-01-02", 100.0), ("2024-01-03", 101.5)])
    monkeypatch.setattr(markets, "_yahoo_chart", lambda symbol, range_="6mo", interval="1d": payload)

    out = markets.history("AAPL", "1y")
    assert out["source"] == "yahoo"
    assert [b["date"] for b in out["bars"]] == ["2024-01-02", "2024-01-03"]
    # backtest.py and forward_tracker.py both key off this field by name.
    assert all(b.get("date") for b in out["bars"])


# --- Stooq fallback --------------------------------------------------------------


def test_yahoo_failure_falls_back_to_stooq(monkeypatch):
    def boom(symbol, range_="6mo", interval="1d"):
        raise RuntimeError("Yahoo is down")

    monkeypatch.setattr(markets, "_yahoo_chart", boom)
    csv = "Date,Open,High,Low,Close,Volume\n2024-01-02,99,101,98,100,1000000\n2024-01-03,100,103,99,101.5,1200000\n"
    monkeypatch.setattr(markets.httpx, "Client", _FakeClient(_FakeResponse(text_data=csv)))

    out = markets.history("AAPL", "1y")
    assert out["source"] == "stooq"
    assert out["bars"][-1]["close"] == 101.5
    assert out["bars"][-1]["date"] == "2024-01-03"


def test_both_sources_failing_returns_an_error_not_an_exception(monkeypatch):
    def boom(symbol, range_="6mo", interval="1d"):
        raise RuntimeError("Yahoo is down")

    monkeypatch.setattr(markets, "_yahoo_chart", boom)
    monkeypatch.setattr(markets.httpx, "Client", _FakeClient(_FakeResponse(status=403, text_data="blocked")))

    out = markets.history("ZZZZZZ", "1y")
    assert "error" in out
    assert "Yahoo is down" in out["error"]


def test_stooq_symbol_mapping_adds_us_suffix():
    assert markets._stooq_symbol("AAPL") == "aapl.us"
    assert markets._stooq_symbol("BTC-USD") == "BTC-USD"


# --- OHLCV cache ------------------------------------------------------------------


def test_history_cached_reads_the_cache_without_hitting_yahoo_again(monkeypatch):
    calls = {"n": 0}

    def fake_history(symbol, range_="6mo"):
        calls["n"] += 1
        return {"symbol": symbol, "bars": [{"date": "2024-01-02", "close": 100.0}], "count": 1, "source": "yahoo"}

    monkeypatch.setattr(markets, "history", fake_history)

    first = markets.history_cached("ZCACHE1", "1y")
    second = markets.history_cached("ZCACHE1", "1y")
    assert calls["n"] == 1, "the second call within the TTL must not refetch"
    assert second.get("cached") is True
    assert first["bars"] == second["bars"]


def test_history_cached_refetches_once_stale(monkeypatch):
    calls = {"n": 0}

    def fake_history(symbol, range_="6mo"):
        calls["n"] += 1
        return {"symbol": symbol, "bars": [{"date": "2024-01-0" + str(calls["n"]), "close": float(calls["n"])}],
                "count": 1, "source": "yahoo"}

    monkeypatch.setattr(markets, "history", fake_history)

    markets.history_cached("ZCACHE2", "1y", max_age=0)
    second = markets.history_cached("ZCACHE2", "1y", max_age=0)
    assert calls["n"] == 2, "max_age=0 means every call is stale"
    assert second.get("cached") is not True


# --- batch fetch --------------------------------------------------------------


def test_history_batch_skips_the_network_for_already_cached_symbols(monkeypatch):
    markets._cache_put("ZBATCH1", "1y", {"symbol": "ZBATCH1", "bars": [{"date": "2024-01-02", "close": 5.0}], "source": "yahoo"})

    called = {"download": False}

    class _FakeYF:
        @staticmethod
        def download(**kwargs):
            called["download"] = True
            raise AssertionError("should not be called when everything is cached")

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)

    out = markets.history_batch(["ZBATCH1"], "1y")
    assert out["ZBATCH1"]["cached"] is True
    assert called["download"] is False


def test_history_batch_falls_back_to_single_fetch_when_yfinance_has_nothing(monkeypatch):
    class _EmptyFrame:
        empty = True

    class _FakeYF:
        @staticmethod
        def download(**kwargs):
            return _EmptyFrame()

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)
    monkeypatch.setattr(markets, "history", lambda symbol, range_="6mo": {
        "symbol": symbol, "bars": [{"date": "2024-01-02", "close": 42.0}], "count": 1, "source": "yahoo",
    })

    out = markets.history_batch(["ZBATCH2"], "1y")
    assert out["ZBATCH2"]["bars"][0]["close"] == 42.0
