"""The governor must sit in front of the broker, not beside it.

A limit that a standing grant or a confirmed=True flag can step around is decoration.
These test the wiring rather than the arithmetic: that the gate is reached first, that
nothing legitimate skips it, and that it never blocks the way OUT of a position.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import ibkr


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: True)


def _deny(monkeypatch, reason="halted for the test"):
    from app import risk

    monkeypatch.setattr(risk, "check", lambda notional=0, kind="trade": {
        "allowed": False, "reason": reason, "halted": True, "state": {"halted": True}})


def test_a_halt_blocks_a_new_option_order(live, monkeypatch):
    _deny(monkeypatch)
    out = ibkr._need_confirm("ibkr_option", {"symbol": "AAPL", "qty": 1, "strike": 100},
                             confirmed=False, confirm_token=None)
    assert out and "risk governor" in out["error"]


def test_confirmed_true_does_not_skip_the_governor(live, monkeypatch):
    """An explicit confirm is consent to a trade, not consent to trade past the limit."""
    _deny(monkeypatch)
    out = ibkr._need_confirm("ibkr_stock", {"symbol": "AAPL", "qty": 100, "limit": 50},
                             confirmed=True, confirm_token=None)
    assert out is not None, "confirmed=True must not bypass the day limit"


def test_a_standing_grant_does_not_skip_the_governor(live, monkeypatch):
    """A grant authorises a KIND of order. It does not authorise exceeding the day limit."""
    from app import trust

    monkeypatch.setattr(trust, "check_and_spend", lambda kind, payload: {"trusted": True})
    _deny(monkeypatch)
    out = ibkr._need_confirm("ibkr_option", {"symbol": "AAPL", "qty": 1, "strike": 100},
                             confirmed=False, confirm_token=None)
    assert out is not None, "a trust grant must not outrank the governor"


def test_a_valid_confirm_token_does_not_skip_the_governor(live, monkeypatch):
    _deny(monkeypatch)
    out = ibkr._need_confirm("ibkr_stock", {"symbol": "AAPL", "qty": 1, "limit": 10},
                             confirmed=False, confirm_token="whatever")
    assert out is not None


def test_closing_a_position_is_never_blocked(live, monkeypatch):
    """A halt that traps you in a losing position turns the rail into the hazard."""
    _deny(monkeypatch)
    out = ibkr._need_confirm("ibkr_close", {"symbol": "AAPL", "qty": 100},
                             confirmed=True, confirm_token=None)
    assert out is None, "closing must always be reachable"


def test_every_exposure_increasing_kind_is_gated(live, monkeypatch):
    _deny(monkeypatch)
    for kind in ("ibkr_option", "ibkr_stock", "ibkr_bracket"):
        out = ibkr._need_confirm(kind, {"symbol": "X", "qty": 1, "limit": 10},
                                 confirmed=True, confirm_token=None)
        assert out is not None, f"{kind} reached the broker without passing the governor"


def test_paper_trading_is_not_governed(monkeypatch):
    """The governor is about real money; paper must stay frictionless."""
    monkeypatch.setattr(ibkr, "gateway_is_live", lambda: False)
    _deny(monkeypatch)
    assert ibkr._need_confirm("ibkr_option", {"symbol": "X", "qty": 1}, confirmed=False,
                              confirm_token=None) is None


def test_option_notional_counts_the_contract_multiplier():
    """One contract is a hundred shares. Missing that under-reports exposure 100x."""
    assert ibkr._estimate_notional("ibkr_option", {"qty": 2, "limit": 5.0}) == 1000.0


def test_notional_falls_back_to_the_strike_when_no_price_is_known():
    """Erring high is correct: under-estimating exposure is the dangerous direction."""
    assert ibkr._estimate_notional("ibkr_option", {"qty": 1, "strike": 250}) == 25_000.0


def test_a_broken_risk_module_does_not_wedge_the_desk(live, monkeypatch):
    """Fail-open is deliberate here: the confirm-token rail still stands behind it."""
    import builtins

    real = builtins.__import__

    def boom(name, *a, **k):
        if name == "risk" or name.endswith(".risk"):
            raise ImportError("risk is broken")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    out = ibkr._risk_gate("ibkr_option", {"symbol": "X", "qty": 1, "strike": 10})
    assert out is None
