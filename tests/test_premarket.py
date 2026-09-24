"""Readiness is a report, never a lever: it must never clear a halt, raise a limit, or
place anything - only say plainly what would block an order right now.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config, ibkr, premarket, risk


def test_ready_when_everything_is_fine(monkeypatch):
    monkeypatch.setattr(ibkr, "probe", lambda: {"ok": True, "gateway_live": True, "port_name": "TWS live"})
    monkeypatch.setattr(ibkr, "open_orders", lambda: {"ok": True, "orders": []})
    monkeypatch.setattr(ibkr, "account", lambda: {"ok": True, "positions": []})
    monkeypatch.setattr(risk, "state", lambda: {
        "halted": False, "halt_reason": None, "loss_today": 0, "limit": 25000, "remaining": 25000,
        "day": "2026-09-24", "trades_today": 0, "consecutive_losses": 0,
    })
    monkeypatch.setattr(risk, "max_daily_loss", lambda: 25000.0)
    monkeypatch.setattr(risk, "max_trade_notional", lambda: 25000.0)
    monkeypatch.setattr(config, "WATCHLIST", ["SPY", "AAPL"])

    from app import markets

    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "price": 100.0})

    out = premarket.readiness()
    assert out["ready"] is True
    assert out["blockers"] == []


def test_tws_not_listening_is_a_blocker(monkeypatch):
    monkeypatch.setattr(ibkr, "probe", lambda: {"ok": False, "hint": "Start TWS and log in."})
    monkeypatch.setattr(risk, "state", lambda: {
        "halted": False, "halt_reason": None, "loss_today": 0, "limit": 25000, "remaining": 25000,
        "day": "2026-09-24", "trades_today": 0, "consecutive_losses": 0,
    })
    monkeypatch.setattr(risk, "max_daily_loss", lambda: 25000.0)
    monkeypatch.setattr(risk, "max_trade_notional", lambda: 25000.0)
    monkeypatch.setattr(config, "WATCHLIST", ["SPY"])

    from app import markets

    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "price": 100.0})

    out = premarket.readiness()
    assert out["ready"] is False
    assert any("TWS" in b for b in out["blockers"])


def test_a_sticky_halt_from_a_prior_day_is_surfaced_not_cleared(monkeypatch):
    monkeypatch.setattr(ibkr, "probe", lambda: {"ok": True, "gateway_live": True, "port_name": "TWS live"})
    monkeypatch.setattr(ibkr, "open_orders", lambda: {"ok": True, "orders": []})
    monkeypatch.setattr(ibkr, "account", lambda: {"ok": True, "positions": []})
    monkeypatch.setattr(risk, "state", lambda: {
        "halted": True, "halt_reason": "Daily loss limit reached: 25000 of 25000.",
        "loss_today": 25000, "limit": 25000, "remaining": 0,
        "day": "2026-09-23", "trades_today": 12, "consecutive_losses": 1,
    })
    monkeypatch.setattr(risk, "max_daily_loss", lambda: 25000.0)
    monkeypatch.setattr(risk, "max_trade_notional", lambda: 25000.0)
    monkeypatch.setattr(config, "WATCHLIST", ["SPY"])

    from app import markets

    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "price": 100.0})

    out = premarket.readiness()
    assert out["ready"] is False
    assert any("halted" in b.lower() for b in out["blockers"])
    # The report only reads state - resume is a human's call, made through risk itself.
    assert out["risk"]["halted"] is True


def test_misconfigured_risk_limits_are_flagged(monkeypatch):
    monkeypatch.setattr(ibkr, "probe", lambda: {"ok": True, "gateway_live": True, "port_name": "TWS live"})
    monkeypatch.setattr(ibkr, "open_orders", lambda: {"ok": True, "orders": []})
    monkeypatch.setattr(ibkr, "account", lambda: {"ok": True, "positions": []})
    monkeypatch.setattr(risk, "state", lambda: {
        "halted": False, "halt_reason": None, "loss_today": 0, "limit": 0, "remaining": 0,
        "day": "2026-09-24", "trades_today": 0, "consecutive_losses": 0,
    })
    monkeypatch.setattr(risk, "max_daily_loss", lambda: 0.0)
    monkeypatch.setattr(risk, "max_trade_notional", lambda: 25000.0)
    monkeypatch.setattr(config, "WATCHLIST", ["SPY"])

    from app import markets

    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "price": 100.0})

    out = premarket.readiness()
    assert out["ready"] is False
    assert any("MAX_DAILY_LOSS" in b for b in out["blockers"])


def test_data_source_failure_is_a_warning_not_a_blocker(monkeypatch):
    """A quote hiccup shouldn't stop trading outright - Yahoo/Stooq fail sometimes and
    history() already falls back; this is visibility, not a new gate.
    """
    monkeypatch.setattr(ibkr, "probe", lambda: {"ok": True, "gateway_live": True, "port_name": "TWS live"})
    monkeypatch.setattr(ibkr, "open_orders", lambda: {"ok": True, "orders": []})
    monkeypatch.setattr(ibkr, "account", lambda: {"ok": True, "positions": []})
    monkeypatch.setattr(risk, "state", lambda: {
        "halted": False, "halt_reason": None, "loss_today": 0, "limit": 25000, "remaining": 25000,
        "day": "2026-09-24", "trades_today": 0, "consecutive_losses": 0,
    })
    monkeypatch.setattr(risk, "max_daily_loss", lambda: 25000.0)
    monkeypatch.setattr(risk, "max_trade_notional", lambda: 25000.0)
    monkeypatch.setattr(config, "WATCHLIST", ["SPY"])

    from app import markets

    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "error": "Yahoo down; stooq: down"})

    out = premarket.readiness()
    assert out["ready"] is True
    assert any("Quote check" in w for w in out["warnings"])


def test_dispatch_routes_check():
    out = premarket.dispatch("check")
    assert "ready" in out
    err = premarket.dispatch("nonsense")
    assert "error" in err
