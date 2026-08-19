from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import ibkr, marketbeast


def test_ibkr_host_is_loopback():
    assert ibkr.host() == "127.0.0.1"
    assert ibkr.probe().get("adapter") == "persistent-tws-2026"


def test_gateway_live_requires_open_port(monkeypatch):
    ibkr._probe_val = None
    monkeypatch.setattr(ibkr, "port_open", lambda p: False)
    monkeypatch.setattr(ibkr, "tws_state", lambda: {"process": False, "login_screen": False, "window": "", "pid": None})
    from app import config

    monkeypatch.setattr(config, "IBKR_LIVE", True)
    assert ibkr.gateway_is_live() is False
    assert ibkr.live_cash() is False
    out = ibkr.account()
    assert "error" in out
    assert "not running" in out["error"].lower() or "login" in out["error"].lower()


def test_login_screen_named_in_account_error(monkeypatch):
    ibkr._probe_val = None
    monkeypatch.setattr(ibkr, "port_open", lambda p: False)
    monkeypatch.setattr(
        ibkr,
        "tws_state",
        lambda: {"process": True, "login_screen": True, "window": "Login", "pid": 1, "path": r"C:\Jts\tws.exe"},
    )
    out = ibkr.account()
    assert "error" in out
    assert "login" in out["error"].lower()


def test_live_option_blocked_without_confirm(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    monkeypatch.setattr(ibkr, "port", lambda: 7496)
    out = ibkr.place_option("NVDA", "20260821", 180, "C", 1)
    assert out.get("blocked") is True
    assert "token" in out or "confirm" in (out.get("reason") or "").lower()


def test_live_ibkr_does_not_need_alpaca_trading_mode(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "IBKR_LIVE", True)
    monkeypatch.setattr(config, "TRADING_MODE", "paper")
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    assert ibkr.allow_live_orders() is True


def test_stock_live_blocked_without_confirm(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    monkeypatch.setattr(ibkr, "port", lambda: 7496)
    out = ibkr.place_stock("AAPL", "buy", 1)
    assert out.get("blocked") is True
    assert out.get("confirm_token")


def test_grade_and_enrich():
    wide = marketbeast.enrich(
        {
            "symbol": "XYZ",
            "strike": 10,
            "option_price": 0.05,
            "delta": 0.05,
            "combined_score": 0.2,
            "price": 10,
        },
        {"bid": 0.01, "ask": 0.20, "oi": 5},
    )
    tight = marketbeast.enrich(
        {
            "symbol": "NVDA",
            "strike": 180,
            "option_price": 4.0,
            "delta": 0.48,
            "combined_score": 0.8,
            "price": 182,
        },
        {"bid": 3.90, "ask": 4.10, "oi": 800, "type": "ATM"},
    )
    assert wide["grade"] == "WATCH"
    assert wide["buyable"] is False
    assert tight["grade"] in {"A", "B"}
    assert tight["buyable"] is True
    assert tight["breakeven"] == 184.0
    assert tight["max_loss"] == 400.0


def test_marketbeast_root_detected():
    info = marketbeast.ready()
    assert info["ok"] is True
    assert info.get("v9") is True
    assert "scanner.py" in (info.get("scanner") or "")


def test_paper_option_buy(tmp_path, monkeypatch):
    from app import markets, config

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(config, "PAPER_CASH", 100000)
    markets.init()
    out = markets.paper_option_buy("NVDA", "20260821", 180, right="C", qty=1, debit=2.5)
    assert out["ok"]
    assert out["cost"] == 250
    book = markets.list_paper_options()
    assert book and book[0]["symbol"] == "NVDA"


def test_bad_expiry():
    monkeypatch_port = ibkr.port
    out = ibkr.place_option("NVDA", "08-21", 180, "C", 1)
    assert "error" in out
    _ = monkeypatch_port
