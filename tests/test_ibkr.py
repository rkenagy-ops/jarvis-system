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


def test_permissions_blocked_when_tws_down(monkeypatch):
    ibkr._probe_val = None
    monkeypatch.setattr(ibkr, "port_open", lambda p: False)
    monkeypatch.setattr(ibkr, "tws_state", lambda: {"process": False, "login_screen": False, "window": "", "pid": None})
    out = ibkr.permissions()
    assert out.get("can_trade") is False
    assert out.get("needs_confirm") is True
    assert out.get("stocks") is False


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


# --- bracket / cancel / close / pnl -----------------------------------------


def test_bracket_rejects_inverted_stop_for_buy():
    """A buy bracket with the stop above entry is not a bracket."""
    out = ibkr.place_bracket("AAPL", "buy", 10, entry=100.0, stop=110.0, target=120.0)
    assert "error" in out
    assert "stop < entry < target" in out["error"]


def test_bracket_rejects_inverted_stop_for_sell():
    out = ibkr.place_bracket("AAPL", "sell", 10, entry=100.0, stop=90.0, target=80.0)
    assert "error" in out
    assert "target < entry < stop" in out["error"]


def test_bracket_accepts_correct_sides(monkeypatch):
    """Valid geometry should get past validation to the confirm gate."""
    from app import memory as mem

    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)
    monkeypatch.setattr(
        mem, "create_pending", lambda kind, payload, ttl_sec=180: {"confirm_token": "tok", "kind": kind}
    )
    monkeypatch.setattr(mem, "set_fact", lambda *a, **k: None)

    out = ibkr.place_bracket("AAPL", "buy", 10, entry=100.0, stop=95.0, target=110.0)
    assert out.get("blocked") is True
    assert out.get("confirm_token") == "tok"


def test_bracket_rejects_bad_numbers():
    assert "error" in ibkr.place_bracket("AAPL", "buy", 10, entry="x", stop=1, target=2)
    assert "error" in ibkr.place_bracket("AAPL", "buy", 0, entry=1, stop=0.5, target=2)
    assert "error" in ibkr.place_bracket("", "buy", 10, entry=1, stop=0.5, target=2)
    assert "error" in ibkr.place_bracket("AAPL", "buy", 10, entry=0, stop=0, target=0)


def test_cancel_needs_a_target(monkeypatch):
    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    out = ibkr.cancel_order()
    assert "error" in out
    assert "all_orders" in out["error"]


def test_cancel_rejects_non_numeric_id(monkeypatch):
    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    out = ibkr.cancel_order("abc")
    assert "error" in out and "numeric" in out["error"]


def test_cancel_is_not_confirm_gated(monkeypatch):
    """Pulling an order reduces exposure — it must not wait on a token."""
    cancelled = []

    class FakeOrder:
        orderId = 7

    class FakeTrade:
        order = FakeOrder()

    class FakeIB:
        @staticmethod
        def openTrades():
            return [FakeTrade()]

        @staticmethod
        def cancelOrder(o):
            cancelled.append(o.orderId)

        @staticmethod
        def sleep(_):
            return None

    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "_call", lambda fn, **k: fn(FakeIB()))
    from app import memory as mem

    monkeypatch.setattr(mem, "remember", lambda *a, **k: None)

    out = ibkr.cancel_order(7)
    assert out["ok"] is True
    assert out["cancelled"] == [7]
    assert cancelled == [7]


def test_close_position_reports_when_flat(monkeypatch):
    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "_call", lambda fn, **k: {})
    out = ibkr.close_position("AAPL")
    assert out["ok"] is False
    assert "No open position" in out["error"]


def test_close_position_requires_symbol():
    assert "error" in ibkr.close_position("")


def test_pnl_totals(monkeypatch):
    class Item:
        def __init__(self, sym, u, r):
            self.contract = type("C", (), {"localSymbol": sym, "symbol": sym, "secType": "STK"})()
            self.position = 10
            self.averageCost = 100
            self.marketPrice = 105
            self.marketValue = 1050
            self.unrealizedPNL = u
            self.realizedPNL = r

    class FakeIB:
        @staticmethod
        def portfolio():
            return [Item("AAPL", 50.0, 10.0), Item("MSFT", -20.0, 5.0)]

    monkeypatch.setattr(ibkr, "port_open", lambda p: True)
    monkeypatch.setattr(ibkr, "_call", lambda fn, **k: fn(FakeIB()))
    out = ibkr.pnl()
    assert out["ok"] is True
    assert out["total_unrealized"] == 30.0
    assert out["total_realized"] == 15.0
    # worst first
    assert out["positions"][0]["symbol"] == "MSFT"


def test_dispatch_routes_new_actions(monkeypatch):
    monkeypatch.setattr(ibkr, "open_orders", lambda: {"ok": True, "marker": "orders"})
    monkeypatch.setattr(ibkr, "pnl", lambda: {"ok": True, "marker": "pnl"})
    assert ibkr.dispatch("orders")["marker"] == "orders"
    assert ibkr.dispatch("pnl")["marker"] == "pnl"


def test_explicit_mode_is_not_overridden_by_inference(monkeypatch):
    """market action=ibkr mode=bracket must not be rewritten to a plain order."""
    from app import markets

    seen = {}

    def fake_dispatch(action, **kwargs):
        seen["mode"] = action
        return {"ok": True}

    monkeypatch.setattr(ibkr, "dispatch", fake_dispatch)
    markets.dispatch(
        "ibkr", mode="bracket", symbol="AAPL", side="buy", qty=10, entry=100, stop=95, target=110
    )
    assert seen["mode"] == "bracket"

    # cancel with a stray side present must still cancel
    markets.dispatch("ibkr", mode="cancel", symbol="AAPL", side="buy", order_id=3)
    assert seen["mode"] == "cancel"

    # with no explicit mode, inference still works as before
    markets.dispatch("ibkr", symbol="AAPL", side="buy", qty=1)
    assert seen["mode"] == "order"
    markets.dispatch("ibkr", symbol="AAPL", expiry="20260101", strike=100)
    assert seen["mode"] == "option"


def test_ib_names_prefers_ib_async(monkeypatch):
    """ib_insync is archived; ib_async is the maintained fork with the same API."""
    import sys as _sys
    import types

    fake_async = types.ModuleType("ib_async")
    fake_async.Stock = "ASYNC_STOCK"
    fake_insync = types.ModuleType("ib_insync")
    fake_insync.Stock = "INSYNC_STOCK"

    monkeypatch.setitem(_sys.modules, "ib_async", fake_async)
    monkeypatch.setitem(_sys.modules, "ib_insync", fake_insync)
    assert ibkr._ib_names("Stock") == ("ASYNC_STOCK",)
    assert ibkr.ib_backend() == "ib_async"


def test_ib_names_falls_back_to_ib_insync(monkeypatch):
    """Existing installs with only ib_insync must keep working."""
    import builtins
    import sys as _sys
    import types

    fake_insync = types.ModuleType("ib_insync")
    fake_insync.Stock = "INSYNC_STOCK"
    monkeypatch.setitem(_sys.modules, "ib_insync", fake_insync)
    _sys.modules.pop("ib_async", None)

    real_import = builtins.__import__

    def no_ib_async(name, *a, **k):
        if name == "ib_async":
            raise ImportError("no ib_async")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_ib_async)
    assert ibkr._ib_names("Stock") == ("INSYNC_STOCK",)
    assert "archived" in ibkr.ib_backend()
