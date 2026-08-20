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


def test_regime_risk_on_and_off():
    on = intel.regime(
        {
            "^VIX": {"price": 14.2, "change_pct": -4},
            "SPY": {"price": 560, "change_pct": 0.8},
            "QQQ": {"price": 480, "change_pct": 1.1},
            "XLK": {"price": 230, "change_pct": 1.4},
            "XLU": {"price": 70, "change_pct": -0.3},
        }
    )
    off = intel.regime(
        {
            "^VIX": {"price": 31, "change_pct": 12},
            "SPY": {"price": 540, "change_pct": -2.1},
            "QQQ": {"price": 450, "change_pct": -2.4},
            "XLK": {"price": 210, "change_pct": -3},
            "XLU": {"price": 72, "change_pct": 0.6},
        }
    )
    assert on["bias"] == "risk-on"
    assert off["bias"] == "risk-off"


def test_advise_stand_down_risk_off(monkeypatch, tmp_path):
    from app import ibkr, obsidian

    intel._scan_cache.clear()
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    obsidian.init_vault()
    monkeypatch.setattr(
        intel,
        "scan",
        lambda *a, **k: {
            "movers": [{"symbol": "NVDA", "change_pct": -4}],
            "count": 5,
            "quotes": [
                {"symbol": "SPY", "price": 540, "change_pct": -2.1, "source": "yahoo"},
                {"symbol": "QQQ", "price": 450, "change_pct": -2.4, "source": "yahoo"},
                {"symbol": "^VIX", "price": 31, "change_pct": 12, "source": "yahoo"},
                {"symbol": "XLK", "price": 210, "change_pct": -3, "source": "yahoo"},
                {"symbol": "XLU", "price": 72, "change_pct": 0.6, "source": "yahoo"},
            ],
        },
    )
    monkeypatch.setattr(intel.feeds, "snapshot", lambda: {"news": [{"source": "cnbc", "title": "Risk off"}], "updated": 1})
    monkeypatch.setattr(markets, "quote", lambda s: {"symbol": s, "price": 1, "change_pct": 0, "source": "yahoo"})
    monkeypatch.setattr(
        markets,
        "analyze",
        lambda s, range_="6mo": {"symbol": s, "quote": {"price": 540}, "stats": {"rsi14": 32, "trend": "down"}},
    )
    monkeypatch.setattr(intel, "_fear_greed", lambda: {"value": 18, "label": "Extreme Fear"})
    monkeypatch.setattr(intel, "_beast", lambda top, dte: {"ok": True, "picks": []})
    monkeypatch.setattr(ibkr, "permissions", lambda: {"ok": False, "can_trade": False, "hint": "TWS off"})
    monkeypatch.setattr(ibkr, "busy", lambda: True)
    out = intel.advise(top=4)
    assert out["ok"] is True
    assert out["regime"]["bias"] == "risk-off"
    assert out["ideas"][0]["action"] == "STAND DOWN"
    assert out["ibkr"]["can_trade"] is False
    assert out["verdict"] == "NO-GO"
    assert out["enter"] is False
    assert "no-go" in (out.get("spoken") or "").lower()
    assert out["decision"]["breakdown"]


def test_decide_enter_and_nogo():
    nogo = intel.decide(
        regime={"bias": "risk-off", "vix": 31, "why": "VIX 31 is elevated"},
        fear_greed={"value": 18, "label": "Fear"},
        spy={"stats": {"trend": "down", "rsi14": 32}},
        picks=[{"buyable": True, "grade": "A", "symbol": "NVDA", "strike": 180, "expiration": "20260821", "max_loss": 400}],
        ibkr={"can_trade": True, "hint": "live"},
        breadth={"up": 2, "n": 10},
    )
    go = intel.decide(
        regime={"bias": "risk-on", "vix": 14, "why": "calm tape"},
        fear_greed={"value": 52, "label": "Neutral"},
        spy={"stats": {"trend": "up", "rsi14": 55}},
        picks=[{"buyable": True, "grade": "A", "symbol": "NVDA", "strike": 180, "expiration": "20260821", "max_loss": 400}],
        ibkr={"can_trade": True, "hint": "live"},
        breadth={"up": 8, "n": 10},
    )
    assert nogo["enter"] is False and nogo["verdict"] == "NO-GO"
    assert go["enter"] is True and go["verdict"] == "ENTER"
    assert "enter" in go["spoken"].lower()


def test_market_advise_dispatch(monkeypatch):
    monkeypatch.setattr(intel, "advise", lambda **k: {"ok": True, "ideas": [{"action": "WATCH SPY"}]})
    out = markets.dispatch("advise")
    assert out["ok"] is True
    assert out["ideas"]


def test_broker_offline_without_keys(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ALPACA_KEY_ID", "")
    monkeypatch.setattr(config, "ALPACA_SECRET_KEY", "")
    st = broker.status()
    assert st["configured"] is False
    assert "confirm" in st["hint"].lower() or "ALPACA" in st["hint"]
