from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import broker, intel, markets


def test_universe_all_covers_asset_classes():
    u = intel.universe("all")
    assert "SPY" in u and "XLK" in u and "EURUSD=X" in u and "BTC-USD" in u
    assert "CL=F" in u


def test_news_ticker_link():
    hits = intel._tickers_in("NVIDIA and Apple rally as Bitcoin jumps")
    assert "NVDA" in hits and "AAPL" in hits and "BTC-USD" in hits


def test_scan_uses_quotes(monkeypatch):
    intel._scan_cache.clear()
    monkeypatch.setattr(
        markets,
        "watchlist",
        lambda symbols=None: [{"symbol": "NVDA", "price": 1, "change_pct": 3.2}, {"symbol": "MSFT", "price": 1, "change_pct": 0.1}],
    )
    out = intel.scan("mega", threshold=1.5)
    assert out["movers"][0]["symbol"] == "NVDA"
    assert out["count"] == 2


def test_broker_offline_without_keys(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ALPACA_KEY_ID", "")
    monkeypatch.setattr(config, "ALPACA_SECRET_KEY", "")
    st = broker.status()
    assert st["configured"] is False
    assert "confirm" in st["hint"].lower() or "ALPACA" in st["hint"]
